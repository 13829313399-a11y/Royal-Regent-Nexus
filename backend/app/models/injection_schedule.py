from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
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


class InjectionScheduleFactorySettings(Base):
    __tablename__ = "injection_schedule_factory_settings"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id"),
        CheckConstraint("schedule_revision >= 1"),
        CheckConstraint("schedule_horizon_days BETWEEN 1 AND 90"),
        CheckConstraint("freeze_hours BETWEEN 0 AND 720"),
        CheckConstraint(
            "effective_hours_per_day > 0 AND effective_hours_per_day <= 24"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    factory_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    business_date: Mapped[str] = mapped_column(String(10), default="", index=True)
    current_shift: Mapped[str] = mapped_column(String(16), default="DAY")
    day_shift_start: Mapped[str] = mapped_column(String(5), default="08:00")
    day_shift_end: Mapped[str] = mapped_column(String(5), default="20:00")
    night_shift_start: Mapped[str] = mapped_column(String(5), default="20:00")
    night_shift_end: Mapped[str] = mapped_column(String(5), default="08:00")
    warehouse_buffer_days: Mapped[int] = mapped_column(Integer, default=3)
    fallback_water_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0.01")
    )
    auto_schedule_mode: Mapped[str] = mapped_column(
        String(32), default="PREVIEW_CONFIRM"
    )
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    template_family: Mapped[str] = mapped_column(
        String(64), default="unified_injection_schedule"
    )
    template_version: Mapped[str] = mapped_column(String(32), default="1.0")
    schedule_revision: Mapped[int] = mapped_column(Integer, default=1)
    schedule_horizon_days: Mapped[int] = mapped_column(Integer, default=14)
    freeze_hours: Mapped[int] = mapped_column(Integer, default=12)
    effective_hours_per_day: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("24")
    )
    scheduling_rule_config_json: Mapped[str] = mapped_column(Text, default="{}")
    color_rule_config_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)


