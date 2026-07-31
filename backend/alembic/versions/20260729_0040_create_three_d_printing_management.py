"""create 3D printing management, edge control and migration ledger

Revision ID: 20260729_0040
Revises: 20260728_0039
Create Date: 2026-07-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260729_0040"
down_revision: str | Sequence[str] | None = "20260728_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "three_d_printing:read",
        "查看3D打印管理",
        "查看华康B厂3D打印机、生产记录、物料和计划",
        "read",
        "normal",
    ),
    (
        "three_d_printing:operate",
        "操作3D打印业务",
        "维护华康B厂3D打印生产记录、产品、物料、库存和计划",
        "operate",
        "normal",
    ),
    (
        "three_d_printing:image_upload",
        "上传3D产品图片",
        "上传和替换华康B厂3D打印产品图片",
        "operate",
        "high",
    ),
    (
        "three_d_printing:export",
        "导出3D打印数据",
        "导出华康B厂3D打印业务数据",
        "operate",
        "normal",
    ),
    (
        "three_d_printing:printer_control",
        "远程控制3D打印机",
        "通过华康B厂边缘代理暂停或恢复3D打印机",
        "operate",
        "high",
    ),
    (
        "three_d_printing:audit_read",
        "查看3D打印审计",
        "查看华康B厂3D打印业务和远程控制审计记录",
        "read",
        "high",
    ),
)

OPERATOR_ROLE_IDS = (
    "position_3d_operator",
    "position_3d_supervisor",
    "position_3d_manager",
    "position_production_supervisor",
    "admin",
)
AUDIT_ROLE_IDS = (
    "position_3d_supervisor",
    "position_3d_manager",
    "position_production_supervisor",
    "admin",
)
CONTROL_ROLE_IDS = ("admin",)


def _create_indexes(table_name: str, columns: Sequence[str]) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def _create_tables() -> None:
    op.create_table(
        "three_d_printing_settings",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("machine_count", sa.Integer(), nullable=False, server_default="11"),
        sa.Column(
            "electricity_per_machine_day",
            sa.Numeric(14, 4),
            nullable=False,
            server_default="1.5",
        ),
        sa.Column("labor_per_day", sa.Numeric(14, 4), nullable=False, server_default="220"),
        sa.Column(
            "material_loss_rate",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="1.2",
        ),
        sa.Column(
            "profit_rate_percent",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="40",
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "three_d_printing_materials",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("material_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("price_per_kg", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "name",
            name="uq_three_d_printing_material_factory_name",
        ),
    )
    _create_indexes(
        "three_d_printing_materials",
        ("factory_id", "legacy_id", "name", "is_active"),
    )

    op.create_table(
        "three_d_printing_products",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("customer", sa.String(255), nullable=False, server_default=""),
        sa.Column("material_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("weight_g", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("duration_hours", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("default_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("quoted_price", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_product_id_factory",
        ),
    )
    _create_indexes(
        "three_d_printing_products",
        (
            "factory_id",
            "legacy_id",
            "name",
            "customer",
            "material_name",
            "is_active",
        ),
    )
    op.create_index(
        "ix_three_d_printing_product_search",
        "three_d_printing_products",
        ["factory_id", "name", "customer"],
    )

    op.create_table(
        "three_d_printing_product_images",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("product_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("original_file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("uploaded_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("uploaded_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id", "factory_id"],
            ["three_d_printing_products.id", "three_d_printing_products.factory_id"],
            name="fk_three_d_printing_image_product_factory",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_image_id_factory",
        ),
        sa.UniqueConstraint("product_id", name="uq_three_d_printing_product_image"),
    )
    _create_indexes(
        "three_d_printing_product_images",
        ("product_id", "factory_id", "sha256", "is_current", "created_at"),
    )

    op.create_table(
        "three_d_printing_printers",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("machine_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("printer_type", sa.String(64), nullable=False, server_default="bambu"),
        sa.Column("model", sa.String(128), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("state", sa.String(32), nullable=False, server_default="OFFLINE"),
        sa.Column("current_file", sa.String(512), nullable=False, server_default=""),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("live_material", sa.String(255), nullable=False, server_default=""),
        sa.Column("nozzle_temperature", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("bed_temperature", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("error_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "machine_no",
            name="uq_three_d_printing_printer_factory_machine",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_printer_id_factory",
        ),
    )
    _create_indexes(
        "three_d_printing_printers",
        (
            "factory_id",
            "legacy_id",
            "machine_no",
            "enabled",
            "connected",
            "state",
            "last_seen_at",
        ),
    )

    op.create_table(
        "three_d_printing_day_statuses",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("is_day_off", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "business_date",
            name="uq_three_d_printing_day_factory_date",
        ),
    )
    _create_indexes("three_d_printing_day_statuses", ("factory_id", "business_date"))

    op.create_table(
        "three_d_printing_production_records",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(96), nullable=True),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("machine_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("material_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("weight_g", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("duration_hours", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("design_fee", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("quoted_price", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("customer", sa.String(255), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("auto_record", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("print_start_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("print_end_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("gcode_file", sa.String(512), nullable=False, server_default=""),
        sa.Column(
            "inventory_consumed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("legacy_updated_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("deleted_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_record_factory_legacy",
        ),
    )
    _create_indexes(
        "three_d_printing_production_records",
        (
            "factory_id",
            "legacy_id",
            "business_date",
            "machine_no",
            "status",
            "product_id",
            "product_name",
            "material_name",
            "auto_record",
            "print_start_at",
            "print_end_at",
            "gcode_file",
            "deleted_at",
            "created_at",
            "updated_at",
        ),
    )
    op.create_index(
        "ix_three_d_printing_record_day_machine",
        "three_d_printing_production_records",
        ["factory_id", "business_date", "machine_no"],
    )

    op.create_table(
        "three_d_printing_inventory",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("material_name", sa.String(255), nullable=False),
        sa.Column("stock_g", sa.Numeric(16, 4), nullable=False, server_default="0"),
        sa.Column("min_stock_g", sa.Numeric(16, 4), nullable=False, server_default="3000"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "material_name",
            name="uq_three_d_printing_inventory_factory_material",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_inventory_id_factory",
        ),
    )
    _create_indexes("three_d_printing_inventory", ("factory_id", "material_name"))

    op.create_table(
        "three_d_printing_inventory_movements",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inventory_id", sa.String(96), nullable=False),
        sa.Column("material_name", sa.String(255), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("delta_g", sa.Numeric(16, 4), nullable=False),
        sa.Column("balance_after_g", sa.Numeric(16, 4), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("vendor", sa.String(255), nullable=False, server_default=""),
        sa.Column("cost", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_record_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("legacy_id", sa.String(96), nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["inventory_id", "factory_id"],
            ["three_d_printing_inventory.id", "three_d_printing_inventory.factory_id"],
            name="fk_three_d_printing_movement_inventory_factory",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_movement_factory_legacy",
        ),
    )
    _create_indexes(
        "three_d_printing_inventory_movements",
        (
            "factory_id",
            "inventory_id",
            "material_name",
            "movement_type",
            "business_date",
            "source_record_id",
            "legacy_id",
            "created_at",
        ),
    )

    op.create_table(
        "three_d_printing_schedules",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(96), nullable=True),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("product_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("customer", sa.String(255), nullable=False, server_default=""),
        sa.Column("material_name", sa.String(255), nullable=False),
        sa.Column("weight_g", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("machine_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_schedule_factory_legacy",
        ),
    )
    _create_indexes(
        "three_d_printing_schedules",
        (
            "factory_id",
            "legacy_id",
            "business_date",
            "product_id",
            "product_name",
            "material_name",
            "priority",
            "status",
        ),
    )

    op.create_table(
        "three_d_printing_maintenance",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("legacy_id", sa.String(96), nullable=True),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("machine_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maintenance_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cost", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("vendor", sa.String(255), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_maintenance_factory_legacy",
        ),
    )
    _create_indexes(
        "three_d_printing_maintenance",
        ("factory_id", "legacy_id", "business_date", "machine_no", "maintenance_type"),
    )

    op.create_table(
        "three_d_printing_edge_agents",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="offline"),
        sa.Column("host_fingerprint", sa.String(128), nullable=False, server_default=""),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_seen_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "agent_key",
            name="uq_three_d_printing_agent_factory_key",
        ),
    )
    _create_indexes(
        "three_d_printing_edge_agents",
        ("factory_id", "agent_key", "status", "last_seen_at"),
    )

    op.create_table(
        "three_d_printing_printer_commands",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("printer_id", sa.String(96), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("requested_by_name", sa.String(128), nullable=False),
        sa.Column("requested_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("claimed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("completed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("result_message", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["printer_id", "factory_id"],
            ["three_d_printing_printers.id", "three_d_printing_printers.factory_id"],
            name="fk_three_d_printing_command_printer_factory",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "idempotency_key",
            name="uq_three_d_printing_command_factory_idempotency",
        ),
    )
    _create_indexes(
        "three_d_printing_printer_commands",
        (
            "factory_id",
            "printer_id",
            "action",
            "status",
            "idempotency_key",
            "requested_by",
            "requested_at",
            "expires_at",
            "agent_id",
        ),
    )

    op.create_table(
        "three_d_printing_audit_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("actor_type", sa.String(24), nullable=False, server_default="user"),
        sa.Column("request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
    )
    _create_indexes(
        "three_d_printing_audit_events",
        (
            "factory_id",
            "entity_type",
            "entity_id",
            "action",
            "actor_id",
            "actor_type",
            "created_at",
        ),
    )

    op.create_table(
        "three_d_printing_migration_runs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "factory_id",
            "source_sha256",
            name="uq_three_d_printing_migration_factory_source",
        ),
    )
    _create_indexes(
        "three_d_printing_migration_runs",
        ("factory_id", "source_sha256", "status"),
    )


def _seed_settings() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO three_d_printing_settings (
                factory_id, machine_count, electricity_per_machine_day,
                labor_per_day, material_loss_rate, profit_rate_percent,
                revision, updated_by, updated_by_name, created_at, updated_at
            )
            SELECT
                'huakang-b', 11, 1.5, 220, 1.2, 40,
                1, '', '', '2026-07-29 00:00:00', '2026-07-29 00:00:00'
            WHERE NOT EXISTS (
                SELECT 1
                FROM three_d_printing_settings
                WHERE factory_id = 'huakang-b'
            )
            """
        )
    )
    for machine_no in range(1, 12):
        connection.execute(
            sa.text(
                """
                INSERT INTO three_d_printing_printers (
                    id, factory_id, legacy_id, machine_no, name, printer_type,
                    model, enabled, connected, state, current_file,
                    progress_percent, remaining_minutes, live_material,
                    nozzle_temperature, bed_temperature, error_text,
                    status_payload_json, last_seen_at, revision, created_at, updated_at
                )
                SELECT
                    :id, 'huakang-b', :legacy_id, :machine_no, :name, 'bambu',
                    '', :enabled, :connected, 'OFFLINE', '',
                    0, 0, '', 0, 0, '', '{}', '', 1, :timestamp, :timestamp
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM three_d_printing_printers
                    WHERE factory_id = 'huakang-b' AND machine_no = :machine_no
                )
                """
            ),
            {
                "id": f"3dprinter-huakang-b-{machine_no}",
                "legacy_id": str(machine_no),
                "machine_no": machine_no,
                "name": f"{machine_no}号机",
                "enabled": True,
                "connected": False,
                "timestamp": "2026-07-29 00:00:00",
            },
        )


