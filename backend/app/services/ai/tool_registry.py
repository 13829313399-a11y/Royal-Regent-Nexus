from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from app.schemas.ai import AIServerPageContext, AIToolAuditPolicy, AIToolRiskLevel
from app.services.ai.providers import ProviderToolDefinition
from app.services.auth import ALLOWED_FACTORY_IDS, authorization_decision

if TYPE_CHECKING:
    from app.services.ai.tool_executor import ToolExecutionContext


ToolCallable = Callable[["ToolExecutionContext", BaseModel], object]
ToolSerializer = Callable[[object], object]

_TOOL_NAME_PATTERN = re.compile(
    r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+"
)

class ToolAccessContext(Protocol):
    user: object
    page_context: object | None


class ToolSideEffectClass(StrEnum):
    UNCLASSIFIED = "UNCLASSIFIED"
    NONE = "NONE"
    PREVIEW_STATE = "PREVIEW_STATE"
    CONSEQUENTIAL_STATE = "CONSEQUENTIAL_STATE"


class ToolIdempotency(StrEnum):
    UNKNOWN = "UNKNOWN"
    IDEMPOTENT = "IDEMPOTENT"
    IDEMPOTENT_WITH_KEY = "IDEMPOTENT_WITH_KEY"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"


class ToolRetryPolicy(StrEnum):
    NEVER_RETRY = "NEVER_RETRY"
    SAFE_TRANSIENT = "SAFE_TRANSIENT"


