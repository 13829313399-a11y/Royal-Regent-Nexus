import json
import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.ai_artifacts import (
    ArtifactScannerDependency,
    ArtifactStorageDependency,
    _artifact_error,
    _require_artifacts,
)
from app.core.config import settings
from app.db import SessionLocal, get_db
from app.schemas.ai import (
    AICapabilities,
    AICapabilityContextRequest,
    AIChatRequest,
    AINIFCapabilities,
    AIPilotAccessCapability,
)
from app.schemas.ai.artifact import AIArtifactEgressConsent
from app.schemas.ai.context import AIPageContextInput, AIServerPageContext
from app.schemas.ai.conversation import (
    AIContextOption,
    AIContextOptionsResponse,
    AIConversationMessageCreate,
)
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.workbook import (
    AIWorkbookMappingProposal,
    AIWorkbookSemanticSnapshot,
)
from app.services.ai.artifacts.egress import require_artifact_egress_consent
from app.services.ai.artifacts.service import ArtifactError, create_artifact
from app.services.ai.artifacts.vision_adapter import prepare_vision_artifacts
from app.services.ai.artifacts.workbook_adapter import (
    inspect_workbook_artifact,
    require_matching_snapshot,
)
from app.services.ai.attachment_service import (
    clear_prepared_attachments,
    discard_raw_attachment_inputs,
)
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    available_contexts,
    build_server_page_context,
    supports_vision,
)
from app.services.ai.conversation_service import (
    MAX_SUMMARY_CHARS,
    AssistantMessageMetadata,
    ConversationError,
    ConversationNotFoundError,
    ConversationValidationError,
    append_assistant_message,
    append_user_message,
    assemble_conversation_history,
    bound_page_context,
    get_owned_conversation,
)
from app.services.ai.observability.metrics import safe_record_metric_event
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
    AIPilotGuardError,
    AIPilotLease,
    build_pilot_guard,
)
from app.services.ai.prompts.compiler import PromptCompiler
from app.services.ai.provider_factory import (
    ProviderConfigurationError,
    build_provider,
    get_provider_status,
    get_vision_provider_status,
)
from app.services.ai.providers.base import LLMProvider
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.ai.workbook_inspection import (
    MAX_WORKBOOK_BYTES,
    WorkbookInspectionError,
    inspect_workbook,
)
from app.services.ai.workbook_mapping import (
    WorkbookMappingError,
    propose_workbook_mapping,
)
from app.services.auth import (
    AuthContext,
    get_current_user,
)
from app.services.business_authz import (
    ensure_permission_for_departments,
    is_wildcard_super_admin,
)
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS

router = APIRouter(prefix="/api/ai")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
tool_registry = build_default_tool_registry(
    controlled_apply_enabled=settings.ai_controlled_apply_enabled,
    semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
    knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
)
pilot_guard = build_pilot_guard()
pilot_logger = logging.getLogger("app.ai.pilot")
workbook_logger = logging.getLogger("app.ai.workbook")
conversation_logger = logging.getLogger("app.ai.conversation")


def _workbook_error(
    error: WorkbookInspectionError | WorkbookMappingError,
) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.public_message,
            "retryable": False,
        },
    )


def _ensure_workbook_permission(
    db: Session,
    current_user: AuthContext,
    factory_id: str,
) -> str:
    normalized = factory_id.strip()
    if is_wildcard_super_admin(current_user):
        return normalized
    ensure_permission_for_departments(
        db,
        current_user,
        "injection_scheduling:import",
        normalized,
        SCHEDULING_DEPARTMENTS,
    )
    return normalized


