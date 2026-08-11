import asyncio
import inspect
import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import perf_counter

from app.core.config import Settings
from app.schemas.ai import (
    AIChatRequest,
    AIPageContextInput,
    AIServerPageContext,
    AIStreamEvent,
    AIStreamEventType,
)
from app.services.ai.attachment_service import (
    AIAttachmentValidationError,
    PreparedImageAttachment,
    clear_prepared_attachments,
    discard_raw_attachment_inputs,
    prepare_image_attachments,
)
from app.services.ai.context_builder import render_server_page_context, supports_vision
from app.services.ai.output_policy import (
    SYSTEM_POLICY,
    AIErrorCode,
    PublicAIError,
    internal_error,
    public_configuration_error,
    public_provider_error,
    timeout_error,
)
from app.services.ai.provider_factory import get_vision_provider_status
from app.services.ai.providers.base import (
    LLMProvider,
    ProviderCompleted,
    ProviderError,
    ProviderErrorCode,
    ProviderImageContent,
    ProviderMessage,
    ProviderRequest,
    ProviderTextContent,
    ProviderTextDelta,
    ProviderToolCall,
    ProviderToolCallEvent,
    ProviderToolResult,
)
from app.services.ai.runtime_gate import is_ai_runtime_disabled
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import ToolRegistry

ai_logger = logging.getLogger("app.ai")
_TOOL_CALL_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_MAX_TOOL_CALLS_PER_ROUND = 8
_MODEL_DATA_URL_PATTERN = re.compile(r"data:image", re.IGNORECASE)
_MODEL_LONG_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{512,}={0,2}")
_MODEL_OUTPUT_GUARD_CHARS = 512
_MAX_VISION_MODEL_OUTPUT_CHARS = 65_536
_ASCII_WHITESPACE_TRANSLATION = str.maketrans("", "", " \t\r\n\v\f")


@dataclass(frozen=True, slots=True)
class ValidatedChatInput:
    messages: tuple[ProviderMessage, ...]
    message_count: int
    input_chars: int
    page_context: AIPageContextInput | None = None
    server_page_context: AIServerPageContext | None = None
    attachments: tuple[PreparedImageAttachment, ...] = ()


class AIRequestValidationError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_error = PublicAIError(
            code=AIErrorCode.INVALID_REQUEST,
            message=message,
        )


def validate_chat_request_envelope(
    request: AIChatRequest,
    settings: Settings,
) -> ValidatedChatInput:
    if len(request.messages) > settings.ai_max_input_messages:
        raise AIRequestValidationError(
            f"消息数量不能超过 {settings.ai_max_input_messages} 条。"
        )
    if request.messages[-1].role != "user":
        raise AIRequestValidationError("最后一条消息必须由用户发送。")

    messages: list[ProviderMessage] = []
    input_chars = 0
    for message in request.messages:
        text = "".join(part.text for part in message.content)
        if not text.strip():
            raise AIRequestValidationError("消息内容不能为空。")
        if len(text) > settings.ai_max_input_message_chars:
            raise AIRequestValidationError(
                f"单条消息不能超过 {settings.ai_max_input_message_chars} 个字符。"
            )
        input_chars += len(text)
        messages.append(ProviderMessage(role=message.role, content=text))

    if input_chars > settings.ai_max_input_chars:
        raise AIRequestValidationError(
            f"消息总长度不能超过 {settings.ai_max_input_chars} 个字符。"
        )

    if request.attachments:
        vision_status = get_vision_provider_status(settings)
        if not vision_status.available:
            raise AIRequestValidationError("图片识别功能当前未启用。")
        consent = request.cloud_processing_consent
        attachment_ids = [attachment.id for attachment in request.attachments]
        if (
            len(set(attachment_ids)) != len(attachment_ids)
            or consent is None
            or consent.attachment_ids != attachment_ids
        ):
            raise AIRequestValidationError(
                "请确认本次图片将发送到阿里云北京视觉服务处理。"
            )
    elif request.cloud_processing_consent is not None:
        raise AIRequestValidationError("没有图片时不能提交云端图片处理确认。")

    return ValidatedChatInput(
        messages=tuple(messages),
        message_count=len(messages),
        input_chars=input_chars,
        page_context=request.page_context,
    )


