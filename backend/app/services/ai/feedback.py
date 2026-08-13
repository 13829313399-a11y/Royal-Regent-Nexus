from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.ai_action import AIActionConfirmation
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_observability import AIFeedback, AIMetricEvent
from app.models.ai_task import AITask
from app.schemas.ai.feedback import (
    AIFeedbackCreate,
    AIFeedbackData,
    AIFeedbackPage,
    AIFeedbackReview,
)
from app.services.auth import AuthContext


@dataclass(frozen=True, slots=True)
class FeedbackError(RuntimeError):
    status_code: int
    code: str
    public_message: str


def _error(status_code: int, code: str, message: str) -> FeedbackError:
    return FeedbackError(status_code, code, message)


def _ensure_target(
    db: Session,
    *,
    payload: AIFeedbackCreate,
    user: AuthContext,
) -> None:
    if payload.target_type == "RESPONSE":
        record = db.scalar(
            select(AIMetricEvent).where(
                AIMetricEvent.request_id == payload.target_id,
                AIMetricEvent.event_type == "MODEL_RUN",
            )
        )
        owner_id = record.owner_user_id if record else ""
        factory_id = record.factory_id if record else ""
    elif payload.target_type == "MESSAGE":
        row = db.execute(
            select(AIMessage, AIConversation)
            .join(AIConversation, AIConversation.id == AIMessage.conversation_id)
            .where(AIMessage.id == payload.target_id, AIMessage.role == "ASSISTANT")
        ).first()
        owner_id = row[1].owner_user_id if row else ""
        factory_id = row[1].factory_scope if row else ""
    elif payload.target_type == "TASK":
        record = db.get(AITask, payload.target_id)
        owner_id = record.owner_user_id if record else ""
        factory_id = record.factory_scope if record else ""
    else:
        record = db.get(AIActionConfirmation, payload.target_id)
        owner_id = record.user_id if record else ""
        factory_id = record.factory_id if record else ""
    if not owner_id or owner_id != user.id:
        raise _error(404, "AI_FEEDBACK_TARGET_NOT_FOUND", "反馈对象不存在或不可访问")
    if factory_id and factory_id != payload.factory_id:
        raise _error(409, "AI_FEEDBACK_FACTORY_MISMATCH", "反馈对象与当前厂区不一致")


def feedback_data(record: AIFeedback) -> AIFeedbackData:
    return AIFeedbackData(
        id=record.id,
        owner_user_id=record.owner_user_id,
        factory_id=record.factory_id,
        target_type=record.target_type,
        target_id=record.target_id,
        rating=record.rating,
        issue_category=record.issue_category,
        comment=record.comment_text,
        status=record.status,
        reviewed_by=record.reviewed_by,
        review_note=record.review_note,
        eval_suite_id=record.eval_suite_id,
        eval_case_id=record.eval_case_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        reviewed_at=record.reviewed_at,
    )


def create_feedback(
    db: Session,
    *,
    payload: AIFeedbackCreate,
    user: AuthContext,
) -> AIFeedback:
    _ensure_target(db, payload=payload, user=user)
    replay = db.scalar(
        select(AIFeedback).where(
            AIFeedback.owner_user_id == user.id,
            AIFeedback.idempotency_key == payload.idempotency_key,
        )
    )
    if replay is not None:
        if (
            replay.target_type != payload.target_type
            or replay.target_id != payload.target_id
            or replay.rating != payload.rating
            or replay.issue_category != payload.issue_category
            or replay.comment_text != payload.comment
        ):
            raise _error(
                409, "AI_FEEDBACK_REQUEST_CONFLICT", "反馈请求标识已用于其他内容"
            )
        return replay
    existing = db.scalar(
        select(AIFeedback).where(
            AIFeedback.owner_user_id == user.id,
            AIFeedback.target_type == payload.target_type,
            AIFeedback.target_id == payload.target_id,
        )
    )
    if existing is not None:
        if (
            existing.rating == payload.rating
            and existing.issue_category == payload.issue_category
            and existing.comment_text == payload.comment
        ):
            return existing
        raise _error(409, "AI_FEEDBACK_ALREADY_SUBMITTED", "该回复已经提交过反馈")
    now = business_now().isoformat(timespec="seconds")
    record = AIFeedback(
        id=f"aifb-{uuid4().hex}",
        owner_user_id=user.id,
        factory_id=payload.factory_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        rating=payload.rating,
        issue_category=payload.issue_category,
        comment_text=payload.comment,
        status="SUBMITTED",
        idempotency_key=payload.idempotency_key,
        reviewed_by=None,
        review_note="",
        eval_suite_id="",
        eval_case_id="",
        created_at=now,
        updated_at=now,
        reviewed_at="",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(AIFeedback).where(
                AIFeedback.owner_user_id == user.id,
                AIFeedback.target_type == payload.target_type,
                AIFeedback.target_id == payload.target_id,
            )
        )
        if (
            replay is not None
            and replay.rating == payload.rating
            and replay.issue_category == payload.issue_category
            and replay.comment_text == payload.comment
        ):
            return replay
        raise _error(409, "AI_FEEDBACK_CONFLICT", "反馈发生并发冲突") from None
    return record


def review_feedback(
    db: Session,
    *,
    feedback_id: str,
    payload: AIFeedbackReview,
    reviewer: AuthContext,
) -> AIFeedback:
    record = db.scalar(
        select(AIFeedback).where(AIFeedback.id == feedback_id).with_for_update()
    )
    if record is None:
        raise _error(404, "AI_FEEDBACK_NOT_FOUND", "反馈记录不存在")
    if record.status in {"EVAL_CANDIDATE", "DISMISSED"}:
        if (
            record.status == payload.status
            and record.review_note == payload.review_note
            and record.eval_suite_id == payload.eval_suite_id
            and record.eval_case_id == payload.eval_case_id
        ):
            return record
        raise _error(409, "AI_FEEDBACK_REVIEW_FINAL", "反馈终态不能被覆盖")
    now = business_now().isoformat(timespec="seconds")
    record.status = payload.status
    record.reviewed_by = reviewer.id
    record.review_note = payload.review_note
    record.eval_suite_id = payload.eval_suite_id
    record.eval_case_id = payload.eval_case_id
    record.reviewed_at = now
    record.updated_at = now
    db.commit()
    return record


def list_feedback(
    db: Session,
    *,
    owner_user_id: str | None,
    status: str,
    limit: int,
    offset: int,
) -> AIFeedbackPage:
    filters = []
    if owner_user_id:
        filters.append(AIFeedback.owner_user_id == owner_user_id)
    if status:
        filters.append(AIFeedback.status == status)
    total = int(db.scalar(select(func.count(AIFeedback.id)).where(*filters)) or 0)
    records = db.scalars(
        select(AIFeedback)
        .where(*filters)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AIFeedbackPage(
        items=[feedback_data(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )
