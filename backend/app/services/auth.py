import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import (
    AuthAuditLog,
    AuthPermission,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
)
from app.schemas.auth import AuthMeResponse

SESSION_COOKIE_NAME = "rr_session"
DEFAULT_PASSWORD = "123456"
PASSWORD_HASH_ITERATIONS = 160_000
SESSION_HOURS = 12

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
    "system:user_manage",
    "system:role_manage",
]

DEFAULT_ROLES = [
    ("engineer", "工程师", "工程部开单与草稿维护"),
    ("engineering_supervisor", "工程主管", "工程主管审核"),
    ("manager", "经理", "经理终审、改价和敏感审计"),
    ("molding_clerk", "啤机部文员", "啤机部啤办任务接收、回填和完成"),
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
    "molding_clerk": {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
    },
    "molding_operator": {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:notification_read",
    },
    "molding_supervisor": {
        "molding_sample:read",
        "molding_sample:production_read",
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
    },
    "admin": set(MOLDING_SAMPLE_PERMISSIONS),
}

DEFAULT_USERS = [
    ("user-engineer", "engineer", "华兴工程师", "engineer", "huaxing", "engineering"),
    ("user-supervisor", "supervisor", "华兴工程主管", "engineering_supervisor", "huaxing", "engineering"),
    ("user-manager", "manager", "华兴经理", "manager", "huaxing", "management"),
    ("user-molding-clerk", "molding_clerk", "华兴啤机部文员", "molding_clerk", "huaxing", "molding"),
    ("user-admin", "admin", "系统管理员", "admin", "*", "system"),
]

RETIRED_DEFAULT_USERNAMES = {"molding", "warehouse"}
RETIRED_DEFAULT_USER_IDS = {"user-molding", "user-warehouse"}


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


def seed_auth_defaults(db: Session) -> None:
    now = now_text()
    active_default_user_ids = {user_id for user_id, *_ in DEFAULT_USERS}
    active_role_ids = {role_id for role_id, *_ in DEFAULT_ROLES}

    for code in MOLDING_SAMPLE_PERMISSIONS:
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
            salt, password_hash = make_password_hash(DEFAULT_PASSWORD)
            db.add(
                AuthUser(
                    id=user_id,
                    username=username,
                    display_name=display_name,
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            user.username = username
            user.display_name = display_name
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
    user = db.scalar(select(AuthUser).where(AuthUser.username == username.strip()))
    if not user or user.status != "active" or not verify_password(password, user):
        add_auth_audit(db, "login_denied", username=username.strip(), detail="用户名或密码错误", request=request)
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login_at = now_text()
    user.updated_at = now_text()
    add_auth_audit(db, "login_success", username=user.username, user_id=user.id, detail="账号登录成功", request=request)
    db.commit()
    return user


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
        db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all()
    )
    role_ids = [user_role.role_id for user_role in user_roles]
    roles = list(db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids))).all()) if role_ids else []
    role_name_by_id = {role.id: role.name for role in roles}
    role_code_by_id = {role.id: role.code for role in roles}

    permission_codes: set[str] = set()
    if role_ids:
        role_permissions = list(
            db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id.in_(role_ids))).all()
        )
        permission_ids = [role_permission.permission_id for role_permission in role_permissions]
        if permission_ids:
            permissions = db.scalars(select(AuthPermission).where(AuthPermission.id.in_(permission_ids))).all()
            permission_codes = {permission.code for permission in permissions}

    role_names = tuple(role_name_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    role_codes = tuple(role_code_by_id.get(user_role.role_id, user_role.role_id) for user_role in user_roles)
    factory_scopes = tuple(sorted({user_role.factory_id for user_role in user_roles if user_role.factory_id}))
    department_scopes = tuple(sorted({user_role.department for user_role in user_roles if user_role.department}))

    return AuthContext(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        roles=role_names,
        role_codes=role_codes,
        permissions=frozenset(permission_codes),
        factory_scopes=factory_scopes,
        department_scopes=department_scopes,
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
        force_password_change=context.force_password_change,
    )


def has_factory_scope(user: AuthContext, factory_id: str) -> bool:
    return "*" in user.factory_scopes or factory_id in user.factory_scopes


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
