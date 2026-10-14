"""Delivery is a projection of the current review, never a workflow decision."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.auth import AuthUser, SystemNotification
from app.models.position_review import PositionReview
from app.services.auth import build_auth_context
from app.services.identity_resolver import stamp
from app.services.position_workbench_read import ensure_item_scope, declaration
from app.services.identity_policy import ensure_change_authority

KINDS = {"position_review_" + kind for kind in ("submitted", "updated", "returned", "applied", "withdrawn", "invalidated")}


def recipients(db, review):
    from app.services.identity_policy import additional_source_scopes
    from app.services.position_reviews import official
    declared, current = declaration(review), official(db, review.user_id)
    scopes = [(declared["org_unit_id"], declared["org_unit_id"], declared["department_code"])]
    if current:
        scopes.append((current["org_unit_id"], current["org_unit_id"], current["department_code"]))
    scopes += [(f, f, d) for f, d in additional_source_scopes(db, [review.user_id]).get(review.user_id, set())]
    result = []
    for user in db.scalars(select(AuthUser).where(AuthUser.status == "active")):
        if user.id == review.user_id:
            continue
        actor = build_auth_context(db, user)
        try:
            ensure_item_scope(db, actor, review)
            ensure_change_authority(db, actor, review.user_id, scopes, [])
        except HTTPException:
            continue
        result.append(user.id)
    return result


def deliver(db, outbox, payload):
    review = db.get(PositionReview, payload["review_id"])
    if review is None:
        raise ValueError("POSITION_REVIEW_MISSING")
    now = stamp()
    prefix = "position-admin:" + review.id + ":"
    existing = list(db.scalars(select(SystemNotification).where(SystemNotification.id.startswith(prefix))))
    if review.status != "pending":
        for item in existing:
            item.status, item.handled_at = "handled", now
    if outbox.kind in {"position_review_submitted", "position_review_updated"}:
        if review.status != "pending":
            return
        targets = recipients(db, review)
        for item in existing:
            if item.target_user_id not in targets:
                item.status, item.handled_at = "handled", now
        if not targets:
            # Kept retryable/diagnosable, without deleting the source task.
            db.flush()
            return "POSITION_NO_RECIPIENT"
        for uid in targets:
            nid = prefix + hashlib.sha256(uid.encode()).hexdigest()[:16]
            item = db.get(SystemNotification, nid)
            if item is None:
                item = SystemNotification(id=nid, target_user_id=uid, type="position_review_submitted", created_at=now)
                db.add(item)
            old = json.loads(item.payload_json or "{}")
            if old.get("revision", 0) >= review.revision:
                continue
            item.title, item.message = "岗位更新待核对", "员工岗位资料已更新，请核对岗位与当前权限。"
            item.payload_json = json.dumps({"review_id": review.id, "position_review_id": review.id, "revision": review.revision,
                "item_key": "position:" + review.id, "purpose": "review"})
            item.status, item.handled_at, item.read_at = "unread", "", ""
    else:
        if payload["revision"] != review.revision:
            return  # Obsolete results must not arrive after a newer submission.
        label = {"returned": "岗位更新需要补充", "applied": "岗位与权限核对已完成", "withdrawn": "岗位更新已撤回", "invalidated": "岗位更新已失效"}[outbox.kind.removeprefix("position_review_")]
        nid = "position-result:" + outbox.id.removeprefix("position-")
        if db.get(SystemNotification, nid) is None:
            db.add(SystemNotification(id=nid, target_user_id=review.user_id, type=outbox.kind, title=label,
                message="请在我的岗位与权限中查看当前资料和处理结果。", created_at=now,
                payload_json=json.dumps({"review_id": review.id, "position_review_id": review.id, "revision": review.revision,
                    "item_key": "position:" + review.id, "purpose": "self"})))
    db.flush()
