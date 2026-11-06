"""Exact gross-demand trials. Unknown supply is never treated as zero."""
import hashlib
import json
from decimal import Decimal, localcontext, ROUND_HALF_UP
from fractions import Fraction
from uuid import uuid4
from sqlalchemy import and_, inspect, select, text
from app.core.time import business_now
from app.models.material_plan import MaterialPlan, MaterialPlanEvent
from app.services import engineering_bom as bom
from app.services import material_plan_orders as orders
from app.services.auth import authorization_decision
from app.services.transaction_lock import lock_transaction

FACTORY = bom.FACTORY
TABLES = (MaterialPlan.__table__, MaterialPlanEvent.__table__)


def allowed(user, action):
    department = 'pmc-warehouse' if action in ('dates_read', 'dates_write') else 'sales-business'
    return authorization_decision(user, 'material_plan:' + action, FACTORY, department)[0]


def authorize(user, factory, action='read'):
    bom.require(factory == FACTORY, '请选择华康 C', 422)
    read = 'dates_read' if action in ('dates_read', 'dates_write') else 'read'
    bom.require(allowed(user, read) and allowed(user, action), '没有需求流程相应权限', 403)


def ready(db):
    if not bom.ready(db):
        return False
    inspector = inspect(db.get_bind()); names = set(inspector.get_table_names())
    if not all(t.name in names and set(t.columns.keys()) <= {c['name'] for c in inspector.get_columns(t.name)} for t in TABLES):
        return False
    unique = any(set(c['column_names']) == {'factory_id', 'operation_id'} for c in inspector.get_unique_constraints('material_plan_events'))
    scoped = all(any('huakang-c' in c['sqltext'] and 'factory_id' in c['sqltext'] for c in inspector.get_check_constraints(t.name)) for t in TABLES)
    if db.get_bind().dialect.name == 'sqlite':
        triggers = set(db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='material_plan_events'")))
        protected = {'material_plan_no_update', 'material_plan_no_delete'} <= triggers
    else:
        protected = bool(db.scalar(text("SELECT COUNT(*) FROM pg_trigger WHERE tgname='material_plan_immutable' AND tgenabled <> 'D' AND tgrelid='material_plan_events'::regclass")))
    return unique and scoped and protected


def effective_bom(db, identity, version):
    record = bom.document(db, identity)
    bom.require(record.effective_version == version, 'BOM 有效版本已变化，请刷新并明确选择当前依据')
    frozen = bom.view(db, record, version)
    bom.require(frozen and frozen['status'] == 'APPROVED', '仅可选择当前已审核的 BOM', 422)
    return {k: frozen[k] for k in ('id', 'version', 'data', 'materials')}


def amount(value):
    """The decimal is presentation only; fractions are the exact business basis."""
    bom.require(0 <= value <= 10 ** 24, '试算用量超出支持范围，请核对 BOM', 422)
    with localcontext() as ctx:
        ctx.prec = 80
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        display = format(decimal.quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_UP), 'f').rstrip('0').rstrip('.') or '0'
        if value and Decimal(display) == 0:
            display = format(decimal, '.12E')
    return dict(value=display, numerator=str(value.numerator), denominator=str(value.denominator), approximate=Fraction(display) != value)


