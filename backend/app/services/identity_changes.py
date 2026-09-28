"""Application service owns the transaction; domain helpers never commit."""
from __future__ import annotations
import hashlib
import json
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.models.auth import (AuthAccessRequest, AuthAuthorizationPreview, AuthRole, AuthRoleBindingMetadata,
    AuthSession, AuthUser, AuthUserAuthorizationRevision, AuthUserPermissionOverride, AuthUserRole, EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamMutationReceipt, IamOrgDepartment, IamOrgUnit, IamOutbox
from app.schemas.identity import IdentityChange
from app.services.identity_policy import (ensure_admin_survives, ensure_change_authority, ensure_reader,
    fail, fresh_actor, lock_mutation, require_writes)
from app.services.identity_resolver import instant, resolve_identity_at, stamp, utc_now
from app.services.identity_sources import definition_hash, role_definition, snapshot_role


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def load_change(db, change_id):
    row = db.get(AuthAccessRequest, change_id, populate_existing=True)
    if row is None or not row.request_type.startswith("identity:"):
        fail("CHANGE_NOT_FOUND", "变更单不存在", 404)
    return row


def result_out(row):
    result = json.loads(row.result_json or "{}")
    state = row.lifecycle_state
    if state == "scheduled" and instant(row.effective_at) <= utc_now():
        state = "applied"
    return {"id": row.id, "target_user_id": row.target_user_id, "requester_user_id": row.requester_user_id,
            "request_type": row.request_type.removeprefix("identity:"), "state": state, "revision": row.revision,
            "handover_refresh_pending": row.lifecycle_state == "scheduled" and state == "applied",
            "reason": row.reason, "effective_at": row.effective_at, "created_at": row.created_at,
            "payload": json.loads(row.payload_json), "result": result}


def save_draft(db, actor_id, payload: IdentityChange, *, change_id=None, expected_revision=None):
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    ensure_reader(db, actor, payload.target_user_id)
    if not db.get(AuthUser, payload.target_user_id):
        fail("USER_NOT_FOUND", "人员不存在", 404)
    now = stamp()
    if change_id:
        row = load_change(db, change_id)
        if row.requester_user_id != actor_id or row.lifecycle_state != "draft" or row.revision != expected_revision:
            fail("DRAFT_CONFLICT", "草稿已变化，请刷新后重试")
        if row.target_user_id != payload.target_user_id:
            fail("INVALID_CHANGE", "不能更换草稿中的人员", 422)
        row.revision += 1
    else:
        row = AuthAccessRequest(id=f"identity-{uuid4().hex}", requester_user_id=actor_id,
                                target_user_id=payload.target_user_id, created_at=now, status="pending", revision=1)
        db.add(row)
    row.request_type = "identity:" + payload.request_type
    row.lifecycle_state = "draft"
    row.reason = payload.reason.strip()
    row.payload_json = encoded(payload.model_dump(mode="json"))
    row.updated_at = now
    db.commit()
    return result_out(row)


def prepare(db, row, actor):
    from app.services.auth import build_auth_context
    from app.services.iam import _get_revision
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    payload = IdentityChange.model_validate_json(row.payload_json)
    profile = db.get(EmployeeProfile, row.target_user_id)
    user = db.get(AuthUser, row.target_user_id)
    missing_profile = profile is None
    if not profile:
        if payload.request_type != "confirm_identity":
            fail("IDENTITY_REVIEW_REQUIRED", "缺少正式档案，请先人工核实并确认任职")
        from app.services.identity_policy import is_group_manager
        if not is_group_manager(actor):
            fail("IDENTITY_REVIEW_REQUIRED", "缺少正式档案，须由集团管理员核实", 403)
        profile = EmployeeProfile(user_id=user.id, identity_mode="legacy", identity_version=0, employment_epoch=1,
            employment_status="active", primary_org_unit_id="", primary_factory_id="", primary_department="", position="",
            confirmation_status="unconfirmed", created_at=stamp(), updated_at=stamp())
    identity = resolve_identity_at(db, user.id)
    revision = _get_revision(db, user.id)
    if profile.identity_version != payload.base_identity_version or revision != payload.base_authorization_version:
        fail("IDENTITY_VERSION_CONFLICT", "人员或授权已变化，请刷新后重新预览")
    now = utc_now()
    effective = instant(payload.effective_at) if payload.effective_at else now
    if effective < now - timedelta(seconds=5):
        fail("INVALID_TIME_RANGE", "生效时间不能早于服务器当前时间", 422)
    scheduled = effective > now + timedelta(seconds=1)
    if scheduled and (payload.request_type in {"freeze", "unfreeze", "leave", "rehire", "confirm_identity", "profile_correction", "upgrade_packages"}
                      or not settings.iam_identity_scheduling_enabled):
        fail("SCHEDULING_UNAVAILABLE", "此操作当前只支持立即办理", 422)
    if payload.request_type not in {"confirm_identity", "freeze", "unfreeze", "leave"} and profile.identity_mode != "v2":
        fail("IDENTITY_REVIEW_REQUIRED", "请先明确历史授权来源并确认正式任职")
    if profile.employment_status == "left" and payload.request_type != "rehire":
        fail("REHIRE_REQUIRED", "离职人员须重新确认任职后复职")
    if payload.request_type == "rehire" and profile.employment_status != "left":
        fail("INVALID_CHANGE", "只有离职人员可以复职", 422)
    if payload.request_type == "confirm_identity" and profile.identity_mode == "v2":
        fail("IDENTITY_ALREADY_CONFIRMED", "此人员已建立正式任职")
    if payload.request_type == "unfreeze" and user.status != "suspended":
        fail("INVALID_CHANGE", "只有冻结账号可以恢复", 422)
    if user.status not in {"active", "suspended"} and payload.request_type != "rehire":
        fail("INVALID_CHANGE", "请先完成注册审核", 422)
    source = db.get(EmployeeAssignment, payload.source_assignment_id) if payload.source_assignment_id else None
    if payload.source_assignment_id and (source is None or source.user_id != user.id or source.lifecycle_state != "approved"
                                        or source.employment_epoch != profile.employment_epoch):
        fail("SOURCE_CHANGED", "来源任职不存在或已结束")
    if source and payload.request_type in {"primary_assignment_transfer", "end_assignment"}:
        if not (instant(source.valid_from) <= effective and (not source.valid_until or effective < instant(source.valid_until))):
            fail("SOURCE_CHANGED", "来源任职在生效时点无效")
        if payload.request_type == "primary_assignment_transfer" and not source.is_primary:
            fail("INVALID_CHANGE", "调动的来源必须为主职", 422)
    roles = []
    dependencies = {"identity": profile.identity_version, "authorization": revision, "source": source.revision if source else None,
                    "actor_authorization": actor.authorization_version, "actor_identity": actor.identity["effective_context_key"],
                    "missing_profile": missing_profile}
    from app.models.identity import IamDelegation
    dependencies["delegations"] = sorted((d.id, d.revision, d.status, d.role_ids_json, d.factory_ids_json)
        for d in db.scalars(select(IamDelegation).where(IamDelegation.user_id == actor.id)))
    scopes = []
    if source:
        old_org = db.get(IamOrgUnit, source.org_unit_id)
        scopes.append((source.org_unit_id, old_org.legacy_factory_id, source.department_code))
    if payload.request_type in {"freeze", "unfreeze", "leave", "rehire", "profile_correction", "confirm_identity"}:
        scopes.extend((a["org_unit_id"], a["factory_id"], a["department_code"]) for a in identity["assignments"] if a["state"] in {"current", "scheduled"})
        if not scopes:
            scopes.append((profile.primary_org_unit_id or profile.primary_factory_id, profile.primary_factory_id, profile.primary_department))
        from app.services.identity_policy import additional_source_scopes
        scopes.extend((f, f, d) for f, d in additional_source_scopes(db, [user.id]).get(user.id, set()))
    spec = payload.new_assignment
    if spec:
        org = db.get(IamOrgUnit, spec.org_unit_id)
        dept = db.get(IamOrgDepartment, (spec.org_unit_id, spec.department_code))
        if not org or org.status != "active" or org.kind == "group" or not dept or dept.status != "active":
            fail("INVALID_ORG", "请选择有效组织与正式部门", 422)
        if spec.valid_until and instant(spec.valid_until) <= effective:
            fail("INVALID_TIME_RANGE", "结束时间必须晚于开始时间", 422)
        if spec.assignment_type in {"temporary", "acting"} and not spec.valid_until:
            fail("INVALID_TIME_RANGE", "临时支援和代理必须填写结束时间", 422)
        dependencies["organization"] = [org.id, org.revision, dept.revision]
        scopes.append((org.id, org.legacy_factory_id, spec.department_code))
        for binding in spec.role_bindings:
            definition = role_definition(db, binding.role_id)
            if definition["role_code"] == "admin" or any(p.startswith("system:") for p in definition["permissions"]):
                fail("ADMINISTRATION_SEPARATE", "系统管理权须通过独立授权办理", 422)
            if binding.department not in DEPARTMENTS:
                fail("INVALID_SCOPE", "请选择权限包作用部门", 422)
            from app.services.permission_scope_policy import role_scope_policy
            from app.services.iam import _ensure_scope_applicable
            factories = ([org.legacy_factory_id] if binding.factory_scope.kind == "home" else sorted(FACTORIES)
                         if binding.factory_scope.kind == "all_current" else sorted(set(binding.factory_scope.factory_ids)))
            if not factories or any(f not in FACTORIES for f in factories):
                fail("INVALID_SCOPE", "职能组织必须选择具体业务厂区", 422)
            for factory in factories:
                business_org = db.get(IamOrgUnit, factory)
                if not business_org or business_org.status != "active":
                    fail("INVALID_SCOPE", "业务厂区已停用，请重新选择", 422)
                dependencies.setdefault("business_organizations", []).append([factory, business_org.revision, business_org.status])
                _ensure_scope_applicable(role_scope_policy(definition["role_code"]), factory, binding.department, subject=definition["role_name"])
            version = snapshot_role(db, binding.role_id, actor.id)
            if binding.role_version_id and version.id != binding.role_version_id:
                fail("ROLE_VERSION_CHANGED", "权限包已发布新版本，请重新预览")
            roles.append({**definition, "version_id": version.id, "hash": version.definition_hash,
                          "factories": factories, "department": binding.department})
        dependencies["roles"] = [(r["role_id"], r["hash"]) for r in roles]
    if payload.request_type == "upgrade_packages":
        for meta in db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.assignment_id == source.id)):
            binding = db.get(AuthUserRole, meta.user_role_id)
            version = snapshot_role(db, binding.role_id, actor.id)
            dependencies.setdefault("upgrades", []).append([binding.id, version.id, version.definition_hash])
            definition = role_definition(db, binding.role_id)
            if definition["role_code"] == "admin" or any(p.startswith("system:") for p in definition["permissions"]):
                fail("ADMINISTRATION_SEPARATE", "升级不能把系统管理权附加到普通任职，请独立办理", 422)
            roles.append({**definition, "factories": json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json else list(FACTORIES)})
    overrides = list(db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == user.id,
                                                                       AuthUserPermissionOverride.status == "active")))
    decisions = {d.override_id: d.decision for d in payload.exception_decisions}
    if any(key not in {o.id for o in overrides} for key in decisions):
        fail("SOURCE_CHANGED", "个人例外已变化")
    from app.services.permission_codes import CARTON_SUPPLIER_PERMISSION_CODES
    from app.models.auth import AuthPermission
    permissions = {p.id: p.code for p in db.scalars(select(AuthPermission))}
    from app.models.auth import AuthPermissionMetadata
    dependencies["permission_registry"] = sorted((m.permission_id, m.status, m.access_kind) for m in db.scalars(select(AuthPermissionMetadata)))
    independent = [o for o in overrides if o.effect == "allow" and not o.assignment_id and permissions.get(o.permission_id) not in CARTON_SUPPLIER_PERMISSION_CODES]
    if payload.request_type in {"confirm_identity", "primary_assignment_transfer"} and any(o.id not in decisions for o in independent):
        fail("EXCEPTION_DECISION_REQUIRED", "请逐项确认个人独立允许的保留或终止", 422)
    for o in overrides:
        if decisions.get(o.id) == "end":
            scopes.append((o.factory_id, o.factory_id, o.department))
    dependencies["overrides"] = [[o.id, o.status, o.valid_from, o.valid_until, o.assignment_id, o.effect, o.factory_id, o.department] for o in overrides]
    bindings = list(db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)))
    if payload.request_type == "confirm_identity":
        confirmed = bool(profile.primary_factory_id or profile.primary_org_unit_id) and bool(profile.primary_department) and profile.confirmation_status == "confirmed"
        if (confirmed and (spec.org_unit_id != (profile.primary_org_unit_id or profile.primary_factory_id)
                or spec.department_code != profile.primary_department or spec.official_position_title != profile.position)) or spec.role_bindings:
            fail("MIGRATION_MUST_PRESERVE", "首次确认须保留已确认组织、职位与授权；之后另办调动", 422)
        dispositions = {d.binding_id: d.source for d in payload.binding_dispositions}
        active_ids = {b.id for b in bindings if (m := db.get(AuthRoleBindingMetadata, b.id)) is None or m.state == "active"}
        if set(dispositions) != active_ids:
            fail("SOURCE_REVIEW_REQUIRED", "请逐项核实全部现有和未来授权来源", 422)
        for b in bindings:
            if b.id not in active_ids:
                continue
            role = db.get(AuthRole, b.role_id)
            scopes.append((b.factory_id, b.factory_id, b.department))
            definition = role_definition(db, b.role_id)
            if (role.code == "admin" or any(p.startswith("system:") for p in definition["permissions"])) and dispositions[b.id] != "system_administration":
                fail("ADMINISTRATION_SEPARATE", "系统管理员来源必须独立保留", 422)
            snapshot_role(db, b.role_id, actor.id)
        dependencies["migration_roles"] = [(b.id, definition_hash(role_definition(db, b.role_id))) for b in bindings]
    dependencies["bindings"] = [[b.id, b.role_id, b.factory_id, b.department,
                                 (m.version if (m := db.get(AuthRoleBindingMetadata, b.id)) else None)] for b in bindings]
    requires_approval = False
    try:
        ensure_change_authority(db, actor, user.id, scopes, roles)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        requires_approval = True
    return {"payload": payload, "profile": profile, "source": source, "roles": roles, "dependencies": dependencies,
            "missing_profile": missing_profile,
            "effective": stamp(effective), "scheduled": scheduled, "requires_approval": requires_approval,
            "scopes": scopes, "identity": identity, "user": user}


