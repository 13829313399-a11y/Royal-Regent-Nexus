"""Warehouse document posting, without importing historical balances or valuing stock.

All writes share the existing fabric factory lock. Views replay immutable documents
over immutable original fabric receipts; transfer/return lots retain their lineage.
"""
import copy
import json
from decimal import Decimal
from uuid import uuid4, uuid5
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.core.time import business_now
from app.models.warehouse_operations import WarehouseOperation
from app.models.fabric_receiving import FabricStockBatch, FabricInventoryMovement, FabricReceipt
from app.services import fabric_procurement as procurement
from app.services.fabric_procurement_parser import dump, digest
from app.services.fabric_receiving import quantity
from app.services import warehouse_locations as locations

FACTORY = 'huakang-c'
REVISION = '20261009_0152'
OUTBOUND = {'ISSUE', 'PROCESS_SEND', 'PACK_SEND'}


def ensure_schema(db):
    procurement.ensure_schema(db)
    if WarehouseOperation.__tablename__ not in inspect(db.get_bind()).get_table_names():
        raise HTTPException(503, f'仓库收发数据库尚未升级，请备份后执行迁移 {REVISION}')


def required(body, *fields):
    labels = {'source_no': '来源单号或手工凭证号', 'source_line': '来源明细编号', 'item_code': '物料 / 产品编码',
              'item_name': '物料 / 产品名称', 'unit': '单位', 'location': '仓位', 'counterparty': '往来单位 / 领用方',
              'reason': '依据或原因', 'process_state': '加工状态', 'lot': '缸号', 'responsible_person': '确认人', 'purpose': '用途 / 工序'}
    for field in fields:
        if not str(body.get(field) or '').strip():
            raise HTTPException(422, f'请填写{labels.get(field, field)}')


def decimal(value):
    return Decimal(str(value))


def text(value):
    return format(value, 'f')


def documents(db, warehouse):
    return list(db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == FACTORY,
        WarehouseOperation.warehouse == warehouse).order_by(WarehouseOperation.sequence)))


def entry_data(row):
    return {'id': row.id, 'kind': row.kind, 'sequence': row.sequence, 'business_date': row.business_date,
            'data': json.loads(row.payload_json), 'actor_name': row.actor_name, 'occurred_at': row.occurred_at}


def initial_stock(db, warehouse):
    stock = {}
    if warehouse != 'fabric':
        return stock
    from app.services.fabric_receiving import ensure_schema as receiving_schema
    receiving_schema(db)
    rows = db.execute(select(FabricStockBatch, FabricInventoryMovement, FabricReceipt).join(FabricInventoryMovement,
        (FabricInventoryMovement.batch_id == FabricStockBatch.id) & (FabricInventoryMovement.factory_id == FACTORY)
        & (FabricInventoryMovement.kind == 'RECEIPT')).join(FabricReceipt, FabricReceipt.id == FabricStockBatch.receipt_id)
        .where(FabricStockBatch.factory_id == FACTORY, FabricReceipt.factory_id == FACTORY))
    for batch, movement, receipt in rows:
        facts = json.loads(receipt.source_json)
        evidence = json.loads(receipt.payload_json)
        saved_location = evidence.get('batch_locations', {}).get(batch.id, {})
        stock[batch.id] = {'id': batch.id, 'item_code': facts.get('material_code', ''), 'item_name': facts.get('material_name', ''),
            'unit': receipt.unit, 'process_state': '', 'material_category': batch.material_category, 'location': batch.location,
            'location_id': saved_location.get('id', ''), 'location_snapshot': saved_location,
            'inbound_quantity': movement.quantity, 'outbound_quantity': '0', 'transfer_quantity': '0',
            'lot': batch.dye_lot, 'roll_no': batch.roll_no, 'quantity': movement.quantity, 'quality_status': batch.quality_status,
            'source_no': receipt.delivery_reference, 'source_document': receipt.id, 'production_no': facts.get('production_no', ''),
            'received_on': receipt.receipt_date, 'counterparty': facts.get('supplier', ''), 'original_batch_id': batch.id,
            'actor_name': receipt.actor_name, 'occurred_at': receipt.occurred_at}
    return stock


def batch_for(stock, key):
    if key not in stock:
        raise HTTPException(404, '所选批次不存在于当前仓库')
    return stock[key]


