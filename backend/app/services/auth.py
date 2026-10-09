import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from io import BytesIO

from fastapi import Depends, HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import serialize_process_local_timestamp
from app.db import get_db
from app.models.auth import (
    AuthAuditLog,
    AuthIamState,
    AuthPasswordResetRequest,
    AuthPermissionMetadata,
    AuthPermission,
    AuthRegistrationRequest,
    AuthRole,
    AuthRoleBindingMetadata,
    AuthRoleMetadata,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserAuthorizationRevision,
    AuthUserPermissionOverride,
    AuthUserRole,
    EmployeeProfile,
    SystemNotification,
)
from app.schemas.auth import (
    AuthMeResponse,
    ChangePasswordRequest,
    PasswordResetClaimCompleteRequest,
    PasswordResetClaimCompleteResponse,
    PasswordResetClaimResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services.iam_scope import (
    CROSS_FACTORY_OPERATE_SCOPE,
    CROSS_FACTORY_READ_LOCAL_ONLY_PERMISSION_CODES,
    CROSS_FACTORY_READ_SCOPE,
    OPERATE_ACCESS_KIND,
    OWN_FACTORY_SCOPE,
    READ_ACCESS_KIND,
    SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES,
    VALID_ACCESS_KINDS,
    VALID_SCOPE_MODES,
    default_permission_access_kind,
)
from app.services.permission_codes import (
    WAREHOUSE_OPERATIONS_PERMISSION_CODES,
    APPLICATION_PERMISSION_CODES,
    CUTTING_OPS_PERMISSION_CODES,
    CARTON_SUPPLIER_PERMISSION_CODES,
    UV_OPS_PERMISSION_CODES,
    INTERNAL_QUOTE_PERMISSION_CODES,
    INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE,
    INTERNAL_QUOTE_SECTION_CODES,
)
from app.services.system_positions import (
    CARTON_QC_WORKSPACE_PERMISSION_CODES,
    CARTON_QC_WORKSPACE_POSITION_ROLE_IDS,
    SYSTEM_POSITION_DEFINITIONS,
    get_system_position,
)
from app.services.system_position_reconcile import reconcile_system_position_catalog

SESSION_COOKIE_NAME = "rr_session"
PASSWORD_RESET_CLAIM_COOKIE_NAME = "rr_password_reset_claim"
PASSWORD_RESET_CLAIM_COOKIE_MAX_AGE_SECONDS = 48 * 60 * 60
logger = logging.getLogger(__name__)
LEGACY_EXPORT_COMPAT_MARKER = "legacy_export_compat_v1_completed"
LEGACY_EXPORT_COMPAT_PERMISSION = "molding_sample:export"
RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER = "raw_material_write_default_grant_v1_completed"
RAW_MATERIAL_WRITE_PERMISSION = "molding_sample:raw_material_write"
RAW_MATERIAL_WRITE_DEFAULT_ROLE_IDS = ("engineer", "engineering_supervisor", "warehouse_keeper")
INTERNAL_QUOTE_DEFAULT_GRANT_MARKER = "internal_quote_p1_default_grant_v1_completed"
INTERNAL_QUOTE_P2_REFERENCE_GRANT_MARKER = "internal_quote_p2_reference_grant_v1_completed"
INTERNAL_QUOTE_REFERENCE_PERMISSION = "internal_quote:reference_manage"
INTERNAL_QUOTE_REFERENCE_DEFAULT_ROLE_IDS = ("sales_customer_supervisor", "engineering_supervisor")
INTERNAL_QUOTE_P3_EXPORT_GRANT_MARKER = "internal_quote_p3_export_grant_v1_completed"
INTERNAL_QUOTE_EXPORT_PERMISSION = "internal_quote:export"
INTERNAL_QUOTE_EXPORT_DEFAULT_ROLE_IDS = ("sales_customer_owner", "sales_customer_supervisor")
INTERNAL_QUOTE_P4_RELEASE_GRANT_MARKER = "internal_quote_p4_release_grant_v1_completed"
INTERNAL_QUOTE_BASELINE_GRANT_MARKER = "internal_quote_baseline_grant_v1_completed"
INTERNAL_QUOTE_CUSTOMER_GRANT_MARKER = "internal_quote_customer_grant_v2_completed"
INTERNAL_QUOTE_CUSTOMER_PERMISSION = "internal_quote:customer_manage"
INTERNAL_QUOTE_CUSTOMER_DEFAULT_ROLE_IDS = (
    "sales_customer_supervisor",
    "engineering_supervisor",
)
INTERNAL_QUOTE_SELF_REVIEW_GRANT_MARKER = "internal_quote_self_review_grant_v1_completed"
INTERNAL_QUOTE_SELF_REVIEW_DEFAULT_ROLE_IDS = ("sales_customer_supervisor",)
CUSTOMER_ORDER_CONTROL_GRANT_MARKER = "customer_order_control_grant_v1_completed"
CUSTOMER_PRICE_SETTINGS_GRANT_MARKER = "customer_price_settings_grant_v1_completed"
CUSTOMER_PRICE_SETTINGS_ROLE_PERMISSIONS = {
    "sales_customer_owner": ("customer_price:settings_read",),
    "sales_customer_supervisor": (
        "customer_price:settings_read",
        "customer_price:settings_manage",
    ),
}
CUSTOMER_ORDER_CONTROL_ROLE_PERMISSIONS = {
    "sales_customer_owner": ("customer_order:duplicate_confirm",),
    "sales_customer_supervisor": (
        "customer_order:duplicate_confirm",
        "customer_order:audit_read",
    ),
}
INTERNAL_QUOTE_BASELINE_ROLE_PERMISSIONS = {
    "sales_customer_owner": ("internal_quote:baseline_read",),
    "sales_customer_supervisor": (
        "internal_quote:baseline_read",
        "internal_quote:baseline_manage",
    ),
}
INTERNAL_QUOTE_P4_RELEASE_ROLE_PERMISSIONS = {
    "sales_customer_owner": ("internal_quote:final_submit",),
    "sales_customer_supervisor": (
        "internal_quote:final_submit",
        "internal_quote:final_approve",
    ),
}
DEFAULT_PASSWORD = "123456"
PASSWORD_HASH_ITERATIONS = 160_000
SESSION_HOURS = 12
MIN_SEED_ADMIN_PASSWORD_LENGTH = 12
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW_MINUTES = 15
LOGIN_LOCKED_MESSAGE = f"登录失败次数过多，请 {LOGIN_FAILURE_WINDOW_MINUTES} 分钟后再试"
BAD_CREDENTIALS_MESSAGE = "用户名或密码错误"
PASSWORD_RESET_PUBLIC_MESSAGE = (
    "申请已提交。请保留当前浏览器，管理员审核通过后可在此直接设置新密码。"
)
PASSWORD_RESET_RATE_LIMIT = 5
PASSWORD_RESET_RATE_WINDOW_MINUTES = 15
MIN_ACCOUNT_PASSWORD_LENGTH = 6
DUMMY_PASSWORD_SALT = "00000000000000000000000000000000"
PASSWORD_CHINESE_MESSAGE = "密码不能包含中文，请使用英文、数字或符号"
AVATAR_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
AVATAR_MAX_PIXELS = 16_000_000
AVATAR_OUTPUT_SIZE = 256
AVATAR_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
CHINESE_CHARACTER_RANGES = (
    ("\u3400", "\u4dbf"),
    ("\u4e00", "\u9fff"),
    ("\uf900", "\ufaff"),
)

APPLICATION_PERMISSIONS = list(APPLICATION_PERMISSION_CODES)

INTERNAL_QUOTE_COMMON_PERMISSIONS = {
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
}
INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS = {
    "sales_customer_owner": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:create",
        "internal_quote:clone",
        "internal_quote:header_edit",
        "internal_quote:baseline_read",
        "internal_quote:sales_edit",
        "internal_quote:export",
        "internal_quote:final_submit",
    },
    "sales_customer_supervisor": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:create",
        "internal_quote:clone",
        "internal_quote:header_edit",
        "internal_quote:archive",
        "internal_quote:baseline_read",
        "internal_quote:baseline_manage",
        "internal_quote:customer_manage",
        "internal_quote:sales_edit",
        "internal_quote:sales_review",
        "internal_quote:reference_manage",
        "internal_quote:export",
        "internal_quote:final_submit",
        "internal_quote:final_approve",
        INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE,
    },
    "engineer": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:create",
        "internal_quote:clone",
        "internal_quote:engineering_edit",
    },
    "engineering_supervisor": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:create",
        "internal_quote:clone",
        "internal_quote:customer_manage",
        "internal_quote:engineering_edit",
        "internal_quote:engineering_review",
        "internal_quote:reference_manage",
    },
    "molding_clerk": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:molding_edit",
    },
    "molding_supervisor": {
        *INTERNAL_QUOTE_COMMON_PERMISSIONS,
        "internal_quote:molding_edit",
        "internal_quote:molding_review",
    },
}

DEFAULT_ROLES = [
    ("group_molding_readonly", "集团啤办只读", "跨厂查看啤办单，默认隐藏成本且不可导出或修改"),
    ("engineer", "工程师", "工程开单、本人草稿维护、导出和通知；不含审核、啤机回填、仓库出库或成本权限"),
    ("engineering_supervisor", "工程主管", "工程主管审核与啤办生产任务分派"),
    ("manager", "经理", "经理终审、生产任务分派、改价和敏感审计"),
    ("warehouse_keeper", "PMC / 仓管", "啤办领料、发料与库存管理"),
    ("carton_warehouse_keeper", "纸箱仓管", "纸箱箱唛 Excel、打印 PDF 与文字核对维护"),
    ("qa_inspector", "QA 检验员", "兼容旧入口的箱唛实拍上传与核对"),
    ("molding_clerk", "啤机部文员", "啤办任务接收、开始、生产回填和完成；不可修改或删除工程草稿"),
    ("molding_production_observer", "啤办生产只读观察者", "只读查看本厂啤办生产任务和进度，不可开始、回填或完成"),
    ("sales_customer_owner", "车间业务跟客", "按车间和客户范围转换报客价"),
    ("sales_customer_supervisor", "车间业务主管", "统筹车间客户报价转换、复核和报客价输出"),
    ("factory_permission_admin", "厂区权限管理员", "在授权厂区内管理普通用户权限"),
    ("department_permission_admin", "部门权限管理员", "在授权部门内管理普通用户权限"),
    ("admin", "系统管理员", "系统配置和权限管理"),
] + [
    (item.role_id, item.name, item.description)
    for item in SYSTEM_POSITION_DEFINITIONS
]

