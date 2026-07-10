import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.auth import (
    AuthAuditLog,
    AuthPermission,
    AuthRegistrationRequest,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
    SystemNotification,
)
from app.schemas.auth import AuthMeResponse, PasswordResetRequest, PasswordResetResponse, RegisterRequest, RegisterResponse

SESSION_COOKIE_NAME = "rr_session"
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
CHINESE_CHARACTER_RANGES = (
    ("\u3400", "\u4dbf"),
    ("\u4e00", "\u9fff"),
    ("\uf900", "\ufaff"),
)

MOLDING_SAMPLE_PERMISSIONS = [
    "molding_sample:read",
    "molding_sample:create",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:supervisor_review",
    "molding_sample:manager_review",
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
    "system:user_manage",
    "system:role_manage",
]

INJECTION_SCHEDULE_PERMISSIONS = [
    "injection_schedule:read",
    "injection_schedule:import",
]

APPLICATION_PERMISSIONS = MOLDING_SAMPLE_PERMISSIONS + INJECTION_SCHEDULE_PERMISSIONS

DEFAULT_ROLES = [
    ("engineer", "工程师", "工程部开单与草稿维护"),
    ("engineering_supervisor", "工程主管", "工程主管审核"),
    ("manager", "经理", "经理终审、改价和敏感审计"),
    ("carton_warehouse_keeper", "纸箱仓管", "纸箱箱唛 PDF 模板维护"),
    ("qa_inspector", "QA 检验员", "QA 箱唛实拍上传与核对"),
    ("molding_clerk", "啤机部文员", "啤机部啤办任务接收、回填和完成"),
    ("sales_customer_owner", "车间业务跟客", "按车间和客户范围转换报客价"),
    ("sales_customer_supervisor", "车间业务主管", "统筹车间客户报价转换、复核和报客价输出"),
    ("admin", "系统管理员", "系统配置和权限管理"),
]

ROLE_PERMISSIONS = {
    "engineer": {
        "molding_sample:read",
        "molding_sample:create",
        "molding_sample:edit_draft",
        "molding_sample:delete_draft",
        "molding_sample:notification_read",
    },
    "engineering_supervisor": {
        "molding_sample:read",
        "molding_sample:supervisor_review",
        "molding_sample:notification_read",
    },
    "manager": {
        "molding_sample:read",
        "molding_sample:edit_draft",
        "molding_sample:delete_draft",
        "molding_sample:manager_review",
        "molding_sample:price_update",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
    },
    "warehouse_keeper": {
        "molding_sample:read",
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
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
        "injection_schedule:read",
        "injection_schedule:import",
    },
    "sales_customer_owner": {
        "customer_price:read",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
    },
    "sales_customer_supervisor": {
        "customer_price:read",
        "customer_price:import_internal_quote",
        "customer_price:export_customer_quote",
        "customer_price:compare",
    },
    "molding_operator": {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
        "injection_schedule:read",
    },
    "molding_supervisor": {
        "molding_sample:read",
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
    ("user-admin", "admin", "系统管理员", "admin", "*", "system"),
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
ALLOWED_FACTORY_IDS = {"huakang-a", "huakang-b", "huadeng", "huaxing"}
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

    @property
    def primary_role(self) -> str:
        return self.roles[0] if self.roles else ""


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


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


def seed_auth_defaults(db: Session) -> None:
    now = now_text()
    active_default_user_ids = {user_id for user_id, *_ in DEFAULT_USERS}
    active_role_ids = {role_id for role_id, *_ in DEFAULT_ROLES}

    for code in APPLICATION_PERMISSIONS:
        permission_id = f"perm-{code.replace(':', '-')}"
        if db.get(AuthPermission, permission_id) is None:
            db.add(AuthPermission(id=permission_id, code=code, name=code, description=""))

    for role_id, code, description in DEFAULT_ROLES:
        role = db.get(AuthRole, role_id)
        if role is None:
            db.add(AuthRole(id=role_id, code=role_id, name=code, description=description))
        else:
            role.name = code
            role.description = description

    db.flush()

    permissions_by_code = {
        permission.code: permission
        for permission in db.scalars(select(AuthPermission)).all()
    }
    for role_id, permission_codes in ROLE_PERMISSIONS.items():
        if role_id not in active_role_ids:
            continue

        desired_permission_ids = {
            permissions_by_code[permission_code].id
            for permission_code in permission_codes
        }
        existing_role_permissions = list(
            db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id == role_id)).all()
        )
        for role_permission in existing_role_permissions:
            if role_permission.permission_id not in desired_permission_ids:
                db.delete(role_permission)

        for permission_code in permission_codes:
            permission = permissions_by_code[permission_code]
            role_permission_id = f"{role_id}:{permission.id}"
            if db.get(AuthRolePermission, role_permission_id) is None:
                db.add(
                    AuthRolePermission(
                        id=role_permission_id,
                        role_id=role_id,
                        permission_id=permission.id,
                    )
                )

    if not settings.seed_default_accounts:
        db.commit()
        return

    seed_admin_password = get_seed_admin_password()
    if not seed_admin_password:
        for user_id, *_ in DEFAULT_USERS:
            user = db.get(AuthUser, user_id)
            if user is not None and verify_password(DEFAULT_PASSWORD, user):
                user.status = "locked"
                user.force_password_change = 1
                user.updated_at = now
        db.commit()
        return

    retired_users = db.scalars(
        select(AuthUser).where(
            (AuthUser.username.in_(RETIRED_DEFAULT_USERNAMES))
            | (AuthUser.id.in_(RETIRED_DEFAULT_USER_IDS - active_default_user_ids))
        )
    ).all()
    for user in retired_users:
        user.status = "retired"
        user.updated_at = now

    for user_id, username, display_name, role_id, factory_id, department in DEFAULT_USERS:
        user = db.get(AuthUser, user_id)
        if user is None:
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
        else:
            user.username = username
            user.display_name = display_name
            if verify_password(DEFAULT_PASSWORD, user):
                salt, password_hash = make_password_hash(seed_admin_password)
                user.password_salt = salt
                user.password_hash = password_hash
                user.force_password_change = 1
            user.status = "active"
            user.updated_at = now

        user_role_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        existing_user_roles = list(
            db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user_id)).all()
        )
        for user_role in existing_user_roles:
            if user_role.id != user_role_id:
                db.delete(user_role)

        if db.get(AuthUserRole, user_role_id) is None:
            db.add(
                AuthUserRole(
                    id=user_role_id,
                    user_id=user_id,
                    role_id=role_id,
                    factory_id=factory_id,
                    department=department,
                )
            )

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
        for user_role in db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == existing_user.id)).all():
            db.delete(user_role)

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


