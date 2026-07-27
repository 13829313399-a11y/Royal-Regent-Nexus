from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import event
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


FACTORY_SCOPED_ID_CONSTRAINT = ("id", "factory_id")


class InjectionScheduleImportBatch(Base):
    __tablename__ = "injection_schedule_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "source_sha256",
            name="uq_injection_import_batch_factory_sha256",
        ),
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_import_batch_id_factory",
        ),
        CheckConstraint(
            "status IN ('previewed', 'confirmed', 'rejected')",
            name="ck_injection_import_batch_status",
        ),
        CheckConstraint("revision >= 1", name="ck_injection_import_batch_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_content_type: Mapped[str] = mapped_column(String(128), default="")
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64))
    detected_sheets_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    business_date: Mapped[str] = mapped_column(String(20), default="")
    draft_version_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_at: Mapped[str] = mapped_column(String(32), default="")
    confirm_reason: Mapped[str] = mapped_column(Text, default="")
    rejected_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    rejected_by_name: Mapped[str] = mapped_column(String(128), default="")
    rejected_at: Mapped[str] = mapped_column(String(32), default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")


class InjectionScheduleImportIssue(Base):
    __tablename__ = "injection_schedule_import_issues"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_import_issue_id_factory",
        ),
        ForeignKeyConstraint(
            ("batch_id", "factory_id"),
            (
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ),
            name="fk_injection_import_issue_batch_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="ck_injection_import_issue_severity",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    source_sheet: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(64), default="")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_value: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text)


class InjectionMachineMaster(Base):
    __tablename__ = "injection_machine_masters"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_machine_factory_code",
        ),
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_machine_id_factory",
        ),
        CheckConstraint(
            "status IN ('available', 'maintenance', 'stopped', 'retired')",
            name="ck_injection_machine_status",
        ),
        CheckConstraint("revision >= 1", name="ck_injection_machine_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_code: Mapped[str] = mapped_column(String(64))
    machine_name: Mapped[str] = mapped_column(String(128), default="")
    workshop: Mapped[str] = mapped_column(String(64), default="", index=True)
    machine_class: Mapped[str] = mapped_column(String(128), default="")
    tonnage_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    process_type: Mapped[str] = mapped_column(String(64), default="")
    screw_type: Mapped[str] = mapped_column(String(64), default="")
    robot_type: Mapped[str] = mapped_column(String(64), default="")
    fixture_type: Mapped[str] = mapped_column(String(64), default="")
    max_shot_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    tie_bar_x_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    tie_bar_y_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    mold_thickness_min_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    mold_thickness_max_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_stroke_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ejector_stroke_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    available_at: Mapped[str] = mapped_column(String(32), default="")
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    material_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    quality_status: Mapped[str] = mapped_column(String(32), default="incomplete", index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    source_batch_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionMoldMaster(Base):
    __tablename__ = "injection_mold_masters"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "normalized_mold_code",
            name="uq_injection_mold_factory_code",
        ),
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_mold_id_factory",
        ),
        CheckConstraint("revision >= 1", name="ck_injection_mold_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_code: Mapped[str] = mapped_column(String(128))
    normalized_mold_code: Mapped[str] = mapped_column(String(128))
    mold_name: Mapped[str] = mapped_column(String(255), default="")
    machine_class: Mapped[str] = mapped_column(String(128), default="")
    robot_type: Mapped[str] = mapped_column(String(64), default="")
    fixture_type: Mapped[str] = mapped_column(String(64), default="")
    length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    mold_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_shot_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    mold_thickness_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_opening_stroke_mm: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    required_screw_type: Mapped[str] = mapped_column(String(64), default="")
    cavities: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    material_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    quality_status: Mapped[str] = mapped_column(String(32), default="incomplete", index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    source_batch_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionOrderMaster(Base):
    __tablename__ = "injection_order_masters"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "natural_key",
            name="uq_injection_order_factory_natural_key",
        ),
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_order_id_factory",
        ),
        CheckConstraint(
            "status IN ('open', 'completed', 'canceled')",
            name="ck_injection_order_status",
        ),
        CheckConstraint(
            "priority_code IN ('P0', 'P1', 'P2', 'P3')",
            name="ck_injection_order_priority_code",
        ),
        CheckConstraint("order_qty >= 0", name="ck_injection_order_qty"),
        CheckConstraint("produced_qty >= 0", name="ck_injection_produced_qty"),
        CheckConstraint("outstanding_qty >= 0", name="ck_injection_outstanding_qty"),
        CheckConstraint("revision >= 1", name="ck_injection_order_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    natural_key: Mapped[str] = mapped_column(String(256))
    order_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    product_code: Mapped[str] = mapped_column(String(128), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    mold_code: Mapped[str] = mapped_column(String(128), default="", index=True)
    color: Mapped[str] = mapped_column(String(128), default="")
    pigment: Mapped[str] = mapped_column(String(128), default="")
    material: Mapped[str] = mapped_column(String(255), default="")
    machine_class: Mapped[str] = mapped_column(String(128), default="")
    order_qty: Mapped[float] = mapped_column(Float, default=0)
    produced_qty: Mapped[float] = mapped_column(Float, default=0)
    outstanding_qty: Mapped[float] = mapped_column(Float, default=0)
    daily_target_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_due_date: Mapped[str] = mapped_column(String(20), default="")
    priority_flag: Mapped[str] = mapped_column(String(32), default="")
    priority_code: Mapped[str] = mapped_column(
        String(2),
        default="P3",
        index=True,
    )
    color_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    downstream_urgency: Mapped[float | None] = mapped_column(Float, nullable=True)
    warehouse_buffer_hours: Mapped[float] = mapped_column(Float, default=0)
    downstream_buffer_hours: Mapped[float] = mapped_column(Float, default=0)
    special_handling_reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    imported_assigned_machine_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    imported_plan_start_at: Mapped[str] = mapped_column(String(32), default="")
    imported_plan_finish_at: Mapped[str] = mapped_column(String(32), default="")
    source_sheet: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int] = mapped_column(Integer, default=0)
    source_batch_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    source_values_json: Mapped[str] = mapped_column(Text, default="{}")
    quality_status: Mapped[str] = mapped_column(String(32), default="incomplete", index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionScheduleFactoryState(Base):
    __tablename__ = "injection_schedule_factory_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ("current_published_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_factory_state_published_version",
            use_alter=True,
        ),
        CheckConstraint("next_version_no >= 1", name="ck_injection_factory_next_version"),
        CheckConstraint("revision >= 1", name="ck_injection_factory_state_revision"),
    )

    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_published_version_id: Mapped[str | None] = mapped_column(
        String(96),
        nullable=True,
        default=None,
    )
    next_version_no: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionScheduleRuleConfig(Base):
    __tablename__ = "injection_schedule_rule_configs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_injection_rule_config_revision"),
    )

    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionScheduleVersion(Base):
    __tablename__ = "injection_schedule_versions"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "version_no",
            name="uq_injection_schedule_version_factory_no",
        ),
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_schedule_version_id_factory",
        ),
        ForeignKeyConstraint(
            ("base_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_schedule_version_base_factory",
            use_alter=True,
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'superseded')",
            name="ck_injection_schedule_version_status",
        ),
        CheckConstraint("revision >= 1", name="ck_injection_schedule_version_revision"),
        Index(
            "uq_injection_schedule_one_published_per_factory",
            "factory_id",
            unique=True,
            sqlite_where=text("status = 'published'"),
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    business_date: Mapped[str] = mapped_column(String(20), default="")
    plan_base_at: Mapped[str] = mapped_column(String(32))
    base_version_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    source_batch_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    rules_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    rule_config_revision: Mapped[int] = mapped_column(Integer, default=0)
    data_hash: Mapped[str] = mapped_column(String(64), default="")
    validation_hash: Mapped[str] = mapped_column(String(64), default="")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")
    published_by: Mapped[str] = mapped_column(String(64), default="")
    published_by_name: Mapped[str] = mapped_column(String(128), default="")
    published_at: Mapped[str] = mapped_column(String(32), default="")
    publish_reason: Mapped[str] = mapped_column(Text, default="")
    superseded_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionScheduleTask(Base):
    __tablename__ = "injection_schedule_tasks"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_schedule_task_id_factory",
        ),
        UniqueConstraint(
            "id",
            "version_id",
            "factory_id",
            name="uq_injection_schedule_task_id_version_factory",
        ),
        UniqueConstraint(
            "version_id",
            "machine_id",
            "sequence_no",
            name="uq_injection_schedule_task_machine_sequence",
        ),
        ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_schedule_task_version_factory",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("order_id", "factory_id"),
            (
                "injection_order_masters.id",
                "injection_order_masters.factory_id",
            ),
            name="fk_injection_schedule_task_order_factory",
        ),
        ForeignKeyConstraint(
            ("machine_id", "factory_id"),
            (
                "injection_machine_masters.id",
                "injection_machine_masters.factory_id",
            ),
            name="fk_injection_schedule_task_machine_factory",
        ),
        ForeignKeyConstraint(
            ("mold_id", "factory_id"),
            (
                "injection_mold_masters.id",
                "injection_mold_masters.factory_id",
            ),
            name="fk_injection_schedule_task_mold_factory",
        ),
        CheckConstraint("sequence_no >= 0", name="ck_injection_schedule_task_sequence"),
        CheckConstraint("planned_qty > 0", name="ck_injection_schedule_task_qty"),
        CheckConstraint("revision >= 1", name="ck_injection_schedule_task_revision"),
        CheckConstraint(
            "source IN ('import', 'manual', 'recommendation', 'auto', 'legacy')",
            name="ck_injection_schedule_task_source",
        ),
        CheckConstraint(
            "execution_status IN ('planned', 'running', 'completed', 'cancelled')",
            name="ck_injection_schedule_task_execution_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[str] = mapped_column(String(96), index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    mold_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    planned_qty: Mapped[float] = mapped_column(Float)
    planned_start_at: Mapped[str] = mapped_column(String(32), default="")
    planned_finish_at: Mapped[str] = mapped_column(String(32), default="")
    setup_hours: Mapped[float] = mapped_column(Float, default=0)
    duration_hours: Mapped[float] = mapped_column(Float, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    split_group_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    parent_task_id: Mapped[str] = mapped_column(String(96), default="")
    order_no_snapshot: Mapped[str] = mapped_column(String(128), default="")
    product_code_snapshot: Mapped[str] = mapped_column(String(128), default="")
    product_name_snapshot: Mapped[str] = mapped_column(String(255), default="")
    delivery_due_date_snapshot: Mapped[str] = mapped_column(String(20), default="")
    mold_code_snapshot: Mapped[str] = mapped_column(String(128), default="")
    color_snapshot: Mapped[str] = mapped_column(String(128), default="")
    color_rank_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    material_snapshot: Mapped[str] = mapped_column(String(255), default="")
    machine_code_snapshot: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(32), default="legacy", index=True)
    execution_status: Mapped[str] = mapped_column(
        String(32),
        default="planned",
        index=True,
    )
    protected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    recommendation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown_json: Mapped[str] = mapped_column(Text, default="[]")
    constraint_snapshot_json: Mapped[str] = mapped_column(Text, default="[]")
    recommendation_context_hash: Mapped[str] = mapped_column(
        String(64),
        default="",
        index=True,
    )
    risk_level: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    risk_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    order_revision_snapshot: Mapped[int] = mapped_column(Integer)
    machine_revision_snapshot: Mapped[int] = mapped_column(Integer)
    mold_revision_snapshot: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionScheduleReplanRun(Base):
    __tablename__ = "injection_schedule_replan_runs"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_replan_run_id_factory",
        ),
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_replan_run_factory_request",
        ),
        ForeignKeyConstraint(
            ("source_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_replan_run_source_version_factory",
        ),
        ForeignKeyConstraint(
            ("result_version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_replan_run_result_version_factory",
        ),
        CheckConstraint(
            "trigger_type IN "
            "('auto_draft', 'urgent_order', 'machine_downtime', 'shift_actual')",
            name="ck_injection_replan_run_trigger_type",
        ),
        CheckConstraint(
            "status IN ('previewed', 'applied')",
            name="ck_injection_replan_run_status",
        ),
        CheckConstraint(
            "source_revision >= 1",
            name="ck_injection_replan_run_source_revision",
        ),
        CheckConstraint(
            "result_revision >= 1",
            name="ck_injection_replan_run_result_revision",
        ),
        CheckConstraint(
            "source_version_id <> result_version_id",
            name="ck_injection_replan_run_distinct_versions",
        ),
        CheckConstraint(
            "length(context_hash) = 64",
            name="ck_injection_replan_run_context_hash",
        ),
        CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_replan_run_request_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_version_id: Mapped[str] = mapped_column(String(96), index=True)
    result_version_id: Mapped[str] = mapped_column(String(96), index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    result_revision: Mapped[int] = mapped_column(Integer)
    context_hash: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    affected_machine_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    affected_order_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    affected_task_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    impact_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionScheduleShiftActual(Base):
    __tablename__ = "injection_schedule_shift_actuals"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_shift_actual_id_factory",
        ),
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_shift_actual_factory_request",
        ),
        UniqueConstraint(
            "factory_id",
            "source_task_id",
            "shift_date",
            "shift",
            name="uq_injection_shift_actual_source_task_shift",
        ),
        UniqueConstraint(
            "factory_id",
            "source_task_id",
            "lineage_sequence",
            name="uq_injection_shift_actual_source_task_sequence",
        ),
        ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_shift_actual_version_factory",
        ),
        ForeignKeyConstraint(
            ("task_id", "version_id", "factory_id"),
            (
                "injection_schedule_tasks.id",
                "injection_schedule_tasks.version_id",
                "injection_schedule_tasks.factory_id",
            ),
            name="fk_injection_shift_actual_task_version_factory",
        ),
        ForeignKeyConstraint(
            ("source_task_id", "source_version_id", "factory_id"),
            (
                "injection_schedule_tasks.id",
                "injection_schedule_tasks.version_id",
                "injection_schedule_tasks.factory_id",
            ),
            name="fk_injection_shift_actual_source_task_version_factory",
        ),
        ForeignKeyConstraint(
            ("order_id", "factory_id"),
            (
                "injection_order_masters.id",
                "injection_order_masters.factory_id",
            ),
            name="fk_injection_shift_actual_order_factory",
        ),
        ForeignKeyConstraint(
            ("machine_id", "factory_id"),
            (
                "injection_machine_masters.id",
                "injection_machine_masters.factory_id",
            ),
            name="fk_injection_shift_actual_machine_factory",
        ),
        CheckConstraint(
            "shift IN ('day', 'night')",
            name="ck_injection_shift_actual_shift",
        ),
        CheckConstraint(
            "source IN ('manual', 'workbook')",
            name="ck_injection_shift_actual_source",
        ),
        CheckConstraint(
            "actual_qty >= 0",
            name="ck_injection_shift_actual_qty",
        ),
        CheckConstraint(
            "produced_baseline_qty >= 0",
            name="ck_injection_shift_actual_baseline",
        ),
        CheckConstraint(
            "outstanding_qty_before >= 0 AND outstanding_qty_after >= 0",
            name="ck_injection_shift_actual_outstanding",
        ),
        CheckConstraint(
            "shortage_qty >= 0",
            name="ck_injection_shift_actual_shortage",
        ),
        CheckConstraint(
            "revision >= 1 AND correction_count >= 0",
            name="ck_injection_shift_actual_revision",
        ),
        CheckConstraint(
            "lineage_sequence >= 1",
            name="ck_injection_shift_actual_lineage_sequence",
        ),
        CheckConstraint(
            "outstanding_qty_after <= outstanding_qty_before",
            name="ck_injection_shift_actual_outstanding_direction",
        ),
        CheckConstraint(
            "abs((outstanding_qty_before - actual_qty) - "
            "outstanding_qty_after) <= 0.000001",
            name="ck_injection_shift_actual_authoritative_balance",
        ),
        CheckConstraint(
            "shortage_qty <= task_planned_qty_before",
            name="ck_injection_shift_actual_task_balance",
        ),
        CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_injection_shift_actual_payload_hash",
        ),
        CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_shift_actual_request_id",
        ),
        CheckConstraint(
            "(correction_count = 0 "
            "AND last_correction_request_id = '' "
            "AND last_correction_payload_hash = '') "
            "OR (correction_count > 0 "
            "AND length(trim(last_correction_request_id)) > 0 "
            "AND length(last_correction_payload_hash) = 64)",
            name="ck_injection_shift_actual_correction_trace",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[str] = mapped_column(String(96), index=True)
    task_id: Mapped[str] = mapped_column(String(96), index=True)
    source_version_id: Mapped[str] = mapped_column(String(96), index=True)
    source_task_id: Mapped[str] = mapped_column(String(96), index=True)
    lineage_sequence: Mapped[int] = mapped_column(Integer, index=True)
    order_id: Mapped[str] = mapped_column(String(96), index=True)
    machine_id: Mapped[str] = mapped_column(String(96), index=True)
    shift_date: Mapped[str] = mapped_column(String(20), index=True)
    shift: Mapped[str] = mapped_column(String(16), index=True)
    legacy_shift_code: Mapped[str] = mapped_column(String(8), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual", index=True)
    target_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_qty: Mapped[float] = mapped_column(Float)
    variance_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_reason: Mapped[str] = mapped_column(Text, default="")
    produced_baseline_qty: Mapped[float] = mapped_column(Float)
    outstanding_qty_before: Mapped[float] = mapped_column(Float)
    outstanding_qty_after: Mapped[float] = mapped_column(Float)
    shortage_qty: Mapped[float] = mapped_column(Float)
    task_planned_qty_before: Mapped[float] = mapped_column(Float)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    projection_json: Mapped[str] = mapped_column(Text, default="[]")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    correction_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    corrected_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    corrected_by_name: Mapped[str] = mapped_column(String(128), default="")
    corrected_at: Mapped[str] = mapped_column(String(32), default="")
    last_correction_request_id: Mapped[str] = mapped_column(
        String(128),
        default="",
        index=True,
    )
    last_correction_payload_hash: Mapped[str] = mapped_column(
        String(64),
        default="",
    )


class InjectionScheduleActualCorrection(Base):
    __tablename__ = "injection_schedule_actual_corrections"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_actual_correction_id_factory",
        ),
        UniqueConstraint(
            "factory_id",
            "request_id",
            name="uq_injection_actual_correction_factory_request",
        ),
        UniqueConstraint(
            "factory_id",
            "actual_id",
            "result_actual_revision",
            name="uq_injection_actual_correction_actual_revision",
        ),
        ForeignKeyConstraint(
            ("actual_id", "factory_id"),
            (
                "injection_schedule_shift_actuals.id",
                "injection_schedule_shift_actuals.factory_id",
            ),
            name="fk_injection_actual_correction_actual_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "previous_actual_qty >= 0 AND corrected_actual_qty >= 0",
            name="ck_injection_actual_correction_qty",
        ),
        CheckConstraint(
            "previous_actual_revision >= 1 "
            "AND result_actual_revision = previous_actual_revision + 1",
            name="ck_injection_actual_correction_revision",
        ),
        CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_injection_actual_correction_payload_hash",
        ),
        CheckConstraint(
            "length(trim(request_id)) > 0",
            name="ck_injection_actual_correction_request_id",
        ),
        CheckConstraint(
            "length(trim(response_json)) > 2",
            name="ck_injection_actual_correction_response",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    actual_id: Mapped[str] = mapped_column(String(96), index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    previous_actual_qty: Mapped[float] = mapped_column(Float)
    corrected_actual_qty: Mapped[float] = mapped_column(Float)
    previous_actual_revision: Mapped[int] = mapped_column(Integer)
    result_actual_revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionScheduleValidationRun(Base):
    __tablename__ = "injection_schedule_validation_runs"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_validation_run_id_factory",
        ),
        ForeignKeyConstraint(
            ("version_id", "factory_id"),
            (
                "injection_schedule_versions.id",
                "injection_schedule_versions.factory_id",
            ),
            name="fk_injection_validation_run_version_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('passed', 'blocked')",
            name="ck_injection_validation_run_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[str] = mapped_column(String(96), index=True)
    version_revision: Mapped[int] = mapped_column(Integer)
    data_hash: Mapped[str] = mapped_column(String(64), index=True)
    result_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)
    blocking_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionScheduleValidationItem(Base):
    __tablename__ = "injection_schedule_validation_items"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_validation_item_id_factory",
        ),
        ForeignKeyConstraint(
            ("run_id", "factory_id"),
            (
                "injection_schedule_validation_runs.id",
                "injection_schedule_validation_runs.factory_id",
            ),
            name="fk_injection_validation_item_run_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pass', 'fail', 'unknown')",
            name="ck_injection_validation_item_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    version_id: Mapped[str] = mapped_column(String(96), index=True)
    task_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    constraint_code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")


class InjectionScheduleAuditEvent(Base):
    __tablename__ = "injection_schedule_audit_events"
    __table_args__ = (
        UniqueConstraint(
            *FACTORY_SCOPED_ID_CONSTRAINT,
            name="uq_injection_audit_event_id_factory",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str] = mapped_column(String(128), default="")
    ip_address: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    old_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


@event.listens_for(InjectionScheduleAuditEvent, "before_update")
@event.listens_for(InjectionScheduleAuditEvent, "before_delete")
def _reject_injection_schedule_audit_mutation(*_args) -> None:
    raise ValueError("injection schedule audit events are append-only")
