from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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


class ThreeDPrintingOperationsItem(Base):
    """Versioned typed resource documents; validated by the operations domain schemas."""
    __tablename__ = "three_d_printing_operations_items"
    __table_args__ = (
        CheckConstraint("factory_id = 'huakang-a'", name="ck_3d_ops_factory"),
        CheckConstraint("kind IN ('spool','request','file_alias','profile','file','run_evidence')", name="ck_3d_ops_kind"),
        CheckConstraint("length(data_json) <= 16384", name="ck_3d_ops_payload"),
        UniqueConstraint("factory_id", "kind", "resource_key", name="uq_3d_ops_resource"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    resource_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(96))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


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
        Index("uq_3d_material_id_factory", "id", "factory_id", unique=True),
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
    legacy_sha256: Mapped[str] = mapped_column(String(64), default="")
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
    site_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
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
        ForeignKeyConstraint(["site_id", "factory_id"], ["three_d_printing_sites.id", "three_d_printing_sites.factory_id"], name="fk_3d_record_site", ondelete="RESTRICT"),
        ForeignKeyConstraint(["migration_batch_id", "factory_id"], ["three_d_printing_migration_batches.id", "three_d_printing_migration_batches.factory_id"], name="fk_3d_record_batch", ondelete="RESTRICT"),
        UniqueConstraint("factory_id", "device_job_key", name="uq_3d_record_device_job"),
        CheckConstraint("run_status IN ('pending','running','paused','succeeded','failed','cancelled','unknown')", name="ck_3d_record_run_status"),
        CheckConstraint("reconciliation_status IN ('none','pending','resolved')", name="ck_3d_record_reconciliation"),
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
    site_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    device_job_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    legacy_status: Mapped[str] = mapped_column(String(32), default="")
    run_status: Mapped[str] = mapped_column(String(24), default="unknown")
    reconciliation_status: Mapped[str] = mapped_column(String(24), default="none")
    data_quality_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    product_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    cost_profile_version: Mapped[str] = mapped_column(String(64), default="")
    calculated_cost_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    migration_batch_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), default="nexus")
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
        Index("uq_3d_movement_id_factory", "id", "factory_id", unique=True),
        ForeignKeyConstraint(["migration_batch_id", "factory_id"], ["three_d_printing_migration_batches.id", "three_d_printing_migration_batches.factory_id"], name="fk_3d_movement_batch", ondelete="RESTRICT"),
        ForeignKeyConstraint(["reversal_of_movement_id", "factory_id"], ["three_d_printing_inventory_movements.id", "three_d_printing_inventory_movements.factory_id"], name="fk_3d_movement_reversal", ondelete="RESTRICT", use_alter=True),
        ForeignKeyConstraint(["source_event_id", "factory_id"], ["three_d_printing_printer_state_events.id", "three_d_printing_printer_state_events.factory_id"], name="fk_3d_movement_event", ondelete="RESTRICT"),
        UniqueConstraint("factory_id", "idempotency_key", name="uq_3d_movement_idempotency"),
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
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    movement_status: Mapped[str] = mapped_column(String(24), default="posted")
    reversal_of_movement_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    migration_batch_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    raw_material_name: Mapped[str] = mapped_column(String(255), default="")
    affects_balance: Mapped[bool] = mapped_column(Boolean, default=True)
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
        ForeignKeyConstraint(["connector_instance_id", "factory_id"], ["three_d_printing_connector_instances.id", "three_d_printing_connector_instances.factory_id"], name="fk_3d_command_connector", ondelete="RESTRICT"),
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
    connector_instance_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    lease_id: Mapped[str] = mapped_column(String(96), default="")
    leased_until: Mapped[str] = mapped_column(String(32), default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[str] = mapped_column(String(32), default="")
    result_evidence_json: Mapped[str] = mapped_column(Text, default="{}")


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


class ThreeDPrintingSite(Base):
    __tablename__ = "three_d_printing_sites"
    __table_args__ = (
        CheckConstraint("factory_id = 'huakang-a'", name="ck_3d_site_factory"),
        UniqueConstraint("id", "factory_id", name="uq_3d_site_id_factory"),
        UniqueConstraint("factory_id", "site_code", name="uq_3d_site_code"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    site_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class ThreeDPrintingNetworkGateway(Base):
    __tablename__ = "three_d_printing_network_gateways"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "factory_id"], ["three_d_printing_sites.id", "three_d_printing_sites.factory_id"], name="fk_3d_gateway_site", ondelete="RESTRICT"),
        UniqueConstraint("factory_id", "gateway_key", name="uq_3d_gateway_key"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str] = mapped_column(String(96))
    gateway_key: Mapped[str] = mapped_column(String(96))
    vpn_type: Mapped[str] = mapped_column(String(24))
    advertised_cidr: Mapped[str] = mapped_column(String(128), default="")
    tunnel_address: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(24), default="unknown")
    last_handshake_at: Mapped[str] = mapped_column(String(32), default="")
    latency_ms: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    packet_loss_percent: Mapped[float] = mapped_column(Numeric(10, 4), default=0)
    config_revision: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(String(255), default="")


