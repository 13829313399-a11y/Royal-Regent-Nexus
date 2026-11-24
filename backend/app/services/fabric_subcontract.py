"""Fabric subcontract orders. Stock postings and their order vouchers commit together."""
from decimal import Decimal
from uuid import uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import business_now
from app.models.warehouse_operations import WarehouseOperation
from app.schemas.fabric_subcontract import Action, Order, Processor
from app.schemas.warehouse_operations import WarehouseDocumentRequest
from app.services import fabric_master, warehouse_operations as wh
from app.services.transaction_lock import lock_transaction

SOURCE = 'FABRIC_SUBCONTRACT'
PROCESSOR, ORDER, ACTION = 'SUB_PROCESSOR', 'SUB_ORDER', 'SUB_ACTION'
ENGINEERING = {'电绣', '丝印'}
ZERO = Decimal(0)


def require(condition, detail, status=422):
    if not condition:
        raise HTTPException(status, detail)


def materials(db):
    result = {}
    for row in fabric_master.records(db):
        if row.kind == 'MATERIAL' and row.status == 'ACTIVE':
            data = fabric_master.record_data(row)['data']
            if data.get('category') and data.get('unit'):
                result[row.id] = dict(id=row.id, item_code=row.code, item_name=row.name,
                                      material_category=data['category'], unit=data['unit'])
    return result


def indexed(entries, kind, key):
    return {e['data'][key]: e['data'] for e in entries.values() if e['kind'] == kind}


def batch_info(batch):
    return {k: batch.get(k, '') for k in ('id', 'item_code', 'item_name', 'unit', 'material_category',
                                           'location', 'location_id', 'lot', 'roll_no')}


def usable(batch, places):
    return (batch.get('location_id') in places and batch['quality_status'] not in {'REJECTED', 'HOLD'}
            and Decimal(batch['quantity']) > 0)


def detail(order, entries, stock, places):
    rows = [dict(**e['data'], id=e['id'], actor=e['actor_name'], recorded_at=e['occurred_at'])
            for e in entries.values() if e['kind'] == ACTION and e['data']['order_id'] == order['id']]
    voided = {r['target_id'] for r in rows if r['kind'] == 'VOID'}
    active = [r for r in rows if r['id'] not in voided]
    inputs = {r['id']: dict(r) for r in order['inputs']}
    for r in active:
        if r['kind'] == 'SELECT':
            inputs[r['batch']['id']] = {**r['batch'], 'planned': r['quantity']}
    def total(kind, key, field='target_id'):
        return sum((Decimal(r['quantity']) for r in active if r['kind'] == kind and r.get(field) == key), ZERO)
    for line in inputs.values():
        line['sent'] = wh.text(total('SEND', line['id']))
    receipts = {r['stock_id']: r['output_id'] for r in active if r['kind'] == 'RECEIVE'}
    all_roots = {r['stock_id'] for r in rows if r['kind'] == 'RECEIVE'}
    linked_stock = {r['stock_id'] for r in rows if r.get('stock_id')}
    other_movements = []
    for entry in entries.values():
        kind, body = entry['kind'], entry['data']
        if kind not in {'ISSUE', 'TRANSFER', 'RETURN', 'CORRECTION'} or entry['id'] in linked_stock:
            continue
        original = entries.get(body.get('original_id', ''), {})
        target = original if kind == 'CORRECTION' else entry
        target_body = target.get('data', {})
        batch = stock.get(target['id'] if target.get('kind') == 'RETURN' else target_body.get('batch_id', ''), {})
        if batch.get('original_batch_id') in all_roots:
            other_movements.append(dict(id=entry['id'], kind=kind, business_date=entry['business_date'],
                actor=entry['actor_name'], voucher=body.get('source_no'), original_id=body.get('original_id', ''),
                item_name=batch['item_name'], unit=batch['unit'], quantity=target_body.get('quantity', ''),
                recipient=target_body.get('counterparty',''), destination=target_body.get('purpose',''),
                reversed=entry.get('reversed', False)))
    batches = [{**batch_info(b), 'output_id': receipts[b['original_batch_id']], 'available': b['quantity']}
               for b in stock.values() if b['original_batch_id'] in receipts and usable(b, places)]
    outputs = []
    for line in order['outputs']:
        key = line['id']
        received = total('RECEIVE', key, 'output_id')
        delivered = total('DELIVER', key)
        outputs.append({**line, 'received': wh.text(received), 'delivered': wh.text(delivered),
                        'outstanding': wh.text(Decimal(line['planned']) - received),
                        'undelivered': wh.text(Decimal(line['planned']) - delivered),
                        'uncounted': wh.text(delivered - received),
                        'available': wh.text(sum((Decimal(b['available']) for b in batches if b['output_id'] == key), ZERO))})
    for row in rows:
        row['voided'] = row['id'] in voided
        if row['kind'] in {'DELIVER', 'SEND'}:
            follow = 'RECEIVE' if row['kind'] == 'DELIVER' else 'SIGN'
            row['remaining'] = wh.text(Decimal(row['quantity']) - total(follow, row['id']))
    source_no = next((r['voucher'] for r in reversed(rows) if r['kind'] == 'SOURCE'), order['source_no'])
    return {**order, 'source_no': source_no, 'inputs': list(inputs.values()), 'outputs': outputs, 'batches': batches, 'events': rows,
            'other_movements': other_movements}


