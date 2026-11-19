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


def plan_role_bindings(db, actor, org, bindings, dependencies, scopes):
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    roles = []
    for binding in bindings:
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
            scopes.append((business_org.id, factory, binding.department))
            _ensure_scope_applicable(role_scope_policy(definition["role_code"]), factory, binding.department, subject=definition["role_name"])
        version = snapshot_role(db, binding.role_id, actor.id)
        if binding.role_version_id and version.id != binding.role_version_id:
            fail("ROLE_VERSION_CHANGED", "权限包已发布新版本，请重新预览")
        roles.append({**definition, "version_id": version.id, "hash": version.definition_hash,
                      "factories": factories, "department": binding.department})
    return roles


def prepare(db, row, actor):
    from app.services.auth import build_auth_context
    from app.services.iam import _get_revision
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    if row.request_type == "identity:adjust_packages" or row.id.startswith(("studio-confirm-", "studio-action-")):
        from app.services.access_studio import require_studio_writes
        from app.services.iam import _has_scoped_permission
        require_studio_writes()
        if not _has_scoped_permission(db, actor.id, "system:access_manage"):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "需要权限配置办理权限", 403)
        if row.id.startswith("studio-action-") and actor.id == row.target_user_id:
            fail("SELF_ESCALATION", "本人的任职或账号状态须由其他管理员办理", 403)
    if row.request_type == "identity:adjust_packages":
        from app.schemas.access_studio import StudioChange
        payload = StudioChange.model_validate_json(row.payload_json)
    else:
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
    if profile.identity_mode != "v2" and (row.id.startswith("studio-action-") or
            payload.request_type not in {"confirm_identity", "freeze", "unfreeze", "leave"}):
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
    if source and payload.request_type in {"primary_assignment_transfer", "end_assignment", "upgrade_packages"}:
        if not (instant(source.valid_from) <= effective and (not source.valid_until or effective < instant(source.valid_until))):
            fail("SOURCE_CHANGED", "来源任职在生效时点无效")
        if payload.request_type == "primary_assignment_transfer" and not source.is_primary:
            fail("INVALID_CHANGE", "调动的来源必须为主职", 422)
        if row.id.startswith("studio-action-") and payload.request_type == "end_assignment" and source.is_primary:
            fail("INVALID_CHANGE", "结束兼任需要明确选择副职，主职请单独办理调动或离职", 422)
    if row.id.startswith("studio-action-") and payload.request_type in {"freeze", "add_assignment", "end_assignment"} and (
            user.status != "active" or profile.employment_status != "active"):
        fail("INACTIVE_EMPLOYEE", "此操作仅适用于启用且在职的人员", 422)
    roles = []
    dependencies = {"identity": profile.identity_version, "authorization": revision, "source": source.revision if source else None,
                    "actor_authorization": actor.authorization_version, "actor_identity": actor.identity["effective_context_key"],
                    "missing_profile": missing_profile}
    authorization_deadline = None
    if payload.request_type in {"adjust_packages", "confirm_identity"} or row.id.startswith("studio-action-"):
        subject = build_auth_context(db, user, at=effective)
        upcoming = [instant(i["next_transition_at"]) for i in (actor.identity, subject.identity) if i.get("next_transition_at")]
        authorization_deadline = min(upcoming, default=None)
        if payload.request_type == "adjust_packages" or row.id.startswith("studio-action-"):
            dependencies["target_context"] = [subject.identity["effective_context_key"], subject.identity.get("next_transition_at")]
    from app.models.identity import IamDelegation
    dependencies["delegations"] = sorted((d.id, d.revision, d.status, d.role_ids_json, d.factory_ids_json)
        for d in db.scalars(select(IamDelegation).where(IamDelegation.user_id == actor.id)))
    scopes = []
    scopes.extend((a["org_unit_id"], a["factory_id"], a["department_code"]) for a in identity["assignments"]
                  if a["state"] in {"current", "scheduled"} and a["employment_epoch"] == profile.employment_epoch)
    from app.services.identity_policy import additional_source_scopes
    scopes.extend((f, f, d) for f, d in additional_source_scopes(db, [user.id]).get(user.id, set()))
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
        roles = plan_role_bindings(db, actor, org, spec.role_bindings, dependencies, scopes)
        if row.id.startswith("studio-action-") and roles:
            from app.services.iam import _ensure_permission_catalog_reader
            _ensure_permission_catalog_reader(db, actor)
            for role in roles:
                for factory in role["factories"]:
                    target = db.get(IamOrgDepartment, (factory, role["department"]))
                    if target is None or target.status != "active":
                        fail("INVALID_SCOPE", "所选业务厂区的作用部门不可用", 422)
                    dependencies.setdefault("target_departments", []).append([factory, target.department_code, target.revision])
        dependencies["roles"] = [(r["role_id"], r["hash"]) for r in roles]
    if payload.request_type == "upgrade_packages":
        for meta in db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.assignment_id == source.id,
                                                                    AuthRoleBindingMetadata.state == "active")):
            if meta.valid_until and instant(meta.valid_until) <= effective:
                continue
            binding = db.get(AuthUserRole, meta.user_role_id)
            version = snapshot_role(db, binding.role_id, actor.id)
            dependencies.setdefault("upgrades", []).append([binding.id, version.id, version.definition_hash])
            definition = role_definition(db, binding.role_id)
            if definition["role_code"] == "admin" or any(p.startswith("system:") for p in definition["permissions"]):
                fail("ADMINISTRATION_SEPARATE", "升级不能把系统管理权附加到普通任职，请独立办理", 422)
            factories = json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json is not None else (
                ["*"] if definition["scope_mode"] == "cross_factory_operate" else [binding.factory_id])
            scopes.extend((factory, factory, binding.department) for factory in factories)
            roles.append({**definition, "factories": factories})
    if payload.request_type == "adjust_packages":
        from app.services.access_studio import plan_delta
        roles = plan_delta(db, row, actor, user, profile, source, payload, effective, dependencies, scopes)
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
        if any(d.decision != "keep_original_scope" for d in payload.exception_decisions):
            fail("MIGRATION_MUST_PRESERVE", "历史核实须保留全部个人允许，完成后请另办调整", 422)
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
            "scopes": scopes, "identity": identity, "user": user, "authorization_deadline": authorization_deadline}


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
                from app.services.identity_review_notifications import close
                close(db, pending.id)
        profile.employment_epoch += 1
        from app.services.position_reviews import invalidate_obsolete_tx
        db.flush()
        invalidate_obsolete_tx(db, user.id, actor.id)
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
                if not meta.role_version_id:
                    meta.role_version_id = snapshot_role(db, binding.role_id, actor.id).id
                meta.employment_epoch = profile.employment_epoch
                meta.source_type = disposition.source
                meta.version = (meta.version or 0) + 1
            for override in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == user.id)):
                override.employment_epoch = profile.employment_epoch
    if kind == "adjust_packages":
        from app.services.access_studio import apply_delta
        apply_delta(db, row, actor, plan)
        new_id = plan["package_evidence"].get("transfer", {}).get("assignment_id")
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
    return {**({"package_changes": plan["package_evidence"]} if kind == "adjust_packages" else {}),
            "assignment_id": new_id, "source_assignment_id": source.id if source else None, "old_source_until": old_end,
            "exception_before": exception_before,
            "source_revision": source.revision if source else None, "identity_version": profile.identity_version,
            "authorization_version": revision.revision, "identity": identity}