class InjectionScheduleImportBatch(Base):
    __tablename__ = "injection_schedule_import_batches"
    __table_args__ = (UniqueConstraint("id", "factory_id"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    source_sheet: Mapped[str] = mapped_column(String(128), default="")
    template_family: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[str] = mapped_column(String(32))
    contract_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    document_type: Mapped[str] = mapped_column(String(32), default="UNIFIED_TEMPLATE")
    import_profile_code: Mapped[str] = mapped_column(
        String(64), default="UNIFIED_TEMPLATE_V1"
    )
    header_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="PREVIEW", index=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    preview_request_id: Mapped[str] = mapped_column(String(128))
    commit_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    confirmed_by: Mapped[str] = mapped_column(String(64), default="")
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_at: Mapped[str] = mapped_column(String(40), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class InjectionScheduleImportRequestBinding(Base):
    __tablename__ = "injection_schedule_import_request_bindings"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "request_id"),
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    source_file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class InjectionScheduleImportIssue(Base):
    __tablename__ = "injection_schedule_import_issues"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    source_sheet: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_name: Mapped[str] = mapped_column(String(128), default="")
    raw_value: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), index=True)
    error_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class InjectionScheduleOrderDemand(Base):
    __tablename__ = "injection_schedule_order_demands"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
        ),
        Index(
            "uq_injection_schedule_order_demand_active_business_key_v2",
            "factory_id",
            "business_key",
            unique=True,
            sqlite_where=text("status NOT IN ('COMPLETED', 'CANCELLED')"),
            postgresql_where=text("status NOT IN ('COMPLETED', 'CANCELLED')"),
        ),
        Index(
            "ix_injection_schedule_order_demand_factory_due",
            "factory_id",
            "delivery_due_date",
        ),
        Index(
            "ix_injection_schedule_order_demand_factory_status_priority",
            "factory_id",
            "status",
            "priority",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_batch_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    source_sheet: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    demand_line_no: Mapped[str] = mapped_column(String(64), default="")
    business_key: Mapped[str] = mapped_column(String(64), default="")
    raw_total_sets: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    raw_source_json: Mapped[str] = mapped_column(Text, default="{}")
    order_no: Mapped[str] = mapped_column(String(128), index=True)
    product_code: Mapped[str] = mapped_column(String(128), index=True)
    mold_code: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    quantity_sets: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_sets: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    order_shots: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    pieces_per_shot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    single_machine_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    single_color_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    mold_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    required_machine_a_label: Mapped[str] = mapped_column(String(64), default="")
    required_machine_a_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL", index=True)
    order_date: Mapped[str] = mapped_column(String(10), default="")
    delivery_start_date: Mapped[str] = mapped_column(String(10), default="")
    delivery_due_date: Mapped[str] = mapped_column(String(10), default="", index=True)
    shipping_date: Mapped[str] = mapped_column(String(10), default="")
    warehouse: Mapped[str] = mapped_column(String(128), default="")
    delivery_location: Mapped[str] = mapped_column(String(255), default="")
    ordered_by_name: Mapped[str] = mapped_column(String(128), default="")
    operator_name: Mapped[str] = mapped_column(String(128), default="")
    color: Mapped[str] = mapped_column(String(128), default="")
    pigment_code: Mapped[str] = mapped_column(String(128), default="")
    color_lightness: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    color_family: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    color_lightness_rank: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    material_name: Mapped[str] = mapped_column(String(128), default="")
    water_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    net_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    gross_weight_g: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    material_weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    daily_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    material_status: Mapped[str] = mapped_column(String(16), default="UNPREPARED")
    material_prepared_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    spray_required: Mapped[bool] = mapped_column(Boolean, default=False)
    data_completeness_status: Mapped[str] = mapped_column(
        String(16), default="INCOMPLETE"
    )
    remark: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleMachine(Base):
    __tablename__ = "injection_schedule_machines"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "machine_code"),
        Index(
            "ix_injection_schedule_machine_factory_display",
            "factory_id",
            "display_order",
            "machine_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_code: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[str] = mapped_column(String(64), default="")
    machine_name: Mapped[str] = mapped_column(String(128), default="")
    machine_a_label: Mapped[str] = mapped_column(String(64), default="")
    machine_ounce_capacity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    shot_capacity_g: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    tonnage: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    is_high_speed: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    robot_arm_type: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    fixture: Mapped[str] = mapped_column(String(128), default="")
    supports_core_pull: Mapped[bool] = mapped_column(Boolean, default=False)
    efficiency_factor: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("1")
    )
    max_mold_length_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    max_mold_width_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    max_mold_height_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    min_mold_thickness_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    max_mold_thickness_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    tie_bar_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    tie_bar_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    allowed_materials_json: Mapped[str] = mapped_column(Text, default="[]")
    forbidden_materials_json: Mapped[str] = mapped_column(Text, default="[]")
    allowed_color_lightness_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    available_from: Mapped[str] = mapped_column(String(40), default="")
    structured_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    raw_remark: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleMold(Base):
    __tablename__ = "injection_schedule_molds"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "mold_code", "product_code"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_code: Mapped[str] = mapped_column(String(128), index=True)
    product_code: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    required_machine_a_label: Mapped[str] = mapped_column(String(64), default="")
    mold_ounce_requirement: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    min_machine_ounce: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    max_machine_ounce: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    cavity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pieces_per_shot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    single_machine_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    single_color_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    mold_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    shot_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    recommended_tonnage: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    mold_length_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    mold_width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    mold_height_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    mold_thickness_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    requires_core_pull: Mapped[bool] = mapped_column(Boolean, default=False)
    required_robot_arm: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    required_fixture: Mapped[str] = mapped_column(String(128), default="")
    allowed_materials_json: Mapped[str] = mapped_column(Text, default="[]")
    forbidden_machine_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    structured_constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    daily_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    mold_change_reference_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleLine(Base):
    __tablename__ = "injection_schedule_lines"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "machine_id", "sequence_no"),
        ForeignKeyConstraint(
            ["order_demand_id", "factory_id"],
            [
                "injection_schedule_order_demands.id",
                "injection_schedule_order_demands.factory_id",
            ],
        ),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
        ),
        ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_schedule_molds.id", "injection_schedule_molds.factory_id"],
        ),
        Index(
            "ix_injection_schedule_line_factory_window",
            "factory_id",
            "planned_start_at",
            "planned_finish_at",
        ),
        Index(
            "ix_injection_schedule_line_factory_revision",
            "factory_id",
            "schedule_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_demand_id: Mapped[str] = mapped_column(String(96), index=True)
    machine_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    sequence_no: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(16), default="NORMAL")
    planned_start_at: Mapped[str] = mapped_column(String(40), default="")
    planned_finish_at: Mapped[str] = mapped_column(String(40), default="")
    suggested_changeover_hours: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0")
    )
    manual_changeover_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    final_changeover_hours: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0")
    )
    manual_changeover_reason: Mapped[str] = mapped_column(Text, default="")
    downtime_hours: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0")
    )
    system_daily_target: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    manual_daily_target: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    effective_daily_target: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    warehouse_date: Mapped[str] = mapped_column(String(10), default="")
    delivery_gap_days: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    schedule_revision: Mapped[int] = mapped_column(Integer, default=1)
    schedule_source: Mapped[str] = mapped_column(String(16), default="MANUAL")
    actual_started_at: Mapped[str] = mapped_column(String(40), default="")
    actual_finished_at: Mapped[str] = mapped_column(String(40), default="")
    assignment_reason_json: Mapped[str] = mapped_column(Text, default="{}")
    manual_adjustment_reason: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleShiftOutput(Base):
    __tablename__ = "injection_schedule_shift_outputs"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "schedule_line_id", "production_date", "shift"),
        ForeignKeyConstraint(
            ["schedule_line_id", "factory_id"],
            ["injection_schedule_lines.id", "injection_schedule_lines.factory_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    schedule_line_id: Mapped[str] = mapped_column(String(96), index=True)
    production_date: Mapped[str] = mapped_column(String(10), index=True)
    shift: Mapped[str] = mapped_column(String(16))
    reported_shots: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    defect_shots: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    qualified_shots: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    downtime_reason: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    reported_by: Mapped[str] = mapped_column(String(64))
    reported_by_name: Mapped[str] = mapped_column(String(128), default="")
    reported_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)


class InjectionScheduleMachineUnavailableWindow(Base):
    __tablename__ = "injection_schedule_machine_unavailable_windows"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("start_at < end_at"),
        Index(
            "ix_injection_schedule_machine_window_factory_range",
            "factory_id",
            "start_at",
            "end_at",
        ),
        Index(
            "ix_injection_schedule_machine_window_machine_range",
            "factory_id",
            "machine_id",
            "start_at",
            "end_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    start_at: Mapped[str] = mapped_column(String(40))
    end_at: Mapped[str] = mapped_column(String(40))
    window_type: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text, default="")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleSavedView(Base):
    __tablename__ = "injection_schedule_saved_views"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "user_id", "name", "scope"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(16), default="PERSONAL")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class InjectionScheduleAuditEvent(Base):
    __tablename__ = "injection_schedule_audit_events"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "event_sequence"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    event_sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    entity_version: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text, default="")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_user_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_display_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40), index=True)


class InjectionScheduleAutoProposal(Base):
    __tablename__ = "injection_schedule_auto_proposals"
    __table_args__ = (
        UniqueConstraint("id", "factory_id"),
        UniqueConstraint("factory_id", "request_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(128))
    request_payload_sha256: Mapped[str] = mapped_column(String(64), index=True)
    input_version_digest: Mapped[str] = mapped_column(String(64), index=True)
    algorithm_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PREVIEW", index=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    changes_json: Mapped[str] = mapped_column(Text, default="[]")
    unscheduled_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    applied_by: Mapped[str] = mapped_column(String(64), default="")
    applied_at: Mapped[str] = mapped_column(String(40), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
