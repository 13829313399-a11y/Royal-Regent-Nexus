"""Factory/customer responsibility checks for order work, separate from stock and QC."""
from fastapi import HTTPException
from sqlalchemy import delete, select, or_

from app.models.auth import AuthUser
from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment, CartonCustomerOwner as Owner
from app.models.carton_procurement import CartonCustomer
from app.services.auth import build_auth_context, has_permission_in_scope


def allowed(user, factory, permission):
    return any(has_permission_in_scope(user, f"carton_procurement:{permission}", factory, department)
               for department in ("carton", "pmc-warehouse"))


def unrestricted(user, factory):
    return allowed(user, factory, "order_adjust")


def assigned_codes(db, user, factory):
    return set(db.scalars(select(CartonCustomer.customer_code).join(Assignment, Assignment.customer_id == CartonCustomer.id)
                         .where(CartonCustomer.factory_id == factory, Assignment.factory_id == factory, Assignment.user_id == user.id)))


def eligible(user, factory):
    return allowed(user, factory, "read") and any(allowed(user, factory, p) for p in ("order_write", "receipt_write"))


def customer_predicate(user, factory, column):
    if unrestricted(user, factory):
        return True
    restricted = select(CartonCustomer.customer_code).join(Assignment, Assignment.customer_id == CartonCustomer.id).where(
        CartonCustomer.factory_id == factory, Assignment.factory_id == factory)
    own = select(CartonCustomer.customer_code).join(Assignment, Assignment.customer_id == CartonCustomer.id).where(
        CartonCustomer.factory_id == factory, Assignment.factory_id == factory, Assignment.user_id == user.id)
    return or_(column.not_in(restricted), column.in_(own))


def ensure_customer_operation(db, user, factory, customer_code):
    # Business writers hold the same factory lock as claim/delegation writers.
    if unrestricted(user, factory):
        return
    if not db.scalar(select(CartonCustomer.id).where(CartonCustomer.factory_id == factory,
            CartonCustomer.customer_code == customer_code.strip().upper(),
            ~customer_predicate(user, factory, CartonCustomer.customer_code))):
        return
    raise HTTPException(403, "该客户已由其他人员负责，你未获授权；请联系客户负责人或主管")


def ensure_receipt_operation(db, user, factory, lines):
    for code in {line.customer_code for line in lines}:
        ensure_customer_operation(db, user, factory, code)


def workspace(db, user, factory, *, summary=False):
    manager = unrestricted(user, factory)
    customers = list(db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id == factory).order_by(CartonCustomer.customer_name)))
    bindings = list(db.scalars(select(Assignment).where(Assignment.factory_id == factory)))
    owners = {row.customer_id: row.user_id for row in db.scalars(select(Owner).where(Owner.factory_id == factory))}
    own = assigned_codes(db, user, factory)
    restricted = {row.customer_id for row in bindings}
    result = dict(can_manage=manager or eligible(user, factory), unrestricted=manager,
        own_customer_codes=sorted(own), blocked_customer_codes=sorted(row.customer_code for row in customers
            if row.id in restricted and row.customer_code not in own), users=[], customers=[])
    if summary:
        return result
    identifiers = {binding.user_id for binding in bindings} | set(owners.values())
    users = list(db.scalars(select(AuthUser).where(AuthUser.status == "active").order_by(AuthUser.display_name, AuthUser.id)))
    candidates = [dict(id=row.id, name=row.display_name) for row in users
        if eligible(build_auth_context(db, row), factory)] if manager or user.id in owners.values() else []
    names = {row.id: row.display_name for row in users}
    if identifiers - set(names):
        names.update((row.id, row.display_name) for row in db.scalars(select(AuthUser).where(AuthUser.id.in_(identifiers - set(names)))))
    result.update(users=candidates, customers=[dict(id=row.id, code=row.customer_code, name=row.customer_name,
        revision=row.revision, status=row.status,
        owner=dict(id=owners[row.id], name=names.get(owners[row.id], "账号已停用")) if row.id in owners else None,
        can_manage=manager or (eligible(user, factory) and owners.get(row.id) == user.id),
        can_claim=eligible(user, factory) and row.status == "ACTIVE" and row.id not in restricted,
        users=[dict(id=b.user_id, name=names.get(b.user_id, "账号已停用")) for b in bindings if b.customer_id == row.id])
        for row in customers])
    return result