def original_for(entries, key, kinds):
    item = entries.get(key)
    if not item or item['kind'] not in kinds or item.get('reversed'):
        raise HTTPException(409, '原单不存在、已更正或不适用于本次业务')
    return item


def new_batch(stock, entry, data, quantity_value, base=None, quality='PENDING_INSPECTION'):
    row = copy.deepcopy(base) if base else {key: data.get(key, '') for key in
        ('item_code', 'item_name', 'unit', 'process_state', 'material_category', 'lot', 'roll_no', 'counterparty', 'production_no')}
    row.update(id=entry['id'], quantity=text(quantity_value), quality_status=quality, location=data['location'],
        source_no=data['source_no'], source_document=entry['id'], received_on=entry['business_date'], last_business_date=entry['business_date'])
    row.update(location_id=data.get('location_id', ''), location_snapshot=data.get('location_snapshot', {}),
        inbound_quantity='0' if entry['kind'] == 'TRANSFER' else text(quantity_value), outbound_quantity='0',
        transfer_quantity=text(quantity_value) if entry['kind'] == 'TRANSFER' else '0')
    if base and entry['kind'] == 'TRANSFER':
        for key in ('source_no', 'source_document', 'received_on'):
            row[key] = base[key]
    row.setdefault('original_batch_id', entry['id'])
    stock[entry['id']] = row


def same_item(batch, data):
    return all(batch.get(key, '') == data.get(key, '') for key in ('item_code', 'unit', 'process_state'))


def describe_item(data, batch):
    for key in ('item_code', 'item_name', 'unit', 'process_state', 'material_category', 'lot', 'roll_no'):
        data[key] = batch.get(key, '')


def validate_current_master(db, warehouse, body, stock):
    """Current master checks run only on new postings, never reinterpret history."""
    kind = body['kind']
    if kind in {'RECEIPT', 'RETURN', 'TRANSFER', 'PROCESS_RETURN', 'LOCATION_BIND'}:
        target = locations.resolve(db, warehouse, body.get('location_id', ''))
        body['location_id'], body['location'], body['location_snapshot'] = target['id'], target['label'], target
    if kind in OUTBOUND | {'TRANSFER', 'LOCATION_BIND'}:
        batch = batch_for(stock, body['batch_id'])
        if kind == 'LOCATION_BIND':
            if batch.get('location_id'):
                raise HTTPException(409, '该批次已经关联正式仓位；实际移动请使用调仓')
            if not body.get('confirmed') or not body.get('reason'):
                raise HTTPException(422, '请核实实物所在仓位，确认并填写核对依据')
            if decimal(batch['quantity']) <= 0:
                raise HTTPException(409, '该批次已无结余，无需核实仓位')
        else:
            locations.resolve(db, warehouse, batch.get('location_id', ''), inbound=False)
    if warehouse != 'fabric' or kind in {'QUALITY', 'CORRECTION', 'LOCATION_BIND'}:
        return
    from app.services.fabric_master import records
    current = records(db)
    identity = stock.get(body.get('batch_id')) or body
    if body['kind'] not in {'RETURN', 'TRANSFER'}:
        for record in current:
            known = (record.kind == 'MATERIAL' and record.code == identity.get('item_code')) or (
                record.kind == 'UNIT' and identity.get('unit') in (record.code, record.name))
            if known and record.status == 'INACTIVE':
                raise HTTPException(422, '所选物料或单位已停用，请核对基础资料')


