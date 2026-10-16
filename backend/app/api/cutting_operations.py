from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
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
from app.services import cutting_reporting as reporting, cutting_reporting_schemas as rs
from app.services import cutting_usage as usage, cutting_usage_schemas as us
from app.services import cutting_periods as periods, cutting_period_guards as period_guards, cutting_period_schemas as pcs
from app.services import cutting_settlement as settlement, cutting_settlement_schemas as ss
from app.services import cutting_payments as payments, cutting_payment_schemas as pay
from app.services import cutting_exports as exports
from app.services import cutting_cutover as cutover
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
                reporting_schema_ready=reporting.schema_ready(db.connection()) if enabled else False,
                usage_schema_ready=usage.schema_ready(db.connection()) if enabled else False,
                periods_schema_ready=period_guards.schema_ready(db.connection()) if enabled else False,
                settlements_schema_ready=settlement.schema_ready(db.connection()) if enabled else False,
                payments_schema_ready=payments.schema_ready(db.connection()) if enabled else False,
                permissions=[code.split(':')[1] for code in
                CUTTING_OPS_PERMISSION_CODES if c.allowed(user, code.split(':')[1])])


@router.post('/cutover/preview')
def cutover_preview(body: cutover.Selection, db: Db, user: User):
    for permission in cutover.PERMISSIONS[body.scope]:
        c.authorize(user, body.factory_id, permission)
    orders_ready(db)
    return JSONResponse(cutover.preview(db, body), headers={'Cache-Control': 'no-store'})


@router.post('/exports/preview')
def export_preview(body: exports.Selection, db: Db, user: User):
    c.authorize(user, body.factory_id, exports.PERMISSIONS[body.kind])
    orders_ready(db)
    report = exports.capture(db, body)
    return dict(token=periods.digest(report), title=exports.TITLES[body.kind], metadata=report['metadata'],
                sheets=[dict(name=s['name'], rows=len(s['rows'])) for s in report['sheets']], delivery=report['delivery'])


@router.post('/exports/download')
def export_download(body: exports.Selection, request: Request, db: Db, user: User):
    permission = exports.PERMISSIONS[body.kind]
    c.authorize(user, body.factory_id, permission)
    orders_ready(db)
    report = exports.capture(db, body)
    c.require(body.token and body.token == periods.digest(report), '报表依据或当前有效状态已变化，请重新预览导出')
    report.update(token=body.token, captured_at=exports.business_now().isoformat())
    db.rollback()  # XLSX generation holds no cutting/warehouse write lock.
    content, extension = exports.package(report, user)
    db.expire_all()
    current = get_current_user(request, db)
    c.require(current.id == user.id, '登录身份已变化，请重新导出', 403)
    c.authorize(current, body.factory_id, permission)
    orders_ready(db)
    # Recheck after generation: do not download a newly reopened or changed live report unnoticed.
    c.require(periods.digest(exports.capture(db, body)) == body.token, '生成期间报表依据发生变化，请重新预览导出')
    filename = f'cutting-{body.kind}-{body.month}-{body.token[:12]}.{extension}'
    return Response(content, media_type='application/zip' if extension == 'zip' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store',
                 'X-Content-Type-Options': 'nosniff', 'X-Cutting-Report-Token': body.token})


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


@router.get('/settlements/{month}')
def settlement_read(month: pcs.Month, db: Db, user: User, factory_id: str = '', document_id: str | None = None, event_id: str | None = None):
    c.authorize(user, factory_id, 'settlement_read')
    orders_ready(db)
    result = settlement.read(db, month, document_id, event_id)
    if document_id and c.allowed(user, 'payment_read'):
        result['payment_dependencies'] = payments.blockers(db, document_id)
    return result


@router.get('/settlements/{month}/basis')
def settlement_basis(month: pcs.Month, db: Db, user: User, factory_id: str = '', document_id: str | None = None):
    c.authorize(user, factory_id, 'settlement_read')
    orders_ready(db)
    return settlement.basis(db, month, document_id)


