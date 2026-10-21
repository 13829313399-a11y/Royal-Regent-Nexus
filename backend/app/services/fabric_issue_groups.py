"""Order kit recommendations and atomic multi-requisition issues on the existing ledger."""
import json
from collections import defaultdict
from decimal import Decimal
from uuid import uuid4, uuid5
from fastapi import HTTPException
from sqlalchemy import select
from app.core.time import business_now
from app.models.warehouse_operations import WarehouseOperation
from app.schemas.warehouse_operations import WarehouseDocumentRequest
from app.services import warehouse_operations as wh
from app.services.fabric_receiving import quantity

GROUP_KIND = 'FABRIC_ISSUE_GROUP'
SCALE = Decimal(1000000)
IDENTITY = ('item_code', 'item_name', 'unit', 'process_state', 'material_category')


def identity(data):
    return tuple(data.get(key, '') for key in IDENTITY)


def lot_identity(batch):
    # Supplier lot labels are not globally unique; unknown labels stay separate.
    if not batch.get('lot'):
        return ('', batch['id'])
    supplier = (batch.get('procurement_receipt') or {}).get('source_facts', {}).get('supplier') or batch.get('counterparty')
    return (batch['lot'], supplier or batch['id'])


def groups(entries):
    result = {}
    for entry in entries.values():
        if entry['kind'] == GROUP_KIND:
            result[entry['data']['group_id']] = {**entry['data'], 'actor_name': entry['actor_name'], 'occurred_at': entry['occurred_at']}
    return list(result.values())


def current_group(entries, identifier):
    group = next((g for g in groups(entries) if g['group_id'] == identifier), None)
    if group is None:
        raise HTTPException(404, '配套组不存在于当前布料仓')
    return group


def revision(entries):
    return max((e['sequence'] for e in entries.values()), default=0)


def ensure_revision(entries, expected):
    if revision(entries) != expected:
        raise HTTPException(409, '库存、领料单或配套关系已变化，请重新生成方案')


def save(db, actor, payload):
    wh.ensure_schema(db)
    body = payload.model_dump(mode='json')
    signature = wh.digest(['fabric-issue-group', actor.id, body])
    try:
        state = wh.procurement.lock_factory(db)
        old = db.scalar(select(WarehouseOperation).where(WarehouseOperation.factory_id == wh.FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.request_id == str(payload.request_id)))
        if old:
            if old.kind != GROUP_KIND or old.request_hash != signature:
                raise HTTPException(409, '请求编号已用于其他内容或操作者')
            result = json.loads(old.payload_json)
            db.rollback()
            return result
        _, entries = wh.projection(db, 'fabric')
        ensure_revision(entries, payload.expected_revision)
        if len(set(payload.request_ids)) != len(payload.request_ids):
            raise HTTPException(422, '领料单不能重复关联')
        existing = current_group(entries, payload.group_id) if payload.group_id else None
        if existing and (existing['order_no'] != payload.order_no or existing['name'] != payload.name
                         or not set(existing['request_ids']).issubset(payload.request_ids)):
            raise HTTPException(422, '已有配套组保留原订单、名称及关联单据，可追加领料单')
        ownership = {rid: g['group_id'] for g in groups(entries) for rid in g['request_ids']}
        for rid in payload.request_ids:
            request = wh.original_for(entries, rid, {'REQUEST'})
            if ownership.get(rid) and ownership[rid] != payload.group_id:
                raise HTTPException(409, '领料单已属于其他配套组，请核对原关联')
            data = request['data']
            order = (data.get('cutting_request') or {}).get('order_no') or data.get('production_no', '')
            if order and order != payload.order_no:
                raise HTTPException(422, '领料单已有订单 / 放产单编号与配套订单不一致，不能跨订单关联')
        body['group_id'] = payload.group_id or 'FG-' + uuid4().hex[:20]
        body['request_ids'] = sorted(payload.request_ids)
        now = business_now()
        db.add(WarehouseOperation(id='FG-E-' + uuid4().hex[:20], factory_id=wh.FACTORY, warehouse='fabric',
            sequence=revision(entries)+1, request_id=str(payload.request_id), request_hash=signature,
            kind=GROUP_KIND, business_date=now.date().isoformat(), payload_json=wh.dump(body),
            actor_id=actor.id, actor_name=actor.display_name, occurred_at=now.isoformat()))
        state.revision += 1
        db.commit()
        return body
    except Exception:
        db.rollback()
        raise


def proportional(total, needs):
    """Largest remainder in millionths: exact conservation and stable tie-breaking."""
    units = int(total * SCALE)
    weights = [int(value * SCALE) for value in needs]
    denominator = sum(weights)
    if not denominator:
        return [Decimal(0) for _ in needs]
    quotients = [divmod(units * value, denominator) for value in weights]
    result = [value[0] for value in quotients]
    for index in sorted(range(len(needs)), key=lambda i: (-quotients[i][1], i))[:units-sum(result)]:
        result[index] += 1
    return [Decimal(value) / SCALE for value in result]


