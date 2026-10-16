"""Scope-aware read adapters for registration and position workflow sources."""
import json
from collections import defaultdict
from sqlalchemy import func, literal, or_, select, union_all
from app.core.time import serialize_process_local_timestamp
from app.models.auth import (AuthPermission, AuthRegistrationRequest, AuthRole, AuthRoleBindingMetadata,
    AuthUser, AuthUserRole, AuthUserPermissionOverride, EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamRoleVersion, IamOutbox
from app.models.position_review import PositionReview
from app.services.auth import can
from app.services.iam_management_scopes import complete_scopes
from app.services.identity_changes import digest
from app.services.identity_policy import additional_source_scopes, ensure_reader, fail
from app.services.identity_resolver import identity_columns, instant, resolve_identity_at, stamp, utc_now
from app.services import position_reviews as reviews


def revision(row):
    if isinstance(row, PositionReview):
        return f"position:{row.revision}"
    # Includes every source field used by the adapter. Independent of timestamp precision.
    return digest({c.name: getattr(row, c.name) for c in AuthRegistrationRequest.__table__.columns})


def declaration(row):
    if isinstance(row, PositionReview):
        return json.loads(row.declared_snapshot_json)
    return {"org_unit_id": row.org_unit_id or row.factory_id, "department_code": row.department,
            "position": row.position, "note": ""}


def allowed_scope(actor, org, department):
    return all(can(actor, code, org or "*", department or "*")
               for code in ("system:user_manage", "system:access_manage"))


def provisional_registration_users(db):
    # Rejected applicants may resubmit elsewhere while their unconfirmed legacy
    # profile still holds an earlier declaration. It is not a formal assignment.
    formal = select(EmployeeAssignment.id).where(EmployeeAssignment.user_id == AuthUser.id,
        EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
        EmployeeAssignment.lifecycle_state == "approved",
        or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp())).exists()
    return set(db.scalars(select(AuthUser.id).join(EmployeeProfile).where(AuthUser.status == "pending",
        EmployeeProfile.identity_mode == "legacy", EmployeeProfile.confirmation_status == "pending", ~formal)))


def ensure_item_scope(db, actor, row, *, permissions=("system:user_manage", "system:access_manage")):
    ensure_reader(db, actor)
    # Historical registrations expose current identity as well as their original
    # declaration, so they require the same complete person scope as reviews.
    provisional = not isinstance(row, PositionReview) and row.status == "pending" and row.user_id in provisional_registration_users(db)
    if not provisional:
        ensure_reader(db, actor, row.user_id)
    identity = resolve_identity_at(db, row.user_id)
    scopes = [(a["factory_id"] or a["org_unit_id"], a["department_code"]) for a in identity["assignments"]
              if a["state"] in {"current", "scheduled"} and a["employment_epoch"] == identity["employment_epoch"]]
    current = None if provisional else reviews.official(db, row.user_id, identity)
    if current:
        scopes.append((current["org_unit_id"], current["department_code"]))
    scopes += list(additional_source_scopes(db, [row.user_id]).get(row.user_id, set()))
    declared = declaration(row)
    scopes.append((declared["org_unit_id"], declared["department_code"]))
    if any(not all(can(actor, code, org or "*", dept or "*") for code in permissions)
           for org, dept in complete_scopes(scopes)):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "来源和申报岗位超出当前完整管理范围", 403)


def load_item(db, actor, item_key, expected=None, *, pending=False):
    reviews.require_schema(db)
    kind, sep, source_id = item_key.partition(":")
    if not sep or kind not in {"position", "registration"} or not source_id or "/" in source_id:
        fail("ITEM_NOT_FOUND", "办理事项不存在", 404)
    row = db.get(PositionReview if kind == "position" else AuthRegistrationRequest, source_id)
    if not row:
        fail("ITEM_NOT_FOUND", "办理事项不存在", 404)
    ensure_item_scope(db, actor, row)
    if pending and row.status != "pending":
        fail("ALREADY_HANDLED", "该事项已经处理，请刷新查看最新结果")
    if expected is not None and revision(row) != expected:
        fail("REVIEW_REVISION_CONFLICT", "申报内容已更新，请读取最新内容后重新核对")
    return row