def calculate(frozen, inputs):
    nodes = frozen['data']['nodes']; by_id = bom.validate_tree(frozen['data'])
    overrides = inputs['loss_exemptions']
    attributes = inputs.get('material_attributes', {})
    bom.require(set(overrides) <= {n['key'] for n in nodes if n['parent']}, '免损设置包含不属于本 BOM 的用料行', 422)
    bom.require(set(attributes) <= {n['key'] for n in nodes if n['parent']}, '物料属性设置包含不属于本 BOM 的用料行', 422)
    quantity, rate = Fraction(str(inputs['quantity'])), Fraction(str(inputs['loss_percent'])) / 100
    memo, lines, groups = {}, [], {}
    def per_unit(n):
        if n['key'] not in memo:
            memo[n['key']] = (per_unit(by_id[n['parent']]) if n['parent'] else Fraction(1)) * Fraction(n['numerator']) / Fraction(n['denominator'])
        return memo[n['key']]
    for n in nodes:
        if not n['parent']:
            continue
        material = frozen['materials'].get(f"{n['material_id']}:{n['material_version']}")
        bom.require(material is not None, 'BOM 物料快照不完整，请工程核对', 409)
        engineering_attribute = material['data']['engineering']['attribute']
        attribute = attributes.get(n['key'], engineering_attribute)
        bom.require(attribute == engineering_attribute or {attribute, engineering_attribute} <= {'自制', '委外'},
                    '业务可调整自制／委外；外购及客供属性沿用工程依据', 422)
        base = quantity * per_unit(n)
        exempt = overrides.get(n['key'], n['exempt_loss'])
        bom.validate_material_loss(attribute, exempt, n['key'])
        loss = Fraction(0) if exempt else base * rate
        gross = base + loss
        metadata = dict(material_id=material['id'], material_version=material['version'], code=material['code'],
            name=material['name'], unit=n['unit'], attribute=attribute)
        lines.append(metadata | dict(key=n['key'], parent=n['parent'], process=n['process'], exempt_loss=exempt,
            engineering_exempt_loss=n['exempt_loss'], engineering_attribute=engineering_attribute,
            base=amount(base), loss=amount(loss), gross=amount(gross)))
        key = (material['id'], material['version'], n['unit'], attribute)
        group = groups.setdefault(key, dict(metadata=metadata, base=Fraction(0), loss=Fraction(0), gross=Fraction(0), processes=set(), keys=[]))
        for field, value in (('base', base), ('loss', loss), ('gross', gross)):
            group[field] += value
        group['processes'].add(n['process']); group['keys'].append(n['key'])
    return dict(lines=lines, totals=[g['metadata'] | dict(base=amount(g['base']), loss=amount(g['loss']), gross=amount(g['gross']),
            processes=sorted(g['processes']), keys=g['keys']) for g in groups.values()],
        finished_quantity=amount(quantity), finished_unit=next(n['unit'] for n in nodes if not n['parent']),
        supply_status='PENDING_VERIFICATION', net_purchase_quantity=None,
        pending=['库存基线及占用', '有效在途及分配', '采购填写工序物料期', '正式订单绑定'], algorithm='gross-fraction-v2-attribute')


def record(db, user, identity):
    row = db.get(MaterialPlan, identity)
    bom.require(row is not None and row.factory_id == FACTORY and row.owner_id == user.id, '找不到本人的试算草稿', 404)
    return row


def history(db, user, identity):
    record(db, user, identity)
    items = [json.loads(e.result_json) for e in db.scalars(select(MaterialPlanEvent).where(
        MaterialPlanEvent.factory_id == FACTORY, MaterialPlanEvent.entity_id == identity).order_by(MaterialPlanEvent.version.desc()))]
    for item in items:
        orders.require_snapshot_access(user, item)
    return items


def workspace(db, user):
    effective = []
    for row in db.scalars(select(bom.EngineeringBom).where(bom.EngineeringBom.factory_id == FACTORY, bom.EngineeringBom.effective_version.is_not(None))):
        effective.append(effective_bom(db, row.id, row.effective_version))
    latest = select(MaterialPlanEvent).join(MaterialPlan, and_(MaterialPlanEvent.entity_id == MaterialPlan.id,
        MaterialPlanEvent.factory_id == MaterialPlan.factory_id, MaterialPlanEvent.version == MaterialPlan.version)).where(
        MaterialPlan.factory_id == FACTORY, MaterialPlan.owner_id == user.id)
    drafts = [json.loads(e.result_json) for e in db.scalars(latest)]
    if not orders.allowed(user):
        drafts = [d for d in drafts if not d['inputs'].get('order')]
    drafts.sort(key=lambda r: r['occurred_at'], reverse=True)
    return dict(boms=effective, drafts=drafts)