@router.post('/settlement-preview')
def settlement_preview(body: ss.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'settlement_read')
    orders_ready(db)
    return settlement.preview(db, body)


@router.post('/settlements/{action}')
def settlement_write(action: ss.Action, body: dict, db: Db, user: User):
    permission = 'settlement_price' if action == 'price' else 'settlement_prepare' if action in {'save', 'submit'} else 'settlement_reopen' if action == 'reopen' else 'settlement_confirm'
    c.authorize(user, body.get('factory_id', ''), 'settlement_read')
    c.authorize(user, body.get('factory_id', ''), permission)
    orders_ready(db)
    parsed = ss.parse(action, body)
    return c.command(db, user, parsed, 'settlement-'+action, lambda: settlement.execute(db, user, parsed, action))


@router.post('/settlement-operations/recover')
def settlement_recover(body: ss.Recover, db: Db, user: User):
    identity = s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作回执需先完成迁移', 503)
    try:
        parsed = ss.parse(body.action, body.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, 'settlement-'+body.action, invalid_payload=body.command)
    return orders.recover_operation(db, user, parsed, 'settlement-'+body.action)


@router.get('/payments/{month}')
def payment_read(month: pcs.Month, db: Db, user: User, factory_id: str = '', document_id: str | None = None, event_id: str | None = None):
    c.authorize(user, factory_id, 'payment_read')
    orders_ready(db)
    return payments.read(db, month, document_id, event_id)


@router.get('/payment-basis')
def payment_basis(db: Db, user: User, factory_id: str = '', document_id: str | None = None):
    c.authorize(user, factory_id, 'payment_read')
    orders_ready(db)
    return payments.basis(db, document_id)


@router.post('/payment-preview')
def payment_preview(body: pay.Save, db: Db, user: User):
    c.authorize(user, body.factory_id, 'payment_read')
    orders_ready(db)
    return payments.preview(db, body)


@router.post('/payments/{action}')
def payment_write(action: pay.Action, body: dict, db: Db, user: User):
    c.authorize(user, body.get('factory_id', ''), 'payment_read')
    permission = 'payment_prepare' if action in {'save', 'submit'} else 'payment_reverse' if action == 'reverse' else 'payment_confirm'
    c.authorize(user, body.get('factory_id', ''), permission)
    orders_ready(db)
    parsed = pay.parse(action, body)
    return c.command(db, user, parsed, 'payment-'+action, lambda: payments.execute(db, user, parsed, action))


@router.post('/payment-operations/recover')
def payment_recover(body: pay.Recover, db: Db, user: User):
    identity = s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '付款操作回执需先完成迁移', 503)
    try:
        parsed = pay.parse(body.action, body.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, 'payment-'+body.action, invalid_payload=body.command)
    return orders.recover_operation(db, user, parsed, 'payment-'+body.action)


@router.get('/periods/{month}')
def period_read(month: pcs.Month, db: Db, user: User, factory_id: str = '', event_id: str | None = None):
    c.authorize(user, factory_id, 'cost_read')
    orders_ready(db)
    return periods.read(db, month, event_id)


@router.get('/periods/{month}/basis')
def period_basis(month: pcs.Month, db: Db, user: User, factory_id: str = ''):
    c.authorize(user, factory_id, 'cost_read')
    orders_ready(db)
    return periods.prepare(db, month)


@router.post('/periods/{action}')
def period_write(action: Literal['save', 'submit', 'return', 'lock', 'reopen'], body: dict, db: Db, user: User):
    permission = 'period_prepare' if action in {'save', 'submit'} else 'period_reopen' if action == 'reopen' else 'period_lock'
    c.authorize(user, body.get('factory_id', ''), permission)
    c.authorize(user, body.get('factory_id', ''), 'cost_read')
    orders_ready(db)
    parsed = (pcs.PeriodSave if action == 'save' else pcs.PeriodDecision).model_validate(body)
    return c.command(db, user, parsed, 'period-'+action, lambda: periods.execute(db, user, parsed, action))


