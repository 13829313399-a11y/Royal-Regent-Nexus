import asyncio
import base64
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from app.services.ai.providers.base import (
    ProviderCompleted,
    ProviderError,
    ProviderErrorCode,
    ProviderErrorEvent,
    ProviderImageContent,
    ProviderIncomplete,
    ProviderInputItem,
    ProviderMessage,
    ProviderRefusal,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderTextContent,
    ProviderTextDelta,
    ProviderToolCall,
    ProviderToolCallEvent,
    ProviderToolResult,
    ProviderUsage,
    ProviderUsageEvent,
)
from app.services.ai.providers.capabilities import (
    CachePolicy,
    ConversationStatePolicy,
    InputModality,
    ParallelToolPolicy,
    ResponseFormatKind,
    RetryMode,
    StorePolicy,
    ToolChoicePolicy,
)
from app.services.ai.providers.catalog import ModelCatalog, ModelCatalogError

_IGNORED_STREAM_EVENT_TYPES = {
    "response.created",
    "response.in_progress",
    "response.queued",
    "response.output_item.added",
    "response.content_part.added",
    "response.content_part.done",
    "response.output_text.done",
    "response.function_call_arguments.delta",
    "response.function_call_arguments.done",
    "response.reasoning_summary_part.added",
    "response.reasoning_summary_part.done",
    "response.reasoning_summary_text.delta",
    "response.reasoning_summary_text.done",
    "response.reasoning_text.delta",
    "response.reasoning_text.done",
    "response.refusal.delta",
    "response.refusal.done",
}
_SENSITIVE_HTTP_LOGGERS = ("openai", "httpx", "httpcore")
_SAFE_INCOMPLETE_REASONS = {"max_output_tokens", "content_filter"}
_TRANSIENT_ERROR_CODES = {
    ProviderErrorCode.RATE_LIMITED,
    ProviderErrorCode.PROVIDER_UNAVAILABLE,
    ProviderErrorCode.TIMEOUT,
}


def _clamp_sensitive_http_loggers() -> None:
    for logger_name in _SENSITIVE_HTTP_LOGGERS:
        logger = logging.getLogger(logger_name)
        if logger.level < logging.ERROR:
            logger.setLevel(logging.ERROR)


