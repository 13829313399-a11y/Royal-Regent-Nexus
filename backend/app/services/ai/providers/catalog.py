from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.ai.providers.capabilities import (
    InputModality,
    ModelCapability,
    OutputModality,
    ProviderCapabilityProfile,
    ReasoningPolicy,
)

if TYPE_CHECKING:
    from app.core.config import Settings

_CATALOG_KEYS = {"version", "profiles"}
_PROFILE_KEYS = {
    "profile_id",
    "provider",
    "model",
    "region",
    "capabilities",
    "reasoning_efforts",
    "input_modalities",
    "output_modalities",
    "supports_streaming",
    "supports_custom_tools",
    "supports_structured_output",
}
_PROHIBITED_CAPABILITIES = frozenset({ModelCapability.DOCUMENT_OCR})


class ModelCatalogError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    version: str
    profiles: tuple[ProviderCapabilityProfile, ...]

    def __post_init__(self) -> None:
        if self.version != "1":
            raise ModelCatalogError("unsupported_catalog_version")
        if not self.profiles:
            raise ModelCatalogError("missing_catalog_profiles")
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ModelCatalogError("duplicate_profile_id")
        aliases: set[tuple[str, str, ModelCapability]] = set()
        for profile in self.profiles:
            prohibited = profile.capabilities.intersection(_PROHIBITED_CAPABILITIES)
            if prohibited:
                raise ModelCatalogError("prohibited_capability")
            for capability in profile.capabilities:
                key = (profile.provider, profile.region, capability)
                if key in aliases:
                    raise ModelCatalogError("duplicate_capability_alias")
                aliases.add(key)

    def resolve(
        self,
        capability: ModelCapability,
        *,
        provider: str,
        region: str,
    ) -> ProviderCapabilityProfile:
        matches = tuple(
            profile
            for profile in self.profiles
            if profile.provider == provider
            and profile.region == region
            and capability in profile.capabilities
        )
        if not matches:
            same_provider = any(
                profile.provider == provider and capability in profile.capabilities
                for profile in self.profiles
            )
            raise ModelCatalogError(
                "region_mismatch" if same_provider else "capability_unavailable"
            )
        if len(matches) != 1:
            raise ModelCatalogError("duplicate_capability_alias")
        return matches[0]


def _strict_mapping(value: object, *, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ModelCatalogError(reason)
    return value


def _strict_sequence(value: object, *, reason: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ModelCatalogError(reason)
    return value


def _profile_from_json(value: object) -> ProviderCapabilityProfile:
    source = _strict_mapping(value, reason="invalid_catalog_profile")
    if set(source) != _PROFILE_KEYS:
        raise ModelCatalogError("invalid_catalog_profile_fields")
    try:
        reasoning = _strict_mapping(
            source["reasoning_efforts"],
            reason="invalid_reasoning_policy",
        )
        if set(reasoning) != {policy.value for policy in ReasoningPolicy}:
            raise ModelCatalogError("invalid_reasoning_policy")
        return ProviderCapabilityProfile(
            profile_id=str(source["profile_id"]),
            provider=str(source["provider"]),
            model=str(source["model"]),
            region=str(source["region"]),
            capabilities=frozenset(
                ModelCapability(item)
                for item in _strict_sequence(
                    source["capabilities"],
                    reason="invalid_capabilities",
                )
            ),
            reasoning_efforts=tuple(
                (policy, str(reasoning[policy.value])) for policy in ReasoningPolicy
            ),
            input_modalities=frozenset(
                InputModality(item)
                for item in _strict_sequence(
                    source["input_modalities"],
                    reason="invalid_input_modalities",
                )
            ),
            output_modalities=frozenset(
                OutputModality(item)
                for item in _strict_sequence(
                    source["output_modalities"],
                    reason="invalid_output_modalities",
                )
            ),
            supports_streaming=source["supports_streaming"] is True,
            supports_custom_tools=source["supports_custom_tools"] is True,
            supports_structured_output=source["supports_structured_output"] is True,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ModelCatalogError):
            raise
        raise ModelCatalogError("invalid_catalog_profile") from exc


def parse_model_catalog(raw: str) -> ModelCatalog:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ModelCatalogError("invalid_catalog_json") from exc
    source = _strict_mapping(payload, reason="invalid_catalog_document")
    if set(source) != _CATALOG_KEYS:
        raise ModelCatalogError("invalid_catalog_fields")
    profiles = tuple(
        _profile_from_json(item)
        for item in _strict_sequence(
            source["profiles"],
            reason="invalid_catalog_profiles",
        )
    )
    return ModelCatalog(version=str(source["version"]), profiles=profiles)


def _default_profile(settings: Settings) -> ProviderCapabilityProfile:
    provider = settings.ai_provider.strip().lower()
    model = settings.ai_default_model.strip()
    region = settings.ai_region.strip().lower()
    return ProviderCapabilityProfile(
        profile_id=f"{provider}-{region}-default-v1",
        provider=provider,
        model=model,
        region=region,
        capabilities=frozenset(
            {
                ModelCapability.FAST_ROUTER,
                ModelCapability.GENERAL_CHAT,
                ModelCapability.DEEP_REASONING,
                ModelCapability.MULTIMODAL_GENERAL,
                ModelCapability.STRUCTURED_EXTRACTION,
                ModelCapability.TRANSLATION,
            }
        ),
        reasoning_efforts=(
            (ReasoningPolicy.FAST, "low"),
            (ReasoningPolicy.BALANCED, "medium"),
            (ReasoningPolicy.DEEP, "high"),
        ),
        input_modalities=frozenset({InputModality.TEXT, InputModality.IMAGE}),
        output_modalities=frozenset({OutputModality.TEXT}),
        supports_streaming=True,
        supports_custom_tools=True,
        supports_structured_output=True,
    )


def load_model_catalog(settings: Settings) -> ModelCatalog:
    raw = settings.ai_model_catalog_json.strip()
    if raw:
        return parse_model_catalog(raw)
    try:
        return ModelCatalog(version="1", profiles=(_default_profile(settings),))
    except ValueError as exc:
        if isinstance(exc, ModelCatalogError):
            raise
        raise ModelCatalogError("invalid_default_catalog") from exc
