from datetime import datetime
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.auth import AuthAccessRequest, AuthRoleBindingMetadata, AuthUser, AuthUserPermissionOverride, AuthUserRole, EmployeeProfile
from app.models.identity import EmployeeAssignment, IamHandoverItem
from app.schemas.identity import AccessExplain, BatchCommit, DelegationUpdate, DraftUpdate, HandoverReassign, IdentityChange, IdentityCommit, IdentityDecision
from app.services.auth import AuthContext, build_auth_context, get_current_user
from app.services import identity_changes as changes
from app.services.identity_catalog import catalog
from app.services.identity_policy import ensure_reader, fail, fresh_actor, is_group_manager, readable_scopes
from app.services.identity_resolver import identity_columns, resolve_identity_at, stamp

router = APIRouter(prefix="/api")


@router.get("/auth/organization-catalog")
def registration_catalog(db: Session = Depends(get_db)):
    from app.core.config import settings
    result = catalog(db)
    return {"organizations": [{"id": o["id"], "name": o["name"], "factory_id": o["factory_id"],
                                "departments": o["departments"]} for o in result["organizations"]
                              if o["status"] == "active" and (o["kind"] == "factory" or
                                 (o["kind"] == "functional_unit" and settings.iam_identity_writes_enabled))]}


@router.get("/system/organization-catalog")
def organization_catalog(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    ensure_reader(db, user)
    result = catalog(db)
    result["can_manage_delegations"] = is_group_manager(user)
    if not is_group_manager(user):
        from app.services.iam import _manager_scopes
        scopes = _manager_scopes(db, user.id)
        result["organizations"] = [o for o in result["organizations"] if any(f in {"*", o["id"]} for f, _ in scopes)]
    return result


@router.get("/iam/users/{user_id}/delegations")
def read_delegations(user_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_delegation import list_delegations
    return {"items": list_delegations(db, user, user_id)}


@router.put("/iam/users/{user_id}/delegations/{delegation_id}")
def update_delegation(user_id: str, delegation_id: str, payload: DelegationUpdate,
                      db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_delegation import save
    return save(db, user.id, user_id, delegation_id, payload)


@router.post("/iam/identity-batches/commit")
def batch_commit(payload: BatchCommit, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    results = []
    for item in payload.items:
        try:
            result = changes.commit_change(db, user.id, item.change_id, item.commit, item.idempotency_key)
            results.append({"change_id": item.change_id, "status": 200, "result": result})
        except HTTPException as exc:
            db.rollback()
            results.append({"change_id": item.change_id, "status": exc.status_code, "error": exc.detail})
        except Exception:
            db.rollback()
            logging.getLogger(__name__).exception("Identity batch item failed: %s", item.change_id)
            results.append({"change_id": item.change_id, "status": 500, "error": {"code": "ITEM_FAILED", "message": "此项办理失败，可使用原幂等键重试"}})
    return {"items": results}


@router.get("/system/people")
def people(q: str = "", org_unit_id: str = "", status: str = "", page: int = Query(1, ge=1),
           page_size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    ensure_reader(db, user)
    factory, department, title, org = identity_columns(include_org=True)
    query = select(AuthUser, EmployeeProfile, factory.label("factory"), department.label("department"), title.label("title"), org.label("org")).outerjoin(EmployeeProfile)
    scopes = readable_scopes(db, user)
    if is_group_manager(user):
        scopes.extend([("*", "*"), ("*", "system")])
    primary_visible = or_(*[(func.coalesce(org, "") == f) & (func.coalesce(department, "") == d) for f, d in scopes])
    assignment_visible = or_(*[(EmployeeAssignment.org_unit_id == f) & (EmployeeAssignment.department_code == d) for f, d in scopes])
    has_hidden_assignment = exists(select(EmployeeAssignment.id).where(
        EmployeeAssignment.user_id == AuthUser.id, EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
        EmployeeAssignment.lifecycle_state == "approved", or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp()),
        ~assignment_visible))
    has_visible_assignment = exists(select(EmployeeAssignment.id).where(
        EmployeeAssignment.user_id == AuthUser.id, EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
        EmployeeAssignment.lifecycle_state == "approved", or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp()), assignment_visible))
    query = query.where(~has_hidden_assignment, or_(primary_visible, has_visible_assignment))
    if q.strip():
        query = query.where(or_(AuthUser.display_name.contains(q.strip(), autoescape=True), AuthUser.username.contains(q.strip(), autoescape=True)))
    if status:
        query = query.where(EmployeeProfile.employment_status == "left" if status == "left" else AuthUser.status == status)
    if org_unit_id:
        query = query.where(org == org_unit_id)
    from app.services.identity_policy import additional_source_scopes
    from app.services.auth import can
    candidates = query.with_only_columns(AuthUser.id).order_by(None)
    source_scopes = additional_source_scopes(db, candidates)
    hidden = [uid for uid, required in source_scopes.items()
              if any(not can(user, "system:user_manage", f, d) for f, d in required)]
    if hidden:
        query = query.where(AuthUser.id.not_in(hidden))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuthUser.display_name, AuthUser.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [{"id": u.id, "display_name": u.display_name, "username": u.username, "status": u.status,
                       "primary_org_unit_id": o or "", "primary_factory_id": f or "", "primary_department": d or "", "position": t or "",
                       "identity_mode": p.identity_mode if p else "legacy", "employment_status": p.employment_status if p else "unconfirmed",
                       "identity_version": p.identity_version if p else 0} for u, p, f, d, t, o in rows]}


@router.get("/system/users/{user_id}/identity")
def identity(user_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    ensure_reader(db, user, user_id)
    target = db.get(AuthUser, user_id)
    if not target:
        fail("USER_NOT_FOUND", "人员不存在", 404)
    from app.services.iam import _overrides_out, _role_bindings_out
    from app.services.identity_handover import assess
    result = resolve_identity_at(db, user_id)
    context = build_auth_context(db, target)
    return {**result, "id": user_id, "display_name": target.display_name, "status": target.status,
            "authorization_version": context.authorization_version, "role_bindings": [b.model_dump() for b in _role_bindings_out(db, user_id)],
            "overrides": [o.model_dump() for o in _overrides_out(db, user_id)], "handover": assess(db, user_id)}


@router.get("/system/users/{user_id}/assignments")
def assignments(user_id: str, at: datetime | None = None, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    ensure_reader(db, user, user_id)
    return resolve_identity_at(db, user_id, at)["assignments"]


@router.post("/iam/identity-changes")
def create_change(payload: IdentityChange, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.save_draft(db, user.id, payload)


@router.patch("/iam/identity-changes/{change_id}")
def edit_change(change_id: str, payload: DraftUpdate, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.save_draft(db, user.id, payload.change, change_id=change_id, expected_revision=payload.expected_request_revision)


@router.get("/iam/identity-changes")
def list_changes(state: str = "", target_user_id: str = "", page: int = Query(1, ge=1),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    ensure_reader(db, user)
    query = select(AuthAccessRequest).where(AuthAccessRequest.request_type.like("identity:%"))
    if not is_group_manager(user):
        query = query.where(AuthAccessRequest.requester_user_id == user.id)
    if target_user_id:
        ensure_reader(db, user, target_user_id)
        query = query.where(AuthAccessRequest.target_user_id == target_user_id)
    if state == "applied":
        query = query.where(or_(AuthAccessRequest.lifecycle_state == "applied", and_(AuthAccessRequest.lifecycle_state == "scheduled", AuthAccessRequest.effective_at <= stamp())))
    elif state == "scheduled":
        query = query.where(AuthAccessRequest.lifecycle_state == "scheduled", AuthAccessRequest.effective_at > stamp())
    elif state:
        query = query.where(AuthAccessRequest.lifecycle_state == state)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {"total": total, "items": [changes.result_out(r) for r in db.scalars(query.order_by(AuthAccessRequest.created_at.desc()).offset((page - 1) * 30).limit(30))]}


@router.get("/iam/identity-changes/{change_id}")
def read_change(change_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    row = changes.load_change(db, change_id)
    ensure_reader(db, user, row.target_user_id)
    return changes.result_out(row)


@router.post("/iam/identity-changes/{change_id}/preview")
def preview_change(change_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.preview_change(db, user.id, change_id)


@router.post("/iam/identity-changes/{change_id}/commit")
def commit_change(change_id: str, payload: IdentityCommit, idempotency_key: str = Header(default=""),
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.commit_change(db, user.id, change_id, payload, idempotency_key)


@router.post("/iam/identity-changes/{change_id}/approve")
def approve_change(change_id: str, payload: IdentityCommit, idempotency_key: str = Header(default=""),
                   db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.commit_change(db, user.id, change_id, payload, idempotency_key, approving=True)


@router.post("/iam/identity-changes/{change_id}/cancel")
def cancel_change(change_id: str, payload: IdentityDecision, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.cancel_or_reject(db, user.id, change_id, payload)


@router.post("/iam/identity-changes/{change_id}/reject")
def reject_change(change_id: str, payload: IdentityDecision, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.cancel_or_reject(db, user.id, change_id, payload, reject=True)


@router.get("/iam/identity-changes/{change_id}/handover-items")
def handovers(change_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_handover import COVERAGE, item_out
    row = changes.load_change(db, change_id)
    ensure_reader(db, user, row.target_user_id)
    return {"items": [item_out(i) for i in db.scalars(select(IamHandoverItem).where(IamHandoverItem.change_request_id == change_id))], "coverage": COVERAGE}


@router.post("/iam/handover-items/{item_id}/reassign")
def handover_reassign(item_id: str, payload: HandoverReassign, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_handover import reassign
    return reassign(db, user.id, item_id, payload)


@router.get("/iam/handover-items/{item_id}/candidates")
def handover_candidates(item_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_handover import candidates
    item = db.get(IamHandoverItem, item_id)
    if not item:
        fail("HANDOVER_NOT_FOUND", "交接项不存在", 404)
    return {"items": candidates(db, user, item)}


@router.post("/iam/identity-changes/{change_id}/handover-refresh")
def refresh_handover(change_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_policy import lock_mutation, require_writes
    from app.services.identity_handover import reconcile
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, user.id)
    row = changes.load_change(db, change_id)
    ensure_reader(db, actor, row.target_user_id)
    if not is_group_manager(actor):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "需有权管理员重新评估", 403)
    if changes.result_out(row)["state"] not in {"applied", "scheduled"}:
        fail("CHANGE_STATE_CONFLICT", "请先完成任职变更")
    reconcile(db, row)
    db.commit()
    return handovers(change_id, db, actor)


@router.post("/iam/identity-notifications/retry")
def retry_notifications(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_policy import lock_mutation, require_writes
    from app.services.identity_outbox import drain
    require_writes()
    lock_mutation(db)
    if not is_group_manager(fresh_actor(db, user.id)):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "需要集团管理员处理通知", 403)
    return drain(db)


@router.post("/iam/users/{user_id}/access/explain")
def explain(user_id: str, payload: AccessExplain, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.auth import authorization_decision
    ensure_reader(db, user, user_id)
    target = db.get(AuthUser, user_id)
    if not target:
        fail("USER_NOT_FOUND", "人员不存在", 404)
    context = build_auth_context(db, target, at=payload.at)
    allowed, source_type, source_ids, reason = authorization_decision(context, payload.permission_code, payload.factory_id, payload.department, at=payload.at)
    return {"allowed": allowed, "source_type": source_type, "source_ids": source_ids, "reason": reason,
            "identity": context.identity, "limitation": "按当前账号状态、当前在职批次及已保存授权解释指定时点；不提供离职前账号状态或历史业务状态的完整回放"}
