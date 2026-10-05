"""New spray operations domain. Legacy spray_* tables are deliberately unrelated.

Every reference carries its execution factory. Snapshots describe evidence, never
replace normalized document lines, allocations or stock movements.
"""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

FACTORIES = ("huaxing", "huadeng", "huakang-a", "huakang-b")
QTY = Numeric(20, 6)


def now():
    return datetime.now(UTC).isoformat()


def scoped(*refs, checks=(), unique=()):
    return (
        UniqueConstraint("factory_id", "id"),
        *(ForeignKeyConstraint(["factory_id", field], [f"spray_ops_{table}.factory_id", f"spray_ops_{table}.id"]) for field, table in refs),
        *(CheckConstraint(check) for check in checks),
        *(UniqueConstraint("factory_id", *fields) for fields in unique),
    )


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id: Mapped[str] = mapped_column(ForeignKey("spray_ops_factories.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class SprayOpsFactory(Base):
    __tablename__ = "spray_ops_factories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("id IN ('huaxing','huadeng','huakang-a','huakang-b')"),)


class SprayOpsReceipt(Record, Base):
    __tablename__ = "spray_ops_receipts"
    operation_id: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    # Scope the whole receipt: payroll/cost responses must not leak after revocation.
    required_permissions: Mapped[list] = mapped_column(JSON)
    __table_args__ = scoped(unique=(("operation_id",),))


class SprayOpsAudit(Record, Base):
    __tablename__ = "spray_ops_audit"
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    operation_id: Mapped[str] = mapped_column(String(64))
    # Only structural facts; sensitive payloads stay in permission-scoped documents.
    summary: Mapped[str] = mapped_column(Text)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    __table_args__ = scoped()


class SprayOpsPeriod(Record, Base):
    __tablename__ = "spray_ops_periods"
    month: Mapped[str] = mapped_column(String(7))
    status: Mapped[str] = mapped_column(String(16), default="open")
    frozen_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(unique=(("month",),))


class SprayOpsHistoryPolicy(Record, Base):
    __tablename__ = "spray_ops_history_policies"
    mode: Mapped[str] = mapped_column(String(24))
    cutoff: Mapped[str] = mapped_column(String(10))
    evidence: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(checks=("mode IN ('opening', 'replay')",), unique=((),))


class SprayOpsOpening(Record, Base):
    __tablename__ = "spray_ops_openings"
    document_no: Mapped[str] = mapped_column(String(96))
    business_date: Mapped[str] = mapped_column(String(10))
    line_id: Mapped[str] = mapped_column(String(64))
    stock_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = scoped(("line_id", "demand_lines"), ("stock_id", "stock"), unique=(("document_no",),), checks=("quantity > 0",))


class SprayOpsResource(Record, Base):
    __tablename__ = "spray_ops_resources"
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = scoped(checks=("capacity > 0",), unique=(("code",),))


class SprayOpsCapability(Record, Base):
    __tablename__ = "spray_ops_capabilities"
    resource_id: Mapped[str] = mapped_column(String(64))
    capability: Mapped[str] = mapped_column(String(64))
    # Confirmed process output / hour, no hardcoded shift conversion.
    hourly_capacity: Mapped[Decimal | None] = mapped_column(QTY)
    evidence: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(("resource_id", "resources"), checks=("hourly_capacity IS NULL OR hourly_capacity > 0",), unique=(("resource_id", "capability"),))


class SprayOpsCalendar(Record, Base):
    __tablename__ = "spray_ops_calendars"
    resource_id: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[str] = mapped_column(String(40), index=True)
    end_at: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16), default="available")
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(("resource_id", "resources"), checks=("end_at > start_at",))


class SprayOpsRoute(Record, Base):
    __tablename__ = "spray_ops_routes"
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    evidence: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(unique=(("code", "revision"),))


