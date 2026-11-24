"""Explicit changes to a single existing assignment. Previews never persist business rows."""
import json
from uuid import uuid4
from sqlalchemy import delete, select
from app.core.config import settings
from app.models.auth import AuthAccessRequest, AuthAuthorizationPreview, AuthRoleBindingMetadata, AuthUserPermissionOverride, AuthUserRole
from app.models.identity import EmployeeAssignment, IamMutationReceipt, IamOrgDepartment, IamOrgUnit, IamRoleVersion
from app.schemas.access_studio import LegacyConfirmation, PackageEdits, StudioChange, StudioDraft, StudioLifecycle
from app.services import identity_changes as changes
from app.services.auth import can
from app.services.identity_policy import ensure_reader, fail, fresh_actor, lock_mutation, require_writes
from app.services.identity_resolver import instant, stamp
from app.services.identity_sources import role_definition, snapshot_role

OPERATION = "access_studio"


def writes_enabled():
    return (settings.iam_access_studio_writes_enabled and settings.iam_identity_writes_enabled
            and settings.authz_mode == "enforce" and settings.authz_writes_enabled)


def require_studio_writes():
    require_writes()
    if not settings.iam_access_studio_writes_enabled:
        fail("ACCESS_STUDIO_DISABLED", "新版人工办理尚未开放", 503)


