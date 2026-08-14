from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas.ai.conversation import (
    AIConversationContextBinding,
    AIConversationContextUpdate,
    AIConversationCreate,
    AIConversationDetail,
    AIConversationListItem,
    AIConversationListPage,
    AIConversationMessageCreate,
    AIConversationMessageData,
    AIConversationUpdate,
)
from app.services.ai.conversation_service import (
    ConversationError,
    ConversationNotFoundError,
    append_user_message,
    conversation_list_item,
    create_conversation,
    delete_conversation,
    get_conversation_detail,
    get_owned_conversation,
    list_conversations,
    update_conversation,
    update_conversation_context,
)
from app.services.ai.pilot_guard import AIPilotGuardError, build_pilot_guard
from app.services.auth import AuthContext, add_auth_audit, get_current_user

router = APIRouter(prefix="/api/ai/conversations", tags=["ai-conversations"])
conversation_pilot_guard = build_pilot_guard()

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _conversation_error(error: ConversationError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.public_message,
            "retryable": False,
        },
    )


def _require_conversations(user: AuthContext) -> frozenset[str]:
    if not settings.ai_conversations_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        access = conversation_pilot_guard.evaluate_access(user, settings)
        allowed_factories = conversation_pilot_guard.configured_factory_ids(settings)
    except AIPilotGuardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
    if not access.granted:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前账号未开放 AI 会话权限。",
                "retryable": False,
            },
        )
    return allowed_factories


def _require_record_factory(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    allowed_factories: frozenset[str],
):
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    if record.factory_scope not in allowed_factories:
        raise ConversationNotFoundError("会话不存在。")
    return record


def _audit_access_denied(
    db: Session,
    *,
    user: AuthContext,
    operation: str,
    request: Request,
) -> None:
    add_auth_audit(
        db,
        "ai_conversation_access_denied",
        username=user.username,
        user_id=user.id,
        detail=f"operation={operation}",
        request=request,
    )
    db.commit()


@router.post(
    "",
    response_model=AIConversationListItem,
    status_code=status.HTTP_201_CREATED,
)
def post_conversation(
    payload: AIConversationCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_conversations(current_user)
    if payload.factory_scope not in allowed_factories:
        _audit_access_denied(
            db,
            user=current_user,
            operation="create_factory",
            request=request,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前厂区未开放 AI 会话权限。",
                "retryable": False,
            },
        )
    try:
        return conversation_list_item(
            create_conversation(
                db,
                payload=payload,
                user=current_user,
                settings=settings,
            )
        )
    except ConversationError as exc:
        raise _conversation_error(exc) from exc


@router.get("", response_model=AIConversationListPage)
def get_conversations(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
):
    allowed_factories = _require_conversations(current_user)
    try:
        return list_conversations(
            db,
            user=current_user,
            limit=limit,
            cursor=cursor,
            allowed_factory_scopes=allowed_factories,
        )
    except ConversationError as exc:
        raise _conversation_error(exc) from exc


@router.get("/{conversation_id}", response_model=AIConversationDetail)
def get_conversation(
    conversation_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    message_limit: Annotated[int, Query(ge=1, le=50)] = 50,
    message_cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
):
    allowed_factories = _require_conversations(current_user)
    try:
        _require_record_factory(
            db,
            conversation_id=conversation_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        return get_conversation_detail(
            db,
            conversation_id=conversation_id,
            user=current_user,
            message_limit=message_limit,
            message_cursor=message_cursor,
        )
    except ConversationError as exc:
        if isinstance(exc, ConversationNotFoundError):
            _audit_access_denied(
                db,
                user=current_user,
                operation="detail",
                request=request,
            )
        raise _conversation_error(exc) from exc


@router.patch(
    "/{conversation_id}/context",
    response_model=AIConversationContextBinding | None,
)
def patch_conversation_context(
    conversation_id: str,
    payload: AIConversationContextUpdate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    if not settings.ai_conversation_context_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    allowed_factories = _require_conversations(current_user)
    try:
        _require_record_factory(
            db,
            conversation_id=conversation_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        result = update_conversation_context(
            db,
            conversation_id=conversation_id,
            payload=payload,
            user=current_user,
            settings=settings,
        )
        add_auth_audit(
            db,
            "ai_conversation_context_changed",
            username=current_user.username,
            user_id=current_user.id,
            detail=(
                "operation=context_switch module_id="
                + (result.module_id if result is not None else "none")
            ),
            request=request,
        )
        db.commit()
        return result
    except ConversationError as exc:
        add_auth_audit(
            db,
            "ai_conversation_context_denied",
            username=current_user.username,
            user_id=current_user.id,
            detail=f"operation=context_switch code={exc.code}",
            request=request,
        )
        db.commit()
        raise _conversation_error(exc) from exc


@router.patch("/{conversation_id}", response_model=AIConversationListItem)
def patch_conversation(
    conversation_id: str,
    payload: AIConversationUpdate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    if not settings.ai_workbench_v2_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    allowed_factories = _require_conversations(current_user)
    try:
        _require_record_factory(
            db,
            conversation_id=conversation_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        result = update_conversation(
            db,
            conversation_id=conversation_id,
            payload=payload,
            user=current_user,
        )
        add_auth_audit(
            db,
            "ai_conversation_metadata_changed",
            username=current_user.username,
            user_id=current_user.id,
            detail="operation=conversation_management",
            request=request,
        )
        db.commit()
        return result
    except ConversationError as exc:
        raise _conversation_error(exc) from exc


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    allowed_factories = _require_conversations(current_user)
    try:
        try:
            record = _require_record_factory(
                db,
                conversation_id=conversation_id,
                user=current_user,
                allowed_factories=allowed_factories,
            )
        except ConversationNotFoundError:
            _audit_access_denied(
                db,
                user=current_user,
                operation="delete",
                request=request,
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        delete_conversation(
            db,
            conversation_id=record.id,
            user=current_user,
            settings=settings,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ConversationError as exc:
        raise _conversation_error(exc) from exc


@router.post(
    "/{conversation_id}/messages",
    response_model=AIConversationMessageData,
    status_code=status.HTTP_201_CREATED,
)
def post_conversation_message(
    conversation_id: str,
    payload: AIConversationMessageCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_conversations(current_user)
    try:
        _require_record_factory(
            db,
            conversation_id=conversation_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        return append_user_message(
            db,
            conversation_id=conversation_id,
            payload=payload,
            user=current_user,
            settings=settings,
        )
    except ConversationError as exc:
        if isinstance(exc, ConversationNotFoundError):
            _audit_access_denied(
                db,
                user=current_user,
                operation="append",
                request=request,
            )
        raise _conversation_error(exc) from exc