class SprayOpsStep(Record, Base):
    __tablename__ = "spray_ops_steps"
    route_id: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    capability: Mapped[str] = mapped_column(String(64))
    tool_id: Mapped[str | None] = mapped_column(String(64))
    crew_id: Mapped[str | None] = mapped_column(String(64))
    input_unit: Mapped[str] = mapped_column(String(24))
    output_unit: Mapped[str] = mapped_column(String(24))
    output_ratio: Mapped[Decimal] = mapped_column(QTY, default=1)
    transfer_min: Mapped[Decimal] = mapped_column(QTY, default=1)
    drying_minutes: Mapped[int] = mapped_column(Integer, default=0)
    prep_required: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = scoped(("route_id", "routes"), ("tool_id", "resources"), ("crew_id", "resources"), checks=("output_ratio > 0", "transfer_min > 0", "drying_minutes >= 0"), unique=(("route_id", "code"),))


class SprayOpsPredecessor(Record, Base):
    __tablename__ = "spray_ops_predecessors"
    step_id: Mapped[str] = mapped_column(String(64))
    predecessor_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = scoped(("step_id", "steps"), ("predecessor_id", "steps"), checks=("step_id != predecessor_id",), unique=(("step_id", "predecessor_id"),))


class SprayOpsDemand(Record, Base):
    __tablename__ = "spray_ops_demands"
    document_no: Mapped[str] = mapped_column(String(96))
    counterparty: Mapped[str] = mapped_column(String(128))
    source_factory: Mapped[str | None] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(24), default="manual")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(unique=(("document_no",),))


class SprayOpsDemandLine(Record, Base):
    __tablename__ = "spray_ops_demand_lines"
    demand_id: Mapped[str] = mapped_column(String(64), index=True)
    item_no: Mapped[str] = mapped_column(String(128), index=True)
    part: Mapped[str] = mapped_column(String(128))
    color: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(24))
    expected_arrival: Mapped[str | None] = mapped_column(String(10))
    due_date: Mapped[str] = mapped_column(String(10), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    split_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    route_id: Mapped[str | None] = mapped_column(String(64))
    commercial_price: Mapped[Decimal | None] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    price_evidence: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(("demand_id", "demands"), ("route_id", "routes"), checks=("quantity > 0", "commercial_price IS NULL OR commercial_price >= 0"))


class SprayOpsBatch(Record, Base):
    __tablename__ = "spray_ops_batches"
    kind: Mapped[str] = mapped_column(String(16), default="arrival")
    document_no: Mapped[str] = mapped_column(String(96))
    line_id: Mapped[str | None] = mapped_column(String(64))
    item_no: Mapped[str] = mapped_column(String(128))
    part: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    accepted: Mapped[Decimal] = mapped_column(QTY)
    held: Mapped[Decimal] = mapped_column(QTY, default=0)
    rejected: Mapped[Decimal] = mapped_column(QTY, default=0)
    unit: Mapped[str] = mapped_column(String(24))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = scoped(("line_id", "demand_lines"), checks=("quantity > 0", "accepted >= 0 AND held >= 0 AND rejected >= 0", "quantity = accepted + held + rejected"), unique=(("document_no",),))


class SprayOpsStock(Record, Base):
    __tablename__ = "spray_ops_stock"
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    line_id: Mapped[str | None] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    reserved: Mapped[Decimal] = mapped_column(QTY, default=0)
    unit: Mapped[str] = mapped_column(String(24))
    ready_at: Mapped[str] = mapped_column(String(40))
    pending_step_id: Mapped[str | None] = mapped_column(String(64))
    rework_origin: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("batch_id", "batches"), ("line_id", "demand_lines"), ("pending_step_id", "steps"), ("rework_origin", "stock"), checks=("quantity >= 0", "reserved >= 0 AND reserved <= quantity"))


class SprayOpsCompletedStep(Record, Base):
    __tablename__ = "spray_ops_completed_steps"
    stock_id: Mapped[str] = mapped_column(String(64))
    step_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = scoped(("stock_id", "stock"), ("step_id", "steps"), unique=(("stock_id", "step_id"),))


class SprayOpsPreparation(Record, Base):
    __tablename__ = "spray_ops_preparations"
    batch_id: Mapped[str] = mapped_column(String(64))
    step_id: Mapped[str] = mapped_column(String(64))
    ready_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("batch_id", "batches"), ("step_id", "steps"), unique=(("batch_id", "step_id"),))


class SprayOpsScenario(Record, Base):
    __tablename__ = "spray_ops_scenarios"
    label: Mapped[str] = mapped_column(String(128))
    base_revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    __table_args__ = scoped()


