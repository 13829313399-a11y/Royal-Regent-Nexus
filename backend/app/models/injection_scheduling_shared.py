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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InjectionSchedulingRolloutPolicy(Base):
    __tablename__ = "injection_scheduling_rollout_policies"
    __table_args__ = (
        CheckConstraint(
            "demand_mode IN ('SHADOW', 'PREVIEW_ONLY', 'MANUAL_CONFIRM', 'AUTO_ENRICH')",
            name="ck_inj_sched_rollout_demand_mode",
        ),
        CheckConstraint(
            "master_data_mode IN ('PROPOSAL_ONLY', 'APPROVAL_ACTIVE')",
            name="ck_inj_sched_rollout_master_mode",
        ),
        CheckConstraint(
            "business_contract_status IN ('UNSIGNED', 'SIGNED')",
            name="ck_inj_sched_rollout_contract_status",
        ),
        CheckConstraint(
            "tentative_hold_ttl_minutes BETWEEN 5 AND 120",
            name="ck_inj_sched_rollout_hold_ttl",
        ),
    )

    factory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    demand_mode: Mapped[str] = mapped_column(
        String(24), default="MANUAL_CONFIRM", index=True
    )
    master_data_mode: Mapped[str] = mapped_column(
        String(24), default="PROPOSAL_ONLY", index=True
    )
    business_contract_status: Mapped[str] = mapped_column(
        String(16), default="UNSIGNED", index=True
    )
    price_activation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tentative_hold_ttl_minutes: Mapped[int] = mapped_column(Integer, default=30)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingCompanyScope(Base):
    __tablename__ = "injection_scheduling_company_scopes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_inj_sched_company_scope_code"),
        CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_inj_sched_company_scope_status",
        ),
        CheckConstraint("revision >= 1", name="ck_inj_sched_company_scope_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    code: Mapped[str] = mapped_column(String(96), index=True)
    name: Mapped[str] = mapped_column(String(255))
    legal_entity_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingCompanyFactoryMembership(Base):
    __tablename__ = "injection_scheduling_company_factory_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_company_factory_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("factory_id", name="uq_inj_sched_company_factory"),
        CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_inj_sched_company_factory_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingCustomerIdentity(Base):
    __tablename__ = "injection_scheduling_customer_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_customer_company_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_scope_id", "customer_code", name="uq_inj_sched_customer_code"
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'ACTIVE', 'RETIRED')",
            name="ck_inj_sched_customer_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    company_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    customer_code: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingCustomerAlias(Base):
    __tablename__ = "injection_scheduling_customer_aliases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_customer_alias_company_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_identity_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_customer_alias_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_scope_id",
            "source_namespace_id",
            "normalized_alias",
            "valid_from",
            name="uq_inj_sched_customer_alias_effective",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_customer_alias_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    company_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    customer_identity_id: Mapped[str] = mapped_column(String(96), index=True)
    source_namespace_id: Mapped[str] = mapped_column(String(128), index=True)
    raw_alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingMoldDefinition(Base):
    __tablename__ = "injection_scheduling_mold_definitions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_mold_definition_company_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_scope_id",
            "canonical_mold_no",
            name="uq_inj_sched_mold_definition_number",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_definition_status",
        ),
        CheckConstraint(
            "mold_a_class IS NULL OR mold_a_class > 0",
            name="ck_inj_sched_mold_definition_a_class",
        ),
        Index(
            "ix_inj_sched_mold_definition_company_status",
            "company_scope_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    company_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    canonical_mold_no: Mapped[str] = mapped_column(String(128), index=True)
    display_mold_no: Mapped[str] = mapped_column(String(128))
    standard_name: Mapped[str] = mapped_column(String(255), default="")
    recommended_machine_class_raw: Mapped[str] = mapped_column(String(128), default="")
    mold_a_class: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    default_arm_type: Mapped[str] = mapped_column(String(64), default="")
    default_fixture_type: Mapped[str] = mapped_column(String(64), default="")
    process_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    engineering_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    data_quality: Mapped[str] = mapped_column(String(32), default="REVIEW_REQUIRED")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    created_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    approved_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingMoldAlias(Base):
    __tablename__ = "injection_scheduling_mold_aliases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_scope_id"],
            ["injection_scheduling_company_scopes.id"],
            name="fk_inj_sched_mold_alias_company_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_alias_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_scope_id",
            "source_namespace_id",
            "normalized_alias",
            "valid_from",
            name="uq_inj_sched_mold_alias_effective",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_alias_status",
        ),
        Index(
            "ix_inj_sched_mold_alias_lookup",
            "company_scope_id",
            "source_namespace_id",
            "normalized_alias",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    company_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    source_namespace_id: Mapped[str] = mapped_column(String(128), index=True)
    namespace_type: Mapped[str] = mapped_column(String(32), default="FACTORY_SOURCE")
    raw_alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    mold_definition_id: Mapped[str] = mapped_column(String(96), index=True)
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingMoldOutputSpec(Base):
    __tablename__ = "injection_scheduling_mold_output_specs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_output_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["customer_identity_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_mold_output_customer",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "mold_definition_id",
            "customer_identity_id",
            "item_no",
            "variant_code",
            "valid_from",
            name="uq_inj_sched_mold_output_effective",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_mold_output_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    mold_definition_id: Mapped[str] = mapped_column(String(96), index=True)
    customer_identity_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    item_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    variant_code: Mapped[str] = mapped_column(String(128), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    cavity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_per_shot: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    whole_shot_net_weight_g: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    whole_shot_gross_weight_g: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    default_material: Mapped[str] = mapped_column(String(255), default="")
    default_color: Mapped[str] = mapped_column(String(128), default="")
    nominal_cycle_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    nominal_daily_capacity: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingPhysicalMoldAsset(Base):
    __tablename__ = "injection_scheduling_physical_mold_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_mold_asset_definition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "owner_scope_type",
            "owner_scope_id",
            "asset_code",
            name="uq_inj_sched_mold_asset_code",
        ),
        CheckConstraint(
            "status IN ('LEGACY_UNVERIFIED', 'AVAILABLE', 'MAINTENANCE', 'LOANED', 'IN_TRANSIT', 'RETIRED')",
            name="ck_inj_sched_mold_asset_status",
        ),
        CheckConstraint(
            "owner_scope_type IN ('COMPANY', 'FACTORY', 'LEGAL_ENTITY')",
            name="ck_inj_sched_mold_asset_owner_scope",
        ),
        Index(
            "ix_inj_sched_mold_asset_factory_status",
            "current_factory_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    mold_definition_id: Mapped[str] = mapped_column(String(96), index=True)
    owner_scope_type: Mapped[str] = mapped_column(String(24))
    owner_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    asset_code: Mapped[str] = mapped_column(String(128), index=True)
    serial_no: Mapped[str] = mapped_column(String(128), default="")
    current_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    current_location: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(
        String(24), default="LEGACY_UNVERIFIED", index=True
    )
    actual_cavity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_from: Mapped[str] = mapped_column(String(32), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    source_mold_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    source_copy_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_by: Mapped[str] = mapped_column(String(64), default="")
    verified_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingMoldAssetMovement(Base):
    __tablename__ = "injection_scheduling_mold_asset_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_mold_movement_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "physical_asset_id", "request_id", name="uq_inj_sched_mold_movement_request"
        ),
        CheckConstraint(
            "status IN ('PLANNED', 'APPROVED', 'EFFECTIVE', 'CANCELLED')",
            name="ck_inj_sched_mold_movement_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    physical_asset_id: Mapped[str] = mapped_column(String(96), index=True)
    movement_type: Mapped[str] = mapped_column(String(32))
    from_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    to_factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    from_location: Mapped[str] = mapped_column(String(255), default="")
    to_location: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="PLANNED", index=True)
    effective_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingMoldReservation(Base):
    __tablename__ = "injection_scheduling_mold_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_mold_reservation_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "factory_id", "idempotency_key", name="uq_inj_sched_mold_reservation_key"
        ),
        CheckConstraint(
            "status IN ('TENTATIVE', 'ACTIVE', 'RELEASED', 'CANCELLED', 'EXPIRED')",
            name="ck_inj_sched_mold_reservation_status",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_inj_sched_mold_reservation_window",
        ),
        Index(
            "ix_inj_sched_mold_reservation_asset_window",
            "physical_asset_id",
            "window_start",
            "window_end",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    physical_asset_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    task_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    window_start: Mapped[str] = mapped_column(String(32), index=True)
    window_end: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="TENTATIVE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="SCHEDULING_PREVIEW")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    released_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingFactoryMoldCapability(Base):
    __tablename__ = "injection_scheduling_factory_mold_capabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_factory_capability_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_factory_capability_output",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_factory_capability_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "factory_id",
            "applicability_key",
            "priority",
            "valid_from",
            name="uq_inj_sched_factory_capability_effective",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_factory_capability_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_definition_id: Mapped[str] = mapped_column(String(96), index=True)
    mold_output_spec_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    physical_asset_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    machine_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applicability_key: Mapped[str] = mapped_column(String(64), index=True)
    required_arm_type: Mapped[str] = mapped_column(String(64), default="")
    required_fixture_type: Mapped[str] = mapped_column(String(64), default="")
    process_limits_json: Mapped[str] = mapped_column(Text, default="{}")
    nominal_cycle_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    nominal_daily_capacity: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    setup_minutes: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    approved_by: Mapped[str] = mapped_column(String(64), default="")
    approved_at: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingCommercialRateRule(Base):
    __tablename__ = "injection_scheduling_commercial_rate_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_rate_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_rate_output",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["applicable_customer_id"],
            ["injection_scheduling_customer_identities.id"],
            name="fk_inj_sched_rate_customer",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "owner_scope_type IN ('COMPANY', 'FACTORY', 'LEGAL_ENTITY')",
            name="ck_inj_sched_rate_owner_scope",
        ),
        CheckConstraint(
            "applicable_factory_mode IN ('SPECIFIC', 'ANY_IN_OWNER_COMPANY', 'ANY_IN_OWNER_LEGAL_ENTITY')",
            name="ck_inj_sched_rate_factory_mode",
        ),
        CheckConstraint(
            "applicable_customer_mode IN ('SPECIFIC', 'ANY')",
            name="ck_inj_sched_rate_customer_mode",
        ),
        CheckConstraint(
            "pricing_basis IN ('PER_SHOT', 'PER_PIECE', 'PER_SET', 'PER_HOUR')",
            name="ck_inj_sched_rate_pricing_basis",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'APPROVED', 'ACTIVE', 'SUPERSEDED', 'RETIRED', 'REJECTED')",
            name="ck_inj_sched_rate_status",
        ),
        CheckConstraint("amount >= 0", name="ck_inj_sched_rate_amount"),
        CheckConstraint(
            "(applicable_factory_mode = 'SPECIFIC' AND applicable_factory_id IS NOT NULL) "
            "OR (applicable_factory_mode <> 'SPECIFIC' AND applicable_factory_id IS NULL)",
            name="ck_inj_sched_rate_factory_scope_shape",
        ),
        CheckConstraint(
            "(applicable_customer_mode = 'SPECIFIC' AND applicable_customer_id IS NOT NULL) "
            "OR (applicable_customer_mode = 'ANY' AND applicable_customer_id IS NULL)",
            name="ck_inj_sched_rate_customer_scope_shape",
        ),
        CheckConstraint(
            "(contract_mode = 'SPECIFIC' AND contract_id IS NOT NULL) "
            "OR (contract_mode = 'ANY' AND contract_id IS NULL)",
            name="ck_inj_sched_rate_contract_scope_shape",
        ),
        CheckConstraint(
            "owner_scope_type <> 'FACTORY' OR "
            "(applicable_factory_mode = 'SPECIFIC' AND owner_scope_id = applicable_factory_id)",
            name="ck_inj_sched_rate_factory_owner_scope",
        ),
        CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0",
            name="ck_inj_sched_rate_quantity_min",
        ),
        CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= 0",
            name="ck_inj_sched_rate_quantity_max",
        ),
        CheckConstraint(
            "quantity_min IS NULL OR quantity_max IS NULL OR quantity_min <= quantity_max",
            name="ck_inj_sched_rate_quantity_range",
        ),
        CheckConstraint(
            "approved_by = '' OR proposed_by = '' OR approved_by <> proposed_by",
            name="ck_inj_sched_rate_approval_separation",
        ),
        Index(
            "ix_inj_sched_rate_resolution",
            "status",
            "applicable_factory_id",
            "applicable_customer_id",
            "mold_output_spec_id",
            "valid_from",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    owner_scope_type: Mapped[str] = mapped_column(String(24))
    owner_scope_id: Mapped[str] = mapped_column(String(96), index=True)
    applicable_factory_mode: Mapped[str] = mapped_column(String(40))
    applicable_factory_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    applicable_customer_mode: Mapped[str] = mapped_column(String(16))
    applicable_customer_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_definition_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_output_spec_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    contract_mode: Mapped[str] = mapped_column(String(16), default="ANY")
    contract_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pricing_basis: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(8))
    tax_mode: Mapped[str] = mapped_column(String(32))
    quantity_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[str] = mapped_column(String(32), default="")
    valid_to: Mapped[str] = mapped_column(String(32), default="")
    proposal_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    proposed_by: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    approved_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingMasterDataProposal(Base):
    __tablename__ = "injection_scheduling_master_data_proposals"
    __table_args__ = (
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "request_id",
            name="uq_inj_sched_master_proposal_request",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'UNDER_REVIEW', 'APPROVED', 'ACTIVE', 'REJECTED', 'SUPERSEDED', 'RETIRED')",
            name="ck_inj_sched_master_proposal_status",
        ),
        CheckConstraint(
            "action_type IN ('CREATE', 'REVISE', 'MERGE', 'SPLIT', 'RETIRE', 'ALIAS_REDIRECT', 'ACTIVATE')",
            name="ck_inj_sched_master_proposal_action",
        ),
        CheckConstraint(
            "approved_by = '' OR approved_by <> proposed_by",
            name="ck_inj_sched_master_proposal_approval_separation",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(24), index=True)
    target_entity_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    scope_type: Mapped[str] = mapped_column(String(24), index=True)
    scope_id: Mapped[str] = mapped_column(String(96), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    evidence_digest: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    proposed_by: Mapped[str] = mapped_column(String(64), index=True)
    proposed_by_name: Mapped[str] = mapped_column(String(128), default="")
    approved_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    approved_by_name: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    reviewed_at: Mapped[str] = mapped_column(String(32), default="")


class InjectionSchedulingFieldEvidence(Base):
    __tablename__ = "injection_scheduling_field_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proposal_id"],
            ["injection_scheduling_master_data_proposals.id"],
            name="fk_inj_sched_field_evidence_proposal",
            ondelete="CASCADE",
        ),
        Index(
            "ix_inj_sched_field_evidence_entity_field",
            "entity_type",
            "entity_id",
            "field_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    proposal_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    field_name: Mapped[str] = mapped_column(String(128), index=True)
    source_file_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    sheet_name: Mapped[str] = mapped_column(String(128), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cell_ref: Mapped[str] = mapped_column(String(32), default="")
    raw_value: Mapped[str] = mapped_column(Text, default="")
    displayed_value: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(24), default="SOURCE_FACT")
    submitted_by: Mapped[str] = mapped_column(String(64), default="")
    approved_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingDemandOrderIdentity(Base):
    __tablename__ = "injection_scheduling_demand_order_identities"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "source_system",
            "source_namespace_id",
            "source_order_line_id",
            name="uq_inj_sched_demand_order_source_line",
        ),
        UniqueConstraint(
            "factory_id", "stable_line_key", name="uq_inj_sched_demand_order_stable_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    source_namespace_id: Mapped[str] = mapped_column(String(128), index=True)
    source_document_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    source_order_line_id: Mapped[str] = mapped_column(String(128), index=True)
    stable_line_key: Mapped[str] = mapped_column(String(64), index=True)
    current_revision_no: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingDemandOrderVersion(Base):
    __tablename__ = "injection_scheduling_demand_order_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_identity_id"],
            ["injection_scheduling_demand_order_identities.id"],
            name="fk_inj_sched_demand_version_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mold_definition_id"],
            ["injection_scheduling_mold_definitions.id"],
            name="fk_inj_sched_demand_version_definition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mold_output_spec_id"],
            ["injection_scheduling_mold_output_specs.id"],
            name="fk_inj_sched_demand_version_output",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "order_identity_id",
            "source_revision",
            name="uq_inj_sched_demand_version_revision",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED')",
            name="ck_inj_sched_demand_version_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    order_identity_id: Mapped[str] = mapped_column(String(96), index=True)
    source_revision: Mapped[str] = mapped_column(String(128), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    customer_identity_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    source_document_no: Mapped[str] = mapped_column(String(128), index=True)
    item_no: Mapped[str] = mapped_column(String(128), default="", index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    mold_definition_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_output_spec_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    factory_mold_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    order_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    set_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    required_shots: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    delivery_due_date: Mapped[str] = mapped_column(String(32), default="", index=True)
    warehouse_text: Mapped[str] = mapped_column(String(255), default="")
    material_name: Mapped[str] = mapped_column(String(255), default="")
    color_name: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    readiness_status: Mapped[str] = mapped_column(
        String(32), default="NOT_FACTORY_READY", index=True
    )
    commercial_rate_rule_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    frozen_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    frozen_currency: Mapped[str] = mapped_column(String(8), default="")
    frozen_pricing_basis: Mapped[str] = mapped_column(String(16), default="")
    canonical_json: Mapped[str] = mapped_column(Text)
    provenance_json: Mapped[str] = mapped_column(Text)
    source_lineage_json: Mapped[str] = mapped_column(Text)
    version_digest: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingDemandImportRow(Base):
    __tablename__ = "injection_scheduling_demand_import_rows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_scheduling_import_batches.id",
                "injection_scheduling_import_batches.factory_id",
            ],
            name="fk_inj_sched_demand_import_row_batch",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            "preview_generation",
            "source_sheet_name",
            "source_row",
            name="uq_inj_sched_demand_import_row_source",
        ),
        CheckConstraint(
            "resolution_status IN ('READY', 'AUTO_CONFIRMED', 'REVIEW_REQUIRED', 'IDENTITY_REVIEW_REQUIRED', 'AMBIGUOUS', 'NOT_FOUND', 'PRICE_REVIEW_REQUIRED', 'CONFLICT', 'INVALID', 'DUPLICATE', 'UPDATE', 'REMOVAL_REVIEW')",
            name="ck_inj_sched_demand_import_row_resolution",
        ),
        CheckConstraint(
            "confirmation_state IN ('PENDING', 'CONFIRMED', 'SKIPPED', 'RETAINED_FINAL')",
            name="ck_inj_sched_demand_import_row_confirmation",
        ),
        Index(
            "ix_inj_sched_demand_import_row_batch_status",
            "batch_id",
            "preview_generation",
            "resolution_status",
            "confirmation_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    preview_generation: Mapped[int] = mapped_column(Integer, default=1, index=True)
    source_sheet_name: Mapped[str] = mapped_column(String(128))
    source_row: Mapped[int] = mapped_column(Integer)
    source_order_line_id: Mapped[str] = mapped_column(String(128), default="")
    source_revision: Mapped[str] = mapped_column(String(128), default="")
    stable_line_key: Mapped[str] = mapped_column(String(64), index=True)
    identity_quality: Mapped[str] = mapped_column(String(32), default="FALLBACK")
    canonical_json: Mapped[str] = mapped_column(Text)
    source_lineage_json: Mapped[str] = mapped_column(Text)
    resolution_status: Mapped[str] = mapped_column(String(32), index=True)
    confirmation_state: Mapped[str] = mapped_column(
        String(24), default="PENDING", index=True
    )
    row_digest: Mapped[str] = mapped_column(String(64), index=True)
    confirmed_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_order_identity_id: Mapped[str] = mapped_column(String(96), default="")
    confirmed_order_version_id: Mapped[str] = mapped_column(String(96), default="")
    confirmed_plan_order_state_id: Mapped[str] = mapped_column(String(96), default="")
    confirm_request_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingDemandResolutionSnapshot(Base):
    __tablename__ = "injection_scheduling_demand_resolution_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["demand_import_row_id"],
            ["injection_scheduling_demand_import_rows.id"],
            name="fk_inj_sched_demand_resolution_row",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "demand_import_row_id",
            "preview_generation",
            name="uq_inj_sched_demand_resolution_generation",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    demand_import_row_id: Mapped[str] = mapped_column(String(96), index=True)
    preview_generation: Mapped[int] = mapped_column(Integer, default=1, index=True)
    resolution_status: Mapped[str] = mapped_column(String(32), index=True)
    mold_definition_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    mold_output_spec_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    physical_mold_asset_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    factory_capability_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    commercial_rate_rule_id: Mapped[str | None] = mapped_column(
        String(96), nullable=True, index=True
    )
    master_revision_digest: Mapped[str] = mapped_column(String(64), index=True)
    resolution_digest: Mapped[str] = mapped_column(String(64), index=True)
    resolved_values_json: Mapped[str] = mapped_column(Text)
    provenance_json: Mapped[str] = mapped_column(Text)
    candidate_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InjectionSchedulingLegacyMoldCopyBinding(Base):
    __tablename__ = "injection_scheduling_legacy_mold_copy_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["physical_asset_id"],
            ["injection_scheduling_physical_mold_assets.id"],
            name="fk_inj_sched_legacy_binding_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "factory_id",
            "mold_id",
            "mold_copy_no",
            name="uq_inj_sched_legacy_mold_copy",
        ),
        UniqueConstraint(
            "physical_asset_id", name="uq_inj_sched_legacy_physical_asset"
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    mold_id: Mapped[str] = mapped_column(String(96), index=True)
    mold_copy_no: Mapped[int] = mapped_column(Integer)
    physical_asset_id: Mapped[str] = mapped_column(String(96), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    activated_by: Mapped[str] = mapped_column(String(64), default="")
    activated_at: Mapped[str] = mapped_column(String(32), index=True)
