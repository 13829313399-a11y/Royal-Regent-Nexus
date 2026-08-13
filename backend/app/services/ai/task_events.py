from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.task import (
    AIArtifactReference,
    AITaskEventData,
    AITaskEventPage,
    AITaskEventType,
    AITaskState,
    AITaskStepState,
)


class AITaskEventError(ValueError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def append_task_event(
    db: Session,
    *,
    task: AITask,
    event_type: AITaskEventType,
    actor_type: str,
    actor_user_id: str = "",
    step_id: str | None = None,
    transition_from: str = "",
    transition_to: str = "",
    reason_code: str = "",
    evidence: tuple[AIEvidenceReferenceV1, ...] = (),
    artifacts: tuple[AIArtifactReference, ...] = (),
    now: datetime | None = None,
) -> AITaskEvent:
    if actor_type not in {"USER", "SYSTEM"}:
        raise AITaskEventError("Task Event actor type is invalid")
    if actor_type == "USER" and not actor_user_id:
        raise AITaskEventError("User Task Event requires an actor id")
    if step_id is not None:
        owned_step = db.scalar(
            select(AITaskStep.id).where(
                AITaskStep.id == step_id,
                AITaskStep.task_id == task.id,
            )
        )
        if owned_step is None:
            raise AITaskEventError("Task Event step is outside the Task")
    if len(evidence) > 16 or len(artifacts) > 16:
        raise AITaskEventError("Task Event references exceed the bounded limit")

    next_value = db.execute(
        update(AITask)
        .where(AITask.id == task.id)
        .values(next_event_sequence=AITask.next_event_sequence + 1)
        .returning(AITask.next_event_sequence)
    ).scalar_one_or_none()
    if next_value is None:
        raise AITaskEventError("Task no longer exists")
    sequence = int(next_value) - 1
    task.next_event_sequence = int(next_value)
    created = (now or business_now()).isoformat(timespec="seconds")
    event = AITaskEvent(
        id=f"aitev-{uuid4().hex}",
        task_id=task.id,
        step_id=step_id,
        sequence=sequence,
        event_type=event_type.value,
        actor_type=actor_type,
        actor_user_id=actor_user_id if actor_type == "USER" else "",
        transition_from=transition_from,
        transition_to=transition_to,
        reason_code=reason_code,
        evidence_json=_canonical_json(
            [item.model_dump(mode="json") for item in evidence]
        ),
        artifact_refs_json=_canonical_json(
            [item.model_dump(mode="json") for item in artifacts]
        ),
        created_at=created,
    )
    db.add(event)
    db.flush()
    return event


def task_event_data(record: AITaskEvent) -> AITaskEventData:
    try:
        evidence_raw = json.loads(record.evidence_json)
        artifacts_raw = json.loads(record.artifact_refs_json)
        if not isinstance(evidence_raw, list) or not isinstance(artifacts_raw, list):
            raise TypeError("Task Event references must be lists")
        evidence = tuple(
            AIEvidenceReferenceV1.model_validate(item) for item in evidence_raw
        )
        artifacts = tuple(
            AIArtifactReference.model_validate(item) for item in artifacts_raw
        )

        def transition_state(value: str):
            if not value:
                return None
            try:
                return AITaskState(value)
            except ValueError:
                return AITaskStepState(value)

        transition_from = transition_state(record.transition_from)
        transition_to = transition_state(record.transition_to)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AITaskEventError("Task Event metadata is corrupt") from exc
    return AITaskEventData(
        id=record.id,
        task_id=record.task_id,
        step_id=record.step_id,
        sequence=record.sequence,
        event_type=AITaskEventType(record.event_type),
        actor_type=record.actor_type,
        transition_from=transition_from,
        transition_to=transition_to,
        reason_code=record.reason_code,
        evidence=evidence,
        artifacts=artifacts,
        created_at=datetime.fromisoformat(record.created_at),
    )


def read_task_events(
    db: Session,
    *,
    task_id: str,
    after: int = 0,
    limit: int = 100,
) -> AITaskEventPage:
    if after < 0 or not 1 <= limit <= 100:
        raise AITaskEventError("Task Event cursor is invalid")
    records = list(
        db.scalars(
            select(AITaskEvent)
            .where(AITaskEvent.task_id == task_id, AITaskEvent.sequence > after)
            .order_by(AITaskEvent.sequence.asc())
            .limit(limit + 1)
        ).all()
    )
    has_more = len(records) > limit
    selected = records[:limit]
    return AITaskEventPage(
        items=tuple(task_event_data(item) for item in selected),
        next_after=selected[-1].sequence if has_more and selected else None,
    )
