"""create auth registration and system notifications

Revision ID: 20260708_0007
Revises: 20260708_0006
Create Date: 2026-07-08 19:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260708_0007"
down_revision: Union[str, None] = "20260708_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_registration_requests",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("position", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=64), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.String(length=32), nullable=False),
        sa.Column("reviewed_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_registration_requests_department", "auth_registration_requests", ["department"])
    op.create_index("ix_auth_registration_requests_factory_id", "auth_registration_requests", ["factory_id"])
    op.create_index("ix_auth_registration_requests_reviewer_user_id", "auth_registration_requests", ["reviewer_user_id"])
    op.create_index("ix_auth_registration_requests_status", "auth_registration_requests", ["status"])
    op.create_index("ix_auth_registration_requests_user_id", "auth_registration_requests", ["user_id"])
    op.create_index("ix_auth_registration_requests_username", "auth_registration_requests", ["username"])

    op.create_table(
        "system_notifications",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("target_user_id", sa.String(length=64), nullable=False),
        sa.Column("target_permission", sa.String(length=128), nullable=False),
        sa.Column("target_factory_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("read_at", sa.String(length=32), nullable=False),
        sa.Column("handled_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_notifications_status", "system_notifications", ["status"])
    op.create_index("ix_system_notifications_target_factory_id", "system_notifications", ["target_factory_id"])
    op.create_index("ix_system_notifications_target_permission", "system_notifications", ["target_permission"])
    op.create_index("ix_system_notifications_target_user_id", "system_notifications", ["target_user_id"])
    op.create_index("ix_system_notifications_type", "system_notifications", ["type"])


def downgrade() -> None:
    op.drop_index("ix_system_notifications_type", table_name="system_notifications")
    op.drop_index("ix_system_notifications_target_user_id", table_name="system_notifications")
    op.drop_index("ix_system_notifications_target_permission", table_name="system_notifications")
    op.drop_index("ix_system_notifications_target_factory_id", table_name="system_notifications")
    op.drop_index("ix_system_notifications_status", table_name="system_notifications")
    op.drop_table("system_notifications")

    op.drop_index("ix_auth_registration_requests_username", table_name="auth_registration_requests")
    op.drop_index("ix_auth_registration_requests_user_id", table_name="auth_registration_requests")
    op.drop_index("ix_auth_registration_requests_status", table_name="auth_registration_requests")
    op.drop_index("ix_auth_registration_requests_reviewer_user_id", table_name="auth_registration_requests")
    op.drop_index("ix_auth_registration_requests_factory_id", table_name="auth_registration_requests")
    op.drop_index("ix_auth_registration_requests_department", table_name="auth_registration_requests")
    op.drop_table("auth_registration_requests")
