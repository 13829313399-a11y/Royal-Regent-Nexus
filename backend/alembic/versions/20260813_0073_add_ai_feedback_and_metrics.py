"""add AI feedback, eval run and metadata-only metrics

Revision ID: 20260813_0073
Revises: 20260813_0072
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0073"
down_revision: str | Sequence[str] | None = "20260813_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("rating", sa.String(24), nullable=False),
        sa.Column(
            "issue_category", sa.String(32), nullable=False, server_default="NONE"
        ),
        sa.Column("comment_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="SUBMITTED"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "reviewed_by",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("eval_suite_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("eval_case_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("reviewed_at", sa.String(40), nullable=False, server_default=""),
        sa.CheckConstraint(
            "target_type IN ('RESPONSE', 'MESSAGE', 'TASK', 'ACTION')",
            name="ck_ai_feedback_target_type",
        ),
        sa.CheckConstraint(
            "rating IN ('HELPFUL', 'NOT_HELPFUL')", name="ck_ai_feedback_rating"
        ),
        sa.CheckConstraint(
            "issue_category IN ('NONE', 'INCORRECT', 'MISSING_CONTEXT', 'WRONG_TOOL', 'WRONG_ARGUMENTS', 'UNSUPPORTED_CLAIM', 'PERMISSION', 'PREVIEW_MISLABEL', 'UNSAFE', 'OTHER')",
            name="ck_ai_feedback_issue_category",
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'TRIAGED', 'EVAL_CANDIDATE', 'DISMISSED')",
            name="ck_ai_feedback_status",
        ),
    )
    op.create_index("ix_ai_feedback_owner_user_id", "ai_feedback", ["owner_user_id"])
    op.create_index(
        "uq_ai_feedback_owner_target",
        "ai_feedback",
        ["owner_user_id", "target_type", "target_id"],
        unique=True,
    )
    op.create_index(
        "uq_ai_feedback_owner_request",
        "ai_feedback",
        ["owner_user_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_ai_feedback_status_created", "ai_feedback", ["status", "created_at", "id"]
    )
    op.create_index(
        "ix_ai_feedback_factory_created",
        "ai_feedback",
        ["factory_id", "created_at", "id"],
    )

    op.create_table(
        "ai_metric_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("factory_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("conversation_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("task_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("action_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("skill_id", sa.String(160), nullable=False, server_default=""),
        sa.Column("skill_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("skill_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("prompt_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        sa.Column("tool_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("tool_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_microusd", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cost_basis", sa.String(32), nullable=False, server_default="UNAVAILABLE"
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(96), nullable=False, server_default=""),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("truncated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "unauthorized_action", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cross_factory_leakage", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "preview_executed_mislabel",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('MODEL_RUN', 'TOOL_CALL')", name="ck_ai_metric_event_type"
        ),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE', 'DENIED', 'CANCELLED')",
            name="ck_ai_metric_status",
        ),
        sa.CheckConstraint(
            "cost_basis IN ('UNAVAILABLE', 'CONFIGURED_ESTIMATE', 'PROVIDER_REPORTED')",
            name="ck_ai_metric_cost_basis",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 AND estimated_cost_microusd >= 0 AND retry_count >= 0 AND evidence_count >= 0",
            name="ck_ai_metric_nonnegative",
        ),
        sa.CheckConstraint(
            "truncated IN (0, 1) AND unauthorized_action IN (0, 1) AND cross_factory_leakage IN (0, 1) AND preview_executed_mislabel IN (0, 1)",
            name="ck_ai_metric_booleans",
        ),
    )
    for name, columns, unique in (
        ("ix_ai_metric_request_id", ["request_id"], False),
        ("ix_ai_metric_owner_user_id", ["owner_user_id"], False),
        ("uq_ai_metric_event_key", ["request_id", "event_type", "event_key"], True),
        ("ix_ai_metric_created", ["created_at", "id"], False),
        ("ix_ai_metric_skill_created", ["skill_id", "created_at", "id"], False),
        ("ix_ai_metric_factory_created", ["factory_id", "created_at", "id"], False),
        ("ix_ai_metric_status_created", ["status", "created_at", "id"], False),
    ):
        op.create_index(name, "ai_metric_events", columns, unique=unique)

    op.create_table(
        "ai_eval_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("suite_id", sa.String(128), nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("dataset_hash", sa.String(64), nullable=False),
        sa.Column("runner_version", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("skill_id", sa.String(160), nullable=False),
        sa.Column("skill_version", sa.String(32), nullable=False),
        sa.Column("skill_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="fake"),
        sa.Column(
            "model", sa.String(128), nullable=False, server_default="offline-fixture"
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="ci"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40), nullable=False, server_default=""),
        sa.CheckConstraint(
            "mode IN ('OFFLINE_FAKE', 'LIVE_PROVIDER')", name="ck_ai_eval_run_mode"
        ),
        sa.CheckConstraint(
            "status IN ('PASSED', 'FAILED', 'ERROR')", name="ck_ai_eval_run_status"
        ),
        sa.CheckConstraint(
            "case_count >= 0 AND passed_count >= 0 AND failed_count >= 0",
            name="ck_ai_eval_run_counts",
        ),
    )
    op.create_index(
        "ix_ai_eval_suite_created", "ai_eval_runs", ["suite_id", "created_at", "id"]
    )
    op.create_index(
        "ix_ai_eval_skill_created", "ai_eval_runs", ["skill_id", "created_at", "id"]
    )


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because feedback and audit metadata cannot be inspected."
        )
    connection = op.get_bind()
    counts = {
        table: int(
            connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        )
        for table in ("ai_feedback", "ai_metric_events", "ai_eval_runs")
    }
    if any(counts.values()):
        raise RuntimeError(
            "Refusing to downgrade 20260813_0073 while AI evaluation evidence "
            f"exists: {counts}"
        )
    op.drop_table("ai_eval_runs")
    op.drop_table("ai_metric_events")
    op.drop_table("ai_feedback")
