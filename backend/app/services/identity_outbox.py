"""Idempotent local delivery; never used to decide an authorization boundary."""
import json
from datetime import timedelta
from sqlalchemy import select
from app.models.auth import SystemNotification
from app.models.identity import IamOutbox
from app.services.identity_policy import lock_mutation
from app.services.identity_resolver import stamp, utc_now


def reconcile_due(db):
    from app.models.auth import AuthAccessRequest, EmployeeProfile
    from app.models.identity import IamHandoverItem
    from app.services.identity_handover import reconcile
    from app.services.identity_resolver import resolve_identity_at
    lock_mutation(db)
    now = stamp()
    rows = list(db.scalars(select(AuthAccessRequest).where(AuthAccessRequest.request_type.like("identity:%"),
        AuthAccessRequest.lifecycle_state == "scheduled", AuthAccessRequest.effective_at <= now)))
    for row in rows:
        identity = resolve_identity_at(db, row.target_user_id)
        profile = db.get(EmployeeProfile, row.target_user_id)
        primary = identity["primary_assignment"]
        if profile and profile.identity_mode == "v2":
            profile.primary_assignment_id = primary["id"] if primary else None
            profile.primary_org_unit_id = primary["org_unit_id"] if primary else ""
            profile.primary_factory_id = identity["primary_factory_id"]
            profile.primary_department = identity["primary_department"]
            profile.position = identity["position"]
        row.lifecycle_state = "applied"
        reconcile(db, row)
    # Completed handovers still need their unfinished business holder checked.
    ids = set(db.scalars(select(IamHandoverItem.change_request_id).where(
        IamHandoverItem.status.in_(["pending", "completed", "manual_review_required"]))))
    for change_id in ids:
        row = db.get(AuthAccessRequest, change_id)
        if row and row.lifecycle_state == "applied":
            reconcile(db, row)
    db.commit()


async def worker():
    import asyncio
    import logging
    from app.db import SessionLocal
    while True:
        await asyncio.sleep(30)
        def run():
            with SessionLocal() as db:
                try:
                    reconcile_due(db)
                    drain(db)
                except Exception:
                    db.rollback()
                    logging.getLogger(__name__).warning("identity_background_retry_required", exc_info=True)
        await asyncio.to_thread(run)


def drain(db, limit=50):
    lock_mutation(db)
    now = stamp()
    rows = list(db.scalars(select(IamOutbox).where(IamOutbox.status.in_(["pending", "retry"]),
                     IamOutbox.next_attempt_at <= now).order_by(IamOutbox.created_at).limit(limit)))
    delivered = 0
    for row in rows:
        row.attempts += 1
        try:
            with db.begin_nested():
                payload = json.loads(row.payload_json)
                notification_id = "iam:" + row.id
                if db.get(SystemNotification, notification_id) is None:
                    db.add(SystemNotification(id=notification_id, target_user_id=payload["user_id"],
                        type="identity_changed", title="任职与授权已更新", message="请刷新当前页面查看正式任职及可用操作。",
                        payload_json=json.dumps({"change_id": payload["change_id"]}), created_at=now))
                    db.flush()
            row.status = "delivered"
            row.last_error = ""
            delivered += 1
        except Exception:
            row.status = "retry"
            row.last_error = "NOTIFICATION_DELIVERY_FAILED"
            row.next_attempt_at = stamp(utc_now() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 6))))
    db.commit()
    return {"processed": len(rows), "delivered": delivered, "retry": len(rows) - delivered}
