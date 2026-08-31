from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_schedule import InjectionScheduleAuditEvent
from app.services.auth import AuthContext


def write_audit_event(
    db: Session,
    *,
    factory_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    entity_version: int,
    actor: AuthContext,
    reason: str = "",
    before: object | None = None,
    after: object | None = None,
) -> InjectionScheduleAuditEvent:
    sequence = (
        db.scalar(
            select(func.max(InjectionScheduleAuditEvent.event_sequence)).where(
                InjectionScheduleAuditEvent.factory_id == factory_id
            )
        )
        or 0
    ) + 1
    event = InjectionScheduleAuditEvent(
        id=f"is-audit-{uuid4().hex}",
        factory_id=factory_id,
        event_sequence=sequence,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_version=entity_version,
        reason=reason.strip(),
        before_json=json.dumps(before or {}, ensure_ascii=False, default=str),
        after_json=json.dumps(after or {}, ensure_ascii=False, default=str),
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        created_at=business_now().isoformat(timespec="seconds"),
    )
    db.add(event)
    db.flush()
    return event
