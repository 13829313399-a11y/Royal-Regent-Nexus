"""Owning transactions for the personnel workbench. Never compose committed calls."""
import json
import secrets
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.auth import (AuthAuthorizationPreview, AuthPermissionMetadata, AuthRoleBindingMetadata,
    AuthUser, AuthUserRole, AuthUserPermissionOverride, EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamDelegation, IamMutationReceipt, IamOrgDepartment, IamOrgUnit, IamRoleVersion, IamOutbox
from app.models.position_review import PositionReview
from app.schemas.position_review import Declaration, PreviewInput, PackageSelection, Position
from app.services import identity_changes as changes, position_reviews as reviews
from app.services.identity_policy import ensure_admin_survives, ensure_reader, fail, fresh_actor, lock_mutation
from app.services.identity_resolver import instant, resolve_identity_at, stamp, utc_now
from app.services.identity_sources import definition_hash, role_definition
from app.services.position_workbench_read import (allowed_scope, current_sources, declaration, detail, ensure_item_scope,
    load_item, permission_tuples, revision)
from app.services.position_workbench_plan import apply_tx, make_plan, selected_role

OPERATION = "position_workbench"


def row_values(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def dependencies(db, actor, row, payload):
    from app.services.iam import _get_revision
    target = db.get(AuthUser, row.user_id)
    profile = db.get(EmployeeProfile, target.id)
    user_ids = sorted({target.id, actor.id})
    bindings = list(db.scalars(select(AuthUserRole).where(AuthUserRole.user_id.in_(user_ids)).order_by(AuthUserRole.id)))
    metadata = list(db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.user_role_id.in_([b.id for b in bindings]))
                              .order_by(AuthRoleBindingMetadata.user_role_id)))
    role_ids = {b.role_id for b in bindings}
    if payload.package_selection:
        role_ids.add(payload.package_selection.role_id)
    return {"policy": "position-workbench-v1", "source": revision(row), "target_status": target.status,
        "target_identity": resolve_identity_at(db, target.id)["effective_context_key"],
        "target_authorization_version": _get_revision(db, target.id),
        "profile": row_values(profile) if profile else None,
        "actor": [actor.id, actor.authorization_version, actor.identity["effective_context_key"], actor.identity["employment_epoch"]],
        "draft": payload.model_dump(mode="json"),
        "assignments": [row_values(a) for a in db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.user_id.in_(user_ids)).order_by(EmployeeAssignment.id))],
        "bindings": [row_values(b) for b in bindings], "metadata": [row_values(m) for m in metadata],
        "versions": [row_values(v) for v in db.scalars(select(IamRoleVersion).where(IamRoleVersion.id.in_([m.role_version_id for m in metadata if m.role_version_id])).order_by(IamRoleVersion.id))],
        "roles": [(rid, definition_hash(role_definition(db, rid))) for rid in sorted(role_ids)],
        "overrides": [row_values(o) for o in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id.in_(user_ids)).order_by(AuthUserPermissionOverride.id))],
        "delegations": [row_values(d) for d in db.scalars(select(IamDelegation).where(IamDelegation.user_id == actor.id).order_by(IamDelegation.id))],
        "organizations": [row_values(o) for o in db.scalars(select(IamOrgUnit).order_by(IamOrgUnit.id))],
        "departments": [row_values(d) for d in db.scalars(select(IamOrgDepartment).order_by(IamOrgDepartment.org_unit_id, IamOrgDepartment.department_code))],
        "permissions": [row_values(p) for p in db.scalars(select(AuthPermissionMetadata).order_by(AuthPermissionMetadata.permission_id))]}