def access_matrix(db, user_id, at, *, include_provenance=False):
    from app.models.auth import AuthPermission
    from app.services.auth import authorization_decision, build_auth_context, has_permission_in_scope
    from app.services.identity_catalog import DEPARTMENTS, FACTORIES
    context = build_auth_context(db, db.get(AuthUser, user_id), at=at)
    provenance = {}
    if include_provenance:
        bindings = select(AuthUserRole.id, AuthUserRole.role_id, AuthUserRole.factory_id, AuthUserRole.department,
            AuthRoleBindingMetadata.assignment_id, AuthRoleBindingMetadata.role_version_id, AuthRoleBindingMetadata.scope_ceiling_json,
            AuthRoleBindingMetadata.valid_from, AuthRoleBindingMetadata.valid_until, AuthRoleBindingMetadata.source_type,
            AuthRoleBindingMetadata.source_id, AuthRoleBindingMetadata.employment_epoch).outerjoin(AuthRoleBindingMetadata,
            AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).where(AuthUserRole.user_id == user_id)
        overrides = select(AuthUserPermissionOverride.id, AuthUserPermissionOverride.assignment_id,
            AuthUserPermissionOverride.permission_id, AuthUserPermissionOverride.factory_id, AuthUserPermissionOverride.department,
            AuthUserPermissionOverride.effect, AuthUserPermissionOverride.valid_from, AuthUserPermissionOverride.valid_until,
            AuthUserPermissionOverride.lifecycle_policy, AuthUserPermissionOverride.employment_epoch).where(
            AuthUserPermissionOverride.user_id == user_id)
        for query in (bindings, overrides):
            for values in db.execute(query):
                provenance[values[0]] = tuple(values)
    # Empty string is the wire key for an omitted department. Send None to
    # both evaluators. A caller explicitly supplying "*" asks a different question.
    factories = {*FACTORIES, "*", "group-management", *db.scalars(select(IamOrgUnit.id).where(IamOrgUnit.kind != "group"))}
    departments = {*DEPARTMENTS, "system", "*", "", *db.scalars(select(IamOrgDepartment.department_code).distinct())}
    for source in (*context.grants, *context.overrides):
        if source.factory_id:
            factories.add(source.factory_id)
        if source.department:
            departments.add(source.department)
    for grant in context.grants:
        factories.update(grant.factory_ceiling or ())
    # Retired codes can still be present in a historical grant. The runtime
    # compatibility evaluator and canonical IAM may treat them differently.
    permissions = set(db.scalars(select(AuthPermission.code)))
    permissions.update(code for grant in context.grants for code in grant.permissions)
    permissions.update(o.permission_code for o in context.overrides)
    result, configured = {}, set()
    for factory in factories:
        for department in departments:
            for permission in permissions:
                key = (permission, factory, department)
                allowed, _, ids, _ = authorization_decision(context, permission, factory, department or None, at=at)
                if allowed:
                    result[key] = tuple(provenance.get(i, i) for i in ids) if include_provenance else ids
                if has_permission_in_scope(context, permission, factory, department or None, at=at):
                    configured.add(key)
    return result, configured