def prepare_chat_attachments(
    chat: ValidatedChatInput,
    request: AIChatRequest,
    settings: Settings,
) -> ValidatedChatInput:
    if not request.attachments:
        return chat
    try:
        prepared = prepare_image_attachments(
            request.attachments,
            max_count=settings.ai_max_image_attachments,
            max_bytes=settings.ai_max_image_bytes,
            max_total_bytes=settings.ai_max_image_total_bytes,
            max_encoded_chars=settings.ai_max_image_encoded_chars,
            max_pixels=settings.ai_max_image_pixels,
            max_total_pixels=settings.ai_max_image_total_pixels,
        )
    except AIAttachmentValidationError as exc:
        raise AIRequestValidationError(exc.public_message) from None
    try:
        return replace(chat, attachments=prepared)
    except Exception:
        clear_prepared_attachments(prepared)
        raise


def validate_chat_request(
    request: AIChatRequest,
    settings: Settings,
) -> ValidatedChatInput:
    try:
        chat = validate_chat_request_envelope(request, settings)
        return prepare_chat_attachments(chat, request, settings)
    finally:
        discard_raw_attachment_inputs(request.attachments)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _model_output_detection_copy(text: str) -> str:
    return text.translate(_ASCII_WHITESPACE_TRANSLATION)


def _contains_sensitive_model_output(text: str) -> bool:
    detection_copy = _model_output_detection_copy(text)
    return bool(
        _MODEL_DATA_URL_PATTERN.search(detection_copy)
        or _MODEL_LONG_BASE64_PATTERN.search(detection_copy)
    )


async def _safe_close(target: object, method_name: str) -> None:
    close = getattr(target, method_name, None)
    if not callable(close):
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - cleanup must not replace the stream outcome
        return