def preview(db, actor_id, item_key, payload):
    from app.services.iam import _token_hash
    from app.services.identity_handover import assess
    reviews.require_schema(db)
    reviews.require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    row = load_item(db, actor, item_key, payload.expected_source_revision, pending=True)
    fingerprint = changes.digest(dependencies(db, actor, row, payload))
    at = utc_now()
    before = changes.access_matrix(db, row.user_id, at)
    with db.begin_nested() as simulation:
        prepared = make_plan(db, actor, row, payload)
        apply_tx(db, actor, row, prepared)
        ensure_admin_survives(db)
        after = changes.access_matrix(db, row.user_id, utc_now())
        handover = assess(db, row.user_id)
        simulation.rollback()
    if payload.decision == "keep_permissions" and set(before) != set(after):
        fail("KEEP_PERMISSION_DRIFT", "当前计划会改变实际权限，不能按保留原权限提交")
    bindings, allows, denies = current_sources(db, row.user_id)
    diff = {"added": permission_tuples(db, after.keys() - before.keys()),
            "removed": permission_tuples(db, before.keys() - after.keys()),
            "retained": permission_tuples(db, before.keys() & after.keys()),
            "source_changed": permission_tuples(db, [k for k in before.keys() & after.keys() if before[k] != after[k]])}
    now, expires = stamp(), stamp(utc_now() + timedelta(minutes=5))
    primary_id = (resolve_identity_at(db, row.user_id).get("primary_assignment") or {}).get("id")
    summary = {"expires_at": expires, "server_now": now, "source_revision": revision(row), "preview_fingerprint": fingerprint,
        "decision": payload.decision, "permission_diffs": diff,
        "retained_sources": [b["binding_id"] for b in bindings if b["assignment_id"] != primary_id or payload.decision == "keep_permissions"]
            + [d.override_id for d in payload.independent_allow_decisions if d.decision == "keep_original_scope"],
        "explicit_denials": denies, "high_risk": bool(diff["added"]), "requires_independent_approval": False,
        "allowed_to_commit": True, "blocked_reasons": [],
        "handover_summary": f"检测到 {handover['count']} 项内部报价责任；其他业务责任需人工检查。可在更多管理中办理工作交接。"}
    token = secrets.token_urlsafe(32)
    db.add(AuthAuthorizationPreview(id="preview-" + uuid4().hex, token_hash=_token_hash(token), actor_user_id=actor.id,
        target_type=OPERATION, target_id=item_key, base_revision=row.revision if isinstance(row, PositionReview) else 0,
        payload_json=changes.encoded({"draft": payload.model_dump(mode="json"), "fingerprint": fingerprint}),
        summary_json=changes.encoded(summary), expires_at=expires, consumed_at="", created_at=now))
    db.commit()
    return {**summary, "preview_token": token}


def receipt_row(db, actor_id, command_id):
    return db.scalar(select(IamMutationReceipt).where(IamMutationReceipt.actor_id == actor_id,
        IamMutationReceipt.operation == OPERATION, IamMutationReceipt.idempotency_key == str(command_id)))


def read_receipt(db, actor_id, command_id):
    # Only the original actor can observe a command, even after target scope changes.
    fresh_actor(db, actor_id)
    row = receipt_row(db, actor_id, command_id)
    return {"command_id": str(command_id), "status": "committed" if row else "not_observed",
            "result": json.loads(row.result_json) if row else None}


def existing_result(db, actor_id, command_id, body_hash):
    row = receipt_row(db, actor_id, command_id)
    if row:
        if row.payload_hash != body_hash:
            fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "同一命令不能用于不同内容")
        return json.loads(row.result_json)
    return None


def save_receipt_tx(db, actor, row, item_key, command_id, body_hash, decision):
    from app.services.iam import _get_revision
    identity = resolve_identity_at(db, row.user_id)
    result = {"command_id": str(command_id), "status": "committed", "item_key": item_key, "decision": decision,
        "source_status": row.status, "source_revision": revision(row),
        "target_identity_version": identity["identity_version"], "target_authorization_version": _get_revision(db, row.user_id),
        "notification_state": "queued", "committed_at": stamp(), "message": "办理已完成"}
    db.add(IamMutationReceipt(id=uuid4().hex, actor_id=actor.id, operation=OPERATION, idempotency_key=str(command_id),
        payload_hash=body_hash, result_json=changes.encoded(result), created_at=stamp()))
    db.flush()
    return result