def simulate_change(db, actor, row, *, transient=False):
    from app.services.identity_handover import assess
    persistent_plan = None
    studio_action = row.id.startswith("studio-action-")
    if not transient and not studio_action and row.request_type not in {"identity:adjust_packages", "identity:confirm_identity"}:
        persistent_plan = prepare(db, row, actor)
    with db.begin_nested() as simulation:
        if transient:
            db.add(row)
            db.flush()
        plan = persistent_plan or prepare(db, row, actor)
        at = instant(plan["effective"])
        before, configured_before = access_matrix(db, row.target_user_id, at,
            include_provenance=row.request_type == "identity:adjust_packages" or row.id.startswith("studio-confirm-"))
        boundaries = {}
        if row.request_type == "identity:confirm_identity":
            windows = [
                select(AuthRoleBindingMetadata.valid_from, AuthRoleBindingMetadata.valid_until)
                    .join(AuthUserRole, AuthUserRole.id == AuthRoleBindingMetadata.user_role_id)
                    .where(AuthUserRole.user_id == row.target_user_id),
                select(AuthUserPermissionOverride.valid_from, AuthUserPermissionOverride.valid_until)
                    .where(AuthUserPermissionOverride.user_id == row.target_user_id),
                select(EmployeeAssignment.valid_from, EmployeeAssignment.valid_until)
                    .where(EmployeeAssignment.user_id == row.target_user_id)]
            points = {instant(value) for query in windows for period in db.execute(query) for value in period if value}
            if plan["payload"].new_assignment.valid_until:
                points.add(instant(plan["payload"].new_assignment.valid_until))
            instants = {point + timedelta(microseconds=offset) for point in points if point > at for offset in (-1, 0, 1)}
            for point in sorted(instants):
                canonical, configured = access_matrix(db, row.target_user_id, point)
                boundaries[point] = (set(canonical), configured)
        apply_plan(db, row, actor, plan)
        post_denials = []
        if transient:
            from app.services.position_workbench_read import current_sources
            post_denials = current_sources(db, row.target_user_id)[2]
        after, configured_after = access_matrix(db, row.target_user_id, at,
            include_provenance=row.request_type == "identity:adjust_packages" or row.id.startswith("studio-confirm-"))
        for point, expected in boundaries.items():
            canonical, configured = access_matrix(db, row.target_user_id, point)
            if expected != (set(canonical), configured):
                fail("MIGRATION_PERMISSION_DRIFT", "确认任职会改变未来授权边界上的实际权限，请重新核实")
        if row.request_type == "identity:adjust_packages" or studio_action:
            ensure_admin_survives(db)
        after_identity = resolve_identity_at(db, row.target_user_id, at)
        simulation.rollback()
    title_only = row.request_type == "identity:adjust_packages" and not any(plan["payload"].package_delta.model_dump().values())
    if (plan["payload"].request_type == "confirm_identity" or title_only) and (set(before) != set(after) or configured_before != configured_after):
        fail("MIGRATION_PERMISSION_DRIFT", "来源映射改变实际权限，请重新核实")
    if title_only:
        payload = plan["payload"]
        posting = payload.position_review.confirmed_profile if payload.position_review else payload.official_posting
        moving = posting and (posting.org_unit_id, posting.department_code) != (plan["source"].org_unit_id, plan["source"].department_code)
        if not moving and before != after:
            fail("MIGRATION_SOURCE_DRIFT", "仅更正岗位文字时，现有授权来源必须完整保留")
    from app.services.position_workbench_read import permission_tuples, permission_diff_risk
    from app.models.auth import AuthPermission
    permissions = {p.code: p for p in db.scalars(select(AuthPermission))}
    def tuples(keys):
        return permission_tuples(db, keys, permissions=permissions)
    summary = {"before_identity": plan["identity"], "after_identity": after_identity,
               "permission_diffs": {"added": tuples(after.keys() - before.keys()), "removed": tuples(before.keys() - after.keys()),
                                    "retained": tuples(after.keys() & before.keys()),
                                    "source_changed": tuples(k for k in after.keys() & before.keys() if after[k] != before[k])},
               "requires_approval": plan["requires_approval"], "high_risk": bool(after.keys() - before.keys()) or plan["payload"].request_type in {"leave", "freeze"},
               "handover_summary": assess(db, row.target_user_id), "effective_at": plan["effective"],
               "server_now": stamp(), "request_revision": row.revision, "explicit_denials": post_denials,
               "retained_sources": [o.id for o in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == row.target_user_id, AuthUserPermissionOverride.status == "active"))
                                    if o.id not in {d.override_id for d in plan["payload"].exception_decisions if d.decision == "end"}]}
    if studio_action or row.request_type in {"identity:confirm_identity", "identity:adjust_packages"}:
        summary["high_risk"] |= permission_diff_risk(db, summary["permission_diffs"], permissions)
    if row.request_type == "identity:adjust_packages":
        summary["requires_empty_confirmation"] = plan["dependencies"]["clears_assignment_packages"]
        summary["high_risk"] |= summary["requires_empty_confirmation"] or plan["dependencies"]["edits_high_risk"]
    dependencies = plan["dependencies"]
    if (row.request_type == "identity:adjust_packages" or studio_action) and row.lifecycle_state == "pending_approval":
        from app.services.access_studio import submission_hash
        if json.loads(row.result_json or "{}").get("submitted_plan_hash") != submission_hash(dependencies, summary):
            fail("AUTHORIZATION_CHANGED", "提交审核后的人员、方案或权限差异已变化，请退回重新办理")
    fingerprint = digest({"payload": row.payload_json, "revision": row.revision, "dependencies": dependencies})
    return summary, fingerprint, dependencies