def build_auth_context(db: Session, user: AuthUser) -> AuthContext:
    user_roles = list(
        db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id).order_by(AuthUserRole.id)).all()
    )
    role_ids = [user_role.role_id for user_role in user_roles]
    roles = list(db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids))).all()) if role_ids else []
    role_name_by_id = {role.id: role.name for role in roles}
    role_code_by_id = {role.id: role.code for role in roles}

    permission_codes: set[str] = set()
    permissions_by_role_id: dict[str, set[str]] = {role_id: set() for role_id in role_ids}
    if role_ids:
        role_permissions = list(
            db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id.in_(role_ids))).all()
        )
        permission_ids = sorted({role_permission.permission_id for role_permission in role_permissions})
        if permission_ids:
            permissions = db.scalars(select(AuthPermission).where(AuthPermission.id.in_(permission_ids))).all()
            permission_code_by_id = {permission.id: permission.code for permission in permissions}
            for role_permission in role_permissions:
                permission_code = permission_code_by_id.get(role_permission.permission_id)
                if not permission_code:
                    continue
                permission_codes.add(permission_code)
                permissions_by_role_id.setdefault(role_permission.role_id, set()).add(permission_code)

    role_names = tuple(role_name_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    role_codes = tuple(role_code_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    factory_scopes = tuple(sorted({user_role.factory_id for user_role in user_roles if user_role.factory_id}))
    department_scopes = tuple(sorted({user_role.department for user_role in user_roles if user_role.department}))
    grants = tuple(
        AuthGrantContext(
            role_id=user_role.role_id,
            role_name=role_name_by_id.get(user_role.role_id, user_role.role_id),
            factory_id=user_role.factory_id,
            department=user_role.department,
            permissions=frozenset(permissions_by_role_id.get(user_role.role_id, set())),
            data_scope="all" if user_role.factory_id == "*" else "department",
        )
        for user_role in user_roles
    )

    return AuthContext(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=role_names,
        role_codes=role_codes,
        permissions=frozenset(permission_codes),
        factory_scopes=factory_scopes,
        department_scopes=department_scopes,
        grants=grants,
        force_password_change=bool(user.force_password_change),
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
    )


def has_factory_scope(user: AuthContext, factory_id: str) -> bool:
    return "*" in user.factory_scopes or factory_id in user.factory_scopes


def has_permission_in_scope(
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