def apply_entry(stock, entries, entry, warehouse):
    """Validate and apply a document to an isolated projection, before writing any row."""
    data, kind, identifier = entry['data'], entry['kind'], entry['id']
    if kind == 'MASTER_LOCATION':
        entries[identifier] = entry
        return
    if kind == 'LOCATION_BIND':
        batch = batch_for(stock, data['batch_id'])
        entry['batch_snapshot'] = copy.deepcopy(batch)
        describe_item(data, batch)
        data['previous_location'] = batch['location']
        batch.update(location_id=data['location_id'], location=data['location'], location_snapshot=data['location_snapshot'])
        entries[identifier] = entry
        return
    q = quantity(data['quantity'], '本次数量') if kind not in {'QUALITY', 'CORRECTION'} else Decimal(0)
    if kind not in {'QUALITY', 'CORRECTION'}:
        data['quantity'] = text(q)
    for allocation in data.get('allocations', []):
        allocation['quantity'] = text(quantity(allocation['quantity'], '分配数量'))
    if kind in OUTBOUND | {'TRANSFER', 'QUALITY'}:
        batch = batch_for(stock, data['batch_id'])
        if entry['business_date'] < batch.get('last_business_date', batch['received_on']):
            raise HTTPException(409, '业务日期早于该批次最近一次操作，请核对实际日期及补录依据')
    if kind in {'RECEIPT', 'REQUEST', 'TASK'}:
        required(data, 'source_no', 'item_code', 'item_name', 'unit', 'counterparty', 'source_line')
        if warehouse == 'semi':
            required(data, 'process_state')
        for old in entries.values():
            old_data = old['data']
            if old['kind'] == kind and all(data.get(k, '') == old_data.get(k, '') for k in ('source_system', 'source_no', 'source_line')):
                if not old.get('reversed'):
                    raise HTTPException(409, '该来源明细已登记，请查看原单；版本变化不能重复记账')
                data['replaces_id'] = old['id']
        if kind == 'RECEIPT':
            required(data, 'location')
            if warehouse == 'fabric' and data['material_category'] == 'FABRIC':
                required(data, 'lot')
            new_batch(stock, entry, data, q)
        elif kind == 'TASK':
            if warehouse != 'semi':
                raise HTTPException(422, '布料仓不建立半成品加工任务')
            required(data, 'purpose')
            entry.update(received_quantity='0')
        else:
            entry.update(issued_quantity='0')
    elif kind == 'QUALITY':
        batch = batch_for(stock, data['batch_id'])
        if entry['business_date'] < batch['received_on']:
            raise HTTPException(422, '质检日期不能早于该批次收货日期')
        required(data, 'responsible_person')
        if data['quality_status'] == batch['quality_status']:
            raise HTTPException(409, '该批次已是所选质量状态')
        entry['previous_quality'] = batch['quality_status']
        describe_item(data, batch)
        entry['batch_snapshot'] = copy.deepcopy(batch)
        batch['quality_status'] = data['quality_status']
        batch['last_business_date'] = entry['business_date']
    elif kind in OUTBOUND or kind == 'TRANSFER':
        batch = batch_for(stock, data['batch_id'])
        if entry['business_date'] < batch['received_on']:
            raise HTTPException(422, '发出或移库日期不能早于该批次收货日期')
        if q > decimal(batch['quantity']):
            raise HTTPException(409, '本次数量超过当前批次结余，请刷新后核对')
        if kind != 'TRANSFER' and batch['quality_status'] in {'REJECTED', 'HOLD'}:
            raise HTTPException(409, '该批次有不合格或暂停记录，请交 QC 处理后再出库')
        required(data, 'counterparty' if kind != 'TRANSFER' else 'location')
        if kind == 'TRANSFER':
            if (data.get('location_id') and data['location_id'] == batch.get('location_id')) or (not data.get('location_id') and data['location'].casefold() == batch['location'].casefold()):
                raise HTTPException(422, '目标仓位须与来源仓位不同')
            new_batch(stock, entry, data, q, batch, batch['quality_status'])
        if kind == 'ISSUE':
            request = original_for(entries, data['original_id'], {'REQUEST'}) if data['original_id'] else None
            if request:
                if entry['business_date'] < request['business_date']:
                    raise HTTPException(422, '发料日期不能早于申请日期')
                if not same_item(batch, request['data']) or data['counterparty'] != request['data']['counterparty']:
                    raise HTTPException(422, '批次物料、单位、加工状态或领用方与申请不符')
                if decimal(request['issued_quantity']) + q > decimal(request['data']['quantity']):
                    raise HTTPException(409, '累计实发不能超过申请量')
            allocation_total = sum((quantity(a['quantity'], '分配数量') for a in data['allocations']), Decimal(0))
            if data['allocations'] and allocation_total != q:
                raise HTTPException(422, '分配数量合计须等于本次实发，分配不重复扣库存')
            if request:
                request['issued_quantity'] = text(decimal(request['issued_quantity']) + q)
        if kind == 'PROCESS_SEND':
            if warehouse != 'semi':
                raise HTTPException(422, '加工交接只适用于半成品仓')
            task = original_for(entries, data['task_id'], {'TASK'})
            if entry['business_date'] < task['business_date']:
                raise HTTPException(422, '加工发出日期不能早于任务日期')
            if data['counterparty'] != task['data']['counterparty']:
                raise HTTPException(422, '加工方与任务不符')
            entry.update(consumed_quantity='0', returned_quantity='0')
        if kind == 'PACK_SEND':
            if warehouse != 'semi':
                raise HTTPException(422, '包装交接只适用于半成品仓')
            entry.update(received_quantity='0')
        entry['batch_snapshot'] = copy.deepcopy(batch)
        describe_item(data, batch)
        entry['returned_quantity'] = '0'
        flow = 'transfer_quantity' if kind == 'TRANSFER' else 'outbound_quantity'
        batch[flow] = text(decimal(batch.get(flow, '0')) + (-q if kind == 'TRANSFER' else q))
        batch['quantity'] = text(decimal(batch['quantity']) - q)
        batch['last_business_date'] = entry['business_date']
    elif kind in {'RETURN', 'PROCESS_RETURN', 'PACK_RECEIVE'}:
        allowed = {'ISSUE', 'PACK_SEND'} if kind == 'RETURN' else {'PROCESS_SEND'} if kind == 'PROCESS_RETURN' else {'PACK_SEND'}
        original = original_for(entries, data['original_id'], allowed)
        output_lot, output_roll = data['lot'], data['roll_no']
        entry['batch_snapshot'] = copy.deepcopy(original['batch_snapshot'])
        describe_item(data, original['batch_snapshot'])
        data['counterparty'] = original['data']['counterparty']
        if entry['business_date'] < original['business_date']:
            raise HTTPException(422, '回货或回执日期不能早于原发出日期')
        if kind == 'PACK_RECEIVE':
            required(data, 'responsible_person')
            used = decimal(original['received_quantity']) + decimal(original['returned_quantity'])
            if used + q > decimal(original['data']['quantity']):
                raise HTTPException(409, '累计包装实收加退回不能超过原实发量')
            original['received_quantity'] = text(decimal(original['received_quantity']) + q)
        elif kind == 'RETURN':
            required(data, 'location')
            used = decimal(original['returned_quantity'])
            if original['kind'] == 'PACK_SEND':
                used += decimal(original['received_quantity'])
            if used + q > decimal(original['data']['quantity']):
                raise HTTPException(409, '累计退回不能超过原实发可退数量')
            original['returned_quantity'] = text(decimal(original['returned_quantity']) + q)
            new_batch(stock, entry, data, q, original['batch_snapshot'])
        else:
            required(data, 'location')
            task = original_for(entries, original['data']['task_id'], {'TASK'})
            consumed = quantity(data['consumed_quantity'], '本轮核销发出数量')
            data['consumed_quantity'] = text(consumed)
            if decimal(original['consumed_quantity']) + consumed > decimal(original['data']['quantity']):
                raise HTTPException(409, '本轮累计核销量超过原发出量')
            if decimal(task['received_quantity']) + q > decimal(task['data']['quantity']):
                raise HTTPException(409, '累计回货超过任务计划产出，请先核对任务')
            original['consumed_quantity'] = text(decimal(original['consumed_quantity']) + consumed)
            original['returned_quantity'] = text(decimal(original['returned_quantity']) + q)
            task['received_quantity'] = text(decimal(task['received_quantity']) + q)
            output = {**task['data'], 'location_id': data.get('location_id', ''), 'location_snapshot': data.get('location_snapshot', {}), 'location': data['location'], 'lot': output_lot, 'roll_no': output_roll, 'source_no': data['source_no']}
            new_batch(stock, entry, output, q)
            describe_item(data, stock[identifier])
            data['consumed_unit'] = original['batch_snapshot']['unit']
    elif kind == 'CORRECTION':
        required(data, 'reason')
        target = original_for(entries, data['original_id'], {'RECEIPT', 'ISSUE', 'TRANSFER', 'PROCESS_SEND', 'PACK_SEND'})
        if entry['business_date'] < target['business_date']:
            raise HTTPException(422, '更正日期不能早于原业务日期')
        for later in entries.values():
            if later['sequence'] > target['sequence'] and any(later['data'].get(key) == target['id'] for key in ('batch_id', 'original_id', 'task_id')):
                raise HTTPException(409, '原单已有后续质检、收发或交接，不能直接冲销')
        tq = decimal(target['data']['quantity'])
        describe_item(data, target.get('batch_snapshot') or batch_for(stock, target['id']))
        data['quantity'] = text(tq)
        data['reversed_kind'] = target['kind']
        data['counterparty'] = target['data']['counterparty']
        if target['kind'] in {'RECEIPT', 'TRANSFER'}:
            if decimal(batch_for(stock, target['id'])['quantity']) != tq:
                raise HTTPException(409, '原批次数量已变化，不能直接冲销')
            stock[target['id']]['quantity'] = '0'
            flow = 'transfer_quantity' if target['kind'] == 'TRANSFER' else 'inbound_quantity'
            stock[target['id']][flow] = '0'
        if target['kind'] != 'RECEIPT':
            batch = batch_for(stock, target['data']['batch_id'])
            if entry['business_date'] < batch.get('last_business_date', batch['received_on']):
                raise HTTPException(409, '更正日期早于该批次最近一次操作')
            flow = 'transfer_quantity' if target['kind'] == 'TRANSFER' else 'outbound_quantity'
            batch[flow] = text(decimal(batch.get(flow, '0')) + (tq if target['kind'] == 'TRANSFER' else -tq))
            batch['quantity'] = text(decimal(batch['quantity']) + tq)
            batch['last_business_date'] = entry['business_date']
        if target['kind'] == 'ISSUE' and target['data']['original_id']:
            request = entries[target['data']['original_id']]
            request['issued_quantity'] = text(decimal(request['issued_quantity']) - tq)
        target['reversed'] = True
    else:
        raise HTTPException(422, '不支持的仓库业务')
    entries[identifier] = entry