@router.post('/period-operations/recover')
def period_recover(body: pcs.RecoverPeriod, db: Db, user: User):
    identity = s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作回执需先完成迁移', 503)
    try:
        parsed = (pcs.PeriodSave if body.action == 'save' else pcs.PeriodDecision).model_validate(body.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, 'period-'+body.action, invalid_payload=body.command)
    return orders.recover_operation(db, user, parsed, 'period-'+body.action)


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


@router.get('/orders/{line_id}')
def read_order(line_id: str, db: Db, user: User, factory_id: str = ''):
    c.authorize(user, factory_id)
    orders_ready(db)
    dispatch = orders.latest(db, line_id)
    c.require(dispatch is not None, '华康C裁床来源订单不存在', 404)
    return orders.view(db, dispatch)


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


@router.get('/orders/{line_id}/reports')
def production_reports(line_id: str, db: Db, user: User, factory_id: str = '', as_of: ps.BusinessDate | None = None):
    c.authorize(user, factory_id)
    orders_ready(db)
    c.require(reporting.schema_ready(db.connection()), '每日填数需先完成 0155 显式迁移', 503)
    return reporting.view(db, line_id, as_of.isoformat() if as_of else None)


def report_permission(db, line_id, body, action):
    if action == 'review': return 'report_review'
    if action in {'void', 'discard'}:
        document=reporting.documents(reporting.events(db, line_id)).get(body.document_id)
        c.require(document is not None, '原记录不存在', 404)
        entry=(document['posted'] or document['draft'] or document['history'][0])['data']['entry']
        kind=entry['kind']
    else: kind=body.entry.kind
    return 'handover_write' if kind=='handover' else 'acceptance_write' if kind in {'return','accept'} else 'report_write'


@router.post('/orders/{line_id}/reports/{action}')
def production_command(line_id: str, action: Literal['save', 'post', 'void', 'review', 'discard'], body: dict, db: Db, user: User):
    c.authorize(user, body.get('factory_id', ''))
    orders_ready(db)
    c.require(reporting.schema_ready(db.connection()), '每日填数需先完成 0155 显式迁移', 503)
    parsed=(rs.ReportCommand if action in {'save','post'} else rs.ReportDecision).model_validate(body)
    c.authorize(user, parsed.factory_id, report_permission(db, line_id, parsed, action))
    c.command(db, user, parsed, 'report-'+action+':'+line_id, lambda: reporting.apply(db, user, line_id, parsed, action))
    db.expire_all()
    return reporting.view(db, line_id)


@router.post('/orders/{line_id}/report-operations/recover')
def recover_production(line_id: str, body: rs.RecoverReport, db: Db, user: User):
    identity=s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id','operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作记录需先完成迁移', 503)
    action='report-'+body.action+':'+line_id
    try:
        parsed=(rs.ReportCommand if body.action in {'save','post'} else rs.ReportDecision).model_validate(body.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, action, invalid_payload=body.command)
    return orders.recover_operation(db, user, parsed, action)


@router.get('/warehouse-materials')
def warehouse_materials(db: Db, user: User, factory_id: str = '', q: str = Query('', max_length=80), page: int = Query(1, ge=1)):
    from app.services import cutting_materials as materials
    c.authorize(user, factory_id)
    orders_ready(db)
    return materials.catalog(db, q, page)


@router.get('/orders/{line_id}/materials')
def order_materials(line_id: str, db: Db, user: User, factory_id: str = ''):
    from app.services import cutting_materials as materials
    c.authorize(user, factory_id)
    orders_ready(db)
    return materials.read(db, line_id)


@router.post('/orders/{line_id}/materials/{action}')
def material_command(line_id: str, action: Literal['request', 'receive', 'void', 'close', 'reuse'], body: dict, db: Db, user: User):
    from app.services import cutting_materials as materials, cutting_material_schemas as ms
    c.authorize(user, body.get('factory_id', ''), 'material_request' if action in {'request', 'close', 'reuse'} else 'material_receive')
    orders_ready(db)
    parsed = (ms.MaterialRequest if action == 'request' else ms.MaterialReceipt if action == 'receive' else ms.MaterialReuse if action == 'reuse' else ms.MaterialDecision).model_validate(body)
    return c.command(db, user, parsed, 'material-'+action+':'+line_id, lambda: materials.execute(db, user, line_id, parsed, action))


