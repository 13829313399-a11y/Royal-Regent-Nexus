"""Read-only order basis for demand drafts; never dispatches or reserves orders."""
from sqlalchemy import inspect, or_, select
from app.models.customer_order_ledger import OrderLedgerLine
from app.services import engineering_bom as bom
from app.services.auth import authorization_decision


def allowed(user):
    return authorization_decision(user, 'customer_order:read', bom.FACTORY, 'sales-business')[0]


def authorize(user):
    bom.require(allowed(user), '关联订单需要华康 C 业务部的客户订单查看权限', 403)


def ready(db):
    inspector = inspect(db.get_bind())
    table = OrderLedgerLine.__table__
    return inspector.has_table(table.name) and set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}


def snapshot(row):
    def decimal(value):
        return None if value is None else format(value, 'f')
    return dict(line_id=row.id, factory_id=row.factory_id, revision=row.revision, version=row.version,
        customer_code=row.customer_code, customer_name=row.customer_name, reference_no=row.reference_no,
        product_no=row.product_no, quantity=decimal(row.quantity), shipped_quantity=decimal(row.shipped_quantity), status=row.status)


def search(db, user, query):
    authorize(user)
    bom.require(ready(db), '客户订单数据结构尚未部署', 503)
    stmt = select(OrderLedgerLine).where(OrderLedgerLine.factory_id == bom.FACTORY, OrderLedgerLine.status == 'active',
        OrderLedgerLine.quantity > 0)
    if query.strip():
        stmt = stmt.where(or_(*(column.contains(query.strip(), autoescape=True) for column in
            (OrderLedgerLine.reference_no, OrderLedgerLine.product_no, OrderLedgerLine.customer_name))))
    rows = list(db.scalars(stmt.order_by(OrderLedgerLine.updated_at.desc(), OrderLedgerLine.id).limit(51)))
    return dict(items=[snapshot(row) for row in rows[:50]], has_more=len(rows) > 50)


def resolve(db, user, reference, frozen, quantity):
    if not reference:
        return None
    authorize(user)
    bom.require(ready(db), '客户订单数据结构尚未部署', 503)
    # Called after engineering/trial factory locks. PG row lock also serializes
    # against the ledger's optimistic UPDATE without changing its revision.
    row = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.id == reference.line_id,
        OrderLedgerLine.factory_id == bom.FACTORY).with_for_update().execution_options(populate_existing=True))
    bom.require(row is not None, '当前厂区中没有此订单', 404)
    bom.require(row.revision == reference.revision, '订单依据已变化，请重新选择并核对数量、货号和 BOM', 409)
    bom.require(row.status == 'active' and row.quantity is not None and row.quantity > 0, '订单已取消或数量未核实，不能作为新试算依据', 409)
    bom.require(row.product_no.strip() == frozen['data']['item_no'].strip(), '订单货号与 BOM 货号不一致，请选择对应 BOM', 422)
    bom.require(quantity <= row.quantity, '试算数量不能超过所关联订单数量；补料及追加请走后续补单流程', 422)
    return snapshot(row)


def require_snapshot_access(user, saved):
    if saved.get('inputs', {}).get('order'):
        authorize(user)
