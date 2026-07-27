from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.auth import (
    ALLOWED_FACTORY_IDS,
    AuthContext,
    add_auth_audit,
    can,
)
from app.services.business_authz import is_local_factory, is_wildcard_super_admin


INJECTION_READ_PERMISSION = "injection_schedule:read"
INJECTION_EDIT_PERMISSION = "injection_schedule:edit"
INJECTION_PUBLISH_PERMISSION = "injection_schedule:publish"
INJECTION_CONFIG_PERMISSION = "injection_schedule:config"
INJECTION_CROSS_FACTORY_READ_PERMISSION = (
    "injection_schedule:cross_factory_read"
)
INJECTION_DEPARTMENTS = ("production", "molding", "management")


def validate_injection_factory_id(factory_id: str) -> str:
    normalized = factory_id.strip()
    if (
        normalized != factory_id
        or normalized == "*"
        or normalized not in ALLOWED_FACTORY_IDS
    ):
        raise HTTPException(status_code=404, detail="未找到该厂区")
    return normalized


def has_injection_permission(
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> bool:
    return any(
        can(user, permission, factory_id, department)
        for department in INJECTION_DEPARTMENTS
    )


def ensure_injection_read(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> str:
    validate_injection_factory_id(factory_id)
    if is_wildcard_super_admin(user):
        return "admin"
    if is_local_factory(user, factory_id) and has_injection_permission(
        user,
        INJECTION_READ_PERMISSION,
        factory_id,
    ):
        return "local"
    if has_injection_permission(
        user,
        INJECTION_CROSS_FACTORY_READ_PERMISSION,
        factory_id,
    ):
        return "cross_factory_read"
    _deny(
        db,
        user,
        f"缺少注塑排产读取权限：{factory_id}",
        "无该厂区注塑排产查看权限",
    )


def ensure_injection_write(
    db: Session,
    user: AuthContext,
    factory_id: str,
    permission: str,
) -> None:
    validate_injection_factory_id(factory_id)
    if permission not in {
        INJECTION_EDIT_PERMISSION,
        INJECTION_CONFIG_PERMISSION,
        INJECTION_PUBLISH_PERMISSION,
    }:
        raise RuntimeError(f"unsupported injection write permission: {permission}")
    if is_wildcard_super_admin(user):
        return
    if not is_local_factory(user, factory_id):
        _deny(
            db,
            user,
            f"禁止跨厂写入注塑排产：{permission}@{factory_id}",
            "注塑排产仅允许本厂写入",
        )
    if has_injection_permission(user, permission, factory_id):
        return
    _deny(
        db,
        user,
        f"缺少注塑排产写入权限：{permission}@{factory_id}",
        "无注塑排产操作权限",
    )


def _deny(
    db: Session,
    user: AuthContext,
    detail: str,
    public_message: str,
) -> None:
    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=detail,
    )
    db.commit()
    raise HTTPException(status_code=403, detail=public_message)