_READ_CONTRACT = (
    ToolSideEffectClass.NONE,
    ToolIdempotency.IDEMPOTENT,
    ToolRetryPolicy.SAFE_TRANSIENT,
)
_REGISTERED_EXECUTION_CONTRACTS = {
    "artifacts.extract_document": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.inspect_document": _READ_CONTRACT,
    "artifacts.inspect_workbook": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.translate_document_local": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.reconcile_document": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.render_document": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.review_document": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
        ToolRetryPolicy.SAFE_TRANSIENT,
    ),
    "artifacts.verify_document": _READ_CONTRACT,
    "carton_procurement.list_summaries": _READ_CONTRACT,
    "customer_order.get_capabilities": _READ_CONTRACT,
    "customer_order.list_export_audits": _READ_CONTRACT,
    "identity.get_current_context": _READ_CONTRACT,
    "injection_scheduling.compare_previews": _READ_CONTRACT,
    "injection_scheduling.generate_preview": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.NON_IDEMPOTENT,
        ToolRetryPolicy.NEVER_RETRY,
    ),
    "injection_scheduling.get_backlog": _READ_CONTRACT,
    "injection_scheduling.get_plan_context": _READ_CONTRACT,
    "injection_scheduling.propose_apply": (
        ToolSideEffectClass.PREVIEW_STATE,
        ToolIdempotency.NON_IDEMPOTENT,
        ToolRetryPolicy.NEVER_RETRY,
    ),
    "internal_quote.list_summaries": _READ_CONTRACT,
    "knowledge.get_module_help": _READ_CONTRACT,
    "knowledge.search_module": _READ_CONTRACT,
    "molding_sample.list_summaries": _READ_CONTRACT,
    "raw_material.list_inventory_summaries": _READ_CONTRACT,
    "raw_material.list_master_summaries": _READ_CONTRACT,
    "semantic.injection_scheduling.query_backlog": _READ_CONTRACT,
    "vision.compare_injection_backlog": _READ_CONTRACT,
    "vision.observe_injection_backlog_image": (
        ToolSideEffectClass.NONE,
        ToolIdempotency.NON_IDEMPOTENT,
        ToolRetryPolicy.NEVER_RETRY,
    ),
}


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    risk_level: AIToolRiskLevel
    executor: ToolCallable
    serializer: ToolSerializer
    display_label: str
    tool_group: str
    required_permission: str | None = None
    allowed_departments: frozenset[str] = frozenset()
    factory_argument: str | None = None
    requires_db: bool = False
    max_result_rows: int = 50
    timeout_seconds: float = 10
    audit_policy: AIToolAuditPolicy = AIToolAuditPolicy.METADATA_ONLY
    version: str = "1.0.0"
    side_effect_class: ToolSideEffectClass = ToolSideEffectClass.UNCLASSIFIED
    idempotency: ToolIdempotency = ToolIdempotency.UNKNOWN
    retry_policy: ToolRetryPolicy = ToolRetryPolicy.NEVER_RETRY

    def __post_init__(self) -> None:
        if not _TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"invalid tool name: {self.name!r}")
        if not self.description.strip() or not self.display_label.strip():
            raise ValueError("tool description and display label are required")
        if not self.tool_group.strip():
            raise ValueError("tool group is required")
        if not isinstance(self.input_model, type) or not issubclass(
            self.input_model, BaseModel
        ):
            raise TypeError("input_model must be a Pydantic model class")
        if self.input_model.model_config.get("extra") != "forbid":
            raise ValueError("tool input models must set extra='forbid'")
        schema = self.input_model.model_json_schema()
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError("tool input JSON Schema must be a closed object")
        if not callable(self.executor) or not callable(self.serializer):
            raise TypeError("tool executor and serializer must be callable")
        if self.factory_argument and self.factory_argument not in self.input_model.model_fields:
            raise ValueError("factory_argument must name an input model field")
        if self.required_permission and self.factory_argument is None:
            raise ValueError("permissioned tools must declare a factory_argument")
        if self.required_permission and not self.allowed_departments:
            raise ValueError("permissioned tools must declare allowed_departments")
        if self.max_result_rows <= 0 or self.timeout_seconds <= 0:
            raise ValueError("tool result and timeout limits must be positive")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version):
            raise ValueError("tool version must use semantic versioning")
        if self.retry_policy == ToolRetryPolicy.SAFE_TRANSIENT:
            safe_read = (
                self.side_effect_class == ToolSideEffectClass.NONE
                and self.idempotency == ToolIdempotency.IDEMPOTENT
                and self.risk_level == AIToolRiskLevel.READ_ONLY
            )
            keyed_preview = (
                self.side_effect_class == ToolSideEffectClass.PREVIEW_STATE
                and self.idempotency == ToolIdempotency.IDEMPOTENT_WITH_KEY
                and self.risk_level == AIToolRiskLevel.PREVIEW_WITH_AUDIT
            )
            if not (safe_read or keyed_preview):
                raise ValueError(
                    "SAFE_TRANSIENT requires an idempotent read or keyed Preview"
                )

    def provider_definition(self) -> ProviderToolDefinition:
        return ProviderToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_model.model_json_schema(),
        )


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        items = tuple(specs)
        by_name = {item.name: item for item in items}
        if len(by_name) != len(items):
            raise ValueError("tool names must be unique")
        self._specs = tuple(sorted(items, key=lambda item: item.name))
        self._by_name = by_name

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return self._specs

    def resolve(self, name: str) -> ToolSpec | None:
        return self._by_name.get(name)

    def validate_worker_contracts(self) -> None:
        for spec in self._specs:
            if spec.side_effect_class == ToolSideEffectClass.UNCLASSIFIED:
                raise ValueError(f"Tool side effect is unclassified: {spec.name}")
            if spec.idempotency == ToolIdempotency.UNKNOWN:
                raise ValueError(f"Tool idempotency is unknown: {spec.name}")
            if (
                spec.side_effect_class != ToolSideEffectClass.NONE
                and spec.retry_policy != ToolRetryPolicy.NEVER_RETRY
                and (
                spec.idempotency != ToolIdempotency.IDEMPOTENT_WITH_KEY
                or spec.retry_policy != ToolRetryPolicy.SAFE_TRANSIENT
                )
            ):
                raise ValueError(
                    f"non-keyed side-effecting Tool cannot be retried: {spec.name}"
                )

    def provider_definitions(
        self,
        context: ToolAccessContext,
    ) -> tuple[ProviderToolDefinition, ...]:
        return tuple(
            spec.provider_definition()
            for spec in self._specs
            if self.is_available(spec, context)
        )

    def provider_definitions_for_names(
        self,
        context: ToolAccessContext,
        names: Iterable[str],
    ) -> tuple[ProviderToolDefinition, ...]:
        requested = tuple(names)
        if len(requested) != len(set(requested)):
            raise ValueError("Tool definition names must be unique")
        definitions: list[ProviderToolDefinition] = []
        for name in requested:
            spec = self.resolve(name)
            if spec is None or not self.is_available(spec, context):
                raise ValueError("Tool definition is unknown or unauthorized")
            definitions.append(spec.provider_definition())
        return tuple(definitions)

    def available_tool_groups(self, context: ToolAccessContext) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    spec.tool_group
                    for spec in self._specs
                    if self.is_available(spec, context)
                }
            )
        )

    def is_in_request_scope(
        self,
        spec: ToolSpec,
        context: ToolAccessContext,
    ) -> bool:
        if self._by_name.get(spec.name) is not spec:
            return False
        page_context = context.page_context
        if not isinstance(page_context, AIServerPageContext):
            return spec.tool_group == "identity" and spec.required_permission is None
        return spec.tool_group in page_context.allowed_tool_groups

    def is_available(self, spec: ToolSpec, context: ToolAccessContext) -> bool:
        if spec.risk_level not in {
            AIToolRiskLevel.READ_ONLY,
            AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        }:
            return False
        if not self.is_in_request_scope(spec, context):
            return False
        if spec.required_permission is None:
            return True

        page_context = context.page_context
        assert isinstance(page_context, AIServerPageContext)
        page_factory = page_context.verified_factory_id
        if page_factory is None or page_factory not in ALLOWED_FACTORY_IDS:
            return False
        return any(
            authorization_decision(
                context.user,
                spec.required_permission,
                page_factory,
                department,
            )[0]
            for department in spec.allowed_departments
        )


