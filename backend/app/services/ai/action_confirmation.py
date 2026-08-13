from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
from app.models.ai_action import AIActionConfirmation
from app.schemas.ai.action_confirmation import (
    AIActionApprovalBindingData,
    AIActionApprovalPolicyData,
    AIActionCompensationData,
    AIActionConfirmationData,
    AIActionExecuteRequest,
    AIActionExecutionData,
    AIActionHandlerManifestData,
    AIActionProposalData,
    AIActionVerificationData,
    AIControlledApplyResult,
)
from app.services.ai.action_registry import (
    ActionConfirmationStaleError,
    AIActionHandler,
    AIActionRegistry,
)
from app.services.ai.actions.contracts import ActionVerificationError
from app.services.ai.actions.policy import (
    APPROVAL_SOURCE_USER_API,
    validate_approval_source,
)
from app.services.ai.actions.verification import verification_json
from app.services.auth import AuthContext, authorization_decision

action_logger = logging.getLogger("app.ai.action")
_CONFIRMATION_TTL_MINUTES = 10
_GATEWAY_CONTRACT_VERSION = "action-gateway-v1"
_COMPENSATION = AIActionCompensationData()

_LEGACY_TO_LIFECYCLE = {
    "PENDING": "WAITING_APPROVAL",
    "CONFIRMED": "APPROVED",
    "EXECUTED": "EXECUTED",
    "EXPIRED": "EXPIRED",
    "CANCELLED": "CANCELLED",
    "STALE": "STALE",
    "FAILED": "FAILED",
}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _handler(registry: AIActionRegistry, tool_name: str) -> AIActionHandler:
    handler = registry.resolve(tool_name)
    if handler is None:
        raise _error(409, "ACTION_NOT_AVAILABLE", "该确认操作当前不可用")
    return handler


def _action(record: AIActionConfirmation, handler: AIActionHandler) -> BaseModel:
    try:
        return handler.action_model.model_validate_json(record.normalized_action_json)
    except (ValidationError, ValueError) as exc:
        raise _error(409, "INVALID_CANONICAL_ACTION", "确认记录中的规范操作无效") from exc


def _permission_allowed(
    user: AuthContext,
    handler: AIActionHandler,
    factory_id: str,
) -> bool:
    return any(
        authorization_decision(
            user,
            handler.required_permission,
            factory_id,
            department,
        )[0]
        for department in handler.allowed_departments
    )


def _require_permission(
    user: AuthContext,
    handler: AIActionHandler,
    factory_id: str,
) -> None:
    if not _permission_allowed(user, handler, factory_id):
        raise _error(403, "ACTION_PERMISSION_DENIED", "没有执行该确认操作所需的权限")


def _load_owned(
    db: Session,
    confirmation_id: str,
    user: AuthContext,
    factory_id: str,
    *,
    lock: bool,
) -> AIActionConfirmation:
    statement = select(AIActionConfirmation).where(
        AIActionConfirmation.id == confirmation_id
    )
    if lock:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise _error(404, "CONFIRMATION_NOT_FOUND", "确认记录不存在")
    if record.user_id != user.id:
        raise _error(403, "CONFIRMATION_USER_MISMATCH", "只能操作由当前用户创建的确认记录")
    if record.factory_id != factory_id:
        raise _error(403, "CONFIRMATION_FACTORY_MISMATCH", "确认记录不属于当前厂区")
    return record


def _verify_hash(record: AIActionConfirmation, expected_args_hash: str) -> None:
    if record.args_hash != expected_args_hash:
        raise _error(409, "CONFIRMATION_ARGS_MISMATCH", "操作内容已变化，请重新预览")


def _is_expired(record: AIActionConfirmation) -> bool:
    expires_at = parse_business_timestamp(record.expires_at)
    return expires_at is None or expires_at <= business_now()


def _lifecycle(record: AIActionConfirmation) -> str:
    return record.lifecycle_status or _LEGACY_TO_LIFECYCLE.get(
        record.status, "FAILED"
    )


def _require_handler_version(
    record: AIActionConfirmation,
    handler: AIActionHandler,
) -> None:
    if record.gateway_contract_version != _GATEWAY_CONTRACT_VERSION:
        return
    if (
        record.handler_version != handler.manifest.handler_version
        or record.approval_policy_version != handler.approval_policy.policy_version
    ):
        raise _error(
            409,
            "ACTION_HANDLER_VERSION_STALE",
            "Action Handler 或 Approval Policy 版本已变化，请重新创建 Proposal",
        )


