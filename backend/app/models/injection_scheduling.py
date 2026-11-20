"""V3 relational business records; legacy table families remain retired."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

FACTORY_CHECK = "factory_id IN ('huaxing','huadeng','huakang-a','huakang-b')"


def uid():
    return uuid4().hex


class Record:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MoldMaster(Record, Base):
    __tablename__ = "injection_v3_mold_master"
    normalized_code: Mapped[str] = mapped_column(String(200), unique=True)
    mold_code: Mapped[str] = mapped_column(String(200))
    part_name: Mapped[str] = mapped_column(String(255), default="")
    alias_codes: Mapped[list] = mapped_column(JSON, default=list)
    required_machine_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    requirement_raw: Mapped[str] = mapped_column(String(1000), default="")
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    defaults: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(String(4000), default="")
    created_from_factory_id: Mapped[str] = mapped_column(String(64))
    source: Mapped[dict] = mapped_column(JSON, default=dict)


class MoldAsset(Record, Base):
    __tablename__ = "injection_v3_mold_asset"
    __table_args__ = (
        UniqueConstraint("master_id", "asset_code", name="uq_iv3_asset_code"),
    )
    master_id: Mapped[str] = mapped_column(
        ForeignKey("injection_v3_mold_master.id"), index=True
    )
    asset_code: Mapped[str] = mapped_column(String(200))
    current_factory_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="AVAILABLE")
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_source: Mapped[str] = mapped_column(String(255), default="人工维护")
    notes: Mapped[str] = mapped_column(String(2000), default="")


class Machine(Record, Base):
    __tablename__ = "injection_v3_machine"
    __table_args__ = (
        UniqueConstraint("factory_id", "code", name="uq_iv3_machine_code"),
        UniqueConstraint("id", "factory_id", name="uq_iv3_machine_factory"),
        CheckConstraint(FACTORY_CHECK, name="ck_iv3_machine_factory"),
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(100))
    workshop: Mapped[str] = mapped_column(String(100), default="")
    machine_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    clamp_ton: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    machine_family: Mapped[str] = mapped_column(String(32), default="HORIZONTAL")
    speed_class: Mapped[str] = mapped_column(String(32), default="NORMAL")
    manipulator: Mapped[str] = mapped_column(String(200), default="")
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    restrictions: Mapped[dict] = mapped_column(JSON, default=dict)
    operating_status: Mapped[str] = mapped_column(String(32), default="IDLE")
    recovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(String(4000), default="")
    current_setup: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_header_cells: Mapped[dict] = mapped_column(JSON, default=dict)


class CalendarEvent(Record, Base):
    __tablename__ = "injection_v3_calendar_event"
    __table_args__ = (
        CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_iv3_calendar_interval"
        ),
        CheckConstraint(FACTORY_CHECK, name="ck_iv3_calendar_factory"),
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32), default="MAINTENANCE")
    notes: Mapped[str] = mapped_column(String(2000), default="")


class ImportBatch(Record, Base):
    __tablename__ = "injection_v3_import_batch"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "file_sha256",
            "sheet_name",
            "parser_version",
            name="uq_iv3_import_source",
        ),
        CheckConstraint(FACTORY_CHECK, name="ck_iv3_import_factory"),
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    sheet_name: Mapped[str] = mapped_column(String(100))
    parser_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="PREVIEW")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    source_revision: Mapped[int | None] = mapped_column(Integer)


class Demand(Record, Base):
    __tablename__ = "injection_v3_demand"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_iv3_demand_factory"),
        Index(
            "ix_iv3_demand_state_due",
            "factory_id",
            "dispatch_state",
            "delivery_due_at",
            "id",
        ),
        Index("ix_iv3_demand_order", "factory_id", "order_no"),
        Index("ix_iv3_demand_mold", "factory_id", "mold_code"),
        Index("ix_iv3_demand_item", "factory_id", "item_no"),
        CheckConstraint(FACTORY_CHECK, name="ck_iv3_demand_factory"),
    )
    factory_id: Mapped[str] = mapped_column(String(64))
    order_no: Mapped[str | None] = mapped_column(String(255))
    item_no: Mapped[str | None] = mapped_column(String(255))
    part_name: Mapped[str | None] = mapped_column(String(255))
    mold_master_id: Mapped[str | None] = mapped_column(
        ForeignKey("injection_v3_mold_master.id")
    )
    mold_code: Mapped[str] = mapped_column(String(200))
    required_machine_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    requirements_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    demand_sets: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    planned_shots: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    opening_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    adjustment_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    completed_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    remaining_shots: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    overproduced_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    required_units: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    good_units: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    remaining_units: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    pieces_per_set: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1)
    effective_outputs_per_shot: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), default=1
    )
    allocation_mode: Mapped[str] = mapped_column(String(32), default="SEQUENTIAL_SHOTS")
    quantity_basis: Mapped[str] = mapped_column(String(64), default="physical_shots")
    opening_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_shots_per_day: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    target_basis_hours: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=24)
    net_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    gross_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    weight_basis: Mapped[str] = mapped_column(String(64), default="per_shot")
    allowance_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0.01)
    price_per_shot: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    remaining_material_kg: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    remaining_processing_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    color_name: Mapped[str | None] = mapped_column(String(255))
    colorant_code: Mapped[str | None] = mapped_column(String(255))
    color_depth_rank: Mapped[int | None] = mapped_column(Integer)
    material_raw: Mapped[str | None] = mapped_column(String(255))
    resin: Mapped[str | None] = mapped_column(String(100))
    material_grade: Mapped[str | None] = mapped_column(String(200))
    priority_level: Mapped[int] = mapped_column(Integer, default=0)
    dispatch_state: Mapped[str] = mapped_column(String(32), default="READY")
    ordered_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    delivery_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downstream_lead_days: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=3)
    earliest_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_stock_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    delivery_slack_hours: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    machine_code: Mapped[str | None] = mapped_column(String(100))
    order_note: Mapped[str | None] = mapped_column(String(4000))
    production_note: Mapped[str | None] = mapped_column(String(4000))
    warehouse_note: Mapped[str | None] = mapped_column(String(1000))
    source_system: Mapped[str] = mapped_column(String(64), default="MANUAL")
    source_document: Mapped[str | None] = mapped_column(String(255))
    source_line_id: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("injection_v3_import_batch.id")
    )
    stable_sequence: Mapped[int] = mapped_column(Integer, default=0)
    extras: Mapped[dict] = mapped_column(JSON, default=dict)
    field_sources: Mapped[dict] = mapped_column(JSON, default=dict)
    unplaced_reason: Mapped[str | None] = mapped_column(String(2000))


class Run(Record, Base):
    __tablename__ = "injection_v3_run"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_iv3_run_factory"),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            ["injection_v3_machine.id", "injection_v3_machine.factory_id"],
            name="fk_iv3_run_machine",
        ),
        Index(
            "ix_iv3_run_machine_start", "factory_id", "machine_id", "planned_start_at"
        ),
        Index("ix_iv3_run_asset_start", "mold_asset_id", "planned_start_at"),
        CheckConstraint(FACTORY_CHECK, name="ck_iv3_run_factory"),
    )
    factory_id: Mapped[str] = mapped_column(String(64))
    machine_id: Mapped[str] = mapped_column(String(64))
    mold_asset_id: Mapped[str] = mapped_column(ForeignKey("injection_v3_mold_asset.id"))
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("injection_v3_run.id"))
    status: Mapped[str] = mapped_column(String(32), default="PLANNED")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    setup_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_physical_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    physical_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_events: Mapped[list] = mapped_column(JSON, default=list)


class RunDemand(Base):
    __tablename__ = "injection_v3_run_demand"
    __table_args__ = (
        UniqueConstraint("run_id", "demand_id", name="uq_iv3_run_demand"),
        ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["injection_v3_run.id", "injection_v3_run.factory_id"],
            name="fk_iv3_rd_run",
        ),
        ForeignKeyConstraint(
            ["demand_id", "factory_id"],
            ["injection_v3_demand.id", "injection_v3_demand.factory_id"],
            name="fk_iv3_rd_demand",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    factory_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    demand_id: Mapped[str] = mapped_column(String(64), index=True)
    allocation_mode: Mapped[str] = mapped_column(String(32), default="SEQUENTIAL_SHOTS")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    outputs_per_shot: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1)
    product_code: Mapped[str] = mapped_column(String(255), default="")


class ShiftReport(Record, Base):
    __tablename__ = "injection_v3_shift_report"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "production_date",
            "shift_code",
            "segment_key",
            name="uq_iv3_shift_key",
        ),
        UniqueConstraint("client_operation_id", name="uq_iv3_report_operation"),
        ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["injection_v3_run.id", "injection_v3_run.factory_id"],
            name="fk_iv3_report_run",
        ),
        CheckConstraint("physical_shots >= 0", name="ck_iv3_report_nonnegative"),
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    production_date: Mapped[date] = mapped_column(Date)
    shift_code: Mapped[str] = mapped_column(String(16))
    segment_key: Mapped[str] = mapped_column(String(64), default="default")
    physical_shots: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    good_units: Mapped[dict] = mapped_column(JSON, default=dict)
    scrap_units: Mapped[dict] = mapped_column(JSON, default=dict)
    client_operation_id: Mapped[str] = mapped_column(String(128))


class ReportAllocation(Base):
    __tablename__ = "injection_v3_report_allocation"
    __table_args__ = (
        UniqueConstraint("report_id", "run_demand_id", name="uq_iv3_allocation"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("injection_v3_shift_report.id"), index=True
    )
    run_demand_id: Mapped[str] = mapped_column(
        ForeignKey("injection_v3_run_demand.id"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    unit: Mapped[str] = mapped_column(String(16), default="SHOT")


class ImportRow(Base):
    __tablename__ = "injection_v3_import_row"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row", name="uq_iv3_import_row"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("injection_v3_import_batch.id"), index=True
    )
    source_row: Mapped[int] = mapped_column(Integer)
    row_role: Mapped[str] = mapped_column(String(64))
    demand_id: Mapped[str | None] = mapped_column(ForeignKey("injection_v3_demand.id"))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)


class HistoricalOutput(Base):
    """Imported original cells, separate from verified physical run counters."""

    __tablename__ = "injection_v3_historical_output"
    __table_args__ = (
        UniqueConstraint(
            "demand_id",
            "production_date",
            "shift_code",
            "source_key",
            name="uq_iv3_history_key",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    demand_id: Mapped[str] = mapped_column(
        ForeignKey("injection_v3_demand.id"), index=True
    )
    import_row_id: Mapped[str] = mapped_column(ForeignKey("injection_v3_import_row.id"))
    production_date: Mapped[date] = mapped_column(Date)
    shift_code: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    counts_toward_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    allocation_mode: Mapped[str] = mapped_column(
        String(32), default="LEGACY_UNRESOLVED"
    )


class FactorySettings(Base):
    __tablename__ = "injection_v3_factory_settings"
    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)


class SharedRevision(Base):
    __tablename__ = "injection_v3_shared_revision"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class SavedView(Record, Base):
    __tablename__ = "injection_v3_saved_view"
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    view_type: Mapped[str] = mapped_column(String(32), default="table")
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class Operation(Base):
    __tablename__ = "injection_v3_operation"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uid)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    client_operation_id: Mapped[str] = mapped_column(String(128), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
