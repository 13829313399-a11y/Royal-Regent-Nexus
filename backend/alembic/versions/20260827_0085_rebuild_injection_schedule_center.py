"""rebuild the isolated injection schedule center data contract

Revision ID: 20260827_0085
Revises: 20260826_0084
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError

revision: str = "20260827_0085"
down_revision: str | Sequence[str] | None = "20260826_0084"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TARGET_TABLES = (
    "injection_schedule_factory_settings",
    "injection_schedule_import_batches",
    "injection_schedule_import_request_bindings",
    "injection_schedule_order_demands",
    "injection_schedule_machines",
    "injection_schedule_molds",
    "injection_schedule_lines",
    "injection_schedule_shift_outputs",
    "injection_schedule_import_issues",
    "injection_schedule_saved_views",
    "injection_schedule_audit_events",
    "injection_schedule_auto_proposals",
)

TARGET_TABLES_CHILD_FIRST = (
    "injection_schedule_shift_outputs",
    "injection_schedule_lines",
    "injection_schedule_order_demands",
    "injection_schedule_import_issues",
    "injection_schedule_import_request_bindings",
    "injection_schedule_auto_proposals",
    "injection_schedule_audit_events",
    "injection_schedule_saved_views",
    "injection_schedule_molds",
    "injection_schedule_machines",
    "injection_schedule_import_batches",
    "injection_schedule_factory_settings",
)


def _preflight_target_names() -> None:
    """Never adopt or overwrite an orphaned table from an earlier rebuild."""

    if context.is_offline_mode():
        return
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    conflicts = sorted(existing.intersection(TARGET_TABLES))
    if conflicts:
        raise CommandError(
            "20260827_0085 refused to rebuild the injection schedule center because "
            "exact target table names already exist: "
            f"{', '.join(conflicts)}. No existing table will be adopted, overwritten, "
            "renamed, or deleted; back up the database and reconcile schema drift first."
        )


def _create_single_column_indexes(table_name: str, columns: Sequence[str]) -> None:
    for column_name in columns:
        op.create_index(
            f"ix_{table_name}_{column_name}",
            table_name,
            [column_name],
        )


def _create_factory_settings() -> None:
    op.create_table(
        "injection_schedule_factory_settings",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("factory_name", sa.String(128), nullable=False),
        sa.Column(
            "timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"
        ),
        sa.Column("business_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("current_shift", sa.String(16), nullable=False, server_default="DAY"),
        sa.Column(
            "day_shift_start", sa.String(5), nullable=False, server_default="08:00"
        ),
        sa.Column(
            "day_shift_end", sa.String(5), nullable=False, server_default="20:00"
        ),
        sa.Column(
            "night_shift_start", sa.String(5), nullable=False, server_default="20:00"
        ),
        sa.Column(
            "night_shift_end", sa.String(5), nullable=False, server_default="08:00"
        ),
        sa.Column(
            "warehouse_buffer_days", sa.Integer(), nullable=False, server_default="3"
        ),
        sa.Column(
            "fallback_water_ratio",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0.01",
        ),
        sa.Column(
            "auto_schedule_mode",
            sa.String(32),
            nullable=False,
            server_default="PREVIEW_CONFIRM",
        ),
        sa.Column(
            "ai_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "template_family",
            sa.String(64),
            nullable=False,
            server_default="unified_injection_schedule",
        ),
        sa.Column(
            "template_version", sa.String(32), nullable=False, server_default="1.0"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_factory_settings_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id", name="uq_injection_schedule_factory_settings_factory"
        ),
        sa.CheckConstraint(
            "current_shift IN ('DAY', 'NIGHT')",
            name="ck_injection_schedule_factory_settings_shift",
        ),
        sa.CheckConstraint(
            "auto_schedule_mode IN ('DISABLED', 'PREVIEW_ONLY', 'PREVIEW_CONFIRM')",
            name="ck_injection_schedule_factory_settings_auto_mode",
        ),
        sa.CheckConstraint(
            "warehouse_buffer_days >= 0",
            name="ck_injection_schedule_factory_settings_buffer",
        ),
        sa.CheckConstraint(
            "fallback_water_ratio >= 0 AND fallback_water_ratio <= 1",
            name="ck_injection_schedule_factory_settings_water_ratio",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_factory_settings_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_factory_settings",
        (
            "factory_id",
            "business_date",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ),
    )


def _create_import_batches() -> None:
    op.create_table(
        "injection_schedule_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_file_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "source_sheet", sa.String(128), nullable=False, server_default="03_订单导入"
        ),
        sa.Column("template_family", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(32), nullable=False),
        sa.Column("contract_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PREVIEW"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "blocking_issue_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("preview_request_id", sa.String(128), nullable=False),
        sa.Column("commit_request_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "confirmed_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("confirmed_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_import_batch_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "source_file_sha256",
            "template_version",
            name="uq_injection_schedule_import_batch_file_version",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "preview_request_id",
            name="uq_injection_schedule_import_batch_preview_request",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "commit_request_id",
            name="uq_injection_schedule_import_batch_commit_request",
        ),
        sa.CheckConstraint(
            "status IN ('PREVIEW', 'READY', 'CONFIRMED', 'REJECTED')",
            name="ck_injection_schedule_import_batch_status",
        ),
        sa.CheckConstraint(
            "source_size_bytes > 0 AND issue_count >= 0 AND blocking_issue_count >= 0",
            name="ck_injection_schedule_import_batch_counts",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_import_batch_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_import_batches",
        (
            "factory_id",
            "source_file_sha256",
            "contract_fingerprint",
            "status",
            "commit_request_id",
            "created_by",
            "created_at",
            "confirmed_by",
            "confirmed_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_import_batch_factory_created",
        "injection_schedule_import_batches",
        ["factory_id", "created_at"],
    )


def _create_import_request_bindings() -> None:
    op.create_table(
        "injection_schedule_import_request_bindings",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("source_file_sha256", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_schedule_import_request_binding_id_factory",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_schedule_import_request_binding_request",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
            name="fk_injection_schedule_import_request_binding_batch_factory",
        ),
    )
    op.create_index(
        "ix_is_import_request_binding_factory_batch",
        "injection_schedule_import_request_bindings",
        ["factory_id", "batch_id"],
    )
    op.create_index(
        "ix_is_import_request_binding_source_hash",
        "injection_schedule_import_request_bindings",
        ["source_file_sha256"],
    )
    op.create_index(
        "ix_is_import_request_binding_created",
        "injection_schedule_import_request_bindings",
        ["created_at"],
    )


def _create_order_demands() -> None:
    op.create_table(
        "injection_schedule_order_demands",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_batch_id", sa.String(96), nullable=True),
        sa.Column("source_sheet", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("raw_total_sets", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw_source_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("order_no", sa.String(128), nullable=False),
        sa.Column("product_code", sa.String(128), nullable=False),
        sa.Column("mold_code", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("quantity_sets", sa.Numeric(18, 6), nullable=False),
        sa.Column("order_shots", sa.Numeric(18, 6), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="NORMAL"),
        sa.Column("order_date", sa.String(10), nullable=False, server_default=""),
        sa.Column(
            "delivery_start_date", sa.String(10), nullable=False, server_default=""
        ),
        sa.Column(
            "delivery_due_date", sa.String(10), nullable=False, server_default=""
        ),
        sa.Column("shipping_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("warehouse", sa.String(128), nullable=False, server_default=""),
        sa.Column("color", sa.String(128), nullable=False, server_default=""),
        sa.Column("pigment_code", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "color_lightness", sa.String(16), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("material_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("water_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("net_weight_g", sa.Numeric(18, 6), nullable=True),
        sa.Column("gross_weight_g", sa.Numeric(18, 6), nullable=True),
        sa.Column("daily_target", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "material_status",
            sa.String(16),
            nullable=False,
            server_default="UNPREPARED",
        ),
        sa.Column(
            "material_prepared_kg",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_order_demand_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "source_batch_id",
            "source_sheet",
            "source_row",
            name="uq_injection_schedule_order_demand_source",
        ),
        sa.ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
            name="fk_injection_schedule_order_demand_batch_factory",
        ),
        sa.CheckConstraint(
            "quantity_sets > 0 AND order_shots > 0",
            name="ck_injection_schedule_order_demand_quantities",
        ),
        sa.CheckConstraint(
            "water_ratio IS NULL OR (water_ratio >= 0 AND water_ratio <= 1)",
            name="ck_injection_schedule_order_demand_water_ratio",
        ),
        sa.CheckConstraint(
            "material_prepared_kg >= 0",
            name="ck_injection_schedule_order_demand_material_prepared",
        ),
        sa.CheckConstraint(
            "priority IN ('EXPEDITE', 'URGENT', 'NORMAL')",
            name="ck_injection_schedule_order_demand_priority",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SCHEDULED', 'IN_PRODUCTION', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_schedule_order_demand_status",
        ),
        sa.CheckConstraint(
            "material_status IN ('UNPREPARED', 'PARTIAL', 'READY', 'SHORTAGE')",
            name="ck_injection_schedule_order_demand_material_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_order_demand_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_order_demands",
        (
            "factory_id",
            "source_batch_id",
            "order_no",
            "product_code",
            "mold_code",
            "priority",
            "order_date",
            "delivery_start_date",
            "delivery_due_date",
            "shipping_date",
            "warehouse",
            "color",
            "material_name",
            "material_status",
            "status",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_order_demand_factory_due",
        "injection_schedule_order_demands",
        ["factory_id", "delivery_due_date"],
    )
    op.create_index(
        "ix_injection_schedule_order_demand_factory_status_priority",
        "injection_schedule_order_demands",
        ["factory_id", "status", "priority"],
    )
    op.create_index(
        "uq_injection_schedule_order_demand_active_business_key",
        "injection_schedule_order_demands",
        ["factory_id", "order_no", "product_code", "mold_code"],
        unique=True,
        sqlite_where=sa.text("status != 'CANCELLED'"),
        postgresql_where=sa.text("status != 'CANCELLED'"),
    )


def _create_machines() -> None:
    op.create_table(
        "injection_schedule_machines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("position", sa.String(128), nullable=False, server_default=""),
        sa.Column("machine_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("machine_ounce_capacity", sa.Numeric(18, 6), nullable=True),
        sa.Column("shot_capacity_g", sa.Numeric(18, 6), nullable=True),
        sa.Column("tonnage", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "is_automatic", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "robot_arm_type", sa.String(16), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("fixture", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "supports_core_pull",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "efficiency_factor", sa.Numeric(12, 6), nullable=False, server_default="1"
        ),
        sa.Column("max_mold_length_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_mold_width_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_mold_height_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("min_mold_thickness_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_mold_thickness_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("tie_bar_x_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("tie_bar_y_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "allowed_materials_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "forbidden_materials_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "allowed_color_lightness_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="AVAILABLE"),
        sa.Column("available_from", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "structured_constraints_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("raw_remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_machine_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_schedule_machine_factory_code",
        ),
        sa.CheckConstraint(
            "efficiency_factor > 0", name="ck_injection_schedule_machine_efficiency"
        ),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'RUNNING', 'MAINTENANCE', 'DISABLED')",
            name="ck_injection_schedule_machine_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_machine_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_machines",
        (
            "factory_id",
            "machine_code",
            "status",
            "available_from",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_machine_factory_status",
        "injection_schedule_machines",
        ["factory_id", "status"],
    )


def _create_molds() -> None:
    op.create_table(
        "injection_schedule_molds",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_code", sa.String(128), nullable=False),
        sa.Column("product_code", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("mold_ounce_requirement", sa.Numeric(18, 6), nullable=True),
        sa.Column("min_machine_ounce", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_machine_ounce", sa.Numeric(18, 6), nullable=True),
        sa.Column("cavity_count", sa.Integer(), nullable=True),
        sa.Column("shot_weight_g", sa.Numeric(18, 6), nullable=True),
        sa.Column("recommended_tonnage", sa.Numeric(18, 6), nullable=True),
        sa.Column("mold_length_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("mold_width_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("mold_height_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column("mold_thickness_mm", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "requires_core_pull",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "required_robot_arm",
            sa.String(16),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column(
            "required_fixture", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "allowed_materials_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "forbidden_machine_codes_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "structured_constraints_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("daily_target", sa.Numeric(18, 6), nullable=True),
        sa.Column("mold_change_reference_hours", sa.Numeric(12, 6), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_mold_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "mold_code",
            "product_code",
            name="uq_injection_schedule_mold_factory_code_product",
        ),
        sa.CheckConstraint(
            "min_machine_ounce IS NULL OR max_machine_ounce IS NULL "
            "OR min_machine_ounce <= max_machine_ounce",
            name="ck_injection_schedule_mold_machine_range",
        ),
        sa.CheckConstraint(
            "cavity_count IS NULL OR cavity_count > 0",
            name="ck_injection_schedule_mold_cavity_count",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'MAINTENANCE', 'DISABLED')",
            name="ck_injection_schedule_mold_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_injection_schedule_mold_version"),
    )
    _create_single_column_indexes(
        "injection_schedule_molds",
        (
            "factory_id",
            "mold_code",
            "product_code",
            "status",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_mold_factory_status",
        "injection_schedule_molds",
        ["factory_id", "status"],
    )


def _create_lines() -> None:
    op.create_table(
        "injection_schedule_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("order_demand_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=True),
        sa.Column("mold_id", sa.String(96), nullable=True),
        sa.Column("sequence_no", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority", sa.String(16), nullable=False, server_default="NORMAL"),
        sa.Column("planned_start_at", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "planned_finish_at", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column(
            "suggested_changeover_hours",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("manual_changeover_hours", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "final_changeover_hours",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "manual_changeover_reason", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column(
            "downtime_hours", sa.Numeric(12, 6), nullable=False, server_default="0"
        ),
        sa.Column("system_daily_target", sa.Numeric(18, 6), nullable=True),
        sa.Column("manual_daily_target", sa.Numeric(18, 6), nullable=True),
        sa.Column("effective_daily_target", sa.Numeric(18, 6), nullable=True),
        sa.Column("warehouse_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("delivery_gap_days", sa.Numeric(12, 6), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_line_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "machine_id",
            "sequence_no",
            name="uq_injection_schedule_line_machine_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["order_demand_id", "factory_id"],
            [
                "injection_schedule_order_demands.id",
                "injection_schedule_order_demands.factory_id",
            ],
            name="fk_injection_schedule_line_order_factory",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
            name="fk_injection_schedule_line_machine_factory",
        ),
        sa.ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_schedule_molds.id", "injection_schedule_molds.factory_id"],
            name="fk_injection_schedule_line_mold_factory",
        ),
        sa.CheckConstraint(
            "(machine_id IS NULL AND sequence_no IS NULL) "
            "OR (machine_id IS NOT NULL AND sequence_no IS NOT NULL)",
            name="ck_injection_schedule_line_assignment",
        ),
        sa.CheckConstraint(
            "sequence_no IS NULL OR sequence_no >= 0",
            name="ck_injection_schedule_line_sequence_nonnegative",
        ),
        sa.CheckConstraint(
            "status != 'CANCELLED' OR (machine_id IS NULL AND sequence_no IS NULL)",
            name="ck_injection_schedule_line_cancelled_unassigned",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SCHEDULED', 'IN_PRODUCTION', 'PAUSED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_schedule_line_status",
        ),
        sa.CheckConstraint(
            "priority IN ('EXPEDITE', 'URGENT', 'NORMAL')",
            name="ck_injection_schedule_line_priority",
        ),
        sa.CheckConstraint(
            "suggested_changeover_hours >= 0 "
            "AND (manual_changeover_hours IS NULL OR manual_changeover_hours >= 0) "
            "AND final_changeover_hours >= 0 AND downtime_hours >= 0",
            name="ck_injection_schedule_line_hours",
        ),
        sa.CheckConstraint("version >= 1", name="ck_injection_schedule_line_version"),
    )
    _create_single_column_indexes(
        "injection_schedule_lines",
        (
            "factory_id",
            "order_demand_id",
            "machine_id",
            "mold_id",
            "status",
            "is_locked",
            "priority",
            "planned_start_at",
            "planned_finish_at",
            "warehouse_date",
            "delivery_gap_days",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_line_factory_status",
        "injection_schedule_lines",
        ["factory_id", "status"],
    )
    op.create_index(
        "ix_injection_schedule_line_factory_window",
        "injection_schedule_lines",
        ["factory_id", "planned_start_at", "planned_finish_at"],
    )
    op.create_index(
        "uq_injection_schedule_line_active_demand",
        "injection_schedule_lines",
        ["factory_id", "order_demand_id"],
        unique=True,
        sqlite_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
        postgresql_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
    )


def _create_shift_outputs() -> None:
    op.create_table(
        "injection_schedule_shift_outputs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("schedule_line_id", sa.String(96), nullable=False),
        sa.Column("production_date", sa.String(10), nullable=False),
        sa.Column("shift", sa.String(16), nullable=False),
        sa.Column("reported_shots", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "defect_shots", sa.Numeric(18, 6), nullable=False, server_default="0"
        ),
        sa.Column("qualified_shots", sa.Numeric(18, 6), nullable=False),
        sa.Column("downtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("downtime_reason", sa.String(128), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("reported_by", sa.String(64), nullable=False),
        sa.Column(
            "reported_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("reported_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_shift_output_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "schedule_line_id",
            "production_date",
            "shift",
            name="uq_injection_schedule_shift_output_slot",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_line_id", "factory_id"],
            ["injection_schedule_lines.id", "injection_schedule_lines.factory_id"],
            name="fk_injection_schedule_shift_output_line_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "shift IN ('DAY', 'NIGHT')",
            name="ck_injection_schedule_shift_output_shift",
        ),
        sa.CheckConstraint(
            "reported_shots >= 0 AND defect_shots >= 0 "
            "AND qualified_shots >= 0 AND defect_shots <= reported_shots "
            "AND qualified_shots = reported_shots - defect_shots",
            name="ck_injection_schedule_shift_output_quantities",
        ),
        sa.CheckConstraint(
            "downtime_minutes >= 0",
            name="ck_injection_schedule_shift_output_downtime",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_shift_output_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_shift_outputs",
        (
            "factory_id",
            "schedule_line_id",
            "production_date",
            "shift",
            "reported_by",
            "reported_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_shift_output_factory_date",
        "injection_schedule_shift_outputs",
        ["factory_id", "production_date"],
    )


def _create_import_issues() -> None:
    op.create_table(
        "injection_schedule_import_issues",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("source_sheet", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("raw_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_import_issue_id_factory"
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
            name="fk_injection_schedule_import_issue_batch_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_injection_schedule_import_issue_severity",
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_import_issues",
        (
            "factory_id",
            "batch_id",
            "severity",
            "error_type",
            "blocking",
            "created_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_import_issue_batch_blocking_row",
        "injection_schedule_import_issues",
        ["batch_id", "blocking", "source_row"],
    )


def _create_saved_views() -> None:
    op.create_table(
        "injection_schedule_saved_views",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="PERSONAL"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_saved_view_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "user_id",
            "name",
            "scope",
            name="uq_injection_schedule_saved_view_owner_name",
        ),
        sa.CheckConstraint(
            "scope IN ('PERSONAL', 'FACTORY_SHARED')",
            name="ck_injection_schedule_saved_view_scope",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="ck_injection_schedule_saved_view_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_saved_view_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_saved_views",
        (
            "factory_id",
            "user_id",
            "scope",
            "is_default",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_saved_view_factory_user",
        "injection_schedule_saved_views",
        ["factory_id", "user_id"],
    )


def _create_audit_events() -> None:
    op.create_table(
        "injection_schedule_audit_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column(
            "actor_display_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_audit_event_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "event_sequence",
            name="uq_injection_schedule_audit_event_factory_sequence",
        ),
        sa.CheckConstraint(
            "event_sequence >= 1", name="ck_injection_schedule_audit_event_sequence"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_audit_events",
        (
            "factory_id",
            "event_type",
            "entity_type",
            "entity_id",
            "actor_user_id",
            "created_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_audit_event_entity",
        "injection_schedule_audit_events",
        ["factory_id", "entity_type", "entity_id"],
    )


def _create_audit_immutability_guard() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_events_no_update
            BEFORE UPDATE ON injection_schedule_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'injection schedule audit events are immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_events_no_delete
            BEFORE DELETE ON injection_schedule_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'injection schedule audit events are immutable');
            END
            """
        )
    elif dialect_name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_injection_schedule_audit_events_mutation_0085()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'injection schedule audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_events_no_update
            BEFORE UPDATE ON injection_schedule_audit_events
            FOR EACH ROW
            EXECUTE FUNCTION reject_injection_schedule_audit_events_mutation_0085()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_injection_schedule_audit_events_no_delete
            BEFORE DELETE ON injection_schedule_audit_events
            FOR EACH ROW
            EXECUTE FUNCTION reject_injection_schedule_audit_events_mutation_0085()
            """
        )
    else:
        raise CommandError(
            "20260827_0085 cannot enforce immutable injection schedule audit "
            f"events on unsupported database dialect: {dialect_name}"
        )


def _drop_audit_immutability_guard() -> None:
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_schedule_audit_events_no_update"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_schedule_audit_events_no_delete"
        )
    elif dialect_name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_schedule_audit_events_no_update "
            "ON injection_schedule_audit_events"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_injection_schedule_audit_events_no_delete "
            "ON injection_schedule_audit_events"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS "
            "reject_injection_schedule_audit_events_mutation_0085()"
        )
    else:
        raise CommandError(
            "20260827_0085 cannot safely remove immutable injection schedule audit "
            f"guards on unsupported database dialect: {dialect_name}"
        )


def _create_auto_proposals() -> None:
    op.create_table(
        "injection_schedule_auto_proposals",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("request_payload_sha256", sa.String(64), nullable=False),
        sa.Column("input_version_digest", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PREVIEW"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("changes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unscheduled_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("applied_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("applied_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_injection_schedule_auto_proposal_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_schedule_auto_proposal_request",
        ),
        sa.CheckConstraint(
            "status IN ('PREVIEW', 'APPLIED', 'EXPIRED', 'REJECTED')",
            name="ck_injection_schedule_auto_proposal_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_auto_proposal_version"
        ),
    )
    _create_single_column_indexes(
        "injection_schedule_auto_proposals",
        (
            "factory_id",
            "request_payload_sha256",
            "input_version_digest",
            "status",
            "created_by",
            "created_at",
            "expires_at",
            "applied_by",
            "applied_at",
        ),
    )
    op.create_index(
        "ix_injection_schedule_auto_proposal_factory_created",
        "injection_schedule_auto_proposals",
        ["factory_id", "created_at"],
    )


def upgrade() -> None:
    _preflight_target_names()
    _create_factory_settings()
    _create_import_batches()
    _create_import_request_bindings()
    _create_order_demands()
    _create_machines()
    _create_molds()
    _create_lines()
    _create_shift_outputs()
    _create_import_issues()
    _create_saved_views()
    _create_audit_events()
    _create_audit_immutability_guard()
    _create_auto_proposals()


def downgrade() -> None:
    if context.is_offline_mode():
        raise CommandError(
            "20260827_0085 requires an online downgrade so it can protect business data"
        )

    connection = op.get_bind()
    existing = set(sa.inspect(connection).get_table_names())
    missing = sorted(set(TARGET_TABLES) - existing)
    if missing:
        raise CommandError(
            "20260827_0085 downgrade refused because the new injection schedule schema "
            f"is incomplete: {', '.join(missing)}. Reconcile schema drift first."
        )

    populated = [
        table_name
        for table_name in TARGET_TABLES
        if connection.execute(sa.text(f'SELECT 1 FROM "{table_name}" LIMIT 1')).first()
        is not None
    ]
    if populated:
        raise CommandError(
            "20260827_0085 cannot be downgraded after injection schedule center "
            f"business data exists in: {', '.join(populated)}. Restore a verified "
            "pre-migration backup instead of deleting production data."
        )

    _drop_audit_immutability_guard()
    for table_name in TARGET_TABLES_CHILD_FIRST:
        op.drop_table(table_name)