class AIOrchestrator:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        settings: Settings,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        provider_started_recorder: Callable[[], None] | None = None,
        usage_recorder: Callable[[int], None] | None = None,
        completion_recorder: Callable[[], None] | None = None,
    ) -> None:
        if (tool_registry is None) != (tool_executor is None):
            raise ValueError(
                "tool_registry and tool_executor must be configured together"
            )
        self.provider = provider
        self.settings = settings
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.provider_started_recorder = provider_started_recorder
        self.usage_recorder = usage_recorder
        self.completion_recorder = completion_recorder

    async def stream(
        self,
        chat: ValidatedChatInput,
        *,
        request_id: str,
        user_id: str,
        tool_context: ToolExecutionContext | None = None,
    ) -> AsyncIterator[AIStreamEvent]:
        if self.tool_registry is not None and tool_context is None:
            clear_prepared_attachments(chat.attachments)
            raise ValueError("tool_context is required when tools are configured")
        sequence = 0
        output_chars = 0
        delta_count = 0
        tool_count = 0
        tool_rounds = 0
        tool_latency_ms = 0.0
        returned_rows = 0
        truncated = False
        observed_tool_error_code = ""
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        provider_stream: AsyncIterator[object] | None = None
        started_at = perf_counter()
        provider_name = self.provider.provider_name
        model = (
            self.settings.ai_vision_model.strip()
            if chat.attachments
            else self.settings.ai_default_model.strip()
        )
        pending_output = ""
        output_guard_tail = ""
        factory_id = (
            chat.server_page_context.verified_factory_id or ""
            if isinstance(chat.server_page_context, AIServerPageContext)
            else ""
        )
        module_id = (
            chat.server_page_context.verified_module_id
            if isinstance(chat.server_page_context, AIServerPageContext)
            else ""
        )

        def make_event(
            event_type: AIStreamEventType,
            payload: dict[str, object] | None = None,
        ) -> AIStreamEvent:
            nonlocal sequence
            sequence += 1
            return AIStreamEvent(
                request_id=request_id,
                sequence=sequence,
                type=event_type,
                timestamp=_timestamp(),
                payload=payload or {},
            )

        def log_terminal(status: str, error_code: str = "") -> None:
            duration_ms = (perf_counter() - started_at) * 1000
            ai_logger.info(
                "ai_stream request_id=%s user_id=%s provider=%s model=%s "
                "status=%s duration_ms=%.2f input_messages=%d input_chars=%d attachments=%d "
                "output_deltas=%d output_chars=%d tool_count=%d tool_rounds=%d "
                "factory_id=%s module_id=%s input_tokens=%d output_tokens=%d "
                "total_tokens=%d tool_latency_ms=%.2f returned_rows=%d "
                "truncated=%s error_code=%s",
                request_id,
                user_id,
                provider_name,
                model,
                status,
                duration_ms,
                chat.message_count,
                chat.input_chars,
                len(chat.attachments),
                delta_count,
                output_chars,
                tool_count,
                tool_rounds,
                factory_id,
                module_id,
                input_tokens,
                output_tokens,
                total_tokens,
                tool_latency_ms,
                returned_rows,
                truncated,
                error_code or observed_tool_error_code,
            )

        async def emit_error(error: PublicAIError) -> AsyncIterator[AIStreamEvent]:
            log_terminal("error", error.code.value)
            yield make_event("error", error.payload())

        preflight_error: PublicAIError | None = None
        if is_ai_runtime_disabled(self.settings):
            preflight_error = public_configuration_error("disabled")
        elif chat.attachments and not supports_vision(chat.server_page_context):
            preflight_error = PublicAIError(
                code=AIErrorCode.INVALID_PAGE_CONTEXT,
                message="图片识别需要当前页面的有效上下文，请刷新页面后重试。",
            )
        elif chat.attachments:
            vision_status = get_vision_provider_status(self.settings)
            expected_provider = "fake" if vision_status.test_only else "qwen"
            if not vision_status.available or provider_name != expected_provider:
                preflight_error = public_configuration_error(
                    vision_status.reason or "vision_provider_not_allowed"
                )
        if preflight_error is not None:
            try:
                clear_prepared_attachments(chat.attachments)
                yield make_event(
                    "response.started",
                    {
                        "provider": provider_name,
                        "model": model,
                        "attachment_count": len(chat.attachments),
                        "input_source": "USER_PROVIDED",
                    },
                )
                async for terminal in emit_error(preflight_error):
                    yield terminal
            finally:
                await _safe_close(self.provider, "aclose")
                clear_prepared_attachments(chat.attachments)
            return

        try:
            server_context_message = render_server_page_context(
                chat.server_page_context
            )
            provider_input = [ProviderMessage(role="system", content=SYSTEM_POLICY)]
            if server_context_message is not None:
                provider_input.append(
                    ProviderMessage(role="system", content=server_context_message)
                )
            provider_messages = list(chat.messages)
            if chat.attachments:
                final_message = provider_messages[-1]
                if final_message.role != "user" or not isinstance(
                    final_message.content, str
                ):
                    raise ValueError(
                        "validated image input must bind to the final user message"
                    )
                provider_messages[-1] = ProviderMessage(
                    role="user",
                    content=(
                        ProviderTextContent(text=final_message.content),
                        *(
                            ProviderImageContent(
                                attachment_id=attachment.attachment_id,
                                media_type=attachment.media_type,
                                data=attachment.data,
                            )
                            for attachment in chat.attachments
                        ),
                    ),
                )
            provider_input.extend(provider_messages)
        except Exception:
            clear_prepared_attachments(chat.attachments)
            raise
        seen_tool_call_ids: set[str] = set()

        ai_logger.info(
            "ai_stream request_id=%s user_id=%s provider=%s model=%s "
            "status=started input_messages=%d input_chars=%d attachments=%d "
            "factory_id=%s module_id=%s",
            request_id,
            user_id,
            provider_name,
            model,
            chat.message_count,
            chat.input_chars,
            len(chat.attachments),
            factory_id,
            module_id,
        )
        try:
            yield make_event(
                "response.started",
                {
                    "provider": provider_name,
                    "model": model,
                    "attachment_count": len(chat.attachments),
                    **({"input_source": "USER_PROVIDED"} if chat.attachments else {}),
                },
            )
            async with asyncio.timeout(self.settings.ai_request_timeout_seconds):
                while True:
                    if is_ai_runtime_disabled(self.settings):
                        async for terminal in emit_error(
                            public_configuration_error("disabled")
                        ):
                            yield terminal
                        return
                    provider_completed: ProviderCompleted | None = None
                    pending_tool_calls: list[ProviderToolCall] = []
                    provider_tools = (
                        self.tool_registry.provider_definitions(tool_context)
                        if (
                            not chat.attachments
                            and self.tool_registry is not None
                            and tool_context is not None
                        )
                        else ()
                    )
                    provider_request = ProviderRequest(
                        model=model,
                        input=tuple(provider_input),
                        tools=provider_tools,
                        request_id=request_id,
                        max_output_tokens=self.settings.ai_pilot_max_output_tokens,
                    )
                    if self.provider_started_recorder is not None:
                        self.provider_started_recorder()
                    provider_stream = self.provider.stream(provider_request)
                    try:
                        async for provider_event in provider_stream:
                            if is_ai_runtime_disabled(self.settings):
                                async for terminal in emit_error(
                                    public_configuration_error("disabled")
                                ):
                                    yield terminal
                                return
                            if isinstance(provider_event, ProviderTextDelta):
                                if not provider_event.delta:
                                    continue
                                delta_count += 1
                                if not chat.attachments:
                                    detection_delta = _model_output_detection_copy(
                                        provider_event.delta
                                    )
                                    guarded_output = output_guard_tail + detection_delta
                                    if _contains_sensitive_model_output(guarded_output):
                                        raise ProviderError(
                                            ProviderErrorCode.INVALID_EVENT,
                                            "Provider returned blocked image data in model output.",
                                        )
                                    output_guard_tail = guarded_output[
                                        -_MODEL_OUTPUT_GUARD_CHARS:
                                    ]
                                    output_chars += len(provider_event.delta)
                                    yield make_event(
                                        "message.delta",
                                        {
                                            "delta": provider_event.delta,
                                            "source": "MODEL_INFERENCE",
                                        },
                                    )
                                    continue
                                pending_output += provider_event.delta
                                if _contains_sensitive_model_output(pending_output):
                                    raise ProviderError(
                                        ProviderErrorCode.INVALID_EVENT,
                                        "Provider returned blocked image data in model output.",
                                    )
                                if len(pending_output) > _MAX_VISION_MODEL_OUTPUT_CHARS:
                                    raise ProviderError(
                                        ProviderErrorCode.INVALID_EVENT,
                                        "Provider returned an oversized image response.",
                                    )
                                continue

                            if isinstance(provider_event, ProviderToolCallEvent):
                                pending_tool_calls.append(provider_event.tool_call)
                                if len(pending_tool_calls) > _MAX_TOOL_CALLS_PER_ROUND:
                                    raise ProviderError(
                                        ProviderErrorCode.INVALID_EVENT,
                                        "Provider requested too many tools in one round.",
                                    )
                                continue

                            if isinstance(provider_event, ProviderCompleted):
                                provider_completed = provider_event
                                break

                            raise ProviderError(
                                ProviderErrorCode.INVALID_EVENT,
                                "Provider returned an unsupported stream event.",
                            )
                    finally:
                        await _safe_close(provider_stream, "aclose")
                        provider_stream = None

                    if provider_completed is None:
                        raise ProviderError(
                            ProviderErrorCode.INVALID_EVENT,
                            "Provider stream ended without a completion event.",
                        )

                    input_tokens += provider_completed.usage.input_tokens
                    output_tokens += provider_completed.usage.output_tokens
                    total_tokens += provider_completed.usage.total_tokens
                    if self.usage_recorder is not None:
                        self.usage_recorder(provider_completed.usage.total_tokens)

                    if pending_tool_calls:
                        if chat.attachments:
                            error = PublicAIError(
                                code=AIErrorCode.UNEXPECTED_TOOL_CALL,
                                message="图片识别请求不允许调用工具，请重新发起请求。",
                            )
                            async for terminal in emit_error(error):
                                yield terminal
                            return

                        if (
                            self.tool_registry is None
                            or self.tool_executor is None
                            or tool_context is None
                        ):
                            error = PublicAIError(
                                code=AIErrorCode.UNEXPECTED_TOOL_CALL,
                                message="当前纯文本模式不允许调用工具，请重新发起请求。",
                            )
                            async for terminal in emit_error(error):
                                yield terminal
                            return

                        if pending_output:
                            output_chars += len(pending_output)
                            yield make_event(
                                "message.delta",
                                {
                                    "delta": pending_output,
                                    "source": "MODEL_INFERENCE",
                                },
                            )
                            pending_output = ""

                        if tool_rounds >= self.settings.ai_max_tool_rounds:
                            error = PublicAIError(
                                code=AIErrorCode.TOOL_ROUND_LIMIT,
                                message="工具调用轮次已达到上限，请缩小问题范围后重试。",
                            )
                            async for terminal in emit_error(error):
                                yield terminal
                            return

                        tool_rounds += 1
                        for tool_call in pending_tool_calls:
                            if (
                                not _TOOL_CALL_ID_PATTERN.fullmatch(tool_call.call_id)
                                or tool_call.call_id in seen_tool_call_ids
                            ):
                                raise ProviderError(
                                    ProviderErrorCode.INVALID_EVENT,
                                    "Provider returned an invalid tool call identifier.",
                                )
                            seen_tool_call_ids.add(tool_call.call_id)
                            spec = self.tool_registry.resolve(tool_call.name)
                            if is_ai_runtime_disabled(self.settings):
                                async for terminal in emit_error(
                                    public_configuration_error("disabled")
                                ):
                                    yield terminal
                                return
                            yield make_event(
                                "tool.started",
                                {
                                    "tool_call_id": tool_call.call_id,
                                    "tool_name": spec.name if spec else "unregistered",
                                    "display_label": (
                                        spec.display_label
                                        if spec
                                        else "正在检查工具请求"
                                    ),
                                    "status": "running",
                                },
                            )
                            tool_started_at = perf_counter()
                            try:
                                outcome = await self.tool_executor.execute(
                                    tool_call,
                                    tool_context,
                                )
                            finally:
                                tool_latency_ms += (
                                    perf_counter() - tool_started_at
                                ) * 1000
                            tool_count += 1
                            returned_rows += max(outcome.row_count, 0)
                            truncated = truncated or outcome.truncated
                            if outcome.error_code:
                                observed_tool_error_code = outcome.error_code
                            yield make_event(
                                "tool.completed",
                                outcome.safe_event_payload,
                            )
                            provider_input.extend(
                                (
                                    tool_call,
                                    ProviderToolResult(
                                        call_id=tool_call.call_id,
                                        output=outcome.provider_output_json,
                                    ),
                                )
                            )
                        continue

                    if pending_output:
                        output_chars += len(pending_output)
                        yield make_event(
                            "message.delta",
                            {
                                "delta": pending_output,
                                "source": "MODEL_INFERENCE",
                            },
                        )
                        pending_output = ""

                    if output_chars == 0:
                        error = PublicAIError(
                            code=AIErrorCode.EMPTY_RESPONSE,
                            message="AI 未返回有效文本，请重新发起请求。",
                            retryable=True,
                        )
                        async for terminal in emit_error(error):
                            yield terminal
                        return

                    if self.completion_recorder is not None:
                        self.completion_recorder()

                    yield make_event(
                        "message.completed",
                        {
                            "delta_count": delta_count,
                            "output_chars": output_chars,
                            "tool_count": tool_count,
                            "source": "MODEL_INFERENCE",
                        },
                    )
                    log_terminal("completed")
                    yield make_event(
                        "response.completed",
                        {
                            "usage": {
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": total_tokens,
                            },
                            "tool_count": tool_count,
                            "tool_rounds": tool_rounds,
                            "source": "MODEL_INFERENCE",
                        },
                    )
                    return
        except asyncio.CancelledError:
            log_terminal("cancelled")
            raise
        except TimeoutError:
            async for terminal in emit_error(timeout_error()):
                yield terminal
        except ProviderError as exc:
            async for terminal in emit_error(public_provider_error(exc)):
                yield terminal
        except Exception:  # noqa: BLE001 - keep provider internals out of the client/log
            async for terminal in emit_error(internal_error()):
                yield terminal
        finally:
            try:
                if provider_stream is not None:
                    await _safe_close(provider_stream, "aclose")
            finally:
                try:
                    await _safe_close(self.provider, "aclose")
                finally:
                    clear_prepared_attachments(chat.attachments)
