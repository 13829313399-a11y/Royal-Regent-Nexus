"""Read-only IAM workspace projections. Reuse visibility and runtime authorization at a common instant."""
from collections import Counter, defaultdict

from sqlalchemy import exists, func, or_, select

from app.core.config import settings
from app.core.time import serialize_process_local_timestamp
from app.models.auth import (AuthPermission, AuthRole, AuthRoleBindingMetadata, AuthRolePermission, AuthUser, AuthUserRole,
                             EmployeeProfile)
from app.models.identity import EmployeeAssignment, IamOrgDepartment, IamOrgUnit, IamRoleVersion
from app.services.auth import authorization_decision, build_auth_context, can, has_permission_in_scope, time_window_is_active
from app.services.auth_read_inputs import AuthReadInputs
from app.services.iam_management_scopes import complete_scopes
from app.services.identity_catalog import DEPARTMENTS, FACTORIES
from app.services.identity_policy import additional_source_scopes, ensure_reader, fail, is_group_manager, readable_scopes
from app.services import identity_resolver
from app.services.identity_resolver import identity_columns, stamp
from app.services.identity_sources import definition_hash, role_definition, role_definition_from_rows, source_is_active
from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS, get_system_position


def visible_people_query(db, user, at, *, q="", org_unit_id="", status="", department="", identity_mode=""):
    ensure_reader(db, user)
    factory, dept, title, org = identity_columns(at, include_org=True)
    query = select(AuthUser, EmployeeProfile, factory.label("factory"), dept.label("department"), title.label("title"), org.label("org")).outerjoin(EmployeeProfile)
    scopes = readable_scopes(db, user)
    if is_group_manager(user):
        scopes.extend([("*", "*"), ("*", "system")])
    primary_visible = or_(*[(func.coalesce(org, "") == f) & (func.coalesce(dept, "") == d) for f, d in scopes])
    assignment_visible = or_(*[(EmployeeAssignment.org_unit_id == f) & (EmployeeAssignment.department_code == d) for f, d in scopes])
    has_hidden_assignment = exists(select(EmployeeAssignment.id).where(
        EmployeeAssignment.user_id == AuthUser.id, EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
        EmployeeAssignment.lifecycle_state == "approved", or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp(at)),
        ~assignment_visible))
    has_visible_assignment = exists(select(EmployeeAssignment.id).where(
        EmployeeAssignment.user_id == AuthUser.id, EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
        EmployeeAssignment.lifecycle_state == "approved", or_(EmployeeAssignment.valid_until.is_(None), EmployeeAssignment.valid_until > stamp(at)), assignment_visible))
    query = query.where(~has_hidden_assignment, or_(primary_visible, has_visible_assignment))
    if q.strip():
        query = query.where(or_(AuthUser.display_name.contains(q.strip(), autoescape=True), AuthUser.username.contains(q.strip(), autoescape=True)))
    if status:
        query = query.where(EmployeeProfile.employment_status == "left" if status == "left" else AuthUser.status == status)
    if org_unit_id:
        query = query.where(org == org_unit_id)
    if department:
        query = query.where(dept == department)
    if identity_mode:
        query = query.where(func.coalesce(EmployeeProfile.identity_mode, "legacy") == identity_mode)
    candidates = query.with_only_columns(AuthUser.id).order_by(None)
    source_scopes = additional_source_scopes(db, candidates)
    hidden = [uid for uid, required in source_scopes.items()
              if any(not can(user, "system:user_manage", f, d) for f, d in complete_scopes(required))]
    if hidden:
        query = query.where(AuthUser.id.not_in(hidden))
    return query