def revoke_sessions(db, user_id):
    from app.services.auth import now_text
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.status == "active")):
        session.status = "revoked"
        session.revoked_at = now_text()


def apply_plan(db, row, actor, plan):
    from app.services.auth import now_text
    payload, profile, user, source = plan["payload"], plan["profile"], plan["user"], plan["source"]
    if plan["missing_profile"]:
        db.add(profile)
        db.flush()
    at, now = plan["effective"], stamp()
    kind = payload.request_type
    old_end = source.valid_until if source else None
    exception_before = {d.override_id: db.get(AuthUserPermissionOverride, d.override_id).valid_until
                        for d in payload.exception_decisions if d.decision == "end"}
    if source and kind in {"primary_assignment_transfer", "end_assignment"}:
        source.valid_until = at
        source.ended_reason = payload.reason
        source.revision += 1
        source.updated_at = now
    if kind in {"freeze", "leave"}:
        revoke_sessions(db, user.id)
        user.status = "suspended"
        profile.employment_status = "frozen" if kind == "freeze" else "left"
    if kind == "leave":
        for assignment in db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.user_id == user.id,
                                                                       EmployeeAssignment.lifecycle_state == "approved")):
            if instant(assignment.valid_from) >= instant(at):
                assignment.lifecycle_state = "revoked"
                assignment.revoked_at = at
            elif not assignment.valid_until or instant(assignment.valid_until) > instant(at):
                assignment.valid_until = at
            assignment.ended_reason = payload.reason
            assignment.revision += 1
        for binding in db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)):
            meta = db.get(AuthRoleBindingMetadata, binding.id)
            if not meta:
                meta = AuthRoleBindingMetadata(user_role_id=binding.id)
                db.add(meta)
            meta.state = "revoked"
            meta.revoked_at = at
            meta.revoke_reason = payload.reason
        for override in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == user.id,
                                                                           AuthUserPermissionOverride.effect == "allow")):
            override.status = "revoked"
            override.revoked_at = at
            override.revoke_reason = payload.reason
        for pending in db.scalars(select(AuthAccessRequest).where(AuthAccessRequest.target_user_id == user.id,
                AuthAccessRequest.request_type.like("identity:%"), AuthAccessRequest.lifecycle_state.in_(["draft", "pending_approval", "scheduled"]))):
            if pending.id != row.id:
                pending.lifecycle_state = "cancelled"
                pending.revision += 1
        profile.employment_epoch += 1
    if kind in {"unfreeze", "rehire"}:
        user.status = "active"
        profile.employment_status = "active"
        if kind == "rehire":
            profile.employment_epoch += 1
    new_id = None
    if payload.new_assignment:
        spec = payload.new_assignment
        if spec.is_primary:
            for assignment in db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.user_id == user.id,
                    EmployeeAssignment.is_primary.is_(True), EmployeeAssignment.lifecycle_state == "approved",
                    EmployeeAssignment.employment_epoch == profile.employment_epoch)):
                if (not assignment.valid_until or instant(at) < instant(assignment.valid_until)) and (
                        not spec.valid_until or instant(assignment.valid_from) < instant(spec.valid_until)):
                    fail("PRIMARY_ASSIGNMENT_OVERLAP", "此时间范围已有主职，请先调整原计划")
        new_id = f"assignment-{uuid4().hex}"
        assignment = EmployeeAssignment(id=new_id, user_id=user.id, org_unit_id=spec.org_unit_id,
            department_code=spec.department_code, official_position_title=spec.official_position_title,
            assignment_type=spec.assignment_type, is_primary=spec.is_primary, valid_from=at,
            valid_until=stamp(spec.valid_until) if spec.valid_until else None, employment_epoch=profile.employment_epoch,
            source_request_id=row.id, created_by=row.requester_user_id, confirmed_by=actor.id, created_at=now, updated_at=now)
        db.add(assignment)
        db.flush()
        profile.identity_mode = "v2"
        for role in plan["roles"]:
            for factory in role["factories"]:
                binding = AuthUserRole(id=f"assignment-role-{uuid4().hex}", user_id=user.id, role_id=role["role_id"],
                                       factory_id=factory, department=role["department"])
                db.add(binding)
                db.flush()
                db.add(AuthRoleBindingMetadata(user_role_id=binding.id, assignment_id=new_id,
                    role_version_id=role["version_id"], scope_ceiling_json=encoded(role["factories"]),
                    employment_epoch=profile.employment_epoch, state="active", source_type="assignment", source_id=new_id,
                    valid_from=at, valid_until=assignment.valid_until or "", reason=payload.reason,
                    created_by_user_id=row.requester_user_id, approved_by_user_id=actor.id, created_at=now, updated_at=now))
        if kind == "confirm_identity":
            profile.confirmation_status = "confirmed"
            for disposition in payload.binding_dispositions:
                binding = db.get(AuthUserRole, disposition.binding_id)
                meta = db.get(AuthRoleBindingMetadata, binding.id)
                if not meta:
                    meta = AuthRoleBindingMetadata(user_role_id=binding.id, state="active")
                    db.add(meta)
                meta.assignment_id = new_id if disposition.source == "assignment" else None
                meta.role_version_id = snapshot_role(db, binding.role_id, actor.id).id
                meta.scope_ceiling_json = None  # Explicitly preserve legacy template expansion.
                meta.employment_epoch = profile.employment_epoch
                meta.source_type = disposition.source
                meta.version = (meta.version or 0) + 1
            for override in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == user.id)):
                override.employment_epoch = profile.employment_epoch
    if kind == "profile_correction":
        if payload.display_name:
            user.display_name = payload.display_name
        if payload.official_position_title:
            primary = plan["identity"]["primary_assignment"]
            if not primary:
                fail("SOURCE_CHANGED", "当前没有可更正的主职")
            assignment = db.get(EmployeeAssignment, primary["id"])
            assignment.official_position_title = payload.official_position_title
            assignment.revision += 1
    if kind == "upgrade_packages":
        for binding_id, version_id, _ in plan["dependencies"].get("upgrades", []):
            meta = db.get(AuthRoleBindingMetadata, binding_id)
            meta.role_version_id = version_id
            meta.version += 1
    for decision in payload.exception_decisions:
        if decision.decision == "end":
            override = db.get(AuthUserPermissionOverride, decision.override_id)
            override.valid_until = at
            override.revoke_reason = payload.reason
    profile.identity_version += 1
    profile.updated_at = now_text()
    user.updated_at = now_text()
    revision = db.get(AuthUserAuthorizationRevision, user.id)
    if not revision:
        revision = AuthUserAuthorizationRevision(user_id=user.id, revision=0)
        db.add(revision)
    revision.revision += 1
    revision.updated_at = now_text()
    db.flush()
    identity = resolve_identity_at(db, user.id)
    primary = identity["primary_assignment"]
    if profile.identity_mode == "v2":
        profile.primary_assignment_id = primary["id"] if primary else None
        profile.primary_org_unit_id = primary["org_unit_id"] if primary else ""
        profile.primary_factory_id = identity["primary_factory_id"]
        profile.primary_department = identity["primary_department"]
        profile.position = identity["position"]
    db.flush()
    return {"assignment_id": new_id, "source_assignment_id": source.id if source else None, "old_source_until": old_end,
            "exception_before": exception_before,
            "source_revision": source.revision if source else None, "identity_version": profile.identity_version,
            "authorization_version": revision.revision, "identity": identity}