def workspace(db):
    wh.ensure_schema(db)
    stock, entries = wh.projection(db, 'fabric')
    locations = wh.locations.catalog(db, 'fabric')
    places = {loc['id'] for loc in locations}
    orders = indexed(entries, ORDER, 'id')
    return dict(revision=max((e['sequence'] for e in entries.values()), default=0),
                processors=list(indexed(entries, PROCESSOR, 'id').values()), materials=list(materials(db).values()),
                stock=[{**batch_info(b), 'available': b['quantity']} for b in stock.values() if usable(b, places)],
                locations=locations, orders=[detail(o, entries, stock, places) for o in reversed(orders.values())])


def processor_catalog(db):
    wh.ensure_schema(db)
    scope = (WarehouseOperation.factory_id == wh.FACTORY, WarehouseOperation.warehouse == 'fabric')
    revision = db.scalar(select(func.max(WarehouseOperation.sequence)).where(*scope)) or 0
    rows = db.scalars(select(WarehouseOperation).where(*scope, WarehouseOperation.kind == PROCESSOR,
                      WarehouseOperation.sequence <= revision).order_by(WarehouseOperation.sequence))
    processors = {}
    for row in rows:
        value = wh.entry_data(row)['data']
        processors[value['id']] = value
    return dict(revision=revision, processors=list(processors.values()))


def save_processor(payload, entries):
    processors = indexed(entries, PROCESSOR, 'id')
    if payload.id:
        require(payload.id in processors, '找不到这家加工厂', 404)
        require(payload.code == processors[payload.id]['code'], '加工厂编号保存后不可更换')
    require(not any(p['id'] != payload.id and p['code'].casefold() == payload.code.casefold()
                    for p in processors.values()), '加工厂编号已存在', 409)
    return {**payload.model_dump(include={'code', 'name', 'processes', 'phone', 'contact', 'active'}),
            'id': payload.id or 'JG-' + uuid4().hex[:16]}


def plan_batch(stock, places, key, qty):
    batch = stock.get(key)
    require(batch and usable(batch, places), '请选择有可用库存的原料批次', 409)
    return {**batch_info(batch), 'planned': wh.text(wh.quantity(qty, '计划投入'))}


def open_order(db, payload, stock, entries, places):
    require(payload.process not in ENGINEERING, '待工程系统带出指定加工厂，仓库不能自行选厂', 409)
    processor = indexed(entries, PROCESSOR, 'id').get(payload.processor_id)
    require(processor and processor['active'] and payload.process in processor['processes'], '请选用该工艺已启用的加工厂')
    require(payload.due_date >= payload.business_date, '交期不能早于开单日期')
    if payload.previous_order_id:
        require(payload.previous_order_id in indexed(entries, ORDER, 'id'), '前序委外单不属于本仓', 404)
    catalog = materials(db)
    outputs = []
    for line in payload.outputs:
        require(line.id in catalog, '计划产物须选用已启用且具有分类和单位的物料')
        outputs.append({**catalog[line.id], 'planned': wh.text(wh.quantity(line.quantity, '应回数量'))})
    return dict(id='WW-' + uuid4().hex[:16].upper(), process=payload.process, processor=processor,
                warehouse='fabric', business_date=payload.business_date.isoformat(), due_date=payload.due_date.isoformat(),
                source_no=payload.source_no, previous_order_id=payload.previous_order_id, outputs=outputs,
                inputs=[plan_batch(stock, places, line.id, line.quantity) for line in payload.inputs])


