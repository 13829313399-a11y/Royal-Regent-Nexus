"""auth rbac and remove molding sample pin

Revision ID: 20260703_0003
Revises: 20260703_0002
Create Date: 2026-07-03 22:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260703_0003"
down_revision: Union[str, None] = "20260703_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("password_salt", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("force_password_change", sa.Integer(), nullable=False),
        sa.Column("last_login_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_users_status", "auth_users", ["status"])
    op.create_index("ix_auth_users_username", "auth_users", ["username"], unique=True)

    op.create_table(
        "auth_roles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_roles_code", "auth_roles", ["code"], unique=True)

    op.create_table(
        "auth_permissions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_permissions_code", "auth_permissions", ["code"], unique=True)

    op.create_table(
        "auth_role_permissions",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=96), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["auth_permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_role_permissions_permission_id", "auth_role_permissions", ["permission_id"])
    op.create_index("ix_auth_role_permissions_role_id", "auth_role_permissions", ["role_id"])

    op.create_table(
        "auth_user_roles",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_user_roles_department", "auth_user_roles", ["department"])
    op.create_index("ix_auth_user_roles_factory_id", "auth_user_roles", ["factory_id"])
    op.create_index("ix_auth_user_roles_role_id", "auth_user_roles", ["role_id"])
    op.create_index("ix_auth_user_roles_user_id", "auth_user_roles", ["user_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ip_address", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("revoked_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_index("ix_auth_sessions_status", "auth_sessions", ["status"])
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_audit_logs_action", "auth_audit_logs", ["action"])
    op.create_index("ix_auth_audit_logs_user_id", "auth_audit_logs", ["user_id"])
    op.create_index("ix_auth_audit_logs_username", "auth_audit_logs", ["username"])

    op.add_column(
        "molding_sample_audit_logs",
        sa.Column("actor_user_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_audit_logs",
        sa.Column("actor_roles", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_audit_logs",
        sa.Column("factory_scope", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_sensitive_audit_logs",
        sa.Column("actor_user_id", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_sensitive_audit_logs",
        sa.Column("actor_roles", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "molding_sample_sensitive_audit_logs",
        sa.Column("factory_scope", sa.String(length=255), nullable=False, server_default=""),
    )

    op.drop_index("ix_molding_sample_pin_attempts_role", table_name="molding_sample_pin_attempts")
    op.drop_index("ix_molding_sample_pin_attempts_name", table_name="molding_sample_pin_attempts")
    op.drop_table("molding_sample_pin_attempts")
    op.drop_index("ix_molding_sample_auth_pins_role", table_name="molding_sample_auth_pins")
    op.drop_index("ix_molding_sample_auth_pins_name", table_name="molding_sample_auth_pins")
    op.drop_table("molding_sample_auth_pins")


def downgrade() -> None:
    op.create_table(
        "molding_sample_auth_pins",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("pin_salt", sa.String(length=64), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=False),
        sa.Column("must_change", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_auth_pins_name", "molding_sample_auth_pins", ["name"])
    op.create_index("ix_molding_sample_auth_pins_role", "molding_sample_auth_pins", ["role"])

    op.create_table(
        "molding_sample_pin_attempts",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_pin_attempts_name", "molding_sample_pin_attempts", ["name"])
    op.create_index("ix_molding_sample_pin_attempts_role", "molding_sample_pin_attempts", ["role"])

    op.drop_column("molding_sample_sensitive_audit_logs", "factory_scope")
    op.drop_column("molding_sample_sensitive_audit_logs", "actor_roles")
    op.drop_column("molding_sample_sensitive_audit_logs", "actor_user_id")
    op.drop_column("molding_sample_audit_logs", "factory_scope")
    op.drop_column("molding_sample_audit_logs", "actor_roles")
    op.drop_column("molding_sample_audit_logs", "actor_user_id")

    op.drop_index("ix_auth_audit_logs_username", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_user_id", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_action", table_name="auth_audit_logs")
    op.drop_table("auth_audit_logs")

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_status", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_auth_user_roles_user_id", table_name="auth_user_roles")
    op.drop_index("ix_auth_user_roles_role_id", table_name="auth_user_roles")
    op.drop_index("ix_auth_user_roles_factory_id", table_name="auth_user_roles")
    op.drop_index("ix_auth_user_roles_department", table_name="auth_user_roles")
    op.drop_table("auth_user_roles")

    op.drop_index("ix_auth_role_permissions_role_id", table_name="auth_role_permissions")
    op.drop_index("ix_auth_role_permissions_permission_id", table_name="auth_role_permissions")
    op.drop_table("auth_role_permissions")

    op.drop_index("ix_auth_permissions_code", table_name="auth_permissions")
    op.drop_table("auth_permissions")

    op.drop_index("ix_auth_roles_code", table_name="auth_roles")
    op.drop_table("auth_roles")

    op.drop_index("ix_auth_users_username", table_name="auth_users")
    op.drop_index("ix_auth_users_status", table_name="auth_users")
    op.drop_table("auth_users")
