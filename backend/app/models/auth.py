from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuthUser(Base):
    __tablename__ = "auth_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_salt: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    force_password_change: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthRole(Base):
    __tablename__ = "auth_roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class AuthPermission(Base):
    __tablename__ = "auth_permissions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class AuthRolePermission(Base):
    __tablename__ = "auth_role_permissions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(64), index=True)
    permission_id: Mapped[str] = mapped_column(String(96), index=True)


class AuthUserRole(Base):
    __tablename__ = "auth_user_roles"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    role_id: Mapped[str] = mapped_column(String(64), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    ip_address: Mapped[str] = mapped_column(String(128), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    revoked_at: Mapped[str] = mapped_column(String(32), default="")


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(128), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")


class AuthRegistrationRequest(Base):
    __tablename__ = "auth_registration_requests"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    position: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewer_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[str] = mapped_column(String(32), default="")
    reviewed_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class SystemNotification(Base):
    __tablename__ = "system_notifications"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    target_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_permission: Mapped[str] = mapped_column(String(128), default="", index=True)
    target_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    type: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="unread", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    read_at: Mapped[str] = mapped_column(String(32), default="")
    handled_at: Mapped[str] = mapped_column(String(32), default="")
