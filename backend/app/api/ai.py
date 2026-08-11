import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.core.config import settings
from app.db import SessionLocal
from app.schemas.ai import AICapabilities, AIChatRequest, AIPilotAccessCapability
from app.services.ai.attachment_service import (
    clear_prepared_attachments,
    discard_raw_attachment_inputs,
)
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    build_server_page_context,
    supports_vision,
)
from app.services.ai.orchestrator import (
    AIOrchestrator,
    AIRequestValidationError,
    ValidatedChatInput,
    prepare_chat_attachments,
    validate_chat_request_envelope,
)
from app.services.ai.output_policy import public_configuration_error
from app.services.ai.pilot_guard import (
    AIPilotAccess,
    AIPilotGuard,
    AIPilotGuardError,
    AIPilotLease,
)
from app.services.ai.provider_factory import (
    ProviderConfigurationError,
    build_provider,
    get_provider_status,
    get_vision_provider_status,
)
from app.services.ai.providers.base import LLMProvider
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/ai")
tool_registry = build_default_tool_registry()
pilot_guard = AIPilotGuard()
pilot_logger = logging.getLogger("app.ai.pilot")


def get_ai_current_user(request: Request) -> AuthContext:
    """Authenticate AI requests without retaining a Session across the SSE stream."""

    db = SessionLocal()
    try:
        return get_current_user(request, db)
    finally:
        try:
            db.rollback()
        finally:
            db.close()


def _pilot_http_exception(
    error: AIPilotGuardError,
    *,
    request: Request,
    user: AuthContext,
) -> HTTPException:
    pilot_logger.info(
        "ai_pilot_denied request_id=%s user_id=%s error_code=%s",
        str(request.state.request_id),
        user.id,
        error.code,
    )
    headers = (
        {"Retry-After": str(error.retry_after_seconds)}
        if error.retry_after_seconds is not None
        else None
    )
    return HTTPException(
        status_code=error.status_code,
        detail=error.payload(),
        headers=headers,
    )


def _pilot_capability_access(
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
) -> AIPilotAccess:
    try:
        return pilot_guard.evaluate_access(current_user, settings)
    except AIPilotGuardError as exc:
        raise _pilot_http_exception(
            exc,
            request=request,
            user=current_user,
        ) from None


def _pilot_request(
    payload: AIChatRequest,
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
) -> Iterator[AIPilotLease]:
    input_chars = sum(
        len(part.text) for message in payload.messages for part in message.content
    )
    try:
        lease = pilot_guard.acquire(
            user=current_user,
            settings=settings,
            input_chars=input_chars,
            has_attachments=bool(payload.attachments),
        )
    except AIPilotGuardError as exc:
        discard_raw_attachment_inputs(payload.attachments)
        raise _pilot_http_exception(
            exc,
            request=request,
            user=current_user,
        ) from None
    try:
        yield lease
    finally:
        lease.close()


def _validated_chat(
    payload: AIChatRequest,
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    pilot_lease: Annotated[AIPilotLease, Depends(_pilot_request)],
) -> Iterator[ValidatedChatInput]:
    del pilot_lease
    try:
        chat = validate_chat_request_envelope(payload, settings)
    except AIRequestValidationError as exc:
        discard_raw_attachment_inputs(payload.attachments)
        raise HTTPException(
            status_code=422,
            detail=exc.public_error.payload(),
        ) from None
    except Exception:
        discard_raw_attachment_inputs(payload.attachments)
        raise
    try:
        page_context = build_server_page_context(chat.page_context, current_user)
    except AIPageContextValidationError as exc:
        discard_raw_attachment_inputs(payload.attachments)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AI_INVALID_PAGE_CONTEXT",
                "message": exc.public_message,
                "retryable": False,
            },
        ) from None
    except Exception:
        discard_raw_attachment_inputs(payload.attachments)
        raise
    try:
        pilot_guard.require_factory_access(
            user=current_user,
            requested_context=chat.page_context,
            server_context=page_context,
            settings=settings,
        )
    except AIPilotGuardError as exc:
        discard_raw_attachment_inputs(payload.attachments)
        raise _pilot_http_exception(
            exc,
            request=request,
            user=current_user,
        ) from None
    if payload.attachments and not supports_vision(page_context):
        discard_raw_attachment_inputs(payload.attachments)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AI_INVALID_PAGE_CONTEXT",
                "message": "图片识别需要当前页面的有效上下文，请刷新页面后重试。",
                "retryable": False,
            },
        )
    try:
        try:
            chat = prepare_chat_attachments(chat, payload, settings)
        except AIRequestValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.public_error.payload(),
            ) from None
    finally:
        discard_raw_attachment_inputs(payload.attachments)
    try:
        validated = replace(
            chat,
            page_context=None,
            server_page_context=page_context,
        )
    except Exception:
        clear_prepared_attachments(chat.attachments)
        raise
    try:
        yield validated
    finally:
        clear_prepared_attachments(validated.attachments)


async def _provider(
    chat: Annotated[ValidatedChatInput, Depends(_validated_chat)],
) -> AsyncIterator[LLMProvider]:
    try:
        provider = build_provider(settings, require_vision=bool(chat.attachments))
    except ProviderConfigurationError as exc:
        public_error = public_configuration_error(exc.reason)
        raise HTTPException(
            status_code=503,
            detail=public_error.payload(),
        ) from None
    try:
        yield provider
    finally:
        await provider.aclose()


@router.get("/capabilities", response_model=AICapabilities)
def capabilities(
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    pilot_access: Annotated[AIPilotAccess, Depends(_pilot_capability_access)],
) -> AICapabilities:
    provider_status = get_provider_status(settings)
    vision_status = get_vision_provider_status(settings)
    tool_context = ToolExecutionContext(
        db=None,
        user=current_user,
        request_id=str(request.state.request_id),
    )
    available = provider_status.available and pilot_access.granted
    return AICapabilities(
        enabled=provider_status.enabled,
        available=available,
        provider=provider_status.provider,
        model=provider_status.model,
        streaming=provider_status.streaming and pilot_access.granted,
        vision_enabled=vision_status.available and pilot_access.granted,
        conversation_persistence=False,
        tool_groups=(
            list(tool_registry.available_tool_groups(tool_context)) if available else []
        ),
        pilot_access=AIPilotAccessCapability(
            granted=pilot_access.granted,
            status=pilot_access.status,
            read_only=True,
        ),
    )


@router.post("/responses", response_class=EventSourceResponse)
async def responses(
    request: Request,
    chat: Annotated[ValidatedChatInput, Depends(_validated_chat)],
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    provider: Annotated[LLMProvider, Depends(_provider)],
    pilot_lease: Annotated[AIPilotLease, Depends(_pilot_request)],
) -> AsyncIterator[ServerSentEvent]:
    request_id = str(request.state.request_id)
    tool_context = ToolExecutionContext(
        db=None,
        user=current_user,
        request_id=request_id,
        page_context=chat.server_page_context,
        session_factory=SessionLocal,
    )
    orchestrator = AIOrchestrator(
        provider=provider,
        settings=settings,
        tool_registry=tool_registry,
        tool_executor=ToolExecutor(tool_registry, settings),
        provider_started_recorder=pilot_lease.mark_provider_started,
        usage_recorder=pilot_lease.record_usage,
        completion_recorder=pilot_lease.mark_completed,
    )
    async for event in orchestrator.stream(
        chat,
        request_id=request_id,
        user_id=current_user.id,
        tool_context=tool_context,
    ):
        yield ServerSentEvent(event=event.type, data=event)