@router.post('/orders/{line_id}/material-operations/recover')
def recover_material_operation(line_id: str, body: dict, db: Db, user: User):
    from app.services import cutting_material_schemas as ms
    parsed = ms.RecoverMaterial.model_validate(body)
    identity = s.OperationIdentity.model_validate({key: parsed.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作记录需先完成迁移', 503)
    action = 'material-'+parsed.action+':'+line_id
    model = ms.MaterialRequest if parsed.action == 'request' else ms.MaterialReceipt if parsed.action == 'receive' else ms.MaterialReuse if parsed.action == 'reuse' else ms.MaterialDecision
    try:
        original = model.model_validate(parsed.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, action, invalid_payload=parsed.command)
    return orders.recover_operation(db, user, original, action)


@router.get('/orders/{line_id}/usage')
def material_usage(line_id: str, db: Db, user: User, factory_id: str = '', with_costs: bool = False):
    c.authorize(user, factory_id, 'cost_read' if with_costs else 'read')
    orders_ready(db)
    return usage.read(db, line_id, show_costs=with_costs)


@router.get('/orders/{line_id}/closing-preview')
def closing_preview(line_id: str, db: Db, user: User, month: str = Query(..., min_length=7, max_length=7),
                    factory_id: str = '', with_costs: bool = False):
    from app.services import cutting_closing
    c.authorize(user, factory_id, 'cost_read' if with_costs else 'read')
    orders_ready(db)
    return cutting_closing.read(db, line_id, month, show_costs=with_costs)


@router.get('/orders/{line_id}/usage-balance')
def usage_balance(line_id: str, db: Db, user: User, day: ps.BusinessDate, issue_id: str, factory_id: str = '', document_id: str = ''):
    c.authorize(user, factory_id)
    orders_ready(db)
    return usage.balance_preview(db, line_id, issue_id, day, document_id=document_id)


@router.post('/orders/{line_id}/usage/{action}')
def usage_command(line_id: str, action: Literal['post', 'void', 'review', 'price', 'correct', 'allocate'], body: dict, db: Db, user: User):
    c.authorize(user, body.get('factory_id', ''), 'allocation_confirm' if action == 'allocate' else 'cost_write' if action == 'price' else 'usage_review' if action == 'review' else 'usage_write')
    if action in {'price', 'allocate'}:
        c.authorize(user, body.get('factory_id', ''), 'cost_read')
    orders_ready(db)
    model = us.CostAllocation if action == 'allocate' else us.UsageCorrection if action == 'correct' else us.UsageCommand if action == 'post' else us.BatchCost if action == 'price' else us.UsageDecision
    parsed = model.model_validate(body)
    return c.command(db, user, parsed, 'usage-'+action+':'+line_id, lambda: usage.execute(db, user, line_id, parsed, action))


@router.post('/orders/{line_id}/usage-operations/recover')
def recover_usage(line_id: str, body: us.RecoverUsage, db: Db, user: User):
    identity = s.OperationIdentity.model_validate({key: body.command.get(key) for key in ('factory_id', 'operation_id')})
    c.authorize(user, identity.factory_id)
    c.require(c.schema_ready(db.connection()), '裁床操作记录需先完成迁移', 503)
    action = 'usage-'+body.action+':'+line_id
    model = us.CostAllocation if body.action == 'allocate' else us.UsageCorrection if body.action == 'correct' else us.UsageCommand if body.action == 'post' else us.BatchCost if body.action == 'price' else us.UsageDecision
    try:
        original = model.model_validate(body.command)
    except ValidationError:
        return orders.recover_operation(db, user, identity, action, invalid_payload=body.command)
    return orders.recover_operation(db, user, original, action)
