"""Legacy read API overlay: never mutate the shared notification row."""
import json
from sqlalchemy import select
from fastapi import HTTPException
from app.models.work_center import WorkCenterUserState as State
from app.services.work_center.service import context, now


def canonical_id(source, notification):
    """Only map unambiguous event/one-request identities; never guess a new cycle."""
    if source == "molding" and notification.event_type in {"生产开始", "生产完成回传", "生产完成撤回", "生产开始撤回", "生产派厂变更"}:
        return f"molding:{notification.order_id}:info:{notification.id}:1"
    if source == "system":
        if notification.type == "identity_changed": return f"identity:{notification.id}:identity_changed:1"
        try: payload = json.loads(notification.payload_json or "{}")
        except (ValueError, TypeError): return None
        if notification.type == "user_registration" and payload.get("registration_request_id"):
            return f"account_requests:{payload['registration_request_id']}:registration:1"
        if notification.type == "password_reset" and payload.get("password_reset_request_id"):
            return f"account_requests:{payload['password_reset_request_id']}:password_reset:1"
        if notification.type == "internal_quote" and payload.get("event") in {"customer_price_artifact_available", "final_release_approved", "whole_quote_approved"}:
            return f"internal_quote:{payload.get('quote_id')}:info:{notification.id}:1"
    return None


def personal_read(db, user, source, notification_id):
    from app.services.transaction_lock import lock_transaction
    epoch, _ = context(db, user)
    entry_id = f"legacy-{source}:{notification_id}"
    lock_transaction(db, "work-center-state", f"{user.id}:{epoch}:{entry_id}")
    row = db.get(State, (user.id, epoch, entry_id))
    if row is None:
        row = State(user_id=user.id, employment_epoch=epoch, entry_id=entry_id, read_version=1,
                    read_at=now(), state_version=1)
        db.add(row)
    db.flush()
    from app.models.auth import SystemNotification
    from app.models.molding_sample import MoldingSampleNotification
    from app.schemas.work_center import UserStatePatch
    from app.services.work_center.service import detail, patch_state
    notification = db.get(SystemNotification if source == "system" else MoldingSampleNotification, notification_id)
    canonical = canonical_id(source, notification) if notification else None
    if canonical:
        try:
            current = detail(db, user, canonical)
            patch_state(db, user, canonical, UserStatePatch(observed_content_version=current["content_version"]))
        except HTTPException as error:
            if error.status_code != 404: raise


def read_ids(db, user, source, ids):
    epoch, _ = context(db, user)
    prefix = f"legacy-{source}:"
    return {value[len(prefix):] for value in db.scalars(select(State.entry_id).where(State.user_id == user.id,
        State.employment_epoch == epoch, State.read_version > 0, State.entry_id.in_([prefix + i for i in ids])))}


def molding_out(db, user, notifications):
    from app.schemas.molding_sample import MoldingSampleNotificationOut
    read = read_ids(db, user, "molding", [n.id for n in notifications])
    read.update(canonical_reads(db, user, "molding", notifications))
    result = []
    for row in notifications:
        item = MoldingSampleNotificationOut.model_validate(row)
        if item.status != "已处理":
            item.status = "已读" if item.id in read else "未读"
            if item.id not in read: item.read_at = ""
        result.append(item)
    return result


def system_out(db, user, notifications):
    from app.services.system import notification_to_out
    read = read_ids(db, user, "system", [n.id for n in notifications])
    read.update(canonical_reads(db, user, "system", notifications))
    result = []
    for row in notifications:
        item = notification_to_out(row)
        if item.status != "handled":
            item.status = "read" if item.id in read else "unread"
            if item.id not in read: item.read_at = ""
        result.append(item)
    return result


def canonical_reads(db, user, source, notifications):
    from app.models.work_center import WorkCenterEntry as Entry
    epoch, _ = context(db, user)
    mapping = {canonical_id(source, n): n.id for n in notifications if canonical_id(source, n)}
    ids = db.scalars(select(State.entry_id).outerjoin(Entry, Entry.id == State.entry_id).where(
        State.user_id == user.id, State.employment_epoch == epoch, State.entry_id.in_(mapping),
        State.read_version >= 1, (Entry.id.is_(None) | (State.read_version >= Entry.content_version))))
    return {mapping[i] for i in ids}
