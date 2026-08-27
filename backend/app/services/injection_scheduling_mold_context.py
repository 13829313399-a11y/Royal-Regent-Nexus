from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling import InjectionSchedulingMold
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_shared import (
    InjectionSchedulingFactoryMoldCapability,
    InjectionSchedulingMoldDefinition,
    InjectionSchedulingMoldOutputSpec,
    InjectionSchedulingPhysicalMoldAsset,
)


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def order_mold_key(order: InjectionSchedulingOrder) -> str:
    if order.mold_id:
        return order.mold_id
    if order.mold_definition_id:
        return f"shared:{order.mold_definition_id}:{order.mold_output_spec_id or '*'}"
    lineage = _load_json(order.lineage_json, {})
    definition_id = str(lineage.get("mold_definition_id") or "")
    output_id = str(lineage.get("mold_output_spec_id") or "")
    if definition_id:
        return f"shared:{definition_id}:{output_id or '*'}"
    source_mold_no = str(lineage.get("source_mold_no") or "").strip()
    return f"evidence:{source_mold_no}" if source_mold_no else ""


def task_mold_key(
    task: InjectionSchedulingTask,
    order_by_id: dict[str, InjectionSchedulingOrder],
) -> str:
    if task.mold_id:
        return task.mold_id
    order = order_by_id.get(task.order_id)
    return order_mold_key(order) if order is not None else ""


@dataclass(frozen=True, slots=True)
class SchedulingMoldContext:
    id: str
    revision: int
    legacy_mold_id: str | None
    definition_id: str | None
    definition_revision: int | None
    output_spec_id: str | None
    output_spec_revision: int | None
    capability_revisions: tuple[tuple[str, int], ...]
    mold_no: str
    name: str
    mold_a_class: Decimal | None
    whole_shot_net_weight_g: Decimal | None
    whole_shot_gross_weight_g: Decimal | None
    required_arm_type: str
    required_fixture_type: str
    material_code: str
    material_name: str
    color_profile: str
    process_requirements_json: str
    process_tags_json: str
    copy_count: int
    status: str
    normalization_status: str
    special_machine_type: str


def _legacy_context(mold: InjectionSchedulingMold) -> SchedulingMoldContext:
    return SchedulingMoldContext(
        id=mold.id,
        revision=mold.revision,
        legacy_mold_id=mold.id,
        definition_id=mold.definition_id,
        definition_revision=None,
        output_spec_id=None,
        output_spec_revision=None,
        capability_revisions=(),
        mold_no=mold.mold_no,
        name=mold.name,
        mold_a_class=mold.mold_a_class,
        whole_shot_net_weight_g=mold.whole_shot_net_weight_g,
        whole_shot_gross_weight_g=mold.whole_shot_gross_weight_g,
        required_arm_type=mold.required_arm_type,
        required_fixture_type=mold.required_fixture_type,
        material_code=mold.material_code,
        material_name=mold.material_name,
        color_profile=mold.color_profile,
        process_requirements_json=mold.process_requirements_json,
        process_tags_json=mold.process_tags_json,
        copy_count=mold.copy_count,
        status=mold.status,
        normalization_status=mold.normalization_status,
        special_machine_type=mold.special_machine_type,
    )


