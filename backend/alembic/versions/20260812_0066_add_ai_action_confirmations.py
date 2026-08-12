"""add AI action confirmations

Revision ID: 20260812_0066
Revises: 20260811_0065
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0066"
down_revision: str | Sequence[str] | None = "20260811_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_action_confirmations",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("entity_revision", sa.Integer(), nullable=False),
        sa.Column("args_hash", sa.String(64), nullable=False),
        sa.Column("normalized_action_json", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("confirmed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("executed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "execution_request_id", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "execution_result_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("failure_code", sa.String(96), nullable=False, server_default=""),
        sa.CheckConstraint(
            "risk_level IN ('CONSEQUENTIAL_WRITE', 'HIGH_RISK_WRITE')",
            name="ck_ai_action_confirmation_risk",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'EXECUTED', 'EXPIRED', "
            "'CANCELLED', 'STALE', 'FAILED')",
            name="ck_ai_action_confirmation_status",
        ),
    )
    op.create_index(
        "ix_ai_action_confirmations_user_id",
        "ai_action_confirmations",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_action_confirmations_tool_name",
        "ai_action_confirmations",
        ["tool_name"],
    )
    op.create_index(
        "ix_ai_action_confirmations_factory_id",
        "ai_action_confirmations",
        ["factory_id"],
    )
    op.create_index(
        "ix_ai_action_confirmations_entity_type",
        "ai_action_confirmations",
        ["entity_type"],
    )
    op.create_index(
        "ix_ai_action_confirmations_entity_id",
        "ai_action_confirmations",
        ["entity_id"],
    )
    op.create_index(
        "ix_ai_action_confirmations_args_hash",
        "ai_action_confirmations",
        ["args_hash"],
    )
    op.create_index(
        "ix_ai_action_confirmations_request_id",
        "ai_action_confirmations",
        ["request_id"],
    )
    op.create_index(
        "ix_ai_action_confirmations_expires_at",
        "ai_action_confirmations",
        ["expires_at"],
    )
    op.create_index(
        "ix_ai_action_confirmations_status",
        "ai_action_confirmations",
        ["status"],
    )
    op.create_index(
        "ix_ai_action_confirmations_created_at",
        "ai_action_confirmations",
        ["created_at"],
    )
    op.create_index(
        "uq_ai_action_confirmation_request",
        "ai_action_confirmations",
        ["user_id", "tool_name", "request_id"],
        unique=True,
    )
    op.create_index(
        "uq_ai_action_confirmation_execution_request",
        "ai_action_confirmations",
        ["execution_request_id"],
        unique=True,
        sqlite_where=sa.text("execution_request_id != ''"),
        postgresql_where=sa.text("execution_request_id != ''"),
    )
    op.create_index(
        "ix_ai_action_confirmation_user_status_expiry",
        "ai_action_confirmations",
        ["user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_ai_action_confirmation_entity",
        "ai_action_confirmations",
        ["factory_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_table("ai_action_confirmations")
