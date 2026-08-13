from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.schemas.ai import AIServerPageContext
from app.schemas.ai.query_plan import AIQueryPlan, AIQuerySortDirection
from app.services.ai.providers import ProviderToolCall
from app.services.ai.semantic.entities import AIEntityDefinition, get_entity
from app.services.ai.semantic.metrics import get_metric
from app.services.ai.semantic.query_plan import (
    AISemanticNormalizationError,
    normalize_business_id,
    normalize_date,
)
from app.services.ai.tool_registry import ToolRegistry


class _ToolAccessContext(Protocol):
    user: object
    page_context: object | None


class AIQueryPlanValidationError(ValueError):
    public_message = "当前查询计划不在允许范围内，请缩小查询条件后重试。"


@dataclass(frozen=True, slots=True)
class ValidatedAIQueryPlan:
    entity_id: str
    domain: str
    factory_id: str
    tool_name: str
    arguments: dict[str, object]
    provider_tool_call: ProviderToolCall
    metric_ids: tuple[str, ...]


_PRIORITY_ALIASES = {
    "normal": "NORMAL",
    "普通": "NORMAL",
    "urgent": "URGENT",
    "紧急": "URGENT",
    "critical": "CRITICAL",
    "特急": "CRITICAL",
}


def _normalized_value(kind: str, value: str) -> str:
    if kind == "DATE":
        return normalize_date(value)
    if kind == "BUSINESS_ID":
        return normalize_business_id(value)
    if kind == "PRIORITY":
        priority = _PRIORITY_ALIASES.get(value.strip().casefold())
        if priority is None:
            raise AIQueryPlanValidationError("priority is unknown")
        return priority
    normalized = value.strip()
    if not normalized:
        raise AIQueryPlanValidationError("filter value is empty")
    return normalized


def _verified_scope(
    plan: AIQueryPlan,
    page_context: AIServerPageContext,
) -> str:
    factory_id = page_context.verified_factory_id
    if factory_id is None:
        raise AIQueryPlanValidationError("verified factory scope is required")
    if plan.factory_scope and plan.factory_scope != (factory_id,):
        raise AIQueryPlanValidationError("cross-factory scope is not allowed")
    return factory_id


def _validate_catalog_plan(
    plan: AIQueryPlan,
    entity: AIEntityDefinition,
    page_context: AIServerPageContext,
) -> None:
    if entity.module_id != page_context.verified_module_id:
        raise AIQueryPlanValidationError("cross-domain query is not allowed")
    if plan.operation not in entity.operations:
        raise AIQueryPlanValidationError("operation is not allowed")
    for metric_id in plan.metric_ids:
        metric = get_metric(metric_id)
        if metric is None or metric.entity_id != entity.id:
            raise AIQueryPlanValidationError("metric is unknown for entity")
    for sort in plan.sort:
        field = entity.field(sort.field)
        if (
            field is None
            or not field.sortable
            or sort.direction.value not in field.allowed_sort_directions
        ):
            raise AIQueryPlanValidationError("sort is not allowed")


def _map_arguments(
    plan: AIQueryPlan,
    entity: AIEntityDefinition,
    factory_id: str,
) -> dict[str, object]:
    arguments: dict[str, object] = {"factory_id": factory_id}
    for item in plan.filters:
        field = entity.field(item.field)
        if field is None or item.operator not in field.operators:
            raise AIQueryPlanValidationError("field or operator is not allowed")
        argument = field.tool_argument(item.operator)
        if argument is None or argument in arguments:
            raise AIQueryPlanValidationError("filter combination is not allowed")
        try:
            arguments[argument] = _normalized_value(field.value_kind, item.value)
        except AISemanticNormalizationError as exc:
            raise AIQueryPlanValidationError(str(exc)) from exc

    if entity.id == "scheduling_backlog_order":
        if len(plan.sort) > 1 or (plan.sort and plan.sort[0].field != "due_date"):
            raise AIQueryPlanValidationError("scheduling sort is invalid")
        arguments["sort_direction"] = (
            plan.sort[0].direction
            if plan.sort
            else AIQuerySortDirection(entity.default_sort[0][1])
        )

    if entity.tool_name != "customer_order.get_capabilities":
        arguments["limit"] = plan.page_size
        arguments["offset"] = plan.offset
    elif plan.offset != 0 or plan.page_size != 20:
        raise AIQueryPlanValidationError("capability query is not pageable")
    return arguments


def validate_and_map_query_plan(
    plan: AIQueryPlan,
    *,
    registry: ToolRegistry,
    access_context: _ToolAccessContext,
) -> ValidatedAIQueryPlan:
    page_context = access_context.page_context
    if not isinstance(page_context, AIServerPageContext):
        raise AIQueryPlanValidationError("verified page context is required")
    entity = get_entity(plan.entity)
    if entity is None:
        raise AIQueryPlanValidationError("entity is unknown")
    _validate_catalog_plan(plan, entity, page_context)
    factory_id = _verified_scope(plan, page_context)

    spec = registry.resolve(entity.tool_name)
    if spec is None or not registry.is_available(spec, access_context):
        raise AIQueryPlanValidationError("mapped Tool is unavailable")
    arguments = _map_arguments(plan, entity, factory_id)
    try:
        validated = spec.input_model.model_validate(arguments)
    except ValidationError as exc:
        raise AIQueryPlanValidationError("mapped Tool input is invalid") from exc
    canonical_arguments = validated.model_dump(mode="json")
    arguments_json = json.dumps(
        canonical_arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    call_digest = hashlib.sha256(
        f"{entity.id}\n{spec.name}\n{arguments_json}".encode()
    ).hexdigest()[:24]
    return ValidatedAIQueryPlan(
        entity_id=entity.id,
        domain=entity.domain,
        factory_id=factory_id,
        tool_name=spec.name,
        arguments=canonical_arguments,
        provider_tool_call=ProviderToolCall(
            call_id=f"semantic_{call_digest}",
            name=spec.name,
            arguments_json=arguments_json,
        ),
        metric_ids=plan.metric_ids,
    )