def plan_delta(db, row, actor, user, profile, source, payload, effective, dependencies, scopes):
    from app.services.iam import _ensure_permission_catalog_reader
    from app.services.iam_management_scopes import complete_scopes
    from app.services.system import role_is_high_risk
    if actor.id == user.id:
        fail("SELF_ESCALATION", "本人权限配置须由另一位管理员办理", 403)
    if user.status != "active" or profile.employment_status != "active":
        fail("INACTIVE_EMPLOYEE", "仅可配置在职且已启用的人员")
    if not source or instant(source.valid_from) > effective or (source.valid_until and instant(source.valid_until) <= effective):
        fail("SOURCE_CHANGED", "来源任职在办理时点无效")
    org = db.get(IamOrgUnit, source.org_unit_id)
    dept = db.get(IamOrgDepartment, (source.org_unit_id, source.department_code))
    if not org or not dept or org.status != "active" or dept.status != "active":
        fail("INVALID_ORG", "来源任职的组织或部门已停用")
    dependencies["organization"] = [org.id, org.revision, dept.revision]
    dependencies["employment_epoch"] = profile.employment_epoch
    # Time-limited changes need not bump an authorization revision. Pin every
    # target source, including scheduled, independent and explicitly denied ones.
    dependencies["source_metadata"] = [list(row) for row in db.execute(select(AuthUserRole.id,
        AuthRoleBindingMetadata.role_version_id, IamRoleVersion.definition_hash, AuthRoleBindingMetadata.scope_ceiling_json,
        AuthRoleBindingMetadata.assignment_id, AuthRoleBindingMetadata.employment_epoch, AuthRoleBindingMetadata.valid_from,
        AuthRoleBindingMetadata.valid_until, AuthRoleBindingMetadata.state, AuthRoleBindingMetadata.source_type)
        .outerjoin(AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id)
        .outerjoin(IamRoleVersion, IamRoleVersion.id == AuthRoleBindingMetadata.role_version_id)
        .where(AuthUserRole.user_id == user.id).order_by(AuthUserRole.id))]
    dependencies["assignment_windows"] = [list(row) for row in db.execute(select(EmployeeAssignment.id, EmployeeAssignment.revision,
        EmployeeAssignment.valid_from, EmployeeAssignment.valid_until, EmployeeAssignment.lifecycle_state,
        EmployeeAssignment.employment_epoch, EmployeeAssignment.org_unit_id, EmployeeAssignment.department_code)
        .where(EmployeeAssignment.user_id == user.id).order_by(EmployeeAssignment.id))]
    dependencies["exception_versions"] = [list(row) for row in db.execute(select(AuthUserPermissionOverride.id,
        AuthUserPermissionOverride.permission_id, AuthUserPermissionOverride.employment_epoch, AuthUserPermissionOverride.updated_at)
        .where(AuthUserPermissionOverride.user_id == user.id).order_by(AuthUserPermissionOverride.id))]
    edits = payload.package_delta
    scope_updates = {edit.binding_id: sorted(edit.factory_ids) for edit in edits.scope_updates}
    touched = set(edits.remove_binding_ids + edits.upgrade_binding_ids) | scope_updates.keys()
    posting = payload.official_posting
    if posting:
        from app.services.position_reviews import validate_position
        if not source.is_primary or payload.position_review:
            fail("INVALID_CHANGE", "直接调整正式组织和部门须选择主职并单独核对", 422)
        org = validate_position(db, posting)
        target = db.get(IamOrgDepartment, (org.id, posting.department_code))
        scopes.append((org.id, org.legacy_factory_id, target.department_code))
        dependencies["target_posting"] = [org.id, org.revision, target.department_code, target.revision]
    from app.services.access_studio_exceptions import plan_exceptions
    exception_edits = plan_exceptions(db, actor, user, edits, scopes)
    transfer = posting and (posting.org_unit_id, posting.department_code) != (source.org_unit_id, source.department_code)
    if not (payload.position_review or transfer or touched or edits.add_packages or exception_edits) and payload.official_position_title in (None, source.official_position_title):
        fail("NO_CHANGES", "请修改职位名称或明确选择需要调整的权限包", 422)
    if edits.add_packages or edits.upgrade_binding_ids:
        _ensure_permission_catalog_reader(db, actor)
    if payload.position_review:
        from app.services.access_studio_reviews import validate_link
        org = validate_link(db, actor, row, source, payload, dependencies, scopes)
    added = changes.plan_role_bindings(db, actor, org, edits.add_packages, dependencies, scopes)
    for role in added:
        for factory in role["factories"]:
            target_department = db.get(IamOrgDepartment, (factory, role["department"]))
            if not target_department or target_department.status != "active":
                fail("INVALID_SCOPE", "所选厂区的作用部门不可用", 422)
            dependencies.setdefault("target_departments", []).append([factory, role["department"], target_department.revision])
    new_keys = {(r["role_id"], r["department"], f) for r in added for f in r["factories"]}
    roles = list(added)
    risk = any(role_is_high_risk(db, r["role_id"]) for r in added)
    current = set()
    versions = []
    rows = db.execute(select(AuthUserRole, AuthRoleBindingMetadata).join(
        AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id).where(
        AuthUserRole.user_id == user.id, AuthRoleBindingMetadata.assignment_id == source.id,
        AuthRoleBindingMetadata.state == "active").order_by(AuthUserRole.id))
    for binding, meta in rows:
        if (meta.employment_epoch not in (None, profile.employment_epoch)
                or meta.valid_from and instant(meta.valid_from) > effective
                or meta.valid_until and instant(meta.valid_until) <= effective):
            continue
        current.add(binding.id)
        if binding.id not in edits.remove_binding_ids and (binding.role_id, binding.department, binding.factory_id) in new_keys:
            fail("DUPLICATE_BINDING", "该部门和厂区已有此权限包", 422)
        if binding.id not in touched:
            continue
        pinned = db.get(IamRoleVersion, meta.role_version_id) if meta.role_version_id else None
        if not pinned or pinned.role_id != binding.role_id or meta.source_type != "assignment":
            fail("SOURCE_CHANGED", "请选择具有完整固定版本的任职来源")
        previous = json.loads(pinned.definition_json)
        definition = role_definition(db, binding.role_id) if binding.id in edits.upgrade_binding_ids else previous
        if any(d["role_code"] == "admin" or any(p.startswith("system:") for p in d["permissions"])
               for d in (previous, definition)):
            fail("ADMINISTRATION_SEPARATE", "系统管理权须通过独立授权办理", 422)
        new_hash = None
        if binding.id in edits.upgrade_binding_ids:
            next_version = snapshot_role(db, binding.role_id, actor.id)
            if next_version.id == pinned.id:
                fail("VERSION_ALREADY_CURRENT", "所选来源已经使用当前版本", 422)
            new_hash = next_version.definition_hash
        factories = json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json is not None else (
            ["*"] if any(d["scope_mode"] != "own_factory" for d in (previous, definition)) else [binding.factory_id])
        if binding.id in scope_updates:
            from app.services.identity_catalog import FACTORIES
            from app.services.permission_scope_policy import role_scope_policy
            from app.services.iam import _ensure_scope_applicable
            proposed = scope_updates[binding.id]
            if meta.scope_ceiling_json is not None and sorted(factories) == proposed:
                fail("NO_CHANGES", "所选绑定的厂区上限没有变化", 422)
            for factory in proposed:
                business_org = db.get(IamOrgUnit, factory)
                target = db.get(IamOrgDepartment, (factory, binding.department))
                if factory not in FACTORIES or not business_org or business_org.status != "active" or not target or target.status != "active":
                    fail("INVALID_SCOPE", "所选厂区或作用部门不可用", 422)
                _ensure_scope_applicable(role_scope_policy(previous["role_code"]), factory, binding.department, subject=previous["role_name"])
                dependencies.setdefault("target_departments", []).append([factory, binding.department, target.revision, business_org.revision])
            factories = sorted(set(factories) | set(proposed))
        scopes.extend((f, f, binding.department) for f in factories)
        roles.append({**definition, "factories": factories, "department": binding.department})
        versions.append([binding.id, meta.version, pinned.id, new_hash, meta.scope_ceiling_json, meta.valid_from, meta.valid_until])
        risk |= role_is_high_risk(db, binding.role_id)
    if touched - current:
        fail("SOURCE_CHANGED", "所选权限来源已结束或不属于当前任职")
    required = complete_scopes((factory or organization, department) for organization, factory, department in scopes)
    if any(not can(actor, "system:user_manage", f, d) for f, d in required):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "目标业务范围超出可见人员范围", 403)
    dependencies.update(roles=[(r["role_id"], r["hash"]) for r in added], touched_versions=versions,
        clears_assignment_packages=bool(current) and current == set(edits.remove_binding_ids) and not added,
        edits_high_risk=risk or any(o["risk_level"] == "high" for o in exception_edits),
        exception_edits=exception_edits, current_binding_ids=sorted(current))
    return roles