def preview_change(db, actor_id, change_id):
    from app.services.iam import _store_preview
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    row = load_change(db, change_id)
    ensure_reader(db, actor, row.target_user_id)
    if row.lifecycle_state not in {"draft", "pending_approval"}:
        fail("CHANGE_STATE_CONFLICT", "此变更已处理")
    summary, fingerprint, dependencies = simulate_change(db, actor, row)
    token, expires = _store_preview(db, actor_id, "identity_change", row.id, row.revision,
        {"fingerprint": fingerprint, "dependencies": dependencies, "effective_at": summary["effective_at"]}, summary)
    db.commit()
    return {**summary, "preview_token": token, "expires_at": expires, "preview_fingerprint": fingerprint}


def commit_change(db, actor_id, change_id, payload, idempotency_key, *, approving=False):
    result = commit_change_tx(db, actor_id, change_id, payload, idempotency_key, approving=approving)
    db.commit()
    return result


def commit_change_tx(db, actor_id, change_id, payload, idempotency_key, *, approving=False):
    """Flush-only core. The caller owns commit and rolls back on any exception."""
    from app.services.iam import _load_preview
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
    studio_command = row.request_type in {"identity:adjust_packages", "identity:confirm_identity"} or row.id.startswith("studio-action-")
    if studio_command:
        checked, _, _ = simulate_change(db, actor, row)
        for field in ("permission_diffs", "high_risk", "requires_approval", "requires_empty_confirmation"):
            if checked.get(field) != summary.get(field):
                fail("AUTHORIZATION_CHANGED", "预览后的实际权限、风险或审批条件已变化，请重新核对")
    plan = prepare(db, row, actor)
    if evidence["fingerprint"] != digest({"payload": row.payload_json, "revision": row.revision, "dependencies": plan["dependencies"]}):
        fail("AUTHORIZATION_CHANGED", "预览后的授权或组织已变化，请重新预览")
    if studio_command:
        if plan["requires_approval"] != checked["requires_approval"]:
            fail("AUTHORIZATION_CHANGED", "办理权限已变化，请重新预览")
        plan["effective"] = checked["effective_at"]
        plan["verified_diffs"] = checked["permission_diffs"]
    independent_review = row.request_type == "identity:adjust_packages" or row.id.startswith(("studio-confirm-", "studio-action-"))
    if approving and (plan["requires_approval"] or actor_id == row.requester_user_id and (row.target_user_id == actor_id or independent_review)):
        fail("GRANT_NOT_DELEGABLE", "需要有完整授权范围的独立管理员审核", 403)
    if summary["high_risk"] and not payload.confirm_high_risk:
        fail("CONFIRM_HIGH_RISK", "请确认预览中的新增权限或停止访问影响", 422)
    # Immediate changes begin at the instant confirmed in the preview; future
    # plans that passed their boundary while awaiting approval require repreview.
    if not studio_command:
        plan["effective"] = evidence["effective_at"]
    if plan["payload"].effective_at and instant(plan["effective"]) <= utc_now():
        fail("SOURCE_CHANGED", "预约生效点已过，请重新安排")
    preview.consumed_at = stamp()
    plan["command_id"] = idempotency_key
    result = apply_or_submit(db, row, actor, plan)
    db.add(IamMutationReceipt(id=uuid4().hex, actor_id=actor_id, operation=operation, idempotency_key=idempotency_key,
                             payload_hash=body_hash, result_json=encoded(result), created_at=stamp()))
    db.flush()
    return result