def _seed_permissions() -> None:
    connection = op.get_bind()
    timestamp = "2026-07-29 00:00:00"
    affected_roles: list[str] = []
    for sort_offset, (code, name, description, access_kind, risk_level) in enumerate(
        PERMISSIONS
    ):
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permissions (id, code, name, description)
                SELECT
                    CAST(:id AS VARCHAR(96)),
                    CAST(:code AS VARCHAR(128)),
                    CAST(:name AS VARCHAR(128)),
                    CAST(:description AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM auth_permissions
                    WHERE code = CAST(:code AS VARCHAR(128))
                )
                """
            ),
            {
                "id": permission_id,
                "code": code,
                "name": name,
                "description": description,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permission_metadata (
                    permission_id, module_code, action, risk_level,
                    access_kind, scope_type, status, sort_order,
                    created_at, updated_at
                )
                SELECT
                    permission.id, 'three_d_printing', :action, :risk_level,
                    :access_kind, 'factory_department', 'active', :sort_order,
                    :timestamp, :timestamp
                FROM auth_permissions permission
                WHERE permission.code = :code
                  AND NOT EXISTS (
                      SELECT 1
                      FROM auth_permission_metadata metadata
                      WHERE metadata.permission_id = permission.id
                  )
                """
            ),
            {
                "code": code,
                "action": code.partition(":")[2],
                "risk_level": risk_level,
                "access_kind": access_kind,
                "sort_order": 900 + sort_offset,
                "timestamp": timestamp,
            },
        )
        if code.endswith(":printer_control"):
            role_ids = CONTROL_ROLE_IDS
        elif code.endswith(":audit_read"):
            role_ids = AUDIT_ROLE_IDS
        else:
            role_ids = OPERATOR_ROLE_IDS
        affected_roles.extend(role_ids)
        for role_id in role_ids:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO auth_role_permissions (id, role_id, permission_id)
                    SELECT :binding_id, role.id, permission.id
                    FROM auth_roles role
                    JOIN auth_permissions permission ON permission.code = :code
                    WHERE role.id = :role_id
                      AND NOT EXISTS (
                          SELECT 1
                          FROM auth_role_permissions binding
                          WHERE binding.role_id = role.id
                            AND binding.permission_id = permission.id
                      )
                    """
                ),
                {
                    "binding_id": f"{role_id}:{permission_id}",
                    "role_id": role_id,
                    "code": code,
                },
            )
    for role_id in dict.fromkeys(affected_roles):
        connection.execute(
            sa.text(
                """
                UPDATE auth_role_metadata
                SET version = version + 1, updated_at = :timestamp
                WHERE role_id = :role_id
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )
        connection.execute(
            sa.text(
                """
                UPDATE auth_user_authorization_revisions
                SET revision = revision + 1, updated_at = :timestamp
                WHERE user_id IN (
                    SELECT user_id
                    FROM auth_user_roles
                    WHERE role_id = :role_id
                )
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )


def _install_audit_immutability() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_three_d_printing_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '3D printing audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_update
            BEFORE UPDATE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_delete
            BEFORE DELETE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
    elif connection.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_update
            BEFORE UPDATE ON three_d_printing_audit_events
            BEGIN
                SELECT RAISE(ABORT, '3D printing audit events are immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_delete
            BEFORE DELETE ON three_d_printing_audit_events
            BEGIN
                SELECT RAISE(ABORT, '3D printing audit events are immutable');
            END
            """
        )


def upgrade() -> None:
    _create_tables()
    _seed_settings()
    _seed_permissions()
    _install_audit_immutability()


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM three_d_printing_migration_runs
            UNION ALL
            SELECT 1
            FROM three_d_printing_production_records
            LIMIT 1
            """
        )
    ).first()
    if populated is not None:
        raise RuntimeError(
            "20260729_0040 cannot be downgraded after 3D printing data exists; "
            "export and back up the domain and image assets first."
        )

    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_update "
            "ON three_d_printing_audit_events"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_delete "
            "ON three_d_printing_audit_events"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS reject_three_d_printing_audit_mutation()"
        )
    elif connection.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_delete")

    for table_name in (
        "three_d_printing_migration_runs",
        "three_d_printing_audit_events",
        "three_d_printing_printer_commands",
        "three_d_printing_edge_agents",
        "three_d_printing_maintenance",
        "three_d_printing_schedules",
        "three_d_printing_inventory_movements",
        "three_d_printing_inventory",
        "three_d_printing_production_records",
        "three_d_printing_day_statuses",
        "three_d_printing_product_images",
        "three_d_printing_printers",
        "three_d_printing_products",
        "three_d_printing_materials",
        "three_d_printing_settings",
    ):
        op.drop_table(table_name)

    permission_ids = sa.text(
        "SELECT id FROM auth_permissions WHERE code LIKE 'three_d_printing:%'"
    )
    for table_name in (
        "auth_user_permission_overrides",
        "auth_role_permissions",
        "auth_permission_metadata",
    ):
        connection.execute(
            sa.text(
                f"DELETE FROM {table_name} "
                f"WHERE permission_id IN ({permission_ids.text})"
            )
        )
    connection.execute(
        sa.text(
            "DELETE FROM auth_permissions WHERE code LIKE 'three_d_printing:%'"
        )
    )