class SprayOpsTask(Record, Base):
    __tablename__ = "spray_ops_tasks"
    scenario_id: Mapped[str | None] = mapped_column(String(64))
    step_id: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    start_at: Mapped[str] = mapped_column(String(40), index=True)
    end_at: Mapped[str] = mapped_column(String(40), index=True)
    actual_start: Mapped[str | None] = mapped_column(String(40))
    actual_end: Mapped[str | None] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    reported: Mapped[Decimal] = mapped_column(QTY, default=0)
    status: Mapped[str] = mapped_column(String(24), default="planned")
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(("scenario_id", "scenarios"), ("step_id", "steps"), ("resource_id", "resources"), checks=("end_at > start_at", "quantity > 0", "reported >= 0 AND reported <= quantity"))


class SprayOpsForecast(Record, Base):
    """Conditional capacity plan: never a physical inventory reservation."""
    __tablename__ = "spray_ops_forecasts"
    line_id: Mapped[str] = mapped_column(String(64))
    step_id: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[str] = mapped_column(String(40), index=True)
    end_at: Mapped[str] = mapped_column(String(40))
    expected_ready_at: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    condition: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="conditional")
    task_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("line_id", "demand_lines"), ("step_id", "steps"), ("resource_id", "resources"), ("task_id", "tasks"), checks=("end_at > start_at", "quantity > 0"))


class SprayOpsTaskAllocation(Record, Base):
    __tablename__ = "spray_ops_task_allocations"
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    stock_id: Mapped[str] = mapped_column(String(64))
    line_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    consumed: Mapped[Decimal] = mapped_column(QTY, default=0)
    __table_args__ = scoped(("task_id", "tasks"), ("stock_id", "stock"), ("line_id", "demand_lines"), checks=("quantity > 0", "consumed >= 0 AND consumed <= quantity"), unique=(("task_id", "stock_id"),))


class SprayOpsReport(Record, Base):
    __tablename__ = "spray_ops_reports"
    document_no: Mapped[str] = mapped_column(String(96))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    correction_of: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("correction_of", "reports"), unique=(("document_no",),))


class SprayOpsReportRow(Record, Base):
    __tablename__ = "spray_ops_report_rows"
    report_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(64))
    processed: Mapped[Decimal] = mapped_column(QTY)
    good: Mapped[Decimal] = mapped_column(QTY)
    hold: Mapped[Decimal] = mapped_column(QTY)
    scrap: Mapped[Decimal] = mapped_column(QTY)
    normal: Mapped[Decimal] = mapped_column(QTY)
    overtime: Mapped[Decimal] = mapped_column(QTY)
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = scoped(("report_id", "reports"), ("task_id", "tasks"), checks=("processed >= 0 AND good >= 0 AND hold >= 0 AND scrap >= 0 AND normal >= 0 AND overtime >= 0", "processed = good + hold + scrap", "processed = normal + overtime"))


class SprayOpsReportAllocation(Record, Base):
    __tablename__ = "spray_ops_report_allocations"
    row_id: Mapped[str] = mapped_column(String(64), index=True)
    task_allocation_id: Mapped[str] = mapped_column(String(64))
    processed: Mapped[Decimal] = mapped_column(QTY)
    good: Mapped[Decimal] = mapped_column(QTY)
    hold: Mapped[Decimal] = mapped_column(QTY)
    scrap: Mapped[Decimal] = mapped_column(QTY)
    normal: Mapped[Decimal] = mapped_column(QTY)
    overtime: Mapped[Decimal] = mapped_column(QTY)
    __table_args__ = scoped(("row_id", "report_rows"), ("task_allocation_id", "task_allocations"), checks=("processed >= 0 AND good >= 0 AND hold >= 0 AND scrap >= 0 AND normal >= 0 AND overtime >= 0", "processed = good + hold + scrap", "processed = normal + overtime"), unique=(("row_id", "task_allocation_id"),))


class SprayOpsEmployee(Record, Base):
    __tablename__ = "spray_ops_employees"
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = scoped(unique=(("code",),))


