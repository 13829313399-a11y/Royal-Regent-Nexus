"""Flush-only plans used by both SAVEPOINT preview and the owning commit."""
import json
from uuid import uuid4
from sqlalchemy import select
from app.models.auth import (AuthAccessRequest, AuthRoleBindingMetadata, AuthUser, AuthUserRole,
    AuthUserPermissionOverride, EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamRoleVersion
from app.models.position_review import PositionReview
from app.schemas.identity import IdentityChange
from app.schemas.system import RegistrationApproveRequest, RegistrationProfileCorrection
from app.services import identity_changes as changes, position_reviews as reviews
from app.services.identity_policy import ensure_change_authority, fail
from app.services.identity_resolver import instant, resolve_identity_at, stamp, utc_now
from app.services.identity_sources import definition_hash, role_definition, snapshot_role
from app.services.position_workbench_read import current_sources


def role_candidate(db, actor, target_id, selected, position):
    from app.services.system_positions import get_system_position
    from app.services.identity_catalog import FACTORIES
    from app.services.permission_scope_policy import role_scope_policy
    from app.services.iam import _ensure_scope_applicable
    org = reviews.validate_position(db, position)
    fixed = get_system_position(selected.role_id)
    if fixed is None or selected.permission_department != fixed.department:
        fail("INVALID_PACKAGE", "请选择有效内置方案及其真实作用部门", 422)
    definition = role_definition(db, fixed.role_id)
    if definition_hash(definition) != selected.definition_hash:
        fail("ROLE_VERSION_CHANGED", "内置方案已变化，请重新读取并预览")
    if any(code.startswith("system:") for code in definition["permissions"]):
        fail("ADMINISTRATION_SEPARATE", "系统管理权须独立办理", 422)
    scope = selected.factory_scope
    factories = ([org.legacy_factory_id] if scope.kind == "home" else sorted(FACTORIES)
                 if scope.kind == "all_current" else sorted(set(scope.factory_ids)))
    if not factories or any(f not in FACTORIES for f in factories):
        fail("INVALID_SCOPE", "请选择具体业务厂区；总务不是所有厂区", 422)
    for factory in factories:
        business = db.get(IamOrgUnit, factory)
        if not business or business.status != "active":
            fail("INVALID_SCOPE", "业务厂区不可用", 422)
        _ensure_scope_applicable(role_scope_policy(definition["role_code"]), factory, fixed.department, subject=fixed.name)
    result = {**definition, "factories": factories, "department": fixed.department}
    ensure_change_authority(db, actor, target_id,
        [(org.id, org.legacy_factory_id, position.department_code), *[(f, f, fixed.department) for f in factories]], [result])
    return result, org


def selected_role(db, actor, target_id, selected, position):
    result, org = role_candidate(db, actor, target_id, selected, position)
    fixed_id = result["role_id"]
    version = snapshot_role(db, fixed_id, actor.id)
    if selected.role_version_id and version.id != selected.role_version_id:
        fail("ROLE_VERSION_CHANGED", "方案版本已变化，请重新预览")
    return {**result, "version_id": version.id, "hash": version.definition_hash}, org


def make_plan(db, actor, row, payload):
    from app.services.iam import _get_revision
    org = reviews.validate_position(db, payload.confirmed_profile)
    user = db.get(AuthUser, row.user_id)
    position = isinstance(row, PositionReview)
    if user.status != ("active" if position else "pending"):
        fail("ACCOUNT_UNAVAILABLE", "目标账号当前不可办理")
    roles = []
    if payload.package_selection:
        role, _ = selected_role(db, actor, user.id, payload.package_selection, payload.confirmed_profile)
        roles = [role]
    if not position:
        if payload.decision != "apply_package":
            fail("INVALID_DECISION", "注册必须通过并分配内置方案", 422)
        if payload.independent_allow_decisions:
            fail("INVALID_DECISION", "注册不能携带在职独立授权处置", 422)
        from app.schemas.position_review import RegistrationDetails
        contact = payload.registration_details_correction or RegistrationDetails(
            display_name=row.display_name, phone=row.phone, email=row.email)
        return {"kind": "registration", "role": roles[0], "registration": RegistrationApproveRequest(
            system_position_role_id=roles[0]["role_id"], review_comment="人员与权限工作台确认",
            profile=RegistrationProfileCorrection(**contact.model_dump(), org_unit_id=org.id,
                factory_id=org.legacy_factory_id, business_factory_ids=roles[0]["factories"],
                department=payload.confirmed_profile.department_code, position=payload.confirmed_profile.position))}
    if payload.registration_details_correction is not None:
        fail("INVALID_FIELD", "岗位更新不能修改注册联系人", 422)
    identity = resolve_identity_at(db, user.id)
    if identity["employment_epoch"] != row.employment_epoch or identity["employment_status"] == "left":
        fail("SOURCE_CHANGED", "任职周期已改变，此岗位更新不再适用")
    if identity["identity_mode"] != "v2":
        fail("LEGACY_SOURCE_REVIEW_REQUIRED", "请先核实历史来源；不能清理旧授权来代替核实")
    source_info = identity["primary_assignment"]
    if not source_info:
        fail("SOURCE_CHANGED", "当前没有主职，请先在更多管理中核实")
    source = db.get(EmployeeAssignment, source_info["id"])
    if payload.decision == "apply_package":
        scheduled = list(db.scalars(select(AuthRoleBindingMetadata).where(
            AuthRoleBindingMetadata.assignment_id == source.id, AuthRoleBindingMetadata.state == "active")))
        if any(m.valid_from and instant(m.valid_from) > utc_now() for m in scheduled):
            fail("SCHEDULED_SOURCE_REVIEW_REQUIRED", "主职有尚未生效的授权，请先在更多管理中核实预约；未替换任何来源")
    _, independent, _ = current_sources(db, user.id)
    decisions = {d.override_id: d.decision for d in payload.independent_allow_decisions}
    if set(decisions) != {d["override_id"] for d in independent}:
        fail("EXCEPTION_DECISION_REQUIRED", "请逐项明确保留或终止当前独立允许", 422)
    if payload.decision == "keep_permissions" and "end" in decisions.values():
        fail("KEEP_PERMISSION_DRIFT", "保留原权限不能终止独立允许", 422)
    transfer = (source.org_unit_id, source.department_code) != (org.id, payload.confirmed_profile.department_code)
    data = {"request_type": "primary_assignment_transfer" if transfer else "profile_correction",
        "target_user_id": user.id, "reason": "岗位更新办理", "base_identity_version": identity["identity_version"],
        "base_authorization_version": _get_revision(db, user.id), "source_assignment_id": source.id,
        "exception_decisions": [d.model_dump() for d in payload.independent_allow_decisions]}
    if transfer:
        data["new_assignment"] = {"org_unit_id": org.id, "department_code": payload.confirmed_profile.department_code,
            "official_position_title": payload.confirmed_profile.position, "role_bindings": [],
            "valid_until": source.valid_until}
    else:
        data["official_position_title"] = payload.confirmed_profile.position
    change = AuthAccessRequest(id="identity-" + uuid4().hex, requester_user_id=actor.id, target_user_id=user.id,
        request_type="identity:" + data["request_type"], lifecycle_state="draft", status="pending", revision=1,
        reason="岗位更新办理", payload_json=changes.encoded(IdentityChange.model_validate(data).model_dump(mode="json")),
        created_at=stamp(), updated_at=stamp())
    plan = changes.prepare(db, change, actor)
    if plan["requires_approval"]:
        fail("INDEPENDENT_REVIEW_REQUIRED", "需要有完整转授范围的独立管理员办理", 403)
    if transfer and payload.decision == "keep_permissions":
        # Keeping means preserving the exact pinned definition and ceiling. A
        # department change cannot silently retarget old package departments.
        if source.department_code != payload.confirmed_profile.department_code:
            fail("KEEP_PERMISSION_INCOMPATIBLE", "部门改变后需要明确选择方案和业务范围，不能直接保留", 422)
        for binding, meta, version in db.execute(select(AuthUserRole, AuthRoleBindingMetadata, IamRoleVersion)
                .join(AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id)
                .outerjoin(IamRoleVersion, IamRoleVersion.id == AuthRoleBindingMetadata.role_version_id)
                .where(AuthUserRole.user_id == user.id, AuthRoleBindingMetadata.assignment_id == source.id,
                       AuthRoleBindingMetadata.state == "active")):
            if not version or meta.scope_ceiling_json is None or meta.valid_until or (meta.valid_from and instant(meta.valid_from) > utc_now()):
                fail("KEEP_PERMISSION_INCOMPATIBLE", "现有来源包含未固定范围或时间限制，请在更多管理中核实")
            definition = json.loads(version.definition_json)
            roles.append({**definition, "factories": [binding.factory_id], "ceiling": json.loads(meta.scope_ceiling_json),
                "department": binding.department, "version_id": version.id, "hash": version.definition_hash})
    if roles:
        scopes = [*plan["scopes"], *[(f, f, role["department"]) for role in roles for f in role["factories"]]]
        ensure_change_authority(db, actor, user.id, scopes, roles)
    plan["roles"] = roles if transfer else []
    return {"kind": "transfer" if transfer else "replace" if payload.decision == "apply_package" else "correction",
        "change": change, "plan": plan, "roles": roles, "source": source}


def install_roles_tx(db, actor, user_id, assignment, roles, *, reason):
    now = stamp()
    for role in roles:
        for factory in role["factories"]:
            binding = AuthUserRole(id="assignment-role-" + uuid4().hex, user_id=user_id,
                role_id=role["role_id"], factory_id=factory, department=role["department"])
            db.add(binding)
            db.flush()
            db.add(AuthRoleBindingMetadata(user_role_id=binding.id, assignment_id=assignment.id,
                role_version_id=role["version_id"], scope_ceiling_json=changes.encoded(role.get("ceiling", role["factories"])),
                employment_epoch=assignment.employment_epoch, state="active", source_type="assignment", source_id=assignment.id,
                valid_from=now, valid_until=assignment.valid_until or "", reason=reason,
                created_by_user_id=actor.id, approved_by_user_id=actor.id, created_at=now, updated_at=now))
    db.flush()


def apply_tx(db, actor, row, prepared):
    if prepared["kind"] == "registration":
        from app.services.system import approve_registration_with_system_position_tx
        approve_registration_with_system_position_tx(db, actor, row.id, prepared["registration"])
        profile = db.get(EmployeeProfile, row.user_id)
        assignment = db.get(EmployeeAssignment, profile.primary_assignment_id)
        # Registration adapter preserves all legacy contact/functional rules.
        # Replace ONLY its just-created primary bindings with the reviewed ceiling.
        for meta in db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.assignment_id == assignment.id,
                                                                    AuthRoleBindingMetadata.state == "active")):
            meta.state, meta.revoked_at = "revoked", stamp()
            meta.revoke_reason = "注册预览中明确的业务范围"
        install_roles_tx(db, actor, row.user_id, assignment, [prepared["role"]], reason="注册通过并分配权限")
        row.org_unit_id = prepared["registration"].profile.org_unit_id
        row.display_name = prepared["registration"].profile.display_name
        row.phone = prepared["registration"].profile.phone
        row.email = prepared["registration"].profile.email
        row.factory_id = prepared["registration"].profile.factory_id
        row.department = prepared["registration"].profile.department
        row.position = prepared["registration"].profile.position
        db.flush()
        return [assignment.source_request_id]
    change, plan = prepared["change"], prepared["plan"]
    db.add(change)
    db.flush()
    if prepared["kind"] == "transfer":
        # Install explicitly to preserve original ceilings for keep_permissions.
        plan["roles"] = []
    result = changes.apply_plan(db, change, actor, plan)
    if prepared["kind"] == "replace":
        for meta in db.scalars(select(AuthRoleBindingMetadata).where(AuthRoleBindingMetadata.assignment_id == prepared["source"].id,
                                                                    AuthRoleBindingMetadata.state == "active")):
            meta.state, meta.revoked_at, meta.revoked_by_user_id = "revoked", stamp(), actor.id
            meta.revoke_reason = "明确替换主职内置方案"
            meta.version += 1
        install_roles_tx(db, actor, row.user_id, prepared["source"], prepared["roles"], reason="替换主职内置方案")
    elif prepared["kind"] == "transfer":
        assignment = db.get(EmployeeAssignment, result["assignment_id"])
        install_roles_tx(db, actor, row.user_id, assignment, prepared["roles"], reason="岗位更新调动")
    change.lifecycle_state, change.status = "applied", "approved"
    change.decision_by_user_id, change.decided_at, change.effective_at = actor.id, stamp(), plan["effective"]
    change.result_json = changes.encoded(result)
    from app.services.identity_handover import persist_items
    from app.services.iam import _add_event
    result["handover"] = persist_items(db, change)
    change.result_json = changes.encoded(result)
    _add_event(db, actor.id, "position_" + prepared["kind"], "identity_change", change.id,
        target_user_id=row.user_id, before=plan["identity"], after=result, reason=change.reason, access_request_id=change.id)
    db.flush()
    return [change.id]
