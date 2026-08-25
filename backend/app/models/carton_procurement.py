from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CartonCustomer(Base):
    __tablename__ = "carton_customers"
    __table_args__ = (
        UniqueConstraint("factory_id", "customer_code", name="uq_carton_customer_factory_code"),
        UniqueConstraint("id", "factory_id", name="uq_carton_customer_id_factory"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_carton_customer_status"),
        CheckConstraint("revision >= 1", name="ck_carton_customer_revision"),
        Index("ix_carton_customer_factory_status_name", "factory_id", "status", "customer_name"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    country_region: Mapped[str] = mapped_column(String(128), default="")
    contact_name: Mapped[str] = mapped_column(String(128), default="")
    contact_phone: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)


class CartonSupplier(Base):
    __tablename__ = "carton_suppliers"
    __table_args__ = (
        UniqueConstraint("factory_id", "supplier_code", name="uq_carton_supplier_factory_code"),
        UniqueConstraint("id", "factory_id", name="uq_carton_supplier_id_factory"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    supplier_code: Mapped[str] = mapped_column(String(64), index=True)
    supplier_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CartonOrder(Base):
    __tablename__ = "carton_orders"
    __table_args__ = (
        UniqueConstraint("factory_id", "order_no", name="uq_carton_order_factory_no"),
        UniqueConstraint("id", "factory_id", name="uq_carton_order_id_factory"),
        CheckConstraint("product_order_quantity > 0", name="ck_carton_order_product_quantity"),
        CheckConstraint("revision >= 1", name="ck_carton_order_revision"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_SUPPLIER', 'CONFIRMED', "
            "'PARTIALLY_RECEIVED', 'COMPLETED', 'CANCELLED')",
            name="ck_carton_order_status",
        ),
        Index("ix_carton_order_factory_customer_due", "factory_id", "customer_code", "due_date"),
        Index("ix_carton_order_factory_contract_item", "factory_id", "contract_no", "item_no"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_no: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96), index=True)
    supplier_name_snapshot: Mapped[str] = mapped_column(String(255))
    contract_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    product_order_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    order_date: Mapped[str] = mapped_column(String(10), index=True)
    due_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)


class CartonOrderLine(Base):
    __tablename__ = "carton_order_lines"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_order_line_id_factory"),
        UniqueConstraint("order_id", "line_no", name="uq_carton_order_line_order_no"),
        ForeignKeyConstraint(
            ["order_id", "factory_id"],
            ["carton_orders.id", "carton_orders.factory_id"],
            name="fk_carton_order_line_order_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint("line_no >= 1", name="ck_carton_order_line_no"),
        CheckConstraint("usage_quantity > 0", name="ck_carton_order_line_usage"),
        CheckConstraint("required_quantity > 0", name="ck_carton_order_line_required"),
        CheckConstraint("unit_price >= 0", name="ck_carton_order_line_unit_price"),
        Index("ix_carton_order_line_factory_item", "factory_id", "item_no"),
        Index(
            "ix_carton_order_line_inventory_key",
            "factory_id",
            "customer_code",
            "packaging_type",
            "paper_quality",
            "specification",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    contract_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), index=True)
    packaging_type: Mapped[str] = mapped_column(String(64), index=True)
    paper_quality: Mapped[str] = mapped_column(String(128), index=True)
    specification: Mapped[str] = mapped_column(String(255), index=True)
    dimension_unit: Mapped[str] = mapped_column(String(16), default="")
    # 兼容历史数据库列名；自迁移 20260818_0079 起保存“每箱个数”。
    usage_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    required_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    price_source: Mapped[str] = mapped_column(String(128), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")


class CartonImportBatch(Base):
    __tablename__ = "carton_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "factory_id", "import_type", "source_sha256", "import_profile",
            name="uq_carton_import_factory_type_hash",
        ),
        CheckConstraint(
            "import_type IN ('DELIVERY_NOTE', 'WEEKLY_SCHEDULE', 'INSPECTION_SCHEDULE')",
            name="ck_carton_import_type",
        ),
        CheckConstraint(
            "status IN ('REQUIRES_REVIEW', 'CONFIRMED', 'REJECTED')",
            name="ck_carton_import_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    import_profile: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    source_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="REQUIRES_REVIEW", index=True)
    parse_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    imported_by: Mapped[str] = mapped_column(String(64), index=True)
    imported_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class CartonReceipt(Base):
    __tablename__ = "carton_receipts"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_receipt_id_factory"),
        UniqueConstraint(
            "factory_id", "supplier_id", "delivery_note_no",
            name="uq_carton_receipt_delivery_note",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_CONFIRMATION', 'POSTED', 'REVERSED')",
            name="ck_carton_receipt_status",
        ),
        CheckConstraint("revision >= 1", name="ck_carton_receipt_revision"),
        Index("ix_carton_receipt_factory_delivery_date", "factory_id", "delivery_date"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    receipt_no: Mapped[str] = mapped_column(String(64), index=True)
    delivery_note_no: Mapped[str] = mapped_column(String(128), index=True)
    delivery_date: Mapped[str] = mapped_column(String(10), index=True)
    supplier_id: Mapped[str] = mapped_column(String(96), index=True)
    supplier_name_snapshot: Mapped[str] = mapped_column(String(255))
    import_batch_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    confirmed_at: Mapped[str] = mapped_column(String(40), default="", index=True)


class CartonReceiptLine(Base):
    __tablename__ = "carton_receipt_lines"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_receipt_line_id_factory"),
        UniqueConstraint("receipt_id", "line_no", name="uq_carton_receipt_line_receipt_no"),
        ForeignKeyConstraint(
            ["receipt_id", "factory_id"],
            ["carton_receipts.id", "carton_receipts.factory_id"],
            name="fk_carton_receipt_line_receipt_factory",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "factory_id"],
            ["carton_order_lines.id", "carton_order_lines.factory_id"],
            name="fk_carton_receipt_line_order_line_factory",
        ),
        CheckConstraint("line_no >= 1", name="ck_carton_receipt_line_no"),
        CheckConstraint(
            "delivered_quantity >= 0 AND received_quantity >= 0 AND "
            "damaged_quantity >= 0 AND rejected_quantity >= 0 AND unusable_quantity >= 0",
            name="ck_carton_receipt_line_quantities",
        ),
        CheckConstraint("effective_quantity >= 0", name="ck_carton_receipt_line_effective"),
        CheckConstraint("unit_price >= 0", name="ck_carton_receipt_line_price"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    receipt_id: Mapped[str] = mapped_column(String(96), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    order_line_id: Mapped[str] = mapped_column(String(96), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    contract_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), index=True)
    packaging_type: Mapped[str] = mapped_column(String(64), index=True)
    paper_quality: Mapped[str] = mapped_column(String(128), index=True)
    specification: Mapped[str] = mapped_column(String(255), index=True)
    delivered_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    damaged_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    unusable_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0))
    effective_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    location: Mapped[str] = mapped_column(String(128), default="")
    feedback_note: Mapped[str] = mapped_column(Text, default="")


class CartonInventoryMovement(Base):
    __tablename__ = "carton_inventory_movements"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_movement_id_factory"),
        UniqueConstraint(
            "factory_id", "source_type", "source_line_id",
            name="uq_carton_movement_source_line",
        ),
        Index(
            "uq_carton_movement_one_reversal",
            "reversal_of_movement_id",
            unique=True,
            sqlite_where=text("reversal_of_movement_id IS NOT NULL"),
            postgresql_where=text("reversal_of_movement_id IS NOT NULL"),
        ),
        CheckConstraint(
            "movement_type IN ('INBOUND', 'OUTBOUND', 'ADJUSTMENT', 'REVERSAL')",
            name="ck_carton_movement_type",
        ),
        CheckConstraint("quantity <> 0", name="ck_carton_movement_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_carton_movement_price"),
        Index(
            "ix_carton_movement_inventory_key_time",
            "factory_id", "customer_code", "item_no", "packaging_type", "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_line_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    contract_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), index=True)
    packaging_type: Mapped[str] = mapped_column(String(64), index=True)
    paper_quality: Mapped[str] = mapped_column(String(128), index=True)
    specification: Mapped[str] = mapped_column(String(255), index=True)
    movement_type: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    location: Mapped[str] = mapped_column(String(128), default="")
    document_no: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(96), index=True)
    source_line_id: Mapped[str] = mapped_column(String(96), index=True)
    reversal_of_movement_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_user_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    occurred_at: Mapped[str] = mapped_column(String(40), index=True)


class CartonClosing(Base):
    __tablename__ = "carton_closings"
    __table_args__ = (
        UniqueConstraint(
            "factory_id", "period", "customer_code", "currency",
            name="uq_carton_closing_factory_period_customer_currency",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING', 'CONFIRMED', 'LOCKED')",
            name="ck_carton_closing_status",
        ),
        CheckConstraint("revision >= 1", name="ck_carton_closing_revision"),
        Index("ix_carton_closing_factory_period_status", "factory_id", "period", "status"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(255))
    opening_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    inbound_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    outbound_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    adjustment_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    ending_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    ending_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(8), default="CNY", index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    generated_by: Mapped[str] = mapped_column(String(64), index=True)
    generated_by_name: Mapped[str] = mapped_column(String(128), default="")
    generated_at: Mapped[str] = mapped_column(String(40), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(64), default="")
    confirmed_at: Mapped[str] = mapped_column(String(40), default="")
    locked_by: Mapped[str] = mapped_column(String(64), default="")
    locked_at: Mapped[str] = mapped_column(String(40), default="")


class CartonException(Base):
    __tablename__ = "carton_exceptions"
    __table_args__ = (
        UniqueConstraint("factory_id", "exception_no", name="uq_carton_exception_factory_no"),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_carton_exception_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')",
            name="ck_carton_exception_status",
        ),
        CheckConstraint("revision >= 1", name="ck_carton_exception_revision"),
        Index("ix_carton_exception_factory_status", "factory_id", "status", "severity"),
        Index("ix_carton_exception_source", "factory_id", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    exception_no: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(96), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    customer_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    contract_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    item_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_department: Mapped[str] = mapped_column(String(128), default="纸箱下单")
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
    resolved_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    resolved_by_name: Mapped[str] = mapped_column(String(128), default="")
    resolved_at: Mapped[str] = mapped_column(String(40), default="", index=True)


class CartonAuditEvent(Base):
    __tablename__ = "carton_audit_events"
    __table_args__ = (
        Index("ix_carton_audit_factory_sequence", "factory_id", "sequence"),
        Index("ix_carton_audit_entity", "factory_id", "entity_type", "entity_id"),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(96), unique=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_user_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
