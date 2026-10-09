"""P1c evidence chain. Estimated dates never create stock or financial postings."""
from copy import deepcopy
from datetime import datetime, UTC
from zoneinfo import ZoneInfo
from decimal import Decimal, localcontext
from sqlalchemy import inspect, select, func, or_
from app.models.cutting_ops import CuttingOrder, CuttingOrderRevision, CuttingCommand
from app.models.customer_order_ledger import OrderLedgerLine, OrderLedgerDispatch
from app.services import cutting_ops as c
from app.services.transaction_lock import lock_transaction

TABLES = (CuttingOrder.__table__, CuttingOrderRevision.__table__)


def schema_ready(bind):
    inspector = inspect(bind)
    names = set(inspector.get_table_names())
    return c.schema_ready(bind) and all(t.name in names and {col.name for col in t.columns} <=
        {col['name'] for col in inspector.get_columns(t.name)} for t in TABLES)


def latest(db, line_id):
    return db.scalar(select(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id == line_id,
        OrderLedgerDispatch.factory_id == c.FACTORY, OrderLedgerDispatch.recipient == 'cutting')
        .order_by(OrderLedgerDispatch.version.desc()).limit(1))


def revision(db, order, version=None):
    r = db.get(CuttingOrderRevision, (order.line_id, version or order.version))
    c.require(r is not None, '裁床订单版本不存在', 404)
    return dict(version=r.version, data=r.data, actor_id=r.actor_id, created_at=r.created_at, reason=r.reason)


def view(db, dispatch):
    order = db.get(CuttingOrder, dispatch.line_id)
    current = revision(db, order) if order else None
    needs_receipt = order is None or order.dispatch_id != dispatch.id
    data = current['data'] if current else {}
    status = workflow_status(data, dispatch.snapshot.get('status'), needs_receipt)
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    overdue = any(b['expected_date'] < today for b in data.get('batches', []))
    pending_version = pending_purchase_version(db, order, data) if order else None
    pending = purchase_snapshot(db, order.line_id, pending_version) if pending_version else None
    return dict(line_id=dispatch.line_id, dispatch_id=dispatch.id, source_version=dispatch.version,
        snapshot=dispatch.snapshot, received_at=dispatch.received_at,
        needs_receipt=needs_receipt, current=current, workflow_status=status,
        expected_date_passed=overdue, pending_purchase=pending)


def workflow_status(data, source_status='active', needs_receipt=False):
    if needs_receipt:
        return 'cancelled_receipt' if source_status == 'cancelled' else 'awaiting_receipt'
    if data.get('purchase_reconciliation_required'):
        return 'reconciliation'
    if source_status == 'cancelled':
        return 'cancelled'
    req = data.get('requisition')
    if not req:
        return 'awaiting_submission' if data.get('bom') else 'awaiting_bom'
    quantities = [Decimal(r['quantity']) for r in req['lines']]
    if not any(quantities):
        return 'no_purchase'
    totals = {r['row']: Decimal(0) for r in req['lines']}
    for b in data.get('batches', []):
        totals[b['row']] += Decimal(b['quantity'])
    if not any(totals.values()):
        return 'awaiting_reply'
    return 'complete_reply' if all(totals[r['row']] == Decimal(r['quantity']) for r in req['lines']) else 'partial_reply'


def purchase_snapshot(db, line_id, version):
    r = db.scalar(select(CuttingOrderRevision).where(CuttingOrderRevision.line_id == line_id,
        CuttingOrderRevision.data['requisition']['version'].as_integer() == version)
        .order_by(CuttingOrderRevision.version.desc()).limit(1))
    c.require(r is not None, '待核对的原需求版本缺失，请核对历史', 409)
    return dict(requisition=r.data['requisition'], bom=r.data['bom'], order=r.data['order'], batches=r.data['batches'])