def apply_delta(db, row, actor, plan):
    from app.services.position_workbench_plan import install_roles_tx
    source = plan["source"]
    payload = plan["payload"]
    edits = payload.package_delta
    at = plan["effective"]
    evidence = {"title_before": source.official_position_title, "removed": [], "upgraded": [], "added": []}
    official = payload.position_review.confirmed_profile if payload.position_review else payload.official_posting
    if official:
        if (source.org_unit_id, source.department_code) != (official.org_unit_id, official.department_code):
            from app.services.access_studio_reviews import continue_assignment
            source, evidence["transfer"] = continue_assignment(db, row, actor, source, official, at)
        if payload.position_review:
            evidence["position_review"] = payload.position_review.item_key
    for update in edits.scope_updates:
        meta = db.get(AuthRoleBindingMetadata, update.binding_id)
        before = json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json is not None else None
        after = sorted(update.factory_ids)
        meta.scope_ceiling_json, meta.updated_at = changes.encoded(after), at
        meta.version += 1
        evidence.setdefault("scope_updates", []).append({"binding_id": update.binding_id, "before": before, "after": after})
    from app.services.access_studio_exceptions import apply_exceptions
    apply_exceptions(db, actor, row, plan, evidence)
    for binding_id in edits.remove_binding_ids + edits.upgrade_binding_ids:
        meta = db.get(AuthRoleBindingMetadata, binding_id)
        item = {"binding_id": binding_id, "previous_version_id": meta.role_version_id}
        if binding_id in edits.remove_binding_ids:
            meta.state, meta.revoked_at, meta.revoked_by_user_id, meta.revoke_reason = "revoked", at, actor.id, row.reason
            evidence["removed"].append(item)
        else:
            binding = db.get(AuthUserRole, binding_id)
            meta.role_version_id = snapshot_role(db, binding.role_id, actor.id).id
            evidence["upgraded"].append({**item, "version_id": meta.role_version_id})
        meta.updated_at = at
        meta.version += 1
    for role in plan["roles"][:len(edits.add_packages)]:
        ids = install_roles_tx(db, actor, row.target_user_id, source, [role], reason=row.reason, effective_at=at)
        evidence["added"].append({"role_id": role["role_id"], "role_version_id": role["version_id"],
            "binding_ids": ids, "department": role["department"], "factory_ids": role["factories"]})
    if payload.official_position_title is not None:
        source.official_position_title = payload.official_position_title
    evidence["title_after"] = source.official_position_title
    source.revision += 1
    source.updated_at = at
    plan["package_evidence"] = evidence


