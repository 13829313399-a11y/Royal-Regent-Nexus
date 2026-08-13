import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db import get_db
from app.models.auth import AuthUser
from app.schemas.ai.task import (
    AITaskCancelRequest,
    AITaskCapabilities,
    AITaskCreate,
    AITaskData,
    AITaskEventPage,
    AITaskListPage,
    AITaskResumeRequest,
)
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    build_server_page_context,
)
from app.services.ai.pilot_guard import AIPilotGuardError, build_pilot_guard
from app.services.ai.runtime_gate import is_ai_runtime_disabled
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_events import AITaskEventError, read_task_events
from app.services.ai.task_service import (
    AITaskError,
    AITaskNotFoundError,
    create_task,
    get_owned_task,
    list_owned_tasks,
    request_task_cancellation,
    request_task_resume,
    task_data,
)
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import (
    AuthContext,
    add_auth_audit,
    build_auth_context,
    get_current_user,
)

router = APIRouter(prefix="/api/ai/tasks", tags=["ai-tasks"])
task_pilot_guard = build_pilot_guard()
task_tool_registry = build_default_tool_registry(
    controlled_apply_enabled=False,
    semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
    knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
    artifact_workflows_enabled=settings.ai_artifact_workflows_enabled,
    vision_tool_comparison_enabled=settings.ai_vision_tool_comparison_enabled,
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _task_error(error: AITaskError | AITaskEventError) -> HTTPException:
    if isinstance(error, AITaskError):
        return HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.public_message,
                "retryable": False,
            },
        )
    return HTTPException(
        status_code=422,
        detail={
            "code": "AI_TASK_EVENT_INVALID",
            "message": "AI 任务事件游标或元数据无效。",
            "retryable": False,
        },
    )


def _require_tasks(user: AuthContext) -> frozenset[str]:
    if not (
        settings.ai_tasks_enabled
        and settings.ai_nif_runtime_enabled
        and settings.ai_skill_router_enabled
        and settings.ai_evidence_v1_enabled
    ):
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        access = task_pilot_guard.evaluate_access(user, settings)
        allowed_factories = task_pilot_guard.configured_factory_ids(settings)
    except AIPilotGuardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
    if not access.granted:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前账号未开放 AI 任务权限。",
                "retryable": False,
            },
        )
    return allowed_factories


def _audit_access_denied(
    db: Session,
    *,
    user: AuthContext,
    operation: str,
    request: Request,
) -> None:
    add_auth_audit(
        db,
        "ai_task_access_denied",
        username=user.username,
        user_id=user.id,
        detail=f"operation={operation}",
        request=request,
    )
    db.commit()


def _owned_task_or_404(
    db: Session,
    *,
    task_id: str,
    user: AuthContext,
    allowed_factories: frozenset[str],
    request: Request,
    operation: str,
):
    try:
        return get_owned_task(
            db,
            task_id=task_id,
            user=user,
            allowed_factory_scopes=allowed_factories,
        )
    except AITaskNotFoundError:
        _audit_access_denied(
            db,
            user=user,
            operation=operation,
            request=request,
        )
        raise _task_error(AITaskNotFoundError("Task not found")) from None


