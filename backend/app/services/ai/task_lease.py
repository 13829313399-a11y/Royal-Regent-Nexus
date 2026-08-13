from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_task import AITask
from app.schemas.ai.task import AITaskEventType, AITaskState
from app.services.ai.task_events import append_task_event

CLAIMABLE_STATES = (
    AITaskState.CREATED.value,
    AITaskState.UNDERSTOOD.value,
    AITaskState.PLANNED.value,
    AITaskState.RUNNING.value,
    AITaskState.CANCELLING.value,
    AITaskState.RETRY_PENDING.value,
)


class AITaskLeaseError(RuntimeError):
    code = "AI_TASK_LEASE_LOST"


@dataclass(frozen=True, slots=True)
class TaskLease:
    task_id: str
    owner_instance: str
    token: str
    expires_at: datetime


def _text(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _validate_worker_settings(settings: Settings) -> None:
    if (
        settings.ai_task_worker_heartbeat_seconds * 2
        >= settings.ai_task_worker_lease_seconds
    ):
        raise AITaskLeaseError("Worker heartbeat must leave a bounded lease margin")


def claim_next_task(
    db: Session,
    *,
    owner_instance: str,
    settings: Settings,
    now: datetime | None = None,
) -> TaskLease | None:
    _validate_worker_settings(settings)
    if not owner_instance or len(owner_instance) > 128:
        raise AITaskLeaseError("Worker instance id is invalid")
    current = now or business_now()
    current_text = _text(current)
    candidate = db.scalar(
        select(AITask)
        .where(
            AITask.state.in_(CLAIMABLE_STATES),
            or_(AITask.next_attempt_at == "", AITask.next_attempt_at <= current_text),
            or_(AITask.lease_token == "", AITask.lease_expires_at <= current_text),
        )
        .order_by(AITask.updated_at.asc(), AITask.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if candidate is None:
        return None
    expires_at = current + timedelta(seconds=settings.ai_task_worker_lease_seconds)
    token = uuid4().hex
    acquired = db.execute(
        update(AITask)
        .where(
            AITask.id == candidate.id,
            or_(AITask.lease_token == "", AITask.lease_expires_at <= current_text),
        )
        .values(
            lease_owner_instance=owner_instance,
            lease_token=token,
            lease_expires_at=_text(expires_at),
            last_heartbeat_at=current_text,
            next_attempt_at="",
            claim_count=AITask.claim_count + 1,
        )
        .returning(AITask.id)
    ).scalar_one_or_none()
    if acquired is None:
        db.rollback()
        return None
    db.refresh(candidate)
    append_task_event(
        db,
        task=candidate,
        event_type=AITaskEventType.LEASE_CLAIMED,
        actor_type="SYSTEM",
        reason_code="WORKER_LEASE_CLAIMED",
        now=current,
    )
    db.commit()
    return TaskLease(
        task_id=candidate.id,
        owner_instance=owner_instance,
        token=token,
        expires_at=expires_at,
    )


def renew_task_lease(
    db: Session,
    *,
    lease: TaskLease,
    settings: Settings,
    now: datetime | None = None,
) -> TaskLease:
    _validate_worker_settings(settings)
    current = now or business_now()
    expires_at = current + timedelta(seconds=settings.ai_task_worker_lease_seconds)
    updated = db.execute(
        update(AITask)
        .where(
            AITask.id == lease.task_id,
            AITask.lease_owner_instance == lease.owner_instance,
            AITask.lease_token == lease.token,
            AITask.lease_expires_at > _text(current),
        )
        .values(
            lease_expires_at=_text(expires_at),
            last_heartbeat_at=_text(current),
        )
        .returning(AITask.id)
    ).scalar_one_or_none()
    if updated is None:
        db.rollback()
        raise AITaskLeaseError("Worker lease is no longer current")
    db.commit()
    return TaskLease(
        task_id=lease.task_id,
        owner_instance=lease.owner_instance,
        token=lease.token,
        expires_at=expires_at,
    )


def require_live_task_lease(
    db: Session,
    *,
    lease: TaskLease,
    now: datetime | None = None,
) -> AITask:
    current = now or business_now()
    record = db.scalar(
        select(AITask).where(
            AITask.id == lease.task_id,
            AITask.lease_owner_instance == lease.owner_instance,
            AITask.lease_token == lease.token,
            AITask.lease_expires_at > _text(current),
        )
    )
    if record is None:
        raise AITaskLeaseError("Worker lease is no longer current")
    return record


def release_task_lease(
    db: Session,
    *,
    lease: TaskLease,
    reason_code: str,
    next_attempt_at: datetime | None = None,
    now: datetime | None = None,
) -> None:
    current = now or business_now()
    record = require_live_task_lease(db, lease=lease, now=current)
    record.lease_owner_instance = ""
    record.lease_token = ""
    record.lease_expires_at = ""
    record.last_heartbeat_at = ""
    record.next_attempt_at = (
        _text(next_attempt_at) if next_attempt_at is not None else ""
    )
    append_task_event(
        db,
        task=record,
        event_type=(
            AITaskEventType.RETRY_SCHEDULED
            if next_attempt_at is not None
            else AITaskEventType.LEASE_RELEASED
        ),
        actor_type="SYSTEM",
        reason_code=reason_code,
        now=current,
    )
    db.commit()


def clear_owned_lease(
    db: Session,
    *,
    task_id: str,
    owner_instance: str,
    token: str,
) -> bool:
    result = db.execute(
        update(AITask)
        .where(
            and_(
                AITask.id == task_id,
                AITask.lease_owner_instance == owner_instance,
                AITask.lease_token == token,
            )
        )
        .values(
            lease_owner_instance="",
            lease_token="",
            lease_expires_at="",
            last_heartbeat_at="",
        )
    )
    db.commit()
    return bool(result.rowcount)