def projection(db, warehouse):
    stock, entries = initial_stock(db, warehouse), {}
    for row in documents(db, warehouse):
        apply_entry(stock, entries, entry_data(row), warehouse)
    return stock, entries


def workspace(db, warehouse):
    ensure_schema(db)
    stock, entries = projection(db, warehouse)
    rows = list(entries.values())
    original_receipts = []
    if warehouse == 'fabric':
        from app.schemas.warehouse_operations import WarehouseDocumentRequest
        for batch in initial_stock(db, warehouse).values():
            body = WarehouseDocumentRequest(factory_id=FACTORY, request_id='00000000-0000-0000-0000-000000000000', expected_revision=0,
                kind='RECEIPT', business_date=batch['received_on'], source_no=batch['source_no'], source_line=batch['id'],
                item_code=batch['item_code'], item_name=batch['item_name'], unit=batch['unit'], material_category=batch['material_category'],
                location=batch['location'], lot=batch['lot'], roll_no=batch['roll_no'], quantity=batch['quantity'], counterparty=batch['counterparty']).model_dump(mode='json')
            # A read projection must not manufacture new request identities.
            body['request_id'] = ''
            original_receipts.append({'id': batch['id'], 'kind': 'RECEIPT', 'sequence': 0, 'business_date': batch['received_on'],
                'data': body, 'actor_name': batch['actor_name'], 'occurred_at': batch['occurred_at'], 'read_only': True})
    catalog = locations.catalog(db, warehouse)
    by_id = {r['id']: r for r in catalog}
    for batch in stock.values():
        place = by_id.get(batch.get('location_id'))
        batch['location_verified'] = place is not None
        batch['location_status'] = place['status'] if place else 'UNVERIFIED'
        batch['warehouse_name'] = place['warehouse'] if place else ''
        batch['location_label'] = place['label'] if place else batch['location']
        batch['available_quantity'] = '0' if not place or batch['quality_status'] in {'REJECTED', 'HOLD'} else batch['quantity']
    return {'revision': max((row['sequence'] for row in rows), default=0), 'stock': list(stock.values()),
            'locations': catalog, 'documents': [row for row in rows[::-1] if row['kind'] != 'MASTER_LOCATION'], 'original_receipts': original_receipts}