def _read(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage_from(value: object) -> ProviderUsage:
    usage = _read(value, "usage")
    if usage is None:
        return ProviderUsage()
    return ProviderUsage(
        input_tokens=int(_read(usage, "input_tokens", 0) or 0),
        output_tokens=int(_read(usage, "output_tokens", 0) or 0),
        total_tokens=int(_read(usage, "total_tokens", 0) or 0),
    )


def _tool_call_from(value: object) -> ProviderToolCall | None:
    if _read(value, "type") != "function_call":
        return None
    call_id = _read(value, "call_id")
    name = _read(value, "name")
    arguments = _read(value, "arguments")
    if not all(isinstance(item, str) and item for item in (call_id, name, arguments)):
        raise ProviderError(
            ProviderErrorCode.INVALID_EVENT,
            "Provider returned an invalid function call event.",
        )
    return ProviderToolCall(
        call_id=call_id,
        name=name,
        arguments_json=arguments,
    )


def _tool_calls_from_response(value: object) -> tuple[ProviderToolCall, ...]:
    output = _read(value, "output", ()) or ()
    try:
        return tuple(
            tool_call
            for item in output
            if (tool_call := _tool_call_from(item)) is not None
        )
    except TypeError as exc:
        raise ProviderError(
            ProviderErrorCode.INVALID_EVENT,
            "Provider returned an invalid response payload.",
        ) from exc


def _text_from_response(value: object) -> str:
    output_text = _read(value, "output_text")
    if isinstance(output_text, str):
        return output_text

    text_parts: list[str] = []
    output = _read(value, "output", ()) or ()
    try:
        for item in output:
            if _read(item, "type") != "message":
                continue
            for content in _read(item, "content", ()) or ():
                if _read(content, "type") == "output_text":
                    text = _read(content, "text")
                    if isinstance(text, str):
                        text_parts.append(text)
    except TypeError as exc:
        raise ProviderError(
            ProviderErrorCode.INVALID_EVENT,
            "Provider returned an invalid response payload.",
        ) from exc
    return "".join(text_parts)


def _ensure_completed_response(value: object) -> None:
    response_status = _read(value, "status")
    if not isinstance(response_status, str):
        raise ProviderError(
            ProviderErrorCode.INVALID_EVENT,
            "Provider returned an invalid response status.",
        )
    if response_status != "completed":
        raise ProviderError(
            ProviderErrorCode.REQUEST_FAILED,
            "AI provider did not complete the response.",
        )


def _incomplete_reason(value: object) -> str:
    response = _read(value, "response", value)
    details = _read(response, "incomplete_details")
    reason = _read(details, "reason")
    return reason if reason in _SAFE_INCOMPLETE_REASONS else "unknown"


def _response_has_refusal(value: object) -> bool:
    output = _read(value, "output", ()) or ()
    try:
        return any(
            _read(content, "type") == "refusal"
            for item in output
            for content in (_read(item, "content", ()) or ())
        )
    except TypeError as exc:
        raise ProviderError(
            ProviderErrorCode.INVALID_EVENT,
            "Provider returned an invalid response payload.",
        ) from exc


def _serialize_message_content(
    content: object,
) -> str | list[dict[str, object]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, tuple):
        raise TypeError("Unsupported provider message content")

    serialized: list[dict[str, object]] = []
    for part in content:
        if isinstance(part, ProviderTextContent):
            serialized.append({"type": "input_text", "text": part.text})
            continue
        if isinstance(part, ProviderImageContent):
            encoded: bytes | None = None
            try:
                encoded = base64.b64encode(part.data)
                image_url = (
                    f"data:{part.media_type};base64,{encoded.decode('ascii')}"
                )
            finally:
                encoded = None
            serialized.append({"type": "input_image", "image_url": image_url})
            continue
        raise TypeError(f"Unsupported provider content part: {type(part).__name__}")
    return serialized


def _serialize_input(item: ProviderInputItem) -> dict[str, object]:
    if isinstance(item, ProviderMessage):
        return {"role": item.role, "content": _serialize_message_content(item.content)}
    if isinstance(item, ProviderToolCall):
        return {
            "type": "function_call",
            "call_id": item.call_id,
            "name": item.name,
            "arguments": item.arguments_json,
        }
    if isinstance(item, ProviderToolResult):
        return {
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": item.output,
        }
    raise TypeError(f"Unsupported provider input item: {type(item).__name__}")


def _release_serialized_images(kwargs: dict[str, object]) -> None:
    inputs = kwargs.get("input")
    if not isinstance(inputs, list):
        return
    for item in inputs:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "input_image":
                part["image_url"] = ""


def _message_has_image(message: ProviderMessage) -> bool:
    return isinstance(message.content, tuple) and any(
        isinstance(part, ProviderImageContent) for part in message.content
    )


def _validate_image_placement(request: ProviderRequest) -> None:
    messages = [item for item in request.input if isinstance(item, ProviderMessage)]
    image_messages = [message for message in messages if _message_has_image(message)]
    if not image_messages:
        return

    last_user_message = next(
        (message for message in reversed(messages) if message.role == "user"),
        None,
    )
    has_tool_replay = any(
        isinstance(item, (ProviderToolCall, ProviderToolResult))
        for item in request.input
    )
    if (
        len(image_messages) != 1
        or image_messages[0] is not last_user_message
        or image_messages[0] is not messages[-1]
        or image_messages[0].role != "user"
        or has_tool_replay
        or bool(request.tools)
    ):
        raise ProviderError(
            ProviderErrorCode.REQUEST_FAILED,
            "Provider image request violates the safe placement policy.",
        )


def _actual_input_modalities(request: ProviderRequest) -> frozenset[InputModality]:
    modalities = {InputModality.TEXT}
    if any(
        isinstance(item, ProviderMessage) and _message_has_image(item)
        for item in request.input
    ):
        modalities.add(InputModality.IMAGE)
    return frozenset(modalities)


def _is_retry_safe(request: ProviderRequest) -> bool:
    return (
        request.retry_policy.mode is RetryMode.SAFE_TRANSIENT
        and not request.tools
        and not request.built_in_tools
        and request.tool_choice_policy is ToolChoicePolicy.NONE
        and InputModality.IMAGE not in request.multimodal_inputs
        and all(
            not isinstance(item, (ProviderToolCall, ProviderToolResult))
            for item in request.input
        )
        and request.store_policy is StorePolicy.NEVER
        and request.conversation_state_policy is ConversationStatePolicy.STATELESS
    )


def _should_retry(
    request: ProviderRequest,
    error: ProviderError,
    *,
    completed_attempts: int,
) -> bool:
    return (
        _is_retry_safe(request)
        and completed_attempts < request.retry_policy.max_attempts
        and error.code in _TRANSIENT_ERROR_CODES
    )


def _normalize_error(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, (APITimeoutError, TimeoutError, asyncio.TimeoutError)):
        return ProviderError(
            ProviderErrorCode.TIMEOUT,
            "AI provider request timed out.",
            retryable=True,
        )

    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code in {401, 403}:
        return ProviderError(
            ProviderErrorCode.AUTHENTICATION_FAILED,
            "AI provider authentication failed.",
            status_code=status_code,
        )
    if status_code == 429:
        return ProviderError(
            ProviderErrorCode.RATE_LIMITED,
            "AI provider rate limit exceeded.",
            status_code=status_code,
            retryable=True,
        )
    if isinstance(status_code, int) and status_code >= 500:
        return ProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "AI provider is temporarily unavailable.",
            status_code=status_code,
            retryable=True,
        )
    if isinstance(exc, APIConnectionError):
        return ProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "AI provider is temporarily unavailable.",
            retryable=True,
        )
    return ProviderError(
        ProviderErrorCode.REQUEST_FAILED,
        "AI provider request failed.",
        status_code=status_code if isinstance(status_code, int) else None,
    )