class SprayOpsLabor(Record, Base):
    __tablename__ = "spray_ops_labor"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    row_id: Mapped[str] = mapped_column(String(64))
    employee_id: Mapped[str] = mapped_column(String(64))
    personal_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    hours: Mapped[Decimal] = mapped_column(QTY)
    overtime_hours: Mapped[Decimal] = mapped_column(QTY, default=0)
    weight: Mapped[Decimal] = mapped_column(QTY, default=1)
    nonproductive_hours: Mapped[Decimal] = mapped_column(QTY, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (*scoped(("row_id", "report_rows"), ("employee_id", "employees"), checks=("hours >= 0 AND overtime_hours >= 0 AND nonproductive_hours >= 0 AND weight > 0", "personal_quantity IS NULL OR personal_quantity >= 0")), Index("uq_spray_ops_current_labor", "factory_id", "row_id", "employee_id", unique=True, sqlite_where=text("active = 1"), postgresql_where=text("active = true")))


class SprayOpsMovement(Record, Base):
    __tablename__ = "spray_ops_movements"
    from_stock_id: Mapped[str | None] = mapped_column(String(64), index=True)
    to_stock_id: Mapped[str | None] = mapped_column(String(64), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    output_quantity: Mapped[Decimal] = mapped_column(QTY)
    kind: Mapped[str] = mapped_column(String(24))
    reference_id: Mapped[str] = mapped_column(String(64), index=True)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    reversal_of: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("from_stock_id", "stock"), ("to_stock_id", "stock"), ("reversal_of", "movements"), checks=("quantity >= 0 AND output_quantity >= 0",))


class SprayOpsDelivery(Record, Base):
    __tablename__ = "spray_ops_deliveries"
    document_no: Mapped[str] = mapped_column(String(96))
    counterparty: Mapped[str] = mapped_column(String(128))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    warehouse_ref: Mapped[str] = mapped_column(String(128), default="")
    __table_args__ = scoped(unique=(("document_no",),))


class SprayOpsDeliveryLine(Record, Base):
    __tablename__ = "spray_ops_delivery_lines"
    delivery_id: Mapped[str] = mapped_column(String(64), index=True)
    stock_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    accepted: Mapped[Decimal] = mapped_column(QTY, default=0)
    rejected: Mapped[Decimal] = mapped_column(QTY, default=0)
    returned: Mapped[Decimal] = mapped_column(QTY, default=0)
    settled: Mapped[Decimal] = mapped_column(QTY, default=0)
    accepted_date: Mapped[str | None] = mapped_column(String(10), index=True)
    price: Mapped[Decimal | None] = mapped_column(QTY)
    price_evidence: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(8))
    __table_args__ = scoped(("delivery_id", "deliveries"), ("stock_id", "stock"), checks=("quantity > 0", "accepted >= 0 AND rejected >= 0 AND accepted + rejected <= quantity", "returned >= 0 AND returned <= accepted", "settled >= 0 AND settled <= accepted", "price IS NULL OR price >= 0"))


class SprayOpsReturn(Record, Base):
    __tablename__ = "spray_ops_returns"
    delivery_line_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("delivery_line_id", "delivery_lines"), checks=("quantity > 0",))


class SprayOpsContainer(Record, Base):
    __tablename__ = "spray_ops_containers"
    counterparty: Mapped[str] = mapped_column(String(128))
    item: Mapped[str] = mapped_column(String(128))
    owner: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(16))
    recoverable: Mapped[bool] = mapped_column(Boolean)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    delivery_id: Mapped[str | None] = mapped_column(String(64))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = scoped(("delivery_id", "deliveries"), checks=("quantity > 0", "owner IN ('ours','theirs')", "direction IN ('in','out')"))


class SprayOpsMaterial(Record, Base):
    __tablename__ = "spray_ops_materials"
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(24))
    __table_args__ = scoped(unique=(("code",),))


class SprayOpsRule(Record, Base):
    __tablename__ = "spray_ops_rules"
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    effective_from: Mapped[str] = mapped_column(String(10))
    effective_until: Mapped[str | None] = mapped_column(String(10))
    parameters: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[str] = mapped_column(Text)
    confirmed_by: Mapped[str | None] = mapped_column(String(64))
    confirmed_at: Mapped[str | None] = mapped_column(String(40))
    material_id: Mapped[str | None] = mapped_column(String(64))
    step_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("material_id", "materials"), ("step_id", "steps"), unique=(("code", "revision"),))


