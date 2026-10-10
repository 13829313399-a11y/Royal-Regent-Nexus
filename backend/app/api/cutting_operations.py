from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.models.cutting_ops import CuttingMaster, CuttingRevision, CuttingOrder, CuttingOrderRevision
from app.services.auth import AuthContext, get_current_user
from app.services import cutting_ops as c, cutting_schemas as s
from app.services import cutting_orders as orders
from app.services import cutting_planning as planning, cutting_planning_schemas as ps
from app.services.permission_codes import CUTTING_OPS_PERMISSION_CODES


class CuttingRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request: Request):
            # Reject repeated scope parameters rather than picking the last one.
            if len(request.query_params.getlist('factory_id')) > 1:
                return JSONResponse({'detail': '厂区参数不能重复'}, status_code=422)
            try:
                return await original(request)
            except ValidationError as error:
                return JSONResponse({'detail': [{'loc': list(e['loc']), 'msg': e['msg']} for e in error.errors()]}, status_code=422)
        return handler


router = APIRouter(prefix='/api/cutting-operations', tags=['cutting-operations'], route_class=CuttingRoute)
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def ready(db):
    c.require(settings.cutting_ops_enabled, '裁床基础资料尚未启用', 503)
    c.require(c.schema_ready(db.connection()), '裁床基础资料需先完成显式数据库迁移', 503)


@router.get('/access')
def access(db: Db, user: User, factory_id: str = ''):
    c.authorize(user, factory_id)
    enabled = settings.cutting_ops_enabled
    migrated = c.schema_ready(db.connection()) if enabled else False
    return dict(enabled=enabled, schema_ready=migrated, orders_schema_ready=orders.schema_ready(db.connection()) if enabled else False,
                permissions=[code.split(':')[1] for code in
                CUTTING_OPS_PERMISSION_CODES if c.allowed(user, code.split(':')[1])])


@router.get('/masters')
def masters(db: Db, user: User, factory_id: str = '', kind: s.Kind = 'material',
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), q: str = Query('', max_length=80)):
    c.authorize(user, factory_id)
    ready(db)
    query = select(CuttingMaster).where(CuttingMaster.factory_id == factory_id, CuttingMaster.kind == kind)
    if q.strip():
        matches = [CuttingRevision.data[field].as_string().contains(q.strip(), autoescape=True) for field in ('name', 'item_no', 'style', 'color')]
        revisions = select(CuttingRevision.master_id).where(CuttingRevision.master_id == CuttingMaster.id, *[matches[0] | matches[1] | matches[2] | matches[3]]).exists()
        query = query.where(CuttingMaster.code.contains(q.strip(), autoescape=True) | revisions)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(CuttingMaster.code).offset((page-1)*page_size).limit(page_size))
    return dict(data=[c.view(db, item) for item in rows], total=total, page=page, page_size=page_size)


@router.get('/masters/{entity_id}/versions')
def versions(entity_id: str, db: Db, user: User, factory_id: str = '', page: int = Query(1, ge=1)):
    c.authorize(user, factory_id)
    ready(db)
    item = c.master(db, entity_id)
    numbers = db.scalars(select(CuttingRevision.version).where(CuttingRevision.master_id == item.id)
                         .order_by(CuttingRevision.version.desc()).offset((page-1)*50).limit(50))
    return dict(data=[c.view(db, item, version) for version in numbers], total=item.version, page=page, page_size=50)