def _evidence_context(order: InjectionSchedulingOrder) -> SchedulingMoldContext | None:
    lineage = _load_json(order.lineage_json, {})
    mold_no = str(lineage.get("source_mold_no") or "").strip()
    if not mold_no:
        return None
    process_tags = lineage.get("process_tags_evidence") or []
    if not isinstance(process_tags, list):
        process_tags = []
    mold_a_class = _positive_decimal(
        lineage.get("required_machine_a_class_evidence")
        or lineage.get("required_machine_a")
    )
    net_weight = _positive_decimal(lineage.get("whole_shot_net_weight_g"))
    gross_weight = _positive_decimal(lineage.get("whole_shot_gross_weight_g"))
    arm_type = str(lineage.get("required_arm_type") or "")
    fixture_type = str(lineage.get("required_fixture_type") or "")
    complete = bool(mold_a_class and net_weight and arm_type and fixture_type)
    return SchedulingMoldContext(
        id=f"evidence:{mold_no}",
        revision=1,
        legacy_mold_id=None,
        definition_id=None,
        definition_revision=None,
        output_spec_id=None,
        output_spec_revision=None,
        capability_revisions=(),
        mold_no=mold_no,
        name=order.product_name,
        mold_a_class=mold_a_class,
        whole_shot_net_weight_g=net_weight,
        whole_shot_gross_weight_g=gross_weight,
        required_arm_type=arm_type,
        required_fixture_type=fixture_type,
        material_code=str(lineage.get("material_name") or ""),
        material_name=str(lineage.get("material_name") or ""),
        color_profile=str(
            lineage.get("color_depth") or lineage.get("color_name") or ""
        ),
        process_requirements_json=json.dumps(
            process_tags, ensure_ascii=False, separators=(",", ":")
        ),
        process_tags_json=json.dumps(
            process_tags, ensure_ascii=False, separators=(",", ":")
        ),
        copy_count=1,
        status="available",
        normalization_status="COMPLETE" if complete else "REVIEW_REQUIRED",
        special_machine_type="two_color" if "two_color" in process_tags else "",
    )


def _with_evidence_contexts(
    result: dict[str, SchedulingMoldContext],
    orders: list[InjectionSchedulingOrder],
) -> dict[str, SchedulingMoldContext]:
    for order in orders:
        key = order_mold_key(order)
        if not key or key in result:
            continue
        evidence = _evidence_context(order)
        if evidence is not None:
            result[key] = evidence
    return result