ROLE_PERMISSIONS = {
    "group_molding_readonly": {
        "molding_sample:cross_factory_read",
    },
    "engineer": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:create",
        "molding_sample:raw_material_write",
        "molding_sample:edit_draft",
        "molding_sample:delete_draft",
        "molding_sample:notification_read",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["engineer"],
    },
    "engineering_supervisor": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:raw_material_write",
        "molding_sample:supervisor_review",
        "molding_sample:dispatch",
        "molding_sample:notification_read",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["engineering_supervisor"],
    },
    "manager": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:edit_draft",
        "molding_sample:delete_draft",
        "molding_sample:manager_review",
        "molding_sample:dispatch",
        "molding_sample:price_update",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
        "carton_procurement:read",
        "carton_procurement:order_write",
        "carton_procurement:order_adjust",
        "carton_procurement:master_manage",
        "carton_procurement:receipt_write",
        "carton_procurement:inventory_write",
        "carton_procurement:closing_manage",
        "carton_procurement:import",
        "carton_procurement:exception_manage",
    },
    "warehouse_keeper": {
        "carton_mark:read",
        "carton_mark:template_upload",
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:raw_material_write",
        "molding_sample:warehouse_requisition",
        "molding_sample:inventory_issue",
        "molding_sample:notification_read",
        "carton_procurement:master_manage",
        "carton_procurement:read",
        "carton_procurement:order_write",
        "carton_procurement:receipt_write",
        "carton_procurement:inventory_write",
        "carton_procurement:closing_manage",
        "carton_procurement:import",
        "carton_procurement:exception_manage",
    },
    "carton_warehouse_keeper": {
        "carton_mark:read",
        "carton_mark:template_upload",
        "carton_procurement:master_manage",
        "carton_procurement:read",
        "carton_procurement:order_write",
        "carton_procurement:receipt_write",
        "carton_procurement:inventory_write",
        "carton_procurement:closing_manage",
        "carton_procurement:import",
        "carton_procurement:exception_manage",
    },
    "qa_inspector": {
        "carton_mark:read",
        "carton_mark:photo_upload",
        "carton_mark:review",
    },
    "qa_clerk": {
        "carton_mark:read",
        "carton_mark:photo_upload",
    },
    "carton_external": {
        "carton_mark:read",
    },
    "molding_clerk": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["molding_clerk"],
    },
    "molding_production_observer": {
        "molding_sample:production_read",
    },
    "sales_customer_owner": {
        "customer_price:read",
        "customer_price:settings_read",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
        "customer_order:read",
        "customer_order:export",
        "customer_order:duplicate_confirm",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["sales_customer_owner"],
    },
    "sales_customer_supervisor": {
        "customer_price:read",
        "customer_price:settings_read",
        "customer_price:settings_manage",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
        "customer_order:read",
        "customer_order:export",
        "customer_order:duplicate_confirm",
        "customer_order:audit_read",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["sales_customer_supervisor"],
    },
    "factory_permission_admin": {
        "system:user_manage",
        "system:access_manage",
        "system:access_request",
        "system:permission_catalog_read",
    },
    "department_permission_admin": {
        "system:user_manage",
        "system:access_manage",
        "system:access_request",
        "system:permission_catalog_read",
    },
    "molding_operator": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
    },
    "molding_supervisor": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
        *INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS["molding_supervisor"],
    },
    "admin": set(APPLICATION_PERMISSIONS),
}

for system_position in SYSTEM_POSITION_DEFINITIONS:
    ROLE_PERMISSIONS[system_position.role_id] = set(system_position.permission_codes)

DEFAULT_USERS = [
    ("user-admin", "admin", "系统管理员", "admin", "*", "*"),
]

RETIRED_DEFAULT_USERNAMES = {
    "engineer",
    "supervisor",
    "manager",
    "carton_warehouse",
    "qa_inspector",
    "molding_clerk",
    "huaxing_molding_a_sales",
    "molding",
    "warehouse",
    "huaxing_buzzbee_sales",
}
RETIRED_DEFAULT_USER_IDS = {
    "user-engineer",
    "user-supervisor",
    "user-manager",
    "user-carton-warehouse",
    "user-qa-inspector",
    "user-molding-clerk",
    "user-huaxing-molding-a-sales",
    "user-molding",
    "user-warehouse",
    "user-huaxing-buzzbee-sales",
}
DEFAULT_USERNAMES = {username for _, username, *_ in DEFAULT_USERS}
ALLOWED_FACTORY_IDS = {"huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng", "huaxing"}
ALLOWED_DEPARTMENTS = {
    "assembly",
    "electronic",
    "engineering",
    "management",
    "molding",
    "painting",
    "pmc-warehouse",
    "production",
    "qa",
    "qc",
    "carton",
    "sales-business",
    "sewing",
    "hair",
    "slush",
    "three-d-printing",
}


@dataclass(frozen=True)
class AuthGrantContext:
    role_id: str
    role_name: str
    factory_id: str
    department: str
    permissions: frozenset[str]
    data_scope: str = "department"
    scope_mode: str = OWN_FACTORY_SCOPE
    read_permissions: frozenset[str] = frozenset()
    unrestricted_department: bool = False
    binding_id: str = ""
    role_code: str = ""
    valid_from: str = ""
    valid_until: str = ""
    factory_ceiling: tuple[str, ...] | None = None
    assignment_id: str = ""


@dataclass(frozen=True)
class AuthOverrideContext:
    id: str
    permission_code: str
    effect: str
    factory_id: str
    department: str
    valid_from: str = ""
    valid_until: str = ""
    source_type: str = "manual"


@dataclass(frozen=True)
class AuthProfileContext:
    primary_factory_id: str = ""
    primary_department: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""
    confirmation_status: str = "needs_review"


@dataclass(frozen=True)
class AuthEffectiveAccessContext:
    permission_code: str
    factory_id: str
    department: str
    effect: str
    allowed: bool
    source_type: str
    source_ids: tuple[str, ...] = ()
    source_name: str = ""