def recommend(stock, entries, group, date, eligible_ids):
    if date > business_now().date().isoformat():
        raise HTTPException(422, '实际发料日期不能晚于今天')
    requests = []
    for rid in group['request_ids']:
        request = wh.original_for(entries, rid, {'REQUEST'})
        if request.get('closed'):
            continue
        left = wh.decimal(request['data']['quantity']) - wh.decimal(request['issued_quantity'])
        if left <= 0:
            continue
        if date < request['business_date']:
            raise HTTPException(422, '发料日期不能早于组内领料申请日期')
        requests.append(request)
    requests.sort(key=lambda r: (r['sequence'], r['id']))
    lots_used = defaultdict(lambda: defaultdict(Decimal))
    for entry in entries.values():
        if entry['kind'] == 'ISSUE' and not entry.get('reversed') and entry['data'].get('original_id') in group['request_ids']:
            batch = entry['batch_snapshot']
            # Unknown lot labels cannot establish same-dye-lot evidence.
            if batch.get('lot'):
                lots_used[identity(batch)][lot_identity(batch)] += wh.decimal(entry['data']['quantity'])
    buckets = defaultdict(list)
    for request in requests:
        buckets[identity(request['data'])].append(request)
    allocations, demands, candidates = [], [], []
    for key, members in buckets.items():
        needs = [wh.decimal(r['data']['quantity']) - wh.decimal(r['issued_quantity']) for r in members]
        original_needs = list(needs)
        batches = [b for b in stock.values() if identity(b) == key and b['id'] in eligible_ids
                   and wh.decimal(b['quantity']) > 0 and b['quality_status'] not in {'HOLD', 'REJECTED'}
                   and date >= b.get('last_business_date', b['received_on'])]
        batches.sort(key=lambda b: (b['received_on'], b.get('occurred_at', ''), b['id']))
        candidates.extend(batches)
        lots = defaultdict(list)
        for batch in batches:
            lots[lot_identity(batch)].append(batch)
        totals = {lot: sum((wh.decimal(b['quantity']) for b in rows), Decimal(0)) for lot, rows in lots.items()}
        total_need = sum(needs, Decimal(0))
        def lot_rank(lot):
            used = lots_used[key].get(lot, Decimal(0))
            first = lots[lot][0]
            return (0 if used else 1, -used, 0 if totals[lot] >= total_need else 1,
                    0 if totals[lot] >= total_need else -totals[lot], first['received_on'], first.get('occurred_at', ''), lot)
        for lot in sorted(lots, key=lot_rank):
            amount = min(totals[lot], sum(needs, Decimal(0)))
            if amount <= 0:
                break
            shares = proportional(amount, needs)
            batch_left = [wh.decimal(b['quantity']) for b in lots[lot]]
            for i, share in enumerate(shares):
                needs[i] -= share
                for j, batch in enumerate(lots[lot]):
                    take = min(share, batch_left[j])
                    if take > 0:
                        allocations.append({'original_id': members[i]['id'], 'batch_id': batch['id'], 'quantity': wh.text(take)})
                        share -= take
                        batch_left[j] -= take
                    if share == 0:
                        break
        for i, request in enumerate(members):
            demands.append({'request': request, 'remaining': wh.text(original_needs[i]),
                            'recommended': wh.text(original_needs[i]-needs[i]), 'shortage': wh.text(needs[i])})
    if len(allocations) > 500:
        raise HTTPException(422, '本次推荐超过 500 条批次明细，请先处理部分领料需求')
    return {'items': allocations, 'demands': demands, 'candidates': candidates}


def build_plan(db, actor, payload, entries=None, stock=None):
    if entries is None:
        stock, entries = wh.projection(db, 'fabric')
    group = current_group(entries, payload.group_id)
    from app.services import fabric_master
    inactive = fabric_master.records(db)
    locations = {r['id'] for r in wh.locations.catalog(db, 'fabric')}
    eligible = {b['id'] for b in stock.values() if b.get('location_id') in locations and not any(
        r.status == 'INACTIVE' and ((r.kind == 'MATERIAL' and r.code == b['item_code']) or
        (r.kind == 'UNIT' and b['unit'] in (r.code, r.name))) for r in inactive)}
    result = recommend(stock, entries, group, payload.business_date.isoformat(), eligible)
    token = wh.digest(['fabric-kit-v1', actor.id, payload.group_id, payload.business_date.isoformat(), revision(entries), result])
    return {**result, 'group': group, 'revision': revision(entries), 'token': token}


def preview(db, actor, payload):
    wh.ensure_schema(db)
    try:
        wh.procurement.lock_factory(db)
        return build_plan(db, actor, payload)
    finally:
        db.rollback()