def create_action_confirmation(
    db: Session,
    *,
    handler: AIActionHandler,
    normalized_action: BaseModel,
    user: AuthContext,
    request_id: str,
) -> AIActionConfirmation:
    canonical = normalized_action.model_dump(mode="json")
    factory_id = str(canonical[handler.factory_argument])
    entity_id = str(canonical[handler.entity_id_argument])
    entity_revision = int(canonical[handler.entity_revision_argument])
    args_hash = _hash(canonical)
    replay = db.scalar(
        select(AIActionConfirmation).where(
            AIActionConfirmation.user_id == user.id,
            AIActionConfirmation.tool_name == handler.tool_name,
            AIActionConfirmation.request_id == request_id,
        )
    )
    if replay is not None:
        if replay.args_hash != args_hash:
            raise _error(409, "CONFIRMATION_REQUEST_CONFLICT", "相同请求已用于不同操作")
        _require_handler_version(replay, handler)
        return replay
    now = business_now()
    record = AIActionConfirmation(
        id=f"aic-{uuid4().hex}",
        user_id=user.id,
        tool_name=handler.tool_name,
        risk_level=handler.risk_level,
        factory_id=factory_id,
        entity_type=handler.entity_type,
        entity_id=entity_id,
        entity_revision=entity_revision,
        args_hash=args_hash,
        normalized_action_json=_json(canonical),
        request_id=request_id,
        expires_at=(now + timedelta(minutes=_CONFIRMATION_TTL_MINUTES)).isoformat(
            timespec="seconds"
        ),
        status="PENDING",
        created_at=now.isoformat(timespec="seconds"),
        confirmed_at="",
        executed_at="",
        execution_request_id="",
        execution_result_json="{}",
        failure_code="",
        gateway_contract_version=(
            _GATEWAY_CONTRACT_VERSION
            if handler.post_verifier is not None
            else "legacy-confirmation-v1"
        ),
        action_type=handler.manifest.action_type,
        handler_version=handler.manifest.handler_version,
        approval_policy_version=handler.approval_policy.policy_version,
        lifecycle_status="PROPOSED",
        waiting_approval_at="",
        approval_user_id=None,
        approval_request_id="",
        approval_args_hash="",
        approval_entity_revision=0,
        approval_expires_at="",
        rejected_at="",
        rejection_reason="",
        commit_started_at="",
        verification_started_at="",
        verified_at="",
        execution_user_id=None,
        domain_audit_id="",
        verification_result_json="{}",
        compensation_json=_json(_COMPENSATION.model_dump(mode="json")),
    )
    db.add(record)
    try:
        db.flush()
        record.lifecycle_status = "WAITING_APPROVAL"
        record.waiting_approval_at = now.isoformat(timespec="seconds")
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(AIActionConfirmation).where(
                AIActionConfirmation.user_id == user.id,
                AIActionConfirmation.tool_name == handler.tool_name,
                AIActionConfirmation.request_id == request_id,
            )
        )
        if replay is not None and replay.args_hash == args_hash:
            _require_handler_version(replay, handler)
            return replay
        raise _error(409, "CONFIRMATION_REQUEST_CONFLICT", "确认请求发生并发冲突") from None
    action_logger.info(
        "ai_action_confirmation_created confirmation_id=%s user_id=%s tool=%s factory_id=%s",
        record.id,
        user.id,
        handler.tool_name,
        factory_id,
    )
    return record


def confirmation_data(
    db: Session,
    record: AIActionConfirmation,
    registry: AIActionRegistry,
) -> AIActionConfirmationData:
    handler = _handler(registry, record.tool_name)
    action = _action(record, handler)
    return AIActionConfirmationData(
        confirmation_id=record.id,
        tool_name=record.tool_name,
        risk_level=record.risk_level,
        factory_id=record.factory_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        entity_revision=record.entity_revision,
        args_hash=record.args_hash,
        expires_at=record.expires_at,
        status=record.status,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
        executed_at=record.executed_at,
        failure_code=record.failure_code,
        action_summary=handler.summary_builder(db, action),
    )


