"""Factory/customer responsibility checks for order work, separate from stock and QC."""
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.auth import AuthUser
from app.models.carton_customer_assignment import CartonCustomerAssignment as Assignment
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


def ensure_customer_operation(db, user, factory, customer_code):
    # Every business caller already holds the shared factory transaction lock.
    if unrestricted(user, factory) or customer_code.strip().upper() in assigned_codes(db, user, factory):
        return
    raise HTTPException(403, "该客户未分配给你，无法操作此客户订单；请联系主管分配客户责任范围")


def workspace(db, user, factory, *, summary=False):
    manager = unrestricted(user, factory)
    result = dict(can_manage=manager, unrestricted=manager,
                  own_customer_codes=sorted(assigned_codes(db, user, factory)), users=[], customers=[])
    if not manager or summary:
        return result
    customers = list(db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id == factory).order_by(CartonCustomer.customer_name)))
    bindings = list(db.scalars(select(Assignment).where(Assignment.factory_id == factory)))
    identifiers = {binding.user_id for binding in bindings}
    users = list(db.scalars(select(AuthUser).where(AuthUser.status == "active").order_by(AuthUser.display_name, AuthUser.id)))
    candidates = [dict(id=row.id, name=row.display_name) for row in users
                  if allowed(build_auth_context(db, row), factory, "order_write")]
    names = {row.id: row.display_name for row in users}
    if identifiers - set(names):
        names.update((row.id, row.display_name) for row in db.scalars(select(AuthUser).where(AuthUser.id.in_(identifiers - set(names)))))
    return dict(**{key: value for key, value in result.items() if key not in {"users", "customers"}},
                users=candidates, customers=[dict(id=row.id, code=row.customer_code, name=row.customer_name,
                    revision=row.revision, status=row.status,
                    users=[dict(id=b.user_id, name=names.get(b.user_id, "账号已停用")) for b in bindings if b.customer_id == row.id])
                    for row in customers])


def save(db, user, customer_id, payload):
    from app.services.carton_procurement import _lock_receipt_factory, _audit, now_text
    factory = payload.factory_id
    _lock_receipt_factory(db, factory)
    actor = db.get(AuthUser, user.id)
    if actor is None or actor.status != "active":
        raise HTTPException(403, "账号已停用，请重新登录")
    user = build_auth_context(db, actor)
    if not unrestricted(user, factory):
        raise HTTPException(403, "客户责任分配需要本厂主管订单统筹权限")
    customer = db.scalar(select(CartonCustomer).where(CartonCustomer.id == customer_id, CartonCustomer.factory_id == factory).execution_options(populate_existing=True))
    if customer is None:
        raise HTTPException(404, "未找到本厂客户")
    if customer.revision != payload.expected_revision:
        raise HTTPException(409, "客户或责任范围已更新，请刷新后重新分配")
    if len(set(payload.user_ids)) != len(payload.user_ids):
        raise HTTPException(422, "责任人员不能重复")
    for identifier in payload.user_ids:
        row = db.get(AuthUser, identifier)
        if row is None or row.status != "active" or not allowed(build_auth_context(db, row), factory, "order_write"):
            raise HTTPException(422, "所选人员缺少本厂订单操作权限或账号已停用，请刷新人员列表")
    before = sorted(db.scalars(select(Assignment.user_id).where(Assignment.customer_id == customer.id, Assignment.factory_id == factory)))
    db.execute(delete(Assignment).where(Assignment.customer_id == customer.id, Assignment.factory_id == factory))
    for identifier in payload.user_ids:
        db.add(Assignment(customer_id=customer.id, factory_id=factory, user_id=identifier))
    customer.revision += 1
    customer.updated_by = user.id; customer.updated_by_name = user.display_name; customer.updated_at = now_text()
    _audit(db, user, factory, "CUSTOMER_RESPONSIBILITY_CHANGED", "carton_customer", customer.id,
           dict(customer_code=customer.customer_code, reason=payload.reason, before=before,
                after=sorted(payload.user_ids), revision=customer.revision))
    db.commit()
    return workspace(db, user, factory)