class ThreeDPrintingConnectorInstance(Base):
    __tablename__ = "three_d_printing_connector_instances"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "factory_id"], ["three_d_printing_sites.id", "three_d_printing_sites.factory_id"], name="fk_3d_connector_site", ondelete="RESTRICT"),
        UniqueConstraint("id", "factory_id", name="uq_3d_connector_id_factory"),
        UniqueConstraint("site_id", "instance_id", name="uq_3d_connector_instance"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str] = mapped_column(String(96))
    connector_key: Mapped[str] = mapped_column(String(96))
    instance_id: Mapped[str] = mapped_column(String(96))
    version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="offline")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[str] = mapped_column(String(32), default="")
    last_seen_at: Mapped[str] = mapped_column(String(32), default="")
    leader_printer_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(255), default="")


class ThreeDPrintingPrinterConnection(Base):
    """Restricted infrastructure metadata; serial/access codes live in Secret Store."""
    __tablename__ = "three_d_printing_printer_connections"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "factory_id"], ["three_d_printing_sites.id", "three_d_printing_sites.factory_id"], name="fk_3d_connection_site", ondelete="RESTRICT"),
        ForeignKeyConstraint(["printer_id", "factory_id"], ["three_d_printing_printers.id", "three_d_printing_printers.factory_id"], name="fk_3d_connection_printer", ondelete="RESTRICT"),
        CheckConstraint("mqtt_port BETWEEN 1 AND 65535", name="ck_3d_connection_port"),
    )
    printer_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str] = mapped_column(String(96))
    lan_host: Mapped[str] = mapped_column(String(255))
    mqtt_port: Mapped[int] = mapped_column(Integer, default=8883)
    credential_ref: Mapped[str] = mapped_column(String(255))
    certificate_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    connection_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    connection_revision: Mapped[int] = mapped_column(Integer, default=1)
    connection_owner: Mapped[str] = mapped_column(String(24), default="edge-legacy")
    # Recording a finished print is deliberately independent of connection ownership:
    # an observer connection may settle runs while hardware control stays refused.
    record_reconcile_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    leader_instance_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    leader_lease_id: Mapped[str] = mapped_column(String(96), default="")
    leader_leased_until: Mapped[str] = mapped_column(String(32), default="")
    last_connect_at: Mapped[str] = mapped_column(String(32), default="")
    last_disconnect_at: Mapped[str] = mapped_column(String(32), default="")


