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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.auth import (
    AuthAuditLog,
    AuthIamState,
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
from app.schemas.auth import AuthMeResponse, PasswordResetRequest, PasswordResetResponse, RegisterRequest, RegisterResponse

SESSION_COOKIE_NAME = "rr_session"
logger = logging.getLogger(__name__)
LEGACY_READ_COMPAT_MARKER = "legacy_read_compat_v1_completed"
LEGACY_READ_COMPAT_PERMISSION = "injection_schedule:read"
LEGACY_EXPORT_COMPAT_MARKER = "legacy_export_compat_v1_completed"
LEGACY_EXPORT_COMPAT_PERMISSION = "molding_sample:export"
RAW_MATERIAL_WRITE_DEFAULT_GRANT_MARKER = "raw_material_write_default_grant_v1_completed"
RAW_MATERIAL_WRITE_PERMISSION = "molding_sample:raw_material_write"
RAW_MATERIAL_WRITE_DEFAULT_ROLE_IDS = ("engineer", "engineering_supervisor", "warehouse_keeper")
INTERNAL_PRICING_WORKFLOW_GRANT_MARKER = "internal_pricing_workflow_grants_v1_completed"
INTERNAL_PRICING_WORKFLOW_ROLE_PERMISSIONS = {
    "sales_customer_owner": {
        "internal_pricing:read",
        "internal_pricing:create",
        "internal_pricing:edit",
        "internal_pricing:export",
    },
    "sales_customer_supervisor": {
        "internal_pricing:read",
        "internal_pricing:create",
        "internal_pricing:edit",
        "internal_pricing:review",
        "internal_pricing:export",
    },
}
DEFAULT_PASSWORD = "123456"
PASSWORD_HASH_ITERATIONS = 160_000
SESSION_HOURS = 12
MIN_SEED_ADMIN_PASSWORD_LENGTH = 12
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW_MINUTES = 15
LOGIN_LOCKED_MESSAGE = f"登录失败次数过多，请 {LOGIN_FAILURE_WINDOW_MINUTES} 分钟后再试"
BAD_CREDENTIALS_MESSAGE = "用户名或密码错误"
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

MOLDING_SAMPLE_PERMISSIONS = [
    "molding_sample:read",
    "molding_sample:cross_factory_read",
    "molding_sample:cross_factory_cost_read",
    "molding_sample:export",
    "molding_sample:create",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:supervisor_review",
    "molding_sample:manager_review",
    "molding_sample:raw_material_write",
    "molding_sample:warehouse_requisition",
    "molding_sample:inventory_issue",
    "molding_sample:production_read",
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:price_update",
    "molding_sample:audit_read",
    "molding_sample:notification_read",
    "carton_mark:read",
    "carton_mark:template_upload",
    "carton_mark:photo_upload",
    "carton_mark:review",
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "internal_pricing:read",
    "internal_pricing:create",
    "internal_pricing:edit",
    "internal_pricing:review",
    "internal_pricing:export",
    "system:user_manage",
    "system:role_manage",
]

INJECTION_SCHEDULE_PERMISSIONS = [
    "injection_schedule:read",
    "injection_schedule:import",
]

IAM_PERMISSIONS = [
    "system:access_manage",
    "system:access_request",
    "system:access_approve",
    "system:audit_read",
    "system:permission_catalog_read",
]

APPLICATION_PERMISSIONS = list(dict.fromkeys(MOLDING_SAMPLE_PERMISSIONS + INJECTION_SCHEDULE_PERMISSIONS + IAM_PERMISSIONS))

DEFAULT_ROLES = [
    ("group_molding_readonly", "集团啤办只读", "跨厂查看啤办单，默认隐藏成本且不可导出或修改"),
    ("engineer", "工程师", "工程开单、本人草稿维护、导出和通知；不含审核、啤机回填、仓库出库或成本权限"),
    ("engineering_supervisor", "工程主管", "工程主管审核"),
    ("manager", "经理", "经理终审、改价和敏感审计"),
    ("warehouse_keeper", "PMC / 仓管", "啤办领料、发料与库存管理"),
    ("carton_warehouse_keeper", "纸箱仓管", "纸箱箱唛 PDF 模板维护"),
    ("qa_inspector", "QA 检验员", "QA 箱唛实拍上传与核对"),
    ("molding_clerk", "啤机部文员", "啤办任务接收、开始、生产回填和完成；不可修改或删除工程草稿"),
    ("molding_production_observer", "啤办生产只读观察者", "只读查看本厂啤办生产任务和进度，不可开始、回填或完成"),
    ("sales_customer_owner", "车间业务跟客", "按车间和客户范围转换报客价"),
    ("sales_customer_supervisor", "车间业务主管", "统筹车间客户报价转换、复核和报客价输出"),
    ("factory_permission_admin", "厂区权限管理员", "在授权厂区内管理普通用户权限"),
    ("department_permission_admin", "部门权限管理员", "在授权部门内管理普通用户权限"),
    ("admin", "系统管理员", "系统配置和权限管理"),
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
    },
    "engineering_supervisor": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:raw_material_write",
        "molding_sample:supervisor_review",
        "molding_sample:notification_read",
    },
    "manager": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:edit_draft",
        "molding_sample:delete_draft",
        "molding_sample:manager_review",
        "molding_sample:price_update",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
    },
    "warehouse_keeper": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:raw_material_write",
        "molding_sample:warehouse_requisition",
        "molding_sample:inventory_issue",
        "molding_sample:notification_read",
    },
    "carton_warehouse_keeper": {
        "carton_mark:read",
        "carton_mark:template_upload",
    },
    "qa_inspector": {
        "carton_mark:read",
        "carton_mark:photo_upload",
        "carton_mark:review",
    },
    "molding_clerk": {
        "molding_sample:read",
        "molding_sample:export",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
        "injection_schedule:read",
        "injection_schedule:import",
    },
    "molding_production_observer": {
        "molding_sample:production_read",
    },
    "sales_customer_owner": {
        "customer_price:read",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
        "internal_pricing:read",
        "internal_pricing:create",
        "internal_pricing:edit",
        "internal_pricing:export",
    },
    "sales_customer_supervisor": {
        "customer_price:read",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
        "internal_pricing:read",
        "internal_pricing:create",
        "internal_pricing:edit",
        "internal_pricing:review",
        "internal_pricing:export",
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
        "injection_schedule:read",
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
        "injection_schedule:read",
        "injection_schedule:import",
    },
    "admin": set(APPLICATION_PERMISSIONS),
}

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
    "engineering",
    "pmc-warehouse",
    "production",
    "qa",
    "sales-business",
}