def pending_purchase_version(db, order, data):
    if not data.get('purchase_reconciliation_required'):
        return None
    if data.get('pending_requisition_version'):
        return data['pending_requisition_version']
    # Compatibility with the initial P1c source-change snapshots, which only stored a flag.
    r = db.scalar(select(CuttingOrderRevision).where(CuttingOrderRevision.line_id == order.line_id,
        CuttingOrderRevision.version <= order.version,
        CuttingOrderRevision.data['requisition']['version'].as_integer().is_not(None))
        .order_by(CuttingOrderRevision.version.desc()).limit(1))
    c.require(r is not None, '原采购需求缺失，不能直接解除核对', 409)
    return r.data['requisition']['version']


def list_orders(db, page, q, status=None):
    newest = select(OrderLedgerDispatch.line_id, func.max(OrderLedgerDispatch.version).label('version')).where(
        OrderLedgerDispatch.factory_id == c.FACTORY, OrderLedgerDispatch.recipient == 'cutting').group_by(
        OrderLedgerDispatch.line_id).subquery()
    query = select(OrderLedgerDispatch).join(newest, (newest.c.line_id == OrderLedgerDispatch.line_id) &
        (newest.c.version == OrderLedgerDispatch.version)).join(OrderLedgerLine).where(
        OrderLedgerDispatch.factory_id == c.FACTORY, OrderLedgerDispatch.recipient == 'cutting')
    if q.strip():
        query = query.where(OrderLedgerLine.reference_no.contains(q.strip(), autoescape=True) |
                            OrderLedgerLine.product_no.contains(q.strip(), autoescape=True))
    if status:
        query = query.outerjoin(CuttingOrder, CuttingOrder.line_id == OrderLedgerDispatch.line_id).outerjoin(
            CuttingOrderRevision, (CuttingOrderRevision.line_id == CuttingOrder.line_id) &
            (CuttingOrderRevision.version == CuttingOrder.version))
        stale = or_(CuttingOrder.line_id.is_(None), CuttingOrder.dispatch_id != OrderLedgerDispatch.id)
        if status in {'awaiting_receipt', 'cancelled_receipt'}:
            query = query.where(stale)
        else:
            query = query.where(~stale, or_(CuttingOrderRevision.data['workflow_status'].as_string() == status,
                CuttingOrderRevision.data['workflow_status'].as_string().is_(None)))
        # Only legacy snapshots lacking the derived status need a compatibility scan.
        matches, total = [], 0
        for dispatch in db.scalars(query.order_by(OrderLedgerDispatch.created_at.desc(), OrderLedgerDispatch.id)).yield_per(50):
            result = view(db, dispatch)
            if result['workflow_status'] != status:
                continue
            if (page-1)*50 <= total < page*50:
                matches.append(result)
            total += 1
        return dict(data=matches, total=total, page=page, page_size=50)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(OrderLedgerDispatch.created_at.desc(), OrderLedgerDispatch.id)
                      .offset((page-1)*50).limit(50))
    return dict(data=[view(db, d) for d in rows], total=total, page=page, page_size=50)


def lock_source(db, line_id):
    # Share the ledger's row lock on PostgreSQL; command() reserves SQLite's writer.
    line = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.id == line_id,
        OrderLedgerLine.factory_id == c.FACTORY).with_for_update().execution_options(populate_existing=True))
    c.require(line is not None, '华康C来源订单不存在', 404)
    dispatch = latest(db, line_id)
    c.require(dispatch is not None, '订单尚未向裁床下发', 404)
    c.require(dispatch.version == line.version, '来源订单已有新版本，请等待重新下发')
    return line, dispatch


def append(db, user, order, data, reason):
    data['workflow_status'] = workflow_status(data, data['order'].get('status'))
    order.version += 1
    db.add(CuttingOrderRevision(line_id=order.line_id, version=order.version, data=data,
        actor_id=user.id, created_at=datetime.now(UTC).isoformat(), reason=reason))
    db.flush()
    return view(db, latest(db, order.line_id))