def commit(db, actor_id, item_key, payload):
    from app.services.iam import _token_hash, _add_event
    reviews.require_schema(db)
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    body_hash = changes.digest({"item_key": item_key, "operation": "commit", **payload.model_dump(mode="json")})
    result = existing_result(db, actor.id, payload.command_id, body_hash)
    if result:
        return result
    reviews.require_writes()
    row = load_item(db, actor, item_key, payload.expected_source_revision, pending=True)
    token = db.scalar(select(AuthAuthorizationPreview).where(AuthAuthorizationPreview.token_hash == _token_hash(payload.preview_token)))
    if not token or token.actor_user_id != actor.id or token.target_type != OPERATION or token.target_id != item_key:
        fail("PREVIEW_NOT_FOUND", "预览不存在或不属于此办理事项", 404)
    if token.consumed_at or instant(token.expires_at) <= utc_now():
        fail("PREVIEW_EXPIRED", "预览已失效，请重新核对")
    evidence, summary = json.loads(token.payload_json), json.loads(token.summary_json)
    draft = PreviewInput.model_validate(evidence["draft"])
    if changes.digest(dependencies(db, actor, row, draft)) != evidence["fingerprint"]:
        fail("AUTHORIZATION_CHANGED", "申报、组织、权限或方案已变化，请重新预览")
    if summary["high_risk"] and not payload.risk_acknowledged:
        fail("CONFIRM_HIGH_RISK", "请确认本次实际新增权限", 422)
    before = changes.access_matrix(db, row.user_id, utc_now())
    prepared = make_plan(db, actor, row, draft)
    changes_ids = apply_tx(db, actor, row, prepared)
    after = changes.access_matrix(db, row.user_id, utc_now())
    # Time-based source activation may occur without a row/version write.
    expected_diff = summary["permission_diffs"]
    for key, actual in (("added", after.keys() - before.keys()), ("removed", before.keys() - after.keys())):
        expected = {(p["permission_code"], p["factory_id"], p["department"]) for p in expected_diff[key]}
        if set(actual) != expected:
            fail("AUTHORIZATION_CHANGED", "权限有效时间或实际差异已变化，请重新预览")
    if draft.decision == "keep_permissions" and set(before) != set(after):
        fail("KEEP_PERMISSION_DRIFT", "实际权限发生漂移，未提交任何变更")
    ensure_admin_survives(db)
    if isinstance(row, PositionReview):
        previous = reviews.review_out(row)
        row.status, row.decision, row.reviewer_user_id = "applied", draft.decision, actor.id
        row.confirmed_snapshot_json = changes.encoded(draft.confirmed_profile.model_dump())
        row.applied_identity_change_ids_json = changes.encoded(changes_ids)
        row.receipt_command_id, row.decision_at, row.updated_at = str(payload.command_id), stamp(), stamp()
        row.revision += 1
        reviews.event_tx(db, row, actor.id, "applied", previous)
        reviews.notify_tx(db, row, "applied")
    else:
        db.add(IamOutbox(id="registration-position-" + row.id, aggregate_id=row.id, kind="identity_changed",
            payload_json=changes.encoded({"user_id": row.user_id, "change_id": changes_ids[0]}), created_at=stamp()))
    _add_event(db, actor.id, "position_review_applied", "position_workbench", item_key,
        target_user_id=row.user_id, after={"decision": draft.decision, "source_revision": revision(row)}, reason="岗位与权限确认")
    token.consumed_at = stamp()
    result = save_receipt_tx(db, actor, row, item_key, payload.command_id, body_hash, draft.decision)
    db.commit()
    return result


