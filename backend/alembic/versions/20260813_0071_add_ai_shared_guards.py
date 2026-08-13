"""add metadata-only shared AI Guard state

Revision ID: 20260813_0071
Revises: 20260813_0070
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0071"
down_revision: str | Sequence[str] | None = "20260813_0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_guard_leases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("lease_token", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("instance_id", sa.String(128), nullable=False),
        sa.Column("reservation_tokens", sa.BigInteger(), nullable=False),
        sa.Column("budget_day", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column(
            "provider_started", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reported_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "reservation_tokens >= 0", name="ck_ai_guard_lease_reservation"
        ),
        sa.CheckConstraint("reported_tokens >= 0", name="ck_ai_guard_lease_reported"),
    )
    op.create_index(
        "ix_ai_guard_leases_user_id", "ai_guard_leases", ["user_id"]
    )
    op.create_index(
        "ix_ai_guard_leases_factory_id", "ai_guard_leases", ["factory_id"]
    )
    op.create_index(
        "ix_ai_guard_leases_instance_id", "ai_guard_leases", ["instance_id"]
    )
    op.create_index(
        "ix_ai_guard_leases_budget_day", "ai_guard_leases", ["budget_day"]
    )
    op.create_index(
        "ix_ai_guard_leases_expires_at", "ai_guard_leases", ["expires_at"]
    )
    op.create_index(
        "ix_ai_guard_leases_created_at", "ai_guard_leases", ["created_at"]
    )
    op.create_index(
        "ix_ai_guard_leases_updated_at", "ai_guard_leases", ["updated_at"]
    )
    op.create_index(
        "ix_ai_guard_lease_user_expiry",
        "ai_guard_leases",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "ix_ai_guard_lease_instance_expiry",
        "ai_guard_leases",
        ["instance_id", "expires_at"],
    )

    op.create_table(
        "ai_guard_request_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("instance_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
    )
    for column_name in ("user_id", "factory_id", "instance_id"):
        op.create_index(
            f"ix_ai_guard_request_events_{column_name}",
            "ai_guard_request_events",
            [column_name],
        )
    op.create_index(
        "ix_ai_guard_request_user_created",
        "ai_guard_request_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_guard_request_expiry",
        "ai_guard_request_events",
        ["expires_at"],
    )

    op.create_table(
        "ai_guard_daily_budgets",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("budget_day", sa.String(10), primary_key=True),
        sa.Column("used_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "reserved_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("used_tokens >= 0", name="ck_ai_guard_budget_used"),
        sa.CheckConstraint(
            "reserved_tokens >= 0", name="ck_ai_guard_budget_reserved"
        ),
    )
    op.create_index(
        "ix_ai_guard_budget_day", "ai_guard_daily_budgets", ["budget_day"]
    )
    op.create_index(
        "ix_ai_guard_daily_budgets_updated_at",
        "ai_guard_daily_budgets",
        ["updated_at"],
    )

    op.create_table(
        "ai_guard_disable_states",
        sa.Column("scope_type", sa.String(16), primary_key=True),
        sa.Column("scope_id", sa.String(128), primary_key=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason_code", sa.String(96), nullable=False, server_default=""),
        sa.Column("expires_at", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "updated_by_instance", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('GLOBAL', 'FACTORY', 'USER')",
            name="ck_ai_guard_disable_scope",
        ),
    )
    op.create_index(
        "ix_ai_guard_disable_active",
        "ai_guard_disable_states",
        ["disabled", "expires_at"],
    )
    op.create_index(
        "ix_ai_guard_disable_states_updated_at",
        "ai_guard_disable_states",
        ["updated_at"],
    )


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because shared Guard state cannot be inspected."
        )
    connection = op.get_bind()
    populated = {
        table_name: int(
            connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        )
        for table_name in (
            "ai_guard_leases",
            "ai_guard_request_events",
            "ai_guard_daily_budgets",
            "ai_guard_disable_states",
        )
    }
    if any(populated.values()):
        raise RuntimeError(
            "Refusing to downgrade 20260813_0071 while protected shared Guard "
            "state exists. Stop all AI instances and complete the rollback review."
        )
    for table_name in (
        "ai_guard_disable_states",
        "ai_guard_daily_budgets",
        "ai_guard_request_events",
        "ai_guard_leases",
    ):
        op.drop_table(table_name)