def access_matrix(db, user_id, at):
    from app.services.auth import authorization_decision, build_auth_context
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    context = build_auth_context(db, db.get(AuthUser, user_id), at=at)
    result = {}
    for factory in [*FACTORIES, "*"]:
        for department in [*DEPARTMENTS, "system", "*"]:
            for permission in context.active_permission_codes:
                allowed, _, ids, _ = authorization_decision(context, permission, factory, department, at=at)
                if allowed:
                    result[(permission, factory, department)] = ids
    return result


def preview_change(db, actor_id, change_id):
    from app.services.iam import _store_preview
    from app.services.identity_handover import assess
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    row = load_change(db, change_id)
    ensure_reader(db, actor, row.target_user_id)
    if row.lifecycle_state not in {"draft", "pending_approval"}:
        fail("CHANGE_STATE_CONFLICT", "此变更已处理")
    plan = prepare(db, row, actor)
    at = instant(plan["effective"])
    before = access_matrix(db, row.target_user_id, at)
    with db.begin_nested() as simulation:
        applied = apply_plan(db, row, actor, plan)
        after = access_matrix(db, row.target_user_id, at)
        after_identity = resolve_identity_at(db, row.target_user_id, at)
        simulation.rollback()
    if plan["payload"].request_type == "confirm_identity" and set(before) != set(after):
        fail("MIGRATION_PERMISSION_DRIFT", "来源映射改变实际权限，请重新核实")
    from app.models.auth import AuthPermission
    from app.services.identity_catalog import FACTORIES, DEPARTMENTS
    permission_names = {p.code: p.name for p in db.scalars(select(AuthPermission))}
    def tuples(keys):
        return [{"permission_code": p, "permission_name": permission_names.get(p, p), "factory_id": f,
                 "factory_name": FACTORIES.get(f, "集团管理范围"), "department": d,
                 "department_name": DEPARTMENTS.get(d, "系统管理" if d == "system" else "通用范围")} for p, f, d in sorted(keys)]
    summary = {"before_identity": plan["identity"], "after_identity": after_identity,
               "permission_diffs": {"added": tuples(after.keys() - before.keys()), "removed": tuples(before.keys() - after.keys()),
                                    "retained": tuples(after.keys() & before.keys()),
                                    "source_changed": tuples(k for k in after.keys() & before.keys() if after[k] != before[k])},
               "requires_approval": plan["requires_approval"], "high_risk": bool(after.keys() - before.keys()) or plan["payload"].request_type in {"leave", "freeze"},
               "handover_summary": assess(db, row.target_user_id), "effective_at": plan["effective"],
               "server_now": stamp(), "request_revision": row.revision,
               "retained_sources": [o.id for o in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == row.target_user_id, AuthUserPermissionOverride.status == "active"))
                                    if o.id not in {d.override_id for d in plan["payload"].exception_decisions if d.decision == "end"}]}
    dependencies = plan["dependencies"]
    fingerprint = digest({"payload": row.payload_json, "revision": row.revision, "dependencies": dependencies})
    token, expires = _store_preview(db, actor_id, "identity_change", row.id, row.revision,
        {"fingerprint": fingerprint, "dependencies": dependencies, "effective_at": plan["effective"]}, summary)
    db.commit()
    return {**summary, "preview_token": token, "expires_at": expires, "preview_fingerprint": fingerprint}