def record_action(db, actor, state, payload, order_id, stock, entries, places):
    order = indexed(entries, ORDER, 'id').get(order_id)
    require(order, '布料仓委外单不存在', 404)
    view = detail(order, entries, stock, places)
    kind, target = payload.kind, payload.target_id
    require(kind == 'SELECT' or payload.voucher, '请填写原始凭证号')
    day = payload.business_date.isoformat()
    require(day >= order['business_date'], '业务日期不能早于委外单')
    facts = dict(order_id=order_id, kind=kind, target_id=target, business_date=day, voucher=payload.voucher or order_id)
    events = {r['id']: r for r in view['events'] if not r['voided']}
    parent = events.get(target)
    if parent:
        require(day >= parent['business_date'], '日期不能早于关联凭证')
    posted = None
    output = None
    inputs = {r['id']: r for r in view['inputs']}
    outputs = {r['id']: r for r in view['outputs']}
    supplier = order['processor']['name']
    if kind == 'SOURCE':
        require(target == order_id and not view['source_no'], '该单已有来源依据，不能覆盖', 409)
        return {**facts, 'item_name':'', 'quantity':'', 'unit':''}
    if kind != 'VOID':
        q = wh.quantity(payload.quantity, '本次数量')
        facts['quantity'] = wh.text(q)
        duplicate = any(r['kind'] == kind and r['target_id'] == target and r['voucher'] == payload.voucher
                        and (kind != 'RECEIVE' or (r.get('location_id',''), r.get('lot',''), r.get('roll_no','')) ==
                             (payload.location_id, payload.lot, payload.roll_no)) for r in events.values())
        require(not duplicate, '该明细与凭证已登记，请核对原流水；录错请先办理更正', 409)
    if kind == 'SELECT':
        require(target not in inputs, '此批次已经在计划中', 409)
        facts['batch'] = plan_batch(stock, places, target, payload.quantity)
        facts.update(unit=facts['batch']['unit'], item_name=facts['batch']['item_name'])
    elif kind == 'SEND':
        line = inputs.get(target)
        require(line, '请先在委外单上选择原料批次')
        require(q <= Decimal(line['planned']) - Decimal(line['sent']), '超过该原料批次的计划待发量', 409)
        facts.update(unit=line['unit'], item_name=line['item_name'], destination=supplier, batch=line)
        posted = dict(kind='ISSUE', batch_id=target, counterparty=supplier, purpose='委外原料实发')
    elif kind == 'SIGN':
        require(parent and parent['kind'] == 'SEND', '请选本单有效的实发凭证')
        require(q <= Decimal(parent['remaining']), '超过该笔实发待签收量', 409)
        facts.update(unit=parent['unit'], item_name=parent['item_name'])
    elif kind == 'DELIVER':
        output = outputs.get(target)
        require(output, '请选本单的计划产物')
        require(q <= Decimal(output['undelivered']), '超过本单尚未送达的产物数量', 409)
    elif kind == 'RECEIVE':
        require(parent and parent['kind'] == 'DELIVER', '请先选择加工厂送达批次')
        require(q <= Decimal(parent['remaining']), '超过该送达批次待点收数量', 409)
        output = outputs[parent['output_id']]
        posted = dict(kind='RECEIPT', item_code=output['item_code'], item_name=output['item_name'], unit=output['unit'],
                      material_category=output['material_category'], location_id=payload.location_id, lot=payload.lot,
                      roll_no=payload.roll_no, counterparty=supplier, purpose='委外产物回仓')
        facts.update(location_id=payload.location_id, lot=payload.lot, roll_no=payload.roll_no)
    elif kind == 'ISSUE':
        batch = next((b for b in view['batches'] if b['id'] == target), None)
        require(batch, '只能领用本委外单已回仓且可发的批次', 409)
        require(payload.recipient and payload.destination, '请填写领料部门和实际去向')
        output = outputs[batch['output_id']]
        facts.update(recipient=payload.recipient, destination=payload.destination, batch=batch)
        posted = dict(kind='ISSUE', batch_id=target, counterparty=payload.recipient, purpose=payload.destination)
    elif kind == 'VOID':
        require(parent and parent['kind'] not in {'VOID', 'SELECT', 'SOURCE'}, '请选本单可更正的有效凭证', 409)
        require(payload.reason, '请填写更正原因')
        require(not any(r['target_id'] == target and r['kind'] != 'VOID' for r in events.values()),
                '此凭证已有后续业务，请先核对并更正后续凭证', 409)
        facts.update(reason=payload.reason, quantity=parent['quantity'], unit=parent['unit'], item_name=parent['item_name'])
        if parent.get('stock_id'):
            posted = dict(kind='CORRECTION', original_id=parent['stock_id'], reason=payload.reason)
    if output:
        facts.update(output_id=output['id'], item_name=output['item_name'], unit=output['unit'])
    if posted:
        body = WarehouseDocumentRequest(factory_id=wh.FACTORY, request_id=uuid5(payload.request_id, 'stock'),
            expected_revision=payload.expected_revision, business_date=payload.business_date, source_system=SOURCE,
            source_no=payload.voucher, source_line=str(payload.request_id), quantity=facts['quantity'], **posted)
        recorded = wh.post(db, actor, 'fabric', body, _state=state, _commit=False,
            _metadata={'subcontract_order_id': order_id, 'subcontract_stage': kind, 'processor_id': order['processor']['id']})
        facts['stock_id'] = recorded['id']
        if kind == 'RECEIVE':
            facts['location'] = recorded['data']['location']
    return facts


