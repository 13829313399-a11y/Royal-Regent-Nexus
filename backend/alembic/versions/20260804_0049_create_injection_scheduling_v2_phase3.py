"""create injection scheduling V2 phase 3 heuristic scheduler

Revision ID: 20260804_0049
Revises: 20260804_0048
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0049"
down_revision: str | Sequence[str] | None = "20260804_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "injection_scheduling_runs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("expected_plan_revision", sa.Integer(), nullable=False),
        sa.Column("rule_set_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("rule_revision", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="PREVIEW"),
        sa.Column(
            "solver_type", sa.String(32), nullable=False, server_default="HEURISTIC"
        ),
        sa.Column(
            "solver_version", sa.String(32), nullable=False, server_default="phase3-v1"
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("horizon_start", sa.String(32), nullable=False),
        sa.Column("horizon_end", sa.String(32), nullable=False),
        sa.Column(
            "input_snapshot_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "objective_config_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("finished_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("applied_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("applied_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("applied_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_run_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id", "request_id", name="uq_injection_scheduling_run_request"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_run_plan_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'VALIDATING', 'GENERATING_CANDIDATES', 'SOLVING', "
            "'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'APPLIED')",
            name="ck_injection_scheduling_run_status",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_injection_scheduling_run_revision"
        ),
    )
    op.create_index(
        "ix_injection_scheduling_run_factory_created",
        "injection_scheduling_runs",
        ["factory_id", "created_at"],
    )
    op.create_index(
        "ix_injection_scheduling_run_plan_status",
        "injection_scheduling_runs",
        ["plan_id", "status"],
    )
    op.create_index(
        "ix_injection_scheduling_runs_request_id",
        "injection_scheduling_runs",
        ["request_id"],
    )
    op.create_index(
        "ix_injection_scheduling_runs_payload_hash",
        "injection_scheduling_runs",
        ["payload_hash"],
    )
    for column in (
        "factory_id",
        "plan_id",
        "status",
        "created_by",
        "applied_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_runs_{column}",
            "injection_scheduling_runs",
            [column],
        )

    op.create_table(
        "injection_scheduling_run_assignments",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("existing_task_id", sa.String(96), nullable=True),
        sa.Column("mold_id", sa.String(96), nullable=True),
        sa.Column("mold_copy_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("machine_id", sa.String(96), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=True),
        sa.Column("planned_start", sa.String(32), nullable=False, server_default=""),
        sa.Column("planned_finish", sa.String(32), nullable=False, server_default=""),
        sa.Column("setup_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "production_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "planned_downtime_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("changeover_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("score", sa.Numeric(14, 3), nullable=True),
        sa.Column("explanation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "unassigned_reason_code", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "run_id", "order_id", name="uq_injection_scheduling_run_assignment_order"
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["injection_scheduling_runs.id", "injection_scheduling_runs.factory_id"],
            name="fk_injection_scheduling_assignment_run_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "decision IN ('PASS', 'REVIEW_REQUIRED', 'UNASSIGNED')",
            name="ck_injection_scheduling_assignment_decision",
        ),
    )
    op.create_index(
        "ix_injection_scheduling_assignment_run_machine_sequence",
        "injection_scheduling_run_assignments",
        ["run_id", "machine_id", "sequence_no"],
    )
    for column in (
        "factory_id",
        "run_id",
        "order_id",
        "existing_task_id",
        "mold_id",
        "machine_id",
        "decision",
        "unassigned_reason_code",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_run_assignments_{column}",
            "injection_scheduling_run_assignments",
            [column],
        )

    op.create_table(
        "injection_scheduling_transition_rules",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column(
            "from_material_group", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("from_color_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "from_setup_family", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "to_material_group", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("to_color_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("to_setup_family", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "mold_change_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "color_change_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "material_change_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "fixture_change_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "from_material_group",
            "from_color_rank",
            "from_setup_family",
            "to_material_group",
            "to_color_rank",
            "to_setup_family",
            "revision",
            name="uq_injection_scheduling_transition_rule_key_revision",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_injection_scheduling_transition_revision"
        ),
    )
    op.create_index(
        "ix_injection_scheduling_transition_factory_active",
        "injection_scheduling_transition_rules",
        ["factory_id", "active", "revision"],
    )
    op.create_index(
        "ix_injection_scheduling_transition_rules_factory_id",
        "injection_scheduling_transition_rules",
        ["factory_id"],
    )
    op.create_index(
        "ix_injection_scheduling_transition_rules_created_at",
        "injection_scheduling_transition_rules",
        ["created_at"],
    )

    op.create_table(
        "injection_scheduling_machine_calendars",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("calendar_type", sa.String(32), nullable=False),
        sa.Column("window_start", sa.String(32), nullable=False),
        sa.Column("window_end", sa.String(32), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "machine_id",
            "window_start",
            "window_end",
            "calendar_type",
            name="uq_injection_scheduling_machine_calendar_window",
        ),
        sa.CheckConstraint(
            "calendar_type IN ('SHIFT', 'BREAK', 'MAINTENANCE', 'DOWNTIME', 'UNAVAILABLE')",
            name="ck_injection_scheduling_machine_calendar_type",
        ),
    )
    op.create_index(
        "ix_injection_scheduling_calendar_machine_window",
        "injection_scheduling_machine_calendars",
        ["factory_id", "machine_id", "window_start", "window_end"],
    )
    for column in (
        "factory_id",
        "machine_id",
        "calendar_type",
        "window_start",
        "window_end",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_machine_calendars_{column}",
            "injection_scheduling_machine_calendars",
            [column],
        )

    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("setup_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column(
            "production_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column(
            "planned_downtime_minutes", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("changeover_type", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("auto_schedule_run_id", sa.String(96), nullable=True),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column("auto_score", sa.Numeric(14, 3), nullable=True),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column(
            "auto_explanation_json", sa.Text(), nullable=False, server_default="{}"
        ),
    )
    op.add_column(
        "injection_scheduling_tasks",
        sa.Column(
            "manual_adjusted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(
        "ix_injection_scheduling_tasks_auto_schedule_run_id",
        "injection_scheduling_tasks",
        ["auto_schedule_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_injection_scheduling_tasks_auto_schedule_run_id",
        table_name="injection_scheduling_tasks",
    )
    for column in (
        "manual_adjusted",
        "auto_explanation_json",
        "auto_score",
        "auto_schedule_run_id",
        "changeover_type",
        "planned_downtime_minutes",
        "production_minutes",
        "setup_minutes",
    ):
        op.drop_column("injection_scheduling_tasks", column)
    op.drop_table("injection_scheduling_machine_calendars")
    op.drop_table("injection_scheduling_transition_rules")
    op.drop_table("injection_scheduling_run_assignments")
    op.drop_table("injection_scheduling_runs")
