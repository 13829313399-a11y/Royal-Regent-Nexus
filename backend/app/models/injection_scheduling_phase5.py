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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingIntegrationCursor(Base):
    __tablename__ = "injection_scheduling_integration_cursors"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "source_type",
            "source_key",
            name="uq_injection_scheduling_integration_cursor_source",
        ),
        CheckConstraint(
            "source_type IN ('ERP', 'DEVICE')",
            name="ck_injection_scheduling_integration_cursor_source_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'ERROR', 'NOT_CONFIGURED')",
            name="ck_injection_scheduling_integration_cursor_status",
        ),
        CheckConstraint(
            "event_count >= 0 AND revision >= 1",
            name="ck_injection_scheduling_integration_cursor_counts",
        ),
        Index(
            "ix_injection_scheduling_integration_cursor_factory_type",
            "factory_id",
            "source_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    source_key: Mapped[str] = mapped_column(String(96), index=True)
    cursor_value: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    last_received_at: Mapped[str] = mapped_column(String(32), default="")
    last_success_at: Mapped[str] = mapped_column(String(32), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingExternalEvent(Base):
    __tablename__ = "injection_scheduling_external_events"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "source_type",
            "source_key",
            "external_event_id",
            name="uq_injection_scheduling_external_event_source_id",
        ),
        CheckConstraint(
            "source_type IN ('ERP', 'DEVICE')",
            name="ck_injection_scheduling_external_event_source_type",
        ),
        CheckConstraint(
            "status IN ('APPLIED', 'IGNORED', 'FAILED')",
            name="ck_injection_scheduling_external_event_status",
        ),
        Index(
            "ix_injection_scheduling_external_event_factory_received",
            "factory_id",
            "received_at",
        ),
        Index(
            "ix_injection_scheduling_external_event_linked_entity",
            "factory_id",
            "linked_entity_type",
            "linked_entity_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    source_key: Mapped[str] = mapped_column(String(96), index=True)
    external_event_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="APPLIED", index=True)
    linked_entity_type: Mapped[str] = mapped_column(String(64), default="")
    linked_entity_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    request_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    received_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    received_by_name: Mapped[str] = mapped_column(String(128), default="")
    received_at: Mapped[str] = mapped_column(String(32), index=True)
    applied_at: Mapped[str] = mapped_column(String(32), default="")
    error_detail: Mapped[str] = mapped_column(Text, default="")


class InjectionSchedulingCycleObservation(Base):
    __tablename__ = "injection_scheduling_cycle_observations"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "external_event_id",
            name="uq_injection_scheduling_cycle_observation_event",
        ),
        ForeignKeyConstraint(
            ["task_id", "factory_id"],
            ["injection_scheduling_tasks.id", "injection_scheduling_tasks.factory_id"],
            name="fk_injection_scheduling_cycle_observation_task_factory",
        ),
        ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_cycle_observation_order_factory",
        ),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_cycle_observation_machine_factory",
        ),
        ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_cycle_observation_mold_factory",
        ),
        CheckConstraint(
            "cycle_seconds > 0 AND units_per_cycle > 0",
            name="ck_injection_scheduling_cycle_observation_cycle",
        ),
        CheckConstraint(
            "produced_quantity >= 0 AND runtime_minutes >= 0",
            name="ck_injection_scheduling_cycle_observation_quantities",
        ),
        Index(
            "ix_injection_scheduling_cycle_observation_factory_mold_time",
            "factory_id",
            "mold_id",
            "observed_at",
        ),
        Index(
            "ix_injection_scheduling_cycle_observation_factory_machine_time",
            "factory_id",
            "machine_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    external_event_id: Mapped[str] = mapped_column(String(96), index=True)
    task_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    mold_id: Mapped[str] = mapped_column(String(96), index=True)
    observed_at: Mapped[str] = mapped_column(String(32), index=True)
    cycle_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    units_per_cycle: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(1))
    produced_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    runtime_minutes: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal(0))
    source_key: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingSpeedModel(Base):
    __tablename__ = "injection_scheduling_speed_models"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "mold_id",
            name="uq_injection_scheduling_speed_model_factory_mold",
        ),
        ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_speed_model_mold_factory",
        ),
        CheckConstraint(
            "sample_count >= 0 AND revision >= 1",
            name="ck_injection_scheduling_speed_model_counts",
        ),
        CheckConstraint(
            "calibrated_cycle_seconds > 0 AND units_per_cycle > 0 "
            "AND calibrated_units_per_hour > 0",
            name="ck_injection_scheduling_speed_model_values",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_injection_scheduling_speed_model_confidence",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INSUFFICIENT_DATA')",
            name="ck_injection_scheduling_speed_model_status",
        ),
        Index(
            "ix_injection_scheduling_speed_model_factory_status",
            "factory_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_id: Mapped[str] = mapped_column(String(96), index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    calibrated_cycle_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    units_per_cycle: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(1))
    calibrated_units_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), default=Decimal(0))
    status: Mapped[str] = mapped_column(String(32), default="INSUFFICIENT_DATA")
    source_window_start: Mapped[str] = mapped_column(String(32), default="")
    source_window_end: Mapped[str] = mapped_column(String(32), default="")
    last_observed_at: Mapped[str] = mapped_column(String(32), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[str] = mapped_column(String(32), index=True)