def _consensus(records: list[Any], field: str) -> Any:
    values = {
        value
        for item in records
        if (value := getattr(item, field, None)) not in {None, ""}
    }
    return next(iter(values)) if len(values) == 1 else None


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def machine_capabilities_for_mold(
    mold: SchedulingMoldContext,
    arm_capabilities: tuple[str, ...],
    fixture_capabilities: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Use an active factory capability as the draft-stage fallback for shared molds."""

    if (
        mold.legacy_mold_id is not None
        or mold.definition_id is None
        or mold.status != "available"
    ):
        return arm_capabilities, fixture_capabilities
    return (
        arm_capabilities
        or ((mold.required_arm_type,) if mold.required_arm_type else ()),
        fixture_capabilities
        or ((mold.required_fixture_type,) if mold.required_fixture_type else ()),
    )


def _shared_context(
    order: InjectionSchedulingOrder,
    definition: InjectionSchedulingMoldDefinition,
    output: InjectionSchedulingMoldOutputSpec | None,
    capabilities: list[InjectionSchedulingFactoryMoldCapability],
    asset_count: int,
) -> SchedulingMoldContext:
    lineage = _load_json(order.lineage_json, {})
    process_requirements = list(
        dict.fromkeys(_load_json(definition.process_tags_json, []))
    )
    for capability in capabilities:
        limits = _load_json(capability.process_limits_json, {})
        values = (
            limits.get("process_requirements", []) if isinstance(limits, dict) else []
        )
        if isinstance(values, list):
            process_requirements.extend(str(value) for value in values if value)
    process_requirements = list(dict.fromkeys(process_requirements))
    mold_a_class = definition.mold_a_class or _consensus(capabilities, "machine_class")
    required_arm_type = (
        _consensus(capabilities, "required_arm_type") or definition.default_arm_type
    )
    required_fixture_type = (
        _consensus(capabilities, "required_fixture_type")
        or definition.default_fixture_type
    )
    data_complete = bool(capabilities and mold_a_class)
    return SchedulingMoldContext(
        id=order_mold_key(order),
        revision=definition.revision,
        legacy_mold_id=None,
        definition_id=definition.id,
        definition_revision=definition.revision,
        output_spec_id=output.id if output is not None else None,
        output_spec_revision=output.revision if output is not None else None,
        capability_revisions=tuple(
            sorted((item.id, item.revision) for item in capabilities)
        ),
        mold_no=definition.display_mold_no or definition.canonical_mold_no,
        name=(output.product_name if output is not None else "")
        or definition.standard_name,
        mold_a_class=Decimal(str(mold_a_class)) if mold_a_class else None,
        whole_shot_net_weight_g=(
            output.whole_shot_net_weight_g
            if output is not None and output.whole_shot_net_weight_g
            else _positive_decimal(
                lineage.get("mold_whole_shot_net_weight_g")
                or lineage.get("whole_shot_net_weight_g")
            )
        ),
        whole_shot_gross_weight_g=(
            output.whole_shot_gross_weight_g
            if output is not None and output.whole_shot_gross_weight_g
            else _positive_decimal(
                lineage.get("mold_whole_shot_gross_weight_g")
                or lineage.get("whole_shot_gross_weight_g")
            )
        ),
        required_arm_type=str(required_arm_type or ""),
        required_fixture_type=str(required_fixture_type or ""),
        material_code=str(
            lineage.get("material_name")
            or (output.default_material if output is not None else "")
            or ""
        ),
        material_name=str(
            lineage.get("material_name")
            or (output.default_material if output is not None else "")
            or ""
        ),
        color_profile=str(
            lineage.get("color_name")
            or (output.default_color if output is not None else "")
            or ""
        ),
        process_requirements_json=json.dumps(
            process_requirements, ensure_ascii=False, separators=(",", ":")
        ),
        process_tags_json=definition.process_tags_json or "[]",
        copy_count=max(1, asset_count),
        status="available" if capabilities else "not_arrived",
        normalization_status=(
            "COMPLETE"
            if data_complete and definition.data_quality != "REVIEW_REQUIRED"
            else "REVIEW_REQUIRED"
        ),
        special_machine_type=(
            "two_color" if "two_color" in process_requirements else ""
        ),
    )


def load_scheduling_molds(
    db: Session,
    *,
    factory_id: str,
    orders: list[InjectionSchedulingOrder],
) -> dict[str, SchedulingMoldContext]:
    legacy_ids = {order.mold_id for order in orders if order.mold_id}
    result = (
        {
            mold.id: _legacy_context(mold)
            for mold in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == factory_id,
                    InjectionSchedulingMold.id.in_(legacy_ids),
                )
            ).all()
        }
        if legacy_ids
        else {}
    )

    definition_ids = {
        order.mold_definition_id
        for order in orders
        if order.mold_definition_id and not order.mold_id
    }
    if not definition_ids:
        return _with_evidence_contexts(result, orders)
    definitions = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingMoldDefinition).where(
                InjectionSchedulingMoldDefinition.id.in_(definition_ids),
                InjectionSchedulingMoldDefinition.status == "ACTIVE",
            )
        ).all()
    }
    output_ids = {
        order.mold_output_spec_id
        for order in orders
        if order.mold_output_spec_id and not order.mold_id
    }
    outputs = (
        {
            item.id: item
            for item in db.scalars(
                select(InjectionSchedulingMoldOutputSpec).where(
                    InjectionSchedulingMoldOutputSpec.id.in_(output_ids),
                    InjectionSchedulingMoldOutputSpec.status == "ACTIVE",
                )
            ).all()
        }
        if output_ids
        else {}
    )
    capabilities = list(
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
    assets = list(
        db.scalars(
            select(InjectionSchedulingPhysicalMoldAsset).where(
                InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
                InjectionSchedulingPhysicalMoldAsset.mold_definition_id.in_(
                    definition_ids
                ),
                InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
            )
        ).all()
    )
    asset_counts: dict[str, int] = {}
    for asset in assets:
        asset_counts[asset.mold_definition_id] = (
            asset_counts.get(asset.mold_definition_id, 0) + 1
        )
    for order in orders:
        key = order_mold_key(order)
        definition = definitions.get(order.mold_definition_id or "")
        if not key or definition is None or key in result:
            continue
        output = outputs.get(order.mold_output_spec_id or "")
        relevant = [
            capability
            for capability in capabilities
            if capability.mold_definition_id == definition.id
            and capability.mold_output_spec_id in {None, order.mold_output_spec_id}
        ]
        result[key] = _shared_context(
            order,
            definition,
            output,
            relevant,
            asset_counts.get(definition.id, 0),
        )
    return _with_evidence_contexts(result, orders)