def _locked_actor_customer(db, user, factory, customer_id, revision):
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, factory)
    actor = db.get(AuthUser, user.id)
    if actor is None or actor.status != "active":
        raise HTTPException(403, "账号已停用，请重新登录")
    user = build_auth_context(db, actor)
    if not eligible(user, factory) and not unrestricted(user, factory):
        raise HTTPException(403, "需要本厂订单或入库岗位权限")
    customer = db.scalar(select(CartonCustomer).where(CartonCustomer.id == customer_id, CartonCustomer.factory_id == factory)
        .execution_options(populate_existing=True))
    if customer is None:
        raise HTTPException(404, "未找到本厂客户")
    if customer.revision != revision:
        raise HTTPException(409, "客户或责任范围已更新，请刷新后重试")
    return user, customer


def _finish(db, user, customer, before, after, owner_before, owner_after, reason, event):
    from app.services.carton_procurement import _audit, now_text
    customer.revision += 1
    customer.updated_by = user.id; customer.updated_by_name = user.display_name; customer.updated_at = now_text()
    _audit(db, user, customer.factory_id, event, "carton_customer", customer.id,
        dict(customer_code=customer.customer_code, reason=reason, before=before, after=sorted(after),
             owner_before=owner_before, owner_after=owner_after, revision=customer.revision))
    db.commit()
    return workspace(db, user, customer.factory_id)


def claim(db, user, customer_id, payload):
    factory = payload.factory_id
    user, customer = _locked_actor_customer(db, user, factory, customer_id, payload.expected_revision)
    if customer.status != "ACTIVE":
        raise HTTPException(409, "停用客户不能认领")
    if db.scalar(select(Assignment.user_id).where(Assignment.customer_id == customer.id, Assignment.factory_id == factory).limit(1)):
        raise HTTPException(409, "该客户已有负责人，请刷新或联系负责人授权")
    db.add(Assignment(customer_id=customer.id, factory_id=factory, user_id=user.id))
    db.add(Owner(customer_id=customer.id, factory_id=factory, user_id=user.id))
    return _finish(db, user, customer, [], [user.id], None, user.id, "员工自主认领客户", "CUSTOMER_RESPONSIBILITY_CLAIMED")


def save(db, user, customer_id, payload):
    factory = payload.factory_id
    user, customer = _locked_actor_customer(db, user, factory, customer_id, payload.expected_revision)
    owner = db.get(Owner, customer.id)
    manager = unrestricted(user, factory)
    before = sorted(db.scalars(select(Assignment.user_id).where(Assignment.customer_id == customer.id, Assignment.factory_id == factory)))
    if not manager and (owner is None or owner.user_id != user.id):
        raise HTTPException(403, "只有客户负责人或本厂主管可以授权同事；未认领客户请先认领")
    if len(set(payload.user_ids)) != len(payload.user_ids):
        raise HTTPException(422, "责任人员不能重复")
    for identifier in payload.user_ids:
        row = db.get(AuthUser, identifier)
        if row is None or row.status != "active" or not eligible(build_auth_context(db, row), factory):
            raise HTTPException(422, "所选人员缺少本厂订单或入库权限或账号已停用，请刷新人员列表")
    owner_before = owner.user_id if owner else None
    new_owner = payload.owner_user_id if "owner_user_id" in payload.model_fields_set else owner_before
    if not payload.user_ids:
        new_owner = None
    elif new_owner is None and len(payload.user_ids) == 1:
        new_owner = payload.user_ids[0]
    if not manager and new_owner != owner_before:
        raise HTTPException(403, "负责人转交或解除认领需要主管统筹权限")
    if new_owner is not None and new_owner not in payload.user_ids:
        raise HTTPException(422, "负责人必须保留在责任人员中；转交请同时选择新的负责人")
    db.execute(delete(Assignment).where(Assignment.customer_id == customer.id, Assignment.factory_id == factory))
    for identifier in payload.user_ids:
        db.add(Assignment(customer_id=customer.id, factory_id=factory, user_id=identifier))
    if owner:
        if new_owner: owner.user_id = new_owner
        else: db.delete(owner)
    elif new_owner:
        db.add(Owner(customer_id=customer.id, factory_id=factory, user_id=new_owner))
    return _finish(db, user, customer, before, payload.user_ids, owner_before, new_owner, payload.reason,
                   "CUSTOMER_RESPONSIBILITY_CHANGED")