def _legacy_workbook_artifact(
    db: Session,
    *,
    content: bytes,
    filename: str,
    factory_id: str,
    user: AuthContext,
    storage,
    scanner,
):
    if not (
        settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
        and filename.lower().endswith(".xlsx")
    ):
        return None
    allowed_factories = _require_artifacts(user)
    return create_artifact(
        db,
        user=user,
        factory_id=factory_id,
        classification="CONFIDENTIAL_BUSINESS",
        filename=filename,
        # The legacy multipart endpoint historically accepted an omitted or
        # generic Content-Type for a valid .xlsx upload.  Internal Artifact
        # registration must preserve that compatibility while validation still
        # verifies the package signature and extension.
        declared_mime_type=XLSX_MEDIA_TYPE,
        data=content,
        storage=storage,
        scanner=scanner,
        settings=settings,
        allowed_factory_ids=allowed_factories,
    )


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


def _build_page_context(
    requested_context: AIPageContextInput | None,
    user: AuthContext,
) -> AIServerPageContext | None:
    if (
        settings.ai_semantic_gateway_enabled
        and getattr(requested_context, "selected_entity", None) is not None
    ):
        db = SessionLocal()
        try:
            return build_server_page_context(
                requested_context,
                user,
                db=db,
                semantic_gateway_enabled=True,
                knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
            )
        finally:
            try:
                db.rollback()
            finally:
                db.close()
    return build_server_page_context(
        requested_context,
        user,
        semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
        knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
    )


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
    input_chars = (
        settings.ai_max_input_chars
        if payload.conversation_id is not None
        else sum(
            len(part.text) for message in payload.messages for part in message.content
        )
    )
    try:
        lease = pilot_guard.acquire(
            user=current_user,
            settings=settings,
            input_chars=input_chars,
            has_attachments=bool(payload.attachments or payload.artifact_attachments),
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


def _bind_conversation_chat(
    *,
    payload: AIChatRequest,
    request: Request,
    current_user: AuthContext,
    chat: ValidatedChatInput,
) -> ValidatedChatInput:
    if payload.conversation_id is None:
        return chat
    if not settings.ai_conversations_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    if len(payload.messages) != 1 or payload.messages[0].role != "user":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AI_CONVERSATION_INVALID",
                "message": "绑定服务端会话时只能提交一条新的用户消息。",
                "retryable": False,
            },
        )
    conversation_db = SessionLocal()
    try:
        record = get_owned_conversation(
            conversation_db,
            conversation_id=payload.conversation_id,
            user=current_user,
        )
        allowed_factories = pilot_guard.configured_factory_ids(settings)
        requested_factory = (
            payload.page_context.factory_id
            if payload.page_context is not None
            else None
        )
        if (
            record.factory_scope not in allowed_factories
            or requested_factory is not None
            and requested_factory != record.factory_scope
        ):
            raise ConversationNotFoundError("会话不存在。")
        if settings.ai_conversation_context_enabled:
            stored_context = bound_page_context(
                conversation_db,
                conversation_id=record.id,
            )
            if payload.page_context != stored_context:
                raise ConversationValidationError(
                    "会话业务上下文已变化，请刷新后重新选择。"
                )
        current_message = chat.messages[-1]
        current_text = (
            current_message.content if isinstance(current_message.content, str) else ""
        )
        history = assemble_conversation_history(
            conversation_db,
            conversation_id=record.id,
            user=current_user,
            settings=settings,
            reserve_messages=2,
            reserve_chars=len(current_text) + MAX_SUMMARY_CHARS + 512,
        )
        stored_user = append_user_message(
            conversation_db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text=current_text,
                idempotency_key=f"response:{request.state.request_id}:user",
            ),
            user=current_user,
            settings=settings,
        )
        conversation_messages = list(history.messages)
        if history.summary:
            conversation_messages.insert(
                0,
                PromptCompiler.data_block(
                    label="CONVERSATION_SAFE_SUMMARY",
                    content=history.summary,
                    max_chars=MAX_SUMMARY_CHARS,
                ),
            )
        conversation_messages.extend(chat.messages)
        conversation_input_chars = sum(
            len(item.content)
            for item in conversation_messages
            if isinstance(item.content, str)
        )
        return replace(
            chat,
            messages=tuple(conversation_messages),
            message_count=len(conversation_messages),
            input_chars=conversation_input_chars,
            conversation_id=record.id,
            conversation_user_message_id=stored_user.id,
            conversation_history_truncated=history.truncated,
        )
    except ConversationError as exc:
        conversation_db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.public_message,
                "retryable": False,
            },
        ) from exc
    finally:
        conversation_db.close()