@router.post("", response_model=AITaskData, status_code=status.HTTP_201_CREATED)
def post_task(
    payload: AITaskCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_tasks(current_user)
    try:
        try:
            server_context = build_server_page_context(
                payload.page_context,
                current_user,
                db=db,
                semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
                knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
            )
            task_pilot_guard.require_factory_access(
                user=current_user,
                requested_context=payload.page_context,
                server_context=server_context,
                settings=settings,
            )
        except AIPageContextValidationError as exc:
            raise AITaskError("Task page context is invalid") from exc
        except AIPilotGuardError as exc:
            raise AITaskNotFoundError("Task page context is unavailable") from exc
        try:
            skill_registry = SkillRegistry(task_tool_registry)
        except SkillRegistryError as exc:
            raise AITaskError("Task Skill registry is unavailable") from exc
        record = create_task(
            db,
            payload=payload,
            user=current_user,
            settings=settings,
            registry=task_tool_registry,
            skill_registry=skill_registry,
            server_page_context=server_context,
            allowed_factory_scopes=allowed_factories,
            request_id=str(request.state.request_id),
        )
        return task_data(db, record)
    except AITaskError as exc:
        if isinstance(exc, AITaskNotFoundError):
            _audit_access_denied(
                db,
                user=current_user,
                operation="create",
                request=request,
            )
        raise _task_error(exc) from exc


@router.get("/capabilities", response_model=AITaskCapabilities)
def get_task_capabilities(current_user: CurrentUser) -> AITaskCapabilities:
    _require_tasks(current_user)
    worker_enabled = settings.ai_task_worker_enabled
    return AITaskCapabilities(
        available=worker_enabled and not is_ai_runtime_disabled(settings),
        worker_enabled=worker_enabled,
    )


@router.get("", response_model=AITaskListPage)
def get_tasks(
    current_user: CurrentUser,
    db: DbSession,
    conversation_id: Annotated[str | None, Query(max_length=64)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    allowed_factories = _require_tasks(current_user)
    try:
        return list_owned_tasks(
            db,
            user=current_user,
            allowed_factory_scopes=allowed_factories,
            conversation_id=conversation_id,
            cursor=cursor,
            limit=limit,
        )
    except AITaskError as exc:
        raise _task_error(exc) from exc


@router.get("/{task_id}", response_model=AITaskData)
def get_task(
    task_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_tasks(current_user)
    record = _owned_task_or_404(
        db,
        task_id=task_id,
        user=current_user,
        allowed_factories=allowed_factories,
        request=request,
        operation="detail",
    )
    try:
        return task_data(db, record)
    except AITaskError as exc:
        raise _task_error(exc) from exc


@router.post("/{task_id}/cancel", response_model=AITaskData)
def cancel_task(
    task_id: str,
    payload: AITaskCancelRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_tasks(current_user)
    record = _owned_task_or_404(
        db,
        task_id=task_id,
        user=current_user,
        allowed_factories=allowed_factories,
        request=request,
        operation="cancel",
    )
    previous_revision = record.revision
    try:
        request_task_cancellation(
            db,
            task=record,
            user=current_user,
            expected_revision=payload.expected_revision,
            reason_code=payload.reason_code,
            settings=settings,
        )
        if record.revision != previous_revision:
            add_auth_audit(
                db,
                "ai_task_cancel_requested",
                username=current_user.username,
                user_id=current_user.id,
                detail=f"task_id={record.id};state={record.state}",
                request=request,
            )
        db.commit()
        return task_data(db, record)
    except AITaskError as exc:
        db.rollback()
        raise _task_error(exc) from exc


@router.post("/{task_id}/resume", response_model=AITaskData)
def resume_task(
    task_id: str,
    payload: AITaskResumeRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_tasks(current_user)
    record = _owned_task_or_404(
        db,
        task_id=task_id,
        user=current_user,
        allowed_factories=allowed_factories,
        request=request,
        operation="resume",
    )
    try:
        try:
            skill_registry = SkillRegistry(task_tool_registry)
        except SkillRegistryError as exc:
            raise AITaskError("Task Skill registry is unavailable") from exc
        request_task_resume(
            db,
            task=record,
            user=current_user,
            expected_revision=payload.expected_revision,
            expected_input_hash=payload.expected_input_hash,
            expected_runtime_plan_hash=payload.expected_runtime_plan_hash,
            registry=task_tool_registry,
            skill_registry=skill_registry,
            settings=settings,
        )
        add_auth_audit(
            db,
            "ai_task_resume_requested",
            username=current_user.username,
            user_id=current_user.id,
            detail=f"task_id={record.id};state={record.state}",
            request=request,
        )
        db.commit()
        return task_data(db, record)
    except AITaskError as exc:
        db.rollback()
        raise _task_error(exc) from exc


@router.get("/{task_id}/events", response_model=AITaskEventPage)
def get_task_events(
    task_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    allowed_factories = _require_tasks(current_user)
    record = _owned_task_or_404(
        db,
        task_id=task_id,
        user=current_user,
        allowed_factories=allowed_factories,
        request=request,
        operation="events",
    )
    try:
        return read_task_events(
            db,
            task_id=record.id,
            after=after,
            limit=limit,
        )
    except AITaskEventError as exc:
        raise _task_error(exc) from exc


@router.get("/{task_id}/events/stream", response_class=EventSourceResponse)
async def stream_task_events(
    task_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    after: Annotated[int, Query(ge=0)] = 0,
):
    allowed_factories = _require_tasks(current_user)
    _owned_task_or_404(
        db,
        task_id=task_id,
        user=current_user,
        allowed_factories=allowed_factories,
        request=request,
        operation="event_stream",
    )
    stream_session_factory = sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    header_value = request.headers.get("last-event-id", "").strip()
    if header_value:
        if not header_value.isdecimal():
            raise _task_error(AITaskEventError("Task Event header is invalid"))
        after = max(after, int(header_value))

    async def events():
        cursor = after
        elapsed = 0.0
        terminal_states = {"COMPLETED", "FAILED", "CANCELLED"}
        while elapsed < settings.ai_task_event_stream_max_seconds:
            with stream_session_factory() as stream_db:
                try:
                    auth_user = stream_db.get(AuthUser, current_user.id)
                    if (
                        auth_user is None
                        or auth_user.status != "active"
                        or auth_user.force_password_change
                    ):
                        raise AITaskNotFoundError("Task access changed")
                    live_user = build_auth_context(stream_db, auth_user)
                    live_allowed_factories = _require_tasks(live_user)
                    record = get_owned_task(
                        stream_db,
                        task_id=task_id,
                        user=live_user,
                        allowed_factory_scopes=live_allowed_factories,
                    )
                    page = read_task_events(
                        stream_db,
                        task_id=record.id,
                        after=cursor,
                        limit=100,
                    )
                except (AITaskNotFoundError, AITaskEventError, HTTPException):
                    yield ServerSentEvent(
                        event="task.error",
                        data=json.dumps(
                            {"code": "AI_TASK_NOT_FOUND"},
                            separators=(",", ":"),
                        ),
                    )
                    return
                for item in page.items:
                    cursor = item.sequence
                    yield ServerSentEvent(
                        event="task.event",
                        id=str(item.sequence),
                        data=item.model_dump_json(),
                    )
                if record.state in terminal_states and not page.items:
                    yield ServerSentEvent(
                        event="task.closed",
                        id=str(cursor),
                        data=json.dumps(
                            {"task_id": record.id, "state": record.state},
                            separators=(",", ":"),
                        ),
                    )
                    return
            await asyncio.sleep(settings.ai_task_event_stream_poll_seconds)
            elapsed += settings.ai_task_event_stream_poll_seconds
        yield ServerSentEvent(
            event="task.keepalive",
            id=str(cursor),
            data=json.dumps({"after": cursor}, separators=(",", ":")),
        )

    async for event in events():
        yield event
