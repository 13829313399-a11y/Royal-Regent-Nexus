"""Employee declarations. Public mutations own exactly one transaction."""
import json
from uuid import uuid4
from sqlalchemy import func, inspect, select
from app.core.config import settings
from app.models.auth import AuthPermission, AuthUser, EmployeeProfile
from app.models.identity import IamOrgDepartment, IamOrgUnit, IamOutbox
from app.models.position_review import PositionReview, PositionReviewEvent
from app.services.identity_changes import encoded
from app.services.identity_policy import fail, fresh_actor, lock_mutation
from app.services.identity_resolver import resolve_identity_at, stamp

OPEN = ("pending", "returned")


def schema_available(db):
    return inspect(db.connection()).has_table("position_reviews")


def require_schema(db):
    if not schema_available(db):
        fail("POSITION_SCHEMA_REQUIRED", "岗位工作台需要先完成 20261013_0160 结构迁移", 503)


def writes_enabled():
    return (settings.iam_position_workbench_enabled and settings.iam_identity_writes_enabled
            and settings.authz_mode == "enforce" and settings.authz_writes_enabled)


def require_writes():
    if not writes_enabled():
        fail("WRITES_DISABLED", "当前仅可查看，岗位更新暂不可提交", 403)


def validate_position(db, value):
    org = db.get(IamOrgUnit, value.org_unit_id)
    dept = db.get(IamOrgDepartment, (value.org_unit_id, value.department_code))
    if not org or org.status != "active" or org.kind == "group" or not dept or dept.status != "active":
        fail("INVALID_ORG", "请选择有效组织和部门；集团浏览根不能作为正式岗位", 422)
    return org


def official(db, user_id, identity=None):
    identity = identity or resolve_identity_at(db, user_id)
    profile = db.get(EmployeeProfile, user_id)
    primary = identity["primary_assignment"]
    org = primary["org_unit_id"] if primary else ((profile.primary_org_unit_id or profile.primary_factory_id) if profile else "")
    if not org or not identity["primary_department"]:
        return None
    return {"org_unit_id": org, "department_code": identity["primary_department"], "position": identity["position"]}


def review_out(row):
    return {"id": row.id, "user_id": row.user_id, "employment_epoch": row.employment_epoch,
            "origin": row.origin, "status": row.status, "revision": row.revision,
            "declaration": json.loads(row.declared_snapshot_json),
            "base_official": json.loads(row.base_official_snapshot_json),
            "confirmed_profile": json.loads(row.confirmed_snapshot_json),
            "decision": row.decision or None, "review_comment": row.review_comment,
            "created_at": row.created_at, "updated_at": row.updated_at}


def event_tx(db, row, actor_id, kind, before=None, comment=""):
    db.flush()
    db.add(PositionReviewEvent(id=uuid4().hex, review_id=row.id, revision=row.revision, actor_id=actor_id,
        event_type=kind, before_json=encoded(before), after_json=encoded(review_out(row)),
        comment=comment, created_at=stamp()))


def notify_tx(db, row, kind):
    db.add(IamOutbox(id=f"position-{row.id}-{row.revision}-{kind}", aggregate_id=row.id,
        kind="position_review_" + kind, payload_json=encoded({"review_id": row.id, "revision": row.revision,
        "item_key": "position:" + row.id}), created_at=stamp()))


def invalidate_obsolete_tx(db, user_id=None, actor_id=None):
    """Called under the shared IAM lock, including from lifecycle/worker paths."""
    if not schema_available(db):
        return
    query = select(PositionReview, EmployeeProfile).join(EmployeeProfile, EmployeeProfile.user_id == PositionReview.user_id).where(
        PositionReview.status.in_(OPEN))
    if user_id:
        query = query.where(PositionReview.user_id == user_id)
    for row, profile in db.execute(query):
        if row.employment_epoch == profile.employment_epoch and profile.employment_status != "left":
            continue
        before = review_out(row)
        row.status, row.review_comment = "invalidated", "任职周期已改变，此岗位更新不再适用"
        row.revision += 1
        row.updated_at = stamp()
        event_tx(db, row, actor_id or row.initiator_user_id, "invalidated", before, row.review_comment)
        notify_tx(db, row, "invalidated")


def self_actor(db, actor_id):
    from app.services.internal_members import is_internal
    actor = fresh_actor(db, actor_id)
    if not is_internal(actor):
        fail("ACCOUNT_UNAVAILABLE", "当前身份不可提交内部岗位更新", 403)
    return actor


def open_review(db, actor):
    return db.scalar(select(PositionReview).where(PositionReview.user_id == actor.id,
        PositionReview.employment_epoch == actor.identity["employment_epoch"], PositionReview.status.in_(OPEN)))


