from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

_IDENTIFIER_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}


class ModelCapability(StrEnum):
    FAST_ROUTER = "FAST_ROUTER"
    GENERAL_CHAT = "GENERAL_CHAT"
    DEEP_REASONING = "DEEP_REASONING"
    MULTIMODAL_GENERAL = "MULTIMODAL_GENERAL"
    STRUCTURED_EXTRACTION = "STRUCTURED_EXTRACTION"
    DOCUMENT_OCR = "DOCUMENT_OCR"
    TRANSLATION = "TRANSLATION"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"


class ReasoningPolicy(StrEnum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"


class ResponseFormatKind(StrEnum):
    TEXT = "TEXT"
    JSON_SCHEMA = "JSON_SCHEMA"


class StorePolicy(StrEnum):
    NEVER = "NEVER"


class ConversationStatePolicy(StrEnum):
    STATELESS = "STATELESS"


class CachePolicy(StrEnum):
    DISABLED = "DISABLED"


class ToolChoicePolicy(StrEnum):
    NONE = "NONE"
    AUTO = "AUTO"
    REQUIRED = "REQUIRED"


class ParallelToolPolicy(StrEnum):
    DISABLED = "DISABLED"


class InputModality(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class OutputModality(StrEnum):
    TEXT = "TEXT"


class RetryMode(StrEnum):
    NONE = "NONE"
    SAFE_TRANSIENT = "SAFE_TRANSIENT"


class FallbackPolicy(StrEnum):
    NONE = "NONE"
    SAME_REGION_REQUIRED = "SAME_REGION_REQUIRED"


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True, slots=True)
class ProviderResponseFormat:
    kind: ResponseFormatKind = ResponseFormatKind.TEXT
    name: str = ""
    schema: Mapping[str, object] = field(default_factory=dict)
    strict: bool = True

    def __post_init__(self) -> None:
        if self.kind is ResponseFormatKind.TEXT:
            if self.name or self.schema:
                raise ValueError("text responses cannot include a JSON schema")
            return
        if not _IDENTIFIER_PATTERN.fullmatch(self.name):
            raise ValueError("structured response name is invalid")
        if self.schema.get("type") != "object":
            raise ValueError("structured response schema must be an object")
        if self.schema.get("additionalProperties") is not False:
            raise ValueError("structured response schema must be closed")


@dataclass(frozen=True, slots=True)
class ProviderRetryPolicy:
    mode: RetryMode = RetryMode.NONE
    max_attempts: int = 1
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.2

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("provider retry attempts must be between 1 and 3")
        if self.mode is RetryMode.NONE and self.max_attempts != 1:
            raise ValueError("disabled retries must use exactly one attempt")
        if not 0 <= self.base_delay_seconds <= self.max_delay_seconds <= 1:
            raise ValueError("provider retry delays are outside the safe bounds")

    def delay_for_retry(self, completed_attempts: int) -> float:
        return min(
            self.base_delay_seconds * (2 ** max(completed_attempts - 1, 0)),
            self.max_delay_seconds,
        )


@dataclass(frozen=True, slots=True)
class ProviderRegionPolicy:
    required_region: str
    allow_cross_region_fallback: bool = False

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.required_region):
            raise ValueError("provider region is invalid")
        if self.allow_cross_region_fallback:
            raise ValueError("cross-region fallback is not allowed")


@dataclass(frozen=True, slots=True)
class ProviderCapabilityProfile:
    profile_id: str
    provider: str
    model: str
    region: str
    capabilities: frozenset[ModelCapability]
    reasoning_efforts: tuple[tuple[ReasoningPolicy, str], ...]
    input_modalities: frozenset[InputModality]
    output_modalities: frozenset[OutputModality]
    supports_streaming: bool
    supports_custom_tools: bool
    supports_structured_output: bool

    def __post_init__(self) -> None:
        for value in (self.profile_id, self.provider, self.model, self.region):
            if not _IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError("provider capability profile identifier is invalid")
        if not self.capabilities:
            raise ValueError("provider capability profile has no capabilities")
        if InputModality.TEXT not in self.input_modalities:
            raise ValueError("provider capability profile must support text input")
        if OutputModality.TEXT not in self.output_modalities:
            raise ValueError("provider capability profile must support text output")
        policies = [policy for policy, _effort in self.reasoning_efforts]
        if len(policies) != len(set(policies)) or set(policies) != set(ReasoningPolicy):
            raise ValueError("provider reasoning policies must be complete and unique")
        if any(effort not in _REASONING_EFFORTS for _policy, effort in self.reasoning_efforts):
            raise ValueError("provider reasoning effort is unsupported")

    def effort_for(self, policy: ReasoningPolicy) -> str:
        return dict(self.reasoning_efforts)[policy]
