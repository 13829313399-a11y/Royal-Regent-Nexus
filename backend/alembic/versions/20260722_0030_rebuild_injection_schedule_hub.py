"""rebuild injection schedule hub

Revision ID: 20260722_0030
Revises: 20260721_0029
Create Date: 2026-07-22 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260722_0030"
down_revision: Union[str, None] = "20260721_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    batch_columns = (
        sa.Column("source_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parser_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("detected_sheets_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("rejected_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("rejected_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("rejection_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("activated_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("superseded_at", sa.String(32), nullable=False, server_default=""),
    )
    for column in batch_columns:
        op.add_column("injection_schedule_import_batches", column)
    op.create_index(
        "ix_injection_schedule_import_batches_source_sha256",
        "injection_schedule_import_batches",
        ["source_sha256"],
    )
    op.execute(
        "UPDATE injection_schedule_import_batches SET status = 'legacy_snapshot' WHERE status = 'imported'"
    )

    op.create_table(
        "injection_schedule_import_diffs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("injection_schedule_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("diff_type", sa.String(32), nullable=False),
        sa.Column("task_match_key", sa.String(512), nullable=False),
        sa.Column("source_task_id", sa.String(96), nullable=False),
        sa.Column("current_task_id", sa.String(96), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=False),
        sa.Column("requires_confirmation", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(32), nullable=False),
    )
    _indexes("injection_schedule_import_diffs", "batch_id", "factory_id", "diff_type")

    op.create_table(
        "injection_machine_masters",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("workshop", sa.String(64), nullable=False),
        sa.Column("machine_spec_label", sa.String(128), nullable=False),
        sa.Column("machine_process_type", sa.String(64), nullable=False),
        sa.Column("robot_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("available_at", sa.String(32), nullable=False),
        sa.Column("source_batch_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("factory_id", "machine_code", name="uq_injection_machine_factory_code"),
    )
    _indexes("injection_machine_masters", "factory_id", "machine_code", "source_batch_id")

    op.create_table(
        "injection_mold_masters",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_code", sa.String(128), nullable=False),
        sa.Column("normalized_mold_code", sa.String(128), nullable=False),
        sa.Column("mold_name", sa.String(255), nullable=False),
        sa.Column("machine_class", sa.String(128), nullable=False),
        sa.Column("robot_type", sa.String(64), nullable=False),
        sa.Column("dimensions_json", sa.Text(), nullable=False),
        sa.Column("mold_weight_kg", sa.Float(), nullable=True),
        sa.Column("aliases_json", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("source_batch_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("factory_id", "normalized_mold_code", name="uq_injection_mold_factory_code"),
    )
    _indexes("injection_mold_masters", "factory_id", "normalized_mold_code", "source_batch_id")

    op.create_table(
        "injection_order_tasks",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_batch_id", sa.String(64), nullable=False),
        sa.Column("source_task_id", sa.String(96), nullable=False),
        sa.Column("task_match_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("material_readiness", sa.String(32), nullable=False),
        sa.Column("assigned_machine_code", sa.String(64), nullable=False),
        sa.Column("task_bucket", sa.String(32), nullable=False),
        sa.Column("mold_code", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("order_no", sa.String(128), nullable=False),
        sa.Column("product_code", sa.String(128), nullable=False),
        sa.Column("machine_model", sa.String(128), nullable=False),
        sa.Column("color", sa.String(128), nullable=False),
        sa.Column("pigment", sa.String(128), nullable=False),
        sa.Column("material", sa.String(128), nullable=False),
        sa.Column("order_qty", sa.Float(), nullable=True),
        sa.Column("produced_qty", sa.Float(), nullable=True),
        sa.Column("shortage_qty", sa.Float(), nullable=True),
        sa.Column("daily_target_qty", sa.Float(), nullable=True),
        sa.Column("delivery_due_date", sa.String(32), nullable=False),
        sa.Column("plan_start_at", sa.String(32), nullable=False),
        sa.Column("plan_finish_at", sa.String(32), nullable=False),
        sa.Column("warehouse_due_at", sa.String(32), nullable=False),
        sa.Column("delivery_gap_days", sa.Float(), nullable=True),
        sa.Column("priority_flag", sa.String(32), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("source_values_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )
    _indexes("injection_order_tasks", "factory_id", "source_batch_id", "task_match_key", "status", "material_readiness", "assigned_machine_code", "task_bucket")

    op.create_table(
        "injection_schedule_rules",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("factory_id", "rule_type", "rule_key", name="uq_injection_rule_factory_key"),
    )
    _indexes("injection_schedule_rules", "factory_id", "rule_type")

    op.create_table(
        "injection_schedule_versions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_batch_id", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.String(20), nullable=False),
        sa.Column("rules_snapshot_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("published_at", sa.String(32), nullable=False),
        sa.Column("superseded_at", sa.String(32), nullable=False),
    )
    _indexes("injection_schedule_versions", "factory_id", "source_batch_id", "status")

    op.create_table(
        "injection_schedule_assignments",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("version_id", sa.String(96), sa.ForeignKey("injection_schedule_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("planned_start_at", sa.String(32), nullable=False),
        sa.Column("planned_finish_at", sa.String(32), nullable=False),
        sa.Column("setup_hours", sa.Float(), nullable=False),
        sa.Column("duration_hours", sa.Float(), nullable=False),
        sa.Column("forced", sa.Integer(), nullable=False),
        sa.Column("forced_reason", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
    )
    _indexes("injection_schedule_assignments", "version_id", "factory_id", "task_id", "machine_id")

    op.create_table(
        "injection_schedule_constraint_results",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("version_id", sa.String(96), nullable=False),
        sa.Column("assignment_id", sa.String(96), nullable=False),
        sa.Column("constraint_code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("overridden", sa.Integer(), nullable=False),
    )
    _indexes("injection_schedule_constraint_results", "version_id", "assignment_id", "constraint_code")

    op.create_table(
        "injection_schedule_audit_logs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
    )
    _indexes("injection_schedule_audit_logs", "factory_id", "entity_type", "entity_id", "event_type")

    op.create_table(
        "injection_shift_outputs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("schedule_version_id", sa.String(96), nullable=False),
        sa.Column("assignment_id", sa.String(96), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("shift_date", sa.String(20), nullable=False),
        sa.Column("shift_code", sa.String(16), nullable=False),
        sa.Column("output_qty", sa.Float(), nullable=False),
        sa.Column("reported_by", sa.String(64), nullable=False),
        sa.Column("reported_at", sa.String(32), nullable=False),
    )
    _indexes("injection_shift_outputs", "factory_id", "schedule_version_id", "assignment_id", "machine_code", "shift_date")

    op.create_table(
        "injection_machine_downtimes",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("finished_at", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reported_by", sa.String(64), nullable=False),
        sa.Column("reported_at", sa.String(32), nullable=False),
    )
    _indexes("injection_machine_downtimes", "factory_id", "machine_code")


def downgrade() -> None:
    for table_name in (
        "injection_machine_downtimes",
        "injection_shift_outputs",
        "injection_schedule_audit_logs",
        "injection_schedule_constraint_results",
        "injection_schedule_assignments",
        "injection_schedule_versions",
        "injection_schedule_rules",
        "injection_order_tasks",
        "injection_mold_masters",
        "injection_machine_masters",
        "injection_schedule_import_diffs",
    ):
        op.drop_table(table_name)
    op.drop_index("ix_injection_schedule_import_batches_source_sha256", table_name="injection_schedule_import_batches")
    for column_name in (
        "superseded_at", "activated_at", "rejection_reason", "rejected_at", "rejected_by_name",
        "rejected_by", "confirmed_at", "confirmed_by_name", "confirmed_by", "created_by_name",
        "revision", "detected_sheets_json", "parser_version", "source_size_bytes", "source_sha256",
    ):
        op.drop_column("injection_schedule_import_batches", column_name)


def _indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])
