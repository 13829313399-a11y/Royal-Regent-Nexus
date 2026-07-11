from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
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
    avatar_png: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_version: Mapped[str] = mapped_column(String(64), default="")
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
    role_id: Mapped[str] = mapped_column(ForeignKey("auth_roles.id", ondelete="CASCADE"), index=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("auth_permissions.id", ondelete="CASCADE"), index=True)


class AuthUserRole(Base):
    __tablename__ = "auth_user_roles"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("auth_roles.id", ondelete="CASCADE"), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True)
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
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True)
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


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    primary_department: Mapped[str] = mapped_column(String(64), default="", index=True)
    position: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    confirmation_status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    source_registration_request_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthPermissionMetadata(Base):
    __tablename__ = "auth_permission_metadata"

    permission_id: Mapped[str] = mapped_column(
        ForeignKey("auth_permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), default="", index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="normal", index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="factory_department", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthRoleMetadata(Base):
    __tablename__ = "auth_role_metadata"

    role_id: Mapped[str] = mapped_column(
        ForeignKey("auth_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    protected: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")
    updated_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class AuthRoleBindingMetadata(Base):
    __tablename__ = "auth_role_binding_metadata"

    user_role_id: Mapped[str] = mapped_column(
        ForeignKey("auth_user_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(32), default="active", index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="legacy_import", index=True)
    source_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_until: Mapped[str] = mapped_column(String(32), default="", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    approved_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    revoked_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    revoked_at: Mapped[str] = mapped_column(String(32), default="")
    revoke_reason: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthUserPermissionOverride(Base):
    __tablename__ = "auth_user_permission_overrides"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        index=True,
    )
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("auth_permissions.id", ondelete="CASCADE"),
        index=True,
    )
    effect: Mapped[str] = mapped_column(String(16), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_until: Mapped[str] = mapped_column(String(32), default="", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(64), default="manual", index=True)
    source_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    approved_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    revoked_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    revoked_at: Mapped[str] = mapped_column(String(32), default="")
    revoke_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthUserAuthorizationRevision(Base):
    __tablename__ = "auth_user_authorization_revisions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthIamState(Base):
    __tablename__ = "auth_iam_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthAccessRequest(Base):
    __tablename__ = "auth_access_requests"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    requester_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    base_revision: Mapped[int] = mapped_column(Integer, default=0)
    decision_by_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    decision_comment: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[str] = mapped_column(String(32), default="")
    decided_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class AuthAccessRequestItem(Base):
    __tablename__ = "auth_access_request_items"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("auth_access_requests.id", ondelete="CASCADE"),
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(32), index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    role_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    permission_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    effect: Mapped[str] = mapped_column(String(16), default="", index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_until: Mapped[str] = mapped_column(String(32), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), default="")


class AuthAuthorizationPreview(Base):
    __tablename__ = "auth_authorization_previews"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    base_revision: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
    consumed_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")


class AuthAuthorizationEvent(Base):
    __tablename__ = "auth_authorization_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    target_user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    target_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    permission_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    effect: Mapped[str] = mapped_column(String(16), default="", index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(128), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    access_request_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), default="", index=True)
