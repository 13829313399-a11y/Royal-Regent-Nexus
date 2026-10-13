"""Read recorded fabric order balances from the same immutable stock evidence."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.fabric_receiving import FabricReceipt
from app.services import warehouse_operations as operations
from app.services.fabric_procurement_parser import digest

FIELDS = ('opening', 'inbound', 'outbound', 'adjustment', 'balance')


def identity(batch, fallback_id=''):
    link = batch.get('procurement_receipt', {})
    facts = link.get('source_facts', {})
    source = link.get('source_line_id', '')
    root = batch.get('original_batch_id') or fallback_id
    code, unit = batch.get('item_code', ''), batch.get('unit', '')
    return dict(key=digest([source or 'unlinked:' + root, code, unit]), source_line_id=source,
        order_no=facts.get('order_no', ''), production_no=facts.get('production_no', batch.get('production_no', '')),
        style_no=facts.get('style_no', ''), supplier=facts.get('supplier', batch.get('counterparty', '')),
        item_code=code, item_name=batch.get('item_name', ''), unit=unit, linked=bool(source))


def collect(receipts, entries, stock):
    events = []

    def add(entry, batch, mode, value, label, moved='0'):
        body = entry['data']
        info = identity(batch, entry['id'])
        q = Decimal(value)
        change = -q if mode == 'OUTBOUND' else q
        events.append(dict(**info, id=entry['id'], date=entry['business_date'], mode=mode, label=label,
            quantity=operations.text(q), stock_change=operations.text(change), moved_quantity=moved,
            source_no=body.get('source_no') or entry['id'], original_id=body.get('original_id', ''),
            recipient=body.get('counterparty', '') if mode != 'INBOUND' else '',
            location=body.get('location') or batch.get('location', ''),
            channel='SCAN' if body.get('handover_document_id') else 'MANUAL',
            actor_name=entry.get('actor_name', ''), reason=body.get('reason', ''), sequence=entry.get('sequence', 0)))

    # Original receipt headers are counted once even if stored in multiple rolls/bins.
    for receipt in receipts:
        facts, payload = json.loads(receipt.source_json), json.loads(receipt.payload_json)
        batch = dict(item_code=facts.get('material_code', ''), item_name=facts.get('material_name', ''), unit=receipt.unit,
            procurement_receipt=dict(source_line_id=receipt.source_line_id, source_facts=facts))
        add(dict(id=receipt.id, business_date=receipt.receipt_date, actor_name=receipt.actor_name,
            data=dict(source_no=payload.get('delivery_reference', receipt.delivery_reference))), batch, 'INBOUND', receipt.quantity, '采购实收入库')
    for entry in entries.values():
        body, kind = entry['data'], entry['kind']
        if kind == 'OPENING':
            add(entry, stock[entry['id']], 'ADJUSTMENT', body['quantity'], '期初库存建立')
        elif kind == 'STOCKTAKE':
            add(entry, entry['batch_snapshot'], 'ADJUSTMENT', body['quantity'], '库存盘点差异')
        elif kind == 'RECEIPT':
            add(entry, stock[entry['id']], 'INBOUND', body['quantity'], '送货单入库' if body.get('handover_document_id') else '手动入库')
        elif kind == 'ISSUE':
            add(entry, entry['batch_snapshot'], 'OUTBOUND', body['quantity'], '扫码出库' if body.get('handover_document_id') else '手动出库')
        elif kind == 'RETURN':
            add(entry, entry['batch_snapshot'], 'ADJUSTMENT', body['quantity'], '车间退料')
        elif kind == 'TRANSFER':
            add(entry, entry['batch_snapshot'], 'ADJUSTMENT', '0', '调仓（总库存不变）', body['quantity'])
        elif kind == 'CORRECTION':
            if body.get('procurement_original_receipt_id'):
                original = next(row for row in receipts if row.id == body['procurement_original_receipt_id'])
                facts = json.loads(original.source_json)
                batch = dict(item_code=facts.get('material_code', ''), item_name=facts.get('material_name', ''), unit=original.unit,
                    procurement_receipt=dict(source_line_id=original.source_line_id, source_facts=facts))
                add(entry, batch, 'INBOUND', str(-Decimal(body['quantity'])), '整单入库冲销')
            else:
                original = entries.get(body.get('original_id'))
                if not original:
                    continue
                batch = original.get('batch_snapshot') or stock.get(original['id'])
                if original['kind'] in ('RECEIPT', 'ISSUE'):
                    mode = 'INBOUND' if original['kind'] == 'RECEIPT' else 'OUTBOUND'
                    event_entry = {**entry, 'data': {**body, 'handover_document_id': original['data'].get('handover_document_id', '')}}
                    add(event_entry, batch, mode, str(-Decimal(original['data']['quantity'])), '整单入库冲销' if mode == 'INBOUND' else '整单出库冲销')
                elif original['kind'] == 'TRANSFER':
                    add(entry, batch, 'ADJUSTMENT', '0', '调仓冲销（总库存不变）', original['data']['quantity'])
    return events


def summarize(events, date_from='', date_to='', search='', supplier=''):
    for value in (date_from, date_to):
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                raise HTTPException(422, '请填写有效的开始和结束日期')
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, '结束日期不能早于开始日期')
    if len(search) > 128 or len(supplier) > 255:
        raise HTTPException(422, '查询条件过长')
    groups = defaultdict(list)
    for event in events:
        groups[event['key']].append(event)
    suppliers = sorted({event['supplier'] for event in events if event['supplier']})
    rows, details, totals = [], [], {}
    for key, history in groups.items():
        # Search selects the identity first; every earlier event remains in its balance.
        if supplier and not any(row['supplier'] == supplier for row in history):
            continue
        if search.strip().casefold() not in json.dumps(history, ensure_ascii=False).casefold():
            continue
        included = [row for row in history if not date_to or row['date'] <= date_to]
        if not included:
            continue
        before = [row for row in included if date_from and row['date'] < date_from]
        period = [row for row in included if not date_from or row['date'] >= date_from]
        quantities = dict(opening=sum((Decimal(row['stock_change']) for row in before), Decimal(0)),
            inbound=sum((Decimal(row['quantity']) for row in period if row['mode'] == 'INBOUND'), Decimal(0)),
            outbound=sum((Decimal(row['quantity']) for row in period if row['mode'] == 'OUTBOUND'), Decimal(0)),
            adjustment=sum((Decimal(row['quantity']) for row in period if row['mode'] == 'ADJUSTMENT'), Decimal(0)))
        quantities['balance'] = quantities['opening'] + quantities['inbound'] - quantities['outbound'] + quantities['adjustment']
        info = {field: history[0][field] for field in ('key', 'source_line_id', 'order_no', 'production_no', 'style_no', 'supplier', 'item_code', 'item_name', 'unit', 'linked')}
        rows.append({**info, **{field: operations.text(value) for field, value in quantities.items()}, 'document_count': len(period)})
        details.extend(period)
        unit_totals = totals.setdefault(info['unit'], {field: Decimal(0) for field in FIELDS})
        for field in FIELDS:
            unit_totals[field] += quantities[field]
    return dict(date_from=date_from, date_to=date_to, search=search, supplier=supplier, suppliers=suppliers,
        rows=sorted(rows, key=lambda row: (row['order_no'], row['production_no'], row['item_code'], row['unit'], row['key'])),
        details=sorted(details, key=lambda row: (row['date'], row['sequence'], row['id']), reverse=True),
        totals=[dict(unit=unit, **{field: operations.text(value) for field, value in values.items()}) for unit, values in sorted(totals.items())],
        basis='记录期初为开始日期前的全部已记结余；期间建立的期初库存及盘点差异列入调整，不增加采购实收。调仓调整量为零，另列移动数量。尚未计价。')


def report(db, date_from='', date_to='', search='', supplier=''):
    operations.ensure_schema(db)
    operations.procurement.lock_factory(db)
    stock, entries = operations.projection(db, 'fabric')
    receipts = list(db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == operations.FACTORY)))
    result = summarize(collect(receipts, entries, stock), date_from, date_to, search, supplier)
    result['version'] = digest(result)
    return result