def _validated_chat(
    payload: AIChatRequest,
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    pilot_lease: Annotated[AIPilotLease, Depends(_pilot_request)],
    artifact_storage: ArtifactStorageDependency,
) -> Iterator[ValidatedChatInput]:
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
        page_context = _build_page_context(chat.page_context, current_user)
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
        verified_factory_id = (
            page_context.verified_factory_id
            if page_context is not None and page_context.verified_factory_id is not None
            else ""
        )
        pilot_lease.bind_factory(verified_factory_id)
    except AIPilotGuardError as exc:
        discard_raw_attachment_inputs(payload.attachments)
        raise _pilot_http_exception(
            exc,
            request=request,
            user=current_user,
        ) from None
    if (payload.attachments or payload.artifact_attachments) and not supports_vision(
        page_context
    ):
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
            if payload.artifact_attachments:
                if not (
                    settings.ai_artifacts_enabled
                    and settings.ai_artifact_workflows_enabled
                ):
                    raise HTTPException(status_code=404, detail="Not Found")
                allowed_factories = _require_artifacts(current_user)
                # Resolve and verify Artifact bytes before the SSE generator is
                # yielded, then close the short-lived Session.  A request-scoped
                # get_db dependency would otherwise stay open for the full stream.
                artifact_db = SessionLocal()
                try:
                    prepared = prepare_vision_artifacts(
                        artifact_db,
                        references=payload.artifact_attachments,
                        consent=payload.artifact_egress_consent,
                        user=current_user,
                        factory_id=verified_factory_id,
                        allowed_factory_ids=allowed_factories,
                        storage=artifact_storage,
                        settings=settings,
                    )
                finally:
                    artifact_db.close()
                chat = replace(
                    chat,
                    attachments=prepared,
                    artifact_ids=tuple(
                        item.artifact_id for item in payload.artifact_attachments
                    ),
                )
            else:
                chat = prepare_chat_attachments(chat, payload, settings)
        except AIRequestValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.public_error.payload(),
            ) from None
        except ArtifactError as exc:
            raise _artifact_error(exc) from exc
    finally:
        discard_raw_attachment_inputs(payload.attachments)
    try:
        chat = _bind_conversation_chat(
            payload=payload,
            request=request,
            current_user=current_user,
            chat=chat,
        )
    except Exception:
        clear_prepared_attachments(chat.attachments)
        raise
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


@router.get(
    "/capabilities",
    response_model=AICapabilities,
    response_model_exclude_none=True,
)
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
        conversation_persistence=(available and settings.ai_conversations_enabled),
        adaptive_surface_enabled=(
            True if available and settings.ai_adaptive_surface_enabled else None
        ),
        rich_message_renderer_enabled=(
            True if available and settings.ai_rich_message_renderer_enabled else None
        ),
        workbench_v2_enabled=(
            True if available and settings.ai_workbench_v2_enabled else None
        ),
        conversation_context_enabled=(
            True if available and settings.ai_conversation_context_enabled else None
        ),
        presentation_blocks_enabled=(
            True if available and settings.ai_presentation_blocks_enabled else None
        ),
        artifact_workflows_enabled=(
            True
            if available
            and settings.ai_artifacts_enabled
            and settings.ai_artifact_workflows_enabled
            else None
        ),
        vision_tool_comparison_enabled=(
            True
            if available
            and vision_status.available
            and settings.ai_nif_runtime_enabled
            and settings.ai_provider_capability_router_enabled
            and settings.ai_skill_router_enabled
            and settings.ai_evidence_v1_enabled
            and settings.ai_conversations_enabled
            and settings.ai_tasks_enabled
            and settings.ai_task_worker_enabled
            and settings.ai_semantic_gateway_enabled
            and settings.ai_artifacts_enabled
            and settings.ai_artifact_workflows_enabled
            and settings.ai_vision_tool_comparison_enabled
            else None
        ),
        feedback_enabled=(True if available and settings.ai_feedback_enabled else None),
        tool_groups=(
            list(tool_registry.available_tool_groups(tool_context)) if available else []
        ),
        pilot_access=AIPilotAccessCapability(
            granted=pilot_access.granted,
            status=pilot_access.status,
            read_only=False,
            max_tool_risk_level="PREVIEW_WITH_AUDIT",
        ),
    )


