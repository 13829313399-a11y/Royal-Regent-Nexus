"""add injection schedule phase4 execution and actual ledger

Revision ID: 20260725_0035
Revises: 20260723_0034
Create Date: 2026-07-25 09:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260725_0035"
down_revision: str | Sequence[str] | None = "20260723_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "injection_order_masters",
        sa.Column(
            "priority_code",
            sa.String(2),
            nullable=False,
            server_default="P3",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE injection_order_masters "
            "SET priority_code = CASE "
            "WHEN upper(trim(priority_flag)) IN ('P0', 'P1', 'P2', 'P3') "
            "THEN upper(trim(priority_flag)) "
            "WHEN upper(trim(priority_flag)) IN "
            "('特急', 'URGENT', 'RUSH', '急单') "
            "OR upper(trim(priority_flag)) LIKE '%特急%' "
            "OR upper(trim(priority_flag)) LIKE '%URGENT%' "
            "OR upper(trim(priority_flag)) LIKE '%RUSH%' "
            "OR upper(trim(priority_flag)) LIKE '%急单%' THEN 'P0' "
            "WHEN trim(priority_flag) = '急' "
            "OR trim(priority_flag) LIKE '%▲%' THEN 'P1' "
            "ELSE 'P3' END"
        )
    )
    with op.batch_alter_table(
        "injection_order_masters",
        recreate="auto",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_injection_order_priority_code",
            "priority_code IN ('P0', 'P1', 'P2', 'P3')",
        )
    op.create_index(
        "ix_injection_order_masters_priority_code",
        "injection_order_masters",
        ["priority_code"],
    )

    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "execution_status",
            sa.String(32),
            nullable=False,
            server_default="planned",
        ),
    )
    op.add_column(
        "injection_schedule_tasks",
        sa.Column(
            "protected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    with op.batch_alter_table(
        "injection_schedule_tasks",
        recreate="auto",
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_injection_schedule_task_source",
            "source IN ('import', 'manual', 'recommendation', 'auto', 'legacy')",
        )
        batch_op.create_check_constraint(
            "ck_injection_schedule_task_execution_status",
            "execution_status IN ('planned', 'running', 'completed', 'cancelled')",
        )
        batch_op.create_unique_constraint(
            "uq_injection_schedule_task_id_version_factory",
            ["id", "version_id", "factory_id"],
        )
    op.create_index(
        "ix_injection_schedule_tasks_execution_status",
        "injection_schedule_tasks",
        ["execution_status"],
    )
    op.create_index(
        "ix_injection_schedule_tasks_protected",
        "injection_schedule_tasks",
        ["protected"],
    )

    op.create_table(
        "injection_schedule_replan_runs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_version_id", sa.String(96), nullable=False),
        sa.Column("result_version_id", sa.String(96), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "affected_machine_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "affected_order_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "affected_task_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "impact_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_replan_run_id_factory",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_replan_run_factory_request",
        ),
        sa.ForeignKeyConstraint(
            ("source_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_replan_run_source_version_factory",
        ),
        sa.ForeignKeyConstraint(
            ("result_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_replan_run_result_version_factory",
        ),
        sa.CheckConstraint(
            "trigger_type IN "
            "('auto_draft', 'urgent_order', 'machine_downtime', 'shift_actual')",
            name="ck_injection_replan_run_trigger_type",
        ),
        sa.CheckConstraint(
            "status IN ('previewed', 'applied')",
            name="ck_injection_replan_run_status",
        ),
        sa.CheckConstraint(
            "source_revision >= 1",
            name="ck_injection_replan_run_source_revision",
        ),
        sa.CheckConstraint(
            "result_revision >= 1",
            name="ck_injection_replan_run_result_revision",
        ),
        sa.CheckConstraint(
            "source_version_id <> result_version_id",
            name="ck_injection_replan_run_distinct_versions",
        ),
        sa.CheckConstraint(
            "length(context_hash) = 64",
            name="ck_injection_replan_run_context_hash",
        ),
        sa.CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_replan_run_request_id",
        ),
    )
    for column_name in (
        "factory_id",
        "source_version_id",
        "result_version_id",
        "trigger_type",
        "status",
        "context_hash",
        "request_id",
        "created_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_schedule_replan_runs_{column_name}",
            "injection_schedule_replan_runs",
            [column_name],
        )

    op.create_table(
        "injection_schedule_shift_actuals",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(96), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("source_version_id", sa.String(96), nullable=False),
        sa.Column("source_task_id", sa.String(96), nullable=False),
        sa.Column("lineage_sequence", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("shift_date", sa.String(20), nullable=False),
        sa.Column("shift", sa.String(16), nullable=False),
        sa.Column(
            "legacy_shift_code",
            sa.String(8),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "source",
            sa.String(16),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("target_qty", sa.Float(), nullable=True),
        sa.Column("actual_qty", sa.Float(), nullable=False),
        sa.Column("variance_qty", sa.Float(), nullable=True),
        sa.Column(
            "variance_reason",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column("produced_baseline_qty", sa.Float(), nullable=False),
        sa.Column("outstanding_qty_before", sa.Float(), nullable=False),
        sa.Column("outstanding_qty_after", sa.Float(), nullable=False),
        sa.Column("shortage_qty", sa.Float(), nullable=False),
        sa.Column("task_planned_qty_before", sa.Float(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "projection_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "correction_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column(
            "corrected_by",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "corrected_by_name",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "corrected_at",
            sa.String(32),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "last_correction_request_id",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "last_correction_payload_hash",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_shift_actual_id_factory",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_shift_actual_factory_request",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "source_task_id",
            "shift_date",
            "shift",
            name="uq_injection_shift_actual_source_task_shift",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "source_task_id",
            "lineage_sequence",
            name="uq_injection_shift_actual_source_task_sequence",
        ),
        sa.ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_shift_actual_version_factory",
        ),
        sa.ForeignKeyConstraint(
            ("task_id", "version_id", "factory_id"),
            (
                "injection_schedule_tasks.id",
                "injection_schedule_tasks.version_id",
                "injection_schedule_tasks.factory_id",
            ),
            name="fk_injection_shift_actual_task_version_factory",
        ),
        sa.ForeignKeyConstraint(
            ("source_task_id", "source_version_id", "factory_id"),
            (
                "injection_schedule_tasks.id",
                "injection_schedule_tasks.version_id",
                "injection_schedule_tasks.factory_id",
            ),
            name="fk_injection_shift_actual_source_task_version_factory",
        ),
        sa.ForeignKeyConstraint(
            ("order_id", "factory_id"),
            (
                "injection_order_masters.id",
                "injection_order_masters.factory_id",
            ),
            name="fk_injection_shift_actual_order_factory",
        ),
        sa.ForeignKeyConstraint(
            ("machine_id", "factory_id"),
            (
                "injection_machine_masters.id",
                "injection_machine_masters.factory_id",
            ),
            name="fk_injection_shift_actual_machine_factory",
        ),
        sa.CheckConstraint(
            "shift IN ('day', 'night')",
            name="ck_injection_shift_actual_shift",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'workbook')",
            name="ck_injection_shift_actual_source",
        ),
        sa.CheckConstraint(
            "actual_qty >= 0",
            name="ck_injection_shift_actual_qty",
        ),
        sa.CheckConstraint(
            "produced_baseline_qty >= 0",
            name="ck_injection_shift_actual_baseline",
        ),
        sa.CheckConstraint(
            "outstanding_qty_before >= 0 AND outstanding_qty_after >= 0",
            name="ck_injection_shift_actual_outstanding",
        ),
        sa.CheckConstraint(
            "shortage_qty >= 0",
            name="ck_injection_shift_actual_shortage",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND correction_count >= 0",
            name="ck_injection_shift_actual_revision",
        ),
        sa.CheckConstraint(
            "lineage_sequence >= 1",
            name="ck_injection_shift_actual_lineage_sequence",
        ),
        sa.CheckConstraint(
            "outstanding_qty_after <= outstanding_qty_before",
            name="ck_injection_shift_actual_outstanding_direction",
        ),
        sa.CheckConstraint(
            "abs((outstanding_qty_before - actual_qty) - "
            "outstanding_qty_after) <= 0.000001",
            name="ck_injection_shift_actual_authoritative_balance",
        ),
        sa.CheckConstraint(
            "shortage_qty <= task_planned_qty_before",
            name="ck_injection_shift_actual_task_balance",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_injection_shift_actual_payload_hash",
        ),
        sa.CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_shift_actual_request_id",
        ),
        sa.CheckConstraint(
            "(correction_count = 0 "
            "AND last_correction_request_id = '' "
            "AND last_correction_payload_hash = '') "
            "OR (correction_count > 0 "
            "AND length(trim(last_correction_request_id)) > 0 "
            "AND length(last_correction_payload_hash) = 64)",
            name="ck_injection_shift_actual_correction_trace",
        ),
    )
    for column_name in (
        "factory_id",
        "version_id",
        "task_id",
        "source_version_id",
        "source_task_id",
        "lineage_sequence",
        "order_id",
        "machine_id",
        "shift_date",
        "shift",
        "source",
        "request_id",
        "created_by",
        "created_at",
        "corrected_by",
        "last_correction_request_id",
    ):
        op.create_index(
            f"ix_injection_schedule_shift_actuals_{column_name}",
            "injection_schedule_shift_actuals",
            [column_name],
        )

    op.create_table(
        "injection_schedule_actual_corrections",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("actual_id", sa.String(96), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("previous_actual_qty", sa.Float(), nullable=False),
        sa.Column("corrected_actual_qty", sa.Float(), nullable=False),
        sa.Column("previous_actual_revision", sa.Integer(), nullable=False),
        sa.Column("result_actual_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "response_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_actual_correction_id_factory",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_actual_correction_factory_request",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "actual_id",
            "result_actual_revision",
            name="uq_injection_actual_correction_actual_revision",
        ),
        sa.ForeignKeyConstraint(
            ("actual_id", "factory_id"),
            (
                "injection_schedule_shift_actuals.id",
                "injection_schedule_shift_actuals.factory_id",
            ),
            name="fk_injection_actual_correction_actual_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "previous_actual_qty >= 0 AND corrected_actual_qty >= 0",
            name="ck_injection_actual_correction_qty",
        ),
        sa.CheckConstraint(
            "previous_actual_revision >= 1 "
            "AND result_actual_revision = previous_actual_revision + 1",
            name="ck_injection_actual_correction_revision",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_injection_actual_correction_payload_hash",
        ),
        sa.CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_actual_correction_request_id",
        ),
        sa.CheckConstraint(
            "length(trim(response_json)) > 2",
            name="ck_injection_actual_correction_response",
        ),
    )
    for column_name in (
        "factory_id",
        "actual_id",
        "request_id",
        "created_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_schedule_actual_corrections_{column_name}",
            "injection_schedule_actual_corrections",
            [column_name],
        )


def downgrade() -> None:
    op.drop_table("injection_schedule_actual_corrections")
    op.drop_table("injection_schedule_shift_actuals")
    op.drop_table("injection_schedule_replan_runs")
    with op.batch_alter_table(
        "injection_schedule_tasks",
        recreate="auto",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_injection_schedule_task_execution_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_injection_schedule_task_source",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_injection_schedule_task_id_version_factory",
            type_="unique",
        )
    op.drop_index(
        "ix_injection_schedule_tasks_protected",
        table_name="injection_schedule_tasks",
    )
    op.drop_index(
        "ix_injection_schedule_tasks_execution_status",
        table_name="injection_schedule_tasks",
    )
    op.drop_column("injection_schedule_tasks", "protected")
    op.drop_column("injection_schedule_tasks", "execution_status")
    op.drop_index(
        "ix_injection_order_masters_priority_code",
        table_name="injection_order_masters",
    )
    with op.batch_alter_table(
        "injection_order_masters",
        recreate="auto",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_injection_order_priority_code",
            type_="check",
        )
    op.drop_column("injection_order_masters", "priority_code")