def receive(db, user, line_id, body):
    line, dispatch = lock_source(db, line_id)
    c.require(dispatch.id == body.dispatch_id, '只能接收最新下发版本')
    order = db.get(CuttingOrder, line_id)
    if order and order.dispatch_id == dispatch.id:
        return view(db, dispatch)  # Separate retries cannot create another receipt revision.
    c.require((order.version if order else 0) == body.expected_version, '裁床记录已更新，请重新读取')
    if order is None:
        order = CuttingOrder(line_id=line_id, factory_id=c.FACTORY, dispatch_id=dispatch.id, version=0)
        db.add(order)
    previous = revision(db, order)['data'] if order.version else None
    # Never imply that replacing a source version cancels a real purchase order.
    pending_version = None
    if previous:
        pending_version = previous['requisition']['version'] if previous.get('requisition') else pending_purchase_version(db, order, previous)
    order.dispatch_id = dispatch.id
    dispatch.received_at = datetime.now(UTC).isoformat()
    dispatch.received_by = user.id
    data = dict(order=deepcopy(dispatch.snapshot), dispatch_id=dispatch.id, bom=None, requisition=None,
                batches=[], purchase_reconciliation_required=bool(pending_version), pending_requisition_version=pending_version,
                reconciliation_request={'kind': 'source_change', 'actor_id': user.id, 'reason': body.reason} if pending_version else None)
    return append(db, user, order, data, body.reason)


def writable(db, line_id, expected, *, allow_cancelled=False):
    line, dispatch = lock_source(db, line_id)
    c.require(allow_cancelled or line.status == 'active', '订单已取消，仅可签收通知及核对旧采购需求')
    order = db.get(CuttingOrder, line_id)
    c.require(order is not None and order.dispatch_id == dispatch.id, '请先签收最新订单版本')
    c.require(order.version == expected, '裁床记录已更新，请重新读取后再操作')
    return order, deepcopy(revision(db, order)['data'])


def bind_bom(db, user, line_id, body):
    order, data = writable(db, line_id, body.expected_version)
    c.require(not data['requisition'], '需求已提交，不能直接替换 BOM；需先核对原需求')
    item = c.master(db, body.bom_id)
    c.require(item.kind == 'bom', '请选择生产 BOM', 422)
    bom = c.view(db, item, body.bom_version)
    c.require(bom['status'] == 'published', '只能明确选择已发布 BOM 版本', 422)
    c.require(bom['data']['item_no'] == data['order']['product_no'] or body.bom_match_basis,
              '订单与 BOM 货号不同，请工程明确填写对应依据', 422)
    c.validate_references(db, bom['data'], publishing=True)
    data.update(bom=bom, target_sets=body.target_sets, quantity_basis=body.quantity_basis, bom_match_basis=body.bom_match_basis)
    return append(db, user, order, data, body.reason)


def submit(db, user, line_id, body):
    order, data = writable(db, line_id, body.expected_version)
    c.require(data['bom'] is not None, '工程需先关联已发布 BOM')
    c.require(not data['requisition'], '物料需求已提交，不可重复提交')
    c.require(not data['purchase_reconciliation_required'], '旧版已有采购需求，请先由采购确认变更核对')
    requirements = data['bom']['data']['requirements']
    c.validate_references(db, data['bom']['data'], publishing=True)
    c.require(sorted(r.row for r in body.lines) == list(range(len(requirements))), '需求必须逐行覆盖 BOM，不可重复或遗漏', 422)
    lines = []
    with localcontext() as ctx:
        ctx.prec = 50
        for row in sorted(body.lines, key=lambda r: r.row):
            req = requirements[row.row]
            ref = data['bom']['material_references'][f"{req['material_id']}:{req['material_version']}"]
            lines.append(dict(req, row=row.row, material=ref, quantity=str(row.quantity),
                purchase_mode=row.purchase_mode, no_purchase_reason=row.no_purchase_reason,
                replied_quantity='0', awaiting_reply_quantity=str(row.quantity),
                theoretical_quantity=format(Decimal(req['quantity_per_set']) * data['target_sets'], 'f')))
    data['requisition'] = dict(version=order.version+1, lines=lines, actor_id=user.id,
        created_at=datetime.now(UTC).isoformat(), supersedes_version=data.get('reconciliation', {}).get('requisition_version'))
    data['batches'] = []
    return append(db, user, order, data, body.reason)