class SprayOpsPurchase(Record, Base):
    __tablename__ = "spray_ops_purchases"
    document_no: Mapped[str] = mapped_column(String(96))
    supplier: Mapped[str] = mapped_column(String(128))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    currency: Mapped[str] = mapped_column(String(8))
    tax_basis: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="ordered")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = scoped(unique=(("document_no",),))


class SprayOpsPurchaseLine(Record, Base):
    __tablename__ = "spray_ops_purchase_lines"
    purchase_id: Mapped[str] = mapped_column(String(64), index=True)
    material_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(24))
    price: Mapped[Decimal | None] = mapped_column(QTY)
    received: Mapped[Decimal] = mapped_column(QTY, default=0)
    cancelled: Mapped[Decimal] = mapped_column(QTY, default=0)
    due_date: Mapped[str] = mapped_column(String(10))
    __table_args__ = scoped(("purchase_id", "purchases"), ("material_id", "materials"), checks=("quantity > 0", "received >= 0 AND cancelled >= 0 AND received + cancelled <= quantity", "price IS NULL OR price >= 0"))


class SprayOpsMaterialReceipt(Record, Base):
    __tablename__ = "spray_ops_material_receipts"
    document_no: Mapped[str] = mapped_column(String(96))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    supplier: Mapped[str] = mapped_column(String(128))
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    __table_args__ = scoped(unique=(("document_no",),))


class SprayOpsMaterialLot(Record, Base):
    __tablename__ = "spray_ops_material_lots"
    receipt_id: Mapped[str] = mapped_column(String(64))
    purchase_line_id: Mapped[str] = mapped_column(String(64))
    material_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    unit: Mapped[str] = mapped_column(String(24))
    unit_cost: Mapped[Decimal | None] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8))
    warehouse: Mapped[Decimal] = mapped_column(QTY)
    floor: Mapped[Decimal] = mapped_column(QTY, default=0)
    consumed: Mapped[Decimal] = mapped_column(QTY, default=0)
    conversion_rule_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = scoped(("receipt_id", "material_receipts"), ("purchase_line_id", "purchase_lines"), ("material_id", "materials"), ("conversion_rule_id", "rules"), checks=("quantity > 0", "warehouse >= 0 AND floor >= 0 AND consumed >= 0", "quantity = warehouse + floor + consumed", "unit_cost IS NULL OR unit_cost >= 0"))


class SprayOpsMaterialMovement(Record, Base):
    __tablename__ = "spray_ops_material_movements"
    lot_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    cost: Mapped[Decimal | None] = mapped_column(QTY)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    line_id: Mapped[str | None] = mapped_column(String(64))
    issue_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("lot_id", "material_lots"), ("line_id", "demand_lines"), ("issue_id", "material_movements"), checks=("quantity > 0",))


class SprayOpsSaving(Record, Base):
    __tablename__ = "spray_ops_savings"
    purchase_line_id: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    old_price: Mapped[Decimal] = mapped_column(QTY)
    new_price: Mapped[Decimal] = mapped_column(QTY)
    signed_difference: Mapped[Decimal] = mapped_column(QTY)
    saving: Mapped[Decimal] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    source_ref: Mapped[str] = mapped_column(String(255))
    __table_args__ = scoped(("purchase_line_id", "purchase_lines"), checks=("quantity > 0 AND old_price >= 0 AND new_price >= 0",))


class SprayOpsPayroll(Record, Base):
    __tablename__ = "spray_ops_payroll"
    document_no: Mapped[str] = mapped_column(String(96))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="trial")
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8))
    __table_args__ = scoped(("rule_id", "rules"), unique=(("document_no",),))


class SprayOpsPayrollLine(Record, Base):
    __tablename__ = "spray_ops_payroll_lines"
    payroll_id: Mapped[str] = mapped_column(String(64))
    employee_id: Mapped[str] = mapped_column(String(64))
    base_amount: Mapped[Decimal] = mapped_column(QTY)
    guarantee: Mapped[Decimal] = mapped_column(QTY)
    subsidy: Mapped[Decimal] = mapped_column(QTY)
    adjustment: Mapped[Decimal] = mapped_column(QTY)
    payroll_amount: Mapped[Decimal] = mapped_column(QTY)
    evidence: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("payroll_id", "payroll"), ("employee_id", "employees"), unique=(("payroll_id", "employee_id"),))