def command_row(actor_id, user_id, draft, row_id):
    if isinstance(draft, (LegacyConfirmation, StudioLifecycle)):
        if draft.target_user_id != user_id:
            fail("INVALID_TARGET", "确认来源与目标人员不一致", 422)
        command = draft
    else:
        official = draft.position_review.confirmed_profile if draft.position_review else draft.official_posting
        if official:
            title = official.position
            if draft.official_position_title not in (None, title):
                fail("INVALID_CHANGE", "岗位单正式职位与人员配置不一致", 422)
            draft = draft.model_copy(update={"official_position_title": title})
        command = StudioChange(request_type="adjust_packages", target_user_id=user_id,
            package_delta=PackageEdits(**draft.model_dump(include=set(PackageEdits.model_fields))),
            **draft.model_dump(exclude=set(PackageEdits.model_fields)))
    return AuthAccessRequest(id=row_id, requester_user_id=actor_id, target_user_id=user_id, created_at=stamp(),
        updated_at=stamp(), status="pending", revision=1, lifecycle_state="draft", request_type="identity:" + command.request_type,
        reason=command.reason, payload_json=changes.encoded(command.model_dump(mode="json")))


def proposed_effect(summary):
    return changes.digest({key: summary.get(key, False) for key in ("permission_diffs", "high_risk", "requires_approval",
        "requires_empty_confirmation")})


def preview(db, actor_id, user_id, draft):
    from app.services.auth import now_text
    from app.services.iam import _store_preview
    require_studio_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    ensure_reader(db, actor, user_id)
    prefix = ("studio-confirm-" if isinstance(draft, LegacyConfirmation) else
              "studio-action-" if isinstance(draft, StudioLifecycle) else "identity-")
    row = command_row(actor.id, user_id, draft, prefix + uuid4().hex)
    summary, fingerprint, _ = changes.simulate_change(db, actor, row, transient=True)
    summary.update(allowed_to_commit=True, blocked_reasons=[])
    summary.setdefault("requires_empty_confirmation", False)
    # Reclaim only this feature's expired tokens and keep its persisted preview
    # free of personnel details, handover records and full permission matrices.
    db.execute(delete(AuthAuthorizationPreview).where(AuthAuthorizationPreview.target_type == OPERATION,
        AuthAuthorizationPreview.expires_at <= now_text()))
    token, expiry = _store_preview(db, actor.id, OPERATION, user_id, draft.base_authorization_version,
        {"kind": row.request_type, "draft": draft.model_dump(mode="json"), "row_id": row.id, "fingerprint": fingerprint},
        {"effect_hash": proposed_effect(summary)})
    db.commit()
    response = {key: summary[key] for key in ("permission_diffs", "high_risk", "server_now", "requires_approval",
        "requires_empty_confirmation", "explicit_denials", "allowed_to_commit", "blocked_reasons")}
    response["will_confirm_legacy"] = isinstance(draft, LegacyConfirmation)
    count = summary["handover_summary"]["count"]
    response["handover_summary"] = f"检测到 {count} 项内部报价责任，其他业务责任需要人工核对。"
    return {**response, "preview_token": token, "expires_at": stamp(instant(expiry))}


