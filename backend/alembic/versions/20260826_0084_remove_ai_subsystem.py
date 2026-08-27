"""remove the retired AI subsystem and its persisted data

Revision ID: 20260826_0084
Revises: 20260825_0083
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0084"
down_revision: str | Sequence[str] | None = "20260825_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AI_TABLES_CHILD_FIRST = (
    "ai_conversation_context_bindings",
    "ai_task_events",
    "ai_task_steps",
    "ai_tasks",
    "ai_messages",
    "ai_conversation_summaries",
    "ai_conversations",
    "ai_feedback",
    "ai_metric_events",
    "ai_eval_runs",
    "ai_guard_leases",
    "ai_guard_request_events",
    "ai_guard_daily_budgets",
    "ai_guard_disable_states",
    "ai_action_confirmations",
    "ai_artifacts",
)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names())

    if "system_notifications" in existing_tables:
        connection.execute(
            sa.text(
                "DELETE FROM system_notifications "
                "WHERE type = 'ai_operational_alert'"
            )
        )

    for table_name in AI_TABLES_CHILD_FIRST:
        if table_name in existing_tables:
            op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20260826_0084 is irreversible because it intentionally removes the "
        "retired AI subsystem and its persisted data. Restore a pre-removal "
        "database backup instead of downgrading this revision."
    )
