"""IAM mutation lock order: global invariant -> users -> request -> resources."""
import json
from fastapi import HTTPException
from sqlalchemy import select, update
from app.core.config import settings
from app.models.auth import AuthIamState, AuthUser, EmployeeProfile
from app.models.identity import IamDelegation
from app.services.identity_resolver import stamp

LOCK_KEY = "identity_mutation_lock"


def fail(code, message, status=409):
    raise HTTPException(status, {"code": code, "message": message})


def lock_mutation(db):
    # Seeded before traffic; an UPDATE obtains a SQLite writer lock as well as a
    # PostgreSQL row lock. Never use a process-only mutex for database invariants.
    result = db.execute(update(AuthIamState).where(AuthIamState.key == LOCK_KEY).values(updated_at=stamp()))
    if result.rowcount != 1:
        fail("IDENTITY_SCHEMA_REQUIRED", "请先执行 IAM 结构迁移")
    db.expire_all()


def require_writes():
    if settings.authz_mode != "enforce" or not settings.authz_writes_enabled or not settings.iam_identity_writes_enabled:
        fail("IDENTITY_WRITES_DISABLED", "任职办理尚未启用，请先完成迁移核验", 403)


def fresh_actor(db, actor_id):
    from app.services.auth import build_auth_context
    actor = db.get(AuthUser, actor_id, populate_existing=True)
    if actor is None or actor.status != "active":
        fail("ACCOUNT_UNAVAILABLE", "操作账号已不可用", 401)
    return build_auth_context(db, actor)


def is_group_manager(actor):
    from app.services.auth import can
    return can(actor, "system:user_manage", "*", "*") and can(actor, "system:access_manage", "*", "*")


def ensure_reader(db, actor, target_id=None):
    from app.services.auth import can
    scopes = readable_scopes(db, actor)
    if not scopes:
        fail("OUTSIDE_MANAGEABLE_SCOPE", "无权限查看人员管理", 403)
    if target_id:
        from app.services.identity_resolver import resolve_identity_at
        identity = resolve_identity_at(db, target_id)
        required = [(a["factory_id"] or a["org_unit_id"], a["department_code"]) for a in identity["assignments"]
                    if a["state"] in {"current", "scheduled"} and a["employment_epoch"] == identity["employment_epoch"]]
        if not required:
            required = [(identity["primary_factory_id"], identity["primary_department"])]
        required.extend(additional_source_scopes(db, [target_id]).get(target_id, set()))
        if any(not can(actor, "system:user_manage", f or "*", d or "*") for f, d in required):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "完整人员资料超出管理范围", 403)


def additional_source_scopes(db, user_ids=None):
    """Bulk management scopes for current/future grants, including independent ones.

    This is provenance inspection, not a per-person permission matrix. Callers
    must filter before counting/paginating so hidden personnel never leak totals.
    """
    from app.models.auth import AuthRoleBindingMetadata, AuthRoleMetadata, AuthUserPermissionOverride, AuthUserRole
    from app.models.identity import EmployeeAssignment, IamRoleVersion
    from app.services.identity_resolver import instant, utc_now
    now = utc_now()
    result = {}

    def relevant(meta, profile, assignment, state):
        if state != "active":
            return False
        if meta is not None:
            if meta.valid_until and instant(meta.valid_until) <= now:
                return False
            if meta.assignment_id:
                return bool(assignment and profile and assignment.user_id == profile.user_id
                    and assignment.lifecycle_state == "approved"
                    and assignment.employment_epoch == profile.employment_epoch
                    and (not assignment.valid_until or instant(assignment.valid_until) > now))
            if profile and profile.identity_mode == "v2" and getattr(meta, "effect", "allow") != "deny":
                return profile.employment_status != "left" and meta.employment_epoch == profile.employment_epoch
        return True

    bindings = (select(AuthUserRole, AuthRoleBindingMetadata, EmployeeProfile, EmployeeAssignment, AuthRoleMetadata, IamRoleVersion)
        .select_from(AuthUserRole).outerjoin(AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUserRole.user_id)
        .outerjoin(EmployeeAssignment, EmployeeAssignment.id == AuthRoleBindingMetadata.assignment_id)
        .outerjoin(AuthRoleMetadata, AuthRoleMetadata.role_id == AuthUserRole.role_id)
        .outerjoin(IamRoleVersion, IamRoleVersion.id == AuthRoleBindingMetadata.role_version_id))
    overrides = (select(AuthUserPermissionOverride, EmployeeProfile, EmployeeAssignment).select_from(AuthUserPermissionOverride)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUserPermissionOverride.user_id)
        .outerjoin(EmployeeAssignment, EmployeeAssignment.id == AuthUserPermissionOverride.assignment_id))
    if user_ids is not None:
        bindings = bindings.where(AuthUserRole.user_id.in_(user_ids))
        overrides = overrides.where(AuthUserPermissionOverride.user_id.in_(user_ids))
    for binding, meta, profile, assignment, role_meta, version in db.execute(bindings):
        if not relevant(meta, profile, assignment, meta.state if meta else "active"):
            continue
        scope_mode = json.loads(version.definition_json)["scope_mode"] if version else (role_meta.scope_mode if role_meta else "own_factory")
        factories = json.loads(meta.scope_ceiling_json) if meta and meta.scope_ceiling_json is not None else (
            ["*"] if scope_mode == "cross_factory_operate" else [binding.factory_id])
        result.setdefault(binding.user_id, set()).update((f or "*", binding.department or "*") for f in factories)
    for override, profile, assignment in db.execute(overrides):
        if relevant(override, profile, assignment, override.status):
            result.setdefault(override.user_id, set()).add((override.factory_id or "*", override.department or "*"))
    return result