class ThreeDPrintingPrinterStateEvent(Base):
    __tablename__ = "three_d_printing_printer_state_events"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_3d_event_id_factory"),
        UniqueConstraint("printer_id", "connection_session_id", "sequence", name="uq_3d_event_session_sequence"),
        ForeignKeyConstraint(["printer_id", "factory_id"], ["three_d_printing_printers.id", "three_d_printing_printers.factory_id"], name="fk_3d_event_printer", ondelete="RESTRICT"),
        ForeignKeyConstraint(["connector_instance_id", "factory_id"], ["three_d_printing_connector_instances.id", "three_d_printing_connector_instances.factory_id"], name="fk_3d_event_connector", ondelete="RESTRICT"),
        Index("ix_3d_event_printer_observed", "factory_id", "printer_id", "observed_at"),
        Index("ix_3d_event_analytics", "factory_id", "machine_no", "observed_at",
              postgresql_include=["state", "error_code", "temperatures_json"]),
        CheckConstraint("sequence >= 0", name="ck_3d_event_sequence"),
        CheckConstraint("length(raw_payload_json) <= 65536", name="ck_3d_event_payload_limit"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    connector_instance_id: Mapped[str] = mapped_column(String(96))
    printer_id: Mapped[str] = mapped_column(String(96))
    machine_no: Mapped[int] = mapped_column(Integer)
    connection_session_id: Mapped[str] = mapped_column(String(96))
    sequence: Mapped[int] = mapped_column(BigInteger)
    observed_at: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    remaining_minutes: Mapped[int] = mapped_column(Integer, default=0)
    current_file: Mapped[str] = mapped_column(String(512), default="")
    temperatures_json: Mapped[str] = mapped_column(Text, default="{}")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_text: Mapped[str] = mapped_column(String(255), default="")
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    raw_payload_json: Mapped[str] = mapped_column(Text, default="{}")


class ThreeDPrintingTelemetryRollup(Base):
    __tablename__ = "three_d_printing_telemetry_rollups"
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket_start: Mapped[str] = mapped_column(String(32), primary_key=True)
    dirty: Mapped[bool] = mapped_column(Boolean, default=True)
    counters_json: Mapped[str] = mapped_column(Text, default="{}")
    calculated_at: Mapped[str] = mapped_column(String(32), default="")


class ThreeDPrintingTelemetryRollupState(Base):
    __tablename__ = "three_d_printing_telemetry_rollup_state"
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    initialized_at: Mapped[str] = mapped_column(String(32), default="")


class ThreeDPrintingMaterialAlias(Base):
    __tablename__ = "three_d_printing_material_aliases"
    __table_args__ = (
        ForeignKeyConstraint(["canonical_material_id", "factory_id"], ["three_d_printing_materials.id", "three_d_printing_materials.factory_id"], name="fk_3d_alias_material", ondelete="RESTRICT"),
        CheckConstraint("factory_id = 'huakang-a'", name="ck_3d_alias_factory"),
        UniqueConstraint("factory_id", "raw_name", name="uq_3d_alias_raw_name"),
        Index("ix_3d_alias_normalized", "factory_id", "normalized_name"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    raw_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255))
    canonical_material_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="legacy")
    approved_by: Mapped[str] = mapped_column(String(96), default="")
    approved_at: Mapped[str] = mapped_column(String(32), default="")


class ThreeDPrintingMigrationBatch(Base):
    __tablename__ = "three_d_printing_migration_batches"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_3d_batch_id_factory"),
        UniqueConstraint("factory_id", "site_id", "source_system", "source_sha256", name="uq_3d_batch_source"),
        ForeignKeyConstraint(["site_id", "factory_id"], ["three_d_printing_sites.id", "three_d_printing_sites.factory_id"], name="fk_3d_batch_site", ondelete="RESTRICT"),
        CheckConstraint("status IN ('analyzed','dry_run','importing','imported','reconciled','failed','rolled_back')", name="ck_3d_batch_status"),
        Index("ix_3d_batch_source_updated", "factory_id", "site_id", "source_system", "source_updated_at_ms"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str] = mapped_column(String(96))
    source_system: Mapped[str] = mapped_column(String(64))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_updated_at_ms: Mapped[int] = mapped_column(BigInteger)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    image_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    migration_version: Mapped[str] = mapped_column(String(64))
    code_revision: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="analyzed")
    expected_counts_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    reconciliation_json: Mapped[str] = mapped_column(Text, default="{}")
    checkpoint_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[str] = mapped_column(String(32))
    completed_at: Mapped[str] = mapped_column(String(32), default="")
    lease_id: Mapped[str] = mapped_column(String(96), default="")
    leased_until: Mapped[str] = mapped_column(String(32), default="")
    error_code: Mapped[str] = mapped_column(String(64), default="")


class ThreeDPrintingMigrationRowResult(Base):
    __tablename__ = "three_d_printing_migration_row_results"
    __table_args__ = (
        ForeignKeyConstraint(["batch_id", "factory_id"], ["three_d_printing_migration_batches.id", "three_d_printing_migration_batches.factory_id"], name="fk_3d_row_batch", ondelete="RESTRICT"),
        UniqueConstraint("batch_id", "entity_type", "legacy_id", name="uq_3d_row_source"),
        Index("ix_3d_row_target", "factory_id", "entity_type", "target_id"),
        Index("ix_3d_row_batch_status", "batch_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(96))
    entity_type: Mapped[str] = mapped_column(String(64))
    legacy_id: Mapped[str] = mapped_column(String(255))
    target_id: Mapped[str] = mapped_column(String(96), default="")
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    target_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(32))
