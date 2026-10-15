"""Approval notifications use the same read-only scope projection as the inbox."""
import hashlib
import json
from sqlalchemy import select
from app.models.auth import AuthAccessRequest, AuthUser, SystemNotification
from app.services.identity_resolver import stamp, utc_now


def visible(db, actor, change_id, *, actionable=False):
    from app.services.iam_workspace import Projection
    if "system:user_manage" not in actor.permissions:
        return False
    return any(item["source_id"] == change_id and (not actionable or item["raw_status"] == "pending_approval"
        and item["state"] == "actionable") for item in Projection(db, actor, utc_now()).changes())


def close(db, change_id):
    for item in db.scalars(select(SystemNotification).where(SystemNotification.id.startswith("identity-review:" + change_id + ":"))):
        item.status, item.handled_at = "handled", stamp()


def deliver(db, outbox, payload):
    from app.services.auth import build_auth_context
    row = db.get(AuthAccessRequest, payload["change_id"])
    if row is None or row.lifecycle_state != "pending_approval":
        close(db, payload["change_id"])
        return
    targets = []
    for user in db.scalars(select(AuthUser).where(AuthUser.status == "active")):
        if user.id == row.target_user_id == row.requester_user_id:
            continue
        if visible(db, build_auth_context(db, user), row.id, actionable=True):
            targets.append(user.id)
    prefix = "identity-review:" + row.id + ":"
    for item in db.scalars(select(SystemNotification).where(SystemNotification.id.startswith(prefix))):
        if item.target_user_id not in targets:
            item.status, item.handled_at = "handled", stamp()
    for uid in targets:
        nid = prefix + hashlib.sha256(uid.encode()).hexdigest()[:16]
        if db.get(SystemNotification, nid) is None:
            db.add(SystemNotification(id=nid, target_user_id=uid, type="identity_change_submitted",
                title="职位与权限调整待审核", message="请核对人员资料、权限变化及管理范围后办理。",
                payload_json=json.dumps({"change_id": row.id}), created_at=stamp()))
    db.flush()
    return None if targets else "IDENTITY_NO_RECIPIENT"