def request_body(payload):
    body = payload.model_dump(mode='json')
    # Preserve hashes for exact retries saved before stable location fields existed.
    for key in ('location_id', 'confirmed'):
        if not body.get(key):
            body.pop(key, None)
    return body


def post(db, actor, warehouse, payload, *, _state=None, _commit=True, _metadata=None):
    ensure_schema(db)
    body = request_body(payload)
    signature = digest([warehouse, actor.id, body])
    try:
        state = _state if _state is not None else procurement.lock_factory(db)
        old = db.scalar(select(WarehouseOperation).where(WarehouseOperation.factory_id == FACTORY,
            WarehouseOperation.warehouse == warehouse, WarehouseOperation.request_id == str(payload.request_id)))
        if old:
            if old.request_hash != signature:
                raise HTTPException(409, '请求编号已用于其他内容或操作者，请核对原单')
            if _metadata is None and json.loads(old.payload_json).get('bulk_request_id'):
                raise HTTPException(409, '该请求属于批量出库，请使用原批量请求核对')
            result = entry_data(old)
            if _commit:
                db.rollback()
            return result
        if payload.kind == 'QUALITY':
            raise HTTPException(409, '质检由 QC 模块负责，仓库不再登记质检结论')
        stock, entries = projection(db, warehouse)
        revision = max((entry['sequence'] for entry in entries.values()), default=0)
        if payload.expected_revision != revision:
            raise HTTPException(409, '收发记录已变化，请刷新并重新核对后保存')
        if payload.business_date > business_now().date():
            raise HTTPException(422, '实际业务日期不能晚于今天')
        identifier = ('FB-' if warehouse == 'fabric' else 'SF-') + uuid4().hex[:20]
        now = business_now().isoformat()
        entry = {'id': identifier, 'kind': payload.kind, 'sequence': revision + 1, 'business_date': body['business_date'],
                 'data': body, 'actor_name': actor.display_name, 'occurred_at': now}
        if _metadata:
            body.update(_metadata)
        validate_current_master(db, warehouse, body, stock)
        apply_entry(stock, entries, entry, warehouse)
        # Source-linked fabric receipts are created by the existing receiving API;
        # this manual path never invents purchase progress or imported opening stock.
        row = WarehouseOperation(id=identifier, factory_id=FACTORY, warehouse=warehouse, sequence=revision + 1,
            request_id=str(payload.request_id), request_hash=signature, kind=payload.kind, business_date=body['business_date'],
            payload_json=dump(body), actor_id=actor.id, actor_name=actor.display_name, occurred_at=now)
        db.add(row)
        state.revision += 1
        db.flush()
        if _commit:
            db.commit()
        return entry_data(row)
    except Exception:
        db.rollback()
        raise


