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
        CheckConstraint(
            "status IN ('available', 'running', 'maintenance', 'offline')",
            name="ck_injection_scheduling_machine_status",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_machine_revision",
        ),
        CheckConstraint(
            "machine_a_class IS NULL OR machine_a_class > 0",
            name="ck_injection_scheduling_machine_a_class",
        ),
        CheckConstraint(
            "normalization_status IN ('COMPLETE', 'REVIEW_REQUIRED')",
            name="ck_injection_scheduling_machine_normalization_status",
        ),
        Index(
            "ix_injection_scheduling_machine_factory_status_code",
            "factory_id",
            "status",
            "machine_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_code: Mapped[str] = mapped_column(String(64), index=True)
    area: Mapped[str] = mapped_column(String(128), default="")
    position: Mapped[str] = mapped_column(String(128), default="")
    machine_class: Mapped[str] = mapped_column(String(64), default="", index=True)
    machine_class_raw: Mapped[str] = mapped_column(String(128), default="")
    machine_a_class: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 3), nullable=True, index=True
    )
    normalization_status: Mapped[str] = mapped_column(
        String(32), default="REVIEW_REQUIRED", index=True
    )
    process_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    special_machine_type: Mapped[str] = mapped_column(String(64), default="")
    clamping_force_tons: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    injection_capacity_g: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    tie_bar_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    tie_bar_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    platen_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    platen_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    min_mold_thickness_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    max_mold_thickness_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    opening_stroke_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    machine_type: Mapped[str] = mapped_column(String(64), default="standard")
    robot_capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    fixture_capabilities_json: Mapped[str] = mapped_column(Text, default="[]")
    process_restrictions_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


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
            ["definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_shared_definition",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('available', 'maintenance', 'not_arrived', "
            "'occupied', 'retired')",
            name="ck_injection_scheduling_mold_status",
        ),
        CheckConstraint(
            "data_quality_status IN ('complete', 'needs_review')",
            name="ck_injection_scheduling_mold_data_quality",
        ),
        CheckConstraint(
            "copy_count >= 1",
            name="ck_injection_scheduling_mold_copy_count",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_mold_revision",
        ),
        CheckConstraint(
            "mold_a_class IS NULL OR mold_a_class > 0",
            name="ck_injection_scheduling_mold_a_class",
        ),
        CheckConstraint(
            "normalization_status IN ('COMPLETE', 'REVIEW_REQUIRED')",
            name="ck_injection_scheduling_mold_normalization_status",
        ),
        Index(
            "ix_injection_scheduling_mold_factory_status_no",
            "factory_id",
            "status",
            "mold_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    definition_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_no: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    length_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    recommended_machine_class: Mapped[str] = mapped_column(
        String(64), default="", index=True
    )
    mold_class_raw: Mapped[str] = mapped_column(String(128), default="")
    mold_a_class: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 3), nullable=True, index=True
    )
    normalization_status: Mapped[str] = mapped_column(
        String(32), default="REVIEW_REQUIRED", index=True
    )
    process_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    special_machine_type: Mapped[str] = mapped_column(String(64), default="")
    whole_shot_net_weight_g: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    whole_shot_gross_weight_g: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    required_arm_type: Mapped[str] = mapped_column(String(64), default="")
    required_fixture_type: Mapped[str] = mapped_column(String(128), default="")
    material_code: Mapped[str] = mapped_column(String(128), default="", index=True)
    material_name: Mapped[str] = mapped_column(String(255), default="")
    color_profile: Mapped[str] = mapped_column(String(128), default="")
    process_requirements_json: Mapped[str] = mapped_column(Text, default="[]")
    copy_count: Mapped[int] = mapped_column(Integer, default=1)
    data_quality_status: Mapped[str] = mapped_column(
        String(32), default="needs_review", index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


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
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_injection_scheduling_rule_status",
        ),
        CheckConstraint(
            "configured_max_utilization > 0 AND configured_max_utilization <= 1",
            name="ck_injection_scheduling_rule_utilization",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_rule_revision",
        ),
        Index(
            "ix_injection_scheduling_rule_factory_status_revision",
            "factory_id",
            "status",
            "revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    configured_max_utilization: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("1.0")
    )
    allow_mold_rotation_90: Mapped[bool] = mapped_column(Boolean, default=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    superseded_at: Mapped[str] = mapped_column(String(32), default="")
