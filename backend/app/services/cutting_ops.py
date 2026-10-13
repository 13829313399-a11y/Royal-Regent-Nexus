"""Huakang C master revisions, pinned BOM references and transactional commands."""
import hashlib
import json
from datetime import datetime, UTC
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from app.models.cutting_ops import CuttingMaster, CuttingRevision, CuttingCommand
from app.services import cutting_schemas as s
from app.services.auth import authorization_decision
from app.services.transaction_lock import lock_transaction

FACTORY = 'huakang-c'
TABLES = (CuttingMaster.__table__, CuttingRevision.__table__, CuttingCommand.__table__)


def require(condition, message, status=409):
    if not condition:
        raise HTTPException(status, message)


def allowed(user, action):
    departments = ('engineering',) if action in {'bom_write', 'bom_publish', 'requisition_submit'} else ('production',)
    if action in {'eta_write', 'requisition_reconcile'}:
        departments = ('pmc-warehouse',)
    if action == 'read':
        departments = ('production', 'engineering', 'pmc-warehouse')
    return any(authorization_decision(user, 'cutting_ops:' + action, FACTORY, department)[0] for department in departments)


def authorize(user, factory, action='read'):
    require(factory == FACTORY, '请选择明确的华康C厂区', 422)
    require(allowed(user, 'read') and allowed(user, action), '没有华康C裁床相应部门及操作权限', 403)


def schema_ready(bind):
    inspector = inspect(bind)
    names = set(inspector.get_table_names())
    return all(table.name in names and {c.name for c in table.columns} <=
               {c['name'] for c in inspector.get_columns(table.name)} for table in TABLES)


def master(db, entity_id):
    item = db.get(CuttingMaster, entity_id)
    require(item is not None and item.factory_id == FACTORY, '资料不存在', 404)
    return item


def view(db, item, version=None):
    revision = db.get(CuttingRevision, (item.id, version or item.version))
    require(revision is not None, '资料版本不存在', 404)
    references = {}
    if item.kind == 'bom':
        for row in revision.data['requirements']:
            ref_item = master(db, row['material_id'])
            ref = db.get(CuttingRevision, (ref_item.id, row['material_version']))
            require(ref is not None, '引用的物料版本缺失，需核对资料', 409)
            references[f"{ref_item.id}:{ref.version}"] = dict(code=ref_item.code, name=ref.data['name'])
    return dict(id=item.id, factory_id=item.factory_id, kind=item.kind, code=item.code, material_references=references,
                version=revision.version, status=revision.status, data=revision.data,
                actor_id=revision.actor_id, created_at=revision.created_at, reason=revision.reason)


def validate_references(db, data, *, publishing=False):
    for row in data['requirements']:
        item = master(db, row['material_id'])
        require(item.kind == 'material', 'BOM 只能关联物料资料', 422)
        ref = view(db, item, row['material_version'])
        require(ref['status'] == 'active', 'BOM 引用的物料版本必须有效', 422)
        require(ref['data']['unit'] == row['unit'], '物料用量单位必须与引用版本一致；尚未启用单位换算', 422)
        if publishing:
            require(view(db, item)['status'] == 'active', '物料已停用，不能发布新 BOM')
    if publishing:
        require(any(r['required_for_cutting'] for r in data['requirements']), '请明确至少一种当前裁剪必需物料', 422)
        covered = {code for row in data['requirements'] for code in row['part_codes']}
        require(covered == {p['code'] for p in data['parts']}, '每个部件必须有物料用量依据', 422)


def append(db, user, item, data, status, reason):
    item.version += 1
    db.add(CuttingRevision(master_id=item.id, version=item.version, data=data, status=status,
                           reason=reason, actor_id=user.id, created_at=datetime.now(UTC).isoformat()))
    db.flush()
    return view(db, item)


def save(db, user, body, entity_id=None):
    data = s.DATA_MODELS[body.kind].model_validate(body.data).model_dump(mode='json')
    if entity_id:
        item = master(db, entity_id)
        require(item.kind == body.kind and item.code == body.code, '资料类型及编码不可修改', 422)
        require(item.version == body.expected_version, '资料已更新，请重新读取后再保存')
        require(view(db, item)['status'] != 'inactive', '请先启用资料后再修订')
    else:
        require(body.expected_version == 0, '新资料版本必须为零')
        exists = db.scalar(select(CuttingMaster.id).where(CuttingMaster.factory_id == FACTORY,
                           CuttingMaster.kind == body.kind, CuttingMaster.code == body.code))
        require(not exists, '资料编码已存在，请打开原资料修订')
        item = CuttingMaster(id=str(uuid4()), factory_id=FACTORY, kind=body.kind, code=body.code, version=0)
        db.add(item)
    if body.kind == 'bom':
        validate_references(db, data)
    return append(db, user, item, data, 'draft' if body.kind == 'bom' else 'active', body.reason)


def state(db, user, body, entity_id):
    item = master(db, entity_id)
    require(item.version == body.expected_version, '资料已更新，请重新读取后再操作')
    previous = view(db, item)
    if item.kind == 'bom':
        require(body.status == 'published' and previous['status'] == 'draft', 'BOM 只允许发布草稿；修订请另存新草稿', 422)
        validate_references(db, previous['data'], publishing=True)
    else:
        require(body.status in {'active', 'inactive'} and body.status != previous['status'], '资料状态转换无效', 422)
    return append(db, user, item, previous['data'], body.status, body.reason)


def command_fingerprint(body, action):
    payload = body.model_dump(mode='json')
    # Keep original empty-removal plan commands recoverable across this extension.
    if action.startswith('plan_write:') and not payload.get('removed_task_reasons'):
        payload.pop('removed_task_reasons', None)
    if action.startswith('plan_write:'):
        for task in payload.get('tasks', []):
            if not task.get('resource_change_basis'): task.pop('resource_change_basis', None)
    return payload_fingerprint(payload, action)


def payload_fingerprint(payload, action):
    return hashlib.sha256(json.dumps(dict(action=action, body=payload),
                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def command(db: Session, user, body, action, handler):
    fingerprint = command_fingerprint(body, action)
    try:
        lock_transaction(db, 'cutting-master', FACTORY)
        receipt = db.get(CuttingCommand, body.operation_id)
        if receipt:
            require(receipt.actor_id == user.id and receipt.fingerprint == fingerprint,
                    '操作编号已用于其他请求，请核对原保存结果')
            require(receipt.result.get('operation_status') != 'abandoned', '此操作已核实未执行并停止，请重新提交新操作')
            return receipt.result
        result = handler()
        db.add(CuttingCommand(operation_id=body.operation_id, factory_id=FACTORY, actor_id=user.id,
                              action=action, fingerprint=fingerprint, result=result,
                              created_at=datetime.now(UTC).isoformat()))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