def active_bindings(db, query, at, role_ids=()):
    """Only inspect bindings belonging to the already scope-filtered directory.

    Joined entities stay in the identity map throughout each source check. In
    particular, missing versions or mismatched assignment owners never count.
    """
    statement = (select(AuthUserRole, AuthRoleBindingMetadata, EmployeeProfile, EmployeeAssignment,
                        IamOrgUnit, IamOrgDepartment, IamRoleVersion)
                 .select_from(AuthUserRole)
                 .outerjoin(AuthRoleBindingMetadata, AuthRoleBindingMetadata.user_role_id == AuthUserRole.id)
                 .outerjoin(EmployeeProfile, AuthUserRole.user_id == EmployeeProfile.user_id)
                 .outerjoin(EmployeeAssignment, AuthRoleBindingMetadata.assignment_id == EmployeeAssignment.id)
                 .outerjoin(IamOrgUnit, EmployeeAssignment.org_unit_id == IamOrgUnit.id)
                 .outerjoin(IamOrgDepartment, (EmployeeAssignment.org_unit_id == IamOrgDepartment.org_unit_id)
                            & (EmployeeAssignment.department_code == IamOrgDepartment.department_code))
                 .outerjoin(IamRoleVersion, IamRoleVersion.id == AuthRoleBindingMetadata.role_version_id)
                 .where(AuthUserRole.user_id.in_(query.with_only_columns(AuthUser.id))))
    if role_ids:
        statement = statement.where(AuthUserRole.role_id.in_(role_ids))
    for binding, meta, profile, assignment, org, dept, version in db.execute(statement):
        if meta:
            if meta.state != "active" or not time_window_is_active(meta.valid_from, meta.valid_until, at):
                continue
            if meta.assignment_id and (not assignment or not org or not dept or not meta.role_version_id):
                continue
            if meta.role_version_id and (not version or version.role_id != binding.role_id):
                continue
        if source_is_active(db, meta, profile, at):
            yield binding, meta, version


def person_out(row):
    user, profile, factory, department, title, org = row
    return {"id": user.id, "display_name": user.display_name, "username": user.username, "status": user.status,
            "last_login_at": serialize_process_local_timestamp(user.last_login_at), "primary_org_unit_id": org or "",
            "primary_factory_id": factory or "", "primary_department": department or "", "position": title or "",
            "identity_mode": profile.identity_mode if profile else "legacy",
            "employment_status": profile.employment_status if profile else "unconfirmed",
            "identity_version": profile.identity_version if profile else 0}


def current_role_hashes(inputs):
    permissions = {p.id: p for p in inputs.permissions}
    # AuthReadInputs uses the same database ORDER BY code as the single-role definition.
    order = {p.id: i for i, p in enumerate(inputs.permissions)}
    metadata = {m.permission_id: m for m in inputs.permission_metadata}
    rows = defaultdict(list)
    for link in inputs.role_permissions:
        if link.permission_id in permissions:
            rows[link.role_id].append((permissions[link.permission_id], metadata.get(link.permission_id)))
    return {role.id: definition_hash(role_definition_from_rows(
        role, inputs.role_metadata.get(role.id), sorted(rows[role.id], key=lambda pair: order[pair[0].id])))
        for role in inputs.roles.values()}


def active_packages(context, inputs, latest_hashes):
    primary = context.identity.get("primary_assignment") or {}
    versions = {v.id: v for v in inputs.role_versions}
    packages = []
    for grant in context.grants:
        meta = inputs.binding_metadata.get(grant.binding_id)
        version = versions.get(meta.role_version_id) if meta else None
        packages.append({
            "binding_id": grant.binding_id, "role_id": grant.role_id, "role_name": grant.role_name,
            "department": grant.department, "department_name": DEPARTMENTS.get(grant.department, grant.department),
            "factory_id": grant.factory_id, "factory_ceiling": None if grant.factory_ceiling is None else list(grant.factory_ceiling),
            "assignment_id": grant.assignment_id or None,
            "is_primary_assignment": bool(grant.assignment_id and grant.assignment_id == primary.get("id")),
            "source_type": meta.source_type if meta else "legacy_import",
            "is_system_position": get_system_position(grant.role_id) is not None,
            "role_version_id": version.id if version else None,
            "version_outdated": bool(version and version.definition_hash != latest_hashes[grant.role_id]),
            "valid_from": grant.valid_from or None, "valid_until": grant.valid_until or None,
        })
    return packages


def candidate_codes(context):
    if not context.account_available:
        return set()
    if any(g.role_code == "admin" and g.factory_id == "*" and g.department in {"*", "system"}
           for g in context.grants):
        return context.active_permission_codes
    return {p for grant in context.grants for p in grant.permissions} | {
        item.permission_code for item in context.overrides if item.effect == "allow"}


def effective_factories(context, at):
    codes = sorted(candidate_codes(context))
    if settings.authz_mode != "enforce" and context.identity.get("identity_mode") != "v2":
        return [f for f in FACTORIES if any(has_permission_in_scope(context, code, f, d)
                for code in codes for d in (*DEPARTMENTS, "system", "*"))]
    return [f for f in FACTORIES if any(can(context, code, f, d, at=at)
            for code in codes for d in (*DEPARTMENTS, "system", "*"))]


