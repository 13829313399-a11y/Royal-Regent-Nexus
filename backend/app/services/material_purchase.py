"""Purchase preparation only: no supplier release or on-order supply is created."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from uuid import uuid4
from sqlalchemy import and_, inspect, select, text
from app.core.time import business_now
from app.models.material_purchase import MaterialPurchase, MaterialPurchaseEvent
from app.models.material_plan import MaterialPlan, MaterialPlanEvent
from app.models.customer_order_ledger import OrderLedgerLine
from app.schemas.material_purchase import PurchaseData
from app.services import material_plan as trial, material_plan_workflow as workflow
from app.services.auth import authorization_decision
from app.services.transaction_lock import lock_transaction

FACTORY = trial.FACTORY
DRAFT, PENDING, APPROVED, CHANGE, CANCELLED = 'DRAFT', 'PENDING_APPROVAL', 'APPROVED_UNRELEASED', 'CHANGE_PENDING', 'CANCELLED_UNRELEASED'
BLOCKERS = ['STOCK_AND_ON_ORDER_VERIFICATION', 'DEMAND_ALLOCATION', 'UNIT_CONVERSION', 'SUPPLIER_AND_COMMERCIAL_DATA', 'RELEASE_INTEGRATION']


def allowed(user, action):
    return authorization_decision(user, 'material_purchase:' + action, FACTORY, 'pmc-warehouse')[0]


def authorize(user, factory, action='read'):
    trial.bom.require(factory == FACTORY, '请选择华康 C', 422)
    trial.bom.require(allowed(user, 'read') and allowed(user, action), '没有采购准备流程相应权限', 403)


def ready(db):
    if not trial.ready(db): return False
    inspector = inspect(db.get_bind())
    for table in (MaterialPurchase.__table__, MaterialPurchaseEvent.__table__):
        if not inspector.has_table(table.name) or not set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}: return False
        if not any('huakang-c' in c['sqltext'] and 'factory_id' in c['sqltext'] for c in inspector.get_check_constraints(table.name)): return False
    unique = {frozenset(c['column_names']) for c in inspector.get_unique_constraints('material_purchase_events')}
    if not {frozenset(('factory_id', 'operation_id')), frozenset(('entity_id', 'version'))} <= unique: return False
    if db.get_bind().dialect.name == 'sqlite':
        triggers = set(db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='material_purchase_events'")))
        return {'material_purchase_no_update', 'material_purchase_no_delete'} <= triggers
    return bool(db.scalar(text("SELECT COUNT(*) FROM pg_trigger WHERE tgname='material_purchase_immutable' AND tgenabled <> 'D' AND tgrelid='material_purchase_events'::regclass")))


def group_key(line):
    return hashlib.sha256(trial.bom.dump([line['material_id'], line['material_version'], line['unit'], line['attribute']]).encode()).hexdigest()


def source_view(saved):
    return dict(id=saved['id'], version=saved['version'], item_no=saved['bom']['data']['item_no'],
        owner_name=saved['owner_name'], process_dates=saved['process_dates'],
        groups=[dict(line, source_key=group_key(line), purchasable=line['attribute'] in ('外购', '委外')) for line in saved['result']['totals']])


def source(db, identity, version):
    row = db.get(MaterialPlan, identity)
    trial.bom.require(row is not None and row.factory_id == FACTORY, '找不到本厂需求依据', 404)
    saved = workflow.latest(db, row)
    trial.bom.require(row.version == version and saved['status'] == workflow.REVIEWED, '需求版本或自审状态已变化，请业务重新核对', 409)
    trial.effective_bom(db, saved['bom']['id'], saved['bom']['version'])
    trial.bom.require(trial.orders.ready(db), '订单依据结构尚未部署', 503)
    reference = saved['inputs'].get('order')
    trial.bom.require(reference is not None, '需求缺少订单依据', 409)
    order = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.id == reference['line_id'], OrderLedgerLine.factory_id == FACTORY)
        .with_for_update().execution_options(populate_existing=True))
    trial.bom.require(order is not None and order.revision == reference['revision'] and order.status == 'active'
        and order.quantity is not None and Decimal(saved['inputs']['quantity']) <= order.quantity
        and order.product_no.strip() == saved['bom']['data']['item_no'].strip(), '订单依据已变化，请业务重新核对', 409)
    return source_view(saved)


def view(db, row):
    event = db.scalar(select(MaterialPurchaseEvent).where(MaterialPurchaseEvent.entity_id == row.id,
        MaterialPurchaseEvent.factory_id == FACTORY, MaterialPurchaseEvent.version == row.version))
    trial.bom.require(event is not None, '采购版本依据缺失', 409)
    return json.loads(event.result_json)


def record(db, identity):
    row = db.get(MaterialPurchase, identity)
    trial.bom.require(row is not None and row.factory_id == FACTORY, '找不到本厂采购准备单', 404)
    return row


def workspace(db):
    events = db.scalars(select(MaterialPlanEvent).join(MaterialPlan, and_(MaterialPlanEvent.entity_id == MaterialPlan.id,
        MaterialPlanEvent.factory_id == MaterialPlan.factory_id, MaterialPlanEvent.version == MaterialPlan.version)).where(MaterialPlan.factory_id == FACTORY))
    demands = [json.loads(e.result_json) for e in events]
    documents = [view(db, row) for row in db.scalars(select(MaterialPurchase).where(MaterialPurchase.factory_id == FACTORY))]
    return dict(sources=[source_view(d) for d in demands if d['status'] == workflow.REVIEWED],
        documents=sorted(documents, key=lambda s: s['occurred_at'], reverse=True))


def history(db, identity):
    record(db, identity)
    return [json.loads(e.result_json) for e in db.scalars(select(MaterialPurchaseEvent).where(
        MaterialPurchaseEvent.factory_id == FACTORY, MaterialPurchaseEvent.entity_id == identity).order_by(MaterialPurchaseEvent.version.desc()))]


def validate_lines(data, basis, complete=False):
    groups = {g['source_key']: g for g in basis['groups']}
    seen = set()
    for line in data['lines']:
        key = line['source_key']
        trial.bom.require(key in groups and groups[key]['purchasable'] and key not in seen, '采购行必须引用不重复的外购／委外来源，不得合并不同属性或加入自制／客供', 422)
        seen.add(key)
        if complete:
            trial.bom.require(line['quantity'] is not None and line['purchase_unit'] and line['unit_price'] is not None, '请填齐拟订整数数量、采购单位及单价', 422)
    if complete:
        trial.bom.require(data['lines'] and all(data[k] for k in ('supplier_reference', 'currency', 'delivery_date', 'delivery_location', 'payment_terms'))
            and data['tax_rate'] is not None, '请填齐供应商参考、币种、税率、交期、交货地点、付款条款及采购行', 422)


def command(db, user, body, action, identity=''):
    permission = 'release' if action == 'release' else 'approve' if action in ('approve', 'reject', 'approve-change', 'reject-change') else 'write'
    authorize(user, body.factory_id, permission)
    lock_transaction(db, 'engineering-bom', FACTORY)
    lock_transaction(db, 'material-plan', FACTORY)
    lock_transaction(db, 'material-purchase', FACTORY)
    row = record(db, identity) if identity else None
    current = view(db, row) if row else None
    # Deliberately no successful release branch, even for administrators.
    if action == 'release':
        trial.bom.require(False, '资料未齐，正式下发未开放；未生成供应商订单、有效在途或仓库收货来源', 409)
    digest = hashlib.sha256(trial.bom.dump([user.id, identity, action, body.model_dump(mode='json')]).encode()).hexdigest()
    receipt = db.scalar(select(MaterialPurchaseEvent).where(MaterialPurchaseEvent.factory_id == FACTORY, MaterialPurchaseEvent.operation_id == body.operation_id))
    if receipt:
        trial.bom.require(receipt.request_hash == digest, '请求编号已用于其他内容或账号', 409)
        db.rollback()
        return json.loads(receipt.result_json)
    trial.bom.require(body.expected_version == (row.version if row else 0), '采购准备单已更新，请刷新后核对', 409)
    saved = deepcopy(current) if current else {}
    actor = dict(id=user.id, name=user.display_name, at=business_now().isoformat())
    if action == 'replacement':
        from app.services.material_purchase_comparison import latest_comparison
        trial.bom.require(current and current['status'] == CANCELLED, '请先由负责人批准取消原准备单，再建立关联草稿', 409)
        comparison = latest_comparison(db, current)
        trial.bom.require(comparison['status'] == 'COMPARED' and comparison['target_version'] == body.demand_version
                          and body.demand_version > current['data']['demand_version'],
                          '新需求依据已变化或尚未自审，请重新核对同一订单的需求版本', 409)
        latest_events = select(MaterialPurchaseEvent).join(MaterialPurchase, and_(
            MaterialPurchaseEvent.entity_id == MaterialPurchase.id, MaterialPurchaseEvent.factory_id == MaterialPurchase.factory_id,
            MaterialPurchaseEvent.version == MaterialPurchase.version)).where(MaterialPurchase.factory_id == FACTORY)
        trial.bom.require(not any(json.loads(e.result_json).get('replacement_of', {}).get('id') == identity
                                  for e in db.scalars(latest_events)), '原准备单已有关联新草稿，请从列表打开已有单据', 409)
        basis = source(db, current['data']['demand_id'], body.demand_version)
        saved = dict(status=DRAFT, data=PurchaseData(demand_id=basis['id'], demand_version=basis['version']).model_dump(mode='json'),
            source=basis, created_by=actor, replacement_of=dict(id=identity, version=current['version'],
                demand_version=current['data']['demand_version']))
        row = None  # create a new identity; never advance or rewrite the cancelled original
    elif action == 'save':
        trial.bom.require(current is None or current['status'] == DRAFT, '仅草稿可以直接编辑', 409)
        data = body.data.model_dump(mode='json')
        if current:
            trial.bom.require((data['demand_id'], data['demand_version']) == (current['data']['demand_id'], current['data']['demand_version']), '现有采购单不能更换需求依据，请重新制单', 422)
        basis = source(db, data['demand_id'], data['demand_version'])
        validate_lines(data, basis)
        saved.update(status=DRAFT, data=data, source=basis)
        if not current: saved['created_by'] = actor
    elif action == 'submit':
        trial.bom.require(current and current['status'] == DRAFT, '仅草稿可以提交审核', 409)
        basis = source(db, current['data']['demand_id'], current['data']['demand_version'])
        validate_lines(current['data'], basis, complete=True)
        saved.update(status=PENDING, submitted_by=actor)
    elif action in ('approve', 'reject'):
        trial.bom.require(current and current['status'] == PENDING, '当前不在待审核状态', 409)
        if action == 'approve':
            source(db, current['data']['demand_id'], current['data']['demand_version'])
            saved.update(status=APPROVED, approved_by=actor)
        else:
            saved.update(status=DRAFT)
    elif action == 'change':
        allowed_states = {DRAFT, PENDING, APPROVED} if body.kind == 'CANCEL' else {APPROVED}
        trial.bom.require(current and current['status'] in allowed_states,
                          '草稿、待审核及内部已审单可申请取消；改量仅限内部已审未下发单', 409)
        old = {line['source_key']: line['quantity'] for line in current['data']['lines']}
        quantities = body.quantities
        trial.bom.require((body.kind == 'CANCEL' and not quantities) or (body.kind == 'QUANTITY' and quantities
            and set(quantities) <= set(old) and any(old[k] != value for k, value in quantities.items())), '请选择实际改量行；取消申请不能携带新数量', 422)
        if body.kind == 'QUANTITY': source(db, current['data']['demand_id'], current['data']['demand_version'])
        saved.update(status=CHANGE, pending_change=dict(kind=body.kind, quantities=quantities, before=old,
            before_status=current['status'], requested_by=actor, reason=body.reason))
    elif action in ('approve-change', 'reject-change'):
        trial.bom.require(current and current['status'] == CHANGE, '当前没有待审核的变更申请', 409)
        change = saved.pop('pending_change')
        # Older requests could only originate from APPROVED; retain their contract.
        previous_status = change.get('before_status', APPROVED)
        trial.bom.require(previous_status in {DRAFT, PENDING, APPROVED}
            and (change['kind'] == 'CANCEL' or previous_status == APPROVED), '变更申请的原状态依据异常，请核对历史', 409)
        saved['last_change'] = dict(change, decision=action, decided_by=actor, decision_reason=body.reason)
        saved['status'] = previous_status
        if action == 'approve-change':
            if change['kind'] == 'CANCEL': saved['status'] = CANCELLED
            else:
                source(db, current['data']['demand_id'], current['data']['demand_version'])
                for line in saved['data']['lines']:
                    if line['source_key'] in change['quantities']: line['quantity'] = change['quantities'][line['source_key']]
    else:
        trial.bom.require(False, '未知采购动作', 422)
    if row is None:
        row = MaterialPurchase(id=uuid4().hex, factory_id=FACTORY, version=0); db.add(row)
    row.version += 1
    saved.update(id=row.id, version=row.version, occurred_at=actor['at'], reason=body.reason, last_action=dict(action=action, **actor),
        release_gate=dict(can_release=False, blockers=BLOCKERS), released_at=None, effective_on_order=False)
    db.add(MaterialPurchaseEvent(id=uuid4().hex, factory_id=FACTORY, operation_id=body.operation_id, request_hash=digest,
        entity_id=row.id, version=row.version, result_json=trial.bom.dump(saved), actor_id=user.id, occurred_at=actor['at'], reason=body.reason))
    db.commit()
    return saved
