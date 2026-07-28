"""rebuild injection schedule phase 2

Revision ID: 20260723_0032
Revises: 20260723_0031
Create Date: 2026-07-23 16:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0032"
down_revision: str | Sequence[str] | None = "20260723_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "injection_schedule_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_content_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_content", sa.LargeBinary(), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("detected_sheets_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("business_date", sa.String(20), nullable=False, server_default=""),
        sa.Column("draft_version_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("confirm_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("rejected_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("rejected_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("rejection_reason", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('previewed', 'confirmed', 'rejected')",
            name="ck_injection_import_batch_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_injection_import_batch_revision"),
        sa.UniqueConstraint(
            "factory_id",
            "source_sha256",
            name="uq_injection_import_batch_factory_sha256",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_import_batch_id_factory",
        ),
    )
    _indexes(
        "injection_schedule_import_batches",
        "factory_id",
        "source_sha256",
        "status",
        "draft_version_id",
        "created_by",
        "created_at",
    )

    op.create_table(
        "injection_schedule_import_issues",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("source_sheet", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("field_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="ck_injection_import_issue_severity",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_import_issue_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ("batch_id", "factory_id"),
            (
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ),
            name="fk_injection_import_issue_batch_factory",
            ondelete="CASCADE",
        ),
    )
    _indexes(
        "injection_schedule_import_issues",
        "factory_id",
        "batch_id",
        "severity",
        "code",
        "blocking",
    )

    op.create_table(
        "injection_machine_masters",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("machine_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("workshop", sa.String(64), nullable=False, server_default=""),
        sa.Column("machine_class", sa.String(128), nullable=False, server_default=""),
        sa.Column("tonnage_t", sa.Float(), nullable=True),
        sa.Column("process_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("robot_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("fixture_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("max_shot_weight_g", sa.Float(), nullable=True),
        sa.Column("tie_bar_x_mm", sa.Float(), nullable=True),
        sa.Column("tie_bar_y_mm", sa.Float(), nullable=True),
        sa.Column("mold_thickness_min_mm", sa.Float(), nullable=True),
        sa.Column("mold_thickness_max_mm", sa.Float(), nullable=True),
        sa.Column("opening_stroke_mm", sa.Float(), nullable=True),
        sa.Column("ejector_stroke_mm", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
        sa.Column("available_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("material_rules_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="incomplete"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_batch_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('available', 'maintenance', 'stopped', 'retired')",
            name="ck_injection_machine_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_injection_machine_revision"),
        sa.UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_machine_factory_code",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_machine_id_factory",
        ),
    )
    _indexes(
        "injection_machine_masters",
        "factory_id",
        "workshop",
        "status",
        "quality_status",
        "source_batch_id",
    )

    op.create_table(
        "injection_mold_masters",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_code", sa.String(128), nullable=False),
        sa.Column("normalized_mold_code", sa.String(128), nullable=False),
        sa.Column("mold_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("machine_class", sa.String(128), nullable=False, server_default=""),
        sa.Column("robot_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("fixture_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("length_mm", sa.Float(), nullable=True),
        sa.Column("width_mm", sa.Float(), nullable=True),
        sa.Column("height_mm", sa.Float(), nullable=True),
        sa.Column("mold_weight_kg", sa.Float(), nullable=True),
        sa.Column("gross_shot_weight_g", sa.Float(), nullable=True),
        sa.Column("cavities", sa.Integer(), nullable=True),
        sa.Column("cycle_seconds", sa.Float(), nullable=True),
        sa.Column("required_capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("material_rules_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="incomplete"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_batch_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint("revision >= 1", name="ck_injection_mold_revision"),
        sa.UniqueConstraint(
            "factory_id",
            "normalized_mold_code",
            name="uq_injection_mold_factory_code",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_mold_id_factory",
        ),
    )
    _indexes(
        "injection_mold_masters",
        "factory_id",
        "quality_status",
        "source_batch_id",
    )

    op.create_table(
        "injection_order_masters",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("natural_key", sa.String(256), nullable=False),
        sa.Column("order_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_code", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("mold_code", sa.String(128), nullable=False, server_default=""),
        sa.Column("color", sa.String(128), nullable=False, server_default=""),
        sa.Column("pigment", sa.String(128), nullable=False, server_default=""),
        sa.Column("material", sa.String(255), nullable=False, server_default=""),
        sa.Column("machine_class", sa.String(128), nullable=False, server_default=""),
        sa.Column("order_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("produced_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("outstanding_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("daily_target_qty", sa.Float(), nullable=True),
        sa.Column("delivery_due_date", sa.String(20), nullable=False, server_default=""),
        sa.Column("priority_flag", sa.String(32), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("imported_assigned_machine_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("imported_plan_start_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("imported_plan_finish_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("source_sheet", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_batch_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("source_values_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="incomplete"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('open', 'completed', 'canceled')",
            name="ck_injection_order_status",
        ),
        sa.CheckConstraint("order_qty >= 0", name="ck_injection_order_qty"),
        sa.CheckConstraint("produced_qty >= 0", name="ck_injection_produced_qty"),
        sa.CheckConstraint("outstanding_qty >= 0", name="ck_injection_outstanding_qty"),
        sa.CheckConstraint("revision >= 1", name="ck_injection_order_revision"),
        sa.UniqueConstraint(
            "factory_id",
            "natural_key",
            name="uq_injection_order_factory_natural_key",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_order_id_factory",
        ),
    )
    _indexes(
        "injection_order_masters",
        "factory_id",
        "order_no",
        "product_code",
        "mold_code",
        "status",
        "imported_assigned_machine_code",
        "source_batch_id",
        "quality_status",
    )

    op.create_table(
        "injection_schedule_rule_configs",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint("revision >= 1", name="ck_injection_rule_config_revision"),
    )

    op.create_table(
        "injection_schedule_versions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("business_date", sa.String(20), nullable=False, server_default=""),
        sa.Column("plan_base_at", sa.String(32), nullable=False),
        sa.Column("base_version_id", sa.String(96), nullable=True),
        sa.Column("source_batch_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("rules_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("data_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("validation_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("published_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("published_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("published_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("publish_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("superseded_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_injection_schedule_version_status",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_schedule_version_revision",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "version_no",
            name="uq_injection_schedule_version_factory_no",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_schedule_version_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ("base_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_schedule_version_base_factory",
        ),
    )
    _indexes(
        "injection_schedule_versions",
        "factory_id",
        "status",
        "source_batch_id",
        "created_by",
        "created_at",
    )
    op.create_index(
        "uq_injection_schedule_one_published_per_factory",
        "injection_schedule_versions",
        ["factory_id"],
        unique=True,
        sqlite_where=sa.text("status = 'published'"),
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "injection_schedule_factory_states",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("current_published_version_id", sa.String(96), nullable=True),
        sa.Column("next_version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "next_version_no >= 1",
            name="ck_injection_factory_next_version",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_factory_state_revision",
        ),
        sa.ForeignKeyConstraint(
            ("current_published_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_factory_state_published_version",
        ),
    )

    op.create_table(
        "injection_schedule_tasks",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("mold_id", sa.String(96), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("planned_qty", sa.Float(), nullable=False),
        sa.Column("planned_start_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("planned_finish_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("setup_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("split_group_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("parent_task_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("order_no_snapshot", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_code_snapshot", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_name_snapshot", sa.String(255), nullable=False, server_default=""),
        sa.Column("mold_code_snapshot", sa.String(128), nullable=False, server_default=""),
        sa.Column("machine_code_snapshot", sa.String(64), nullable=False, server_default=""),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("risk_reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("order_revision_snapshot", sa.Integer(), nullable=False),
        sa.Column("machine_revision_snapshot", sa.Integer(), nullable=False),
        sa.Column("mold_revision_snapshot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False, server_default=""),
        sa.CheckConstraint(
            "sequence_no >= 0",
            name="ck_injection_schedule_task_sequence",
        ),
        sa.CheckConstraint(
            "planned_qty > 0",
            name="ck_injection_schedule_task_qty",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_schedule_task_revision",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_schedule_task_id_factory",
        ),
        sa.UniqueConstraint(
            "version_id",
            "machine_id",
            "sequence_no",
            name="uq_injection_schedule_task_machine_sequence",
        ),
        sa.ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_schedule_task_version_factory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ("order_id", "factory_id"),
            (
                "injection_order_masters.id",
                "injection_order_masters.factory_id",
            ),
            name="fk_injection_schedule_task_order_factory",
        ),
        sa.ForeignKeyConstraint(
            ("machine_id", "factory_id"),
            (
                "injection_machine_masters.id",
                "injection_machine_masters.factory_id",
            ),
            name="fk_injection_schedule_task_machine_factory",
        ),
        sa.ForeignKeyConstraint(
            ("mold_id", "factory_id"),
            (
                "injection_mold_masters.id",
                "injection_mold_masters.factory_id",
            ),
            name="fk_injection_schedule_task_mold_factory",
        ),
    )
    _indexes(
        "injection_schedule_tasks",
        "factory_id",
        "version_id",
        "order_id",
        "machine_id",
        "mold_id",
        "locked",
        "split_group_id",
        "risk_level",
    )

    op.create_table(
        "injection_schedule_validation_runs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(96), nullable=False),
        sa.Column("version_revision", sa.Integer(), nullable=False),
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("blocking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "status IN ('passed', 'blocked')",
            name="ck_injection_validation_run_status",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_validation_run_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_validation_run_version_factory",
            ondelete="CASCADE",
        ),
    )
    _indexes(
        "injection_schedule_validation_runs",
        "factory_id",
        "version_id",
        "data_hash",
        "status",
        "created_by",
        "created_at",
    )

    op.create_table(
        "injection_schedule_validation_items",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("version_id", sa.String(96), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("constraint_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'unknown')",
            name="ck_injection_validation_item_status",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_validation_item_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ("run_id", "factory_id"),
            (
                "injection_schedule_validation_runs.id",
                "injection_schedule_validation_runs.factory_id",
            ),
            name="fk_injection_validation_item_run_factory",
            ondelete="CASCADE",
        ),
    )
    _indexes(
        "injection_schedule_validation_items",
        "factory_id",
        "run_id",
        "version_id",
        "task_id",
        "constraint_code",
        "status",
        "blocking",
    )

    op.create_table(
        "injection_schedule_audit_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(128), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("old_revision", sa.Integer(), nullable=True),
        sa.Column("new_revision", sa.Integer(), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_audit_event_id_factory",
        ),
    )
    _indexes(
        "injection_schedule_audit_events",
        "factory_id",
        "entity_type",
        "entity_id",
        "action",
        "actor_id",
        "created_at",
    )
    _create_audit_immutability_guard()


def downgrade() -> None:
    raise RuntimeError(
        "20260723_0032 contains authoritative Phase 2 scheduling data and is "
        "intentionally forward-only. Restore a pre-upgrade database backup "
        "instead of downgrading."
    )


def _indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def _create_audit_immutability_guard() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_no_update
            BEFORE UPDATE ON injection_schedule_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'injection schedule audit events are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_no_delete
            BEFORE DELETE ON injection_schedule_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'injection schedule audit events are append-only');
            END
            """
        )
    elif dialect_name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_injection_schedule_audit_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              RAISE EXCEPTION 'injection schedule audit events are append-only';
            END;
            $$
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_immutable
            BEFORE UPDATE OR DELETE ON injection_schedule_audit_events
            FOR EACH ROW
            EXECUTE FUNCTION reject_injection_schedule_audit_mutation()
            """
        )
