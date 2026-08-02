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


class InjectionSchedulingOrder(Base):
    __tablename__ = "injection_scheduling_orders"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_order_id_factory",
        ),
        CheckConstraint(
            "order_quantity > 0",
            name="ck_injection_scheduling_order_quantity",
        ),
        CheckConstraint(
            "source_completed_quantity >= 0 AND completed_quantity >= 0",
            name="ck_injection_scheduling_order_completed_quantity",
        ),
        CheckConstraint(
            "priority_code IN ('NORMAL', 'URGENT', 'CRITICAL')",
            name="ck_injection_scheduling_order_priority",
        ),
        CheckConstraint(
            "material_readiness_status IN "
            "('unknown', 'ready', 'partial', 'blocked')",
            name="ck_injection_scheduling_order_material_readiness",
        ),
        CheckConstraint(
            "status IN ('BACKLOG', 'SCHEDULED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_scheduling_order_status",
        ),
        CheckConstraint(
            "revision >= 1 AND estimated_remaining_shifts >= 0",
            name="ck_injection_scheduling_order_revision",
        ),
        Index(
            "ix_injection_scheduling_order_factory_status_due",
            "factory_id",
            "status",
            "delivery_due_date",
        ),
        Index(
            "ix_injection_scheduling_order_factory_number_item",
            "factory_id",
            "order_no",
            "item_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    order_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    mold_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    order_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    source_completed_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    completed_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    estimated_completion_at: Mapped[str] = mapped_column(String(32), default="")
    estimated_remaining_shifts: Mapped[int] = mapped_column(Integer, default=0)
    delivery_slack_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_start_date: Mapped[str] = mapped_column(String(32), default="")
    delivery_due_date: Mapped[str] = mapped_column(String(32), default="", index=True)
    priority_code: Mapped[str] = mapped_column(String(32), default="NORMAL", index=True)
    material_readiness_status: Mapped[str] = mapped_column(
        String(32), default="unknown", index=True
    )
    warehouse_text: Mapped[str] = mapped_column(String(255), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    source_version: Mapped[str] = mapped_column(String(128), default="")
    lineage_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="BACKLOG", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingPlan(Base):
    __tablename__ = "injection_scheduling_plans"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_plan_id_factory",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_injection_scheduling_plan_status",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_plan_revision",
        ),
        Index(
            "uq_injection_scheduling_one_draft_per_factory",
            "factory_id",
            unique=True,
            sqlite_where=text("status = 'DRAFT'"),
            postgresql_where=text("status = 'DRAFT'"),
        ),
        Index(
            "uq_injection_scheduling_one_published_per_factory",
            "factory_id",
            unique=True,
            sqlite_where=text("status = 'PUBLISHED'"),
            postgresql_where=text("status = 'PUBLISHED'"),
        ),
        Index(
            "uq_injection_scheduling_rollback_request",
            "factory_id",
            "rollback_request_id",
            unique=True,
            sqlite_where=text("rollback_request_id IS NOT NULL"),
            postgresql_where=text("rollback_request_id IS NOT NULL"),
        ),
        Index(
            "ix_injection_scheduling_plan_factory_status_updated",
            "factory_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    business_date: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    rule_set_id: Mapped[str] = mapped_column(String(96), default="")
    rule_revision: Mapped[int] = mapped_column(Integer, default=0)
    based_on_plan_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    rollback_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    published_by: Mapped[str] = mapped_column(String(64), default="")
    published_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)
    published_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    archived_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingTask(Base):
    __tablename__ = "injection_scheduling_tasks"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_task_id_factory",
        ),
        UniqueConstraint(
            "plan_id",
            "machine_id",
            "sequence_no",
            name="uq_injection_scheduling_task_plan_machine_sequence",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_task_plan_factory",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_task_order_factory",
        ),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_task_machine_factory",
        ),
        ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_task_mold_factory",
        ),
        CheckConstraint(
            "execution_status IN "
            "('QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_scheduling_task_execution_status",
        ),
        CheckConstraint(
            "sequence_no >= 0 AND mold_copy_no >= 1",
            name="ck_injection_scheduling_task_sequence_copy",
        ),
        CheckConstraint(
            "shift_target_quantity >= 0 AND reported_quantity >= 0",
            name="ck_injection_scheduling_task_quantities",
        ),
        CheckConstraint(
            "revision >= 1 AND estimated_remaining_shifts >= 0",
            name="ck_injection_scheduling_task_revision",
        ),
        Index(
            "uq_injection_scheduling_one_running_per_machine",
            "factory_id",
            "machine_id",
            unique=True,
            sqlite_where=text(
                "active_execution = 1 AND execution_status = 'RUNNING'"
            ),
            postgresql_where=text(
                "active_execution = true AND execution_status = 'RUNNING'"
            ),
        ),
        Index(
            "ix_injection_scheduling_task_plan_machine_sequence",
            "plan_id",
            "machine_id",
            "sequence_no",
        ),
        Index(
            "ix_injection_scheduling_task_factory_execution",
            "factory_id",
            "active_execution",
            "execution_status",
        ),
        Index(
            "uq_injection_scheduling_task_plan_source_row",
            "factory_id",
            "plan_id",
            "source_file_hash",
            "source_sheet_name",
            "source_row",
            unique=True,
            sqlite_where=text("source_file_hash <> '' AND source_row IS NOT NULL"),
            postgresql_where=text("source_file_hash <> '' AND source_row IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    mold_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    mold_copy_no: Mapped[int] = mapped_column(Integer, default=1)
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    execution_status: Mapped[str] = mapped_column(
        String(32), default="QUEUED", index=True
    )
    planned_start: Mapped[str] = mapped_column(String(32), default="")
    planned_finish: Mapped[str] = mapped_column(String(32), default="")
    shift_target_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    reported_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    estimated_start: Mapped[str] = mapped_column(String(32), default="")
    estimated_finish: Mapped[str] = mapped_column(String(32), default="")
    estimated_remaining_shifts: Mapped[int] = mapped_column(Integer, default=0)
    delivery_slack_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_override_reason: Mapped[str] = mapped_column(Text, default="")
    active_execution: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    source_sheet_name: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_file_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingShiftReport(Base):
    __tablename__ = "injection_scheduling_shift_reports"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_scheduling_shift_report_request",
        ),
        ForeignKeyConstraint(
            ["task_id", "factory_id"],
            ["injection_scheduling_tasks.id", "injection_scheduling_tasks.factory_id"],
            name="fk_injection_scheduling_shift_report_task_factory",
        ),
        ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_shift_report_order_factory",
        ),
        CheckConstraint(
            "shift_code IN ('DAY', 'NIGHT')",
            name="ck_injection_scheduling_shift_report_shift",
        ),
        CheckConstraint(
            "quantity_mode IN ('INCREMENTAL', 'CUMULATIVE')",
            name="ck_injection_scheduling_shift_report_mode",
        ),
        CheckConstraint(
            "reported_quantity >= 0 AND normalized_increment_quantity >= 0",
            name="ck_injection_scheduling_shift_report_quantity",
        ),
        CheckConstraint(
            "shift_target_quantity >= 0 AND downtime_minutes >= 0",
            name="ck_injection_scheduling_shift_report_operating_values",
        ),
        Index(
            "ix_injection_scheduling_shift_report_factory_task_created",
            "factory_id",
            "task_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    business_date: Mapped[str] = mapped_column(String(32), index=True)
    shift_code: Mapped[str] = mapped_column(String(16), index=True)
    quantity_mode: Mapped[str] = mapped_column(String(16))
    reported_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    normalized_increment_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    shift_target_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=Decimal(0)
    )
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    exception_code: Mapped[str] = mapped_column(String(64), default="")
    exception_detail: Mapped[str] = mapped_column(Text, default="")
    reported_status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    reported_by: Mapped[str] = mapped_column(String(64), index=True)
    reported_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingPlanRevision(Base):
    __tablename__ = "injection_scheduling_plan_revisions"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "plan_revision",
            name="uq_injection_scheduling_plan_revision",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_plan_revision_plan_factory",
        ),
        Index(
            "ix_injection_scheduling_plan_revision_factory_created",
            "factory_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingPublishedSnapshot(Base):
    __tablename__ = "injection_scheduling_published_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_scheduling_published_snapshot_request",
        ),
        UniqueConstraint(
            "plan_id",
            name="uq_injection_scheduling_published_snapshot_plan",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_published_snapshot_plan_factory",
        ),
        Index(
            "ix_injection_scheduling_published_snapshot_factory_created",
            "factory_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)
    published_by: Mapped[str] = mapped_column(String(64), index=True)
    published_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingAuditEvent(Base):
    __tablename__ = "injection_scheduling_audit_events"
    __table_args__ = (
        UniqueConstraint(
            "id",
            name="uq_injection_scheduling_audit_event_id",
        ),
        Index(
            "ix_injection_scheduling_audit_factory_sequence",
            "factory_id",
            "sequence",
        ),
        Index(
            "ix_injection_scheduling_audit_entity",
            "factory_id",
            "entity_type",
            "entity_id",
        ),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(96))
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    entity_revision: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_user_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
