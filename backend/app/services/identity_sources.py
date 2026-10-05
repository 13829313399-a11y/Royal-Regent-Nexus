"""Read frozen permission packages; never union them with mutable role grants."""
import hashlib
import json
from dataclasses import replace
from uuid import uuid4
from sqlalchemy import select
from app.models.auth import AuthPermission, AuthPermissionMetadata, AuthRole, AuthRoleMetadata, AuthRolePermission
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamOrgDepartment, IamRoleVersion
from app.services.identity_resolver import assignment_active, stamp


def source_is_active(db, source, profile, at):
    if source is None:
        return not profile or profile.identity_mode != "v2"
    if source.assignment_id:
        assignment = db.get(EmployeeAssignment, source.assignment_id)
        org = db.get(IamOrgUnit, assignment.org_unit_id) if assignment else None
        dept = db.get(IamOrgDepartment, (assignment.org_unit_id, assignment.department_code)) if assignment else None
        return bool(dept and dept.status == "active" and profile and assignment and assignment.user_id == profile.user_id and org
                    and org.status == "active" and assignment_active(assignment, profile, at))
    if profile and profile.identity_mode == "v2" and getattr(source, "effect", "allow") != "deny":
        return source.employment_epoch == profile.employment_epoch and profile.employment_status != "left"
    return True


def role_definition(db, role_id):
    from app.services.iam_scope import default_permission_access_kind
    from app.services.system_positions import get_system_position
    role = db.get(AuthRole, role_id)
    if role is None:
        from app.services.identity_policy import fail
        fail("UNKNOWN_ROLE", "权限包不存在，请刷新后选择", 422)
    meta = db.get(AuthRoleMetadata, role_id)
    rows = db.execute(select(AuthPermission, AuthPermissionMetadata).join(AuthRolePermission,
        AuthRolePermission.permission_id == AuthPermission.id).outerjoin(AuthPermissionMetadata)
        .where(AuthRolePermission.role_id == role_id).order_by(AuthPermission.code)).all()
    return {"role_id": role_id, "role_code": role.code, "role_name": role.name,
            "permissions": [p.code for p, _ in rows],
            "read_permissions": [p.code for p, m in rows if (m.access_kind if m else default_permission_access_kind(p.code)) == "read"],
            "scope_mode": meta.scope_mode if meta else "own_factory",
            "unrestricted_department": get_system_position(role_id) is not None}


def definition_hash(definition):
    return hashlib.sha256(json.dumps(definition, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot_role(db, role_id, actor_id=""):
    definition = role_definition(db, role_id)
    digest = definition_hash(definition)
    version = db.scalar(select(IamRoleVersion).where(IamRoleVersion.role_id == role_id, IamRoleVersion.definition_hash == digest))
    if version is None:
        version = IamRoleVersion(id=f"role-version-{uuid4().hex}", role_id=role_id, definition_hash=digest,
                                 definition_json=json.dumps(definition, ensure_ascii=False), created_at=stamp(), created_by=actor_id)
        db.add(version)
        db.flush()
    return version


def binding_grants(db, grants, metadata, active_codes):
    result = []
    for grant in grants:
        meta = metadata.get(grant.binding_id)
        if meta and meta.role_version_id:
            version = db.get(IamRoleVersion, meta.role_version_id)
            if not version or version.role_id != grant.role_id:
                continue  # Broken provenance fails closed.
            definition = json.loads(version.definition_json)
            ceiling = json.loads(meta.scope_ceiling_json) if meta.scope_ceiling_json is not None else None
            grant = replace(grant, permissions=frozenset(definition["permissions"]) & active_codes,
                            read_permissions=frozenset(definition["read_permissions"]) & active_codes,
                            scope_mode=definition["scope_mode"], unrestricted_department=definition["unrestricted_department"],
                            role_code=definition["role_code"], factory_ceiling=tuple(ceiling) if ceiling is not None else None,
                            assignment_id=meta.assignment_id or "")
        elif meta and meta.assignment_id:
            continue
        result.append(grant)
    return tuple(result)
