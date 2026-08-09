import json
from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.injection_scheduling import InjectionSchedulingMold
from app.models.injection_scheduling_execution import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingPlanOrderState,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_import import InjectionSchedulingImportBatch
from app.models.injection_scheduling_shared import (
    InjectionSchedulingCommercialRateRule,
    InjectionSchedulingCompanyFactoryMembership,
    InjectionSchedulingDemandImportRow,
    InjectionSchedulingDemandOrderVersion,
    InjectionSchedulingFactoryMoldCapability,
    InjectionSchedulingFieldEvidence,
    InjectionSchedulingLegacyMoldCopyBinding,
    InjectionSchedulingMasterDataProposal,
    InjectionSchedulingMoldAlias,
    InjectionSchedulingMoldDefinition,
    InjectionSchedulingMoldOutputSpec,
    InjectionSchedulingMoldReservation,
    InjectionSchedulingPhysicalMoldAsset,
    InjectionSchedulingRolloutPolicy,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_demand_import import normalize_identifier
from app.services.injection_scheduling_execution import (
    _actor_name,
    _audit,
    _ensure_physical_reservation_window_available,
    _now,
)
from app.services.injection_scheduling_master_consolidation import (
    CAPABILITY_BUNDLE_ENTITY,
    MOLD_BUNDLE_ENTITY,
    RATE_BUNDLE_ENTITY,
    activate_commercial_rate_bundle,
    activate_factory_capability_bundle,
    activate_mold_definition_bundle,
)

router = APIRouter(prefix="/api/injection-scheduling", tags=["injection-scheduling"])


class StrictSharedWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MasterProposalCreate(StrictSharedWrite):
    factory_id: str
    entity_type: Literal[
        "MOLD_DEFINITION_BUNDLE",
        "MOLD_DEFINITION",
        "MOLD_ALIAS",
        "MOLD_OUTPUT_SPEC",
        "PHYSICAL_MOLD_ASSET",
        "FACTORY_MOLD_CAPABILITY",
        "FACTORY_MOLD_CAPABILITY_BUNDLE",
        "COMMERCIAL_RATE_RULE",
    ]
    action_type: Literal[
        "CREATE", "REVISE", "MERGE", "SPLIT", "RETIRE", "ALIAS_REDIRECT", "ACTIVATE"
    ]
    target_entity_id: str = Field(default="", max_length=96)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)
    payload: dict[str, Any]

    @field_validator("factory_id", "target_entity_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class CommercialRateActivationConfirmation(StrictSharedWrite):
    pricing_basis: Literal["PER_SHOT"]
    currency: Literal["CNY"]
    tax_mode: Literal["AS_LISTED"]
    owner_scope_type: Literal["FACTORY"]
    applicable_factory_mode: Literal["SPECIFIC"]
    applicable_customer_mode: Literal["ANY"]
    contract_mode: Literal["ANY"]
    confirmed_business_signoff: Literal[True]


class MasterProposalReview(StrictSharedWrite):
    factory_id: str
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)
    price_confirmation: CommercialRateActivationConfirmation | None = None

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class RolloutPolicyUpdate(StrictSharedWrite):
    factory_id: str
    expected_revision: int = Field(ge=1)
    demand_mode: Literal["SHADOW", "PREVIEW_ONLY", "MANUAL_CONFIRM", "AUTO_ENRICH"]
    master_data_mode: Literal["PROPOSAL_ONLY", "APPROVAL_ACTIVE"]
    business_contract_status: Literal["UNSIGNED", "SIGNED"]
    price_activation_enabled: bool
    tentative_hold_ttl_minutes: int = Field(ge=5, le=120)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class LegacyCandidateCreate(StrictSharedWrite):
    factory_id: str
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class LegacyBindingActivate(StrictSharedWrite):
    factory_id: str
    mold_id: str = Field(min_length=1, max_length=96)
    mold_copy_no: int = Field(ge=1)
    expected_asset_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("factory_id", "mold_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class DemandMoldEnrichmentRequest(StrictSharedWrite):
    factory_id: str
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class SharedMoldProposalOutput(StrictSharedWrite):
    item_no: str = Field(default="", max_length=128)
    variant_code: str = Field(default="", max_length=128)
    product_name: str = Field(min_length=1, max_length=255)
    cavity_count: int | None = Field(default=None, ge=1)
    whole_shot_net_weight_g: Decimal | None = Field(default=None, ge=0)
    whole_shot_gross_weight_g: Decimal | None = Field(default=None, ge=0)
    default_material: str = Field(default="", max_length=255)
    default_color: str = Field(default="", max_length=128)
    nominal_daily_capacity: Decimal | None = Field(default=None, ge=0)
    unit_price_cny: Decimal | None = Field(default=None, gt=0)

    @field_validator(
        "item_no", "variant_code", "product_name", "default_material", "default_color"
    )
    @classmethod
    def strip_output_text(cls, value: str) -> str:
        return value.strip()


class SharedMoldProposalCapability(StrictSharedWrite):
    machine_class: int | None = Field(default=None, ge=1)
    machine_class_raw: str = Field(default="", max_length=128)
    required_arm_type: str = Field(default="", max_length=64)
    required_fixture_type: str = Field(default="", max_length=64)

    @field_validator(
        "machine_class_raw", "required_arm_type", "required_fixture_type"
    )
    @classmethod
    def strip_capability_text(cls, value: str) -> str:
        return value.strip()


class SharedMoldProposalCreate(StrictSharedWrite):
    factory_id: str
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=4, max_length=500)
    canonical_mold_no: str = Field(min_length=1, max_length=128)
    display_mold_no: str = Field(default="", max_length=128)
    standard_name: str = Field(min_length=1, max_length=255)
    raw_aliases: list[str] = Field(default_factory=list, max_length=20)
    recommended_machine_class_raw: str = Field(default="", max_length=128)
    mold_a_class: int | None = Field(default=None, ge=1)
    default_arm_type: str = Field(default="", max_length=64)
    default_fixture_type: str = Field(default="", max_length=64)
    outputs: list[SharedMoldProposalOutput] = Field(min_length=1, max_length=20)
    capability: SharedMoldProposalCapability | None = None

    @field_validator(
        "factory_id",
        "request_id",
        "reason",
        "canonical_mold_no",
        "display_mold_no",
        "standard_name",
        "recommended_machine_class_raw",
        "default_arm_type",
        "default_fixture_type",
    )
    @classmethod
    def strip_mold_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("raw_aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()
        for raw in value:
            alias = raw.strip()
            normalized = normalize_identifier(alias)
            if alias and normalized and normalized not in seen:
                aliases.append(alias)
                seen.add(normalized)
        return aliases


def _ensure_permission(
    db: Session, user: AuthContext, permission: str, factory_id: str
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db, user, permission, factory_id, SCHEDULING_DEPARTMENTS[0]
    )
    return factory_id


def _company_scope_id(db: Session, factory_id: str) -> str:
    membership = db.scalar(
        select(InjectionSchedulingCompanyFactoryMembership).where(
            InjectionSchedulingCompanyFactoryMembership.factory_id == factory_id,
            InjectionSchedulingCompanyFactoryMembership.status == "ACTIVE",
        )
    )
    if membership is None:
        raise HTTPException(status_code=409, detail="当前厂区未配置公司共享范围")
    return membership.company_scope_id


def _consensus_value(records: list[Any], field_name: str) -> Any | None:
    values = [
        getattr(record, field_name)
        for record in records
        if getattr(record, field_name, None) not in {None, ""}
    ]
    distinct = {str(value) for value in values}
    if len(distinct) != 1:
        return None
    value = values[0]
    return float(value) if isinstance(value, Decimal) else value


def _rate_applies_to_demand(
    rule: InjectionSchedulingCommercialRateRule,
    *,
    company_scope_id: str,
    factory_id: str,
    business_date: str,
    order_quantity: Decimal,
) -> bool:
    if rule.status != "ACTIVE" or rule.currency != "CNY":
        return False
    if rule.owner_scope_type == "FACTORY" and rule.owner_scope_id != factory_id:
        return False
    if rule.owner_scope_type == "COMPANY" and rule.owner_scope_id != company_scope_id:
        return False
    if rule.applicable_factory_mode == "SPECIFIC":
        if rule.applicable_factory_id != factory_id:
            return False
    elif rule.applicable_factory_mode != "ANY_IN_OWNER_COMPANY":
        return False
    if rule.applicable_customer_mode != "ANY" or rule.contract_mode != "ANY":
        return False
    if rule.valid_from and rule.valid_from[:10] > business_date:
        return False
    if rule.valid_to and rule.valid_to[:10] < business_date:
        return False
    if rule.quantity_min is not None and order_quantity < rule.quantity_min:
        return False
    if rule.quantity_max is not None and order_quantity > rule.quantity_max:
        return False
    return True


def _proposal_out(record: InjectionSchedulingMasterDataProposal) -> dict[str, Any]:
    payload = json.loads(record.payload_json)
    if isinstance(payload.get("entries"), list):
        entries = payload.pop("entries")
        payload["entry_count"] = len(entries)
    return {
        "id": record.id,
        "entity_type": record.entity_type,
        "action_type": record.action_type,
        "target_entity_id": record.target_entity_id,
        "scope_type": record.scope_type,
        "scope_id": record.scope_id,
        "payload": payload,
        "status": record.status,
        "revision": record.revision,
        "request_id": record.request_id,
        "proposed_by": record.proposed_by,
        "proposed_by_name": record.proposed_by_name,
        "approved_by": record.approved_by,
        "approved_by_name": record.approved_by_name,
        "reason": record.reason,
        "created_at": record.created_at,
        "reviewed_at": record.reviewed_at,
    }


def _policy_out(record: InjectionSchedulingRolloutPolicy) -> dict[str, Any]:
    return {
        "factory_id": record.factory_id,
        "demand_mode": record.demand_mode,
        "master_data_mode": record.master_data_mode,
        "business_contract_status": record.business_contract_status,
        "price_activation_enabled": record.price_activation_enabled,
        "tentative_hold_ttl_minutes": record.tentative_hold_ttl_minutes,
        "revision": record.revision,
        "updated_by": record.updated_by,
        "updated_by_name": record.updated_by_name,
        "updated_at": record.updated_at,
    }


@router.post("/demand-orders/enrich-molds")
def post_enrich_demand_order_molds(
    payload: DemandMoldEnrichmentRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    replay = db.scalar(
        select(InjectionSchedulingAuditEvent).where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.event_type == "demand_mold_enrichment_run",
            InjectionSchedulingAuditEvent.request_id == payload.request_id,
        )
    )
    if replay is not None:
        return json.loads(replay.detail_json)

    company_scope_id = _company_scope_id(db, factory_id)
    can_read_prices = any(
        has_permission_in_scope(
            current_user, "shared_mold_price:read", factory_id, department
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    molds = list(
        db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.status != "retired",
            )
        ).all()
    )
    definitions = list(
        db.scalars(
            select(InjectionSchedulingMoldDefinition).where(
                InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
                InjectionSchedulingMoldDefinition.status == "ACTIVE",
            )
        ).all()
    )
    aliases = list(
        db.scalars(
            select(InjectionSchedulingMoldAlias).where(
                InjectionSchedulingMoldAlias.company_scope_id == company_scope_id,
                InjectionSchedulingMoldAlias.status == "ACTIVE",
            )
        ).all()
    )
    definition_ids = [item.id for item in definitions]
    output_specs = (
        list(
            db.scalars(
                select(InjectionSchedulingMoldOutputSpec).where(
                    InjectionSchedulingMoldOutputSpec.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    capabilities = (
        list(
            db.scalars(
                select(InjectionSchedulingFactoryMoldCapability).where(
                    InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                    InjectionSchedulingFactoryMoldCapability.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    physical_assets = (
        list(
            db.scalars(
                select(InjectionSchedulingPhysicalMoldAsset).where(
                    InjectionSchedulingPhysicalMoldAsset.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
                    InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    rate_rules = (
        list(
            db.scalars(
                select(InjectionSchedulingCommercialRateRule).where(
                    InjectionSchedulingCommercialRateRule.status == "ACTIVE",
                    InjectionSchedulingCommercialRateRule.currency == "CNY",
                    or_(
                        InjectionSchedulingCommercialRateRule.mold_definition_id.in_(
                            definition_ids
                        ),
                        InjectionSchedulingCommercialRateRule.mold_output_spec_id.in_(
                            [item.id for item in output_specs]
                        ),
                    ),
                )
            ).all()
        )
        if can_read_prices and definition_ids and output_specs
        else []
    )
    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder)
            .where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.source_type == "DEMAND_ORDER_VERSION",
                InjectionSchedulingOrder.status == "BACKLOG",
                InjectionSchedulingOrder.mold_id.is_(None),
            )
            .with_for_update()
        ).all()
    )
    timestamp = _now()
    matched = 0
    pending = 0
    ambiguous = 0
    execution_ready = 0
    matched_order_ids: list[str] = []
    for order in orders:
        version = db.get(InjectionSchedulingDemandOrderVersion, order.source_ref)
        if version is None:
            pending += 1
            continue
        canonical = json.loads(version.canonical_json)
        normalized_mold_no = normalize_identifier(
            canonical.get("source_mold_no", "")
        )
        matched_definition_ids = {
            item.id
            for item in definitions
            if normalize_identifier(item.canonical_mold_no) == normalized_mold_no
        }
        matched_definition_ids.update(
            item.mold_definition_id
            for item in aliases
            if item.normalized_alias == normalized_mold_no
        )
        legacy_candidates = {
            item.id: item
            for item in molds
            if normalize_identifier(item.mold_no) == normalized_mold_no
            or item.definition_id in matched_definition_ids
        }
        lineage = json.loads(order.lineage_json or "{}")
        lineage["mold_enrichment_checked_at"] = timestamp
        if len(matched_definition_ids) > 1 or (
            not matched_definition_ids and len(legacy_candidates) > 1
        ):
            lineage["mold_enrichment_status"] = (
                "AMBIGUOUS"
            )
            lineage["mold_definition_ids"] = sorted(matched_definition_ids)
            lineage["legacy_factory_mold_ids"] = sorted(legacy_candidates)
            order.lineage_json = json.dumps(
                lineage, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            ambiguous += 1
            continue

        definition = (
            next(
                item for item in definitions if item.id in matched_definition_ids
            )
            if len(matched_definition_ids) == 1
            else None
        )
        legacy_mold = (
            next(iter(legacy_candidates.values()))
            if len(legacy_candidates) == 1
            else None
        )
        if definition is None and legacy_mold is None:
            lineage["mold_enrichment_status"] = "PENDING"
            lineage["mold_definition_ids"] = []
            lineage["legacy_factory_mold_ids"] = []
            order.lineage_json = json.dumps(
                lineage, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            pending += 1
            continue

        relevant_outputs: list[InjectionSchedulingMoldOutputSpec] = []
        relevant_capabilities: list[InjectionSchedulingFactoryMoldCapability] = []
        relevant_assets: list[InjectionSchedulingPhysicalMoldAsset] = []
        relevant_rates: list[InjectionSchedulingCommercialRateRule] = []
        if definition is not None:
            relevant_outputs = [
                item
                for item in output_specs
                if item.mold_definition_id == definition.id
            ]
            item_keys = {
                normalize_identifier(canonical.get("item_no", "")),
                normalize_identifier(canonical.get("product_group_no", "")),
            } - {""}
            item_matched_outputs = [
                item
                for item in relevant_outputs
                if normalize_identifier(item.item_no) in item_keys
            ]
            if item_keys:
                relevant_outputs = item_matched_outputs
            output_ids = {item.id for item in relevant_outputs}
            relevant_capabilities = [
                item
                for item in capabilities
                if item.mold_definition_id == definition.id
                and item.mold_output_spec_id in {None, *output_ids}
            ]
            relevant_assets = [
                item
                for item in physical_assets
                if item.mold_definition_id == definition.id
            ]
            relevant_rates = [
                item
                for item in rate_rules
                if (
                    item.mold_definition_id == definition.id
                    or item.mold_output_spec_id in output_ids
                )
                and _rate_applies_to_demand(
                    item,
                    company_scope_id=company_scope_id,
                    factory_id=factory_id,
                    business_date=timestamp[:10],
                    order_quantity=order.order_quantity,
                )
            ]

        selected_output = relevant_outputs[0] if len(relevant_outputs) == 1 else None
        selected_capability = (
            relevant_capabilities[0] if len(relevant_capabilities) == 1 else None
        )
        rate_signatures = {
            (
                str(item.amount),
                item.currency,
                item.pricing_basis,
                item.tax_mode,
            )
            for item in relevant_rates
        }
        selected_rate = relevant_rates[0] if len(rate_signatures) == 1 else None
        price_fields = (
            {
                "unit_price": float(selected_rate.amount),
                "currency": selected_rate.currency,
                "pricing_basis": selected_rate.pricing_basis,
                "price_tax_mode": selected_rate.tax_mode,
            }
            if selected_rate is not None
            else {}
        )
        master_fields = {
            "master_mold_no": (
                definition.display_mold_no if definition is not None else legacy_mold.mold_no
            ),
            "master_mold_name": (
                definition.standard_name if definition is not None else legacy_mold.name
            ),
            "machine_a_class": (
                _consensus_value(relevant_capabilities, "machine_class")
                if relevant_capabilities
                else definition.mold_a_class if definition is not None else None
            ),
            "machine_class_raw": (
                definition.recommended_machine_class_raw
                if definition is not None
                else legacy_mold.recommended_machine_class
            ),
            "required_arm_type": (
                _consensus_value(relevant_capabilities, "required_arm_type")
                or (definition.default_arm_type if definition is not None else None)
            ),
            "required_fixture_type": (
                _consensus_value(relevant_capabilities, "required_fixture_type")
                or (definition.default_fixture_type if definition is not None else None)
            ),
            "mold_daily_capacity": (
                _consensus_value(relevant_outputs, "nominal_daily_capacity")
                or _consensus_value(relevant_capabilities, "nominal_daily_capacity")
            ),
            "mold_whole_shot_net_weight_g": _consensus_value(
                relevant_outputs, "whole_shot_net_weight_g"
            ),
            "mold_whole_shot_gross_weight_g": _consensus_value(
                relevant_outputs, "whole_shot_gross_weight_g"
            ),
            "mold_cavity_count": _consensus_value(relevant_outputs, "cavity_count"),
            "mold_units_per_shot": _consensus_value(relevant_outputs, "units_per_shot"),
            "master_material_name": _consensus_value(
                relevant_outputs, "default_material"
            ),
            "master_color_name": _consensus_value(relevant_outputs, "default_color"),
            **price_fields,
        }
        master_fields = {
            key: value for key, value in master_fields.items() if value not in {None, ""}
        }
        for key, value in master_fields.items():
            if lineage.get(key) in {None, ""}:
                lineage[key] = value
        execution_is_ready = bool(relevant_assets and relevant_capabilities)
        readiness = "FACTORY_READY" if execution_is_ready else "NOT_FACTORY_READY"
        if legacy_mold is not None:
            order.mold_id = legacy_mold.id
        order.revision += 1
        order.updated_by = current_user.id
        order.updated_by_name = _actor_name(current_user)
        order.updated_at = timestamp
        lineage.update(
            {
                "mold_enrichment_status": "MATCHED",
                "mold_definition_id": definition.id if definition is not None else None,
                "mold_definition_ids": sorted(matched_definition_ids),
                "mold_output_spec_id": selected_output.id if selected_output else None,
                "mold_output_spec_ids": [item.id for item in relevant_outputs],
                "mold_output_match_status": (
                    "MATCHED"
                    if selected_output is not None
                    else "CONSENSUS"
                    if relevant_outputs and master_fields
                    else "PENDING"
                ),
                "factory_capability_id": (
                    selected_capability.id if selected_capability else None
                ),
                "factory_capability_ids": [
                    item.id for item in relevant_capabilities
                ],
                "commercial_rate_rule_id": (
                    selected_rate.id if selected_rate and len(relevant_rates) == 1 else None
                ),
                "commercial_rate_rule_ids": [item.id for item in relevant_rates],
                "physical_mold_asset_ids": [item.id for item in relevant_assets],
                "legacy_factory_mold_id": legacy_mold.id if legacy_mold else None,
                "legacy_factory_mold_ids": sorted(legacy_candidates),
                "factory_readiness_status": readiness,
                "master_data_fields": master_fields,
            }
        )
        order.lineage_json = json.dumps(
            lineage, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        for state in db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(
                InjectionSchedulingPlanOrderState.factory_id == factory_id,
                InjectionSchedulingPlanOrderState.order_id == order.id,
                InjectionSchedulingPlanOrderState.status == "BACKLOG",
            )
            .with_for_update()
        ).all():
            state.factory_readiness_status = readiness
            state.revision += 1
        matched += 1
        execution_ready += int(execution_is_ready)
        matched_order_ids.append(order.id)

    result = {
        "factory_id": factory_id,
        "scanned": len(orders),
        "matched": matched,
        "pending": pending,
        "ambiguous": ambiguous,
        "execution_ready": execution_ready,
        "matched_order_ids": matched_order_ids,
        "reason": payload.reason,
    }
    _audit(
        db,
        factory_id=factory_id,
        event_type="demand_mold_enrichment_run",
        entity_type="demand_order",
        entity_id=factory_id,
        entity_revision=matched,
        request_id=payload.request_id,
        detail=result,
        user=current_user,
    )
    db.commit()
    return result


@router.get("/shared-molds/definitions")
def get_shared_mold_definitions(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    q: Annotated[str, Query(max_length=128)] = "",
):
    factory_id = _ensure_permission(db, current_user, "shared_mold:read", factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    statement = select(InjectionSchedulingMoldDefinition).where(
        InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
        InjectionSchedulingMoldDefinition.status == "ACTIVE",
    )
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                InjectionSchedulingMoldDefinition.canonical_mold_no.ilike(pattern),
                InjectionSchedulingMoldDefinition.display_mold_no.ilike(pattern),
                InjectionSchedulingMoldDefinition.standard_name.ilike(pattern),
            )
        )
    definitions = list(
        db.scalars(
            statement.order_by(
                InjectionSchedulingMoldDefinition.canonical_mold_no
            ).limit(100)
        ).all()
    )
    definition_ids = [item.id for item in definitions]
    outputs = (
        list(
            db.scalars(
                select(InjectionSchedulingMoldOutputSpec).where(
                    InjectionSchedulingMoldOutputSpec.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    assets = (
        list(
            db.scalars(
                select(InjectionSchedulingPhysicalMoldAsset).where(
                    InjectionSchedulingPhysicalMoldAsset.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingPhysicalMoldAsset.current_factory_id
                    == factory_id,
                    InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    capabilities = (
        list(
            db.scalars(
                select(InjectionSchedulingFactoryMoldCapability).where(
                    InjectionSchedulingFactoryMoldCapability.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                    InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    return [
        {
            "id": definition.id,
            "canonical_mold_no": definition.canonical_mold_no,
            "display_mold_no": definition.display_mold_no,
            "standard_name": definition.standard_name,
            "mold_a_class": definition.mold_a_class,
            "revision": definition.revision,
            "outputs": [
                {
                    "id": output.id,
                    "item_no": output.item_no,
                    "product_name": output.product_name,
                    "cavity_count": output.cavity_count,
                    "revision": output.revision,
                }
                for output in outputs
                if output.mold_definition_id == definition.id
            ],
            "company_catalog_status": "AVAILABLE",
            "factory_readiness": {
                "status": "FACTORY_READY"
                if any(item.mold_definition_id == definition.id for item in assets)
                and any(
                    item.mold_definition_id == definition.id for item in capabilities
                )
                else "NOT_FACTORY_READY",
                "available_asset_count": sum(
                    item.mold_definition_id == definition.id for item in assets
                ),
                "active_capability_count": sum(
                    item.mold_definition_id == definition.id for item in capabilities
                ),
            },
        }
        for definition in definitions
    ]


def _shared_mold_catalog_item(
    definition: InjectionSchedulingMoldDefinition,
    *,
    outputs: list[InjectionSchedulingMoldOutputSpec],
    assets: list[InjectionSchedulingPhysicalMoldAsset],
    capabilities: list[InjectionSchedulingFactoryMoldCapability],
    rates: list[InjectionSchedulingCommercialRateRule],
    can_read_prices: bool,
) -> dict[str, Any]:
    definition_outputs = [
        item for item in outputs if item.mold_definition_id == definition.id
    ]
    definition_output_ids = {item.id for item in definition_outputs}
    definition_assets = [
        item for item in assets if item.mold_definition_id == definition.id
    ]
    definition_capabilities = sorted(
        [item for item in capabilities if item.mold_definition_id == definition.id],
        key=lambda item: (-item.priority, item.id),
    )
    definition_rates = [
        item
        for item in rates
        if item.mold_definition_id == definition.id
        or item.mold_output_spec_id in definition_output_ids
    ]
    primary_capability = definition_capabilities[0] if definition_capabilities else None
    price = _consensus_value(definition_rates, "amount") if can_read_prices else None
    daily_capacity = _consensus_value(definition_outputs, "nominal_daily_capacity")
    return {
        "id": definition.id,
        "canonical_mold_no": definition.canonical_mold_no,
        "display_mold_no": definition.display_mold_no,
        "standard_name": definition.standard_name,
        "mold_a_class": definition.mold_a_class,
        "recommended_machine_class_raw": definition.recommended_machine_class_raw,
        "default_arm_type": definition.default_arm_type,
        "default_fixture_type": definition.default_fixture_type,
        "status": definition.status,
        "data_quality": definition.data_quality,
        "revision": definition.revision,
        "output_count": len(definition_outputs),
        "outputs": [
            {
                "id": item.id,
                "item_no": item.item_no,
                "product_name": item.product_name,
                "cavity_count": item.cavity_count,
            }
            for item in definition_outputs[:3]
        ],
        "nominal_daily_capacity": daily_capacity,
        "factory_capability": {
            "machine_class": primary_capability.machine_class,
            "required_arm_type": primary_capability.required_arm_type,
            "required_fixture_type": primary_capability.required_fixture_type,
        }
        if primary_capability
        else None,
        "price": {
            "amount": price,
            "currency": "CNY",
            "pricing_basis": "PER_SHOT",
            "tax_mode": "AS_LISTED",
        }
        if price is not None
        else None,
        "factory_readiness": {
            "status": "FACTORY_READY"
            if definition_assets and definition_capabilities
            else "NOT_FACTORY_READY",
            "available_asset_count": len(definition_assets),
            "active_capability_count": len(definition_capabilities),
        },
    }


@router.get("/shared-molds/catalog")
def get_shared_mold_catalog(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    q: Annotated[str, Query(max_length=128)] = "",
    readiness: Annotated[
        Literal["ALL", "FACTORY_READY", "NOT_FACTORY_READY"], Query()
    ] = "ALL",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 30,
):
    factory_id = _ensure_permission(db, current_user, "shared_mold:read", factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    can_read_prices = any(
        has_permission_in_scope(
            current_user, "shared_mold_price:read", factory_id, department
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    asset_exists = exists().where(
        InjectionSchedulingPhysicalMoldAsset.mold_definition_id
        == InjectionSchedulingMoldDefinition.id,
        InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
        InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
    )
    capability_exists = exists().where(
        InjectionSchedulingFactoryMoldCapability.mold_definition_id
        == InjectionSchedulingMoldDefinition.id,
        InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
        InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
    )
    filters: list[Any] = [
        InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
        InjectionSchedulingMoldDefinition.status == "ACTIVE",
    ]
    query = q.strip()
    if query:
        pattern = f"%{query}%"
        output_match = exists().where(
            InjectionSchedulingMoldOutputSpec.mold_definition_id
            == InjectionSchedulingMoldDefinition.id,
            InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
            or_(
                InjectionSchedulingMoldOutputSpec.item_no.ilike(pattern),
                InjectionSchedulingMoldOutputSpec.product_name.ilike(pattern),
            ),
        )
        filters.append(
            or_(
                InjectionSchedulingMoldDefinition.canonical_mold_no.ilike(pattern),
                InjectionSchedulingMoldDefinition.display_mold_no.ilike(pattern),
                InjectionSchedulingMoldDefinition.standard_name.ilike(pattern),
                output_match,
            )
        )
    if readiness == "FACTORY_READY":
        filters.extend([asset_exists, capability_exists])
    elif readiness == "NOT_FACTORY_READY":
        filters.append(or_(~asset_exists, ~capability_exists))

    total = int(
        db.scalar(
            select(func.count(InjectionSchedulingMoldDefinition.id)).where(*filters)
        )
        or 0
    )
    definitions = list(
        db.scalars(
            select(InjectionSchedulingMoldDefinition)
            .where(*filters)
            .order_by(InjectionSchedulingMoldDefinition.canonical_mold_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    definition_ids = [item.id for item in definitions]
    outputs = (
        list(
            db.scalars(
                select(InjectionSchedulingMoldOutputSpec).where(
                    InjectionSchedulingMoldOutputSpec.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    assets = (
        list(
            db.scalars(
                select(InjectionSchedulingPhysicalMoldAsset).where(
                    InjectionSchedulingPhysicalMoldAsset.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingPhysicalMoldAsset.current_factory_id
                    == factory_id,
                    InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    capabilities = (
        list(
            db.scalars(
                select(InjectionSchedulingFactoryMoldCapability).where(
                    InjectionSchedulingFactoryMoldCapability.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                    InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids
        else []
    )
    rates = (
        list(
            db.scalars(
                select(InjectionSchedulingCommercialRateRule).where(
                    InjectionSchedulingCommercialRateRule.mold_definition_id.in_(
                        definition_ids
                    ),
                    InjectionSchedulingCommercialRateRule.applicable_factory_id
                    == factory_id,
                    InjectionSchedulingCommercialRateRule.status == "ACTIVE",
                )
            ).all()
        )
        if definition_ids and can_read_prices
        else []
    )
    catalog_filters = [
        InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
        InjectionSchedulingMoldDefinition.status == "ACTIVE",
    ]
    catalog_total = int(
        db.scalar(
            select(func.count(InjectionSchedulingMoldDefinition.id)).where(
                *catalog_filters
            )
        )
        or 0
    )
    factory_ready_total = int(
        db.scalar(
            select(func.count(InjectionSchedulingMoldDefinition.id)).where(
                *catalog_filters, asset_exists, capability_exists
            )
        )
        or 0
    )
    pending_proposals = int(
        db.scalar(
            select(func.count(InjectionSchedulingMasterDataProposal.id)).where(
                or_(
                    (
                        InjectionSchedulingMasterDataProposal.scope_type == "COMPANY"
                    )
                    & (
                        InjectionSchedulingMasterDataProposal.scope_id
                        == company_scope_id
                    ),
                    (
                        InjectionSchedulingMasterDataProposal.scope_type == "FACTORY"
                    )
                    & (InjectionSchedulingMasterDataProposal.scope_id == factory_id),
                ),
                InjectionSchedulingMasterDataProposal.status.in_(
                    ["PROPOSED", "UNDER_REVIEW", "APPROVED"]
                ),
            )
        )
        or 0
    )
    return {
        "items": [
            _shared_mold_catalog_item(
                definition,
                outputs=outputs,
                assets=assets,
                capabilities=capabilities,
                rates=rates,
                can_read_prices=can_read_prices,
            )
            for definition in definitions
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "summary": {
            "total_definitions": catalog_total,
            "factory_ready": factory_ready_total,
            "not_factory_ready": catalog_total - factory_ready_total,
            "pending_proposals": pending_proposals,
            "can_read_prices": can_read_prices,
        },
    }


@router.get("/shared-molds/catalog/{definition_id}")
def get_shared_mold_catalog_detail(
    definition_id: str,
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(db, current_user, "shared_mold:read", factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    definition = db.scalar(
        select(InjectionSchedulingMoldDefinition).where(
            InjectionSchedulingMoldDefinition.id == definition_id,
            InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
            InjectionSchedulingMoldDefinition.status == "ACTIVE",
        )
    )
    if definition is None:
        raise HTTPException(status_code=404, detail="共享模具不存在或不在当前公司范围")
    can_read_prices = any(
        has_permission_in_scope(
            current_user, "shared_mold_price:read", factory_id, department
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    outputs = list(
        db.scalars(
            select(InjectionSchedulingMoldOutputSpec)
            .where(
                InjectionSchedulingMoldOutputSpec.mold_definition_id == definition.id,
                InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
            )
            .order_by(InjectionSchedulingMoldOutputSpec.item_no)
        ).all()
    )
    aliases = list(
        db.scalars(
            select(InjectionSchedulingMoldAlias)
            .where(
                InjectionSchedulingMoldAlias.mold_definition_id == definition.id,
                InjectionSchedulingMoldAlias.status == "ACTIVE",
            )
            .order_by(InjectionSchedulingMoldAlias.raw_alias)
        ).all()
    )
    assets = list(
        db.scalars(
            select(InjectionSchedulingPhysicalMoldAsset)
            .where(
                InjectionSchedulingPhysicalMoldAsset.mold_definition_id
                == definition.id,
                InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
            )
            .order_by(InjectionSchedulingPhysicalMoldAsset.asset_code)
        ).all()
    )
    capabilities = list(
        db.scalars(
            select(InjectionSchedulingFactoryMoldCapability)
            .where(
                InjectionSchedulingFactoryMoldCapability.mold_definition_id
                == definition.id,
                InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
            )
            .order_by(InjectionSchedulingFactoryMoldCapability.priority.desc())
        ).all()
    )
    output_ids = [item.id for item in outputs]
    rates = (
        list(
            db.scalars(
                select(InjectionSchedulingCommercialRateRule)
                .where(
                    or_(
                        InjectionSchedulingCommercialRateRule.mold_definition_id
                        == definition.id,
                        InjectionSchedulingCommercialRateRule.mold_output_spec_id.in_(
                            output_ids
                        ),
                    ),
                    InjectionSchedulingCommercialRateRule.applicable_factory_id
                    == factory_id,
                    InjectionSchedulingCommercialRateRule.status == "ACTIVE",
                )
                .order_by(InjectionSchedulingCommercialRateRule.priority.desc())
            ).all()
        )
        if can_read_prices and output_ids
        else []
    )
    summary = _shared_mold_catalog_item(
        definition,
        outputs=outputs,
        assets=assets,
        capabilities=capabilities,
        rates=rates,
        can_read_prices=can_read_prices,
    )
    return {
        **summary,
        "aliases": [
            {
                "id": item.id,
                "raw_alias": item.raw_alias,
                "source_namespace_id": item.source_namespace_id,
            }
            for item in aliases
        ],
        "outputs": [
            {
                "id": item.id,
                "item_no": item.item_no,
                "variant_code": item.variant_code,
                "product_name": item.product_name,
                "cavity_count": item.cavity_count,
                "whole_shot_net_weight_g": item.whole_shot_net_weight_g,
                "whole_shot_gross_weight_g": item.whole_shot_gross_weight_g,
                "default_material": item.default_material,
                "default_color": item.default_color,
                "nominal_daily_capacity": item.nominal_daily_capacity,
                "revision": item.revision,
            }
            for item in outputs
        ],
        "assets": [
            {
                "id": item.id,
                "asset_code": item.asset_code,
                "serial_no": item.serial_no,
                "current_location": item.current_location,
                "status": item.status,
                "actual_cavity_count": item.actual_cavity_count,
                "revision": item.revision,
            }
            for item in assets
        ],
        "capabilities": [
            {
                "id": item.id,
                "machine_class": item.machine_class,
                "required_arm_type": item.required_arm_type,
                "required_fixture_type": item.required_fixture_type,
                "nominal_daily_capacity": item.nominal_daily_capacity,
                "priority": item.priority,
                "revision": item.revision,
            }
            for item in capabilities
        ],
        "prices": [
            {
                "id": item.id,
                "mold_output_spec_id": item.mold_output_spec_id,
                "amount": item.amount,
                "currency": item.currency,
                "pricing_basis": item.pricing_basis,
                "tax_mode": item.tax_mode,
                "revision": item.revision,
            }
            for item in rates
        ]
        if can_read_prices
        else [],
        "price_access": "GRANTED" if can_read_prices else "RESTRICTED",
    }


@router.post("/shared-molds/proposals", status_code=201)
def post_shared_mold_proposal(
    payload: SharedMoldProposalCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "shared_mold:propose", payload.factory_id
    )
    company_scope_id = _company_scope_id(db, factory_id)
    existing_replay = db.scalar(
        select(InjectionSchedulingMasterDataProposal).where(
            InjectionSchedulingMasterDataProposal.scope_type == "COMPANY",
            InjectionSchedulingMasterDataProposal.scope_id == company_scope_id,
            InjectionSchedulingMasterDataProposal.request_id == payload.request_id,
        )
    )
    if existing_replay is not None:
        related = list(
            db.scalars(
                select(InjectionSchedulingMasterDataProposal).where(
                    InjectionSchedulingMasterDataProposal.proposed_by
                    == existing_replay.proposed_by,
                    InjectionSchedulingMasterDataProposal.created_at
                    == existing_replay.created_at,
                )
            ).all()
        )
        return {"proposals": [_proposal_out(item) for item in related]}

    canonical_mold_no = normalize_identifier(payload.canonical_mold_no)
    existing_definition = db.scalar(
        select(InjectionSchedulingMoldDefinition).where(
            InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
            InjectionSchedulingMoldDefinition.canonical_mold_no == canonical_mold_no,
            InjectionSchedulingMoldDefinition.status == "ACTIVE",
        )
    )
    if existing_definition is not None:
        raise HTTPException(
            status_code=409,
            detail="该模具编号已在正式共享模具库中，请从详情页发起修订提案",
        )
    output_keys: set[tuple[str, str]] = set()
    for output in payload.outputs:
        key = (normalize_identifier(output.item_no), output.variant_code.casefold())
        if key in output_keys:
            raise HTTPException(status_code=422, detail="同一货号和变体不能重复")
        output_keys.add(key)

    wants_capability = payload.capability is not None and any(
        [
            payload.capability.machine_class,
            payload.capability.machine_class_raw,
            payload.capability.required_arm_type,
            payload.capability.required_fixture_type,
        ]
    )
    wants_price = any(item.unit_price_cny is not None for item in payload.outputs)
    if wants_capability:
        _ensure_permission(
            db, current_user, "factory_mold_capability:manage", factory_id
        )
    if wants_price:
        _ensure_permission(db, current_user, "shared_mold_price:propose", factory_id)

    timestamp = _now()
    manual_digest = uuid4().hex * 2
    mold_key = f"manual-{uuid4().hex}"
    output_entries: list[dict[str, Any]] = []
    rate_entries: list[dict[str, Any]] = []
    for output in payload.outputs:
        output_key = uuid4().hex * 2
        output_entries.append(
            {
                "output_key": output_key,
                "item_no": output.item_no,
                "variant_code": output.variant_code,
                "product_name": output.product_name,
                "cavity_count": output.cavity_count,
                "whole_shot_net_weight_g": str(output.whole_shot_net_weight_g or ""),
                "whole_shot_gross_weight_g": str(
                    output.whole_shot_gross_weight_g or ""
                ),
                "default_material": output.default_material,
                "default_color": output.default_color,
                "nominal_daily_capacity": str(output.nominal_daily_capacity or ""),
                "source_rows": [],
            }
        )
        if output.unit_price_cny is not None:
            rate_entries.append(
                {
                    "rate_key": uuid4().hex * 2,
                    "mold_key": mold_key,
                    "canonical_mold_no": canonical_mold_no,
                    "output_key": output_key,
                    "item_no": output.item_no,
                    "product_name": output.product_name,
                    "amount": str(output.unit_price_cny),
                    "pricing_basis": "PER_SHOT",
                    "currency": "CNY",
                    "tax_mode": "AS_LISTED",
                    "activation_blockers": [],
                    "source": {"kind": "MANUAL_PROPOSAL"},
                }
            )
    aliases = payload.raw_aliases[:]
    if payload.canonical_mold_no not in aliases:
        aliases.insert(0, payload.canonical_mold_no)
    mold_payload = {
        "source_namespace_id": f"manual:factory:{factory_id}",
        "source_file_hash": manual_digest,
        "entries": [
            {
                "mold_key": mold_key,
                "canonical_mold_no": canonical_mold_no,
                "display_mold_no": payload.display_mold_no
                or payload.canonical_mold_no,
                "raw_aliases": aliases,
                "standard_name": payload.standard_name,
                "recommended_machine_class_raw": payload.recommended_machine_class_raw,
                "mold_a_class": payload.mold_a_class,
                "default_arm_type": payload.default_arm_type,
                "default_fixture_type": payload.default_fixture_type,
                "process_tags": [],
                "engineering": {"source_kind": "MANUAL_PROPOSAL"},
                "source_priority": {"manual": True},
                "outputs": output_entries,
            }
        ],
    }

    def add_proposal(
        *, entity_type: str, scope_type: str, scope_id: str, request_id: str, controlled: dict[str, Any]
    ) -> InjectionSchedulingMasterDataProposal:
        record = InjectionSchedulingMasterDataProposal(
            id=f"ismasterproposal-{uuid4().hex}",
            entity_type=entity_type,
            action_type="CREATE",
            target_entity_id="",
            scope_type=scope_type,
            scope_id=scope_id,
            payload_json=json.dumps(
                controlled, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
            evidence_digest="",
            status="PROPOSED",
            revision=1,
            request_id=request_id,
            proposed_by=current_user.id,
            proposed_by_name=_actor_name(current_user),
            approved_by="",
            approved_by_name="",
            reason=payload.reason,
            created_at=timestamp,
            reviewed_at="",
        )
        db.add(record)
        return record

    proposals = [
        add_proposal(
            entity_type=MOLD_BUNDLE_ENTITY,
            scope_type="COMPANY",
            scope_id=company_scope_id,
            request_id=payload.request_id,
            controlled=mold_payload,
        )
    ]
    if wants_capability and payload.capability is not None:
        proposals.append(
            add_proposal(
                entity_type=CAPABILITY_BUNDLE_ENTITY,
                scope_type="FACTORY",
                scope_id=factory_id,
                request_id=f"{payload.request_id}-capability",
                controlled={
                    "source_file_hash": manual_digest,
                    "entries": [
                        {
                            "mold_key": mold_key,
                            "canonical_mold_no": canonical_mold_no,
                            "machine_class": payload.capability.machine_class,
                            "machine_class_raw": payload.capability.machine_class_raw,
                            "required_arm_type": payload.capability.required_arm_type,
                            "required_fixture_type": payload.capability.required_fixture_type,
                            "process_limits": {},
                            "source_priority": "MANUAL_PROPOSAL",
                        }
                    ],
                },
            )
        )
    if rate_entries:
        proposals.append(
            add_proposal(
                entity_type=RATE_BUNDLE_ENTITY,
                scope_type="FACTORY",
                scope_id=factory_id,
                request_id=f"{payload.request_id}-price",
                controlled={
                    "source_file_hash": manual_digest,
                    "entries": rate_entries,
                },
            )
        )
    _audit(
        db,
        factory_id=factory_id,
        event_type="shared_mold_proposal_created",
        entity_type="master_data_proposal",
        entity_id=proposals[0].id,
        entity_revision=1,
        request_id=payload.request_id,
        detail={
            "canonical_mold_no": canonical_mold_no,
            "proposal_ids": [item.id for item in proposals],
        },
        user=current_user,
    )
    db.commit()
    return {"proposals": [_proposal_out(item) for item in proposals]}


@router.get("/mold-assets")
def get_factory_mold_assets(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    try:
        factory_id = _ensure_permission(
            db, current_user, "factory_mold_asset:manage", factory_id
        )
    except HTTPException:
        factory_id = _ensure_permission(
            db, current_user, "factory_mold:manage", factory_id
        )
    return [
        {
            "id": item.id,
            "mold_definition_id": item.mold_definition_id,
            "asset_code": item.asset_code,
            "serial_no": item.serial_no,
            "current_factory_id": item.current_factory_id,
            "current_location": item.current_location,
            "status": item.status,
            "revision": item.revision,
        }
        for item in db.scalars(
            select(InjectionSchedulingPhysicalMoldAsset)
            .where(
                InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id
            )
            .order_by(InjectionSchedulingPhysicalMoldAsset.asset_code)
        ).all()
    ]


@router.post("/mold-assets/generate-legacy-candidates")
def post_generate_legacy_asset_candidates(
    payload: LegacyCandidateCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "factory_mold_asset:manage", payload.factory_id
    )
    molds = list(
        db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.definition_id.is_not(None),
                InjectionSchedulingMold.status != "retired",
            )
        ).all()
    )
    existing_keys = {
        (item.source_mold_id, item.source_copy_no)
        for item in db.scalars(
            select(InjectionSchedulingPhysicalMoldAsset).where(
                InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
                InjectionSchedulingPhysicalMoldAsset.source_mold_id.is_not(None),
            )
        ).all()
    }
    timestamp = _now()
    created: list[InjectionSchedulingPhysicalMoldAsset] = []
    for mold in molds:
        for copy_no in range(1, mold.copy_count + 1):
            if (mold.id, copy_no) in existing_keys:
                continue
            asset = InjectionSchedulingPhysicalMoldAsset(
                id=f"isphysicalmold-{uuid4().hex}",
                mold_definition_id=mold.definition_id,
                owner_scope_type="FACTORY",
                owner_scope_id=factory_id,
                asset_code=f"LEGACY-{mold.mold_no}-{copy_no}",
                serial_no="",
                current_factory_id=factory_id,
                current_location="",
                status="LEGACY_UNVERIFIED",
                actual_cavity_count=None,
                available_from="",
                revision=1,
                source_mold_id=mold.id,
                source_copy_no=copy_no,
                verified_by="",
                verified_at="",
                created_at=timestamp,
            )
            db.add(asset)
            created.append(asset)
    _audit(
        db,
        factory_id=factory_id,
        event_type="legacy_mold_asset_candidates_generated",
        entity_type="physical_mold_asset",
        entity_id=factory_id,
        entity_revision=1,
        request_id=payload.request_id,
        detail={
            "created_count": len(created),
            "candidate_ids": [item.id for item in created],
            "reason": payload.reason,
        },
        user=current_user,
    )
    db.commit()
    return {
        "factory_id": factory_id,
        "created_count": len(created),
        "candidate_ids": [item.id for item in created],
    }


@router.post("/mold-assets/{asset_id}/activate-legacy-binding")
def post_activate_legacy_mold_binding(
    asset_id: str,
    payload: LegacyBindingActivate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "factory_mold_asset:manage", payload.factory_id
    )
    replay = db.scalar(
        select(InjectionSchedulingAuditEvent).where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.event_type
            == "legacy_mold_copy_binding_activated",
            InjectionSchedulingAuditEvent.request_id == payload.request_id,
        )
    )
    if replay is not None:
        binding = db.get(InjectionSchedulingLegacyMoldCopyBinding, replay.entity_id)
        if binding is None or binding.physical_asset_id != asset_id:
            raise HTTPException(status_code=409, detail="request_id 已用于其他资产激活")
        return {
            "binding_id": binding.id,
            "asset_id": binding.physical_asset_id,
            "status": binding.status,
            "revision": binding.revision,
            "idempotent_replay": True,
        }
    asset = db.scalar(
        select(InjectionSchedulingPhysicalMoldAsset)
        .where(InjectionSchedulingPhysicalMoldAsset.id == asset_id)
        .with_for_update()
    )
    mold = db.get(InjectionSchedulingMold, payload.mold_id)
    if (
        asset is None
        or asset.current_factory_id != factory_id
        or mold is None
        or mold.factory_id != factory_id
    ):
        raise HTTPException(status_code=404, detail="待核验实物模具不存在")
    if asset.revision != payload.expected_asset_revision:
        raise HTTPException(status_code=409, detail="实物模具 revision 已变化")
    if asset.status != "LEGACY_UNVERIFIED":
        raise HTTPException(status_code=409, detail="只有待核验候选可执行旧副模具激活")
    if (
        mold.definition_id is None
        or asset.mold_definition_id != mold.definition_id
        or asset.source_mold_id not in {None, mold.id}
        or asset.source_copy_no not in {None, payload.mold_copy_no}
    ):
        raise HTTPException(status_code=409, detail="资产候选与旧模具定义或副号不一致")
    conflicting_binding = db.scalar(
        select(InjectionSchedulingLegacyMoldCopyBinding)
        .where(
            or_(
                (
                    (InjectionSchedulingLegacyMoldCopyBinding.factory_id == factory_id)
                    & (InjectionSchedulingLegacyMoldCopyBinding.mold_id == mold.id)
                    & (
                        InjectionSchedulingLegacyMoldCopyBinding.mold_copy_no
                        == payload.mold_copy_no
                    )
                ),
                InjectionSchedulingLegacyMoldCopyBinding.physical_asset_id == asset.id,
            )
        )
        .with_for_update()
    )
    if conflicting_binding is not None:
        raise HTTPException(status_code=409, detail="旧副模具或实体资产已存在绑定")
    legacy_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .join(
                InjectionSchedulingPlan,
                InjectionSchedulingPlan.id == InjectionSchedulingTask.plan_id,
            )
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.mold_id == mold.id,
                InjectionSchedulingTask.mold_copy_no == payload.mold_copy_no,
                InjectionSchedulingTask.physical_mold_asset_id.is_(None),
                InjectionSchedulingTask.execution_status.notin_(
                    ("COMPLETED", "CANCELLED")
                ),
                InjectionSchedulingPlan.status.in_(("DRAFT", "PUBLISHED")),
            )
            .order_by(InjectionSchedulingTask.planned_start, InjectionSchedulingTask.id)
            .with_for_update()
        ).all()
    )
    for left, right in pairwise(legacy_tasks):
        if not left.planned_start or left.planned_finish <= left.planned_start:
            raise HTTPException(
                status_code=409, detail="旧任务时间窗无效，需先盘点对账"
            )
        if left.planned_finish > right.planned_start:
            raise HTTPException(
                status_code=409, detail="旧任务时间窗重叠，不能唯一激活实物副模具"
            )
    if legacy_tasks:
        last = legacy_tasks[-1]
        if not last.planned_start or last.planned_finish <= last.planned_start:
            raise HTTPException(
                status_code=409, detail="旧任务时间窗无效，需先盘点对账"
            )
    timestamp = _now()
    for task in legacy_tasks:
        _ensure_physical_reservation_window_available(
            db,
            physical_asset_id=asset.id,
            planned_start=task.planned_start,
            planned_finish=task.planned_finish,
        )
        db.add(
            InjectionSchedulingMoldReservation(
                id=f"ismoldreservation-{uuid4().hex}",
                physical_asset_id=asset.id,
                factory_id=factory_id,
                plan_id=task.plan_id,
                task_id=task.id,
                window_start=task.planned_start,
                window_end=task.planned_finish,
                status="ACTIVE",
                revision=1,
                expires_at="",
                idempotency_key=f"legacy-binding:{asset.id}:{task.id}",
                source_kind="LEGACY_BINDING",
                created_by=current_user.id,
                created_at=timestamp,
                released_at="",
            )
        )
    binding = InjectionSchedulingLegacyMoldCopyBinding(
        id=f"islegacybinding-{uuid4().hex}",
        factory_id=factory_id,
        mold_id=mold.id,
        mold_copy_no=payload.mold_copy_no,
        physical_asset_id=asset.id,
        status="ACTIVE",
        revision=1,
        activated_by=current_user.id,
        activated_at=timestamp,
    )
    db.add(binding)
    asset.status = "AVAILABLE"
    asset.source_mold_id = mold.id
    asset.source_copy_no = payload.mold_copy_no
    asset.verified_by = current_user.id
    asset.verified_at = timestamp
    asset.available_from = timestamp
    asset.revision += 1
    _audit(
        db,
        factory_id=factory_id,
        event_type="legacy_mold_copy_binding_activated",
        entity_type="legacy_mold_copy_binding",
        entity_id=binding.id,
        entity_revision=1,
        request_id=payload.request_id,
        detail={
            "asset_id": asset.id,
            "mold_id": mold.id,
            "mold_copy_no": payload.mold_copy_no,
            "legacy_task_ids": [item.id for item in legacy_tasks],
            "reason": payload.reason,
        },
        user=current_user,
    )
    db.commit()
    return {
        "binding_id": binding.id,
        "asset_id": asset.id,
        "status": binding.status,
        "revision": binding.revision,
        "reservation_count": len(legacy_tasks),
        "idempotent_replay": False,
    }


@router.get("/commercial-rate-rules")
def get_commercial_rate_rules(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "shared_mold_price:read", factory_id
    )
    company_scope_id = _company_scope_id(db, factory_id)
    rules = db.scalars(
        select(InjectionSchedulingCommercialRateRule).where(
            or_(
                InjectionSchedulingCommercialRateRule.owner_scope_id
                == company_scope_id,
                InjectionSchedulingCommercialRateRule.owner_scope_id == factory_id,
            )
        )
    ).all()
    return [
        {
            "id": item.id,
            "owner_scope_type": item.owner_scope_type,
            "owner_scope_id": item.owner_scope_id,
            "applicable_factory_mode": item.applicable_factory_mode,
            "applicable_factory_id": item.applicable_factory_id,
            "applicable_customer_mode": item.applicable_customer_mode,
            "applicable_customer_id": item.applicable_customer_id,
            "mold_definition_id": item.mold_definition_id,
            "mold_output_spec_id": item.mold_output_spec_id,
            "pricing_basis": item.pricing_basis,
            "amount": str(item.amount),
            "currency": item.currency,
            "status": item.status,
            "revision": item.revision,
            "valid_from": item.valid_from,
            "valid_to": item.valid_to,
        }
        for item in rules
    ]


@router.get("/master-data-proposals")
def get_master_data_proposals(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    status: Annotated[str, Query(max_length=24)] = "",
):
    factory_id = _ensure_permission(db, current_user, "shared_mold:read", factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    can_read_prices = any(
        has_permission_in_scope(
            current_user, "shared_mold_price:read", factory_id, department
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    statement = select(InjectionSchedulingMasterDataProposal).where(
        or_(
            (
                (InjectionSchedulingMasterDataProposal.scope_type == "COMPANY")
                & (InjectionSchedulingMasterDataProposal.scope_id == company_scope_id)
            ),
            (
                (InjectionSchedulingMasterDataProposal.scope_type == "FACTORY")
                & (InjectionSchedulingMasterDataProposal.scope_id == factory_id)
            ),
        )
    )
    if status.strip():
        statement = statement.where(
            InjectionSchedulingMasterDataProposal.status == status.strip()
        )
    records = list(
        db.scalars(
            statement.order_by(
                InjectionSchedulingMasterDataProposal.created_at.desc()
            ).limit(200)
        ).all()
    )
    return [
        _proposal_out(item)
        for item in records
        if can_read_prices or item.entity_type != "COMMERCIAL_RATE_RULE"
    ]


@router.get("/rollout-policy")
def get_rollout_policy(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    record = db.get(InjectionSchedulingRolloutPolicy, factory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="当前厂区未配置推广策略")
    return _policy_out(record)


@router.patch("/rollout-policy")
def patch_rollout_policy(
    payload: RolloutPolicyUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "shared_mold_price:manage", payload.factory_id
    )
    record = db.scalar(
        select(InjectionSchedulingRolloutPolicy)
        .where(InjectionSchedulingRolloutPolicy.factory_id == factory_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="当前厂区未配置推广策略")
    if record.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="推广策略 revision 已变化")
    if (
        payload.price_activation_enabled
        and payload.business_contract_status != "SIGNED"
    ):
        raise HTTPException(
            status_code=409, detail="价格规则启用前必须记录业务合同已签字"
        )
    record.demand_mode = payload.demand_mode
    record.master_data_mode = payload.master_data_mode
    record.business_contract_status = payload.business_contract_status
    record.price_activation_enabled = payload.price_activation_enabled
    record.tentative_hold_ttl_minutes = payload.tentative_hold_ttl_minutes
    record.revision += 1
    record.updated_by = current_user.id
    record.updated_by_name = _actor_name(current_user)
    record.updated_at = _now()
    _audit(
        db,
        factory_id=factory_id,
        event_type="injection_scheduling_rollout_policy_updated",
        entity_type="rollout_policy",
        entity_id=factory_id,
        entity_revision=record.revision,
        request_id=payload.request_id,
        detail={**_policy_out(record), "reason": payload.reason},
        user=current_user,
    )
    db.commit()
    return _policy_out(record)


@router.get("/operational-metrics")
def get_operational_metrics(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    batches = list(
        db.scalars(
            select(InjectionSchedulingImportBatch).where(
                InjectionSchedulingImportBatch.factory_id == factory_id,
                InjectionSchedulingImportBatch.document_kind.in_(
                    ("DEMAND_ORDER", "MASTER_DATA")
                ),
            )
        ).all()
    )
    demand_rows = list(
        db.scalars(
            select(InjectionSchedulingDemandImportRow).where(
                InjectionSchedulingDemandImportRow.factory_id == factory_id
            )
        ).all()
    )
    company_scope_id = _company_scope_id(db, factory_id)
    proposals = list(
        db.scalars(
            select(InjectionSchedulingMasterDataProposal).where(
                or_(
                    InjectionSchedulingMasterDataProposal.scope_id == factory_id,
                    InjectionSchedulingMasterDataProposal.scope_id == company_scope_id,
                )
            )
        ).all()
    )
    recognized_batches = sum(item.profile_id is not None for item in batches)
    unmatched = sum(item.resolution_status == "NOT_FOUND" for item in demand_rows)
    ambiguous = sum(item.resolution_status == "AMBIGUOUS" for item in demand_rows)
    ready = sum(
        item.resolution_status in {"READY", "AUTO_CONFIRMED", "UPDATE"}
        for item in demand_rows
    )
    price_missing = sum(
        item.resolution_status == "PRICE_REVIEW_REQUIRED" for item in demand_rows
    )
    approval_hours: list[float] = []
    for proposal in proposals:
        if not proposal.reviewed_at:
            continue
        try:
            approval_hours.append(
                (
                    datetime.fromisoformat(proposal.reviewed_at)
                    - datetime.fromisoformat(proposal.created_at)
                ).total_seconds()
                / 3600
            )
        except ValueError:
            continue
    total_batches = len(batches)
    total_rows = len(demand_rows)
    return {
        "factory_id": factory_id,
        "batch_count": total_batches,
        "profile_recognition_rate": recognized_batches / total_batches
        if total_batches
        else 0,
        "demand_row_count": total_rows,
        "unmatched_count": unmatched,
        "unmatched_rate": unmatched / total_rows if total_rows else 0,
        "ambiguity_count": ambiguous,
        "ambiguity_rate": ambiguous / total_rows if total_rows else 0,
        "enrichment_coverage_rate": ready / total_rows if total_rows else 0,
        "price_missing_count": price_missing,
        "price_missing_rate": price_missing / total_rows if total_rows else 0,
        "proposal_count": len(proposals),
        "approved_proposal_count": sum(
            item.status in {"APPROVED", "ACTIVE"} for item in proposals
        ),
        "average_proposal_approval_hours": sum(approval_hours) / len(approval_hours)
        if approval_hours
        else None,
        "generated_at": _now(),
    }


@router.post("/master-data-proposals", status_code=201)
def post_master_data_proposal(
    payload: MasterProposalCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    price_proposal = payload.entity_type == "COMMERCIAL_RATE_RULE"
    permission = (
        "shared_mold_price:propose" if price_proposal else "shared_mold:propose"
    )
    factory_id = _ensure_permission(db, current_user, permission, payload.factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    factory_entity = payload.entity_type in {
        "PHYSICAL_MOLD_ASSET",
        "FACTORY_MOLD_CAPABILITY",
        CAPABILITY_BUNDLE_ENTITY,
    }
    timestamp = _now()
    record = InjectionSchedulingMasterDataProposal(
        id=f"ismasterproposal-{uuid4().hex}",
        entity_type=payload.entity_type,
        action_type=payload.action_type,
        target_entity_id=payload.target_entity_id,
        scope_type="FACTORY" if factory_entity else "COMPANY",
        scope_id=factory_id if factory_entity else company_scope_id,
        payload_json=json.dumps(
            payload.payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ),
        evidence_digest="",
        status="PROPOSED",
        revision=1,
        request_id=payload.request_id,
        proposed_by=current_user.id,
        proposed_by_name=_actor_name(current_user),
        approved_by="",
        approved_by_name="",
        reason=payload.reason,
        created_at=timestamp,
        reviewed_at="",
    )
    db.add(record)
    _audit(
        db,
        factory_id=factory_id,
        event_type="master_data_proposal_created",
        entity_type="master_data_proposal",
        entity_id=record.id,
        entity_revision=1,
        request_id=payload.request_id,
        detail={"entity_type": payload.entity_type, "action_type": payload.action_type},
        user=current_user,
    )
    db.commit()
    return _proposal_out(record)


@router.post("/master-data-proposals/{proposal_id}/approve")
def post_approve_master_data_proposal(
    proposal_id: str,
    payload: MasterProposalReview,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    record = db.scalar(
        select(InjectionSchedulingMasterDataProposal)
        .where(InjectionSchedulingMasterDataProposal.id == proposal_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="主数据提案不存在")
    if record.entity_type == "COMMERCIAL_RATE_RULE":
        permission = "shared_mold_price:approve"
    elif record.entity_type in {
        "FACTORY_MOLD_CAPABILITY",
        CAPABILITY_BUNDLE_ENTITY,
    }:
        permission = "factory_mold_capability:manage"
    else:
        permission = "shared_mold:review"
    factory_id = _ensure_permission(db, current_user, permission, payload.factory_id)
    expected_scope = (
        factory_id
        if record.scope_type == "FACTORY"
        else _company_scope_id(db, factory_id)
    )
    if record.scope_id != expected_scope:
        raise HTTPException(status_code=404, detail="主数据提案不存在")
    if record.revision != payload.expected_revision or record.status != "PROPOSED":
        raise HTTPException(status_code=409, detail="提案状态或版本已变化")
    if record.proposed_by == current_user.id:
        raise HTTPException(status_code=403, detail="主数据提案提交人与批准人必须分离")
    record.status = "APPROVED"
    record.revision += 1
    record.approved_by = current_user.id
    record.approved_by_name = _actor_name(current_user)
    record.reason = payload.reason
    record.reviewed_at = _now()
    _audit(
        db,
        factory_id=factory_id,
        event_type="master_data_proposal_approved",
        entity_type="master_data_proposal",
        entity_id=record.id,
        entity_revision=record.revision,
        request_id=payload.request_id,
        detail={"entity_type": record.entity_type},
        user=current_user,
    )
    db.commit()
    return _proposal_out(record)


@router.post("/master-data-proposals/{proposal_id}/activate")
def post_activate_master_data_proposal(
    proposal_id: str,
    payload: MasterProposalReview,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    record = db.scalar(
        select(InjectionSchedulingMasterDataProposal)
        .where(InjectionSchedulingMasterDataProposal.id == proposal_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="主数据提案不存在")
    if record.entity_type == "COMMERCIAL_RATE_RULE":
        permission = "shared_mold_price:manage"
    elif record.entity_type in {
        "FACTORY_MOLD_CAPABILITY",
        CAPABILITY_BUNDLE_ENTITY,
    }:
        permission = "factory_mold_capability:manage"
    else:
        permission = "shared_mold:manage"
    factory_id = _ensure_permission(db, current_user, permission, payload.factory_id)
    company_scope_id = _company_scope_id(db, factory_id)
    expected_scope = (
        factory_id if record.scope_type == "FACTORY" else company_scope_id
    )
    if record.scope_id != expected_scope:
        raise HTTPException(status_code=404, detail="主数据提案不存在")
    if record.revision != payload.expected_revision or record.status != "APPROVED":
        raise HTTPException(status_code=409, detail="提案状态或版本已变化")
    timestamp = _now()
    if record.entity_type == RATE_BUNDLE_ENTITY:
        confirmation = payload.price_confirmation
        if confirmation is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PRICE_ACTIVATION_CONFIRMATION_REQUIRED",
                    "message": "必须明确确认人民币、每啤计价、原表值及华兴适用范围",
                },
            )
        policy = db.scalar(
            select(InjectionSchedulingRolloutPolicy)
            .where(InjectionSchedulingRolloutPolicy.factory_id == factory_id)
            .with_for_update()
        )
        if policy is None:
            raise HTTPException(status_code=404, detail="当前厂区未配置推广策略")

        configuration = {
            **confirmation.model_dump(),
            "owner_scope_id": factory_id,
            "applicable_factory_id": factory_id,
            "confirmed_by": current_user.id,
            "confirmed_by_name": _actor_name(current_user),
            "confirmed_at": timestamp,
            "source_column": "单价",
        }
        controlled = json.loads(record.payload_json)
        controlled["activation_configuration"] = configuration
        record.payload_json = json.dumps(
            controlled, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )

        policy_changed = (
            policy.master_data_mode != "APPROVAL_ACTIVE"
            or policy.business_contract_status != "SIGNED"
            or not policy.price_activation_enabled
        )
        if policy_changed:
            policy.master_data_mode = "APPROVAL_ACTIVE"
            policy.business_contract_status = "SIGNED"
            policy.price_activation_enabled = True
            policy.revision += 1
            policy.updated_by = current_user.id
            policy.updated_by_name = _actor_name(current_user)
            policy.updated_at = timestamp
            _audit(
                db,
                factory_id=factory_id,
                event_type="injection_scheduling_price_policy_confirmed",
                entity_type="rollout_policy",
                entity_id=factory_id,
                entity_revision=policy.revision,
                request_id=payload.request_id,
                detail={"reason": payload.reason, **configuration},
                user=current_user,
            )

        activation_result = activate_commercial_rate_bundle(
            db,
            proposal=record,
            company_scope_id=company_scope_id,
            factory_id=factory_id,
            timestamp=timestamp,
            pricing_basis=confirmation.pricing_basis,
            currency=confirmation.currency,
            tax_mode=confirmation.tax_mode,
        )
        record.status = "ACTIVE"
        record.revision += 1
        record.reason = payload.reason
        db.execute(
            update(InjectionSchedulingFieldEvidence)
            .where(InjectionSchedulingFieldEvidence.proposal_id == record.id)
            .values(approved_by=record.approved_by)
        )
        _audit(
            db,
            factory_id=factory_id,
            event_type="commercial_rate_bundle_activated",
            entity_type="master_data_proposal",
            entity_id=record.id,
            entity_revision=record.revision,
            request_id=payload.request_id,
            detail={**activation_result, "configuration": configuration},
            user=current_user,
        )
        db.commit()
        return {
            **_proposal_out(record),
            "activated_entity": activation_result,
            "price_configuration": configuration,
        }
    if record.entity_type == CAPABILITY_BUNDLE_ENTITY:
        activation_result = activate_factory_capability_bundle(
            db,
            proposal=record,
            company_scope_id=company_scope_id,
            factory_id=factory_id,
            timestamp=timestamp,
        )
        record.status = "ACTIVE"
        record.revision += 1
        record.reason = payload.reason
        db.execute(
            update(InjectionSchedulingFieldEvidence)
            .where(InjectionSchedulingFieldEvidence.proposal_id == record.id)
            .values(approved_by=record.approved_by)
        )
        _audit(
            db,
            factory_id=factory_id,
            event_type="factory_mold_capability_bundle_activated",
            entity_type="master_data_proposal",
            entity_id=record.id,
            entity_revision=record.revision,
            request_id=payload.request_id,
            detail=activation_result,
            user=current_user,
        )
        db.commit()
        return {
            **_proposal_out(record),
            "activated_entity": activation_result,
        }
    if record.entity_type != MOLD_BUNDLE_ENTITY:
        raise HTTPException(status_code=409, detail="当前提案类型不支持该激活动作")

    controlled = json.loads(record.payload_json)
    if controlled.get("entries"):
        activation_result = activate_mold_definition_bundle(
            db,
            proposal=record,
            company_scope_id=company_scope_id,
            factory_id=factory_id,
            timestamp=timestamp,
        )
        record.status = "ACTIVE"
        record.revision += 1
        record.reason = payload.reason
        db.execute(
            update(InjectionSchedulingFieldEvidence)
            .where(InjectionSchedulingFieldEvidence.proposal_id == record.id)
            .values(approved_by=record.approved_by)
        )
        _audit(
            db,
            factory_id=factory_id,
            event_type="master_data_bundle_activated",
            entity_type="master_data_proposal",
            entity_id=record.id,
            entity_revision=record.revision,
            request_id=payload.request_id,
            detail=activation_result,
            user=current_user,
        )
        db.commit()
        return {
            **_proposal_out(record),
            "activated_entity": activation_result,
        }
    canonical = controlled.get("canonical", {})
    mold_no = str(canonical.get("source_mold_no", "")).strip()
    if not mold_no:
        raise HTTPException(status_code=409, detail="提案缺少权威模号，不能激活")
    conflicting_legacy = db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.factory_id == factory_id,
            InjectionSchedulingMold.mold_no == mold_no,
            InjectionSchedulingMold.definition_id.is_not(None),
        )
    )
    definition = db.scalar(
        select(InjectionSchedulingMoldDefinition)
        .where(
            InjectionSchedulingMoldDefinition.company_scope_id == company_scope_id,
            InjectionSchedulingMoldDefinition.canonical_mold_no == mold_no,
            InjectionSchedulingMoldDefinition.status == "ACTIVE",
        )
        .with_for_update()
    )
    if (
        conflicting_legacy is not None
        and definition is not None
        and conflicting_legacy.definition_id != definition.id
    ):
        raise HTTPException(
            status_code=409, detail="旧模具已关联其他共享定义，需先走合并提案"
        )
    if definition is None:
        definition = InjectionSchedulingMoldDefinition(
            id=f"ismolddefinition-{uuid4().hex}",
            company_scope_id=company_scope_id,
            canonical_mold_no=mold_no,
            display_mold_no=mold_no,
            standard_name=str(canonical.get("standard_name", "")).strip(),
            recommended_machine_class_raw=str(
                canonical.get("recommended_machine_class_raw", "")
            ).strip(),
            mold_a_class=None,
            default_arm_type=str(canonical.get("required_arm_type", "")).strip(),
            default_fixture_type=str(
                canonical.get("required_fixture_type", "")
            ).strip(),
            process_tags_json="[]",
            engineering_json=json.dumps(
                {"source_canonical": canonical}, ensure_ascii=False, sort_keys=True
            ),
            status="ACTIVE",
            data_quality="APPROVED_SOURCE",
            revision=1,
            valid_from=timestamp,
            valid_to="",
            proposal_id=record.id,
            created_factory_id=factory_id,
            created_by=record.proposed_by,
            approved_by=record.approved_by,
            created_at=timestamp,
            approved_at=record.reviewed_at,
        )
        db.add(definition)
        db.flush()
    else:
        definition.standard_name = (
            str(canonical.get("standard_name", "")).strip() or definition.standard_name
        )
        definition.recommended_machine_class_raw = (
            str(canonical.get("recommended_machine_class_raw", "")).strip()
            or definition.recommended_machine_class_raw
        )
        definition.default_arm_type = (
            str(canonical.get("required_arm_type", "")).strip()
            or definition.default_arm_type
        )
        definition.default_fixture_type = (
            str(canonical.get("required_fixture_type", "")).strip()
            or definition.default_fixture_type
        )
        definition.proposal_id = record.id
        definition.approved_by = record.approved_by
        definition.approved_at = record.reviewed_at
        definition.revision += 1

    source_namespace_id = str(controlled.get("source_namespace_id", "")).strip()
    normalized_alias = normalize_identifier(mold_no)
    alias = db.scalar(
        select(InjectionSchedulingMoldAlias).where(
            InjectionSchedulingMoldAlias.company_scope_id == company_scope_id,
            InjectionSchedulingMoldAlias.source_namespace_id == source_namespace_id,
            InjectionSchedulingMoldAlias.normalized_alias == normalized_alias,
            InjectionSchedulingMoldAlias.status == "ACTIVE",
        )
    )
    if alias is not None and alias.mold_definition_id != definition.id:
        raise HTTPException(
            status_code=409, detail="来源命名空间别名已指向其他模具定义"
        )
    if alias is None:
        db.add(
            InjectionSchedulingMoldAlias(
                id=f"ismoldalias-{uuid4().hex}",
                company_scope_id=company_scope_id,
                source_namespace_id=source_namespace_id,
                namespace_type="MASTER_DATA_SOURCE",
                raw_alias=mold_no,
                normalized_alias=normalized_alias,
                mold_definition_id=definition.id,
                status="ACTIVE",
                revision=1,
                valid_from=timestamp,
                valid_to="",
                proposal_id=record.id,
                created_at=timestamp,
            )
        )

    item_no = str(canonical.get("item_no", "")).strip()
    output = None
    if item_no:
        output = db.scalar(
            select(InjectionSchedulingMoldOutputSpec)
            .where(
                InjectionSchedulingMoldOutputSpec.mold_definition_id == definition.id,
                InjectionSchedulingMoldOutputSpec.customer_identity_id.is_(None),
                InjectionSchedulingMoldOutputSpec.item_no == item_no,
                InjectionSchedulingMoldOutputSpec.variant_code == "",
                InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
            )
            .with_for_update()
        )
        if output is None:
            output = InjectionSchedulingMoldOutputSpec(
                id=f"ismoldoutput-{uuid4().hex}",
                mold_definition_id=definition.id,
                customer_identity_id=None,
                item_no=item_no,
                variant_code="",
                product_name=str(canonical.get("output_name", "")).strip(),
                cavity_count=int(canonical["cavity_count"])
                if str(canonical.get("cavity_count", "")).isdigit()
                else None,
                units_per_shot=None,
                whole_shot_net_weight_g=canonical.get("whole_shot_net_weight_g")
                or None,
                whole_shot_gross_weight_g=canonical.get("whole_shot_gross_weight_g")
                or None,
                default_material="",
                default_color="",
                nominal_cycle_seconds=None,
                nominal_daily_capacity=canonical.get("nominal_daily_capacity") or None,
                status="ACTIVE",
                revision=1,
                valid_from=timestamp,
                valid_to="",
                proposal_id=record.id,
                evidence_json=json.dumps(
                    {"proposal_id": record.id}, ensure_ascii=False
                ),
                created_at=timestamp,
            )
            db.add(output)
        else:
            output.product_name = (
                str(canonical.get("output_name", "")).strip() or output.product_name
            )
            output.proposal_id = record.id
            output.revision += 1

    legacy_molds = list(
        db.scalars(
            select(InjectionSchedulingMold)
            .where(
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.mold_no == mold_no,
            )
            .with_for_update()
        ).all()
    )
    for legacy_mold in legacy_molds:
        if legacy_mold.definition_id not in {None, definition.id}:
            raise HTTPException(
                status_code=409, detail="旧模具关联冲突，需先走合并提案"
            )
        legacy_mold.definition_id = definition.id
        legacy_mold.revision += 1

    record.status = "ACTIVE"
    record.revision += 1
    record.reason = payload.reason
    for evidence in db.scalars(
        select(InjectionSchedulingFieldEvidence)
        .where(InjectionSchedulingFieldEvidence.proposal_id == record.id)
        .with_for_update()
    ).all():
        evidence.entity_id = definition.id
        evidence.approved_by = record.approved_by
    _audit(
        db,
        factory_id=factory_id,
        event_type="master_data_proposal_activated",
        entity_type="master_data_proposal",
        entity_id=record.id,
        entity_revision=record.revision,
        request_id=payload.request_id,
        detail={
            "mold_definition_id": definition.id,
            "mold_output_spec_id": output.id if output is not None else "",
            "legacy_mold_ids": [item.id for item in legacy_molds],
        },
        user=current_user,
    )
    db.commit()
    return {
        **_proposal_out(record),
        "activated_entity": {
            "mold_definition_id": definition.id,
            "mold_output_spec_id": output.id if output is not None else "",
        },
    }
