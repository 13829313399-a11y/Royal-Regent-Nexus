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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingRun(Base):
    __tablename__ = "injection_scheduling_runs"
    __table_args__ = (
        UniqueConstraint(
            "id", "factory_id", name="uq_injection_scheduling_run_id_factory"
        ),
        UniqueConstraint(
            "factory_id", "request_id", name="uq_injection_scheduling_run_request"
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_run_plan_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('CREATED', 'VALIDATING', 'GENERATING_CANDIDATES', "
            "'SOLVING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'APPLIED')",
            name="ck_injection_scheduling_run_status",
        ),
        CheckConstraint("revision >= 1", name="ck_injection_scheduling_run_revision"),
        Index(
            "ix_injection_scheduling_run_factory_created",
            "factory_id",
            "created_at",
        ),
        Index(
            "ix_injection_scheduling_run_plan_status",
            "plan_id",
            "status",
        ),
        Index(
            "ix_injection_scheduling_run_scenario_group",
            "factory_id",
            "scenario_group_id",
            "alternative_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    expected_plan_revision: Mapped[int] = mapped_column(Integer)
    rule_set_id: Mapped[str] = mapped_column(String(96), default="")
    rule_revision: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16), default="PREVIEW")
    solver_type: Mapped[str] = mapped_column(String(32), default="HEURISTIC")
    solver_version: Mapped[str] = mapped_column(String(32), default="phase3-v1")
    requested_solver: Mapped[str] = mapped_column(String(32), default="HEURISTIC")
    solver_status: Mapped[str] = mapped_column(String(32), default="NOT_RUN")
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str] = mapped_column(Text, default="")
    scenario_group_id: Mapped[str] = mapped_column(String(96), default="")
    scenario_name: Mapped[str] = mapped_column(String(128), default="方案 A")
    alternative_no: Mapped[int] = mapped_column(Integer, default=1)
    replay_of_run_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    horizon_start: Mapped[str] = mapped_column(String(32))
    horizon_end: Mapped[str] = mapped_column(String(32))
    input_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    objective_config_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    error_detail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[str] = mapped_column(String(32), default="")
    finished_at: Mapped[str] = mapped_column(String(32), default="")
    applied_at: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    applied_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    applied_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class InjectionSchedulingRunAssignment(Base):
    __tablename__ = "injection_scheduling_run_assignments"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "order_id", name="uq_injection_scheduling_run_assignment_order"
        ),
        ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["injection_scheduling_runs.id", "injection_scheduling_runs.factory_id"],
            name="fk_injection_scheduling_assignment_run_factory",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["physical_mold_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_assignment_physical_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "decision IN ('PASS', 'REVIEW_REQUIRED', 'UNASSIGNED')",
            name="ck_injection_scheduling_assignment_decision",
        ),
        Index(
            "ix_injection_scheduling_assignment_run_machine_sequence",
            "run_id",
            "machine_id",
            "sequence_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    existing_task_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    physical_mold_asset_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_copy_no: Mapped[int] = mapped_column(Integer, default=1)
    machine_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    sequence_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_start: Mapped[str] = mapped_column(String(32), default="")
    planned_finish: Mapped[str] = mapped_column(String(32), default="")
    setup_minutes: Mapped[int] = mapped_column(Integer, default=0)
    production_minutes: Mapped[int] = mapped_column(Integer, default=0)
    planned_downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    changeover_type: Mapped[str] = mapped_column(String(64), default="")
    decision: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    explanation_json: Mapped[str] = mapped_column(Text, default="{}")
    unassigned_reason_code: Mapped[str] = mapped_column(
        String(64), default="", index=True
    )
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingTransitionRule(Base):
    __tablename__ = "injection_scheduling_transition_rules"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "from_material_group",
            "from_color_rank",
            "from_setup_family",
            "to_material_group",
            "to_color_rank",
            "to_setup_family",
            "revision",
            name="uq_injection_scheduling_transition_rule_key_revision",
        ),
        CheckConstraint(
            "revision >= 1", name="ck_injection_scheduling_transition_revision"
        ),
        Index(
            "ix_injection_scheduling_transition_factory_active",
            "factory_id",
            "active",
            "revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    from_material_group: Mapped[str] = mapped_column(String(128), default="")
    from_color_rank: Mapped[int] = mapped_column(Integer, default=0)
    from_setup_family: Mapped[str] = mapped_column(String(128), default="")
    to_material_group: Mapped[str] = mapped_column(String(128), default="")
    to_color_rank: Mapped[int] = mapped_column(Integer, default=0)
    to_setup_family: Mapped[str] = mapped_column(String(128), default="")
    mold_change_minutes: Mapped[int] = mapped_column(Integer, default=0)
    color_change_minutes: Mapped[int] = mapped_column(Integer, default=0)
    material_change_minutes: Mapped[int] = mapped_column(Integer, default=0)
    fixture_change_minutes: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingMachineCalendar(Base):
    __tablename__ = "injection_scheduling_machine_calendars"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "machine_id",
            "window_start",
            "window_end",
            "calendar_type",
            name="uq_injection_scheduling_machine_calendar_window",
        ),
        CheckConstraint(
            "calendar_type IN ('SHIFT', 'BREAK', 'MAINTENANCE', 'DOWNTIME', 'UNAVAILABLE')",
            name="ck_injection_scheduling_machine_calendar_type",
        ),
        Index(
            "ix_injection_scheduling_calendar_machine_window",
            "factory_id",
            "machine_id",
            "window_start",
            "window_end",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    calendar_type: Mapped[str] = mapped_column(String(32), index=True)
    window_start: Mapped[str] = mapped_column(String(32), index=True)
    window_end: Mapped[str] = mapped_column(String(32), index=True)
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(255), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


# Keep shared physical-asset tables in Base.metadata when focused tests import
# the scheduler model directly.
from app.models import injection_scheduling_shared as _shared_models  # noqa: F401