@router.get("/context-options", response_model=AIContextOptionsResponse)
def context_options(
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    pilot_access: Annotated[AIPilotAccess, Depends(_pilot_capability_access)],
    factory_id: Annotated[str, Query(min_length=1, max_length=64)],
) -> AIContextOptionsResponse:
    if (
        not settings.ai_conversations_enabled
        or not settings.ai_conversation_context_enabled
    ):
        raise HTTPException(status_code=404, detail="Not Found")
    allowed_factories = pilot_guard.configured_factory_ids(settings)
    if not pilot_access.granted or factory_id not in allowed_factories:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前厂区未开放 AI 上下文权限。",
                "retryable": False,
            },
        )
    return AIContextOptionsResponse(
        items=[
            AIContextOption(
                factory_scope=item.page_context.factory_id or "",
                module_id=item.page_context.module_id,
                route_name=item.page_context.route_name,
                path=item.page_context.path,
                display_label=item.display_label,
                tool_groups=list(item.tool_groups),
            )
            for item in available_contexts(
                current_user,
                factory_scope=factory_id,
                knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
            )
        ]
    )


@router.post("/capabilities/context", response_model=AINIFCapabilities)
def contextual_capabilities(
    payload: AICapabilityContextRequest,
    request: Request,
    current_user: Annotated[AuthContext, Depends(get_ai_current_user)],
    pilot_access: Annotated[AIPilotAccess, Depends(_pilot_capability_access)],
) -> AINIFCapabilities:
    if not settings.ai_nif_runtime_enabled:
        raise HTTPException(status_code=404, detail="Not Found")

    server_page_context = None
    context_status = "MISSING"
    if payload.page_context is not None:
        try:
            server_page_context = _build_page_context(
                payload.page_context,
                current_user,
            )
        except AIPageContextValidationError:
            context_status = "INVALID"
        else:
            context_status = (
                "DENIED"
                if payload.page_context.factory_id is not None
                and server_page_context is not None
                and server_page_context.verified_factory_id is None
                else "ALLOWED"
            )

    provider_status = get_provider_status(settings)
    vision_status = get_vision_provider_status(settings)
    runtime_available = provider_status.available and pilot_access.granted
    tool_context = ToolExecutionContext(
        db=None,
        user=current_user,
        request_id=str(request.state.request_id),
        page_context=(
            server_page_context if context_status in {"MISSING", "ALLOWED"} else None
        ),
    )
    definitions = (
        tool_registry.provider_definitions(tool_context)
        if runtime_available and context_status in {"MISSING", "ALLOWED"}
        else ()
    )
    available_tools = [definition.name for definition in definitions]
    available_skills: list[str] = []
    skill_registry_invalid = False
    if (
        settings.ai_skill_router_enabled
        and runtime_available
        and context_status in {"MISSING", "ALLOWED"}
    ):
        try:
            skill_registry = SkillRegistry(tool_registry)
            skills = skill_registry.available(tool_context)
            available_skills = [skill.version_ref for skill in skills]
            skill_tool_names = {
                name for skill in skills for name in skill.manifest.allowed_tools
            }
            available_tools = [
                name for name in available_tools if name in skill_tool_names
            ]
        except SkillRegistryError:
            available_tools = []
            available_skills = []
            skill_registry_invalid = True
    available_tool_groups = sorted(
        {
            spec.tool_group
            for name in available_tools
            if (spec := tool_registry.resolve(name)) is not None
        }
    )
    has_preview_tool = any(
        spec is not None and spec.risk_level.value == "PREVIEW_WITH_AUDIT"
        for spec in (tool_registry.resolve(name) for name in available_tools)
    )
    max_autonomy_level = "L2" if has_preview_tool else "L1" if available_tools else "L0"
    vision_enabled = (
        runtime_available
        and vision_status.available
        and context_status == "ALLOWED"
        and supports_vision(server_page_context)
    )
    if not provider_status.enabled:
        reason_code = "AI_DISABLED"
    elif not pilot_access.granted:
        reason_code = f"AI_{pilot_access.status}"
    elif not provider_status.available:
        reason_code = "AI_PROVIDER_UNAVAILABLE"
    elif skill_registry_invalid:
        reason_code = "AI_SKILL_REGISTRY_INVALID"
    elif context_status == "INVALID":
        reason_code = "AI_INVALID_PAGE_CONTEXT"
    elif context_status == "DENIED":
        reason_code = "AI_CONTEXT_ACCESS_DENIED"
    else:
        reason_code = "AI_READY"

    return AINIFCapabilities(
        configured_enabled=provider_status.enabled,
        runtime_available=runtime_available,
        user_allowed=True,
        context_status=context_status,
        reason_code=reason_code,
        provider=provider_status.provider,
        model=provider_status.model,
        provider_profile=provider_status.capability_profile,
        catalog_version=provider_status.catalog_version,
        model_capabilities=list(provider_status.capabilities),
        reasoning_policies=list(provider_status.reasoning_policies),
        streaming=provider_status.streaming and runtime_available,
        vision_enabled=vision_enabled,
        feature_flags={
            "nif_runtime_enabled": settings.ai_nif_runtime_enabled,
            "provider_capability_router_configured": (
                settings.ai_provider_capability_router_enabled
            ),
            "skill_router_configured": settings.ai_skill_router_enabled,
            "evidence_v1_configured": settings.ai_evidence_v1_enabled,
            "cloud_vision_configured": settings.ai_cloud_vision_enabled,
            "cloud_document_translation_configured": (
                settings.ai_cloud_document_translation_enabled
            ),
            "cloud_workbook_mapping_configured": (
                settings.ai_cloud_workbook_mapping_enabled
            ),
            "controlled_apply_configured": settings.ai_controlled_apply_enabled,
            "feedback_configured": settings.ai_feedback_enabled,
            "observability_configured": settings.ai_observability_enabled,
            "metric_export_configured": settings.ai_metric_export_enabled,
            "operational_alerts_configured": (settings.ai_operational_alerts_enabled),
            "semantic_gateway_configured": settings.ai_semantic_gateway_enabled,
            "knowledge_hub_configured": settings.ai_knowledge_hub_enabled,
            "artifacts_configured": settings.ai_artifacts_enabled,
            "artifact_workflows_configured": settings.ai_artifact_workflows_enabled,
            "vision_tool_comparison_configured": (
                settings.ai_vision_tool_comparison_enabled
            ),
            "tasks_configured": settings.ai_tasks_enabled,
            "task_worker_configured": settings.ai_task_worker_enabled,
        },
        available_tool_groups=available_tool_groups,
        available_tools=available_tools,
        available_skills=available_skills,
        max_autonomy_level=max_autonomy_level,
    )