def apply_or_submit(db, row, actor, plan):
    from app.services.iam import _add_event
    from app.services.identity_handover import persist_items
    actor_id = actor.id
    if plan["requires_approval"]:
        row.lifecycle_state = "pending_approval"
        row.submitted_at = stamp()
        db.add(IamOutbox(id=f"identity-review-{row.id}", aggregate_id=row.id, kind="identity_change_submitted",
                        payload_json=encoded({"change_id": row.id}), created_at=stamp()))
    else:
        before = resolve_identity_at(db, row.target_user_id)
        result = apply_plan(db, row, actor, plan)
        if "verified_diffs" in plan:
            diffs = plan["verified_diffs"]
            result["permission_diffs"] = {k: diffs[k] for k in ("added", "removed", "source_changed")}
            result["retained_count"] = len(diffs["retained"])
            if row.request_type == "identity:adjust_packages":
                result["reviewed_scopes"] = sorted(set(plan["scopes"]))
        ensure_admin_survives(db)
        if row.request_type == "identity:adjust_packages" and plan["payload"].position_review:
            from app.services.access_studio_reviews import complete_review
            complete_review(db, row, actor, plan)
        row.lifecycle_state = "scheduled" if plan["scheduled"] else "applied"
        row.status = "approved"
        from app.services.identity_review_notifications import close
        close(db, row.id)
        row.decision_by_user_id = actor_id
        row.decided_at = stamp()
        row.effective_at = plan["effective"]
        result["handover"] = persist_items(db, row)
        row.result_json = encoded(result)
        _add_event(db, actor_id, "identity_" + plan["payload"].request_type, "identity_change", row.id,
                   target_user_id=row.target_user_id, before=before, after=result, reason=row.reason, access_request_id=row.id)
        db.add(IamOutbox(id=f"identity-notify-{row.id}", aggregate_id=row.id, kind="identity_changed",
                        payload_json=encoded({"user_id": row.target_user_id, "change_id": row.id}), created_at=stamp()))
    row.revision += 1
    row.updated_at = stamp()
    if plan["authorization_deadline"] and plan["authorization_deadline"] <= utc_now():
        fail("AUTHORIZATION_CHANGED", "办理过程中授权已到达生效或结束边界，请重新预览")
    return result_out(row)


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
    from app.services.identity_review_notifications import close
    close(db, row.id)
    row.status = "rejected"
    row.updated_at = row.decided_at = stamp()
    row.decision_by_user_id = actor_id
    row.decision_comment = payload.reason
    row.revision += 1
    _add_event(db, actor_id, "identity_" + row.lifecycle_state, "identity_change", row.id,
               target_user_id=row.target_user_id, reason=payload.reason, access_request_id=row.id)
    db.commit()
    return result_out(row)