class SprayOpsPayrollAllocation(Record, Base):
    __tablename__ = "spray_ops_payroll_allocations"
    payroll_line_id: Mapped[str] = mapped_column(String(64))
    labor_id: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(64))
    payroll_amount: Mapped[Decimal] = mapped_column(QTY)
    __table_args__ = scoped(("payroll_line_id", "payroll_lines"), ("labor_id", "labor"), ("rule_id", "rules"), unique=(("payroll_line_id", "labor_id"),))


class SprayOpsExpense(Record, Base):
    __tablename__ = "spray_ops_expenses"
    document_no: Mapped[str] = mapped_column(String(96))
    category: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8))
    included: Mapped[bool | None] = mapped_column(Boolean)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    line_id: Mapped[str | None] = mapped_column(String(64))
    evidence: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("line_id", "demand_lines"), checks=("amount >= 0",), unique=(("document_no",),))


class SprayOpsValuation(Record, Base):
    __tablename__ = "spray_ops_valuations"
    report_allocation_id: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    price: Mapped[Decimal] = mapped_column(QTY)
    amount: Mapped[Decimal] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    __table_args__ = scoped(("report_allocation_id", "report_allocations"), ("rule_id", "rules"), unique=(("report_allocation_id",),))


class SprayOpsSettlement(Record, Base):
    __tablename__ = "spray_ops_settlements"
    document_no: Mapped[str] = mapped_column(String(96))
    counterparty: Mapped[str] = mapped_column(String(128))
    month: Mapped[str] = mapped_column(String(7), index=True)
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    rule_id: Mapped[str | None] = mapped_column(String(64))
    total_amount: Mapped[Decimal] = mapped_column(QTY)
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    frozen_snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = scoped(("rule_id", "rules"), unique=(("document_no",),))


class SprayOpsSettlementLine(Record, Base):
    __tablename__ = "spray_ops_settlement_lines"
    settlement_id: Mapped[str] = mapped_column(String(64), index=True)
    delivery_line_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    price: Mapped[Decimal] = mapped_column(QTY)
    amount: Mapped[Decimal] = mapped_column(QTY)
    __table_args__ = scoped(("settlement_id", "settlements"), ("delivery_line_id", "delivery_lines"), checks=("quantity > 0 AND price >= 0",), unique=(("settlement_id", "delivery_line_id"),))


class SprayOpsCredit(Record, Base):
    __tablename__ = "spray_ops_credits"
    return_id: Mapped[str] = mapped_column(String(64))
    settlement_line_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    amount: Mapped[Decimal] = mapped_column(QTY)
    currency: Mapped[str] = mapped_column(String(8))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = scoped(("return_id", "returns"), ("settlement_line_id", "settlement_lines"), checks=("quantity > 0 AND amount >= 0",))


class SprayOpsSource(Record, Base):
    __tablename__ = "spray_ops_sources"
    name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(16))
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    payroll_sensitive: Mapped[bool] = mapped_column(Boolean)
    cost_sensitive: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = scoped(unique=(("sha256",),))


class SprayOpsImport(Record, Base):
    __tablename__ = "spray_ops_imports"
    source_id: Mapped[str] = mapped_column(String(64))
    profile: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="review")
    snapshot: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = scoped(("source_id", "sources"))


class SprayOpsImportFact(Record, Base):
    __tablename__ = "spray_ops_import_facts"
    import_id: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(64))
    fact_category: Mapped[str] = mapped_column(String(64))
    source_key: Mapped[str] = mapped_column(String(255))
    semantic_key: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[dict] = mapped_column(JSON)
    __table_args__ = scoped(("import_id", "imports"), ("source_id", "sources"), unique=(("source_id", "fact_category", "source_key"), ("fact_category", "semantic_key")))


class SprayOpsExport(Record, Base):
    __tablename__ = "spray_ops_exports"
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    required_permissions: Mapped[list] = mapped_column(JSON)
    __table_args__ = scoped()