@router.post('/masters')
def create(body: s.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_write' if body.kind == 'bom' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'create', lambda: c.save(db, user, body))


@router.put('/masters/{entity_id}')
def update(entity_id: str, body: s.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_write' if body.kind == 'bom' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'update:' + entity_id, lambda: c.save(db, user, body, entity_id))


@router.post('/masters/{entity_id}/state')
def change_state(entity_id: str, body: s.StateChange, db: Db, user: User):
    c.authorize(user, body.factory_id, 'bom_publish' if body.status == 'published' else 'master_write')
    ready(db)
    return c.command(db, user, body, 'state:' + entity_id, lambda: c.state(db, user, body, entity_id))


def orders_ready(db):
    ready(db)
    c.require(orders.schema_ready(db.connection()), '裁床订单与交期需先完成显式数据库迁移', 503)


@router.get('/orders')
def order_list(db: Db, user: User, factory_id: str = '', page: int = Query(1, ge=1), q: str = Query('', max_length=80),
               status: s.WorkflowStatus | None = None, plan_status: Annotated[str | None, Query(pattern='^(unplanned|partial|published|pending_actual|review)$')] = None):
    c.authorize(user, factory_id)
    orders_ready(db)
    return orders.list_orders(db, page, q, status, plan_status)


@router.get('/orders/{line_id}/versions')
def order_versions(line_id: str, db: Db, user: User, factory_id: str = '', page: int = Query(1, ge=1)):
    c.authorize(user, factory_id)
    orders_ready(db)
    order = db.get(CuttingOrder, line_id)
    c.require(order is not None and order.factory_id == c.FACTORY, '裁床订单不存在', 404)
    numbers = db.scalars(select(CuttingOrderRevision.version).where(CuttingOrderRevision.line_id == line_id)
        .order_by(CuttingOrderRevision.version.desc()).offset((page-1)*50).limit(50))
    return dict(data=[orders.revision(db, order, v) for v in numbers], total=order.version, page=page, page_size=50)


def order_command(db, user, line_id, body, action, handler):
    c.authorize(user, body.factory_id, action)
    orders_ready(db)
    result = c.command(db, user, body, action + ':' + line_id, lambda: handler(db, user, line_id, body))
    if action in {'plan_write', 'plan_publish'}:
        # A historical successful receipt must not hide current rule/resource invalidation.
        # Keep the immutable receipt intact, but return the current order view after replay.
        db.expire_all()
        return orders.view(db, orders.latest(db, line_id))
    return result


@router.post('/orders/{line_id}/receive')
def receive_order(line_id: str, body: s.ReceiveOrder, db: Db, user: User):
    return order_command(db, user, line_id, body, 'order_receive', orders.receive)


@router.post('/orders/{line_id}/bom')
def bind_order_bom(line_id: str, body: s.BindBom, db: Db, user: User):
    return order_command(db, user, line_id, body, 'bom_write', orders.bind_bom)


@router.post('/orders/{line_id}/requisition')
def submit_requisition(line_id: str, body: s.SubmitRequisition, db: Db, user: User):
    return order_command(db, user, line_id, body, 'requisition_submit', orders.submit)


@router.post('/orders/{line_id}/eta')
def eta_reply(line_id: str, body: s.ReplyEta, db: Db, user: User):
    return order_command(db, user, line_id, body, 'eta_write', orders.reply_eta)


@router.post('/orders/{line_id}/withdraw')
def withdraw_requisition(line_id: str, body: s.WithdrawRequisition, db: Db, user: User):
    return order_command(db, user, line_id, body, 'requisition_submit', orders.withdraw)


@router.post('/orders/{line_id}/reconcile')
def reconcile_requisition(line_id: str, body: s.ReconcileRequisition, db: Db, user: User):
    return order_command(db, user, line_id, body, 'requisition_reconcile', orders.reconcile)


@router.post('/orders/{line_id}/plan')
def save_plan(line_id: str, body: ps.SavePlan, db: Db, user: User):
    return order_command(db, user, line_id, body, 'plan_write', planning.save)


@router.post('/orders/{line_id}/plan-publish')
def publish_plan(line_id: str, body: ps.PublishPlan, db: Db, user: User):
    return order_command(db, user, line_id, body, 'plan_publish', planning.publish)


@router.post('/orders/{line_id}/operations/recover')
def recover_order_operation(line_id: str, body: s.RecoverOperation, db: Db, user: User):
    contracts = {
        'receive': (s.ReceiveOrder, 'order_receive'), 'bom': (s.BindBom, 'bom_write'),
        'requisition': (s.SubmitRequisition, 'requisition_submit'), 'eta': (s.ReplyEta, 'eta_write'),
        'plan': (ps.SavePlan, 'plan_write'), 'plan-publish': (ps.PublishPlan, 'plan_publish'),
        'withdraw': (s.WithdrawRequisition, 'requisition_submit'), 'reconcile': (s.ReconcileRequisition, 'requisition_reconcile'),
    }
    model, permission = contracts[body.action]
    identity = s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作记录需先完成迁移', 503)
    try:
        original = model.model_validate(body.command)
    except ValidationError:
        # Even a lost validation response can be resolved. Fence this operation id under
        # the same lock; a delayed request cannot write after the editor is released.
        return orders.recover_operation(db, user, identity, permission + ':' + line_id, invalid_payload=body.command)
    # Read access plus ownership is enough to resolve/stop an own command after write revocation.
    # No source-state check here: stale/cancelled orders must still be recoverable.
    return orders.recover_operation(db, user, original, permission + ':' + line_id)
