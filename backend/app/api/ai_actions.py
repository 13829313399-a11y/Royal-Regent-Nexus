from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas.ai.action_confirmation import (
    AIActionApproveRequest,
    AIActionCancelRequest,
    AIActionConfirmationData,
    AIActionConfirmRequest,
    AIActionExecuteRequest,
    AIActionExecutionData,
    AIActionGatewayExecutionData,
    AIActionProposalData,
    AIActionRejectRequest,
)
from app.services.ai.action_confirmation import (
    cancel_action,
    confirm_action,
    confirmation_data,
    execute_action,
)
from app.services.ai.action_registry import build_default_action_registry
from app.services.ai.actions.gateway import (
    approve_proposal,
    cancel_proposal,
    execute_proposal,
    get_proposal,
    reject_proposal,
)
from app.services.ai.pilot_guard import AIPilotGuard, AIPilotGuardError
from app.services.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/ai/action-confirmations", tags=["ai-actions"])
gateway_router = APIRouter(prefix="/api/ai/actions", tags=["ai-action-gateway"])
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


def _require_action_gateway(user: AuthContext) -> None:
    if not settings.ai_action_gateway_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    _require_controlled_apply(user)


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


@gateway_router.get("/{proposal_id}", response_model=AIActionProposalData)
def get_action_proposal(
    proposal_id: str,
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_action_gateway(current_user)
    return get_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=factory_id,
        user=current_user,
        registry=action_registry,
    )


@gateway_router.post(
    "/{proposal_id}/approve",
    response_model=AIActionProposalData,
)
def post_approve_proposal(
    proposal_id: str,
    payload: AIActionApproveRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_action_gateway(current_user)
    return approve_proposal(
        db,
        proposal_id=proposal_id,
        payload=payload,
        user=current_user,
        registry=action_registry,
    )


@gateway_router.post(
    "/{proposal_id}/reject",
    response_model=AIActionProposalData,
)
def post_reject_proposal(
    proposal_id: str,
    payload: AIActionRejectRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_action_gateway(current_user)
    return reject_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=payload.factory_id,
        expected_args_hash=payload.expected_args_hash,
        rejection_reason=payload.rejection_reason,
        user=current_user,
        registry=action_registry,
    )


@gateway_router.post(
    "/{proposal_id}/cancel",
    response_model=AIActionProposalData,
)
def post_cancel_proposal(
    proposal_id: str,
    payload: AIActionCancelRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_action_gateway(current_user)
    return cancel_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=payload.factory_id,
        expected_args_hash=payload.expected_args_hash,
        user=current_user,
        registry=action_registry,
    )


@gateway_router.post(
    "/{proposal_id}/execute",
    response_model=AIActionGatewayExecutionData,
)
def post_execute_proposal(
    proposal_id: str,
    payload: AIActionExecuteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_action_gateway(current_user)
    return execute_proposal(
        db,
        proposal_id=proposal_id,
        payload=payload,
        user=current_user,
        registry=action_registry,
    )