def effective_access(db, user_id, *, include_summary=False):
    from app.services.iam import _permission_out
    user = db.get(AuthUser, user_id)
    if user is None:
        fail("USER_NOT_FOUND", "人员不存在", 404)
    at = identity_resolver.utc_now()
    inputs = AuthReadInputs(db, [user_id])
    context = build_auth_context(db, user, at=at, read_inputs=inputs)
    metadata = {m.permission_id: m for m in inputs.permission_metadata}
    possible = candidate_codes(context)
    groups = {}
    canonical_names = []
    configured_legacy = settings.authz_mode != "enforce" and context.identity.get("identity_mode") != "v2"
    for perm in inputs.permissions:
        if perm.code not in possible:
            continue
        factories, sources, scopes = [], set(), []
        canonical_any = False
        for factory in (*FACTORIES, "group-management", "*"):
            departments = []
            for department in (*DEPARTMENTS, "system", "*"):
                allowed, _, ids, _ = authorization_decision(context, perm.code, factory, department, at=at)
                canonical_any |= allowed
                effective = has_permission_in_scope(context, perm.code, factory, department) if configured_legacy else allowed
                if effective:
                    departments.append(department)
                    if allowed:
                        sources.update(ids)
            if departments:
                factories.append(factory)
                scopes.append({"factory_id": factory, "department_codes": departments})
        if canonical_any:
            canonical_names.append(perm.name)
        if factories:
            item = _permission_out(perm, metadata.get(perm.id))
            group = groups.setdefault(item.module_code, {"module_code": item.module_code,
                                "module_name": item.module_name, "items": []})
            labels = {**FACTORIES, "*": "全局范围", "group-management": "集团总务"}
            group["items"].append({"code": item.code, "name": item.name, "access_kind": item.access_kind,
                                   "factory_ids": factories, "factory_names": [labels[f] for f in factories],
                                   "source_ids": sorted(sources), "scopes": scopes})
    result = {"current_packages": active_packages(context, inputs, current_role_hashes(inputs)),
              "effective_permissions_grouped": [groups[k] for k in sorted(groups)]}
    if include_summary:
        result["effective_permission_summary"] = canonical_names
        for package in result["current_packages"]:
            role = inputs.roles.get(package["role_id"])
            package["description"] = role.description if role else ""
        allowed_factories = {factory for group in groups.values() for item in group["items"]
                             for factory in item["factory_ids"]}
        result["effective_business_factories"] = [{"id": f, "name": name} for f, name in FACTORIES.items()
                                                 if f in allowed_factories]
    return result


def open_tasks(db, actor, user_ids, at):
    from app.services.iam_workspace import Projection, read_sources
    tasks, coverage = read_sources(Projection(db, actor, at, user_ids=user_ids, open_only=True))
    result = {}
    for task in sorted(tasks, key=lambda t: (t["created_at"], t["key"])):
        if task["state"] != "closed":
            result.setdefault(task["subject"]["user_id"], {
                "key": task["key"], "kind": task["kind"], "state": task["state"], "summary": task["proposed_position"]})
    return result, not any(c["state"] == "unavailable" for c in coverage)


def people(db, actor, *, q, org_unit_id, status, page, page_size, include, department, identity_mode,
           role_id, has_packages, include_org_counts=False):
    at = identity_resolver.utc_now()
    query = visible_people_query(db, actor, at, q=q, org_unit_id="" if include_org_counts else org_unit_id,
                                 status=status, department="" if include_org_counts else department, identity_mode=identity_mode)
    if role_id or has_packages:
        matches = {b.user_id for b, _, _ in active_bindings(db, query, at, [role_id] if role_id else [])}
        query = query.where(AuthUser.id.in_(matches)) if role_id or has_packages == "yes" else query.where(AuthUser.id.not_in(matches))
        if role_id and has_packages == "no":
            query = query.where(False)
    response = {}
    if include_org_counts:
        org = query.selected_columns["org"]
        dept = query.selected_columns["department"]
        visible = query.with_only_columns(org, dept).subquery()
        counts = select(visible.c.org, visible.c.department, func.count()).group_by(visible.c.org, visible.c.department)
        response["org_counts"] = [{"org_unit_id": o or "", "department": d or "", "count": count}
                                  for o, d, count in db.execute(counts)]
        if org_unit_id:
            query = query.where(org == org_unit_id)
        if department:
            query = query.where(dept == department)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AuthUser.display_name, AuthUser.id).offset((page-1)*page_size).limit(page_size)).all()
    items = [person_out(row) for row in rows]
    if rows and include == "access_summary":
        ids = [item["id"] for item in items]
        tasks, complete = open_tasks(db, actor, ids, at)
        inputs = AuthReadInputs(db, ids)
        latest_hashes = current_role_hashes(inputs)
        for item, row in zip(items, rows):
            context = build_auth_context(db, row[0], at=at, read_inputs=inputs)
            counts = Counter(o.effect for o in context.overrides)
            item["access_summary"] = {"active_packages": active_packages(context, inputs, latest_hashes),
                    "effective_factories": effective_factories(context, at),
                    "override_counts": {"allow": counts["allow"], "deny": counts["deny"]},
                    "open_task": tasks.get(item["id"]), "task_coverage_complete": complete}
    return {**response, "total": total, "page": page, "page_size": page_size, "items": items}


