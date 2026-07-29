from sqlalchemy import (
    Boolean,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingImportBatch(Base):
    __tablename__ = "injection_scheduling_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_import_batch_id_factory",
        ),
        UniqueConstraint(
            "factory_id",
            "business_date",
            "preview_revision",
            name="uq_injection_scheduling_import_preview_revision",
        ),
        Index(
            "ix_injection_scheduling_import_source",
            "factory_id",
            "source_sha256",
            "business_date",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    business_date: Mapped[str] = mapped_column(String(32), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    preview_revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="preview", index=True)
    normalized_json: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    blocker_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_at: Mapped[str] = mapped_column(String(32), default="")
    confirm_reason: Mapped[str] = mapped_column(Text, default="")


class InjectionSchedulingImportIssue(Base):
    __tablename__ = "injection_scheduling_import_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_issue_batch_factory",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    sheet_name: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int] = mapped_column(Integer, default=0)
    field: Mapped[str] = mapped_column(String(64), default="")
    source_value: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text)


class InjectionSchedulingMachine(Base):
    __tablename__ = "injection_scheduling_machines"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_scheduling_machine_factory_code",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_machine_id_factory",
        ),
        ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_machine_batch_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_code: Mapped[str] = mapped_column(String(64), index=True)
    machine_name: Mapped[str] = mapped_column(String(128))
    workshop: Mapped[str] = mapped_column(String(128), default="")
    state: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    machine_class: Mapped[str] = mapped_column(String(32), default="", index=True)
    tonnage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injection_capacity_g: Mapped[str] = mapped_column(String(32), default="")
    safety_utilization: Mapped[str] = mapped_column(String(16), default="0.82")
    mold_width_mm: Mapped[str] = mapped_column(String(32), default="")
    mold_height_mm: Mapped[str] = mapped_column(String(32), default="")
    robot_level: Mapped[str] = mapped_column(String(32), default="none")
    capabilities_json: Mapped[str] = mapped_column(Text, default="{}")
    restrictions_json: Mapped[str] = mapped_column(Text, default="[]")
    completeness: Mapped[str] = mapped_column(
        String(32),
        default="needs_review",
        index=True,
    )
    source_batch_id: Mapped[str] = mapped_column(String(96), index=True)
    source_lineage_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class InjectionSchedulingMold(Base):
    __tablename__ = "injection_scheduling_molds"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "mold_no",
            name="uq_injection_scheduling_mold_factory_no",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_mold_id_factory",
        ),
        ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_mold_batch_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_no: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    machine_class_requirement: Mapped[str] = mapped_column(String(64), default="")
    length_mm: Mapped[str] = mapped_column(String(32), default="")
    width_mm: Mapped[str] = mapped_column(String(32), default="")
    thickness_mm: Mapped[str] = mapped_column(String(32), default="")
    shot_weight_g: Mapped[str] = mapped_column(String(32), default="")
    material: Mapped[str] = mapped_column(String(128), default="")
    robot_requirement: Mapped[str] = mapped_column(String(32), default="none")
    core_pull_required: Mapped[bool] = mapped_column(Boolean, default=False)
    unscrew_required: Mapped[bool] = mapped_column(Boolean, default=False)
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    completeness: Mapped[str] = mapped_column(
        String(32),
        default="needs_review",
        index=True,
    )
    source_batch_id: Mapped[str] = mapped_column(String(96), index=True)
    source_lineage_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class InjectionSchedulingOrder(Base):
    __tablename__ = "injection_scheduling_orders"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "natural_key",
            name="uq_injection_scheduling_order_factory_key",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_order_id_factory",
        ),
        ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            [
                "injection_scheduling_molds.id",
                "injection_scheduling_molds.factory_id",
            ],
            name="fk_injection_scheduling_order_mold_factory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_order_batch_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    natural_key: Mapped[str] = mapped_column(String(255), index=True)
    order_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    mold_id: Mapped[str] = mapped_column(String(96), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    order_qty: Mapped[int] = mapped_column(Integer, default=0)
    completed_qty: Mapped[int] = mapped_column(Integer, default=0)
    remaining_qty: Mapped[int] = mapped_column(Integer, default=0)
    daily_target: Mapped[int] = mapped_column(Integer, default=0)
    material: Mapped[str] = mapped_column(String(128), default="")
    color: Mapped[str] = mapped_column(String(128), default="")
    delivery_due_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    priority_code: Mapped[str] = mapped_column(String(8), default="P2", index=True)
    priority_flag: Mapped[str] = mapped_column(String(128), default="")
    requirement_json: Mapped[str] = mapped_column(Text, default="{}")
    completeness: Mapped[str] = mapped_column(
        String(32),
        default="needs_review",
        index=True,
    )
    source_batch_id: Mapped[str] = mapped_column(String(96), index=True)
    source_lineage_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class InjectionSchedulingRuleSet(Base):
    __tablename__ = "injection_scheduling_rule_sets"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "revision",
            name="uq_injection_scheduling_rule_factory_revision",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_rule_id_factory",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    config_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))
    superseded_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingPlan(Base):
    __tablename__ = "injection_scheduling_plans"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_plan_id_factory",
        ),
        Index(
            "ix_injection_scheduling_current_plan",
            "factory_id",
            "is_current",
            unique=True,
            sqlite_where=sql_text("is_current = 1"),
            postgresql_where=sql_text("is_current"),
        ),
        ForeignKeyConstraint(
            ["rule_set_id", "factory_id"],
            [
                "injection_scheduling_rule_sets.id",
                "injection_scheduling_rule_sets.factory_id",
            ],
            name="fk_injection_scheduling_plan_rule_factory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_injection_scheduling_plan_batch_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    published_revision: Mapped[int] = mapped_column(Integer, default=0)
    anchor_at: Mapped[str] = mapped_column(String(32))
    rule_set_id: Mapped[str] = mapped_column(String(96), index=True)
    source_batch_id: Mapped[str] = mapped_column(String(96), index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingPlanRevision(Base):
    __tablename__ = "injection_scheduling_plan_revisions"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "revision",
            name="uq_injection_scheduling_plan_revision",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_revision_plan_factory",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingTask(Base):
    __tablename__ = "injection_scheduling_tasks"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "machine_id",
            "sequence",
            name="uq_injection_scheduling_task_lane_sequence",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_task_id_factory",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_task_plan_factory",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_task_machine_factory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_task_order_factory",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    planned_start: Mapped[str] = mapped_column(String(32), default="")
    planned_end: Mapped[str] = mapped_column(String(32), default="")
    risk: Mapped[str] = mapped_column(String(32), default="normal", index=True)
    task_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class InjectionSchedulingPublishedSnapshot(Base):
    __tablename__ = "injection_scheduling_published_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "version",
            name="uq_injection_scheduling_publish_factory_version",
        ),
        UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_publish_id_factory",
        ),
        ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            [
                "injection_scheduling_plans.id",
                "injection_scheduling_plans.factory_id",
            ],
            name="fk_injection_scheduling_publish_plan_factory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rollback_of_snapshot_id", "factory_id"],
            [
                "injection_scheduling_published_snapshots.id",
                "injection_scheduling_published_snapshots.factory_id",
            ],
            name="fk_injection_scheduling_publish_rollback_factory",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_injection_scheduling_publish_current",
            "factory_id",
            "is_current",
            unique=True,
            sqlite_where=sql_text("is_current = 1"),
            postgresql_where=sql_text("is_current"),
        ),
        Index(
            "ix_inj_sched_publish_rollback",
            "rollback_of_snapshot_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    plan_revision: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    rollback_of_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_by: Mapped[str] = mapped_column(String(64), index=True)
    published_by_name: Mapped[str] = mapped_column(String(128))
    published_at: Mapped[str] = mapped_column(String(32), index=True)
    superseded_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingAuditEvent(Base):
    __tablename__ = "injection_scheduling_audit_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    old_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
