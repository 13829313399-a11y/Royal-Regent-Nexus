"""Versioned date coordination and owner self-review, never procurement release."""
from copy import deepcopy
import hashlib
import json
from uuid import uuid4
from sqlalchemy import and_, select
from app.core.time import business_now
from app.models.material_plan import MaterialPlan, MaterialPlanEvent
from app.schemas.material_plan import TrialRequest
from app.services import material_plan as trial
from app.services.transaction_lock import lock_transaction

DRAFT = 'DRAFT_DATA_PENDING'
DATES = 'AWAITING_PROCESS_DATES'
REVIEW = 'AWAITING_SELF_REVIEW'
REVIEWED = 'SELF_REVIEWED_DATA_PENDING'
SHARED = {DATES, REVIEW, REVIEWED}


def latest(db, row):
    event = db.scalar(select(MaterialPlanEvent).where(MaterialPlanEvent.factory_id == trial.FACTORY,
        MaterialPlanEvent.entity_id == row.id, MaterialPlanEvent.version == row.version))
    trial.bom.require(event is not None, '需求版本依据缺失', 409)
    return json.loads(event.result_json)


def processes(saved):
    return sorted({line['process'] for line in saved['result']['lines']})


def projection(saved):
    # Procurement gets only the shared planning facts, never customer/order data,
    # arbitrary Sales reference text, private drafts or the full engineering BOM.
    return dict(id=saved['id'], version=saved['version'], status=saved['status'], owner_name=saved['owner_name'],
        item_no=saved['bom']['data']['item_no'], quantity=saved['inputs']['quantity'], unit=saved['result']['finished_unit'],
        lines=saved['result']['lines'], processes=processes(saved), process_dates=saved.get('process_dates', {}),
        date_actor=saved.get('date_actor'), occurred_at=saved['occurred_at'])


def queue(db):
    statement = select(MaterialPlanEvent).join(MaterialPlan, and_(MaterialPlanEvent.entity_id == MaterialPlan.id,
        MaterialPlanEvent.factory_id == MaterialPlan.factory_id, MaterialPlanEvent.version == MaterialPlan.version)).where(
        MaterialPlan.factory_id == trial.FACTORY)
    saved = [json.loads(event.result_json) for event in db.scalars(statement)]
    return dict(items=[projection(s) for s in sorted(saved, key=lambda s: s['occurred_at'], reverse=True) if s['status'] in SHARED])


def recheck(db, user, saved):
    trial.bom.require(saved['inputs'].get('order'), '请先关联客户订单并保存草稿', 422)
    body = TrialRequest(factory_id=trial.FACTORY, operation_id=uuid4().hex, expected_version=saved['version'],
        reason='核对流程依据', data=saved['inputs'])
    trial.calculation(db, user, body)
    trial.bom.require(saved['result']['lines'] and all(processes(saved)), '需求缺少有效工序用料，不能提交或自审', 422)


def apply(db, user, identity, action, body):
    procurement = action == 'dates'
    permission = 'dates_write' if procurement else 'self_review' if action == 'self-review' else 'submit'
    trial.authorize(user, body.factory_id, permission)
    lock_transaction(db, 'engineering-bom', trial.FACTORY)
    lock_transaction(db, 'material-plan', trial.FACTORY)
    row = db.get(MaterialPlan, identity)
    trial.bom.require(row is not None and row.factory_id == trial.FACTORY and (procurement or row.owner_id == user.id), '找不到可操作的需求', 404)
    current = latest(db, row)
    if procurement:
        trial.bom.require(current['status'] in SHARED, '需求已退回业务，不再接受采购操作', 409)
    else:
        trial.orders.require_snapshot_access(user, current)
    digest = hashlib.sha256(trial.bom.dump(['workflow', user.id, identity, action, body.model_dump(mode='json')]).encode()).hexdigest()
    receipt = db.scalar(select(MaterialPlanEvent).where(MaterialPlanEvent.factory_id == trial.FACTORY, MaterialPlanEvent.operation_id == body.operation_id))
    if receipt:
        trial.bom.require(receipt.request_hash == digest, '请求编号已用于其他内容或账号', 409)
        saved = json.loads(receipt.result_json)
        db.rollback()
        return projection(saved) if procurement else saved
    trial.bom.require(row.version == body.expected_version, '需求已更新，请刷新核对后重试', 409)
    saved = deepcopy(current)
    actor = dict(id=user.id, name=user.display_name, at=business_now().isoformat())
    if action == 'submit':
        trial.bom.require(current['status'] == DRAFT, '仅草稿可以提交', 409)
        recheck(db, user, current)
        saved.update(status=DATES, process_dates={}, submitted_by=actor)
        saved.pop('reviewed_by', None); saved.pop('date_actor', None)
    elif action == 'dates':
        trial.bom.require(current['status'] in {DATES, REVIEW}, '业务已自审，请先由业务退回草稿', 409)
        required = set(processes(current))
        trial.bom.require(set(body.dates) <= required, '物料期包含不属于本需求的工序', 422)
        dates = {p: value.isoformat() for p, value in body.dates.items() if value is not None}
        saved.update(process_dates=dates, status=REVIEW if required and set(dates) == required else DATES, date_actor=actor)
    elif action == 'self-review':
        trial.bom.require(current['status'] == REVIEW and set(current.get('process_dates', {})) == set(processes(current)), '请先由采购填齐各工序物料期', 409)
        recheck(db, user, current)
        saved.update(status=REVIEWED, reviewed_by=actor)
    elif action == 'reopen':
        trial.bom.require(current['status'] in SHARED, '当前已经是草稿', 409)
        saved.update(status=DRAFT, process_dates={})
        for key in ('reviewed_by', 'date_actor', 'submitted_by'): saved.pop(key, None)
    else:
        trial.bom.require(False, '未知流程动作', 422)
    complete = saved['status'] in {REVIEW, REVIEWED}
    blockers = ['STOCK_VERIFICATION', 'ON_ORDER_ALLOCATION', 'RELEASE_WORKFLOW']
    if not complete: blockers.append('PROCESS_DATES')
    if saved['status'] != REVIEWED: blockers.append('SELF_REVIEW')
    saved['result']['release_gate'] = dict(can_release=False, blockers=blockers)
    saved['result']['pending'] = [p for p in saved['result']['pending'] if p != '采购填写工序物料期']
    if not complete: saved['result']['pending'].append('采购填写工序物料期')
    row.version += 1
    saved.update(version=row.version, occurred_at=actor['at'], reason=body.reason, last_action=dict(action=action, **actor))
    db.add(MaterialPlanEvent(id=uuid4().hex, factory_id=trial.FACTORY, operation_id=body.operation_id, request_hash=digest,
        entity_id=row.id, version=row.version, result_json=trial.bom.dump(saved), actor_id=user.id, occurred_at=actor['at'], reason=body.reason))
    db.commit()
    return projection(saved) if procurement else saved