def build_default_tool_registry(
    *,
    controlled_apply_enabled: bool = False,
    semantic_gateway_enabled: bool = False,
    knowledge_hub_enabled: bool = False,
    artifact_workflows_enabled: bool = False,
    document_studio_enabled: bool = False,
    vision_tool_comparison_enabled: bool = False,
) -> ToolRegistry:
    from app.services.ai.semantic.query_tools import semantic_tool_specs
    from app.services.ai.tools.artifact_workflow_tools import (
        artifact_workflow_tool_specs,
    )
    from app.services.ai.tools.carton_procurement_read_tools import (
        carton_procurement_tool_specs,
    )
    from app.services.ai.tools.controlled_apply_tools import (
        controlled_apply_proposal_tool_spec,
    )
    from app.services.ai.tools.customer_order_read_tools import (
        customer_order_tool_specs,
    )
    from app.services.ai.tools.identity_tools import identity_tool_spec
    from app.services.ai.tools.internal_quote_read_tools import (
        internal_quote_tool_specs,
    )
    from app.services.ai.tools.knowledge_tools import knowledge_hub_tool_specs
    from app.services.ai.tools.module_help_tools import module_help_tool_spec
    from app.services.ai.tools.molding_sample_read_tools import (
        molding_sample_tool_specs,
    )
    from app.services.ai.tools.raw_material_read_tools import raw_material_tool_specs
    from app.services.ai.tools.scheduling_advisor_tools import (
        scheduling_advisor_tool_specs,
    )
    from app.services.ai.tools.scheduling_read_tools import scheduling_tool_specs
    from app.services.ai.tools.vision_workflow_tools import vision_workflow_tool_specs

    specs = [
            identity_tool_spec(),
            module_help_tool_spec(),
            *carton_procurement_tool_specs(),
            *customer_order_tool_specs(),
            *internal_quote_tool_specs(),
            *molding_sample_tool_specs(),
            *raw_material_tool_specs(),
            *scheduling_advisor_tool_specs(),
            *scheduling_tool_specs(),
    ]
    if controlled_apply_enabled:
        specs.append(controlled_apply_proposal_tool_spec())
    if semantic_gateway_enabled:
        specs.extend(semantic_tool_specs())
    if knowledge_hub_enabled:
        specs.extend(knowledge_hub_tool_specs())
    if artifact_workflows_enabled:
        specs.extend(artifact_workflow_tool_specs())
    if document_studio_enabled:
        from app.services.ai.tools.document_studio_tools import (
            document_studio_tool_specs,
        )

        specs.extend(document_studio_tool_specs())
    if vision_tool_comparison_enabled:
        specs.extend(vision_workflow_tool_specs())
    contracted_specs: list[ToolSpec] = []
    for spec in specs:
        contract = _REGISTERED_EXECUTION_CONTRACTS.get(spec.name)
        if contract is None:
            raise ValueError(f"Tool has no registered execution contract: {spec.name}")
        side_effect_class, idempotency, retry_policy = contract
        contracted_specs.append(
            replace(
                spec,
                side_effect_class=side_effect_class,
                idempotency=idempotency,
                retry_policy=retry_policy,
            )
        )
    registry = ToolRegistry(contracted_specs)
    registry.validate_worker_contracts()
    return registry
