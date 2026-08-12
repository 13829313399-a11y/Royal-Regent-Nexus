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
    AIActionConfirmationData,
    AIActionExecuteRequest,
    AIActionExecutionData,
    AIControlledApplyResult,
)
from app.services.ai.action_registry import (
    ActionConfirmationStaleError,
    AIActionHandler,
    AIActionRegistry,
)
from app.services.auth import AuthContext, authorization_decision

action_logger = logging.getLogger("app.ai.action")
_CONFIRMATION_TTL_MINUTES = 10


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
    )
    db.add(record)
    try:
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


def confirm_action(
    db: Session,
    *,
    confirmation_id: str,
    factory_id: str,
    expected_args_hash: str,
    user: AuthContext,
    registry: AIActionRegistry,
) -> AIActionConfirmation:
    record = _load_owned(db, confirmation_id, user, factory_id, lock=True)
    _verify_hash(record, expected_args_hash)
    handler = _handler(registry, record.tool_name)
    _require_permission(user, handler, factory_id)
    if record.status in {"CONFIRMED", "EXECUTED"}:
        return record
    if record.status != "PENDING":
        raise _error(409, "CONFIRMATION_STATE_INVALID", f"状态 {record.status} 不可确认")
    if _is_expired(record):
        record.status = "EXPIRED"
        record.failure_code = "CONFIRMATION_EXPIRED"
        db.commit()
        raise _error(409, "CONFIRMATION_EXPIRED", "确认已过期，请重新预览")
    action = _action(record, handler)
    try:
        handler.freshness_validator(db, record, action)
    except ActionConfirmationStaleError as exc:
        record.status = "STALE"
        record.failure_code = "STALE_CONFIRMATION"
        db.commit()
        raise _error(409, "STALE_CONFIRMATION", str(exc)) from exc
    record.status = "CONFIRMED"
    record.confirmed_at = business_now().isoformat(timespec="seconds")
    db.commit()
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
    if record.status == "CANCELLED":
        return record
    if record.status != "PENDING":
        raise _error(409, "CONFIRMATION_STATE_INVALID", f"状态 {record.status} 不可取消")
    record.status = "CANCELLED"
    db.commit()
    return record


def _mark_failure(
    db: Session,
    confirmation_id: str,
    *,
    status: str,
    failure_code: str,
) -> None:
    db.rollback()
    record = db.get(AIActionConfirmation, confirmation_id)
    if record is not None and record.status == "CONFIRMED":
        record.status = status
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
    action = _action(record, handler)
    if record.status == "EXECUTED":
        if record.execution_request_id != payload.execution_request_id:
            raise _error(409, "CONFIRMATION_ALREADY_EXECUTED", "确认已由另一执行请求使用")
        result = AIControlledApplyResult.model_validate_json(record.execution_result_json)
        result = result.model_copy(update={"idempotent_replay": True})
        return AIActionExecutionData(
            confirmation=confirmation_data(db, record, registry),
            result=result,
        )
    if record.status != "CONFIRMED":
        raise _error(409, "CONFIRMATION_STATE_INVALID", "操作必须先由用户明确确认")
    if _is_expired(record):
        record.status = "STALE"
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
            .values(execution_request_id=payload.execution_request_id)
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
        _mark_failure(db, confirmation_id, status=status, failure_code=code)
        raise
    except Exception:
        _mark_failure(
            db,
            confirmation_id,
            status="FAILED",
            failure_code="ACTION_EXECUTION_FAILED",
        )
        raise

    record = db.get(AIActionConfirmation, confirmation_id)
    if record is None:
        raise _error(409, "CONFIRMATION_NOT_FOUND", "确认记录不存在")
    record.status = "EXECUTED"
    record.executed_at = business_now().isoformat(timespec="seconds")
    record.execution_result_json = _json(result.model_dump(mode="json"))
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