def readable_scopes(db, actor):
    from app.services.auth import can
    from app.models.identity import IamOrgDepartment
    scopes = [(d.org_unit_id, d.department_code) for d in db.scalars(select(IamOrgDepartment))
              if can(actor, "system:user_manage", d.org_unit_id, d.department_code)]
    # The global tuple permits unconfirmed accounts, while concrete checks still
    # honor a deny on a particular factory or department.
    if can(actor, "system:user_manage", "*", "*"):
        scopes.append(("", ""))
    return scopes


def ensure_change_authority(db, actor, subject_id, scopes, roles):
    from app.services.auth import can
    for org, factory, department in scopes:
        if not all(can(actor, code, factory or org, department) for code in ("system:user_manage", "system:access_manage")):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "请提交覆盖来源与目标组织的管理员办理", 403)
    if is_group_manager(actor):
        # Self administration may only retain authority, never create it.
        if subject_id == actor.id and roles:
            fail("SELF_ESCALATION", "新增系统管理来源需要另一位有权管理员办理", 403)
        return
    if subject_id == actor.id:
        fail("SELF_ESCALATION", "本人任职与权限变更须由有权管理员办理", 403)
    delegations = list(db.scalars(select(IamDelegation).where(IamDelegation.user_id == actor.id, IamDelegation.status == "active")))
    for org, factory, department in scopes:
        if not can(actor, "system:user_manage", factory or org, department) or not can(actor, "system:access_manage", factory or org, department):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "请提交覆盖来源与目标组织的管理员办理", 403)
        eligible = [d for d in delegations if d.org_unit_id == org and d.department in {"*", department}]
        if not eligible:
            fail("GRANT_NOT_DELEGABLE", "当前管理员尚未登记此组织的转授上限", 403)
        for role in roles:
            if not any(role["role_id"] in json.loads(d.role_ids_json) and set(role["factories"]) <= set(json.loads(d.factory_ids_json)) for d in eligible):
                fail("GRANT_NOT_DELEGABLE", "权限包或作用范围超过转授上限", 403)


def ensure_admin_survives(db):
    from app.services.auth import build_auth_context, can
    from app.models.auth import AuthRoleBindingMetadata, AuthUserPermissionOverride
    from app.services.identity_resolver import instant, utc_now
    from app.models.identity import EmployeeAssignment
    now = utc_now()
    boundaries = {now}
    for model in (AuthRoleBindingMetadata, AuthUserPermissionOverride, EmployeeAssignment):
        for row in db.scalars(select(model)):
            for value in (row.valid_from, row.valid_until):
                try:
                    boundary = instant(value)
                except (TypeError, ValueError):
                    continue
                if boundary and boundary > now:
                    boundaries.add(boundary)
    candidates = list(db.scalars(select(AuthUser).where(AuthUser.status == "active")))
    for at in sorted(boundaries):
        if not any(all(can(build_auth_context(db, user, at=at), p, "*", "*", at=at)
                       for p in ("system:user_manage", "system:access_manage")) for user in candidates):
            fail("LAST_ADMINISTRATOR", "此变更会导致没有有效集团管理员")