def bulk_issue(db, actor, warehouse, payload):
    from app.schemas.warehouse_operations import WarehouseDocumentRequest
    ensure_schema(db)
    try:
        state = procurement.lock_factory(db)
        signature = digest(['bulk-issue', warehouse, actor.id, payload.model_dump(mode='json')])
        ids = [str(payload.request_id)] + [str(uuid5(payload.request_id, f'issue-{i}')) for i in range(1, len(payload.items))]
        existing = list(db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == FACTORY,
            WarehouseOperation.warehouse == warehouse, WarehouseOperation.request_id.in_(ids))))
        if existing:
            if len(existing) != len(ids) or any(json.loads(r.payload_json).get('bulk_hash') != signature for r in existing):
                raise HTTPException(409, '请求编号已用于其他单据或内容，请核对原批量出库')
            result = [entry_data(r) for r in sorted(existing, key=lambda r: r.sequence)]
            db.rollback(); return {'documents': result}
        if len({item.batch_id for item in payload.items}) != len(payload.items):
            raise HTTPException(422, '同一批次不能重复勾选，请合并数量')
        result = []
        for index, item in enumerate(payload.items):
            request = WarehouseDocumentRequest(factory_id=FACTORY, request_id=ids[index],
                expected_revision=payload.expected_revision + index, kind='ISSUE', business_date=payload.business_date,
                batch_id=item.batch_id, quantity=item.quantity, counterparty=item.counterparty or payload.counterparty, reason=payload.reason)
            result.append(post(db, actor, warehouse, request, _state=state, _commit=False,
                _metadata={'bulk_request_id': str(payload.request_id), 'bulk_hash': signature}))
        db.commit()
        return {'documents': result}
    except Exception:
        db.rollback()
        raise