def commit_change(db, actor_id, change_id, payload, idempotency_key, *, approving=False):
    from app.services.iam import _add_event, _load_preview
    from app.services.identity_handover import persist_items
    require_writes()
    if not idempotency_key or len(idempotency_key) > 128:
        fail("IDEMPOTENCY_KEY_REQUIRED", "请提供有效的幂等键", 422)
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    operation = "identity_approve" if approving else "identity_commit"
    body_hash = digest({"change_id": change_id, **payload.model_dump()})
    receipt = db.scalar(select(IamMutationReceipt).where(IamMutationReceipt.actor_id == actor_id,
                        IamMutationReceipt.operation == operation, IamMutationReceipt.idempotency_key == idempotency_key))
    if receipt:
        if receipt.payload_hash != body_hash:
            fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "相同幂等键不能用于不同提交")
        return json.loads(receipt.result_json)
    row = load_change(db, change_id)
    ensure_reader(db, actor, row.target_user_id)
    if row.revision != payload.expected_request_revision or row.lifecycle_state != ("pending_approval" if approving else "draft"):
        fail("DRAFT_CONFLICT", "变更单已被修改或处理，请刷新")
    preview, evidence, summary = _load_preview(db, payload.preview_token, actor_id, "identity_change", row.id)
    plan = prepare(db, row, actor)
    if evidence["fingerprint"] != digest({"payload": row.payload_json, "revision": row.revision, "dependencies": plan["dependencies"]}):
        fail("AUTHORIZATION_CHANGED", "预览后的授权或组织已变化，请重新预览")
    if approving and (plan["requires_approval"] or actor_id == row.requester_user_id and row.target_user_id == actor_id):
        fail("GRANT_NOT_DELEGABLE", "需要有完整授权范围的独立管理员审核", 403)
    if summary["high_risk"] and not payload.confirm_high_risk:
        fail("CONFIRM_HIGH_RISK", "请确认预览中的新增权限或停止访问影响", 422)
    # Immediate changes begin at the instant confirmed in the preview; future
    # plans that passed their boundary while awaiting approval require repreview.
    plan["effective"] = evidence["effective_at"]
    if plan["payload"].effective_at and instant(plan["effective"]) <= utc_now():
        fail("SOURCE_CHANGED", "预约生效点已过，请重新安排")
    if plan["requires_approval"]:
        row.lifecycle_state = "pending_approval"
        row.submitted_at = stamp()
    else:
        before = resolve_identity_at(db, row.target_user_id)
        result = apply_plan(db, row, actor, plan)
        ensure_admin_survives(db)
        row.lifecycle_state = "scheduled" if plan["scheduled"] else "applied"
        row.status = "approved"
        row.decision_by_user_id = actor_id
        row.decided_at = stamp()
        row.effective_at = plan["effective"]
        result["handover"] = persist_items(db, row)
        row.result_json = encoded(result)
        _add_event(db, actor_id, "identity_" + plan["payload"].request_type, "identity_change", row.id,
                   target_user_id=row.target_user_id, before=before, after=result, reason=row.reason, access_request_id=row.id)
        db.add(IamOutbox(id=f"identity-notify-{row.id}", aggregate_id=row.id, kind="identity_changed",
                        payload_json=encoded({"user_id": row.target_user_id, "change_id": row.id}), created_at=stamp()))
    preview.consumed_at = stamp()
    row.revision += 1
    row.updated_at = stamp()
    result = result_out(row)
    db.add(IamMutationReceipt(id=uuid4().hex, actor_id=actor_id, operation=operation, idempotency_key=idempotency_key,
                             payload_hash=body_hash, result_json=encoded(result), created_at=stamp()))
    db.commit()
    return result


