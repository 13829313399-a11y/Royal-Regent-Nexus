"""Registration remains one workflow; enrollment participates in its transaction."""
import json
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.models.auth import AuthAccessRequest, AuthRoleBindingMetadata, AuthUserRole, EmployeeProfile
from app.models.identity import EmployeeAssignment, IamOrgDepartment, IamOrgUnit
from app.services.identity_catalog import FACTORIES
from app.services.identity_policy import ensure_change_authority, fail, require_writes
from app.services.identity_resolver import stamp
from app.services.identity_sources import role_definition, snapshot_role


def registration_org(db, factory_id, org_unit_id, department):
    selected = org_unit_id or factory_id
    if factory_id and org_unit_id and factory_id != org_unit_id:
        fail("INVALID_ORG", "申报厂区与组织不一致", 422)
    org = db.get(IamOrgUnit, selected)
    dept = db.get(IamOrgDepartment, (selected, department))
    if not org or org.kind == "group" or org.status != "active" or not dept or dept.status != "active":
        fail("INVALID_ORG", "请选择有效组织与部门", 422)
    if org.kind == "functional_unit" and not settings.iam_identity_writes_enabled:
        fail("IDENTITY_WRITES_DISABLED", "集团职能注册尚未启用", 422)
    return org


def enroll_approved_registration(db, user, profile, registration, actor):
    if not settings.iam_identity_writes_enabled:
        return
    require_writes()
    if profile.identity_mode == "v2":
        fail("IDENTITY_CHANGE_REQUIRED", "已有正式任职，请通过人员变更办理")
    org = registration_org(db, profile.primary_factory_id, profile.primary_org_unit_id, profile.primary_department)
    bindings = list(db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)))
    role_plans = []
    for b in bindings:
        m = db.get(AuthRoleBindingMetadata, b.id)
        if m and m.state != "active":
            continue
        definition = role_definition(db, b.role_id)
        factories = list(FACTORIES) if definition["scope_mode"] != "own_factory" else [b.factory_id]
        role_plans.append({**definition, "factories": factories})
    ensure_change_authority(db, actor, user.id, [(org.id, org.legacy_factory_id, profile.primary_department)], role_plans)
    now = stamp()
    change = AuthAccessRequest(id=f"identity-{uuid4().hex}", requester_user_id=actor.id, target_user_id=user.id,
        request_type="identity:confirm_identity", lifecycle_state="applied", status="approved", reason="注册审核确认正式任职",
        effective_at=now, created_at=now, updated_at=now, decision_by_user_id=actor.id,
        payload_json=json.dumps({"registration_request_id": registration.id}), result_json="{}")
    db.add(change)
    db.flush()
    assignment = EmployeeAssignment(id=f"assignment-{uuid4().hex}", user_id=user.id, org_unit_id=org.id,
        department_code=profile.primary_department, official_position_title=profile.position, assignment_type="regular",
        is_primary=True, valid_from=now, employment_epoch=profile.employment_epoch, source_request_id=change.id,
        created_by=actor.id, confirmed_by=actor.id, created_at=now, updated_at=now)
    db.add(assignment)
    db.flush()
    for b in bindings:
        meta = db.get(AuthRoleBindingMetadata, b.id)
        if not meta or meta.state != "active":
            continue
        definition = role_definition(db, b.role_id)
        administration = definition["role_code"] == "admin" or any(p.startswith("system:") for p in definition["permissions"])
        meta.assignment_id = None if administration else assignment.id
        meta.role_version_id = snapshot_role(db, b.role_id, actor.id).id
        meta.employment_epoch = profile.employment_epoch
        meta.source_type = "system_administration" if administration else "assignment"
        meta.source_id = change.id if administration else assignment.id
    profile.identity_mode = "v2"
    profile.identity_version += 1
    profile.primary_assignment_id = assignment.id
    profile.primary_org_unit_id = org.id
    from app.services.iam import _add_event
    _add_event(db, actor.id, "identity_enrollment", "identity_change", change.id,
        target_user_id=user.id, reason=change.reason, access_request_id=change.id,
        after={"assignment_id": assignment.id, "registration_request_id": registration.id})


def approve_functional_registration(db, actor, registration, payload):
    from app.models.auth import AuthUser, AuthUserAuthorizationRevision
    from app.services.auth import now_text
    from app.services.system import mark_registration_notifications_handled, registration_request_to_out
    from app.services.system_positions import get_system_position
    from app.services.identity_policy import is_group_manager
    require_writes()
    if not is_group_manager(actor):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "集团职能入职须由集团管理员确认", 403)
    if registration.status != "pending" or payload.profile is None:
        fail("REGISTRATION_CHANGED", "注册申请已处理或缺少正式资料")
    spec = payload.profile
    org = registration_org(db, spec.factory_id, spec.org_unit_id, spec.department)
    factories = sorted(set(spec.business_factory_ids))
    if not factories or any(f not in FACTORIES for f in factories):
        fail("INVALID_SCOPE", "集团职能须明确选择业务厂区", 422)
    position = get_system_position(payload.system_position_role_id)
    if not position:
        fail("INVALID_ROLE", "请选择有效内置权限包", 422)
    definition = role_definition(db, position.role_id)
    if definition["role_code"] == "admin" or any(p.startswith("system:") for p in definition["permissions"]):
        fail("ADMINISTRATION_SEPARATE", "任职不得隐含系统管理权", 422)
    user = db.get(AuthUser, registration.user_id)
    profile = db.get(EmployeeProfile, user.id)
    if profile is None:
        profile = EmployeeProfile(user_id=user.id)
        db.add(profile)
    profile.primary_factory_id = ""
    profile.primary_org_unit_id = org.id
    profile.primary_department = spec.department
    profile.position = spec.position.strip()
    profile.phone, profile.email = spec.phone.strip(), spec.email.strip()
    profile.confirmation_status = "confirmed"
    profile.source_registration_request_id = registration.id
    user.display_name = spec.display_name.strip()
    user.status = "active"
    now = now_text()
    for factory in factories:
        binding = AuthUserRole(id=f"user-role-{uuid4().hex}", user_id=user.id, role_id=position.role_id,
                               factory_id=factory, department=position.department)
        db.add(binding)
        db.flush()
        db.add(AuthRoleBindingMetadata(user_role_id=binding.id, state="active", source_type="registration",
            scope_ceiling_json=json.dumps(factories), valid_from=now, created_at=now, updated_at=now))
    db.flush()
    enroll_approved_registration(db, user, profile, registration, actor)
    registration.status = "approved"
    registration.reviewer_user_id = actor.id
    registration.reviewed_at = now
    registration.review_comment = payload.review_comment
    revision = db.get(AuthUserAuthorizationRevision, user.id)
    revision.revision += 1
    mark_registration_notifications_handled(db, registration.id, now)
    db.commit()
    return registration_request_to_out(registration)