@router.post(
    "/workbooks/inspect",
    response_model=AIWorkbookSemanticSnapshot,
    response_model_exclude_none=True,
)
def inspect_workbook_endpoint(
    request: Request,
    factory_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AIWorkbookSemanticSnapshot:
    verified_factory_id = _ensure_workbook_permission(db, current_user, factory_id)
    content = file.file.read(MAX_WORKBOOK_BYTES + 1)
    try:
        artifact = _legacy_workbook_artifact(
            db,
            content=content,
            filename=file.filename or "upload.xlsx",
            factory_id=verified_factory_id,
            user=current_user,
            storage=storage,
            scanner=scanner,
        )
        if artifact is None:
            snapshot = inspect_workbook(
                source_file_name=file.filename or "upload.xlsx",
                content=content,
                factory_id=verified_factory_id,
            )
        else:
            snapshot, artifact = inspect_workbook_artifact(
                db,
                artifact_id=artifact.id,
                user=current_user,
                factory_id=verified_factory_id,
                allowed_factory_ids=_require_artifacts(current_user),
                storage=storage,
            )
            snapshot = snapshot.model_copy(
                update={
                    "source_lineage": snapshot.source_lineage.model_copy(
                        update={"artifact_id": None}
                    )
                }
            )
    except ArtifactError as exc:
        raise _artifact_error(exc) from exc
    except WorkbookInspectionError as exc:
        workbook_logger.info(
            "workbook.inspect request_id=%s user_id=%s factory_id=%s status=blocked code=%s",
            str(request.state.request_id),
            current_user.id,
            verified_factory_id,
            exc.code,
        )
        raise _workbook_error(exc) from None
    workbook_logger.info(
        "workbook.inspect request_id=%s user_id=%s factory_id=%s status=completed sha256=%s sheets=%s",
        str(request.state.request_id),
        current_user.id,
        verified_factory_id,
        snapshot.source_lineage.source_sha256,
        snapshot.sheet_count,
    )
    return snapshot


@router.post(
    "/workbooks/inspect/artifact",
    response_model=AIWorkbookSemanticSnapshot,
    response_model_exclude_none=True,
)
def inspect_workbook_artifact_endpoint(
    request: Request,
    factory_id: Annotated[str, Form()],
    artifact_id: Annotated[str, Form()],
    storage: ArtifactStorageDependency,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AIWorkbookSemanticSnapshot:
    if not settings.ai_artifact_workflows_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    verified_factory_id = _ensure_workbook_permission(db, current_user, factory_id)
    allowed_factories = _require_artifacts(current_user)
    try:
        snapshot, record = inspect_workbook_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            factory_id=verified_factory_id,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
    except ArtifactError as exc:
        raise _artifact_error(exc) from exc
    except WorkbookInspectionError as exc:
        raise _workbook_error(exc) from exc
    workbook_logger.info(
        "workbook.inspect_artifact request_id=%s user_id=%s factory_id=%s "
        "artifact_id=%s status=completed sha256=%s sheets=%s parser=%s",
        str(request.state.request_id),
        current_user.id,
        verified_factory_id,
        record.id,
        record.sha256,
        snapshot.sheet_count,
        record.parser_version,
    )
    return snapshot


@router.post(
    "/workbooks/mapping-proposal",
    response_model=AIWorkbookMappingProposal,
)
async def workbook_mapping_proposal_endpoint(
    request: Request,
    factory_id: Annotated[str, Form()],
    document_kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
) -> AIWorkbookMappingProposal:
    verified_factory_id = _ensure_workbook_permission(db, current_user, factory_id)
    if not is_wildcard_super_admin(current_user):
        ensure_permission_for_departments(
            db,
            current_user,
            "injection_scheduling:propose_import_profiles",
            verified_factory_id,
            SCHEDULING_DEPARTMENTS,
        )
    allowed_kinds = {
        "DEMAND_ORDER",
        "PLANNED_SCHEDULE",
        "SYSTEM_ROUND_TRIP",
        "MASTER_DATA",
    }
    if document_kind not in allowed_kinds:
        raise HTTPException(status_code=422, detail="document_kind 无效")
    content = file.file.read()
    try:
        snapshot = inspect_workbook(
            source_file_name=file.filename or "upload.xlsx",
            content=content,
            factory_id=verified_factory_id,
            relaxed_limits=True,
        )
        provider = build_provider(settings)
        try:
            proposal = await propose_workbook_mapping(
                snapshot=snapshot,
                document_kind=document_kind,
                provider=provider,
                settings=settings,
                request_id=str(request.state.request_id),
                user=current_user,
            )
        finally:
            await provider.aclose()
    except (WorkbookInspectionError, WorkbookMappingError) as exc:
        workbook_logger.info(
            "workbook.mapping_proposal request_id=%s user_id=%s factory_id=%s status=failed code=%s",
            str(request.state.request_id),
            current_user.id,
            verified_factory_id,
            exc.code,
        )
        raise _workbook_error(exc) from None
    except ProviderConfigurationError as exc:
        public_error = public_configuration_error(exc.reason)
        raise HTTPException(status_code=503, detail=public_error.payload()) from None
    workbook_logger.info(
        "workbook.mapping_proposal request_id=%s user_id=%s factory_id=%s status=completed sha256=%s mapping_count=%s",
        str(request.state.request_id),
        current_user.id,
        verified_factory_id,
        proposal.source_sha256,
        len(proposal.proposal),
    )
    return proposal


@router.post(
    "/workbooks/mapping-proposal/artifact",
    response_model=AIWorkbookMappingProposal,
)
async def workbook_mapping_proposal_artifact_endpoint(
    request: Request,
    factory_id: Annotated[str, Form()],
    document_kind: Annotated[str, Form()],
    artifact_id: Annotated[str, Form()],
    cloud_consent_json: Annotated[str, Form()],
    storage: ArtifactStorageDependency,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    snapshot_json: Annotated[str, Form()] = "",
) -> AIWorkbookMappingProposal:
    if not settings.ai_artifact_workflows_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    verified_factory_id = _ensure_workbook_permission(db, current_user, factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "injection_scheduling:propose_import_profiles",
        verified_factory_id,
        SCHEDULING_DEPARTMENTS,
    )
    if document_kind not in {
        "DEMAND_ORDER",
        "PLANNED_SCHEDULE",
        "SYSTEM_ROUND_TRIP",
        "MASTER_DATA",
    }:
        raise HTTPException(status_code=422, detail="document_kind 无效")
    try:
        consent = AIArtifactEgressConsent.model_validate_json(cloud_consent_json)
        supplied_snapshot = (
            AIWorkbookSemanticSnapshot.model_validate_json(snapshot_json)
            if snapshot_json.strip()
            else None
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AI_ARTIFACT_WORKFLOW_CONTRACT_INVALID",
                "message": "Artifact 工作流参数格式无效。",
                "retryable": False,
            },
        ) from exc
    allowed_factories = _require_artifacts(current_user)
    try:
        snapshot, record = inspect_workbook_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            factory_id=verified_factory_id,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        snapshot = require_matching_snapshot(snapshot, supplied_snapshot)
        require_artifact_egress_consent(
            consent,
            [record],
            content_class="WORKBOOK",
        )
        provider = build_provider(settings)
        try:
            proposal = await propose_workbook_mapping(
                snapshot=snapshot,
                document_kind=document_kind,
                provider=provider,
                settings=settings,
                request_id=str(request.state.request_id),
                user=current_user,
            )
        finally:
            await provider.aclose()
        record.model_version = proposal.generated_by_model
        db.commit()
    except ArtifactError as exc:
        raise _artifact_error(exc) from exc
    except (WorkbookInspectionError, WorkbookMappingError) as exc:
        raise _workbook_error(exc) from exc
    except ProviderConfigurationError as exc:
        public_error = public_configuration_error(exc.reason)
        raise HTTPException(status_code=503, detail=public_error.payload()) from None
    workbook_logger.info(
        "workbook.mapping_artifact request_id=%s user_id=%s factory_id=%s "
        "artifact_id=%s status=completed snapshot_sha256=%s model=%s",
        str(request.state.request_id),
        current_user.id,
        verified_factory_id,
        record.id,
        proposal.snapshot_sha256,
        proposal.generated_by_model,
    )
    return proposal


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
        metric_recorder=lambda event: safe_record_metric_event(
            SessionLocal,
            event,
            settings=settings,
        ),
    )
    output_parts: list[str] = []
    stream_metadata: dict[str, object] = {}
    stream_evidence: dict[str, AIEvidenceReferenceV1] = {}
    stream_required_access: dict[str, tuple[str, ...]] = {}
    async for event in orchestrator.stream(
        chat,
        request_id=request_id,
        user_id=current_user.id,
        tool_context=tool_context,
    ):
        if chat.conversation_id is not None:
            if event.type == "message.delta":
                delta = event.payload.get("delta")
                if isinstance(delta, str):
                    output_parts.append(delta)
            elif event.type == "response.started":
                stream_metadata.update(event.payload)
            elif event.type == "tool.completed":
                tool_name = event.payload.get("tool_name")
                spec = (
                    tool_registry.resolve(tool_name)
                    if isinstance(tool_name, str)
                    else None
                )
                if spec is not None and spec.required_permission is not None:
                    stream_required_access[spec.required_permission] = tuple(
                        sorted(spec.allowed_departments)
                    )
                result = event.payload.get("result")
                evidence_items = (
                    result.get("evidence") if isinstance(result, dict) else None
                )
                if isinstance(evidence_items, list):
                    for item in evidence_items[:12]:
                        try:
                            evidence = AIEvidenceReferenceV1.model_validate(item)
                        except ValueError:
                            continue
                        stream_evidence[evidence.evidence_id] = evidence
            elif event.type == "response.completed":
                stream_metadata.update(event.payload)
                persisted = False
                assistant_message_id = ""
                persistence_error_code = ""
                conversation_db = SessionLocal()
                try:
                    usage = event.payload.get("usage")
                    stored = append_assistant_message(
                        conversation_db,
                        conversation_id=chat.conversation_id,
                        user=current_user,
                        text="".join(output_parts),
                        idempotency_key=f"response:{request_id}:assistant",
                        settings=settings,
                        metadata=AssistantMessageMetadata(
                            skill_id=str(stream_metadata.get("skill_id", "")),
                            skill_version=str(stream_metadata.get("skill_version", "")),
                            skill_hash=str(stream_metadata.get("skill_hash", "")),
                            prompt_version=str(
                                stream_metadata.get("prompt_version", "")
                            ),
                            prompt_hash=str(stream_metadata.get("prompt_hash", "")),
                            provider_profile=str(
                                stream_metadata.get("capability_profile", "")
                            ),
                            provider_model_alias=str(stream_metadata.get("model", "")),
                            usage=(usage if isinstance(usage, dict) else None),
                            evidence=tuple(stream_evidence.values()),
                            required_access=tuple(
                                sorted(stream_required_access.items())
                            ),
                        ),
                    )
                    persisted = stored.persisted
                    assistant_message_id = stored.id
                except ConversationError as exc:
                    conversation_db.rollback()
                    persistence_error_code = exc.code
                    conversation_logger.warning(
                        "ai_conversation_assistant_not_persisted request_id=%s "
                        "user_id=%s conversation_id=%s error_code=%s",
                        request_id,
                        current_user.id,
                        chat.conversation_id,
                        exc.code,
                    )
                finally:
                    conversation_db.close()
                event = event.model_copy(
                    update={
                        "payload": {
                            **event.payload,
                            "conversation": {
                                "id": chat.conversation_id,
                                "user_message_id": chat.conversation_user_message_id,
                                "assistant_message_id": assistant_message_id,
                                "assistant_persisted": persisted,
                                "history_truncated": chat.conversation_history_truncated,
                                **(
                                    {"persistence_error_code": persistence_error_code}
                                    if persistence_error_code
                                    else {}
                                ),
                            },
                        }
                    }
                )
        yield ServerSentEvent(event=event.type, data=event)