def visible_user_ids(db, actor, *, permissions=("system:user_manage", "system:access_manage")):
    """Bulk provenance filtering; no per-person context/matrix queries."""
    factory, department, title, org = identity_columns(include_org=True)
    rows = db.execute(select(AuthUser.id, factory, department, org).outerjoin(EmployeeProfile)).all()
    scopes = defaultdict(set)
    assignments = db.execute(select(EmployeeAssignment, IamOrgUnit).join(IamOrgUnit)
        .join(EmployeeProfile, EmployeeProfile.user_id == EmployeeAssignment.user_id)
        .where(EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
               EmployeeAssignment.lifecycle_state == "approved",
               or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp())))
    for a, o in assignments:
        scopes[a.user_id].add((o.legacy_factory_id or o.id, a.department_code))
    for uid, f, d, o in rows:
        if o or f or not scopes[uid]:
            scopes[uid].add((o or f or "*", d or "*"))
    for uid, extra in additional_source_scopes(db).items():
        scopes[uid].update(extra)
    return [uid for uid, required in scopes.items() if all(
        can(actor, code, f, d) for f, d in complete_scopes(required) for code in permissions)]


def visible_registration_ids(db, actor, *, permissions=("system:user_manage",)):
    """Registration scope before counts/paging, including independent grants."""
    visible = set(visible_user_ids(db, actor, permissions=permissions))
    provisional = provisional_registration_users(db)
    extra = additional_source_scopes(db)
    result = []
    for rid, uid, org, factory, dept, state in db.execute(select(AuthRegistrationRequest.id,
            AuthRegistrationRequest.user_id, AuthRegistrationRequest.org_unit_id, AuthRegistrationRequest.factory_id,
            AuthRegistrationRequest.department, AuthRegistrationRequest.status)):
        if uid not in visible and not (state == "pending" and uid in provisional): continue
        required = complete_scopes({(org or factory or "*", dept or "*"), *extra.get(uid, set())})
        if all(can(actor, code, f, d) for f, d in required for code in permissions): result.append(rid)
    return result


def item_out(db, row, user=None):
    is_position = isinstance(row, PositionReview)
    user = user or db.get(AuthUser, row.user_id)
    actions = ["inspect_advanced"]
    if row.status == "pending" and reviews.writes_enabled():
        actions = ["preview", "commit", "return_position" if is_position else "reject_registration", *actions]
    return {"item_key": ("position:" if is_position else "registration:") + row.id,
        "kind": "position" if is_position else "registration", "origin": row.origin if is_position else "employee",
        "user": {"id": user.id, "display_name": user.display_name, "username": user.username},
        "source_revision": revision(row), "status": row.status,
        "before": json.loads(row.base_official_snapshot_json) if is_position else None,
        "declaration": declaration(row),
        "created_at": row.created_at if is_position else serialize_process_local_timestamp(row.created_at),
        "updated_at": row.updated_at if is_position else serialize_process_local_timestamp(row.updated_at),
        "available_actions": actions}