def load_action_proposal(
    db: Session,
    *,
    proposal_id: str,
    factory_id: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionConfirmation:
    record = _load_owned(db, proposal_id, user, factory_id, lock=False)
    handler = _handler(registry, record.tool_name)
    _require_permission(user, handler, factory_id)
    _require_handler_version(record, handler)
    return record


def action_proposal_data(
    db: Session,
    record: AIActionConfirmation,
    registry: AIActionRegistry,
) -> AIActionProposalData:
    handler = _handler(registry, record.tool_name)
    action = _action(record, handler)
    approval = None
    if record.approval_user_id:
        approval = AIActionApprovalBindingData(
            approval_user_id=record.approval_user_id,
            approval_request_id=record.approval_request_id,
            factory_id=record.factory_id,
            action_type=record.action_type or handler.manifest.action_type,
            args_hash=record.approval_args_hash,
            entity_revision=record.approval_entity_revision,
            expires_at=record.approval_expires_at,
            approved_at=record.confirmed_at,
        )
    verification = None
    if record.verification_result_json and record.verification_result_json != "{}":
        try:
            verification = AIActionVerificationData.model_validate_json(
                record.verification_result_json
            )
        except (ValidationError, ValueError) as exc:
            raise _error(
                409,
                "ACTION_VERIFICATION_EVIDENCE_INVALID",
                "Action 后置验证证据无效",
            ) from exc
    try:
        compensation = AIActionCompensationData.model_validate_json(
            record.compensation_json or "{}"
        )
    except (ValidationError, ValueError):
        compensation = _COMPENSATION
    return AIActionProposalData(
        proposal_id=record.id,
        compatibility_confirmation_id=record.id,
        lifecycle_status=_lifecycle(record),
        legacy_status=record.status,
        factory_id=record.factory_id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        entity_revision=record.entity_revision,
        args_hash=record.args_hash,
        expires_at=record.expires_at,
        created_at=record.created_at,
        failure_code=record.failure_code,
        manifest=AIActionHandlerManifestData(
            action_type=handler.manifest.action_type,
            handler_version=handler.manifest.handler_version,
            autonomy_level=handler.manifest.autonomy_level,
            risk_level=handler.risk_level,
            target_state=handler.manifest.target_state,
            model_may_propose=handler.manifest.model_may_propose,
            model_may_approve=handler.manifest.model_may_approve,
            model_may_execute=handler.manifest.model_may_execute,
            publish_allowed=handler.manifest.publish_allowed,
            rollback_allowed=handler.manifest.rollback_allowed,
        ),
        approval_policy=AIActionApprovalPolicyData(
            policy_id=handler.approval_policy.policy_id,
            policy_version=handler.approval_policy.policy_version,
            approvals_required=handler.approval_policy.approvals_required,
            approver_must_be_proposer=(
                handler.approval_policy.approver_must_be_proposer
            ),
            allowed_source=handler.approval_policy.allowed_source,
        ),
        approval=approval,
        action_summary=handler.summary_builder(db, action),
        verification=verification,
        compensation=compensation,
    )


def confirm_action(
    db: Session,
    *,
    confirmation_id: str,
    factory_id: str,
    expected_args_hash: str,
    user: AuthContext,
    registry: AIActionRegistry,
    approval_request_id: str = "",
) -> AIActionConfirmation:
    record = _load_owned(db, confirmation_id, user, factory_id, lock=True)
    _verify_hash(record, expected_args_hash)
    handler = _handler(registry, record.tool_name)
    _require_permission(user, handler, factory_id)
    _require_handler_version(record, handler)
    lifecycle = _lifecycle(record)
    effective_request_id = approval_request_id or f"legacy-confirm-{record.id}"
    if lifecycle in {"APPROVED", "COMMITTING", "VERIFYING", "EXECUTED"}:
        if (
            record.approval_request_id
            and record.approval_request_id != effective_request_id
        ):
            raise _error(409, "APPROVAL_REQUEST_CONFLICT", "该操作已由另一批准请求确认")
        return record
    if lifecycle != "WAITING_APPROVAL":
        raise _error(409, "CONFIRMATION_STATE_INVALID", f"状态 {lifecycle} 不可确认")
    if _is_expired(record):
        record.status = "EXPIRED"
        record.lifecycle_status = "EXPIRED"
        record.failure_code = "CONFIRMATION_EXPIRED"
        db.commit()
        raise _error(409, "CONFIRMATION_EXPIRED", "确认已过期，请重新预览")
    action = _action(record, handler)
    try:
        handler.freshness_validator(db, record, action)
    except ActionConfirmationStaleError as exc:
        record.status = "STALE"
        record.lifecycle_status = "STALE"
        record.failure_code = "STALE_CONFIRMATION"
        db.commit()
        raise _error(409, "STALE_CONFIRMATION", str(exc)) from exc
    try:
        validate_approval_source(
            handler.approval_policy,
            approval_source=APPROVAL_SOURCE_USER_API,
            proposer_user_id=record.user_id,
            approver_user_id=user.id,
        )
    except ValueError as exc:
        raise _error(403, "ACTION_APPROVAL_SOURCE_DENIED", str(exc)) from exc
    approved_at = business_now().isoformat(timespec="seconds")
    record.status = "CONFIRMED"
    record.lifecycle_status = "APPROVED"
    record.confirmed_at = approved_at
    record.approval_user_id = user.id
    record.approval_request_id = effective_request_id
    record.approval_args_hash = record.args_hash
    record.approval_entity_revision = record.entity_revision
    record.approval_expires_at = record.expires_at
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(
            409,
            "APPROVAL_REQUEST_CONFLICT",
            "该批准请求已用于另一操作",
        ) from None
    return record


def cancel_action(
    db: Session,
    *,
    confirmation_id: str,
    factory_id: str,
    expected_args_hash: str,
    user: AuthContext,
) -> AIActionConfirmation:
    record = _load_owned(db, confirmation_id, user, factory_id, lock=True)
    _verify_hash(record, expected_args_hash)
    if _lifecycle(record) == "CANCELLED":
        return record
    if _lifecycle(record) != "WAITING_APPROVAL":
        raise _error(
            409,
            "CONFIRMATION_STATE_INVALID",
            f"状态 {_lifecycle(record)} 不可取消",
        )
    record.status = "CANCELLED"
    record.lifecycle_status = "CANCELLED"
    db.commit()
    return record


def reject_action(
    db: Session,
    *,
    confirmation_id: str,
    factory_id: str,
    expected_args_hash: str,
    rejection_reason: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionConfirmation:
    record = _load_owned(db, confirmation_id, user, factory_id, lock=True)
    _verify_hash(record, expected_args_hash)
    handler = _handler(registry, record.tool_name)
    _require_permission(user, handler, factory_id)
    _require_handler_version(record, handler)
    if _lifecycle(record) == "REJECTED":
        return record
    if _lifecycle(record) != "WAITING_APPROVAL":
        raise _error(
            409,
            "ACTION_STATE_INVALID",
            f"状态 {_lifecycle(record)} 不可拒绝",
        )
    record.status = "CANCELLED"
    record.lifecycle_status = "REJECTED"
    record.rejected_at = business_now().isoformat(timespec="seconds")
    record.rejection_reason = rejection_reason[:1000]
    db.commit()
    return record


def _mark_failure(
    db: Session,
    confirmation_id: str,
    *,
    status: str,
    failure_code: str,
    lifecycle_status: str | None = None,
) -> None:
    db.rollback()
    record = db.get(AIActionConfirmation, confirmation_id)
    if record is not None and record.status == "CONFIRMED":
        record.status = status
        record.lifecycle_status = lifecycle_status or status
        record.failure_code = failure_code[:96]
        db.commit()


def execute_action(
    db: Session,
    *,
    confirmation_id: str,
    payload: AIActionExecuteRequest,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionExecutionData:
    record = _load_owned(
        db,
        confirmation_id,
        user,
        payload.factory_id,
        lock=True,
    )
    _verify_hash(record, payload.expected_args_hash)
    handler = _handler(registry, record.tool_name)
    _require_permission(user, handler, payload.factory_id)
    _require_handler_version(record, handler)
    action = _action(record, handler)
    lifecycle = _lifecycle(record)
    if lifecycle == "EXECUTED":
        if record.execution_request_id != payload.execution_request_id:
            raise _error(409, "CONFIRMATION_ALREADY_EXECUTED", "确认已由另一执行请求使用")
        result = AIControlledApplyResult.model_validate_json(record.execution_result_json)
        result = result.model_copy(update={"idempotent_replay": True})
        return AIActionExecutionData(
            confirmation=confirmation_data(db, record, registry),
            result=result,
        )
    if lifecycle not in {"APPROVED", "COMMITTING", "VERIFYING"}:
        raise _error(409, "CONFIRMATION_STATE_INVALID", "操作必须先由用户明确确认")
    if (
        record.gateway_contract_version == _GATEWAY_CONTRACT_VERSION
        and handler.post_verifier is None
    ):
        raise _error(
            409,
            "ACTION_HANDLER_INVALID",
            "Action Handler 缺少正式对象后置验证器",
        )
    if (
        record.approval_user_id != user.id
        or record.approval_args_hash != record.args_hash
        or record.approval_entity_revision != record.entity_revision
        or record.approval_expires_at != record.expires_at
    ):
        record.status = "STALE"
        record.lifecycle_status = "STALE"
        record.failure_code = "APPROVAL_BINDING_INVALID"
        db.commit()
        raise _error(409, "APPROVAL_BINDING_INVALID", "批准绑定已变化，请重新创建 Proposal")
    if _is_expired(record):
        record.status = "STALE"
        record.lifecycle_status = "STALE"
        record.failure_code = "CONFIRMATION_EXPIRED"
        db.commit()
        raise _error(409, "CONFIRMATION_EXPIRED", "确认已过期，请重新预览")
    try:
        handler.freshness_validator(db, record, action)
        handler.execution_validator(
            db,
            action,
            payload.review_override_reason,
            user,
        )
    except ActionConfirmationStaleError as exc:
        record.status = "STALE"
        record.lifecycle_status = "STALE"
        record.failure_code = "STALE_CONFIRMATION"
        db.commit()
        raise _error(409, "STALE_CONFIRMATION", str(exc)) from exc

    if record.execution_request_id:
        if record.execution_request_id != payload.execution_request_id:
            raise _error(409, "CONFIRMATION_EXECUTION_CLAIMED", "确认正在由另一请求执行")
    else:
        claim = db.execute(
            update(AIActionConfirmation)
            .where(
                AIActionConfirmation.id == record.id,
                AIActionConfirmation.status == "CONFIRMED",
                AIActionConfirmation.execution_request_id == "",
            )
            .values(
                execution_request_id=payload.execution_request_id,
                execution_user_id=user.id,
                lifecycle_status="COMMITTING",
                commit_started_at=business_now().isoformat(timespec="seconds"),
            )
        )
        if claim.rowcount != 1:
            db.rollback()
            raise _error(409, "CONFIRMATION_EXECUTION_CLAIMED", "确认已被其他请求占用")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise _error(
                409,
                "EXECUTION_REQUEST_CONFLICT",
                "该执行请求已用于另一确认操作",
            ) from None

    try:
        result = handler.executor(
            db,
            action,
            payload.execution_request_id,
            payload.review_override_reason,
            user,
        )
    except HTTPException as exc:
        status = "STALE" if exc.status_code == 409 else "FAILED"
        code = "STALE_CONFIRMATION" if status == "STALE" else "ACTION_EXECUTION_FAILED"
        _mark_failure(
            db,
            confirmation_id,
            status=status,
            failure_code=code,
            lifecycle_status=status,
        )
        raise
    except Exception:
        _mark_failure(
            db,
            confirmation_id,
            status="FAILED",
            failure_code="ACTION_EXECUTION_FAILED",
            lifecycle_status="FAILED",
        )
        raise

    record = db.get(AIActionConfirmation, confirmation_id)
    if record is None:
        raise _error(409, "CONFIRMATION_NOT_FOUND", "确认记录不存在")
    record.lifecycle_status = "VERIFYING"
    record.verification_started_at = business_now().isoformat(timespec="seconds")
    record.execution_result_json = _json(result.model_dump(mode="json"))
    db.commit()
    verification: AIActionVerificationData | None = None
    if handler.post_verifier is not None:
        try:
            verification = handler.post_verifier(db, action, result)
        except ActionVerificationError as exc:
            _mark_failure(
                db,
                confirmation_id,
                status="FAILED",
                failure_code="ACTION_POST_VERIFICATION_FAILED",
                lifecycle_status="FAILED",
            )
            raise _error(
                409,
                "ACTION_POST_VERIFICATION_FAILED",
                str(exc),
            ) from exc
    record = db.get(AIActionConfirmation, confirmation_id)
    if record is None:
        raise _error(409, "CONFIRMATION_NOT_FOUND", "确认记录不存在")
    if verification is not None:
        record.verification_result_json = _json(verification_json(verification))
        record.domain_audit_id = verification.domain_audit_id
        record.verified_at = verification.verified_at
    record.status = "EXECUTED"
    record.lifecycle_status = "EXECUTED"
    record.executed_at = business_now().isoformat(timespec="seconds")
    record.failure_code = ""
    db.commit()
    action_logger.info(
        "ai_action_executed confirmation_id=%s user_id=%s tool=%s factory_id=%s",
        record.id,
        user.id,
        record.tool_name,
        record.factory_id,
    )
    return AIActionExecutionData(
        confirmation=confirmation_data(db, record, registry),
        result=result,
    )
