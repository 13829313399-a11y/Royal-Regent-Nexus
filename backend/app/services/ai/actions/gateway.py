from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.ai.action_confirmation import (
    AIActionApproveRequest,
    AIActionExecuteRequest,
    AIActionGatewayExecutionData,
    AIActionProposalData,
)
from app.services.ai.action_confirmation import (
    action_proposal_data,
    confirm_action,
    execute_action,
    load_action_proposal,
    reject_action,
)
from app.services.ai.action_registry import AIActionRegistry
from app.services.auth import AuthContext


def get_proposal(
    db: Session,
    *,
    proposal_id: str,
    factory_id: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionProposalData:
    record = load_action_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=factory_id,
        user=user,
        registry=registry,
    )
    return action_proposal_data(db, record, registry)


def approve_proposal(
    db: Session,
    *,
    proposal_id: str,
    payload: AIActionApproveRequest,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionProposalData:
    record = confirm_action(
        db,
        confirmation_id=proposal_id,
        factory_id=payload.factory_id,
        expected_args_hash=payload.expected_args_hash,
        user=user,
        registry=registry,
        approval_request_id=payload.approval_request_id,
    )
    return action_proposal_data(db, record, registry)


def reject_proposal(
    db: Session,
    *,
    proposal_id: str,
    factory_id: str,
    expected_args_hash: str,
    rejection_reason: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionProposalData:
    record = reject_action(
        db,
        confirmation_id=proposal_id,
        factory_id=factory_id,
        expected_args_hash=expected_args_hash,
        rejection_reason=rejection_reason,
        user=user,
        registry=registry,
    )
    return action_proposal_data(db, record, registry)


def cancel_proposal(
    db: Session,
    *,
    proposal_id: str,
    factory_id: str,
    expected_args_hash: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionProposalData:
    from app.services.ai.action_confirmation import cancel_action

    load_action_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=factory_id,
        user=user,
        registry=registry,
    )
    record = cancel_action(
        db,
        confirmation_id=proposal_id,
        factory_id=factory_id,
        expected_args_hash=expected_args_hash,
        user=user,
    )
    return action_proposal_data(db, record, registry)


def execute_proposal(
    db: Session,
    *,
    proposal_id: str,
    payload: AIActionExecuteRequest,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionGatewayExecutionData:
    execution = execute_action(
        db,
        confirmation_id=proposal_id,
        payload=payload,
        user=user,
        registry=registry,
    )
    record = load_action_proposal(
        db,
        proposal_id=proposal_id,
        factory_id=payload.factory_id,
        user=user,
        registry=registry,
    )
    return AIActionGatewayExecutionData(
        proposal=action_proposal_data(db, record, registry),
        result=execution.result,
    )
