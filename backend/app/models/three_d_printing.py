from sqlalchemy import (
    Boolean,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ThreeDPrintingSetting(Base):
    __tablename__ = "three_d_printing_settings"

    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_count: Mapped[int] = mapped_column(Integer, default=11)
    electricity_per_machine_day: Mapped[float] = mapped_column(Numeric(14, 4), default=1.5)
    labor_per_day: Mapped[float] = mapped_column(Numeric(14, 4), default=220)
    material_loss_rate: Mapped[float] = mapped_column(Numeric(10, 4), default=1.2)
    profit_rate_percent: Mapped[float] = mapped_column(Numeric(10, 4), default=40)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingMaterial(Base):
    __tablename__ = "three_d_printing_materials"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "name",
            name="uq_three_d_printing_material_factory_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    material_type: Mapped[str] = mapped_column(String(64), default="")
    price_per_kg: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingProduct(Base):
    __tablename__ = "three_d_printing_products"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_product_id_factory",
        ),
        Index(
            "ix_three_d_printing_product_search",
            "factory_id",
            "name",
            "customer",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    customer: Mapped[str] = mapped_column(String(255), default="", index=True)
    material_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    weight_g: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    duration_hours: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    default_quantity: Mapped[int] = mapped_column(Integer, default=1)
    quoted_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingProductImage(Base):
    __tablename__ = "three_d_printing_product_images"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "factory_id"],
            [
                "three_d_printing_products.id",
                "three_d_printing_products.factory_id",
            ],
            name="fk_three_d_printing_image_product_factory",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_image_id_factory",
        ),
        UniqueConstraint("product_id", name="uq_three_d_printing_product_image"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    original_file_name: Mapped[str] = mapped_column(String(255), default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="")
    uploaded_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class ThreeDPrintingPrinter(Base):
    __tablename__ = "three_d_printing_printers"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "machine_no",
            name="uq_three_d_printing_printer_factory_machine",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_printer_id_factory",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    machine_no: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128))
    printer_type: Mapped[str] = mapped_column(String(64), default="bambu")
    model: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    state: Mapped[str] = mapped_column(String(32), default="OFFLINE", index=True)
    current_file: Mapped[str] = mapped_column(String(512), default="")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    remaining_minutes: Mapped[int] = mapped_column(Integer, default=0)
    live_material: Mapped[str] = mapped_column(String(255), default="")
    nozzle_temperature: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    bed_temperature: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    error_text: Mapped[str] = mapped_column(Text, default="")
    status_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    last_seen_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingDayStatus(Base):
    __tablename__ = "three_d_printing_day_statuses"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "business_date",
            name="uq_three_d_printing_day_factory_date",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingProductionRecord(Base):
    __tablename__ = "three_d_printing_production_records"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_record_factory_legacy",
        ),
        Index(
            "ix_three_d_printing_record_day_machine",
            "factory_id",
            "business_date",
            "machine_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    machine_no: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    product_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    material_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    weight_g: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    duration_hours: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    design_fee: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    quoted_price: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    customer: Mapped[str] = mapped_column(String(255), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    auto_record: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    print_start_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    print_end_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    gcode_file: Mapped[str] = mapped_column(String(512), default="", index=True)
    inventory_consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    legacy_updated_at: Mapped[str] = mapped_column(String(32), default="")
    deleted_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class ThreeDPrintingInventory(Base):
    __tablename__ = "three_d_printing_inventory"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "material_name",
            name="uq_three_d_printing_inventory_factory_material",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_three_d_printing_inventory_id_factory",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str] = mapped_column(String(255), index=True)
    stock_g: Mapped[float] = mapped_column(Numeric(16, 4), default=0)
    min_stock_g: Mapped[float] = mapped_column(Numeric(16, 4), default=3000)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingInventoryMovement(Base):
    __tablename__ = "three_d_printing_inventory_movements"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_movement_factory_legacy",
        ),
        ForeignKeyConstraint(
            ["inventory_id", "factory_id"],
            [
                "three_d_printing_inventory.id",
                "three_d_printing_inventory.factory_id",
            ],
            name="fk_three_d_printing_movement_inventory_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    inventory_id: Mapped[str] = mapped_column(String(96), index=True)
    material_name: Mapped[str] = mapped_column(String(255), index=True)
    movement_type: Mapped[str] = mapped_column(String(32), index=True)
    delta_g: Mapped[float] = mapped_column(Numeric(16, 4))
    balance_after_g: Mapped[float] = mapped_column(Numeric(16, 4))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    vendor: Mapped[str] = mapped_column(String(255), default="")
    cost: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    remark: Mapped[str] = mapped_column(Text, default="")
    source_record_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), default="")
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class ThreeDPrintingSchedule(Base):
    __tablename__ = "three_d_printing_schedules"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_schedule_factory_legacy",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    product_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    customer: Mapped[str] = mapped_column(String(255), default="")
    material_name: Mapped[str] = mapped_column(String(255), index=True)
    weight_g: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    machine_no: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingMaintenance(Base):
    __tablename__ = "three_d_printing_maintenance"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "legacy_id",
            name="uq_three_d_printing_maintenance_factory_legacy",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    machine_no: Mapped[int] = mapped_column(Integer, default=0, index=True)
    maintenance_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    cost: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    vendor: Mapped[str] = mapped_column(String(255), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingEdgeAgent(Base):
    __tablename__ = "three_d_printing_edge_agents"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "agent_key",
            name="uq_three_d_printing_agent_factory_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_key: Mapped[str] = mapped_column(String(96), index=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="offline", index=True)
    host_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    last_seen_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class ThreeDPrintingPrinterCommand(Base):
    __tablename__ = "three_d_printing_printer_commands"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "idempotency_key",
            name="uq_three_d_printing_command_factory_idempotency",
        ),
        ForeignKeyConstraint(
            ["printer_id", "factory_id"],
            [
                "three_d_printing_printers.id",
                "three_d_printing_printers.factory_id",
            ],
            name="fk_three_d_printing_command_printer_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    printer_id: Mapped[str] = mapped_column(String(96), index=True)
    action: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(64), index=True)
    requested_by_name: Mapped[str] = mapped_column(String(128))
    requested_at: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
    agent_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    claimed_at: Mapped[str] = mapped_column(String(32), default="")
    completed_at: Mapped[str] = mapped_column(String(32), default="")
    result_message: Mapped[str] = mapped_column(Text, default="")


class ThreeDPrintingAuditEvent(Base):
    __tablename__ = "three_d_printing_audit_events"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    actor_type: Mapped[str] = mapped_column(String(24), default="user", index=True)
    request_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class ThreeDPrintingMigrationRun(Base):
    __tablename__ = "three_d_printing_migration_runs"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "source_sha256",
            name="uq_three_d_printing_migration_factory_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), index=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[str] = mapped_column(String(32), default="")
