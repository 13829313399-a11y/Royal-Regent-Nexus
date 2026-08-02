"""create the password reset approval and forced-change workflow

Revision ID: 20260802_0046
Revises: 20260731_0045
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0046"
down_revision: str | Sequence[str] | None = "20260731_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_password_reset_requests",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("contact", sa.String(128), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("factory_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("department", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewer_user_id", sa.String(64), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("notification_id", sa.String(96), nullable=True),
        sa.Column("request_ip", sa.String(128), nullable=False, server_default=""),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("approved_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("last_issued_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("expires_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("completed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("rejected_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["system_notifications.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "notification_id", name="uq_auth_password_reset_request_notification"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'completed', 'expired')",
            name="ck_auth_password_reset_request_status",
        ),
        sa.CheckConstraint(
            "issue_count >= 0", name="ck_auth_password_reset_request_issue_count"
        ),
    )
    for column in (
        "user_id",
        "username",
        "status",
        "factory_id",
        "department",
        "reviewer_user_id",
        "request_ip",
        "submitted_at",
        "expires_at",
    ):
        op.create_index(
            f"ix_auth_password_reset_requests_{column}",
            "auth_password_reset_requests",
            [column],
        )
    op.create_index(
        "ix_auth_password_reset_requests_status_submitted",
        "auth_password_reset_requests",
        ["status", "submitted_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    request_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM auth_password_reset_requests")
    ).scalar_one()
    if request_count:
        raise RuntimeError(
            "20260802_0046 cannot be downgraded after password reset requests exist; "
            "back up the authentication data first"
        )
    op.drop_table("auth_password_reset_requests")