class QwenResponsesProvider:
    provider_name = "qwen"
    supports_streaming = True
    supports_function_calls = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        reasoning_effort: str = "low",
        catalog: ModelCatalog | None = None,
        region: str = "cn-beijing",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Qwen API key is required")
        _clamp_sensitive_http_loggers()
        self.reasoning_effort = reasoning_effort
        self.catalog = catalog
        self.region = region
        self._sleep = sleep
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._closed = False

    def _v2_reasoning_effort(self, request: ProviderRequest) -> str:
        if (
            self.catalog is None
            or request.capability_alias is None
            or request.reasoning_policy is None
            or request.region_policy is None
        ):
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider capability request is incomplete.",
            )
        if request.region_policy.required_region != self.region:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider region policy does not match the configured endpoint.",
            )
        try:
            profile = self.catalog.resolve(
                request.capability_alias,
                provider=self.provider_name,
                region=self.region,
            )
        except ModelCatalogError as exc:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider capability is unavailable.",
            ) from exc
        if (
            request.capability_profile != profile.profile_id
            or request.catalog_version != self.catalog.version
            or request.model != profile.model
            or request.multimodal_inputs != _actual_input_modalities(request)
            or not request.multimodal_inputs.issubset(profile.input_modalities)
            or not request.output_modalities.issubset(profile.output_modalities)
        ):
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider capability request does not match the routed profile.",
            )
        if request.store_policy is not StorePolicy.NEVER:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider storage policy is not allowed.",
            )
        if request.conversation_state_policy is not ConversationStatePolicy.STATELESS:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider conversation state is not allowed.",
            )
        if request.cache_policy is not CachePolicy.DISABLED:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider cache policy is not allowed.",
            )
        if request.parallel_tool_policy is not ParallelToolPolicy.DISABLED:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Parallel Provider tools are not allowed.",
            )
        if request.built_in_tools:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Built-in Provider tools are not registered.",
            )
        if request.tools and not profile.supports_custom_tools:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Custom Provider tools are unavailable.",
            )
        if request.tool_choice_policy is ToolChoicePolicy.NONE and request.tools:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Provider tool choice conflicts with custom tools.",
            )
        if request.tool_choice_policy is ToolChoicePolicy.REQUIRED and not request.tools:
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Required Provider tool choice has no tools.",
            )
        if (
            request.response_format.kind is ResponseFormatKind.JSON_SCHEMA
            and not profile.supports_structured_output
        ):
            raise ProviderError(
                ProviderErrorCode.REQUEST_FAILED,
                "Structured Provider output is unavailable.",
            )
        return profile.effort_for(request.reasoning_policy)

    def _request_kwargs(
        self,
        request: ProviderRequest,
        *,
        stream: bool,
    ) -> dict[str, object]:
        _validate_image_placement(request)
        reasoning_effort = (
            self._v2_reasoning_effort(request)
            if request.contract_version == "2"
            else self.reasoning_effort
        )
        kwargs: dict[str, object] = {
            "model": request.model,
            "input": [_serialize_input(item) for item in request.input],
            "store": False,
            "stream": stream,
            "parallel_tool_calls": False,
            "reasoning": {"effort": reasoning_effort},
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                }
                for tool in request.tools
            ]
        if request.contract_version == "2":
            kwargs["tool_choice"] = request.tool_choice_policy.value.lower()
            if request.response_format.kind is ResponseFormatKind.JSON_SCHEMA:
                kwargs["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": request.response_format.name,
                        "schema": dict(request.response_format.schema),
                        "strict": request.response_format.strict,
                    }
                }
        if request.max_output_tokens is not None:
            kwargs["max_output_tokens"] = request.max_output_tokens
        return kwargs

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        completed_attempts = 0
        while True:
            completed_attempts += 1
            kwargs: dict[str, object] = {}
            try:
                kwargs = self._request_kwargs(request, stream=False)
                response = await self._client.responses.create(**kwargs)
                _ensure_completed_response(response)
                return ProviderResponse(
                    text=_text_from_response(response),
                    tool_calls=_tool_calls_from_response(response),
                    usage=_usage_from(response),
                    response_id=str(_read(response, "id", "") or ""),
                )
            except Exception as exc:  # noqa: BLE001 - normalize SDK boundary errors
                error = _normalize_error(exc)
                if not _should_retry(
                    request,
                    error,
                    completed_attempts=completed_attempts,
                ):
                    raise error from None
                await self._sleep(
                    request.retry_policy.delay_for_retry(completed_attempts)
                )
            finally:
                _release_serialized_images(kwargs)

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        completed_attempts = 0
        while True:
            completed_attempts += 1
            emitted = False
            try:
                async for event in self._stream_once(request):
                    emitted = True
                    yield event
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize SDK boundary errors
                error = _normalize_error(exc)
                if emitted or not _should_retry(
                    request,
                    error,
                    completed_attempts=completed_attempts,
                ):
                    raise error from None
                await self._sleep(
                    request.retry_policy.delay_for_retry(completed_attempts)
                )

    async def _stream_once(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[ProviderStreamEvent]:
        completed = False
        refusal_emitted = False
        emitted_call_ids: set[str] = set()
        stream: object | None = None
        kwargs: dict[str, object] = {}
        try:
            kwargs = self._request_kwargs(request, stream=True)
            stream = await self._client.responses.create(**kwargs)
            _release_serialized_images(kwargs)
            async for event in stream:
                event_type = _read(event, "type")
                if not isinstance(event_type, str) or not event_type:
                    raise ProviderError(
                        ProviderErrorCode.INVALID_EVENT,
                        "Provider returned an invalid stream event.",
                    )
                if event_type == "response.output_text.delta":
                    delta = _read(event, "delta")
                    if not isinstance(delta, str):
                        raise ProviderError(
                            ProviderErrorCode.INVALID_EVENT,
                            "Provider returned an invalid text event.",
                        )
                    yield ProviderTextDelta(delta=delta)
                    continue
                if event_type in {"response.refusal.delta", "response.refusal.done"}:
                    if (
                        request.contract_version == "2"
                        and event_type.endswith("done")
                        and not refusal_emitted
                    ):
                        refusal_emitted = True
                        yield ProviderRefusal()
                    continue
                if event_type == "response.output_item.done":
                    tool_call = _tool_call_from(_read(event, "item"))
                    if tool_call is not None:
                        emitted_call_ids.add(tool_call.call_id)
                        yield ProviderToolCallEvent(tool_call=tool_call)
                    continue
                if event_type == "response.completed":
                    response = _read(event, "response")
                    if response is None:
                        raise ProviderError(
                            ProviderErrorCode.INVALID_EVENT,
                            "Provider returned an invalid completion event.",
                        )
                    _ensure_completed_response(response)
                    if request.contract_version == "2" and _response_has_refusal(response):
                        completed = True
                        if not refusal_emitted:
                            refusal_emitted = True
                            yield ProviderRefusal()
                        continue
                    for tool_call in _tool_calls_from_response(response):
                        if tool_call.call_id not in emitted_call_ids:
                            emitted_call_ids.add(tool_call.call_id)
                            yield ProviderToolCallEvent(tool_call=tool_call)
                    completed = True
                    if request.contract_version == "2":
                        yield ProviderUsageEvent(usage=_usage_from(response))
                    yield ProviderCompleted(
                        response_id=str(_read(response, "id", "") or ""),
                        usage=_usage_from(response),
                    )
                    continue
                if event_type == "response.incomplete":
                    if request.contract_version == "2":
                        completed = True
                        yield ProviderIncomplete(reason=_incomplete_reason(event))
                        continue
                    raise ProviderError(
                        ProviderErrorCode.REQUEST_FAILED,
                        "AI provider did not complete the response.",
                    )
                if event_type in {"response.failed", "error"}:
                    if request.contract_version == "2":
                        completed = True
                        yield ProviderErrorEvent(
                            code=ProviderErrorCode.REQUEST_FAILED
                        )
                        continue
                    raise ProviderError(
                        ProviderErrorCode.REQUEST_FAILED,
                        "AI provider did not complete the response.",
                    )
                if event_type not in _IGNORED_STREAM_EVENT_TYPES:
                    raise ProviderError(
                        ProviderErrorCode.INVALID_EVENT,
                        "Provider returned an unsupported stream event.",
                    )
            if not completed:
                raise ProviderError(
                    ProviderErrorCode.INVALID_EVENT,
                    "Provider stream ended without a completion event.",
                )
        finally:
            _release_serialized_images(kwargs)
            if stream is not None:
                close = getattr(stream, "close", None)
                if close is not None:
                    try:
                        await close()
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001, S110 - preserve stream outcome
                        pass

    async def aclose(self) -> None:
        if self._closed:
            return
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()
        self._closed = True