def calculation(db, user, body):
    frozen = effective_bom(db, body.data.bom_id, body.data.bom_version)
    order = orders.resolve(db, user, body.data.order, frozen, body.data.quantity)
    result = calculate(frozen, body.data.model_dump(mode='json'))
    result['order_basis'] = order
    if order:
        result['pending'].remove('正式订单绑定')
    result['release_gate'] = dict(can_release=False, blockers=([] if order else ['ORDER_BINDING']) +
        ['STOCK_VERIFICATION', 'ON_ORDER_ALLOCATION', 'PROCESS_DATES', 'RELEASE_WORKFLOW'])
    return frozen, result


def preview(db, user, body):
    lock_transaction(db, 'engineering-bom', FACTORY)
    lock_transaction(db, 'material-plan', FACTORY)
    return calculation(db, user, body)[1]


def save(db, user, body, identity=''):
    # This ordering serializes approval and trial save, including across PG workers.
    lock_transaction(db, 'engineering-bom', FACTORY)
    lock_transaction(db, 'material-plan', FACTORY)
    digest = hashlib.sha256(bom.dump([user.id, identity, body.model_dump(mode='json')]).encode()).hexdigest()
    previous = db.scalar(select(MaterialPlanEvent).where(MaterialPlanEvent.factory_id == FACTORY, MaterialPlanEvent.operation_id == body.operation_id))
    if previous:
        legacy = body.model_dump(mode='json')
        candidates = {digest}
        if body.data.order is None:
            legacy['data'].pop('order', None)
            candidates.add(hashlib.sha256(bom.dump([user.id, identity, legacy]).encode()).hexdigest())
            if not body.data.material_attributes:
                legacy['data'].pop('material_attributes', None)
                candidates.add(hashlib.sha256(bom.dump([user.id, identity, legacy]).encode()).hexdigest())
        bom.require(previous.request_hash in candidates,
                    '请求编号已用于其他内容或账号')
        saved = json.loads(previous.result_json)
        orders.require_snapshot_access(user, saved)
        db.rollback()
        return saved
    row = record(db, user, identity) if identity else None
    bom.require(body.expected_version == (row.version if row else 0), '草稿已变化，请刷新并核对修改')
    if row:
        latest = db.scalar(select(MaterialPlanEvent).where(MaterialPlanEvent.entity_id == row.id, MaterialPlanEvent.version == row.version))
        orders.require_snapshot_access(user, json.loads(latest.result_json))
        bom.require(json.loads(latest.result_json)['status'] == 'DRAFT_DATA_PENDING', '已提交需求须先退回草稿再编辑', 409)
    frozen, result = calculation(db, user, body)
    inputs = body.data.model_dump(mode='json')
    inputs['loss_exemptions'] = {line['key']: line['exempt_loss'] for line in result['lines']}
    inputs['material_attributes'] = {line['key']: line['attribute'] for line in result['lines']}
    if not row:
        row = MaterialPlan(id=uuid4().hex, factory_id=FACTORY, owner_id=user.id, version=0)
        db.add(row)
    row.version += 1
    snapshot = dict(id=row.id, version=row.version, owner_id=user.id, owner_name=user.display_name,
        status='DRAFT_DATA_PENDING', inputs=inputs, bom=frozen, result=result,
        occurred_at=business_now().isoformat(), reason=body.reason)
    db.add(MaterialPlanEvent(id=uuid4().hex, factory_id=FACTORY, operation_id=body.operation_id, request_hash=digest,
        entity_id=row.id, version=row.version, result_json=bom.dump(snapshot), actor_id=user.id,
        occurred_at=snapshot['occurred_at'], reason=body.reason))
    db.commit()
    return snapshot
