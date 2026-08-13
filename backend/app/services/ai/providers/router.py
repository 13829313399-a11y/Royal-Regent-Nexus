from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.services.ai.providers.base import (
    ProviderInputItem,
    ProviderRequest,
    ProviderToolDefinition,
)
from app.services.ai.providers.capabilities import (
    CachePolicy,
    ConversationStatePolicy,
    DataClassification,
    FallbackPolicy,
    InputModality,
    ModelCapability,
    OutputModality,
    ParallelToolPolicy,
    ProviderCapabilityProfile,
    ProviderRegionPolicy,
    ProviderResponseFormat,
    ProviderRetryPolicy,
    ReasoningPolicy,
    StorePolicy,
    ToolChoicePolicy,
)
from app.services.ai.providers.catalog import ModelCatalog, load_model_catalog

if TYPE_CHECKING:
    from app.core.config import Settings


class ProviderRoutingError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    contract_version: Literal["1", "2"]
    provider: str
    model: str
    region: str
    capability: ModelCapability
    reasoning_policy: ReasoningPolicy
    provider_reasoning_effort: str
    capability_profile: str = ""
    catalog_version: str = ""
    profile: ProviderCapabilityProfile | None = None


def resolve_provider_route(
    settings: Settings,
    *,
    capability: ModelCapability,
    reasoning_policy: ReasoningPolicy,
    legacy_model: str,
    input_modalities: frozenset[InputModality] = frozenset({InputModality.TEXT}),
    output_modalities: frozenset[OutputModality] = frozenset({OutputModality.TEXT}),
    require_streaming: bool = False,
    require_custom_tools: bool = False,
    require_structured_output: bool = False,
    required_region: str | None = None,
) -> ProviderRoute:
    provider = settings.ai_provider.strip().lower()
    region = (required_region or settings.ai_region).strip().lower()
    if not settings.ai_provider_capability_router_enabled:
        return ProviderRoute(
            contract_version="1",
            provider=provider,
            model=legacy_model.strip(),
            region=region,
            capability=capability,
            reasoning_policy=reasoning_policy,
            provider_reasoning_effort=settings.ai_reasoning_effort,
        )

    try:
        catalog = load_model_catalog(settings)
        profile = catalog.resolve(capability, provider=provider, region=region)
    except ValueError as exc:
        reason = getattr(exc, "reason", "provider_route_unavailable")
        raise ProviderRoutingError(str(reason)) from exc
    if not input_modalities.issubset(profile.input_modalities):
        raise ProviderRoutingError("input_modality_unavailable")
    if not output_modalities.issubset(profile.output_modalities):
        raise ProviderRoutingError("output_modality_unavailable")
    if require_streaming and not profile.supports_streaming:
        raise ProviderRoutingError("streaming_unavailable")
    if require_custom_tools and not profile.supports_custom_tools:
        raise ProviderRoutingError("custom_tools_unavailable")
    if require_structured_output and not profile.supports_structured_output:
        raise ProviderRoutingError("structured_output_unavailable")
    return ProviderRoute(
        contract_version="2",
        provider=profile.provider,
        model=profile.model,
        region=profile.region,
        capability=capability,
        reasoning_policy=reasoning_policy,
        provider_reasoning_effort=profile.effort_for(reasoning_policy),
        capability_profile=profile.profile_id,
        catalog_version=catalog.version,
        profile=profile,
    )


def build_provider_request(
    route: ProviderRoute,
    *,
    request_id: str,
    input: tuple[ProviderInputItem, ...],
    tools: tuple[ProviderToolDefinition, ...] = (),
    max_output_tokens: int | None = None,
    response_format: ProviderResponseFormat | None = None,
    retry_policy: ProviderRetryPolicy | None = None,
    tool_choice_policy: ToolChoicePolicy | None = None,
    data_classification: DataClassification = DataClassification.INTERNAL,
    input_modalities: frozenset[InputModality] = frozenset({InputModality.TEXT}),
) -> ProviderRequest:
    response_format = response_format or ProviderResponseFormat()
    retry_policy = retry_policy or ProviderRetryPolicy()
    if route.contract_version == "1":
        return ProviderRequest(
            model=route.model,
            request_id=request_id,
            input=input,
            tools=tools,
            max_output_tokens=max_output_tokens,
        )
    tool_choice = tool_choice_policy or (
        ToolChoicePolicy.AUTO if tools else ToolChoicePolicy.NONE
    )
    return ProviderRequest(
        model=route.model,
        request_id=request_id,
        input=input,
        tools=tools,
        max_output_tokens=max_output_tokens,
        contract_version="2",
        capability_alias=route.capability,
        capability_profile=route.capability_profile,
        catalog_version=route.catalog_version,
        reasoning_policy=route.reasoning_policy,
        response_format=response_format,
        store_policy=StorePolicy.NEVER,
        conversation_state_policy=ConversationStatePolicy.STATELESS,
        cache_policy=CachePolicy.DISABLED,
        tool_choice_policy=tool_choice,
        built_in_tools=(),
        parallel_tool_policy=ParallelToolPolicy.DISABLED,
        multimodal_inputs=input_modalities,
        output_modalities=frozenset({OutputModality.TEXT}),
        retry_policy=retry_policy,
        fallback_policy=FallbackPolicy.SAME_REGION_REQUIRED,
        region_policy=ProviderRegionPolicy(required_region=route.region),
        data_classification=data_classification,
    )


def catalog_for_settings(settings: Settings) -> ModelCatalog:
    return load_model_catalog(settings)
