"""Explicit single-computer trial identity; no production accounts or grants."""
from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError


@dataclass(frozen=True)
class AuthContext:
    id: str = "local-jp-trial"
    username: str = "local-jp-trial"
    display_name: str = "本机试用"


def get_current_user():
    return AuthContext()


def refresh_user(request, db):
    return get_current_user()


def has_permission_for_departments(user, permission, factory, departments):
    return (isinstance(user, AuthContext) and factory == "huakang-b" and tuple(departments) == ("sales-business",)
        and permission in {"customer_order:read", "customer_order:write", "customer_order:export"})


def ensure_permission_for_departments(db, user, permission, factory, departments):
    if not has_permission_for_departments(user, permission, factory, departments):
        raise HTTPException(403, "单机试用仅支持华康 B JP 问单。")


def actor_name(user):
    return f"{user.display_name} ({user.id})"


def transaction(db, operation):
    try:
        result = operation()
        db.commit()
        return result
    except (IntegrityError, OperationalError) as error:
        db.rollback()
        raise HTTPException(409, "记录正在更新或存在重复，请刷新核对后再操作。") from error
    except BaseException:
        db.rollback()
        raise