def decide(db, actor_id, item_key, payload):
    reviews.require_schema(db)
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    body_hash = changes.digest({"item_key": item_key, "operation": "decision", **payload.model_dump(mode="json")})
    result = existing_result(db, actor.id, payload.command_id, body_hash)
    if result:
        return result
    reviews.require_writes()
    row = load_item(db, actor, item_key, payload.expected_source_revision, pending=True)
    if isinstance(row, PositionReview):
        if payload.action != "return_position":
            fail("INVALID_DECISION", "岗位更新只能退回补充", 422)
        before = reviews.review_out(row)
        row.status, row.review_comment, row.reviewer_user_id = "returned", payload.reason, actor.id
        row.revision += 1
        row.updated_at, row.decision_at, row.receipt_command_id = stamp(), stamp(), str(payload.command_id)
        reviews.event_tx(db, row, actor.id, "returned", before, payload.reason)
        reviews.notify_tx(db, row, "returned")
    else:
        if payload.action != "reject_registration":
            fail("INVALID_DECISION", "注册申请只能拒绝注册", 422)
        from app.schemas.system import RegistrationRejectRequest
        from app.services.system import reject_registration_request_tx
        reject_registration_request_tx(db, actor, row.id, RegistrationRejectRequest(review_comment=payload.reason))
    result = save_receipt_tx(db, actor, row, item_key, payload.command_id, body_hash, payload.action)
    db.commit()
    return result


def admin_adjustment(db, actor_id, payload):
    reviews.require_schema(db)
    reviews.require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    ensure_reader(db, actor, payload.target_user_id)
    target = reviews.self_actor(db, payload.target_user_id)
    reviews.validate_position(db, payload.proposed_profile)
    current = reviews.open_review(db, target)
    if current:
        ensure_item_scope(db, actor, current)
        if current.status == "returned":
            before = reviews.review_out(current)
            current.status = "pending"
            current.revision += 1
            current.updated_at = current.last_submitted_at = stamp()
            reviews.event_tx(db, current, actor.id, "admin_resumed", before, payload.reason)
            reviews.notify_tx(db, current, "updated")
        db.commit()
        return {"item_key": "position:" + current.id, "review": reviews.review_out(current), "reused": True}
    row = reviews.create_review_tx(db, actor, target, Declaration(**payload.proposed_profile.model_dump()), origin="admin", reason=payload.reason)
    ensure_item_scope(db, actor, row)
    db.commit()
    return {"item_key": "position:" + row.id, "review": reviews.review_out(row), "reused": False}


def packages(db, actor, item_key="", confirmed_profile=None, factory_scope=None):
    from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS, SYSTEM_POSITION_DEFINITION_VERSION, system_position_catalog_hash
    from app.models.auth import AuthPermission
    ensure_reader(db, actor)
    row = load_item(db, actor, item_key) if item_key else None
    names = {p.code: p.name for p in db.scalars(select(AuthPermission))}
    items = []
    for fixed in SYSTEM_POSITION_DEFINITIONS:
        definition = role_definition(db, fixed.role_id)
        definition_digest = definition_hash(definition)
        version = db.scalar(select(IamRoleVersion).where(IamRoleVersion.role_id == fixed.role_id, IamRoleVersion.definition_hash == definition_digest))
        blocked = "选择办理对象后核对范围" if row is None else None
        if row and not reviews.writes_enabled():
            blocked = "当前仅可查看，岗位更新暂不可提交"
        if row and not blocked:
            try:
                position = confirmed_profile or Position.model_validate({k: v for k, v in declaration(row).items() if k != "note"})
                # No snapshot writes on this GET. Assignment scope is rechecked
                # with the administrator's complete draft in preview/commit.
                from app.services.position_workbench_plan import role_candidate
                role_candidate(db, actor, row.user_id, PackageSelection(role_id=fixed.role_id,
                    definition_hash=definition_digest, permission_department=fixed.department,
                    factory_scope=factory_scope or {"kind": "home", "factory_ids": []}), position)
            except HTTPException as exc:
                blocked = exc.detail.get("message", "超出可分配范围") if isinstance(exc.detail, dict) else str(exc.detail)
        items.append({"role_id": fixed.role_id, "name": fixed.name, "department": fixed.department,
            "description": fixed.description, "definition_hash": definition_digest, "role_version_id": version.id if version else None,
            "assignable": blocked is None, "blocked_reason": blocked, "scope_mode": definition["scope_mode"],
            "capability_summary": [names.get(code, code) for code in definition["permissions"]]})
    return {"items": items, "catalog_definition_version": SYSTEM_POSITION_DEFINITION_VERSION, "catalog_revision": system_position_catalog_hash()}
