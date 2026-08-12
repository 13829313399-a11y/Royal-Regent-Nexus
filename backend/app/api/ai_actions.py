from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas.ai.action_confirmation import (
    AIActionCancelRequest,
    AIActionConfirmationData,
    AIActionConfirmRequest,
    AIActionExecuteRequest,
    AIActionExecutionData,
)
from app.services.ai.action_confirmation import (
    cancel_action,
    confirm_action,
    confirmation_data,
    execute_action,
)
from app.services.ai.action_registry import build_default_action_registry
from app.services.ai.pilot_guard import AIPilotGuard, AIPilotGuardError
from app.services.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/ai/action-confirmations", tags=["ai-actions"])
action_registry = build_default_action_registry()
action_pilot_guard = AIPilotGuard()

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _require_controlled_apply(user: AuthContext) -> None:
    if not settings.ai_controlled_apply_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        access = action_pilot_guard.evaluate_access(user, settings)
    except AIPilotGuardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
    if not access.granted:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前账号未开放 AI 受控操作权限。",
                "retryable": False,
            },
        )


@router.post(
    "/{confirmation_id}/confirm",
    response_model=AIActionConfirmationData,
)
def post_confirm_action(
    confirmation_id: str,
    payload: AIActionConfirmRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_controlled_apply(current_user)
    record = confirm_action(
        db,
        confirmation_id=confirmation_id,
        factory_id=payload.factory_id,
        expected_args_hash=payload.expected_args_hash,
        user=current_user,
        registry=action_registry,
    )
    return confirmation_data(db, record, action_registry)


@router.post(
    "/{confirmation_id}/cancel",
    response_model=AIActionConfirmationData,
)
def post_cancel_action(
    confirmation_id: str,
    payload: AIActionCancelRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_controlled_apply(current_user)
    record = cancel_action(
        db,
        confirmation_id=confirmation_id,
        factory_id=payload.factory_id,
        expected_args_hash=payload.expected_args_hash,
        user=current_user,
    )
    return confirmation_data(db, record, action_registry)


@router.post(
    "/{confirmation_id}/execute",
    response_model=AIActionExecutionData,
)
def post_execute_action(
    confirmation_id: str,
    payload: AIActionExecuteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_controlled_apply(current_user)
    return execute_action(
        db,
        confirmation_id=confirmation_id,
        payload=payload,
        user=current_user,
        registry=action_registry,
    )