def append_entry(db, actor, kind, facts, day, now, sequence, request_id, signature):
    row = WarehouseOperation(id='WJ-' + uuid4().hex[:20], factory_id=wh.FACTORY, warehouse='fabric',
        sequence=sequence, kind=kind, business_date=day.isoformat(), request_id=str(request_id),
        request_hash=signature, payload_json=wh.dump(facts), actor_id=actor.id,
        actor_name=actor.display_name, occurred_at=now.isoformat())
    db.add(row)
    return row


def execute(db, actor, payload, order_id=''):
    kind = PROCESSOR if isinstance(payload, Processor) else ORDER if isinstance(payload, Order) else ACTION
    combined_receipt = kind == ACTION and payload.kind == 'DELIVER_AND_RECEIVE'
    command = payload.model_dump(mode='json')
    # Keep request hashes of older, single-stage actions stable across upgrades.
    if command.get('received_quantity') is None:
        command.pop('received_quantity', None)
    signature = wh.digest([kind, order_id, actor.id, command])
    wh.ensure_schema(db)
    try:
        if isinstance(payload, Action) and payload.kind == 'VOID':
            lock_transaction(db, 'cutting-master', wh.FACTORY)
        state = wh.procurement.lock_factory(db)
        old = db.scalar(select(WarehouseOperation).where(WarehouseOperation.factory_id == wh.FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.request_id == str(payload.request_id)))
        if old:
            require(old.kind == kind and old.request_hash == signature, '请求编号已用于其他操作', 409)
            result = wh.entry_data(old)['data']
            db.rollback()
            return result
        stock, entries = wh.projection(db, 'fabric')
        revision = max((e['sequence'] for e in entries.values()), default=0)
        require(revision == payload.expected_revision, '库存或委外单已变化，请刷新核对后再保存', 409)
        now = business_now()
        day = getattr(payload, 'business_date', now.date())
        require(day <= now.date(), '实际业务日期不能晚于今天')
        places = {p['id'] for p in wh.locations.catalog(db, 'fabric')}
        if kind == PROCESSOR:
            result = save_processor(payload, entries)
        elif kind == ORDER:
            result = open_order(db, payload, stock, entries, places)
        else:
            if combined_receipt:
                delivery = payload.model_copy(update={'kind': 'DELIVER', 'received_quantity': None})
                facts = record_action(db, actor, state, delivery, order_id, stock, entries, places)
                revision += 1
                row = append_entry(db, actor, ACTION, facts, day, now, revision, f'{payload.request_id}:delivery', signature)
                db.flush()
                entries[row.id] = wh.entry_data(row)
                payload = payload.model_copy(update={'kind': 'RECEIVE', 'target_id': row.id,
                    'quantity': payload.received_quantity, 'received_quantity': None, 'expected_revision': revision})
            result = record_action(db, actor, state, payload, order_id, stock, entries, places)
        append_entry(db, actor, kind, result, day, now, revision + (2 if result.get('stock_id') else 1),
                     payload.request_id, signature)
        # wh.post already advanced the shared factory revision for this combined command.
        if not combined_receipt:
            state.revision += 1
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
