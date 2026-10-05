import json
from sqlalchemy import select
from app.models.auth import AuthUser
from app.models.identity import IamDelegation, IamOrgDepartment, IamOrgUnit
from app.services.identity_policy import fail, fresh_actor, is_group_manager, lock_mutation, require_writes
from app.services.identity_sources import role_definition


def out(row):
    return {"id": row.id, "user_id": row.user_id, "org_unit_id": row.org_unit_id, "department": row.department,
            "role_ids": json.loads(row.role_ids_json), "factory_ids": json.loads(row.factory_ids_json),
            "status": row.status, "revision": row.revision}


def list_delegations(db, actor, user_id):
    if not is_group_manager(actor):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "转授上限由集团管理员管理", 403)
    return [out(row) for row in db.scalars(select(IamDelegation).where(IamDelegation.user_id == user_id))]


def save(db, actor_id, user_id, delegation_id, payload):
    from app.services.identity_catalog import FACTORIES
    from app.services.iam import _add_event
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    if not is_group_manager(actor) or actor_id == user_id:
        fail("GRANT_NOT_DELEGABLE", "须由另一位集团管理员设定转授上限", 403)
    if not db.get(AuthUser, user_id):
        fail("USER_NOT_FOUND", "人员不存在", 404)
    org = db.get(IamOrgUnit, payload.org_unit_id)
    dept = db.get(IamOrgDepartment, (payload.org_unit_id, payload.department))
    if not org or org.kind == "group" or org.status != "active" or (payload.department != "*" and (not dept or dept.status != "active")):
        fail("INVALID_ORG", "请选择有效组织与部门", 422)
    if any(f not in FACTORIES for f in payload.factory_ids):
        fail("INVALID_SCOPE", "业务范围只能包含现有生产厂区", 422)
    for role_id in payload.role_ids:
        role = role_definition(db, role_id)
        if role["role_code"] == "admin" or any(p.startswith("system:") for p in role["permissions"]):
            fail("GRANT_NOT_DELEGABLE", "系统管理权限不得通过普通任职转授", 422)
    row = db.get(IamDelegation, delegation_id)
    if row and (row.user_id != user_id or row.revision != payload.expected_revision):
        fail("DELEGATION_CHANGED", "转授范围已变化，请刷新")
    if not row and payload.expected_revision != 0:
        fail("DELEGATION_CHANGED", "转授记录不存在，请刷新")
    before = out(row) if row else None
    if not row:
        row = IamDelegation(id=delegation_id, user_id=user_id, revision=0)
        db.add(row)
    row.org_unit_id, row.department, row.status = payload.org_unit_id, payload.department, payload.status
    row.role_ids_json = json.dumps(sorted(set(payload.role_ids)))
    row.factory_ids_json = json.dumps(sorted(set(payload.factory_ids)))
    row.revision += 1
    _add_event(db, actor_id, "identity_delegation_updated", "delegation", delegation_id, target_user_id=user_id,
               before=before, after=out(row), reason=payload.reason)
    db.commit()
    return out(row)