def cancel_or_reject(db, actor_id, change_id, payload, *, reject=False):
    from app.services.iam import _add_event, _increment_revision
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    row = load_change(db, change_id)
    ensure_reader(db, actor, row.target_user_id)
    if row.revision != payload.expected_request_revision:
        fail("DRAFT_CONFLICT", "变更单已变化")
    from app.services.identity_policy import is_group_manager
    if not is_group_manager(actor) and actor_id != row.requester_user_id:
        fail("OUTSIDE_MANAGEABLE_SCOPE", "只能撤回自己的未批准申请", 403)
    if reject and not is_group_manager(actor):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "需要有权管理员驳回", 403)
    if row.lifecycle_state == "scheduled" and not reject:
        if not is_group_manager(actor):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "已批准计划须由有权管理员取消", 403)
        if instant(row.effective_at) <= utc_now():
            fail("CHANGE_ALREADY_EFFECTIVE", "计划已生效，请办理新的反向变更")
        result = json.loads(row.result_json)
        profile = db.get(EmployeeProfile, row.target_user_id)
        revision = db.get(AuthUserAuthorizationRevision, row.target_user_id)
        if profile.identity_version != result["identity_version"] or not revision or revision.revision != result["authorization_version"]:
            fail("SOURCE_CHANGED", "人员已有后续变更，不能还原旧时间线")
        if result["assignment_id"]:
            new = db.get(EmployeeAssignment, result["assignment_id"])
            new.lifecycle_state = "revoked"
            new.revoked_at = stamp()
            new.revision += 1
        if result["source_assignment_id"]:
            old = db.get(EmployeeAssignment, result["source_assignment_id"])
            if old.revision != result["source_revision"] or old.valid_until != row.effective_at:
                fail("SOURCE_CHANGED", "原任职结束时间已变化")
            old.valid_until = result["old_source_until"]
            old.revision += 1
        for override_id, previous_until in result.get("exception_before", {}).items():
            override = db.get(AuthUserPermissionOverride, override_id)
            if not override or override.valid_until != row.effective_at:
                fail("SOURCE_CHANGED", "例外授权已变化，不能还原旧计划")
            override.valid_until = previous_until
        profile.identity_version += 1
        _increment_revision(db, row.target_user_id)
        ensure_admin_survives(db)
    elif row.lifecycle_state not in {"draft", "pending_approval"}:
        fail("CHANGE_ALREADY_EFFECTIVE", "已生效变更须通过新变更办理")
    row.lifecycle_state = "rejected" if reject else "cancelled"
    row.status = "rejected"
    row.decision_comment = payload.reason
    row.revision += 1
    _add_event(db, actor_id, "identity_" + row.lifecycle_state, "identity_change", row.id,
               target_user_id=row.target_user_id, reason=payload.reason, access_request_id=row.id)
    db.commit()
    return result_out(row)
