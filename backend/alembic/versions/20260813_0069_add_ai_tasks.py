"""add durable AI Task, Step, and Event state

Revision ID: 20260813_0069
Revises: 20260813_0068
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0069"
down_revision: str | Sequence[str] | None = "20260813_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("ai_conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("factory_scope", sa.String(64), nullable=False),
        sa.Column("task_type", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("maximum_risk", sa.String(32), nullable=False),
        sa.Column("primary_skill_id", sa.String(160), nullable=False),
        sa.Column("primary_skill_version", sa.String(32), nullable=False),
        sa.Column("primary_skill_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("runtime_plan_json", sa.Text(), nullable=False),
        sa.Column("runtime_plan_hash", sa.String(64), nullable=False),
        sa.Column(
            "server_page_context_json", sa.Text(), nullable=False, server_default="null"
        ),
        sa.Column("tool_versions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("required_access_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "next_event_sequence", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("terminal_at", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "retention_expires_at", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column("backup_delete_by", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "cancellation_requested_at", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "resume_requested_at", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column("failure_code", sa.String(96), nullable=False, server_default=""),
        sa.CheckConstraint(
            "task_type IN ('READ', 'COMPUTE', 'SIMULATE', 'PREVIEW')",
            name="ck_ai_task_type",
        ),
        sa.CheckConstraint(
            "state IN ('CREATED', 'UNDERSTOOD', 'PLANNED', 'RUNNING', "
            "'WAITING_INPUT', 'WAITING_APPROVAL', 'VERIFYING', 'COMPLETED', "
            "'CANCELLING', 'CANCELLED', 'FAILED', 'RETRY_PENDING')",
            name="ck_ai_task_state",
        ),
        sa.CheckConstraint(
            "maximum_risk IN ('READ_ONLY', 'PREVIEW_WITH_AUDIT')",
            name="ck_ai_task_maximum_risk",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_ai_task_revision"),
        sa.CheckConstraint(
            "next_event_sequence >= 1", name="ck_ai_task_next_event_sequence"
        ),
        sa.CheckConstraint(
            "step_count >= 1 AND step_count <= 6", name="ck_ai_task_steps"
        ),
    )
    for name, columns, unique in (
        ("ix_ai_tasks_owner_user_id", ["owner_user_id"], False),
        ("ix_ai_tasks_conversation_id", ["conversation_id"], False),
        ("ix_ai_tasks_factory_scope", ["factory_scope"], False),
        ("ix_ai_tasks_task_type", ["task_type"], False),
        ("ix_ai_tasks_state", ["state"], False),
        ("ix_ai_tasks_primary_skill_id", ["primary_skill_id"], False),
        ("ix_ai_tasks_runtime_plan_hash", ["runtime_plan_hash"], False),
        ("ix_ai_tasks_input_hash", ["input_hash"], False),
        ("ix_ai_tasks_created_at", ["created_at"], False),
        ("ix_ai_tasks_updated_at", ["updated_at"], False),
        ("ix_ai_tasks_terminal_at", ["terminal_at"], False),
        ("ix_ai_tasks_retention_expires_at", ["retention_expires_at"], False),
        (
            "uq_ai_task_owner_idempotency",
            ["owner_user_id", "idempotency_key"],
            True,
        ),
        ("ix_ai_task_owner_updated", ["owner_user_id", "updated_at", "id"], False),
        (
            "ix_ai_task_factory_state",
            ["factory_scope", "state", "updated_at"],
            False,
        ),
        ("ix_ai_task_retention", ["state", "retention_expires_at"], False),
    ):
        op.create_index(name, "ai_tasks", columns, unique=unique)

    op.create_table(
        "ai_task_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(64),
            sa.ForeignKey("ai_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("tool_version", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "side_effect_class", sa.String(32), nullable=False, server_default="NONE"
        ),
        sa.Column("idempotent", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("completed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("failure_code", sa.String(96), nullable=False, server_default=""),
        sa.CheckConstraint(
            "ordinal >= 1 AND ordinal <= 6", name="ck_ai_task_step_ordinal"
        ),
        sa.CheckConstraint(
            "kind IN ('READ', 'COMPUTE', 'SIMULATE', 'PREVIEW')",
            name="ck_ai_task_step_kind",
        ),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'WAITING_INPUT', 'VERIFYING', "
            "'COMPLETED', 'CANCELLED', 'FAILED', 'RETRY_PENDING')",
            name="ck_ai_task_step_state",
        ),
        sa.CheckConstraint(
            "side_effect_class IN ('NONE', 'PREVIEW_STATE')",
            name="ck_ai_task_step_side_effect",
        ),
        sa.CheckConstraint("idempotent IN (0, 1)", name="ck_ai_task_step_idempotent"),
        sa.CheckConstraint("revision >= 1", name="ck_ai_task_step_revision"),
    )
    for name, columns, unique in (
        ("ix_ai_task_steps_task_id", ["task_id"], False),
        ("ix_ai_task_steps_state", ["state"], False),
        ("uq_ai_task_step_ordinal", ["task_id", "ordinal"], True),
        ("uq_ai_task_step_key", ["task_id", "step_key"], True),
        ("ix_ai_task_step_task_state", ["task_id", "state", "ordinal"], False),
    ):
        op.create_index(name, "ai_task_steps", columns, unique=unique)

    op.create_table(
        "ai_task_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(64),
            sa.ForeignKey("ai_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.String(64),
            sa.ForeignKey("ai_task_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("transition_from", sa.String(32), nullable=False, server_default=""),
        sa.Column("transition_to", sa.String(32), nullable=False, server_default=""),
        sa.Column("reason_code", sa.String(96), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("artifact_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_ai_task_event_sequence"),
        sa.CheckConstraint(
            "event_type IN ('TASK_CREATED', 'STATE_TRANSITION', "
            "'STEP_STATE_TRANSITION', 'CANCEL_REQUESTED', 'RESUME_REQUESTED')",
            name="ck_ai_task_event_type",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SYSTEM')",
            name="ck_ai_task_event_actor_type",
        ),
    )
    for name, columns, unique in (
        ("ix_ai_task_events_task_id", ["task_id"], False),
        ("ix_ai_task_events_step_id", ["step_id"], False),
        ("ix_ai_task_events_event_type", ["event_type"], False),
        ("ix_ai_task_events_created_at", ["created_at"], False),
        ("uq_ai_task_event_sequence", ["task_id", "sequence"], True),
        ("ix_ai_task_event_task_created", ["task_id", "created_at", "id"], False),
    ):
        op.create_index(name, "ai_task_events", columns, unique=unique)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because AI Task data cannot be inspected."
        )
    connection = op.get_bind()
    protected = {
        table_name: int(
            connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        )
        for table_name in ("ai_tasks", "ai_task_steps", "ai_task_events")
    }
    if any(protected.values()):
        counts = ", ".join(f"{key}={value}" for key, value in protected.items())
        raise RuntimeError(
            "Refusing to downgrade 20260813_0069 while protected AI Task data "
            f"exists ({counts}). Disable new Task creation and complete retention review."
        )
    op.drop_table("ai_task_events")
    op.drop_table("ai_task_steps")
    op.drop_table("ai_tasks")
