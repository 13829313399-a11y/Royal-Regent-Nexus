from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from app.services.ai.providers.capabilities import (
    CachePolicy,
    ConversationStatePolicy,
    DataClassification,
    FallbackPolicy,
    InputModality,
    ModelCapability,
    OutputModality,
    ParallelToolPolicy,
    ProviderRegionPolicy,
    ProviderResponseFormat,
    ProviderRetryPolicy,
    ReasoningPolicy,
    StorePolicy,
    ToolChoicePolicy,
)

ProviderMessageRole = Literal["system", "user", "assistant"]
ProviderImageMediaType = Literal["image/png", "image/jpeg", "image/webp"]


@dataclass(frozen=True, slots=True)
class ProviderTextContent:
    text: str


@dataclass(frozen=True, slots=True)
class ProviderImageContent:
    attachment_id: str
    media_type: ProviderImageMediaType
    data: bytearray = field(repr=False)
    source: Literal["USER_PROVIDED"] = "USER_PROVIDED"


ProviderMessageContent = str | tuple[ProviderTextContent | ProviderImageContent, ...]


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    role: ProviderMessageRole
    content: ProviderMessageContent


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ProviderToolResult:
    call_id: str
    output: str


ProviderInputItem = ProviderMessage | ProviderToolCall | ProviderToolResult


@dataclass(frozen=True, slots=True)
class ProviderToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    model: str
    request_id: str
    input: tuple[ProviderInputItem, ...]
    tools: tuple[ProviderToolDefinition, ...] = ()
    max_output_tokens: int | None = None
    contract_version: Literal["1", "2"] = "1"
    capability_alias: ModelCapability | None = None
    capability_profile: str = ""
    catalog_version: str = ""
    reasoning_policy: ReasoningPolicy | None = None
    response_format: ProviderResponseFormat = field(
        default_factory=ProviderResponseFormat
    )
    store_policy: StorePolicy = StorePolicy.NEVER
    conversation_state_policy: ConversationStatePolicy = (
        ConversationStatePolicy.STATELESS
    )
    cache_policy: CachePolicy = CachePolicy.DISABLED
    tool_choice_policy: ToolChoicePolicy = ToolChoicePolicy.AUTO
    built_in_tools: tuple[str, ...] = ()
    parallel_tool_policy: ParallelToolPolicy = ParallelToolPolicy.DISABLED
    multimodal_inputs: frozenset[InputModality] = frozenset({InputModality.TEXT})
    output_modalities: frozenset[OutputModality] = frozenset({OutputModality.TEXT})
    retry_policy: ProviderRetryPolicy = field(default_factory=ProviderRetryPolicy)
    fallback_policy: FallbackPolicy = FallbackPolicy.NONE
    region_policy: ProviderRegionPolicy | None = None
    data_classification: DataClassification = DataClassification.INTERNAL


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    text: str = ""
    tool_calls: tuple[ProviderToolCall, ...] = ()
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    response_id: str = ""


@dataclass(frozen=True, slots=True)
class ProviderTextDelta:
    type: Literal["text_delta"] = "text_delta"
    delta: str = ""


@dataclass(frozen=True, slots=True)
class ProviderToolCallEvent:
    tool_call: ProviderToolCall
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True, slots=True)
class ProviderCompleted:
    response_id: str = ""
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    type: Literal["completed"] = "completed"


class ProviderErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    INVALID_EVENT = "invalid_event"
    REQUEST_FAILED = "request_failed"


@dataclass(frozen=True, slots=True)
class ProviderRefusal:
    reason: str = "model_refusal"
    type: Literal["refusal"] = "refusal"


@dataclass(frozen=True, slots=True)
class ProviderIncomplete:
    reason: str = "unknown"
    type: Literal["incomplete"] = "incomplete"


@dataclass(frozen=True, slots=True)
class ProviderUsageEvent:
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    type: Literal["usage"] = "usage"


@dataclass(frozen=True, slots=True)
class ProviderErrorEvent:
    code: ProviderErrorCode = ProviderErrorCode.REQUEST_FAILED
    retryable: bool = False
    status_code: int | None = None
    type: Literal["error"] = "error"


ProviderStreamEvent = (
    ProviderTextDelta
    | ProviderToolCallEvent
    | ProviderRefusal
    | ProviderIncomplete
    | ProviderUsageEvent
    | ProviderErrorEvent
    | ProviderCompleted
)


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str
    supports_streaming: bool
    supports_function_calls: bool

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...

    def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]: ...

    async def aclose(self) -> None: ...
