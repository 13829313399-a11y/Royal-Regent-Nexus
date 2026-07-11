"""create configurable IAM sidecar schema

Revision ID: 20260711_0010
Revises: 20260710_0009
Create Date: 2026-07-11 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260711_0010"
down_revision: Union[str, None] = "20260710_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("primary_factory_id", sa.String(length=64), nullable=False),
        sa.Column("primary_department", sa.String(length=64), nullable=False),
        sa.Column("position", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("source_registration_request_id", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_employee_profiles_confirmation_status", "employee_profiles", ["confirmation_status"])
    op.create_index("ix_employee_profiles_primary_department", "employee_profiles", ["primary_department"])
    op.create_index("ix_employee_profiles_primary_factory_id", "employee_profiles", ["primary_factory_id"])
    op.create_index(
        "ix_employee_profiles_source_registration_request_id",
        "employee_profiles",
        ["source_registration_request_id"],
    )

    op.create_table(
        "auth_permission_metadata",
        sa.Column("permission_id", sa.String(length=96), nullable=False),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["auth_permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("permission_id"),
    )
    op.create_index("ix_auth_permission_metadata_action", "auth_permission_metadata", ["action"])
    op.create_index("ix_auth_permission_metadata_module_code", "auth_permission_metadata", ["module_code"])
    op.create_index("ix_auth_permission_metadata_risk_level", "auth_permission_metadata", ["risk_level"])
    op.create_index("ix_auth_permission_metadata_scope_type", "auth_permission_metadata", ["scope_type"])
    op.create_index("ix_auth_permission_metadata_status", "auth_permission_metadata", ["status"])

    op.create_table(
        "auth_role_metadata",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("protected", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["auth_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id"),
    )
    op.create_index("ix_auth_role_metadata_protected", "auth_role_metadata", ["protected"])
    op.create_index("ix_auth_role_metadata_updated_by_user_id", "auth_role_metadata", ["updated_by_user_id"])

    op.create_table(
        "auth_role_binding_metadata",
        sa.Column("user_role_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_until", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("approved_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.String(length=32), nullable=False),
        sa.Column("revoke_reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_role_id"], ["auth_user_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_role_id"),
    )
    for column in (
        "approved_by_user_id",
        "created_by_user_id",
        "revoked_by_user_id",
        "source_id",
        "source_type",
        "state",
        "valid_until",
    ):
        op.create_index(f"ix_auth_role_binding_metadata_{column}", "auth_role_binding_metadata", [column])

    op.create_table(
        "auth_user_permission_overrides",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=96), nullable=False),
        sa.Column("effect", sa.String(length=16), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_until", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("approved_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.String(length=32), nullable=False),
        sa.Column("revoke_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["auth_permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "approved_by_user_id",
        "created_by_user_id",
        "department",
        "effect",
        "factory_id",
        "permission_id",
        "revoked_by_user_id",
        "source_id",
        "source_type",
        "status",
        "user_id",
        "valid_until",
    ):
        op.create_index(
            f"ix_auth_user_permission_overrides_{column}",
            "auth_user_permission_overrides",
            [column],
        )

    op.create_table(
        "auth_user_authorization_revisions",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "auth_iam_state",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "auth_access_requests",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("requester_user_id", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("decision_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("decision_comment", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.String(length=32), nullable=False),
        sa.Column("decided_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["target_user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("decision_by_user_id", "requester_user_id", "status", "target_user_id"):
        op.create_index(f"ix_auth_access_requests_{column}", "auth_access_requests", [column])

    op.create_table(
        "auth_access_request_items",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission_id", sa.String(length=96), nullable=False),
        sa.Column("effect", sa.String(length=16), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.String(length=32), nullable=False),
        sa.Column("valid_until", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["auth_access_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "department",
        "effect",
        "factory_id",
        "operation",
        "permission_id",
        "request_id",
        "role_id",
        "target_id",
        "target_type",
    ):
        op.create_index(f"ix_auth_access_request_items_{column}", "auth_access_request_items", [column])

    op.create_table(
        "auth_authorization_previews",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.String(length=32), nullable=False),
        sa.Column("consumed_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_authorization_previews_actor_user_id", "auth_authorization_previews", ["actor_user_id"])
    op.create_index("ix_auth_authorization_previews_expires_at", "auth_authorization_previews", ["expires_at"])
    op.create_index("ix_auth_authorization_previews_target_id", "auth_authorization_previews", ["target_id"])
    op.create_index("ix_auth_authorization_previews_target_type", "auth_authorization_previews", ["target_type"])
    op.create_index(
        "ix_auth_authorization_previews_token_hash",
        "auth_authorization_previews",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "auth_authorization_events",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("permission_id", sa.String(length=96), nullable=False),
        sa.Column("effect", sa.String(length=16), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("access_request_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "access_request_id",
        "actor_user_id",
        "created_at",
        "department",
        "effect",
        "event_type",
        "factory_id",
        "permission_id",
        "target_id",
        "target_type",
        "target_user_id",
    ):
        op.create_index(f"ix_auth_authorization_events_{column}", "auth_authorization_events", [column])


def downgrade() -> None:
    op.drop_table("auth_authorization_events")
    op.drop_table("auth_authorization_previews")
    op.drop_table("auth_access_request_items")
    op.drop_table("auth_access_requests")
    op.drop_table("auth_iam_state")
    op.drop_table("auth_user_authorization_revisions")
    op.drop_table("auth_user_permission_overrides")
    op.drop_table("auth_role_binding_metadata")
    op.drop_table("auth_role_metadata")
    op.drop_table("auth_permission_metadata")
    op.drop_table("employee_profiles")