def queue(db, actor, *, page=1, page_size=30, q="", status="pending", kind="", org_unit_id=""):
    from app.services.work_center.service import Epoch
    reviews.require_schema(db)
    ensure_reader(db, actor)
    visible = set(visible_user_ids(db, actor))
    # JSON source fields are filtered in a bounded-column read before UNION count/paging.
    # No front-end concatenation or first-N truncation; never expose hidden totals.
    position_ids = []
    for rid, uid, raw in db.execute(select(PositionReview.id, PositionReview.user_id, PositionReview.declared_snapshot_json)
                                   .where(PositionReview.user_id.in_(visible))):
        data = json.loads(raw)
        if allowed_scope(actor, data["org_unit_id"], data["department_code"]) and (not org_unit_id or data["org_unit_id"] == org_unit_id):
            position_ids.append(rid)
    extra = additional_source_scopes(db)
    provisional = provisional_registration_users(db)
    registration_ids = []
    for rid, uid, org, factory, dept, state in db.execute(select(AuthRegistrationRequest.id, AuthRegistrationRequest.user_id,
            AuthRegistrationRequest.org_unit_id, AuthRegistrationRequest.factory_id, AuthRegistrationRequest.department, AuthRegistrationRequest.status)):
        if ((uid in visible or (state == "pending" and uid in provisional)) and allowed_scope(actor, org or factory, dept) and (not org_unit_id or (org or factory) == org_unit_id)
                and all(allowed_scope(actor, f, d) for f, d in complete_scopes(extra.get(uid, set())))):
            registration_ids.append(rid)
    pos = select(literal("position").label("kind"), PositionReview.id.label("id"), PositionReview.user_id.label("user_id"),
        PositionReview.created_at.label("created_at"), PositionReview.status.label("status")).where(PositionReview.id.in_(position_ids))
    reg = select(literal("registration").label("kind"), AuthRegistrationRequest.id.label("id"), AuthRegistrationRequest.user_id.label("user_id"),
        AuthRegistrationRequest.created_at.label("created_at"), AuthRegistrationRequest.status.label("status")).where(AuthRegistrationRequest.id.in_(registration_ids))
    sources = union_all(pos, reg).subquery()
    query = select(sources).join(AuthUser, AuthUser.id == sources.c.user_id)
    actionable = db.scalar(select(func.count()).select_from(sources).where(sources.c.status == "pending"))
    if status == "history":
        query = query.where(sources.c.status != "pending")
    elif status:
        query = query.where(sources.c.status == status)
    if kind:
        query = query.where(sources.c.kind == kind)
    if q.strip():
        query = query.where(or_(AuthUser.display_name.contains(q.strip(), autoescape=True), AuthUser.username.contains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    keys = db.execute(query.order_by(Epoch(sources.c.created_at), sources.c.id, sources.c.kind)
                      .offset((page - 1) * page_size).limit(page_size)).mappings().all()
    positions = {r.id: r for r in db.scalars(select(PositionReview).where(PositionReview.id.in_([k["id"] for k in keys if k["kind"] == "position"])))}
    registrations = {r.id: r for r in db.scalars(select(AuthRegistrationRequest).where(AuthRegistrationRequest.id.in_([k["id"] for k in keys if k["kind"] == "registration"])))}
    users = {u.id: u for u in db.scalars(select(AuthUser).where(AuthUser.id.in_([k["user_id"] for k in keys])))}
    return {"items": [item_out(db, (positions if k["kind"] == "position" else registrations)[k["id"]], users[k["user_id"]]) for k in keys],
        "total": total, "page": page, "page_size": page_size, "actionable_total": actionable,
        "routing_attention": bool(db.scalar(select(IamOutbox.id).where(IamOutbox.aggregate_id.in_(position_ids),
            IamOutbox.status == "retry", IamOutbox.last_error == "POSITION_NO_RECIPIENT").limit(1)))}


def permission_tuples(db, keys):
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    names = {p.code: p.name for p in db.scalars(select(AuthPermission))}
    return [{"permission_code": p, "permission_name": names.get(p, p), "factory_id": f,
        "factory_name": FACTORIES.get(f, "集团管理范围"), "department": d,
        "department_name": DEPARTMENTS.get(d, "通用范围")} for p, f, d in sorted(keys)]


def current_sources(db, user_id):
    from app.services.identity_sources import source_is_active
    from app.services.auth import time_window_is_active
    from app.services.permission_codes import CARTON_SUPPLIER_PERMISSION_CODES
    profile, now = db.get(EmployeeProfile, user_id), utc_now()
    bindings = []
    for binding, meta, role in db.execute(select(AuthUserRole, AuthRoleBindingMetadata, AuthRole).outerjoin(
            AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).join(AuthRole, AuthRole.id == AuthUserRole.role_id)
            .where(AuthUserRole.user_id == user_id)):
        if meta and meta.state != "active":
            continue
        # Preserve future sources in the read summary; only the selected current primary can be replaced.
        if meta and meta.valid_until and instant(meta.valid_until) <= now:
            continue
        if meta and meta.assignment_id:
            assignment = db.get(EmployeeAssignment, meta.assignment_id)
            if not assignment or assignment.lifecycle_state != "approved" or assignment.employment_epoch != profile.employment_epoch or (assignment.valid_until and instant(assignment.valid_until) <= now):
                continue
        bindings.append({"binding_id": binding.id, "role_id": role.id, "role_name": role.name,
            "role_version_id": meta.role_version_id if meta else None, "source_type": meta.source_type if meta else "legacy",
            "assignment_id": meta.assignment_id if meta else None,
            "factory_ids": json.loads(meta.scope_ceiling_json) if meta and meta.scope_ceiling_json is not None else [binding.factory_id],
            "department": binding.department, "source_review_required": not profile or profile.identity_mode != "v2"})
    allows, denies = [], []
    for override, permission in db.execute(select(AuthUserPermissionOverride, AuthPermission).join(AuthPermission,
            AuthPermission.id == AuthUserPermissionOverride.permission_id).where(AuthUserPermissionOverride.user_id == user_id,
            AuthUserPermissionOverride.status == "active")):
        if override.effect == "deny":
            if source_is_active(db, override, profile, now) and time_window_is_active(override.valid_from, override.valid_until, now):
                denies.append((permission.code, override.factory_id, override.department))
        elif not override.assignment_id and permission.code not in CARTON_SUPPLIER_PERMISSION_CODES:
            # Include scheduled and dormant active sources: the IAM planner
            # requires explicit dispositions and never reactivates them by keep.
            allows.append({"override_id": override.id, "permission_code": permission.code, "permission_name": permission.name,
                "factory_id": override.factory_id, "department": override.department, "decision_required": True,
                "valid_from": override.valid_from, "valid_until": override.valid_until,
                "currently_effective": source_is_active(db, override, profile, now) and time_window_is_active(override.valid_from, override.valid_until, now)})
    return bindings, allows, permission_tuples(db, denies)


def detail(db, actor, item_key):
    from app.services.iam import _get_revision
    row = load_item(db, actor, item_key)
    identity = resolve_identity_at(db, row.user_id)
    bindings, allows, denies = current_sources(db, row.user_id)
    is_position = isinstance(row, PositionReview)
    blocked = []
    if not reviews.writes_enabled():
        blocked.append("当前仅可查看，岗位更新暂不可提交")
    if is_position and identity["identity_mode"] != "v2":
        blocked.append("请先在本页核实历史授权来源；核实不会改变原权限")
    if is_position and (identity["employment_epoch"] != row.employment_epoch or identity["employment_status"] == "left"):
        blocked.append("任职周期已变化，此申请不再适用")
    if db.get(AuthUser, row.user_id).status not in ({"active"} if is_position else {"pending"}):
        blocked.append("账号当前不可办理")
    provisional = not is_position and row.status == "pending" and row.user_id in provisional_registration_users(db)
    return {**item_out(db, row), "current_official": None if provisional else reviews.official(db, row.user_id, identity),
        "identity_mode": identity["identity_mode"] if is_position else "registration_pending",
        "identity_version": identity["identity_version"], "authorization_version": _get_revision(db, row.user_id),
        "primary_assignment_id": identity["primary_assignment"]["id"] if identity["primary_assignment"] else None,
        "current_bindings": bindings, "independent_allows": allows, "explicit_denials": denies,
        "registration_details": None if is_position else {"display_name": row.display_name, "phone": row.phone, "email": row.email},
        "can_keep_permissions": is_position and identity["identity_mode"] == "v2" and not blocked,
        "blocked_reasons": blocked,
        "review_comment": row.review_comment,
        "confirmed_profile": json.loads(row.confirmed_snapshot_json) if is_position else None,
        "decision": row.decision if is_position else None,
        "reviewer_user_id": row.reviewer_user_id,
        "decision_at": row.decision_at if is_position else row.reviewed_at}