@dataclass(frozen=True)
class AuthGrantContext:
    role_id: str
    role_name: str
    factory_id: str
    department: str
    permissions: frozenset[str]
    data_scope: str = "department"
    binding_id: str = ""
    role_code: str = ""
    valid_from: str = ""
    valid_until: str = ""


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
    checked_at = at or datetime.now()
    starts_at = parse_time(valid_from)
    ends_at = parse_time(valid_until)
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
        "scope_type": "factory_department",
        "status": "active",
        "sort_order": sort_order,
    }


def seed_iam_sidecars(db: Session, now: str) -> None:
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


def seed_internal_pricing_workflow_grants_once(db: Session, now: str) -> int:
    """Extend existing sales role templates for the approved collaborative quote workflow."""
    if db.get(AuthIamState, INTERNAL_PRICING_WORKFLOW_GRANT_MARKER) is not None:
        return 0

    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(select(AuthPermission)).all()
    }
    created_count = 0
    updated_role_ids: set[str] = set()
    for role_id, permission_codes in INTERNAL_PRICING_WORKFLOW_ROLE_PERMISSIONS.items():
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

    db.add(
        AuthIamState(
            key=INTERNAL_PRICING_WORKFLOW_GRANT_MARKER,
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


def seed_legacy_read_compat_once(db: Session, now: str) -> int:
    if db.get(AuthIamState, LEGACY_READ_COMPAT_MARKER) is not None:
        return 0

    # Flush sidecar backfills so canonical contexts see the same state that will
    # be committed with the one-time completion marker.
    db.flush()
    permission = db.scalar(select(AuthPermission).where(AuthPermission.code == LEGACY_READ_COMPAT_PERMISSION))
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
            profile = db.get(EmployeeProfile, user.id)
            if (
                approved_request is None
                or profile is None
                or not profile.primary_factory_id
                or not profile.primary_department
            ):
                continue

            admin_binding_id = db.scalar(
                select(AuthUserRole.id)
                .join(AuthRole, AuthRole.id == AuthUserRole.role_id)
                .where(AuthUserRole.user_id == user.id, AuthRole.code == "admin")
                .limit(1)
            )
            if admin_binding_id is not None:
                continue

            context = build_auth_context(db, user)
            if can(
                context,
                LEGACY_READ_COMPAT_PERMISSION,
                profile.primary_factory_id,
                profile.primary_department,
            ):
                continue

            identity = ":".join(
                (
                    user.id,
                    permission.id,
                    profile.primary_factory_id,
                    profile.primary_department,
                )
            )
            override_id = f"legacy-read-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:40]}"
            if db.get(AuthUserPermissionOverride, override_id) is not None:
                continue
            db.add(
                AuthUserPermissionOverride(
                    id=override_id,
                    user_id=user.id,
                    permission_id=permission.id,
                    effect="allow",
                    factory_id=profile.primary_factory_id,
                    department=profile.primary_department,
                    status="active",
                    valid_from=now,
                    valid_until="",
                    reason="历史登录可读兼容",
                    source_type="legacy_read_compat",
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
            key=LEGACY_READ_COMPAT_MARKER,
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
                AuthUserPermissionOverride.status == "active",
                AuthUserPermissionOverride.effect.in_({"allow", "deny"}),
                AuthUserPermissionOverride.source_type.notin_(
                    {"legacy_read_compat", "legacy_export_compat"}
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

    for code in APPLICATION_PERMISSIONS:
        permission_id = f"perm-{code.replace(':', '-')}"
        if db.get(AuthPermission, permission_id) is None:
            db.add(AuthPermission(id=permission_id, code=code, name=code, description=""))

    for role_id, name, description in DEFAULT_ROLES:
        if db.get(AuthRole, role_id) is None:
            db.add(AuthRole(id=role_id, code=role_id, name=name, description=description))
            created_role_ids.add(role_id)

    db.flush()
    permissions_by_code = {permission.code: permission for permission in db.scalars(select(AuthPermission)).all()}

    # Default mappings initialize brand-new roles only. Existing role templates are
    # administrator-owned data and must never be restored or trimmed on startup.
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
                        force_password_change=1,
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
    seed_internal_pricing_workflow_grants_once(db, now)
    seed_legacy_read_compat_once(db, now)
    seed_legacy_export_compat_once(db, now)
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

    user.last_login_at = now_text()
    user.updated_at = now_text()
    add_auth_audit(db, "login_success", username=user.username, user_id=user.id, detail="账号登录成功", request=request)
    db.commit()
    return user


def register_user(db: Session, payload: RegisterRequest, request: Request | None = None) -> RegisterResponse:
    username = payload.username.strip()
    display_name = payload.display_name.strip()
    phone = payload.phone.strip()
    email = payload.email.strip()
    factory_id = payload.factory_id.strip()
    department = payload.department.strip()
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
    if factory_id not in ALLOWED_FACTORY_IDS:
        raise HTTPException(status_code=400, detail="请选择有效厂区")
    if department not in ALLOWED_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="请选择有效部门")
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
) -> PasswordResetResponse:
    username = payload.username.strip()
    display_name = payload.display_name.strip()
    contact = payload.contact.strip()
    note = payload.note.strip()

    if not username:
        raise HTTPException(status_code=400, detail="请输入需要重置密码的账号")
    if not contact:
        raise HTTPException(status_code=400, detail="请填写联系电话或邮箱")

    now = now_text()
    matched_user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    target_factory_id = "*"
    target_department = "system"
    if matched_user is not None:
        profile = db.get(EmployeeProfile, matched_user.id)
        if profile is not None and profile.primary_factory_id and profile.primary_department:
            target_factory_id = profile.primary_factory_id
            target_department = profile.primary_department
        else:
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
    notification_id = f"system-notification-{secrets.token_hex(12)}"
    payload_json = {
        "username": username,
        "display_name": display_name,
        "contact": contact,
        "note": note,
        "matched_user_id": matched_user.id if matched_user else "",
        "requested_at": now,
    }
    applicant_label = display_name or username

    db.add(
        SystemNotification(
            id=notification_id,
            target_permission="system:user_manage",
            target_factory_id=target_factory_id,
            target_department=target_department,
            type="password_reset",
            title="密码重置待处理",
            message=f"{applicant_label} 提交密码重置申请，账号 {username}，联系方式 {contact}",
            payload_json=json.dumps(payload_json, ensure_ascii=False),
            status="unread",
            created_at=now,
        )
    )
    add_auth_audit(
        db,
        "password_reset_requested",
        username=username,
        user_id=matched_user.id if matched_user else "",
        detail=f"密码重置申请：{contact}",
        request=request,
    )
    db.commit()

    return PasswordResetResponse(status="submitted", message="密码重置申请已提交，请等待管理员核验处理")


def create_session(db: Session, user: AuthUser, request: Request | None = None) -> str:
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
    if user.active_permission_codes and permission not in user.active_permission_codes:
        return False, "inactive_permission", (), "权限未启用"

    superadmin_grants = [
        grant
        for grant in user.grants
        if grant.role_code == "admin"
        and grant.factory_id == "*"
        and grant.department in {"*", "system"}
        and time_window_is_active(grant.valid_from, grant.valid_until, at)
    ]
    if superadmin_grants:
        return (
            True,
            "superadmin",
            tuple(sorted(grant.binding_id for grant in superadmin_grants if grant.binding_id)),
            "集团超级管理员",
        )

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

    allowed = [override for override in matching_overrides if override.effect == "allow"]
    if allowed:
        return True, "user_override", tuple(sorted(override.id for override in allowed)), "用户单独允许"

    matching_grants = [
        grant
        for grant in user.grants
        if permission in grant.permissions
        and scope_matches(grant.factory_id, grant.department, factory_id, department)
        and time_window_is_active(grant.valid_from, grant.valid_until, at)
    ]
    if matching_grants:
        return (
            True,
            "role_binding",
            tuple(sorted(grant.binding_id for grant in matching_grants if grant.binding_id)),
            "、".join(sorted({grant.role_name for grant in matching_grants})),
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


def build_auth_context(db: Session, user: AuthUser) -> AuthContext:
    checked_at = datetime.now()
    all_permissions = list(db.scalars(select(AuthPermission).order_by(AuthPermission.code)).all())
    permission_code_by_id = {permission.id: permission.code for permission in all_permissions}
    permission_metadata = list(db.scalars(select(AuthPermissionMetadata)).all())
    permission_status_by_id = {item.permission_id: item.status for item in permission_metadata}
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
        if metadata is not None and metadata.state != "active":
            continue
        if metadata is not None and not time_window_is_active(metadata.valid_from, metadata.valid_until, checked_at):
            continue
        user_roles.append(user_role)

    role_ids = sorted({user_role.role_id for user_role in user_roles})
    roles = list(db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids))).all()) if role_ids else []
    role_name_by_id = {role.id: role.name for role in roles}
    role_code_by_id = {role.id: role.code for role in roles}

    permissions_by_role_id: dict[str, set[str]] = {role_id: set() for role_id in role_ids}
    if role_ids:
        role_permissions = list(
            db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id.in_(role_ids))).all()
        )
        for role_permission in role_permissions:
            permission_code = permission_code_by_id.get(role_permission.permission_id)
            if permission_code in active_permission_codes:
                permissions_by_role_id.setdefault(role_permission.role_id, set()).add(permission_code)

    grants = tuple(
        AuthGrantContext(
            role_id=user_role.role_id,
            role_name=role_name_by_id.get(user_role.role_id, user_role.role_id),
            factory_id=user_role.factory_id,
            department=user_role.department,
            permissions=frozenset(permissions_by_role_id.get(user_role.role_id, set())),
            data_scope="all" if user_role.factory_id == "*" else "department",
            binding_id=user_role.id,
            role_code=role_code_by_id.get(user_role.role_id, user_role.role_id),
            valid_from=(binding_metadata_by_id[user_role.id].valid_from if user_role.id in binding_metadata_by_id else ""),
            valid_until=(binding_metadata_by_id[user_role.id].valid_until if user_role.id in binding_metadata_by_id else ""),
        )
        for user_role in user_roles
    )

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
        and permission_code_by_id.get(override.permission_id) in active_permission_codes
        and time_window_is_active(override.valid_from, override.valid_until, checked_at)
    )

    profile_row = db.get(EmployeeProfile, user.id)
    if profile_row is not None:
        profile = AuthProfileContext(
            primary_factory_id=profile_row.primary_factory_id,
            primary_department=profile_row.primary_department,
            position=profile_row.position,
            phone=profile_row.phone,
            email=profile_row.email,
            confirmation_status=profile_row.confirmation_status,
        )
    else:
        profile = None

    revision_row = db.get(AuthUserAuthorizationRevision, user.id)
    role_names = tuple(role_name_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    role_codes = tuple(role_code_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    factory_scopes = tuple(sorted({user_role.factory_id for user_role in user_roles if user_role.factory_id}))
    department_scopes = tuple(sorted({user_role.department for user_role in user_roles if user_role.department}))

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
                "role_id": grant.role_id,
                "role_name": grant.role_name,
                "factory_id": grant.factory_id,
                "department": grant.department,
                "permissions": sorted(grant.permissions),
                "data_scope": grant.data_scope,
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
        authz_mode=settings.authz_mode,
    )


def has_factory_scope(user: AuthContext, factory_id: str) -> bool:
    return "*" in user.factory_scopes or factory_id in user.factory_scopes


def has_permission_in_scope(
    user: AuthContext,
    permission: str,
    factory_id: str,
    department: str | None = None,
) -> bool:
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