def submission_hash(dependencies, summary):
    # The reviewer has separate authority. Pin the submitted subject, sources,
    # versions and effective changes independently of either operator's grants.
    target = {k: v for k, v in dependencies.items() if k not in {"actor_identity", "actor_authorization", "delegations"}}
    return changes.digest({"target": target, "diffs": summary["permission_diffs"],
        "high_risk": summary["high_risk"], "empty": summary.get("requires_empty_confirmation", False)})


def receipt(db, actor_id, command_id):
    return db.scalar(select(IamMutationReceipt).where(IamMutationReceipt.actor_id == actor_id,
        IamMutationReceipt.operation == OPERATION, IamMutationReceipt.idempotency_key == str(command_id)))


def read_receipt(db, actor_id, command_id):
    fresh_actor(db, actor_id)
    saved = receipt(db, actor_id, command_id)
    return {"command_id": str(command_id), "status": "committed" if saved else "not_observed",
        "result": json.loads(saved.result_json) if saved else None}


def commit(db, actor_id, user_id, payload, command_id):
    from app.services.iam import _get_revision, _load_preview
    from app.services.identity_resolver import resolve_identity_at
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    body_hash = changes.digest({"user_id": user_id, **payload.model_dump()})
    saved = receipt(db, actor.id, command_id)
    if saved:
        if body_hash != saved.payload_hash:
            fail("IDEMPOTENCY_PAYLOAD_MISMATCH", "同一命令不能用于不同内容")
        return json.loads(saved.result_json)
    require_studio_writes()
    ensure_reader(db, actor, user_id)
    token, evidence, old = _load_preview(db, payload.preview_token, actor_id, OPERATION, user_id)
    model = (LegacyConfirmation if evidence["kind"] == "identity:confirm_identity" else
             StudioDraft if evidence["kind"] == "identity:adjust_packages" else StudioLifecycle)
    row = command_row(actor.id, user_id, model.model_validate(evidence["draft"]), evidence["row_id"])
    current, fingerprint, _ = changes.simulate_change(db, actor, row, transient=True)
    if fingerprint != evidence["fingerprint"] or proposed_effect(current) != old.get("effect_hash"):
        fail("AUTHORIZATION_CHANGED", "实际权限、版本或审批条件已变化，请刷新并重新预览")
    if current.get("requires_empty_confirmation") and not payload.confirm_empty_packages:
        fail("CONFIRM_EMPTY_PACKAGES", "请确认移除本任职的全部有效权限包", 422)
    if current["high_risk"] and not payload.risk_acknowledged:
        fail("CONFIRM_HIGH_RISK", "请确认预览中的权限变化", 422)
    db.add(row)
    db.flush()
    plan = changes.prepare(db, row, actor)
    if (plan["requires_approval"] != current["requires_approval"] or
            changes.digest({"payload": row.payload_json, "revision": row.revision, "dependencies": plan["dependencies"]}) != fingerprint):
        fail("AUTHORIZATION_CHANGED", "授权依赖已变化，请重新预览")
    plan["effective"] = current["effective_at"]
    plan["verified_diffs"] = current["permission_diffs"]
    plan["command_id"] = str(command_id)
    if plan["requires_approval"] and (row.request_type == "identity:adjust_packages" or row.id.startswith("studio-action-")):
        row.result_json = changes.encoded({"submitted_plan_hash": submission_hash(plan["dependencies"], current)})
    changes.apply_or_submit(db, row, actor, plan)
    token.consumed_at = stamp()
    result = {"command_id": str(command_id), "status": "committed", "decision": row.lifecycle_state,
        "change_id": row.id, "target_identity_version": resolve_identity_at(db, user_id)["identity_version"],
        "target_authorization_version": _get_revision(db, user_id), "committed_at": stamp(),
        "message": "已提交独立审核" if row.lifecycle_state == "pending_approval" else "办理已完成"}
    db.add(IamMutationReceipt(id=uuid4().hex, actor_id=actor.id, operation=OPERATION, idempotency_key=str(command_id),
        payload_hash=body_hash, result_json=changes.encoded(result), created_at=stamp()))
    db.commit()
    return result
