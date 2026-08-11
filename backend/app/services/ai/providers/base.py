from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

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


ProviderStreamEvent = ProviderTextDelta | ProviderToolCallEvent | ProviderCompleted


class ProviderErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    INVALID_EVENT = "invalid_event"
    REQUEST_FAILED = "request_failed"


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