def post(db, actor, payload):
    wh.ensure_schema(db)
    signature = wh.digest(['fabric-kit-issue', actor.id, payload.model_dump(mode='json')])
    ids = [str(payload.request_id)] + [str(uuid5(payload.request_id, f'kit-{i}')) for i in range(1, len(payload.items))]
    try:
        # Preserve the cutting -> source orders -> warehouse lock order for every member.
        from app.services import cutting_materials
        linked = [cutting_materials.linked(db, rid) for rid in {item.original_id for item in payload.items}]
        source_ids = sorted({r['data']['cutting_request']['line_id'] for r in linked if r})
        if source_ids:
            cutting_materials.lock_transaction(db, 'cutting-master', wh.FACTORY)
            for source_id in source_ids:
                db.scalar(select(cutting_materials.orders.OrderLedgerLine).where(
                    cutting_materials.orders.OrderLedgerLine.id == source_id,
                    cutting_materials.orders.OrderLedgerLine.factory_id == wh.FACTORY)
                    .with_for_update().execution_options(populate_existing=True))
        state = wh.procurement.lock_factory(db)
        existing = list(db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == wh.FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.request_id.in_(ids))))
        if existing:
            if len(existing) != len(ids) or any(json.loads(r.payload_json).get('bulk_hash') != signature for r in existing):
                raise HTTPException(409, '请求编号已用于其他内容或操作者，请核对原配套发料')
            result = {'documents': [wh.entry_data(r) for r in sorted(existing, key=lambda r: r.sequence)]}
            db.rollback()
            return result
        stock, entries = wh.projection(db, 'fabric')
        ensure_revision(entries, payload.expected_revision)
        plan = build_plan(db, actor, payload, entries, stock)
        if plan['token'] != payload.token:
            raise HTTPException(409, '方案依据已变化，请重新生成并核对')
        if not payload.confirmed:
            raise HTTPException(422, '请核对逐单缸号和实际数量后确认发料')
        pairs = [(item.original_id, item.batch_id) for item in payload.items]
        if len(set(pairs)) != len(pairs):
            raise HTTPException(422, '同一领料单的同批次请合并填写')
        requests = {d['request']['id']: d['request'] for d in plan['demands']}
        candidates = {b['id']: b for b in plan['candidates']}
        result = []
        for index, item in enumerate(payload.items):
            request, batch = requests.get(item.original_id), candidates.get(item.batch_id)
            if not request or not batch or identity(request['data']) != identity(batch):
                raise HTTPException(422, '领料单或批次不属于本组可发的相同物料和单位')
            quantity(item.quantity, '实际发料数量')
            data = request['data']
            child = WarehouseDocumentRequest(factory_id=wh.FACTORY, request_id=ids[index],
                expected_revision=payload.expected_revision+index, kind='ISSUE', business_date=payload.business_date,
                original_id=item.original_id, batch_id=item.batch_id, quantity=item.quantity,
                counterparty=data['counterparty'], production_no=data.get('production_no') or plan['group']['order_no'],
                purpose=data.get('purpose', ''), reason=payload.reason)
            result.append(wh.post(db, actor, 'fabric', child, _state=state, _commit=False, _metadata={
                'bulk_request_id': str(payload.request_id), 'bulk_hash': signature,
                'issue_group': {k: plan['group'][k] for k in ('group_id', 'order_no', 'name', 'request_ids')},
                'issue_plan_token': payload.token}))
        db.commit()
        return {'documents': result}
    except Exception:
        db.rollback()
        raise


def recover(db, actor, payload):
    """Resolve a lost response or permanently fence an uncommitted root UUID."""
    wh.ensure_schema(db)
    body = payload.body.model_dump(mode='json')
    domain = 'fabric-issue-group' if payload.kind == 'group' else 'fabric-kit-issue'
    signature = wh.digest([domain, actor.id, body])
    try:
        state = wh.procurement.lock_factory(db)
        old = db.scalar(select(WarehouseOperation).where(WarehouseOperation.factory_id == wh.FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.request_id == str(payload.body.request_id)))
        if old:
            recorded = json.loads(old.payload_json)
            actual = recorded.get('bulk_hash') if payload.kind == 'issue' and old.kind == 'ISSUE' else old.request_hash
            if actual != signature:
                raise HTTPException(409, '原请求属于其他内容或操作者，不能核对或停止')
            result = {'state': 'abandoned' if old.kind == 'COMMAND_ABANDONED' else 'committed'}
            db.rollback()
            return result
        _, entries = wh.projection(db, 'fabric')
        now = business_now()
        db.add(WarehouseOperation(id='FG-F-' + uuid4().hex[:20], factory_id=wh.FACTORY, warehouse='fabric',
            sequence=revision(entries)+1, request_id=str(payload.body.request_id), request_hash=signature,
            kind='COMMAND_ABANDONED', business_date=now.date().isoformat(), payload_json=wh.dump({'domain': domain}),
            actor_id=actor.id, actor_name=actor.display_name, occurred_at=now.isoformat()))
        state.revision += 1
        db.commit()
        return {'state': 'abandoned'}
    except Exception:
        db.rollback()
        raise
