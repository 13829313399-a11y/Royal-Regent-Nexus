"""Spray workshop records. Physical stock is owned by the movement ledger."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def now():
    return datetime.now(UTC).isoformat()


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id: Mapped[str] = mapped_column(ForeignKey("spray_factories.factory_id"), index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class SprayFactory(Base):
    __tablename__ = "spray_factories"
    factory_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("factory_id IN ('huaxing','huakang-a','huakang-b','huadeng')"),)


class SprayOrder(Record, Base):
    __tablename__ = "spray_orders"
    document_no: Mapped[str] = mapped_column(String(128))
    customer: Mapped[str] = mapped_column(String(128), index=True)
    customer_factory_id: Mapped[str] = mapped_column(String(32), default="")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    due_date: Mapped[str] = mapped_column(String(10), index=True)
    expected_material_date: Mapped[str] = mapped_column(String(10), default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    close_reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("factory_id", "document_no"),)


class SprayOrderLine(Record, Base):
    __tablename__ = "spray_order_lines"
    order_id: Mapped[str] = mapped_column(ForeignKey("spray_orders.id"), index=True)
    product_no: Mapped[str] = mapped_column(String(128), index=True)
    part_name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(16), default="件")
    per_set: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="HKD")
    price_reference: Mapped[str] = mapped_column(String(255), default="")
    route_version: Mapped[int] = mapped_column(Integer, default=1)
    prep_ready_at: Mapped[str] = mapped_column(String(40), default="")
    prep_reason: Mapped[str] = mapped_column(Text, default="")


class SprayStep(Record, Base):
    __tablename__ = "spray_steps"
    line_id: Mapped[str] = mapped_column(ForeignKey("spray_order_lines.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    capability: Mapped[str] = mapped_column(String(24))
    color: Mapped[str] = mapped_column(String(128), default="")
    wait_hours: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    __table_args__ = (UniqueConstraint("line_id", "sequence"),)


class SprayResource(Record, Base):
    __tablename__ = "spray_resources"
    name: Mapped[str] = mapped_column(String(128))
    capability: Mapped[str] = mapped_column(String(24))
    workers: Mapped[int] = mapped_column(Integer)
    machine_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    person_minutes: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    setup_hours: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    calendar: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("factory_id", "name"),)


class SprayBatch(Record, Base):
    __tablename__ = "spray_batches"
    line_id: Mapped[str] = mapped_column(ForeignKey("spray_order_lines.id"), index=True)
    document_no: Mapped[str] = mapped_column(String(128))
    source_line: Mapped[str] = mapped_column(String(128))
    business_date: Mapped[str] = mapped_column(String(10))
    received: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    __table_args__ = (UniqueConstraint("factory_id", "document_no", "source_line"),)


class SprayMovement(Record, Base):
    __tablename__ = "spray_movements"
    batch_id: Mapped[str] = mapped_column(ForeignKey("spray_batches.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str] = mapped_column(String(128))
    to_state: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    available_at: Mapped[str] = mapped_column(String(40), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("quantity > 0"),)


class SprayTask(Record, Base):
    __tablename__ = "spray_tasks"
    batch_id: Mapped[str] = mapped_column(ForeignKey("spray_batches.id"), index=True)
    step_id: Mapped[str] = mapped_column(ForeignKey("spray_steps.id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("spray_resources.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reported: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    start_at: Mapped[str] = mapped_column(String(40), index=True)
    end_at: Mapped[str] = mapped_column(String(40))
    workers: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="planned")
    input_state: Mapped[str] = mapped_column(String(128))
    duration_source: Mapped[str] = mapped_column(String(128))


class SprayScenario(Record, Base):
    __tablename__ = "spray_scenarios"
    base_revision: Mapped[int] = mapped_column(Integer)
    changes: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="draft")


class SprayReport(Record, Base):
    __tablename__ = "spray_reports"
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str] = mapped_column(String(32))
    team: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    corrected_report_id: Mapped[str | None] = mapped_column(ForeignKey("spray_reports.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class SprayReportLine(Record, Base):
    __tablename__ = "spray_report_lines"
    report_id: Mapped[str] = mapped_column(ForeignKey("spray_reports.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("spray_tasks.id"), nullable=True)
    activity: Mapped[str] = mapped_column(String(128), default="")
    regular_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    overtime_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    good: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    held: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    rework: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    scrap: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    people: Mapped[list] = mapped_column(JSON, default=list)
    wage_status: Mapped[str] = mapped_column(String(24), default="unpriced")
    calculation: Mapped[dict] = mapped_column(JSON, default=dict)


class SprayRate(Record, Base):
    __tablename__ = "spray_rates"
    name: Mapped[str] = mapped_column(String(128))
    rule_code: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(8))
    quantity_basis: Mapped[str] = mapped_column(String(24))
    effective_date: Mapped[str] = mapped_column(String(10))
    parameters: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="provisional")


class SprayShipment(Record, Base):
    __tablename__ = "spray_shipments"
    document_no: Mapped[str] = mapped_column(String(128))
    customer: Mapped[str] = mapped_column(String(128), index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="delivery")
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("factory_id", "document_no"),)


class SprayShipmentLine(Record, Base):
    __tablename__ = "spray_shipment_lines"
    shipment_id: Mapped[str] = mapped_column(ForeignKey("spray_shipments.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("spray_batches.id"))
    original_line_id: Mapped[str | None] = mapped_column(ForeignKey("spray_shipment_lines.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    price_reference: Mapped[str] = mapped_column(String(255))


class SprayReturnable(Record, Base):
    __tablename__ = "spray_returnables"
    customer: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(16))
    document_no: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, default="")


class SpraySettlement(Record, Base):
    __tablename__ = "spray_settlements"
    customer: Mapped[str] = mapped_column(String(128))
    period: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(24), default="confirmed")
    __table_args__ = (UniqueConstraint("factory_id", "customer", "period", "currency"),)


class SpraySettlementLine(Record, Base):
    __tablename__ = "spray_settlement_lines"
    settlement_id: Mapped[str] = mapped_column(ForeignKey("spray_settlements.id"), index=True)
    shipment_line_id: Mapped[str] = mapped_column(ForeignKey("spray_shipment_lines.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class SprayPurchase(Record, Base):
    __tablename__ = "spray_purchases"
    document_no: Mapped[str] = mapped_column(String(128))
    supplier: Mapped[str] = mapped_column(String(128))
    material: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(16))
    base_unit: Mapped[str] = mapped_column(String(16))
    conversion: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    conversion_evidence: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    __table_args__ = (UniqueConstraint("factory_id", "document_no", "material"),)


class SprayMaterialEvent(Record, Base):
    __tablename__ = "spray_material_events"
    purchase_id: Mapped[str] = mapped_column(ForeignKey("spray_purchases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    business_date: Mapped[str] = mapped_column(String(10))
    document_no: Mapped[str] = mapped_column(String(128))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("spray_orders.id"), nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("factory_id", "document_no", "purchase_id", "kind"),)


class SprayImport(Record, Base):
    __tablename__ = "spray_imports"
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    format: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="preview")
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("factory_id", "sha256"),)


class SprayImportRow(Record, Base):
    __tablename__ = "spray_import_rows"
    import_id: Mapped[str] = mapped_column(ForeignKey("spray_imports.id"), index=True)
    sheet: Mapped[str] = mapped_column(String(128))
    row_number: Mapped[int] = mapped_column(Integer)
    cells: Mapped[dict] = mapped_column(JSON)
    role: Mapped[str] = mapped_column(String(32), default="historical_review")
    status: Mapped[str] = mapped_column(String(32), default="pending")


class SprayOperation(Record, Base):
    __tablename__ = "spray_operations"
    operation_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("factory_id", "operation_id"),)


# Composite foreign keys enforce the same factory even for direct SQL writers.
for _table in list(Base.metadata.tables.values()):
    if _table.name.startswith("spray_") and "id" in _table.c:
        _table.append_constraint(UniqueConstraint("id", "factory_id"))
        for _fk in list(_table.foreign_keys):
            if _fk.target_fullname.endswith(".id"):
                _table.append_constraint(ForeignKeyConstraint(
                    [_fk.parent.name, "factory_id"],
                    [_fk.target_fullname, _fk.target_fullname.rsplit(".", 1)[0] + ".factory_id"],
                ))