@dataclass(frozen=True)
class AuthContext:
    id: str
    username: str
    display_name: str
    roles: tuple[str, ...]
    role_codes: tuple[str, ...]
    permissions: frozenset[str]
    factory_scopes: tuple[str, ...]
    department_scopes: tuple[str, ...]
    grants: tuple[AuthGrantContext, ...] = ()
    force_password_change: bool = False
    avatar_url: str = ""
    profile: AuthProfileContext | None = None
    authorization_version: int = 0
    effective_access: tuple[AuthEffectiveAccessContext, ...] = ()
    overrides: tuple[AuthOverrideContext, ...] = ()
    active_permission_codes: frozenset[str] = frozenset()
    permission_catalog_loaded: bool = False
    account_available: bool = True
    identity: dict | None = None

    @property
    def primary_role(self) -> str:
        return self.roles[0] if self.roles else ""


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_avatar_image(image_bytes: bytes) -> bytes:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="请选择有效的头像图片")

    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.format not in AVATAR_ALLOWED_FORMATS:
                raise HTTPException(status_code=400, detail="头像仅支持 JPG、PNG 或 WebP 图片")
            if getattr(source, "is_animated", False):
                raise HTTPException(status_code=400, detail="头像不支持动图，请上传静态图片")
            if source.width * source.height > AVATAR_MAX_PIXELS:
                raise HTTPException(status_code=413, detail="头像图片尺寸过大，请控制在 1600 万像素以内")

            source.load()
            normalized = ImageOps.exif_transpose(source)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGBA")

            avatar = ImageOps.fit(
                normalized,
                (AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            output = BytesIO()
            avatar.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except HTTPException:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError):
        raise HTTPException(status_code=400, detail="无法识别头像图片，请上传有效的 JPG、PNG 或 WebP 文件") from None


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def time_window_is_active(
    valid_from: str,
    valid_until: str,
    at: datetime | None = None,
) -> bool:
    from app.services.identity_resolver import instant, utc_now
    checked_at = instant(at) if at else utc_now()
    try:
        starts_at = instant(valid_from)
        ends_at = instant(valid_until)
    except ValueError:
        return False
    if starts_at is not None and checked_at < starts_at:
        return False
    if ends_at is not None and checked_at >= ends_at:
        return False
    return True


def scope_matches(
    granted_factory_id: str,
    granted_department: str,
    target_factory_id: str,
    target_department: str | None,
) -> bool:
    if granted_factory_id not in {"*", target_factory_id}:
        return False
    if target_department is None:
        return True
    return granted_department in {"*", target_department}


def system_position_grant_scope_source(
    grant: AuthGrantContext,
    permission: str,
    factory_id: str,
) -> str | None:
    """Resolve a built-in position without trusting wildcard home scopes."""
    if grant.factory_ceiling is not None and factory_id not in grant.factory_ceiling:
        return None
    if not grant.unrestricted_department:
        return None
    if grant.factory_id != "*" and grant.factory_id == factory_id:
        return "local"
    if grant.scope_mode == CROSS_FACTORY_OPERATE_SCOPE:
        return "cross_operate"
    if (
        permission in SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES
        and permission in grant.read_permissions
    ):
        return "cross_read"
    if (
        grant.scope_mode == CROSS_FACTORY_READ_SCOPE
        and permission in grant.read_permissions
        and permission not in CROSS_FACTORY_READ_LOCAL_ONLY_PERMISSION_CODES
    ):
        return "cross_read"
    return None


POSITION_DEPARTMENT_ALIAS_GROUPS = (
    frozenset({"production", "molding"}),
    frozenset({"pmc-warehouse", "warehouse"}),
)
POSITION_DEPARTMENT_SENSITIVE_PERMISSION_CODES = frozenset(
    {
        *WAREHOUSE_OPERATIONS_PERMISSION_CODES,
        *CUTTING_OPS_PERMISSION_CODES,
        *UV_OPS_PERMISSION_CODES,
        "fabric_warehouse:read",
        "fabric_warehouse:import",
        "fabric_warehouse:receive",
        "molding_sample:dispatch",
        "molding_sample:notification_read",
        "internal_quote:create",
        "internal_quote:clone",
        "carton_mark:read",
        "carton_mark:template_upload",
        "carton_mark:template_release",
        "carton_mark:customer_manage",
        "carton_mark:photo_upload",
        "carton_mark:review",
    }
)


def system_position_grant_department_matches(
    grant: AuthGrantContext,
    permission: str,
    department: str | None,
) -> bool:
    """Keep department-owned actions and feeds inside the bound position department."""
    # The warehouse manager's cross-factory scope covers the PMC inbox, not
    # the injection inbox that shares these permission codes.
    if grant.role_id == "position_warehouse_manager" and permission in {
        "customer_order:inbox_read", "customer_order:inbox_receive"
    } and department not in {None, "*"}:
        return department in {"pmc-warehouse", "warehouse"}
    if permission not in POSITION_DEPARTMENT_SENSITIVE_PERMISSION_CODES or department in {None, "*"}:
        return True
    if grant.role_id == "position_general_manager" or grant.department == "*":
        return True
    if (
        department == "qc"
        and grant.role_id in CARTON_QC_WORKSPACE_POSITION_ROLE_IDS
        and permission in CARTON_QC_WORKSPACE_PERMISSION_CODES
    ):
        return True
    if grant.department == department:
        return True
    return any(
        grant.department in aliases and department in aliases
        for aliases in POSITION_DEPARTMENT_ALIAS_GROUPS
    )


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()


def make_password_hash(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, hash_password(password, salt)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password_reset_claim_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, user: AuthUser) -> bool:
    expected = hash_password(password, user.password_salt)
    return hmac.compare_digest(expected, user.password_hash)


DUMMY_PASSWORD_HASH = hash_password("dummy-password", DUMMY_PASSWORD_SALT)


def verify_dummy_password(password: str) -> bool:
    expected = hash_password(password, DUMMY_PASSWORD_SALT)
    return hmac.compare_digest(expected, DUMMY_PASSWORD_HASH)


def contains_chinese_characters(value: str) -> bool:
    return any(start <= character <= end for character in value for start, end in CHINESE_CHARACTER_RANGES)


def validate_password_characters(password: str) -> None:
    if contains_chinese_characters(password):
        raise HTTPException(status_code=400, detail=PASSWORD_CHINESE_MESSAGE)


def latest_issued_password_reset_request(
    db: Session,
    user_id: str,
) -> AuthPasswordResetRequest | None:
    return db.scalar(
        select(AuthPasswordResetRequest)
        .where(
            AuthPasswordResetRequest.user_id == user_id,
            AuthPasswordResetRequest.status.in_({"approved", "expired"}),
            AuthPasswordResetRequest.claim_token_hash.is_(None),
        )
        .order_by(
            AuthPasswordResetRequest.last_issued_at.desc(),
            AuthPasswordResetRequest.approved_at.desc(),
            AuthPasswordResetRequest.id.desc(),
        )
        .limit(1)
    )


def mark_password_reset_notification_handled(
    db: Session,
    reset_request: AuthPasswordResetRequest,
    handled_at: str,
) -> None:
    if not reset_request.notification_id:
        return
    notification = db.get(SystemNotification, reset_request.notification_id)
    if notification is None:
        return
    notification.status = "handled"
    if not notification.read_at:
        notification.read_at = handled_at
    notification.handled_at = handled_at


def expire_password_reset_request(
    db: Session,
    reset_request: AuthPasswordResetRequest,
    user: AuthUser,
    request: Request | None = None,
) -> None:
    now = now_text()
    reset_request.status = "expired"
    reset_request.updated_at = now
    mark_password_reset_notification_handled(db, reset_request, now)
    add_auth_audit(
        db,
        "password_reset_expired",
        username=user.username,
        user_id=user.id,
        detail=f"密码重置申请 {reset_request.id} 的临时密码已过期",
        request=request,
    )


def get_seed_admin_password() -> str:
    password = settings.seed_admin_password.strip()
    if not password:
        return ""
    if password == DEFAULT_PASSWORD or len(password) < MIN_SEED_ADMIN_PASSWORD_LENGTH:
        raise RuntimeError("SEED_ADMIN_PASSWORD must be at least 12 characters and must not be 123456")
    if contains_chinese_characters(password):
        raise RuntimeError("SEED_ADMIN_PASSWORD must not contain Chinese characters")
    return password


def add_auth_audit(
    db: Session,
    action: str,
    username: str = "",
    user_id: str = "",
    detail: str = "",
    request: Request | None = None,
) -> None:
    db.add(
        AuthAuditLog(
            user_id=user_id,
            username=username,
            action=action,
            detail=detail,
            ip_address=request.client.host if request and request.client else "",
            user_agent=request.headers.get("user-agent", "") if request else "",
            created_at=now_text(),
        )
    )


def request_ip_address(request: Request | None) -> str:
    return request.client.host if request and request.client else ""


def recent_bad_credential_count(db: Session, username: str, request: Request | None = None) -> int:
    cutoff = (datetime.now() - timedelta(minutes=LOGIN_FAILURE_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    return db.scalar(
        select(func.count(AuthAuditLog.id)).where(
            AuthAuditLog.username == username,
            AuthAuditLog.ip_address == request_ip_address(request),
            AuthAuditLog.action == "login_denied",
            AuthAuditLog.detail == BAD_CREDENTIALS_MESSAGE,
            AuthAuditLog.created_at >= cutoff,
        )
    ) or 0


def ensure_login_not_temporarily_locked(db: Session, username: str, request: Request | None = None) -> None:
    if recent_bad_credential_count(db, username, request) < LOGIN_FAILURE_LIMIT:
        return

    add_auth_audit(
        db,
        "login_locked",
        username=username,
        detail=LOGIN_LOCKED_MESSAGE,
        request=request,
    )
    db.commit()
    raise HTTPException(status_code=429, detail=LOGIN_LOCKED_MESSAGE)


def permission_catalog_values(code: str, sort_order: int) -> dict[str, str | int]:
    module_code, _, action = code.partition(":")
    high_risk_actions = {"delete", "approve", "export", "manage"}
    normalized_action = action.lower()
    risk_level = "high" if (
        module_code == "system"
        or code in {
            "molding_sample:cross_factory_read",
            "molding_sample:cross_factory_cost_read",
        }
        or normalized_action in high_risk_actions
        or "delete" in normalized_action
        or "review" in normalized_action
        or "approve" in normalized_action
        or "export" in normalized_action
        or "manage" in normalized_action
    ) else "normal"
    return {
        "module_code": module_code,
        "action": action,
        "risk_level": risk_level,
        "access_kind": default_permission_access_kind(code),
        "scope_type": "factory_department",
        "status": "active",
        "sort_order": sort_order,
    }


def seed_iam_sidecars(db: Session, now: str) -> None:
    from app.services.identity_catalog import seed_identity_catalog
    seed_identity_catalog(db)
    permissions = list(db.scalars(select(AuthPermission).order_by(AuthPermission.code)).all())
    for sort_order, permission in enumerate(permissions):
        if db.get(AuthPermissionMetadata, permission.id) is not None:
            continue
        values = permission_catalog_values(permission.code, sort_order)
        db.add(
            AuthPermissionMetadata(
                permission_id=permission.id,
                created_at=now,
                updated_at=now,
                **values,
            )
        )

    roles = list(db.scalars(select(AuthRole).order_by(AuthRole.id)).all())
    for role in roles:
        if db.get(AuthRoleMetadata, role.id) is None:
            db.add(
                AuthRoleMetadata(
                    role_id=role.id,
                    version=1,
                    protected=1 if role.code == "admin" else 0,
                    scope_mode=OWN_FACTORY_SCOPE,
                    created_at=now,
                    updated_at=now,
                )
            )

    users = list(db.scalars(select(AuthUser).order_by(AuthUser.id)).all())
    for user in users:
        if db.get(AuthUserAuthorizationRevision, user.id) is None:
            db.add(AuthUserAuthorizationRevision(user_id=user.id, revision=1, updated_at=now))

        if db.get(EmployeeProfile, user.id) is not None:
            continue
        approved_request = db.scalar(
            select(AuthRegistrationRequest)
            .where(
                AuthRegistrationRequest.user_id == user.id,
                AuthRegistrationRequest.status == "approved",
            )
            .order_by(
                AuthRegistrationRequest.reviewed_at.desc(),
                AuthRegistrationRequest.updated_at.desc(),
                AuthRegistrationRequest.id.desc(),
            )
            .limit(1)
        )
        db.add(
            EmployeeProfile(
                user_id=user.id,
                primary_factory_id=approved_request.factory_id if approved_request else "",
                primary_department=approved_request.department if approved_request else "",
                position=approved_request.position if approved_request else "",
                phone=approved_request.phone if approved_request else "",
                email=approved_request.email if approved_request else "",
                confirmation_status="confirmed" if approved_request else "needs_review",
                source_registration_request_id=approved_request.id if approved_request else "",
                created_at=now,
                updated_at=now,
            )
        )

    user_roles = list(db.scalars(select(AuthUserRole).order_by(AuthUserRole.id)).all())
    user_created_at = {user.id: user.created_at for user in users}
    for user_role in user_roles:
        if db.get(AuthRoleBindingMetadata, user_role.id) is not None:
            continue
        db.add(
            AuthRoleBindingMetadata(
                user_role_id=user_role.id,
                state="active",
                source_type="legacy_import",
                valid_from=user_created_at.get(user_role.user_id) or now,
                valid_until="",
                reason="旧授权兼容迁移",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )


def seed_raw_material_write_default_grant_once(db: Session, now: str) -> int:
    """Apply the approved raw-material module default to existing role templates once."""
    if db.get(AuthIamState, RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER) is not None:
        return 0

    permission = db.scalar(select(AuthPermission).where(AuthPermission.code == RAW_MATERIAL_WRITE_PERMISSION))
    created_count = 0
    updated_role_ids: set[str] = set()

    if permission is not None:
        for role_id in RAW_MATERIAL_WRITE_DEFAULT_ROLE_IDS:
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()

    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now

        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER,
            value_json=json.dumps(
                {
                    "completed_at": now,
                    "created_role_permission_count": created_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_carton_master_default_grants_once(db: Session, now: str) -> int:
    """Apply the approved carton-master default to existing role templates once."""
    if db.get(AuthIamState, "carton_master_operator_grants_v1") is not None:
        return 0

    permission = db.scalar(select(AuthPermission).where(AuthPermission.code == "carton_procurement:master_manage"))
    if permission is None:
        return 0
    created_count = 0
    updated_role_ids: set[str] = set()

    if permission is not None:
        for role_id in ("warehouse_keeper", "carton_warehouse_keeper"):
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()

    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now

        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key="carton_master_operator_grants_v1",
            value_json=json.dumps(
                {
                    "completed_at": now,
                    "created_role_permission_count": created_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_carton_mark_warehouse_grants_once(db: Session, now: str) -> int:
    """Backfill the two warehouse document grants once, retaining scoped bindings and denies."""
    marker = "carton_mark_warehouse_grants_v1"
    if db.get(AuthIamState, marker) is not None:
        return 0
    codes = {"carton_mark:read", "carton_mark:template_upload"}
    permissions = {p.code: p for p in db.scalars(select(AuthPermission).where(AuthPermission.code.in_(codes)))}
    if codes - permissions.keys():
        raise RuntimeError("Carton mark permissions must be seeded before warehouse grants")
    role_id = "warehouse_keeper"
    created_count = 0
    if db.get(AuthRole, role_id) is not None:
        for code in sorted(codes):
            permission = permissions[code]
            if db.scalar(select(AuthRolePermission.id).where(
                AuthRolePermission.role_id == role_id, AuthRolePermission.permission_id == permission.id,
            )) is None:
                db.add(AuthRolePermission(id=f"{role_id}:{permission.id}", role_id=role_id, permission_id=permission.id))
                created_count += 1
    db.flush()
    if created_count:
        metadata = db.get(AuthRoleMetadata, role_id)
        if metadata is not None:
            metadata.version += 1
            metadata.updated_at = now
        for user_id in set(db.scalars(select(AuthUserRole.user_id).where(AuthUserRole.role_id == role_id))):
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now
    db.add(AuthIamState(key=marker, value_json=json.dumps({
        "completed_at": now, "created_role_permission_count": created_count,
    }, ensure_ascii=False, sort_keys=True), updated_at=now))
    return created_count


def seed_internal_quote_default_grants_once(db: Session, now: str) -> int:
    """Add the approved P1 module permissions to existing default role templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_DEFAULT_GRANT_MARKER) is not None:
        return 0

    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(
            select(AuthPermission).where(
                AuthPermission.code.in_(INTERNAL_QUOTE_PERMISSION_CODES)
            )
        ).all()
    }
    created_count = 0
    updated_role_ids: set[str] = set()

    for role_id, permission_codes in INTERNAL_QUOTE_DEFAULT_ROLE_PERMISSIONS.items():
        if db.get(AuthRole, role_id) is None:
            continue
        for permission_code in permission_codes:
            permission = permissions_by_code.get(permission_code)
            if permission is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now

        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_DEFAULT_GRANT_MARKER,
            value_json=json.dumps(
                {
                    "completed_at": now,
                    "created_role_permission_count": created_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_internal_quote_self_review_grants_once(db: Session, now: str) -> int:
    """Grant self-review to existing legacy business-supervisor role templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_SELF_REVIEW_GRANT_MARKER) is not None:
        return 0

    permission = db.scalar(
        select(AuthPermission).where(
            AuthPermission.code == INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE
        )
    )
    created_count = 0
    updated_role_ids: set[str] = set()
    if permission is not None:
        for role_id in INTERNAL_QUOTE_SELF_REVIEW_DEFAULT_ROLE_IDS:
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(
                    AuthUserAuthorizationRevision(
                        user_id=user_id,
                        revision=1,
                        updated_at=now,
                    )
                )
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_SELF_REVIEW_GRANT_MARKER,
            value_json=json.dumps(
                {
                    "completed_at": now,
                    "created_role_permission_count": created_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_internal_quote_reference_grants_once(db: Session, now: str) -> int:
    """Grant P2 reference-snapshot sync to existing approved supervisor templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_P2_REFERENCE_GRANT_MARKER) is not None:
        return 0
    permission = db.scalar(
        select(AuthPermission).where(AuthPermission.code == INTERNAL_QUOTE_REFERENCE_PERMISSION)
    )
    created_count = 0
    updated_role_ids: set[str] = set()
    if permission is not None:
        for role_id in INTERNAL_QUOTE_REFERENCE_DEFAULT_ROLE_IDS:
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_P2_REFERENCE_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_internal_quote_export_grants_once(db: Session, now: str) -> int:
    """Grant P3 controlled-export access to existing approved business templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_P3_EXPORT_GRANT_MARKER) is not None:
        return 0
    permission = db.scalar(
        select(AuthPermission).where(AuthPermission.code == INTERNAL_QUOTE_EXPORT_PERMISSION)
    )
    created_count = 0
    updated_role_ids: set[str] = set()
    if permission is not None:
        for role_id in INTERNAL_QUOTE_EXPORT_DEFAULT_ROLE_IDS:
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_P3_EXPORT_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_internal_quote_release_grants_once(db: Session, now: str) -> int:
    """Grant P4 final-submit/review access to existing approved business templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_P4_RELEASE_GRANT_MARKER) is not None:
        return 0
    permission_codes = {
        code
        for codes in INTERNAL_QUOTE_P4_RELEASE_ROLE_PERMISSIONS.values()
        for code in codes
    }
    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(
            select(AuthPermission).where(AuthPermission.code.in_(permission_codes))
        ).all()
    }
    created_count = 0
    updated_role_ids: set[str] = set()
    for role_id, codes in INTERNAL_QUOTE_P4_RELEASE_ROLE_PERMISSIONS.items():
        if db.get(AuthRole, role_id) is None:
            continue
        for code in codes:
            permission = permissions_by_code.get(code)
            if permission is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_P4_RELEASE_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_internal_quote_baseline_grants_once(db: Session, now: str) -> int:
    """Grant quote-baseline read/manage access to existing business role templates once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_BASELINE_GRANT_MARKER) is not None:
        return 0
    permission_codes = {
        code
        for codes in INTERNAL_QUOTE_BASELINE_ROLE_PERMISSIONS.values()
        for code in codes
    }
    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(
            select(AuthPermission).where(AuthPermission.code.in_(permission_codes))
        ).all()
    }
    created_count = 0
    updated_role_ids: set[str] = set()
    for role_id, codes in INTERNAL_QUOTE_BASELINE_ROLE_PERMISSIONS.items():
        if db.get(AuthRole, role_id) is None:
            continue
        for code in codes:
            permission = permissions_by_code.get(code)
            if permission is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_BASELINE_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_customer_price_settings_grants_once(db: Session, now: str) -> int:
    """Backfill private pricing access on legacy sales roles, preserving later revocations."""
    if db.get(AuthIamState, CUSTOMER_PRICE_SETTINGS_GRANT_MARKER) is not None:
        return 0
    permission_codes = {
        code for codes in CUSTOMER_PRICE_SETTINGS_ROLE_PERMISSIONS.values() for code in codes
    }
    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(
            select(AuthPermission).where(AuthPermission.code.in_(permission_codes))
        ).all()
    }
    if permission_codes - permissions_by_code.keys():
        raise RuntimeError("Customer pricing permissions must be seeded before role grants")
    created_count = 0
    updated_role_ids: set[str] = set()
    for role_id, codes in CUSTOMER_PRICE_SETTINGS_ROLE_PERMISSIONS.items():
        if db.get(AuthRole, role_id) is None:
            continue
        for code in codes:
            permission = permissions_by_code[code]
            existing = db.scalar(select(AuthRolePermission).where(
                AuthRolePermission.role_id == role_id,
                AuthRolePermission.permission_id == permission.id,
            ))
            if existing is not None:
                continue
            db.add(AuthRolePermission(
                id=f"{role_id}:{permission.id}", role_id=role_id, permission_id=permission.id,
            ))
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    for role_id in updated_role_ids:
        metadata = db.get(AuthRoleMetadata, role_id)
        if metadata is not None:
            metadata.version += 1
            metadata.updated_at = now
    if updated_role_ids:
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
            else:
                revision.revision += 1
                revision.updated_at = now
    db.add(AuthIamState(
        key=CUSTOMER_PRICE_SETTINGS_GRANT_MARKER,
        value_json=json.dumps(
            {"completed_at": now, "created_role_permission_count": created_count},
            ensure_ascii=False, sort_keys=True,
        ),
        updated_at=now,
    ))
    return created_count


def seed_internal_quote_customer_grants_once(db: Session, now: str) -> int:
    """Grant factory customer maintenance to existing sales and engineering supervisors once."""
    if db.get(AuthIamState, INTERNAL_QUOTE_CUSTOMER_GRANT_MARKER) is not None:
        return 0
    permission = db.scalar(
        select(AuthPermission).where(
            AuthPermission.code == INTERNAL_QUOTE_CUSTOMER_PERMISSION
        )
    )
    created_count = 0
    updated_role_ids: set[str] = set()
    if permission is not None:
        for role_id in INTERNAL_QUOTE_CUSTOMER_DEFAULT_ROLE_IDS:
            if db.get(AuthRole, role_id) is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    if updated_role_ids:
        for role_id in updated_role_ids:
            metadata = db.get(AuthRoleMetadata, role_id)
            if metadata is not None:
                metadata.version += 1
                metadata.updated_at = now
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(
                    AuthUserAuthorizationRevision(
                        user_id=user_id,
                        revision=1,
                        updated_at=now,
                    )
                )
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=INTERNAL_QUOTE_CUSTOMER_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_customer_order_control_grants_once(db: Session, now: str) -> int:
    """Add separately revocable confirmation/audit capabilities to existing sales roles."""
    if db.get(AuthIamState, CUSTOMER_ORDER_CONTROL_GRANT_MARKER) is not None:
        return 0

    permission_codes = {
        code
        for codes in CUSTOMER_ORDER_CONTROL_ROLE_PERMISSIONS.values()
        for code in codes
    }
    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(
            select(AuthPermission).where(AuthPermission.code.in_(permission_codes))
        ).all()
    }
    created_count = 0
    updated_role_ids: set[str] = set()
    for role_id, codes in CUSTOMER_ORDER_CONTROL_ROLE_PERMISSIONS.items():
        if db.get(AuthRole, role_id) is None:
            continue
        for code in codes:
            permission = permissions_by_code.get(code)
            if permission is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is not None:
                continue
            db.add(
                AuthRolePermission(
                    id=role_permission_id,
                    role_id=role_id,
                    permission_id=permission.id,
                )
            )
            created_count += 1
            updated_role_ids.add(role_id)

    db.flush()
    for role_id in updated_role_ids:
        metadata = db.get(AuthRoleMetadata, role_id)
        if metadata is not None:
            metadata.version += 1
            metadata.updated_at = now
    if updated_role_ids:
        affected_user_ids = {
            binding.user_id
            for binding in db.scalars(
                select(AuthUserRole).where(AuthUserRole.role_id.in_(updated_role_ids))
            ).all()
        }
        for user_id in affected_user_ids:
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(
                    AuthUserAuthorizationRevision(
                        user_id=user_id,
                        revision=1,
                        updated_at=now,
                    )
                )
            else:
                revision.revision += 1
                revision.updated_at = now

    db.add(
        AuthIamState(
            key=CUSTOMER_ORDER_CONTROL_GRANT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_role_permission_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    return created_count


def seed_legacy_export_compat_once(db: Session, now: str) -> int:
    if db.get(AuthIamState, LEGACY_EXPORT_COMPAT_MARKER) is not None:
        return 0

    db.flush()
    permission = db.scalar(select(AuthPermission).where(AuthPermission.code == LEGACY_EXPORT_COMPAT_PERMISSION))
    created_count = 0
    if permission is not None:
        users = list(
            db.scalars(
                select(AuthUser)
                .where(AuthUser.status.in_({"active", "suspended"}))
                .order_by(AuthUser.id)
            ).all()
        )
        for user in users:
            approved_request = db.scalar(
                select(AuthRegistrationRequest)
                .where(
                    AuthRegistrationRequest.user_id == user.id,
                    AuthRegistrationRequest.status == "approved",
                )
                .order_by(
                    AuthRegistrationRequest.reviewed_at.desc(),
                    AuthRegistrationRequest.updated_at.desc(),
                    AuthRegistrationRequest.id.desc(),
                )
                .limit(1)
            )
            if approved_request is None:
                continue

            context = build_auth_context(db, user)
            if any(
                grant.role_code == "admin"
                and grant.factory_id == "*"
                and grant.department in {"*", "system"}
                for grant in context.grants
            ):
                continue

            scopes = {
                (grant.factory_id, grant.department)
                for grant in context.grants
                if can(context, "molding_sample:read", grant.factory_id, grant.department)
            }
            profile = db.get(EmployeeProfile, user.id)
            if (
                profile
                and profile.primary_factory_id
                and profile.primary_department
                and can(
                    context,
                    "molding_sample:read",
                    profile.primary_factory_id,
                    profile.primary_department,
                )
            ):
                scopes.add((profile.primary_factory_id, profile.primary_department))

            for factory_id, department in sorted(scopes):
                if can(context, LEGACY_EXPORT_COMPAT_PERMISSION, factory_id, department):
                    continue
                identity = ":".join((user.id, permission.id, factory_id, department))
                override_id = f"legacy-export-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:38]}"
                if db.get(AuthUserPermissionOverride, override_id) is not None:
                    continue
                db.add(
                    AuthUserPermissionOverride(
                        id=override_id,
                        user_id=user.id,
                        permission_id=permission.id,
                        effect="allow",
                        factory_id=factory_id,
                        department=department,
                        status="active",
                        valid_from=now,
                        valid_until="",
                        reason="历史导出能力兼容",
                        source_type="legacy_export_compat",
                        source_id=approved_request.id,
                        created_by_user_id="",
                        approved_by_user_id="",
                        revoked_by_user_id="",
                        revoked_at="",
                        revoke_reason="",
                        created_at=now,
                        updated_at=now,
                    )
                )
                created_count += 1

    db.add(
        AuthIamState(
            key=LEGACY_EXPORT_COMPAT_MARKER,
            value_json=json.dumps(
                {"completed_at": now, "created_override_count": created_count},
                ensure_ascii=False,
                sort_keys=True,
            ),
            updated_at=now,
        )
    )
    db.flush()
    return created_count


def ensure_authz_startup_safety(db: Session) -> None:
    if settings.authz_writes_enabled and settings.authz_mode != "enforce":
        raise RuntimeError("AUTHZ_WRITES_ENABLED=true requires AUTHZ_MODE=enforce")
    if settings.authz_mode == "enforce":
        return

    active_overrides = list(
        db.scalars(
            select(AuthUserPermissionOverride).where(
                AuthUserPermissionOverride.permission_id.notin_(
                    select(AuthPermission.id).where(AuthPermission.code.in_(CARTON_SUPPLIER_PERMISSION_CODES))
                ),
                AuthUserPermissionOverride.status == "active",
                AuthUserPermissionOverride.effect.in_({"allow", "deny"}),
                AuthUserPermissionOverride.source_type.notin_(
                    {"legacy_export_compat"}
                ),
            )
        ).all()
    )
    if any(time_window_is_active(item.valid_from, item.valid_until) for item in active_overrides):
        raise RuntimeError(
            "AUTHZ_MODE must remain enforce because active configurable authorization overrides exist"
        )


def seed_auth_defaults(db: Session) -> None:
    now = now_text()
    created_role_ids: set[str] = set()
    system_position_role_ids = {
        item.role_id for item in SYSTEM_POSITION_DEFINITIONS
    }

    for code in APPLICATION_PERMISSIONS:
        permission_id = f"perm-{code.replace(':', '-')}"
        if db.get(AuthPermission, permission_id) is None:
            db.add(AuthPermission(id=permission_id, code=code, name=code, description=""))

    for role_id, name, description in DEFAULT_ROLES:
        if role_id in system_position_role_ids:
            # Fixed positions are created and fully reconciled after the shared
            # permission catalog and IAM sidecars are ready.
            continue
        role = db.get(AuthRole, role_id)
        if role is None:
            db.add(AuthRole(id=role_id, code=role_id, name=name, description=description))
            created_role_ids.add(role_id)

    db.flush()
    permissions_by_code = {permission.code: permission for permission in db.scalars(select(AuthPermission)).all()}

    # Legacy and special roles retain their existing compatibility behavior.
    # Fixed system positions are projected separately from code below.
    for role_id in created_role_ids:
        for permission_code in ROLE_PERMISSIONS.get(role_id, set()):
            permission = permissions_by_code.get(permission_code)
            if permission is None:
                continue
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is None:
                db.add(
                    AuthRolePermission(
                        id=role_permission_id,
                        role_id=role_id,
                        permission_id=permission.id,
                    )
                )

    if settings.seed_default_accounts:
        seed_admin_password = get_seed_admin_password()
        if seed_admin_password:
            for user_id, username, display_name, role_id, factory_id, department in DEFAULT_USERS:
                # Existing accounts, credentials, status and grants are never rewritten.
                if db.get(AuthUser, user_id) is not None:
                    continue
                salt, password_hash = make_password_hash(seed_admin_password)
                db.add(
                    AuthUser(
                        id=user_id,
                        username=username,
                        display_name=display_name,
                        password_salt=salt,
                        password_hash=password_hash,
                        status="active",
                        # The administrator bootstrap secret is already required to be
                        # strong and environment-provided. Other shared seed accounts
                        # must still replace it before entering business APIs.
                        force_password_change=0 if role_id == "admin" else 1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.flush()
                user_role_id = f"{user_id}:{role_id}:{factory_id}:{department}"
                db.add(
                    AuthUserRole(
                        id=user_role_id,
                        user_id=user_id,
                        role_id=role_id,
                        factory_id=factory_id,
                        department=department,
                    )
                )

    db.flush()
    seed_iam_sidecars(db, now)
    seed_raw_material_write_default_grant_once(db, now)
    seed_carton_master_default_grants_once(db, now)
    seed_carton_mark_warehouse_grants_once(db, now)
    seed_internal_quote_default_grants_once(db, now)
    seed_internal_quote_self_review_grants_once(db, now)
    seed_internal_quote_reference_grants_once(db, now)
    seed_internal_quote_export_grants_once(db, now)
    seed_internal_quote_release_grants_once(db, now)
    seed_internal_quote_baseline_grants_once(db, now)
    seed_internal_quote_customer_grants_once(db, now)
    seed_customer_order_control_grants_once(db, now)
    seed_customer_price_settings_grants_once(db, now)
    seed_legacy_export_compat_once(db, now)
    reconcile_system_position_catalog(db, now=now)
    ensure_authz_startup_safety(db)
    db.commit()


def authenticate_user(db: Session, username: str, password: str, request: Request | None = None) -> AuthUser:
    normalized_username = username.strip()
    validate_password_characters(password)
    ensure_login_not_temporarily_locked(db, normalized_username, request)

    user = db.scalar(select(AuthUser).where(AuthUser.username == normalized_username))
    if user is None and normalized_username in DEFAULT_USERNAMES and settings.seed_default_accounts:
        seed_auth_defaults(db)
        user = db.scalar(select(AuthUser).where(AuthUser.username == normalized_username))

    password_matches = verify_password(password, user) if user else verify_dummy_password(password)
    if not user or not password_matches:
        add_auth_audit(db, "login_denied", username=normalized_username, detail=BAD_CREDENTIALS_MESSAGE, request=request)
        db.commit()
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS_MESSAGE)

    if user.status != "active":
        status_message = {
            "pending": "账号申请正在审批中，请等待管理员开通",
            "rejected": "账号申请未通过，请联系管理员",
            "suspended": "账号已停用，请联系管理员",
            "left": "账号已注销，请联系管理员",
            "locked": "账号已锁定，请联系管理员",
        }.get(user.status, "账号不可用，请联系管理员")
        if user.status == "rejected":
            rejected_request = db.scalar(
                select(AuthRegistrationRequest)
                .where(AuthRegistrationRequest.user_id == user.id, AuthRegistrationRequest.status == "rejected")
                .order_by(AuthRegistrationRequest.reviewed_at.desc(), AuthRegistrationRequest.updated_at.desc())
            )
            review_comment = rejected_request.review_comment.strip() if rejected_request else ""
            if review_comment:
                status_message = f"账号申请未通过，原因：{review_comment}"
        add_auth_audit(
            db,
            "login_denied",
            username=user.username,
            user_id=user.id,
            detail=f"账号状态不可登录：{user.status}",
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=401, detail=status_message)

    if user.force_password_change:
        reset_request = latest_issued_password_reset_request(db, user.id)
        expires_at = parse_time(reset_request.expires_at) if reset_request else None
        if reset_request is not None and (
            reset_request.status == "expired" or expires_at is None or expires_at <= datetime.now()
        ):
            if reset_request.status != "expired":
                expire_password_reset_request(db, reset_request, user, request=request)
            db.commit()
            raise HTTPException(status_code=401, detail="临时密码已过期，请重新提交密码重置申请")
        add_auth_audit(
            db,
            "password_reset_temporary_login",
            username=user.username,
            user_id=user.id,
            detail=f"使用临时密码登录；申请 {reset_request.id if reset_request else 'legacy'}",
            request=request,
        )
        add_auth_audit(
            db,
            "password_change_required",
            username=user.username,
            user_id=user.id,
            detail="登录后必须先修改临时密码",
            request=request,
        )

    user.last_login_at = now_text()
    user.updated_at = now_text()
    add_auth_audit(db, "login_success", username=user.username, user_id=user.id, detail="账号登录成功", request=request)
    db.commit()
    return user


def register_user(db: Session, payload: RegisterRequest, request: Request | None = None) -> RegisterResponse:
    from app.services.identity_policy import lock_mutation
    lock_mutation(db)
    username = payload.username.strip()
    display_name = payload.display_name.strip()
    phone = payload.phone.strip()
    email = payload.email.strip()
    factory_id = payload.factory_id.strip()
    department = payload.department.strip()
    if department not in ALLOWED_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="请选择有效部门")
    from app.services.identity_registration import registration_org
    org = registration_org(db, factory_id, payload.org_unit_id.strip(), department)
    factory_id = org.legacy_factory_id
    position = payload.position.strip()

    if not username:
        raise HTTPException(status_code=400, detail="请输入账号或工号")
    if not display_name:
        raise HTTPException(status_code=400, detail="请输入姓名")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")
    validate_password_characters(payload.password)
    validate_password_characters(payload.confirm_password)
    if not phone and not email:
        raise HTTPException(status_code=400, detail="手机或邮箱至少填写一项")
    if factory_id not in ALLOWED_FACTORY_IDS and org.kind != "functional_unit":
        raise HTTPException(status_code=400, detail="请选择有效厂区")
    if not position:
        raise HTTPException(status_code=400, detail="请输入职位")
    if len(position) > 128:
        raise HTTPException(status_code=400, detail="职位不能超过 128 个字符")

    existing_user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    if existing_user is not None and existing_user.status != "rejected":
        raise HTTPException(status_code=409, detail="账号或工号已存在")

    now = now_text()
    user_id = existing_user.id if existing_user is not None else f"user-{secrets.token_hex(8)}"
    salt, password_hash = make_password_hash(payload.password)
    registration_request_id = f"registration-{secrets.token_hex(12)}"

    if existing_user is None:
        db.add(
            AuthUser(
                id=user_id,
                username=username,
                display_name=display_name,
                password_salt=salt,
                password_hash=password_hash,
                status="pending",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
    else:
        existing_user.display_name = display_name
        existing_user.password_salt = salt
        existing_user.password_hash = password_hash
        existing_user.status = "pending"
        existing_user.force_password_change = 0
        existing_user.updated_at = now

    if db.get(AuthUserAuthorizationRevision, user_id) is None:
        db.add(AuthUserAuthorizationRevision(user_id=user_id, revision=1, updated_at=now))
    if db.get(EmployeeProfile, user_id) is None:
        db.add(
            EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_org_unit_id=org.id,
                primary_department=department,
                position=position,
                phone=phone,
                email=email,
                confirmation_status="pending",
                source_registration_request_id=registration_request_id,
                created_at=now,
                updated_at=now,
            )
        )

    db.add(
        AuthRegistrationRequest(
            id=registration_request_id,
            org_unit_id=org.id,
            declared_profile_json=json.dumps({"display_name": display_name, "factory_id": factory_id, "org_unit_id": org.id, "department": department, "position": position}, ensure_ascii=False),
            user_id=user_id,
            username=username,
            display_name=display_name,
            phone=phone,
            email=email,
            factory_id=factory_id,
            department=department,
            position=position,
            status="pending",
            submitted_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        SystemNotification(
            id=f"system-notification-{secrets.token_hex(12)}",
            target_permission="system:user_manage",
            target_factory_id=factory_id,
            target_department=department,
            type="user_registration",
            title="新用户注册待审批",
            message=f"{display_name}（{username}）提交账号申请，厂区 {factory_id}，部门 {department}",
            payload_json=json.dumps({"registration_request_id": registration_request_id, "user_id": user_id}),
            status="unread",
            created_at=now,
        )
    )
    add_auth_audit(
        db,
        "registration_resubmitted" if existing_user is not None else "registration_submitted",
        username=username,
        user_id=user_id,
        detail=f"账号申请提交：{factory_id}/{department}/{position}",
        request=request,
    )
    db.commit()

    return RegisterResponse(status="pending", message="账号申请已提交，请等待管理员审批")


def submit_password_reset_request(
    db: Session,
    payload: PasswordResetRequest,
    request: Request | None = None,
) -> tuple[PasswordResetResponse, str]:
    username = payload.username.strip()
    display_name = payload.display_name.strip()
    contact = payload.contact.strip()
    note = payload.note.strip()

    if not username:
        raise HTTPException(status_code=400, detail="请输入需要重置密码的账号")
    if not display_name:
        raise HTTPException(status_code=400, detail="请输入姓名")
    if not contact:
        raise HTTPException(status_code=400, detail="请填写联系电话或邮箱")

    now = now_text()
    matched_user = db.scalar(
        select(AuthUser).where(func.lower(AuthUser.username) == username.casefold())
    )
    normalized_username = matched_user.username if matched_user else username.casefold()
    request_ip = request_ip_address(request)
    cutoff = (datetime.now() - timedelta(minutes=PASSWORD_RESET_RATE_WINDOW_MINUTES)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    recent_ip_count = db.scalar(
        select(func.count(AuthPasswordResetRequest.id)).where(
            AuthPasswordResetRequest.request_ip == request_ip,
            AuthPasswordResetRequest.submitted_at >= cutoff,
        )
    ) or 0
    if request_ip and recent_ip_count >= PASSWORD_RESET_RATE_LIMIT:
        add_auth_audit(
            db,
            "password_reset_rate_limited",
            username=normalized_username,
            user_id=matched_user.id if matched_user else "",
            detail="密码重置公开申请触发 IP 限流",
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=429, detail="申请过于频繁，请稍后再试")

    target_factory_id = "*"
    target_department = "system"
    if matched_user is not None:
        from app.services.identity_resolver import resolve_identity_at
        identity = resolve_identity_at(db, matched_user.id)
        if identity["primary_factory_id"] and identity["primary_department"]:
            target_factory_id = identity["primary_factory_id"]
            target_department = identity["primary_department"]
        elif identity["identity_mode"] != "v2":
            latest_registration = db.scalar(
                select(AuthRegistrationRequest)
                .where(AuthRegistrationRequest.user_id == matched_user.id)
                .order_by(
                    AuthRegistrationRequest.updated_at.desc(),
                    AuthRegistrationRequest.created_at.desc(),
                    AuthRegistrationRequest.id.desc(),
                )
                .limit(1)
            )
            if latest_registration is not None and latest_registration.factory_id and latest_registration.department:
                target_factory_id = latest_registration.factory_id
                target_department = latest_registration.department
    raw_claim_token = secrets.token_urlsafe(32)
    reset_request = AuthPasswordResetRequest(
        id=f"password-reset-{secrets.token_hex(12)}",
        user_id=matched_user.id if matched_user else None,
        username=normalized_username,
        display_name=display_name,
        contact=contact,
        note=note,
        factory_id=target_factory_id,
        department=target_department,
        status="pending",
        request_ip=request_ip,
        user_agent=request.headers.get("user-agent", "") if request else "",
        claim_token_hash=hash_password_reset_claim_token(raw_claim_token),
        issue_count=0,
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(reset_request)
    db.flush()

    notification_id = f"system-notification-{secrets.token_hex(12)}"
    payload_json = {
        "password_reset_request_id": reset_request.id,
        "matched_user_id": matched_user.id if matched_user else "",
    }

    notification = SystemNotification(
        id=notification_id,
        target_permission="system:user_manage",
        target_factory_id=target_factory_id,
        target_department=target_department,
        type="password_reset",
        title="密码重置待处理",
        message="收到新的密码重置申请，请进入账号管理页核验申请资料。",
        payload_json=json.dumps(payload_json, ensure_ascii=False),
        status="unread",
        created_at=now,
    )
    db.add(notification)
    # The reset request owns a foreign key to this notification. Flush the
    # notification first so SQLAlchemy cannot issue the link UPDATE before the
    # referenced row exists on databases with immediate FK enforcement.
    db.flush()
    reset_request.notification_id = notification_id
    add_auth_audit(
        db,
        "password_reset_requested",
        username=normalized_username,
        user_id=matched_user.id if matched_user else "",
        detail=f"密码重置申请已提交：{reset_request.id}",
        request=request,
    )
    db.commit()

    return (
        PasswordResetResponse(
            status="submitted",
            message=PASSWORD_RESET_PUBLIC_MESSAGE,
            request_id=reset_request.id,
        ),
        raw_claim_token,
    )


def password_reset_claim_none_response() -> PasswordResetClaimResponse:
    return PasswordResetClaimResponse(
        status="none",
        message="当前浏览器没有找到原申请凭证，请重新提交密码重置申请。",
    )


def password_reset_claim_to_response(
    reset_request: AuthPasswordResetRequest,
) -> PasswordResetClaimResponse:
    messages = {
        "pending": "申请正在等待管理员审核",
        "approved": "申请已通过，请在有效期内设置新密码",
        "completed": "密码已成功重置，请使用新密码登录",
        "rejected": "密码重置申请未通过，请检查资料后重新提交",
        "expired": "本次改密时限已过期，请重新提交或联系管理员重新开放",
    }
    status = reset_request.status
    if reset_request.claim_token_hash is None and status in {"pending", "approved", "expired"}:
        status = "legacy_invalid"
    return PasswordResetClaimResponse(
        status=status,
        request_id=reset_request.id,
        can_complete=status == "approved",
        expires_at=(
            serialize_process_local_timestamp(reset_request.expires_at)
            if status == "approved"
            else ""
        ),
        message=(
            "该申请来自旧版流程，请重新提交密码重置申请"
            if status == "legacy_invalid"
            else messages.get(status, "当前浏览器没有可处理的密码重置申请")
        ),
    )


def load_password_reset_claim(
    db: Session,
    raw_claim_token: str | None,
    *,
    for_update: bool = False,
) -> AuthPasswordResetRequest | None:
    if not raw_claim_token:
        return None
    statement = select(AuthPasswordResetRequest).where(
        AuthPasswordResetRequest.claim_token_hash
        == hash_password_reset_claim_token(raw_claim_token)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def expire_password_reset_claim(
    db: Session,
    reset_request: AuthPasswordResetRequest,
    request: Request | None = None,
) -> None:
    now = now_text()
    reset_request.status = "expired"
    reset_request.updated_at = now
    mark_password_reset_notification_handled(db, reset_request, now)
    add_auth_audit(
        db,
        "password_reset_claim_expired",
        username=reset_request.username,
        user_id=reset_request.user_id or "",
        detail=f"原设备重置凭证已过期：{reset_request.id}",
        request=request,
    )


def get_password_reset_claim(
    db: Session,
    raw_claim_token: str | None,
    request: Request | None = None,
) -> PasswordResetClaimResponse:
    if not raw_claim_token:
        return password_reset_claim_none_response()
    reset_request = load_password_reset_claim(db, raw_claim_token)
    if reset_request is None:
        add_auth_audit(
            db,
            "password_reset_claim_invalid",
            detail="收到无效的原设备密码重置凭证",
            request=request,
        )
        db.commit()
        return password_reset_claim_none_response()
    expires_at = parse_time(reset_request.expires_at)
    if reset_request.status == "approved" and (
        expires_at is None or expires_at <= datetime.now()
    ):
        expire_password_reset_claim(db, reset_request, request=request)
        db.commit()
    return password_reset_claim_to_response(reset_request)


def complete_password_reset_claim(
    db: Session,
    raw_claim_token: str | None,
    payload: PasswordResetClaimCompleteRequest,
    request: Request | None = None,
) -> PasswordResetClaimCompleteResponse:
    from app.services.identity_policy import lock_mutation
    lock_mutation(db)
    if not raw_claim_token:
        raise HTTPException(
            status_code=400,
            detail="当前浏览器没有找到原申请凭证，请重新提交密码重置申请",
        )
    reset_request = load_password_reset_claim(db, raw_claim_token, for_update=True)
    if reset_request is None:
        add_auth_audit(
            db,
            "password_reset_claim_invalid",
            detail="使用无效的原设备密码重置凭证尝试完成改密",
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="该重置申请已完成或已失效")
    if reset_request.status != "approved":
        raise HTTPException(status_code=409, detail="该重置申请尚未批准、已完成或已失效")
    expires_at = parse_time(reset_request.expires_at)
    if expires_at is None or expires_at <= datetime.now():
        expire_password_reset_claim(db, reset_request, request=request)
        db.commit()
        raise HTTPException(status_code=409, detail="本次改密时限已过期")

    validate_password_characters(payload.new_password)
    validate_password_characters(payload.confirm_password)
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    if len(payload.new_password) < MIN_ACCOUNT_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"密码至少需要 {MIN_ACCOUNT_PASSWORD_LENGTH} 位",
        )

    user = db.get(AuthUser, reset_request.user_id) if reset_request.user_id else None
    if user is None or user.status != "active":
        raise HTTPException(status_code=409, detail="申请关联账号不可用于密码重置")
    if verify_password(payload.new_password, user):
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")

    now = now_text()
    claim = db.execute(
        update(AuthPasswordResetRequest)
        .where(
            AuthPasswordResetRequest.id == reset_request.id,
            AuthPasswordResetRequest.status == "approved",
            AuthPasswordResetRequest.claim_token_hash
            == hash_password_reset_claim_token(raw_claim_token),
            AuthPasswordResetRequest.issue_count == reset_request.issue_count,
        )
        .values(
            status="completed",
            completed_at=now,
            expires_at="",
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="该重置申请已完成或已失效")

    salt, password_hash = make_password_hash(payload.new_password)
    user.password_salt = salt
    user.password_hash = password_hash
    user.force_password_change = 0
    user.updated_at = now

    active_sessions = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.status == "active",
        )
    ).all()
    for session in active_sessions:
        session.status = "revoked"
        session.revoked_at = now

    reset_request.status = "completed"
    reset_request.completed_at = now
    reset_request.expires_at = ""
    reset_request.updated_at = now
    mark_password_reset_notification_handled(db, reset_request, now)

    other_requests = db.scalars(
        select(AuthPasswordResetRequest).where(
            AuthPasswordResetRequest.user_id == user.id,
            AuthPasswordResetRequest.id != reset_request.id,
            AuthPasswordResetRequest.status.in_({"pending", "approved"}),
        )
    ).all()
    for other_request in other_requests:
        other_request.status = "expired"
        other_request.expires_at = ""
        other_request.updated_at = now
        mark_password_reset_notification_handled(db, other_request, now)

    add_auth_audit(
        db,
        "password_reset_completed",
        username=user.username,
        user_id=user.id,
        detail=(
            f"原设备密码重置申请 {reset_request.id} 已完成；"
            f"撤销会话 {len(active_sessions)} 个，失效其他申请 {len(other_requests)} 个"
        ),
        request=request,
    )
    db.commit()
    return PasswordResetClaimCompleteResponse(
        status="completed",
        message="密码已成功重置，请使用新密码登录",
    )


def create_session(db: Session, user: AuthUser, request: Request | None = None) -> str:
    from app.services.identity_policy import lock_mutation, fail
    user_id = user.id
    verified_hash = user.password_hash
    previous_profile = db.get(EmployeeProfile, user_id)
    verified_epoch = previous_profile.employment_epoch if previous_profile else 1
    lock_mutation(db)
    user = db.get(AuthUser, user_id, populate_existing=True)
    profile = db.get(EmployeeProfile, user_id)
    if (user is None or user.status != "active" or user.password_hash != verified_hash
            or (profile and (profile.employment_status == "left" or profile.employment_epoch != verified_epoch))):
        fail("ACCOUNT_UNAVAILABLE", "账号状态已变化，请重新登录", 401)
    token = secrets.token_urlsafe(32)
    session = AuthSession(
        id=f"session-{secrets.token_hex(16)}",
        user_id=user.id,
        token_hash=hash_session_token(token),
        status="active",
        ip_address=request.client.host if request and request.client else "",
        user_agent=request.headers.get("user-agent", "") if request else "",
        expires_at=(datetime.now() + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S"),
        created_at=now_text(),
    )
    db.add(session)
    db.commit()
    return token


def change_current_password(
    db: Session,
    current_user: AuthContext,
    payload: ChangePasswordRequest,
    request: Request | None = None,
) -> tuple[AuthMeResponse, str]:
    from app.services.identity_policy import lock_mutation
    lock_mutation(db)
    validate_password_characters(payload.current_password)
    validate_password_characters(payload.new_password)
    validate_password_characters(payload.confirm_password)
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    if len(payload.new_password) < MIN_ACCOUNT_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"密码至少需要 {MIN_ACCOUNT_PASSWORD_LENGTH} 位")
    if secrets.compare_digest(payload.current_password, payload.new_password):
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")

    user = db.get(AuthUser, current_user.id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="账号不可用")
    if not verify_password(payload.current_password, user):
        add_auth_audit(
            db,
            "password_change_denied",
            username=user.username,
            user_id=user.id,
            detail="当前密码校验失败",
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="当前密码不正确")

    reset_request = latest_issued_password_reset_request(db, user.id)
    if user.force_password_change and reset_request is not None:
        expires_at = parse_time(reset_request.expires_at)
        if reset_request.status == "expired" or expires_at is None or expires_at <= datetime.now():
            if reset_request.status != "expired":
                expire_password_reset_request(db, reset_request, user, request=request)
            db.commit()
            raise HTTPException(status_code=403, detail="临时密码已过期，请重新提交密码重置申请")
    if reset_request is not None and reset_request.status != "approved":
        reset_request = None

    now = now_text()
    salt, password_hash = make_password_hash(payload.new_password)
    user.password_salt = salt
    user.password_hash = password_hash
    user.force_password_change = 0
    user.updated_at = now

    if reset_request is not None:
        reset_request.status = "completed"
        reset_request.completed_at = now
        reset_request.expires_at = ""
        reset_request.updated_at = now
        mark_password_reset_notification_handled(db, reset_request, now)

    for session in db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.status == "active")
    ).all():
        session.status = "revoked"
        session.revoked_at = now

    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            id=f"session-{secrets.token_hex(16)}",
            user_id=user.id,
            token_hash=hash_session_token(token),
            status="active",
            ip_address=request_ip_address(request),
            user_agent=request.headers.get("user-agent", "") if request else "",
            expires_at=(datetime.now() + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S"),
            created_at=now,
        )
    )
    add_auth_audit(
        db,
        "password_reset_completed" if reset_request is not None else "password_changed",
        username=user.username,
        user_id=user.id,
        detail=(
            f"密码重置申请 {reset_request.id} 已完成并轮换会话"
            if reset_request is not None
            else "账号密码已修改并轮换会话"
        ),
        request=request,
    )
    db.commit()
    return to_auth_response(build_auth_context(db, user)), token


def revoke_session(db: Session, token: str | None, request: Request | None = None) -> None:
    if not token:
        return

    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
    if session is None:
        return

    session.status = "revoked"
    session.revoked_at = now_text()
    user = db.get(AuthUser, session.user_id)
    add_auth_audit(
        db,
        "logout",
        username=user.username if user else "",
        user_id=session.user_id,
        detail="账号退出登录",
        request=request,
    )
    db.commit()


def get_authenticated_user(db: Session, context: AuthContext) -> AuthUser:
    user = db.get(AuthUser, context.id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="账号不可用")
    return user


def save_auth_user_avatar(
    db: Session,
    context: AuthContext,
    image_bytes: bytes,
    request: Request | None = None,
) -> AuthMeResponse:
    user = get_authenticated_user(db, context)
    user.avatar_png = normalize_avatar_image(image_bytes)
    user.avatar_version = secrets.token_urlsafe(18)
    user.updated_at = now_text()
    add_auth_audit(
        db,
        "avatar_updated",
        username=user.username,
        user_id=user.id,
        detail="个人头像已更新",
        request=request,
    )
    db.commit()
    return to_auth_response(build_auth_context(db, user))


def read_auth_user_avatar(db: Session, context: AuthContext) -> bytes:
    user = get_authenticated_user(db, context)
    if not user.avatar_png:
        raise HTTPException(status_code=404, detail="尚未设置个人头像")
    return bytes(user.avatar_png)


def remove_auth_user_avatar(
    db: Session,
    context: AuthContext,
    request: Request | None = None,
) -> AuthMeResponse:
    user = get_authenticated_user(db, context)
    user.avatar_png = None
    user.avatar_version = ""
    user.updated_at = now_text()
    add_auth_audit(
        db,
        "avatar_removed",
        username=user.username,
        user_id=user.id,
        detail="个人头像已恢复为默认头像",
        request=request,
    )
    db.commit()
    return to_auth_response(build_auth_context(db, user))


def authorization_decision(
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
    *,
    at: datetime | None = None,
) -> tuple[bool, str, tuple[str, ...], str]:
    if not user.account_available:
        return False, "account_unavailable", (), "账号不可用"
    if (user.permission_catalog_loaded or user.active_permission_codes) and permission not in user.active_permission_codes:
        return False, "inactive_permission", (), "权限未启用"

    matching_overrides = [
        override
        for override in user.overrides
        if override.permission_code == permission
        and scope_matches(override.factory_id, override.department, factory_id, department)
        and time_window_is_active(override.valid_from, override.valid_until, at)
    ]
    denied = [override for override in matching_overrides if override.effect == "deny"]
    if denied:
        return False, "user_override", tuple(sorted(override.id for override in denied)), "用户单独禁止"

    superadmin_grants = [
        grant
        for grant in user.grants
        if grant.role_code == "admin"
        and grant.factory_id == "*"
        and grant.department in {"*", "system"}
        and (grant.factory_ceiling is None or factory_id in grant.factory_ceiling)
        and time_window_is_active(grant.valid_from, grant.valid_until, at)
    ]
    if superadmin_grants:
        return (
            True,
            "superadmin",
            tuple(sorted(grant.binding_id for grant in superadmin_grants if grant.binding_id)),
            "集团超级管理员",
        )

    allowed = [override for override in matching_overrides if override.effect == "allow"]
    if allowed:
        return True, "user_override", tuple(sorted(override.id for override in allowed)), "用户单独允许"

    matching_grants = [
        grant
        for grant in user.grants
        if permission in grant.permissions
        and (grant.factory_ceiling is None or factory_id in grant.factory_ceiling)
        and (
            (
                grant.unrestricted_department
                and system_position_grant_scope_source(grant, permission, factory_id) == "local"
                and system_position_grant_department_matches(grant, permission, department)
            )
            or (
                not grant.unrestricted_department
                and scope_matches(grant.factory_id, grant.department, factory_id, department)
            )
        )
        and time_window_is_active(grant.valid_from, grant.valid_until, at)
    ]
    if matching_grants:
        return (
            True,
            "role_binding",
            tuple(sorted(grant.binding_id for grant in matching_grants if grant.binding_id)),
            "、".join(sorted({grant.role_name for grant in matching_grants})),
        )

    # A built-in position is a function bundle, not an organization boundary.
    # Its binding factory remains the employee's home-factory anchor while the
    # position template decides whether read-only or operating permissions may
    # expand to another concrete factory. Most module permissions may be
    # combined across departments; explicitly department-owned actions such as
    # internal-quote initiation still have to match the bound position.
    cross_factory_grants = [
        grant
        for grant in user.grants
        if grant.unrestricted_department
        and permission in grant.permissions
        and system_position_grant_scope_source(grant, permission, factory_id)
        in {"cross_read", "cross_operate"}
        and system_position_grant_department_matches(grant, permission, department)
        and time_window_is_active(grant.valid_from, grant.valid_until, at)
    ]
    if cross_factory_grants:
        source_type = (
            "role_binding_cross_operate"
            if any(
                system_position_grant_scope_source(grant, permission, factory_id) == "cross_operate"
                for grant in cross_factory_grants
            )
            else "role_binding_cross_read"
        )
        return (
            True,
            source_type,
            tuple(sorted(grant.binding_id for grant in cross_factory_grants if grant.binding_id)),
            "、".join(sorted({grant.role_name for grant in cross_factory_grants})),
        )

    return False, "default", (), "默认拒绝"


def can(
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
    *,
    at: datetime | None = None,
) -> bool:
    """Evaluate the canonical IAM policy independent of rollout mode."""
    return authorization_decision(user, permission, factory_id, department, at=at)[0]


def build_auth_context(db: Session, user: AuthUser, *, at: datetime | None = None) -> AuthContext:
    from app.services.identity_resolver import resolve_identity_at, instant, utc_now
    from app.services.identity_sources import binding_grants, source_is_active
    checked_at = instant(at) if at else utc_now()
    identity = resolve_identity_at(db, user.id, checked_at)
    identity_profile = db.get(EmployeeProfile, user.id)
    all_permissions = list(db.scalars(select(AuthPermission).order_by(AuthPermission.code)).all())
    permission_code_by_id = {permission.id: permission.code for permission in all_permissions}
    permission_metadata = list(db.scalars(select(AuthPermissionMetadata)).all())
    permission_status_by_id = {item.permission_id: item.status for item in permission_metadata}
    permission_access_kind_by_id = {
        item.permission_id: (
            item.access_kind
            if item.access_kind in VALID_ACCESS_KINDS
            else default_permission_access_kind(permission_code_by_id.get(item.permission_id, ""))
        )
        for item in permission_metadata
    }
    active_permission_codes = frozenset(
        permission.code
        for permission in all_permissions
        if permission_status_by_id.get(permission.id, "active") == "active"
    )

    all_user_roles = list(
        db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id).order_by(AuthUserRole.id)).all()
    )
    user_role_ids = [item.id for item in all_user_roles]
    binding_metadata = (
        list(
            db.scalars(
                select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.user_role_id.in_(user_role_ids))
            ).all()
        )
        if user_role_ids
        else []
    )
    binding_metadata_by_id = {item.user_role_id: item for item in binding_metadata}
    user_roles: list[AuthUserRole] = []
    for user_role in all_user_roles:
        metadata = binding_metadata_by_id.get(user_role.id)
        if not source_is_active(db, metadata, identity_profile, checked_at):
            continue
        if metadata is not None and metadata.state != "active":
            continue
        if metadata is not None and not time_window_is_active(metadata.valid_from, metadata.valid_until, checked_at):
            continue
        user_roles.append(user_role)

    role_ids = sorted({user_role.role_id for user_role in user_roles})
    roles = list(db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids))).all()) if role_ids else []
    role_name_by_id = {role.id: role.name for role in roles}
    role_code_by_id = {role.id: role.code for role in roles}
    role_metadata = (
        list(db.scalars(select(AuthRoleMetadata).where(AuthRoleMetadata.role_id.in_(role_ids))).all())
        if role_ids
        else []
    )
    role_metadata_by_id = {item.role_id: item for item in role_metadata}
    system_position_role_ids = {
        role_id for role_id in role_ids if get_system_position(role_id) is not None
    }

    permissions_by_role_id: dict[str, set[str]] = {role_id: set() for role_id in role_ids}
    read_permissions_by_role_id: dict[str, set[str]] = {role_id: set() for role_id in role_ids}
    if role_ids:
        role_permissions = list(
            db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id.in_(role_ids))).all()
        )
        for role_permission in role_permissions:
            permission_code = permission_code_by_id.get(role_permission.permission_id)
            if permission_code in active_permission_codes:
                permissions_by_role_id.setdefault(role_permission.role_id, set()).add(permission_code)
                access_kind = permission_access_kind_by_id.get(
                    role_permission.permission_id,
                    default_permission_access_kind(permission_code),
                )
                if access_kind == READ_ACCESS_KIND:
                    read_permissions_by_role_id.setdefault(role_permission.role_id, set()).add(permission_code)

    def role_scope_mode(role_id: str) -> str:
        if role_id not in system_position_role_ids:
            return OWN_FACTORY_SCOPE
        metadata = role_metadata_by_id.get(role_id)
        value = metadata.scope_mode if metadata else OWN_FACTORY_SCOPE
        return value if value in VALID_SCOPE_MODES else OWN_FACTORY_SCOPE

    grants = tuple(
        AuthGrantContext(
            role_id=user_role.role_id,
            role_name=role_name_by_id.get(user_role.role_id, user_role.role_id),
            factory_id=user_role.factory_id,
            department=user_role.department,
            permissions=frozenset(permissions_by_role_id.get(user_role.role_id, set())),
            data_scope=(
                "all"
                if user_role.factory_id == "*" or role_scope_mode(user_role.role_id) != OWN_FACTORY_SCOPE
                else "factory"
                if user_role.role_id in system_position_role_ids
                else "department"
            ),
            scope_mode=role_scope_mode(user_role.role_id),
            read_permissions=frozenset(read_permissions_by_role_id.get(user_role.role_id, set())),
            unrestricted_department=user_role.role_id in system_position_role_ids,
            binding_id=user_role.id,
            role_code=role_code_by_id.get(user_role.role_id, user_role.role_id),
            valid_from=(binding_metadata_by_id[user_role.id].valid_from if user_role.id in binding_metadata_by_id else ""),
            valid_until=(binding_metadata_by_id[user_role.id].valid_until if user_role.id in binding_metadata_by_id else ""),
        )
        for user_role in user_roles
    )

    grants = binding_grants(db, grants, binding_metadata_by_id, active_permission_codes)

    override_rows = list(
        db.scalars(
            select(AuthUserPermissionOverride)
            .where(
                AuthUserPermissionOverride.user_id == user.id,
                AuthUserPermissionOverride.status == "active",
            )
            .order_by(AuthUserPermissionOverride.id)
        ).all()
    )
    overrides = tuple(
        AuthOverrideContext(
            id=override.id,
            permission_code=permission_code_by_id[override.permission_id],
            effect=override.effect,
            factory_id=override.factory_id,
            department=override.department,
            valid_from=override.valid_from,
            valid_until=override.valid_until,
            source_type=override.source_type,
        )
        for override in override_rows
        if override.effect in {"allow", "deny"}
        and source_is_active(db, override, identity_profile, checked_at)
        and permission_code_by_id.get(override.permission_id) in active_permission_codes
        and time_window_is_active(override.valid_from, override.valid_until, checked_at)
    )

    profile_row = db.get(EmployeeProfile, user.id)
    if profile_row is not None:
        profile = AuthProfileContext(
            primary_factory_id=identity["primary_factory_id"],
            primary_department=identity["primary_department"],
            position=identity["position"],
            phone=profile_row.phone,
            email=profile_row.email,
            confirmation_status=profile_row.confirmation_status,
        )
    else:
        profile = None

    revision_row = db.get(AuthUserAuthorizationRevision, user.id)
    role_names = tuple(role_name_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    role_codes = tuple(role_code_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    factory_scope_values = {user_role.factory_id for user_role in user_roles if user_role.factory_id}
    department_scope_values = {user_role.department for user_role in user_roles if user_role.department}
    if any(
        grant.unrestricted_department and grant.scope_mode != OWN_FACTORY_SCOPE and grant.factory_ceiling is None
        for grant in grants
    ):
        factory_scope_values.add("*")
    if any(grant.unrestricted_department for grant in grants):
        department_scope_values.add("*")
    factory_scopes = tuple(sorted(factory_scope_values))
    department_scopes = tuple(sorted(department_scope_values))

    from app.services.identity_resolver import stamp
    boundaries = [instant(identity["next_transition_at"])] if identity["next_transition_at"] else []
    for metadata in [*binding_metadata, *override_rows]:
        for value in (metadata.valid_from, metadata.valid_until):
            if value:
                try:
                    boundary = instant(value)
                except (TypeError, ValueError):
                    continue
                if boundary and boundary > checked_at:
                    boundaries.append(boundary)
    identity["next_transition_at"] = stamp(min(boundaries)) if boundaries else None
    identity["effective_context_key"] = hashlib.sha256((identity["effective_context_key"] + ":" +
        str(revision_row.revision if revision_row else 0) + ":" + ",".join(g.binding_id for g in grants) + ":" +
        ",".join(o.id for o in overrides)).encode()).hexdigest()[:24]

    context = AuthContext(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=role_names,
        role_codes=role_codes,
        permissions=frozenset(),
        factory_scopes=factory_scopes,
        department_scopes=department_scopes,
        grants=grants,
        force_password_change=bool(user.force_password_change),
        avatar_url=f"/api/auth/me/avatar?v={user.avatar_version}" if user.avatar_png and user.avatar_version else "",
        profile=profile,
        authorization_version=revision_row.revision if revision_row else 0,
        overrides=overrides,
        active_permission_codes=active_permission_codes,
        permission_catalog_loaded=True,
        account_available=user.status == "active" and identity["employment_status"] != "left",
        identity=identity,
    )

    scope_candidates = {
        (grant.factory_id, grant.department)
        for grant in grants
    } | {
        (override.factory_id, override.department)
        for override in overrides
    }
    if any(
        grant.role_code == "admin" and grant.factory_id == "*" and grant.department in {"*", "system"}
        for grant in grants
    ):
        scope_candidates.add(("*", "*"))

    effective_access: list[AuthEffectiveAccessContext] = []
    allowed_permission_codes: set[str] = set()
    for factory_id, department in sorted(scope_candidates):
        for permission_code in sorted(active_permission_codes):
            allowed, source_type, source_ids, source_name = authorization_decision(
                context,
                permission_code,
                factory_id,
                department,
                at=checked_at,
            )
            if allowed:
                allowed_permission_codes.add(permission_code)
            effective_access.append(
                AuthEffectiveAccessContext(
                    permission_code=permission_code,
                    factory_id=factory_id,
                    department=department,
                    effect="allow" if allowed else "deny",
                    allowed=allowed,
                    source_type=source_type,
                    source_ids=source_ids,
                    source_name=source_name,
                )
            )

    # ``permissions`` is a flat compatibility union consumed by older guards
    # and the frontend's target-less checks. A deny at the home factory must
    # not hide a permission that a cross-scoped built-in position still allows
    # at another real factory. Keep effective_access anchor-centric, but check
    # every known concrete factory when calculating that flat union.
    cross_position_permission_codes = {
        permission_code
        for grant in grants
        if grant.unrestricted_department
        for permission_code in grant.permissions
        if (
            grant.scope_mode != OWN_FACTORY_SCOPE
            or permission_code in SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES
        )
    }
    for permission_code in sorted(cross_position_permission_codes - allowed_permission_codes):
        if any(
            authorization_decision(
                context,
                permission_code,
                candidate_factory_id,
                "*",
                at=checked_at,
            )[0]
            for candidate_factory_id in sorted(ALLOWED_FACTORY_IDS)
        ):
            allowed_permission_codes.add(permission_code)

    return replace(
        context,
        permissions=frozenset(allowed_permission_codes),
        effective_access=tuple(effective_access),
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")

    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
    if session is None or session.status != "active":
        raise HTTPException(status_code=401, detail="登录已失效")

    expires_at = parse_time(session.expires_at)
    if expires_at is None or expires_at <= datetime.now():
        session.status = "expired"
        session.revoked_at = now_text()
        db.commit()
        raise HTTPException(status_code=401, detail="登录已过期")

    user = db.get(AuthUser, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="账号不可用")

    if user.force_password_change:
        allowed_request = (request.method, request.url.path) in {
            ("GET", "/api/auth/me"),
            ("POST", "/api/auth/change-password"),
            ("POST", "/api/auth/logout"),
        }
        if not allowed_request:
            raise HTTPException(status_code=403, detail="请先修改临时密码")

    return build_auth_context(db, user)


def to_auth_response(context: AuthContext) -> AuthMeResponse:
    return AuthMeResponse(
        id=context.id,
        username=context.username,
        display_name=context.display_name,
        roles=list(context.roles),
        permissions=sorted(context.permissions),
        factory_scopes=list(context.factory_scopes),
        department_scopes=list(context.department_scopes),
        grants=[
            {
                "factory_ceiling": list(grant.factory_ceiling) if grant.factory_ceiling is not None else None,
                "assignment_id": grant.assignment_id,
                "role_id": grant.role_id,
                "role_name": grant.role_name,
                "factory_id": grant.factory_id,
                "department": grant.department,
                "permissions": sorted(grant.permissions),
                "data_scope": grant.data_scope,
                "scope_mode": grant.scope_mode,
                "read_permission_codes": sorted(grant.read_permissions),
                "unrestricted_department": grant.unrestricted_department,
            }
            for grant in context.grants
        ],
        force_password_change=context.force_password_change,
        avatar_url=context.avatar_url,
        profile=(
            {
                "primary_factory_id": context.profile.primary_factory_id,
                "primary_department": context.profile.primary_department,
                "position": context.profile.position,
                "phone": context.profile.phone,
                "email": context.profile.email,
                "confirmation_status": context.profile.confirmation_status,
            }
            if context.profile
            else None
        ),
        authorization_version=context.authorization_version,
        effective_access=[
            {
                "permission_code": access.permission_code,
                "factory_id": access.factory_id,
                "department": access.department,
                "effect": access.effect,
                "allowed": access.allowed,
                "source_type": access.source_type,
                "source_ids": list(access.source_ids),
                "source_name": access.source_name,
            }
            for access in context.effective_access
        ],
        authz_mode="enforce" if context.identity and context.identity["identity_mode"] == "v2" else settings.authz_mode,
        identity=context.identity,
    )


def has_factory_scope(user: AuthContext, factory_id: str) -> bool:
    return "*" in user.factory_scopes or factory_id in user.factory_scopes


def has_permission_in_scope(
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
) -> bool:
    if user.identity and user.identity.get("identity_mode") == "v2":
        return can(user, permission, factory_id, department)
    canonical_result, canonical_source, _, _ = authorization_decision(
        user,
        permission,
        factory_id,
        department,
    )
    if canonical_result and canonical_source == "superadmin":
        return True
    if settings.authz_mode == "enforce":
        return canonical_result

    legacy_result = legacy_has_permission_in_scope(user, permission, factory_id, department)
    if settings.authz_mode == "shadow" and legacy_result != canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s permission=%s scope=%s/%s legacy=%s canonical=%s",
            user.id,
            permission,
            factory_id,
            department or "*",
            legacy_result,
            canonical_result,
        )
    return legacy_result


def legacy_has_permission_in_scope(
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
) -> bool:
    for grant in user.grants:
        if permission not in grant.permissions:
            continue
        if grant.unrestricted_department:
            if (
                system_position_grant_scope_source(grant, permission, factory_id) is not None
                and system_position_grant_department_matches(grant, permission, department)
            ):
                return True
            continue
        if grant.factory_id != "*" and grant.factory_id != factory_id:
            continue
        if grant.factory_id == "*":
            return True
        if department and grant.department not in {"*", department}:
            continue
        return True

    return False


def ensure_factory_scope(db: Session, user: AuthContext, factory_id: str) -> None:
    if has_factory_scope(user, factory_id):
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"无厂区数据权限：{factory_id}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无该厂区数据权限")


def ensure_permission(db: Session, user: AuthContext, permission: str) -> None:
    if permission in user.permissions:
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"缺少权限：{permission}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无操作权限")


def ensure_permission_in_scope(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
) -> None:
    if has_permission_in_scope(user, permission, factory_id, department):
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"缺少授权范围内权限：{permission}@{factory_id}/{department or '*'}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无授权范围内操作权限")