def scoped_counts(db, actor, role_ids):
    if "system:user_manage" not in actor.permissions or not readable_scopes(db, actor):
        return None
    at = identity_resolver.utc_now()
    query = visible_people_query(db, actor, at)
    members, bindings = defaultdict(set), Counter()
    for binding, _, _ in active_bindings(db, query, at, role_ids):
        members[binding.role_id].add(binding.user_id)
        bindings[binding.role_id] += 1
    return bindings, {role_id: len(ids) for role_id, ids in members.items()}


def role_members(db, actor, role_id, *, q, org_unit_id, only_outdated, page, page_size):
    from app.services.iam import _ensure_iam_manager, _ensure_permission_catalog_reader, _load_role
    _ensure_iam_manager(db, actor)
    _ensure_permission_catalog_reader(db, actor)
    _load_role(db, role_id)
    latest = definition_hash(role_definition(db, role_id))
    response = {"role_id": role_id, "latest_definition_hash": latest, "members_restricted": True,
                "total": None, "outdated_total": None, "items": [], "page": page, "page_size": page_size}
    if "system:user_manage" not in actor.permissions or not readable_scopes(db, actor):
        return response
    at = identity_resolver.utc_now()
    query = visible_people_query(db, actor, at, q=q, org_unit_id=org_unit_id)
    ids, outdated = set(), set()
    for binding, _, version in active_bindings(db, query, at, [role_id]):
        ids.add(binding.user_id)
        if version and version.definition_hash != latest:
            outdated.add(binding.user_id)
    matched = outdated if only_outdated else ids
    rows = db.execute(query.where(AuthUser.id.in_(matched)).order_by(AuthUser.display_name, AuthUser.id)
                      .offset((page - 1)*page_size).limit(page_size)).all() if matched else []
    items = []
    if rows:
        inputs = AuthReadInputs(db, [r[0].id for r in rows])
        hashes = current_role_hashes(inputs)
        for row in rows:
            person = person_out(row)
            context = build_auth_context(db, row[0], at=at, read_inputs=inputs)
            packages = [b for b in active_packages(context, inputs, hashes) if b["role_id"] == role_id]
            items.append({"user_id": person["id"], "display_name": person["display_name"], "username": person["username"],
                          "user_status": person["status"], "primary_org_unit_id": person["primary_org_unit_id"],
                          "primary_department": person["primary_department"], "position": person["position"],
                          "bindings": packages})
    return {**response, "members_restricted": False, "total": len(matched), "outdated_total": len(outdated), "items": items}


def reference_catalog(db):
    roles = {r for r in db.scalars(select(AuthRole.id))}
    system_roles = set(db.scalars(select(AuthRolePermission.role_id).join(AuthPermission)
                                   .where(AuthPermission.code.startswith("system:"))))
    packages = [{"role_id": r.role_id, "name": r.name, "department_code": r.department, "description": r.description}
                for r in SYSTEM_POSITION_DEFINITIONS if r.role_id in roles
                and r.role_id not in system_roles and r.role_id != "position_external_carton_warehouse_keeper"]
    orgs = db.scalars(select(IamOrgUnit).where(IamOrgUnit.kind == "factory", IamOrgUnit.status == "active")
                      .order_by(IamOrgUnit.id))
    return {"reference_packages": packages, "reference_factories": [{"id": o.id, "name": o.name}
                                                                 for o in orgs if o.id in FACTORIES]}
