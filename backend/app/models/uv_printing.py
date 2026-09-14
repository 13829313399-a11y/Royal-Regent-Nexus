"""UV production facts and immutable valuation/identity evidence."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def now():
    return datetime.now(UTC).isoformat()


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    updated_at: Mapped[str] = mapped_column(String(40), default=now)


class UvFactory(Base):
    __tablename__ = "uv_factories"
    factory_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class UvMachine(Record, Base):
    __tablename__ = "uv_machines"
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    brand: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    price_group: Mapped[str | None] = mapped_column(String(64))
    ink_material: Mapped[str] = mapped_column(String(16), default="other")
    admin_status: Mapped[str] = mapped_column(String(16), default="normal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    runtime_status: Mapped[str] = mapped_column(String(16), default="unknown")
    last_heartbeat_at: Mapped[str | None] = mapped_column(String(40))
    current_task_name: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    connector_id: Mapped[str | None] = mapped_column(String(64))
    connector_mode: Mapped[str | None] = mapped_column(String(64))
    capabilities: Mapped[dict] = mapped_column(JSON, default=lambda: dict(progress=False, exact_completion=False, ink_by_color=False, stable_job_id=False))
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("factory_id", "code"),)


class UvProduct(Record, Base):
    __tablename__ = "uv_products"
    product_no: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    external_ref: Mapped[str | None] = mapped_column(String(255))
    external_ref_kind: Mapped[str] = mapped_column(String(16), default="none")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("factory_id", "product_no"),)


class UvProcessVersion(Record, Base):
    __tablename__ = "uv_process_versions"
    product_id: Mapped[str] = mapped_column(ForeignKey("uv_products.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(128))
    effective_from: Mapped[str] = mapped_column(String(10))
    material: Mapped[str] = mapped_column(String(128), default="")
    pieces_per_board: Mapped[int | None] = mapped_column(Integer)
    board_seconds: Mapped[int | None] = mapped_column(Integer)
    width_cm: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    length_cm: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    pricing_area_cm2: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    machine_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    ink_reference_ml: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("product_id", "version_label"), CheckConstraint("pieces_per_board IS NULL OR pieces_per_board > 0"))


class UvRateVersion(Record, Base):
    __tablename__ = "uv_rate_versions"
    rate_kind: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("uv_products.id"))
    process_version_id: Mapped[str | None] = mapped_column(ForeignKey("uv_process_versions.id"))
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("uv_machines.id"))
    price_group: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    effective_from: Mapped[str] = mapped_column(String(10))
    effective_to: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (CheckConstraint("unit_price >= 0"),)


class UvWorker(Record, Base):
    __tablename__ = "uv_workers"
    employee_profile_id: Mapped[str | None] = mapped_column(String(64))
    employee_no: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="operator")
    employ_state: Mapped[str] = mapped_column(String(16), default="active")
    left_on: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("factory_id", "employee_no"),)


class UvShiftTemplate(Record, Base):
    __tablename__ = "uv_shift_templates"
    label: Mapped[str] = mapped_column(String(128))
    shift: Mapped[str] = mapped_column(String(8))
    start_local: Mapped[str] = mapped_column(String(5))
    end_local: Mapped[str] = mapped_column(String(5))
    effective_from: Mapped[str] = mapped_column(String(10))
    effective_to: Mapped[str | None] = mapped_column(String(10))
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")


class UvAssignmentBatch(Record, Base):
    __tablename__ = "uv_assignment_batches"
    business_date: Mapped[str] = mapped_column(String(10))
    shift: Mapped[str] = mapped_column(String(8))
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"))
    __table_args__ = (UniqueConstraint("factory_id", "business_date", "shift", "machine_id"),)


class UvAssignment(Record, Base):
    __tablename__ = "uv_assignments"
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str] = mapped_column(String(8))
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"))
    worker_id: Mapped[str] = mapped_column(ForeignKey("uv_workers.id"))
    share: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=1)
    work_batch: Mapped[str] = mapped_column(ForeignKey("uv_assignment_batches.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UvJob(Record, Base):
    __tablename__ = "uv_jobs"
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"))
    source_job_id: Mapped[str] = mapped_column(String(255))
    source_event_id: Mapped[str] = mapped_column(String(255))
    connector_id: Mapped[str] = mapped_column(String(64))
    generation: Mapped[str] = mapped_column(String(128))
    raw_task_name: Mapped[str] = mapped_column(Text)
    raw_product_name: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("uv_products.id"))
    process_version_id: Mapped[str | None] = mapped_column(ForeignKey("uv_process_versions.id"))
    state: Mapped[str] = mapped_column(String(16), default="observed")
    reconcile_note: Mapped[str] = mapped_column(Text, default="")
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[str | None] = mapped_column(String(40))
    completed_at: Mapped[str | None] = mapped_column(String(40))
    time_evidence: Mapped[str] = mapped_column(String(16), default="unknown")
    raw_count: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    raw_unit: Mapped[str] = mapped_column(String(16), default="unknown")
    suggested_piece_qty: Mapped[int | None] = mapped_column(Integer)
    print_time_seconds: Mapped[int | None] = mapped_column(Integer)
    print_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    ink_total_ml: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    ink_by_color: Mapped[list] = mapped_column(JSON, default=list)
    resolution: Mapped[str | None] = mapped_column(String(64))
    color_count: Mapped[int | None] = mapped_column(Integer)
    duplicate_suspect: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("factory_id", "connector_id", "generation", "source_job_id"),)


class UvReport(Record, Base):
    __tablename__ = "uv_reports"
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str] = mapped_column(String(8))
    shift_template_version_id: Mapped[str] = mapped_column(ForeignKey("uv_shift_templates.id"))
    machine_id: Mapped[str] = mapped_column(ForeignKey("uv_machines.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("uv_products.id"))
    process_version_id: Mapped[str] = mapped_column(ForeignKey("uv_process_versions.id"))
    product_no: Mapped[str] = mapped_column(String(128))
    product_name: Mapped[str] = mapped_column(String(255))
    source_kind: Mapped[str] = mapped_column(String(16), default="manual")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    reported_qty: Mapped[int] = mapped_column(Integer)
    good_qty: Mapped[int] = mapped_column(Integer)
    defective_qty: Mapped[int] = mapped_column(Integer)
    pending_qty: Mapped[int] = mapped_column(Integer)
    semi_finished_qty: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    replaces_report_id: Mapped[str | None] = mapped_column(ForeignKey("uv_reports.id"))
    correction_reason: Mapped[str] = mapped_column(Text, default="")
    confirmed_at: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("reported_qty = good_qty + defective_qty + pending_qty + semi_finished_qty"), CheckConstraint("good_qty >= 0 AND defective_qty >= 0 AND pending_qty >= 0 AND semi_finished_qty >= 0"))


class UvReportWorker(Record, Base):
    __tablename__ = "uv_report_workers"
    report_id: Mapped[str] = mapped_column(ForeignKey("uv_reports.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("uv_workers.id"))
    employee_no: Mapped[str] = mapped_column(String(64))
    worker_name: Mapped[str] = mapped_column(String(128))
    __table_args__ = (UniqueConstraint("report_id", "worker_id"),)


class UvRateSnapshot(Record, Base):
    __tablename__ = "uv_rate_snapshots"
    report_id: Mapped[str] = mapped_column(ForeignKey("uv_reports.id"), index=True)
    rate_kind: Mapped[str] = mapped_column(String(16))
    rate_version_id: Mapped[str | None] = mapped_column(ForeignKey("uv_rate_versions.id"))
    currency: Mapped[str | None] = mapped_column(String(3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    pricing_area_cm2: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    __table_args__ = (UniqueConstraint("report_id", "rate_kind"),)


class UvAllocation(Record, Base):
    __tablename__ = "uv_allocations"
    job_id: Mapped[str] = mapped_column(ForeignKey("uv_jobs.id"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("uv_reports.id"), index=True)
    piece_qty: Mapped[int] = mapped_column(Integer)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("piece_qty > 0"),)


class UvReportEvidence(Record, Base):
    __tablename__ = "uv_report_evidence"
    report_id: Mapped[str] = mapped_column(ForeignKey("uv_reports.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("uv_jobs.id"))
    __table_args__ = (UniqueConstraint("report_id", "job_id"),)


class UvOperation(Record, Base):
    __tablename__ = "uv_operations"
    actor_id: Mapped[str] = mapped_column(String(64))
    operation_id: Mapped[str] = mapped_column(String(128))
    command: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("factory_id", "actor_id", "operation_id"),)
