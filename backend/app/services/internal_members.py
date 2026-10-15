"""One internal-member rule for roster, profiles and private collaboration.

Legacy empty-permission employees remain compatible. Supplier-only accounts are
excluded unless a current formal internal assignment establishes membership.
Bulk roster evaluation reuses IAM source and decision functions with preloaded
provenance; its SQL count does not grow with the number of employees.
"""
from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from app.models.auth import (AuthUser, EmployeeProfile, AuthPermission, AuthPermissionMetadata,
    AuthRole, AuthRoleMetadata, AuthRolePermission, AuthUserRole, AuthRoleBindingMetadata,
    AuthUserPermissionOverride)
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamOrgDepartment, IamRoleVersion
from app.services.auth import (AuthContext, AuthGrantContext, AuthOverrideContext,
    authorization_decision, time_window_is_active, ALLOWED_FACTORY_IDS,
    SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES)
from app.services.identity_resolver import assignment_active, utc_now
from app.services.identity_sources import source_is_active, binding_grants
from app.services.system_positions import get_system_position
from app.services.iam_scope import default_permission_access_kind


def is_internal(context: AuthContext) -> bool:
    identity = context.identity or {}
    if not context.account_available or identity.get("employment_status") == "left":
        return False
    formal = any(a.get("org_unit_id") and a["org_unit_id"] != "group" for a in identity.get("active_assignments_summary", []))
    supplier_only = bool(context.permissions) and all(p.startswith("carton_supplier:") for p in context.permissions)
    if supplier_only and not formal:
        return False
    if identity.get("identity_mode") == "v2" and not formal and not context.permissions:
        return False
    return True


def require_internal(context: AuthContext):
    if not is_internal(context):
        raise HTTPException(403, {"code": "COLLABORATION_INELIGIBLE", "message": "当前身份不可使用内部成员协作"})
    return context


class _Sources:
    """Only the get protocol needed by the existing IAM source functions."""
    def __init__(self, rows):
        self.rows = rows

    def get(self, model, key):
        return self.rows[model].get(key)


def eligible_member_ids(db, *, at=None) -> list[str]:
    at = at or utc_now()
    users = list(db.execute(select(AuthUser.id, AuthUser.status)).all())
    profiles = {p.user_id: p for p in db.scalars(select(EmployeeProfile))}
    orgs = {o.id: o for o in db.scalars(select(IamOrgUnit))}
    departments = {(d.org_unit_id, d.department_code): d for d in db.scalars(select(IamOrgDepartment))}
    assignments = {a.id: a for a in db.scalars(select(EmployeeAssignment))}
    versions = {v.id: v for v in db.scalars(select(IamRoleVersion))}
    source_db = _Sources({EmployeeAssignment: assignments, IamOrgUnit: orgs,
                          IamOrgDepartment: departments, IamRoleVersion: versions})
    formal = set()
    for a in assignments.values():
        p, org, dept = profiles.get(a.user_id), orgs.get(a.org_unit_id), departments.get((a.org_unit_id, a.department_code))
        if p and org and dept and org.kind in {"factory", "functional_unit"} and org.status == dept.status == "active" and assignment_active(a, p, at):
            formal.add(a.user_id)
    permissions = {p.id: p for p in db.scalars(select(AuthPermission))}
    permission_meta = {m.permission_id: m for m in db.scalars(select(AuthPermissionMetadata))}
    active_codes = frozenset(p.code for p in permissions.values() if p.id not in permission_meta or permission_meta[p.id].status == "active")
    roles = {r.id: r for r in db.scalars(select(AuthRole))}
    role_meta = {m.role_id: m for m in db.scalars(select(AuthRoleMetadata))}
    role_codes, role_read = defaultdict(set), defaultdict(set)
    for item in db.scalars(select(AuthRolePermission)):
        p = permissions.get(item.permission_id)
        if not p or p.code not in active_codes:
            continue
        role_codes[item.role_id].add(p.code)
        kind = permission_meta[p.id].access_kind if p.id in permission_meta else default_permission_access_kind(p.code)
        if kind == "read":
            role_read[item.role_id].add(p.code)
    binding_meta = {m.user_role_id: m for m in db.scalars(select(AuthRoleBindingMetadata))}
    grants = defaultdict(list)
    for b in db.scalars(select(AuthUserRole)):
        meta, profile = binding_meta.get(b.id), profiles.get(b.user_id)
        if not source_is_active(source_db, meta, profile, at):
            continue
        if meta and (meta.state != "active" or not time_window_is_active(meta.valid_from, meta.valid_until, at)):
            continue
        role = roles.get(b.role_id)
        fixed = get_system_position(b.role_id) is not None
        scope = role_meta[b.role_id].scope_mode if fixed and b.role_id in role_meta else "own_factory"
        grant = AuthGrantContext(role_id=b.role_id, role_name=role.name if role else b.role_id,
            factory_id=b.factory_id, department=b.department, permissions=frozenset(role_codes[b.role_id]),
            data_scope="all" if b.factory_id == "*" or scope != "own_factory" else "factory" if fixed else "department",
            scope_mode=scope, read_permissions=frozenset(role_read[b.role_id]), unrestricted_department=fixed,
            binding_id=b.id, role_code=role.code if role else b.role_id,
            valid_from=meta.valid_from if meta else "", valid_until=meta.valid_until if meta else "")
        grants[b.user_id].extend(binding_grants(source_db, [grant], binding_meta, active_codes))
    overrides = defaultdict(list)
    for o in db.scalars(select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.status == "active")):
        p = permissions.get(o.permission_id)
        if p and p.code in active_codes and source_is_active(source_db, o, profiles.get(o.user_id), at) and time_window_is_active(o.valid_from, o.valid_until, at):
            overrides[o.user_id].append(AuthOverrideContext(id=o.id, permission_code=p.code, effect=o.effect,
                factory_id=o.factory_id, department=o.department, valid_from=o.valid_from, valid_until=o.valid_until, source_type=o.source_type))
    result = []
    for uid, status in users:
        p = profiles.get(uid)
        if status != "active" or (p and p.employment_status == "left"):
            continue
        if uid in formal:
            result.append(uid)
            continue
        gs, os = tuple(grants[uid]), tuple(overrides[uid])
        ctx = AuthContext(id=uid, username="", display_name="", roles=(), role_codes=(), permissions=frozenset(),
            factory_scopes=(), department_scopes=(), grants=gs, overrides=os,
            active_permission_codes=active_codes, permission_catalog_loaded=True,
            identity={"identity_mode": p.identity_mode if p else "legacy"})
        scopes = {(g.factory_id, g.department) for g in gs} | {(o.factory_id, o.department) for o in os}
        if any(g.role_code == "admin" and g.factory_id == "*" and g.department in {"*", "system"} for g in gs):
            scopes.add(("*", "*"))
        allowed = {code for code in active_codes if any(authorization_decision(ctx, code, f, d, at=at)[0] for f, d in scopes)}
        cross_codes = {code for g in gs if g.unrestricted_department for code in g.permissions
                       if g.scope_mode != "own_factory" or code in SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES}
        allowed.update(code for code in cross_codes - allowed if any(authorization_decision(ctx, code, f, "*", at=at)[0] for f in ALLOWED_FACTORY_IDS))
        if allowed and all(code.startswith("carton_supplier:") for code in allowed):
            continue
        if p and p.identity_mode == "v2" and not allowed:
            continue
        result.append(uid)
    return result