def self_profile(db, actor_id):
    require_schema(db)
    actor = self_actor(db, actor_id)
    from app.services.identity_changes import access_matrix
    permissions = {p.code: p.name for p in db.scalars(select(AuthPermission))}
    codes = sorted({key[0] for key in access_matrix(db, actor.id, None)})
    row = open_review(db, actor)
    return {"official_position": official(db, actor.id, actor.identity),
            "open_review": review_out(row) if row else None,
            "effective_permission_summary": [permissions.get(code, code) for code in codes],
            "can_submit": writes_enabled(), "blocked_reason": None if writes_enabled() else "当前仅可查看，岗位更新暂不可提交"}


def self_history(db, actor_id, page, page_size):
    require_schema(db)
    actor = self_actor(db, actor_id)
    query = select(PositionReview).where(PositionReview.user_id == actor.id,
        PositionReview.employment_epoch == actor.identity["employment_epoch"])
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(PositionReview.created_at.desc(), PositionReview.id).offset((page - 1) * page_size).limit(page_size))
    return {"items": [review_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def create_review_tx(db, actor, target, declaration, *, origin="employee", reason=""):
    before = official(db, target.id, target.identity)
    now = stamp()
    row = PositionReview(id=uuid4().hex, user_id=target.id, employment_epoch=target.identity["employment_epoch"],
        origin=origin, initiator_user_id=actor.id, status="pending", revision=1,
        declared_snapshot_json=encoded(declaration.model_dump()), base_official_snapshot_json=encoded(before),
        base_identity_version=target.identity["identity_version"], base_authorization_version=target.authorization_version,
        created_at=now, updated_at=now, last_submitted_at=now)
    db.add(row)
    event_tx(db, row, actor.id, "submitted", comment=reason)
    notify_tx(db, row, "submitted")
    return row


def submit(db, actor_id, payload):
    require_schema(db)
    require_writes()
    lock_mutation(db)
    actor = self_actor(db, actor_id)
    invalidate_obsolete_tx(db, actor.id, actor.id)
    validate_position(db, payload.declaration)
    current = open_review(db, actor)
    declaration = payload.declaration.model_dump()
    if current:
        if current.status == "pending" and json.loads(current.declared_snapshot_json) == declaration:
            db.commit()
            return {"changed": False, "review": review_out(current), "message": "已有相同的岗位更新，无需重复提交"}
        fail("OPEN_REVIEW_EXISTS", "已有待处理岗位更新，请刷新后编辑原申请")
    if {k: declaration[k] for k in ("org_unit_id", "department_code", "position")} == official(db, actor.id, actor.identity):
        db.commit()
        return {"changed": False, "review": None, "message": "岗位与当前确认资料相同，无需提交"}
    row = create_review_tx(db, actor, actor, payload.declaration)
    db.commit()
    return {"changed": True, "review": review_out(row), "message": "岗位更新已提交，管理员确认前权限保持不变。"}


def mutate_self(db, actor_id, review_id, payload, *, withdraw=False):
    require_schema(db)
    require_writes()
    lock_mutation(db)
    actor = self_actor(db, actor_id)
    row = db.get(PositionReview, review_id)
    if not row or row.user_id != actor.id or row.employment_epoch != actor.identity["employment_epoch"]:
        fail("REVIEW_NOT_FOUND", "岗位更新不存在", 404)
    if row.revision != payload.expected_revision:
        fail("REVIEW_REVISION_CONFLICT", "岗位更新已变化，请刷新后重试")
    if row.status not in OPEN:
        fail("ALREADY_HANDLED", "该岗位更新已处理，不能再次修改")
    before = review_out(row)
    if withdraw:
        kind, row.status = "withdrawn", "withdrawn"
    else:
        validate_position(db, payload.declaration)
        declaration = encoded(payload.declaration.model_dump())
        if row.status == "pending" and declaration == row.declared_snapshot_json:
            return {"changed": False, "review": before, "message": "没有新的修改"}
        kind = "resubmitted" if row.status == "returned" else "edited"
        row.declared_snapshot_json = declaration
        row.status = "pending"
        row.last_submitted_at = stamp()
    row.revision += 1
    row.updated_at = stamp()
    event_tx(db, row, actor.id, kind, before)
    notify_tx(db, row, "withdrawn" if withdraw else "updated")
    db.commit()
    return {"changed": True, "review": review_out(row),
            "message": "岗位更新已撤回，权限没有改变。" if withdraw else "岗位更新已提交，管理员确认前权限保持不变。"}
