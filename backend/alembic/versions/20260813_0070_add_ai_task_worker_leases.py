"""add AI Task Worker leases and recovery metadata

Revision ID: 20260813_0070
Revises: 20260813_0069
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0070"
down_revision: str | Sequence[str] | None = "20260813_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_TYPES = (
    "event_type IN ('TASK_CREATED', 'STATE_TRANSITION', "
    "'STEP_STATE_TRANSITION', 'CANCEL_REQUESTED', 'RESUME_REQUESTED', "
    "'LEASE_CLAIMED', 'LEASE_RELEASED', 'RETRY_SCHEDULED')"
)
_OLD_EVENT_TYPES = (
    "event_type IN ('TASK_CREATED', 'STATE_TRANSITION', "
    "'STEP_STATE_TRANSITION', 'CANCEL_REQUESTED', 'RESUME_REQUESTED')"
)


def upgrade() -> None:
    with op.batch_alter_table("ai_tasks") as batch:
        batch.add_column(sa.Column("input_message_id", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "lease_owner_instance",
                sa.String(128),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column("lease_token", sa.String(64), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "lease_expires_at", sa.String(32), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "last_heartbeat_at", sa.String(32), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "next_attempt_at", sa.String(32), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_foreign_key(
            "fk_ai_task_input_message",
            "ai_messages",
            ["input_message_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint("ck_ai_task_claim_count", "claim_count >= 0")
    op.create_index(
        "ix_ai_tasks_input_message_id",
        "ai_tasks",
        ["input_message_id"],
    )
    op.create_index(
        "ix_ai_tasks_lease_expires_at",
        "ai_tasks",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_ai_tasks_next_attempt_at",
        "ai_tasks",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_ai_task_worker_claim",
        "ai_tasks",
        ["state", "next_attempt_at", "lease_expires_at", "updated_at", "id"],
    )

    with op.batch_alter_table("ai_task_steps") as batch:
        batch.add_column(
            sa.Column("arguments_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column(
                "arguments_hash", sa.String(64), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
        )
        batch.add_column(
            sa.Column(
                "last_attempt_id", sa.String(64), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "last_attempt_started_at",
                sa.String(32),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "last_attempt_finished_at",
                sa.String(32),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column("result_hash", sa.String(71), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "result_metadata_json", sa.Text(), nullable=False, server_default="{}"
            )
        )
        batch.create_check_constraint(
            "ck_ai_task_step_attempt_count",
            "attempt_count >= 0",
        )
        batch.create_check_constraint(
            "ck_ai_task_step_max_attempts",
            "max_attempts >= 1 AND max_attempts <= 3",
        )

    with op.batch_alter_table("ai_task_events") as batch:
        batch.drop_constraint("ck_ai_task_event_type", type_="check")
        batch.create_check_constraint("ck_ai_task_event_type", _EVENT_TYPES)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because AI Worker recovery data cannot be inspected."
        )
    connection = op.get_bind()
    protected_task_count = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM ai_tasks WHERE input_message_id IS NOT NULL "
                "OR lease_owner_instance != '' OR lease_token != '' "
                "OR lease_expires_at != '' OR last_heartbeat_at != '' "
                "OR next_attempt_at != '' OR claim_count > 0"
            )
        ).scalar_one()
    )
    protected_step_count = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM ai_task_steps WHERE arguments_json != '{}' "
                "OR arguments_hash != '' OR attempt_count > 0 OR last_attempt_id != '' "
                "OR last_attempt_started_at != '' OR last_attempt_finished_at != '' "
                "OR result_hash != '' OR result_metadata_json != '{}'"
            )
        ).scalar_one()
    )
    protected_event_count = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM ai_task_events WHERE event_type IN "
                "('LEASE_CLAIMED', 'LEASE_RELEASED', 'RETRY_SCHEDULED')"
            )
        ).scalar_one()
    )
    if protected_task_count or protected_step_count or protected_event_count:
        raise RuntimeError(
            "Refusing to downgrade 20260813_0070 while protected AI Worker data "
            "exists. Stop the Worker and complete recovery/retention review."
        )

    with op.batch_alter_table("ai_task_events") as batch:
        batch.drop_constraint("ck_ai_task_event_type", type_="check")
        batch.create_check_constraint("ck_ai_task_event_type", _OLD_EVENT_TYPES)

    with op.batch_alter_table("ai_task_steps") as batch:
        batch.drop_constraint("ck_ai_task_step_max_attempts", type_="check")
        batch.drop_constraint("ck_ai_task_step_attempt_count", type_="check")
        for column_name in (
            "result_metadata_json",
            "result_hash",
            "last_attempt_finished_at",
            "last_attempt_started_at",
            "last_attempt_id",
            "max_attempts",
            "attempt_count",
            "arguments_hash",
            "arguments_json",
        ):
            batch.drop_column(column_name)

    op.drop_index("ix_ai_task_worker_claim", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_next_attempt_at", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_lease_expires_at", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_input_message_id", table_name="ai_tasks")
    with op.batch_alter_table("ai_tasks") as batch:
        batch.drop_constraint("ck_ai_task_claim_count", type_="check")
        batch.drop_constraint("fk_ai_task_input_message", type_="foreignkey")
        for column_name in (
            "claim_count",
            "next_attempt_at",
            "last_heartbeat_at",
            "lease_expires_at",
            "lease_token",
            "lease_owner_instance",
            "input_message_id",
        ):
            batch.drop_column(column_name)