def reply_eta(db, user, line_id, body):
    order, data = writable(db, line_id, body.expected_version)
    c.require(not data['purchase_reconciliation_required'], '需求变更待采购核对，不能继续回复原交期')
    req = data['requisition']
    c.require(req and req['version'] == body.requisition_version, '请针对当前已提交需求回复交期')
    totals = {row['row']: Decimal(0) for row in req['lines']}
    for batch in body.batches:
        c.require(batch.row in totals, '交期批次未对应当前需求行', 422)
        totals[batch.row] += batch.quantity
    for row in req['lines']:
        c.require(totals[row['row']] <= Decimal(row['quantity']), '分批交期数量合计不能超过需求量', 422)
        row['replied_quantity'] = str(totals[row['row']])
        row['awaiting_reply_quantity'] = str(Decimal(row['quantity']) - totals[row['row']])
    data['batches'] = [b.model_dump(mode='json') for b in body.batches]
    return append(db, user, order, data, body.reason)


def withdraw(db, user, line_id, body):
    order, data = writable(db, line_id, body.expected_version)
    req = data.get('requisition')
    c.require(req and req['version'] == body.requisition_version, '只能申请撤回当前已提交需求')
    c.require(not data['purchase_reconciliation_required'], '需求已在核对中，请等待采购处理')
    data.update(purchase_reconciliation_required=True, pending_requisition_version=req['version'],
        reconciliation_request=dict(kind='engineering_withdrawal', actor_id=user.id, reason=body.reason,
                                    created_at=datetime.now(UTC).isoformat()))
    return append(db, user, order, data, body.reason)


def reconcile(db, user, line_id, body):
    order, data = writable(db, line_id, body.expected_version, allow_cancelled=True)
    pending = pending_purchase_version(db, order, data)
    c.require(pending and pending == body.requisition_version, '请核对当前待处理的原需求版本')
    purchase_snapshot(db, line_id, pending)
    previous_versions = db.scalars(select(CuttingOrderRevision).where(CuttingOrderRevision.line_id == line_id,
        CuttingOrderRevision.data['requisition']['version'].as_integer() == pending)).yield_per(50)
    had_commitment = any(r.data.get('batches') for r in previous_versions)
    c.require(body.disposition != 'not_ordered' or not had_commitment,
              '原需求已有采购交期证据，请按已采购处置并说明，不可声明尚未采购', 422)
    data.update(requisition=None, batches=[], purchase_reconciliation_required=False, pending_requisition_version=None,
        reconciliation=dict(requisition_version=pending, disposition=body.disposition, evidence=body.evidence, all_handled=True,
                            actor_id=user.id, created_at=datetime.now(UTC).isoformat()), reconciliation_request=None)
    return append(db, user, order, data, body.reason)


def recover_operation(db, user, body, action, *, invalid_payload=None):
    """Resolve an own command or fence it off, atomically with any delayed writer."""
    fingerprint = c.command_fingerprint(body, action) if invalid_payload is None else c.payload_fingerprint(invalid_payload, action)
    try:
        lock_transaction(db, 'cutting-master', c.FACTORY)
        receipt = db.get(CuttingCommand, body.operation_id)
        if receipt:
            c.require(receipt.factory_id == c.FACTORY and receipt.actor_id == user.id and receipt.fingerprint == fingerprint,
                      '操作编号与当前账号或原请求不一致', 409)
            result = dict(state='abandoned') if receipt.result.get('operation_status') == 'abandoned' else dict(state='committed', result=receipt.result)
        else:
            db.add(CuttingCommand(operation_id=body.operation_id, factory_id=c.FACTORY, actor_id=user.id,
                action=action, fingerprint=fingerprint, result={'operation_status': 'abandoned'}, created_at=datetime.now(UTC).isoformat()))
            result = dict(state='abandoned')
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
