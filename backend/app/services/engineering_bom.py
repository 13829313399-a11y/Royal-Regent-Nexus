"""Engineering-only foundation: no order, procurement or inventory writes."""
import hashlib
import json
from decimal import Decimal, localcontext
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import inspect, select, text
from app.core.time import business_now
from app.models.engineering_bom import EngineeringBom, EngineeringEvent
from app.models.fabric_master import FabricMasterRecord, FabricMasterChange
from app.services.auth import authorization_decision
from app.services import fabric_procurement, fabric_master
from app.services.transaction_lock import lock_transaction

FACTORY = 'huakang-c'
ACTIONS = ('read', 'material_write', 'material_approve', 'bom_write', 'bom_approve', 'import')
TABLES = (EngineeringBom.__table__, EngineeringEvent.__table__)


def require(ok, message, status=409):
    if not ok:
        raise HTTPException(status, message)


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def allowed(user, action):
    return authorization_decision(user, 'engineering_bom:' + action, FACTORY, 'engineering')[0]


def authorize(user, factory, action='read'):
    require(factory == FACTORY, '请选择华康 C', 422)
    require(allowed(user, 'read') and allowed(user, action), '没有工程资料相应操作权限', 403)


def ready(db):
    i = inspect(db.get_bind())
    names = set(i.get_table_names())
    if not all(t.name in names and set(t.columns.keys()) <= {c['name'] for c in i.get_columns(t.name)} for t in TABLES):
        return False
    if db.get_bind().dialect.name == 'sqlite':
        triggers = set(db.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='engineering_bom_events'")))
        protected = {'engineering_events_no_update', 'engineering_events_no_delete'} <= triggers
    else:
        protected = bool(db.scalar(text("SELECT COUNT(*) FROM pg_trigger WHERE tgname='engineering_events_immutable' AND tgenabled <> 'D' AND tgrelid='engineering_bom_events'::regclass")))
    unique = any(set(c['column_names']) == {'factory_id', 'operation_id'} for c in i.get_unique_constraints('engineering_bom_events'))
    scoped = all(any('huakang-c' in c['sqltext'] and 'factory_id' in c['sqltext'] for c in i.get_check_constraints(t.name)) for t in TABLES)
    try:
        fabric_master.ensure_schema(db)
    except HTTPException:
        return False
    return protected and unique and scoped


def ensure(db):
    require(ready(db), '工程基础尚未部署，请管理员备份并执行工程迁移后启用', 503)
    fabric_master.ensure_schema(db)


def command(db, user, body, action, entity, apply):
    ensure(db)
    lock_transaction(db, 'engineering-bom', FACTORY)
    # Consistent with all old master mutations; no reverse cutting lock is taken.
    state = fabric_procurement.lock_factory(db)
    request_hash = hashlib.sha256(dump([user.id, action, entity, body.model_dump(mode='json')]).encode()).hexdigest()
    old = db.scalar(select(EngineeringEvent).where(EngineeringEvent.factory_id == FACTORY,
                                                   EngineeringEvent.operation_id == body.operation_id))
    if old:
        require(old.request_hash == request_hash, '请求编号已用于其他操作或内容')
        db.rollback()
        return json.loads(old.result_json)
    result = apply()
    db.add(EngineeringEvent(id=uuid4().hex, factory_id=FACTORY, operation_id=body.operation_id,
        request_hash=request_hash, entity_id=result['id'], action=action, version=result['version'],
        result_json=dump(result), actor_id=user.id, occurred_at=business_now().isoformat(), reason=body.reason))
    state.revision += 1
    db.commit()
    return result


def materials(db):
    return [material_view(r) for r in db.scalars(select(FabricMasterRecord).where(
        FabricMasterRecord.factory_id == FACTORY, FabricMasterRecord.kind == 'MATERIAL').order_by(FabricMasterRecord.code))
        if r.code.startswith(('01-', '02-', '03-', '04-'))]


def material_view(r):
    return dict(id=r.id, code=r.code, name=r.name, version=r.revision, status=r.status, data=json.loads(r.data_json))


def material(db, identity):
    r = db.get(FabricMasterRecord, identity)
    require(r is not None and r.factory_id == FACTORY and r.kind == 'MATERIAL', '物料不存在', 404)
    return r


def save_material(db, user, body):
    def apply():
        r = material(db, body.id) if body.id else None
        require(body.expected_version == (r.revision if r else 0), '物料版本已变化，请刷新后核对')
        code = body.code.strip()
        if r:
            require(code == r.code, '物料编码不能修改', 422)
        elif not code:
            prefix = body.group + '-'
            suffixes = [m['code'][len(prefix):] for m in materials(db) if m['code'].startswith(prefix)]
            number = max([int(s) for s in suffixes if s.isdigit()] or [0]) + 1
            code = f'{prefix}{number:05d}'
        require(code.startswith(body.group + '-'), '物料编码必须属于所选分类', 422)
        duplicate = db.scalar(select(FabricMasterRecord.id).where(FabricMasterRecord.factory_id == FACTORY,
            FabricMasterRecord.kind == 'MATERIAL', FabricMasterRecord.code == code,
            FabricMasterRecord.id != (body.id or '')))
        require(not duplicate, '编码已存在，请选择现有物料')
        before = fabric_master.record_data(r) if r else {}
        data = json.loads(r.data_json) if r else {}
        data.update(unit=body.unit, spec=body.specification, color=body.color, old_code=body.old_code,
            category=body.warehouse_category, engineering=dict(group=body.group, department=body.department,
                attribute=body.attribute, approval='DRAFT'))
        if not r:
            r = FabricMasterRecord(id=uuid4().hex, factory_id=FACTORY, kind='MATERIAL', code=code, revision=0)
            db.add(r)
        r.name, r.status, r.data_json = body.name, 'DRAFT', dump(data)
        r.revision += 1
        r.updated_at = business_now().isoformat()
        db.flush()
        audit_material(db, user, body, r, before)
        return material_view(r)
    return command(db, user, body, 'material_write', body.id, apply)


def audit_material(db, user, body, r, before):
    db.add(FabricMasterChange(id=uuid4().hex, factory_id=FACTORY, record_id=r.id,
        request_id='eng-' + uuid4().hex, request_hash=hashlib.sha256(dump([user.id, body.model_dump(mode='json')]).encode()).hexdigest(),
        before_json=dump(before), after_json=dump(fabric_master.record_data(r)), actor_id=user.id,
        actor_name=user.display_name, occurred_at=r.updated_at))


def material_state(db, user, body, identity, approve):
    def apply():
        r = material(db, identity)
        require(r.revision == body.expected_version, '物料版本已变化')
        data = json.loads(r.data_json)
        require(data.get('engineering'), '请先补齐工程分类和负责部门', 422)
        require(not approve or r.status == 'DRAFT', '仅草稿可审核')
        before = fabric_master.record_data(r)
        data['engineering']['approval'] = 'APPROVED' if approve else 'INACTIVE'
        r.status = 'ACTIVE' if approve else 'INACTIVE'
        r.revision += 1
        r.data_json, r.updated_at = dump(data), business_now().isoformat()
        audit_material(db, user, body, r, before)
        return material_view(r)
    return command(db, user, body, 'material_approve' if approve else 'material_write', identity, apply)


def document(db, identity):
    r = db.get(EngineeringBom, identity)
    require(r is not None and r.factory_id == FACTORY, 'BOM 不存在', 404)
    return r


def versions(db, identity):
    return [json.loads(e.result_json) | {'actor_id': e.actor_id, 'occurred_at': e.occurred_at, 'reason': e.reason}
        for e in db.scalars(select(EngineeringEvent).where(EngineeringEvent.factory_id == FACTORY,
            EngineeringEvent.entity_id == identity).order_by(EngineeringEvent.version.desc()))]


def view(db, r, version=None):
    return next((v for v in versions(db, r.id) if v['version'] == (version or r.version)), None)


def imported_documents(db, digest):
    if not digest:
        return []
    matches = {}
    for event in db.scalars(select(EngineeringEvent).where(EngineeringEvent.factory_id == FACTORY,
            EngineeringEvent.action.in_(('bom_write', 'bom_approve'))).order_by(EngineeringEvent.version)):
        result = json.loads(event.result_json)
        if result['data'].get('source_sha256') == digest:
            matches[event.entity_id] = dict(id=event.entity_id, item_no=result['data']['item_no'], version=event.version)
    return list(matches.values())


def validate_tree(data):
    nodes = data['nodes']
    by_id = {n['key']: n for n in nodes}
    require(len(by_id) == len(nodes), '用料行编号重复', 422)
    roots = [n for n in nodes if not n['parent']]
    require(len(roots) == 1, 'BOM 必须有一个成品根项', 422)
    root = roots[0]
    require(Decimal(root['numerator']) == Decimal(root['denominator']) == 1, '成品根项数量基准必须为 1', 422)
    for n in nodes:
        require(Decimal(n['denominator']) > 0, '用料分母必须大于零', 422)
        require(not n['parent'] or n['parent'] in by_id, '上级用料行不存在', 422)
    for n in nodes:
        seen = {n['key']}
        cursor = n
        while cursor['parent']:
            require(cursor['parent'] not in seen, 'BOM 存在循环关系', 422)
            seen.add(cursor['parent'])
            require(len(seen) <= 32, '层级不能超过 32 层', 422)
            cursor = by_id[cursor['parent']]
    return by_id


def pin_materials(db, data, previous=None, publishing=False):
    snapshots = {}
    old = (previous or {}).get('materials', {})
    for n in data['nodes']:
        if not n['material_id']:
            require(not publishing, '存在未匹配物料，请先建立、审核并选择物料', 422)
            continue
        r = material(db, n['material_id'])
        key = f"{r.id}:{n['material_version']}"
        if key in old:
            snapshots[key] = old[key]
        else:
            require(r.revision == n['material_version'] and r.status == 'ACTIVE', '请选择当前已审核物料版本', 422)
            require(json.loads(r.data_json).get('engineering', {}).get('approval') == 'APPROVED', '物料尚未通过工程审核', 422)
            snapshots[key] = material_view(r)
        require(n['unit'] == snapshots[key]['data'].get('unit'), '用量单位与物料版本不一致；请核对单位', 422)
        if publishing:
            require(r.status == 'ACTIVE', '物料已停用或待审，暂不能审核 BOM', 422)
        require(not publishing or not n['review_required'] or n['review_note'].strip(), '导入差异须填写核对说明', 422)
        require(not publishing or n['process'].strip(), '请确认每一行所属工序', 422)
    return snapshots


def save_bom(db, user, body, identity=''):
    def apply():
        r = document(db, identity) if identity else None
        require(body.expected_version == (r.version if r else 0), 'BOM 已变化，请刷新核对')
        previous = view(db, r) if r else None
        data = body.data.model_dump(mode='json')
        if not r and not body.copy_from:
            require(not imported_documents(db, data['source_sha256']), '此文件已保存为 BOM，请查看原 BOM 或使用复制新货号', 409)
        if r:
            require(data['item_no'] == r.item_no, '不同货号请复制新 BOM', 422)
        if body.copy_from:
            require(not r and body.copy_version, '复制须指定来源版本并新建', 422)
            origin = document(db, body.copy_from)
            previous = view(db, origin, body.copy_version)
            require(previous, '来源版本不存在', 422)
            require(data['item_no'] != origin.item_no, '相同货号请修订原 BOM 或复用有效版本', 422)
        validate_tree(data)
        snapshots = pin_materials(db, data, previous)
        if not r:
            r = EngineeringBom(id=uuid4().hex, factory_id=FACTORY, version=0, item_no=data['item_no'])
            db.add(r)
        r.version += 1
        db.flush()
        return dict(id=r.id, version=r.version, effective_version=r.effective_version,
                    status='DRAFT', data=data, materials=snapshots,
                    copy_from=body.copy_from, copy_version=body.copy_version)
    return command(db, user, body, 'bom_write', identity, apply)


def approve_bom(db, user, body, identity):
    def apply():
        r = document(db, identity)
        require(r.version == body.expected_version, 'BOM 已变化，请刷新核对')
        current = view(db, r)
        require(current['status'] == 'DRAFT', '仅草稿可审核')
        validate_tree(current['data'])
        pin_materials(db, current['data'], current, publishing=True)
        r.version += 1
        r.effective_version = r.version
        return current | dict(version=r.version, effective_version=r.version, status='APPROVED')
    return command(db, user, body, 'bom_approve', identity, apply)


def expansion(data):
    """Theoretical usage only; no inventory, loss, rounding or purchase promise."""
    by_id = validate_tree(data)
    result, memo = [], {}
    def amount(n):
        if n['key'] not in memo:
            memo[n['key']] = (amount(by_id[n['parent']]) if n['parent'] else Decimal(1)) * Decimal(n['numerator']) / Decimal(n['denominator'])
        return memo[n['key']]
    with localcontext() as context:
        context.prec = 48
        for n in data['nodes']:
            result.append(dict(key=n['key'], process=n['process'], quantity=str(amount(n)), unit=n['unit']))
    return result
