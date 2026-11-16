"""One read model for actual receipts, retaining each posting system's identity."""
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models.fabric_receiving import FabricReceipt
from app.models.material_handover import HandoverEvent
from app.models.warehouse_operations import WarehouseOperation
from app.services import fabric_receiving as receiving
from app.services import warehouse_operations as operations
from app.services.fabric_receipt_corrections import reversal_rows
from app.services.fabric_receipt_pricing import purchase_price_reference


def operation_batch(entry):
    body = entry['data']
    return dict(id=entry['id'], quantity=body['quantity'], location=body.get('location', ''),
                dye_lot=body.get('lot', ''), roll_no=body.get('roll_no', ''), quality_status='PENDING_INSPECTION')


def correction_record(entry):
    return dict(id=entry['id'], date=entry['business_date'], reason=entry['data'].get('reason', ''),
                actor_name=entry['actor_name']) if entry else None


def operation_record(entry, reversal):
    body = entry['data']
    purchase = body.get('procurement_receipt') or {}
    pending_reason = body.get('procurement_pending_reason', '')
    purchase_status = ('LINKED' if purchase else 'PENDING') if pending_reason and not reversal else ''
    facts = dict(purchase.get('source_facts') or {})
    facts.update(material_code=body.get('item_code', ''), material_name=body.get('item_name', ''),
                 supplier=body.get('counterparty', ''))
    facts['production_no'] = facts.get('production_no') or body.get('production_no', '')
    facts.setdefault('order_no', '')
    facts['contract_no'] = facts.get('contract_no') or body.get('handover_contract_no', '')
    line = body.get('handover_line_snapshot') or {}
    return dict(id=entry['id'], history_key='OPERATION:' + entry['id'], operation_id=entry['id'],
        receipt_origin='HANDOVER' if body.get('handover_document_id') else 'MANUAL',
        handover_document_id=body.get('handover_document_id', ''),
        purchase_status=purchase_status, procurement_pending_reason=pending_reason,
        source_line_id=purchase.get('source_line_id') or body.get('source_line', ''),
        source_revision=purchase.get('source_revision', 0), source_version=body.get('source_version', ''),
        facts=facts, quantity=body['quantity'], unit=body['unit'], prior_received_quantity=None,
        receipt_date=entry['business_date'], accounting_month=entry['business_date'][:7],
        delivery_reference=body.get('source_no', ''), material_category=body.get('material_category', ''),
        difference_reason=purchase.get('difference_reason', ''), note=body.get('reason', ''),
        actor_name=entry['actor_name'], occurred_at=entry['occurred_at'], stock_posted=True,
        unit_price=line.get('unit_price', ''), price_unit=line.get('price_unit', ''),
        currency=line.get('currency', ''), price_basis='原送货单参考价格；本页不推算金额或应付金额',
        purchase_price=purchase_price_reference(purchase.get('source_facts') or {}),
        reversed=bool(reversal), reversal=correction_record(reversal), batches=[operation_batch(entry)])


def handover_post_key(entry):
    body = entry['data']
    return body.get('handover_document_id'), body.get('handover_request_id'), body.get('handover_line_id')


def line_observation(detail, request_id, line_id, unit, batch_ids):
    evidence = detail.get('receipt_observation') or {}
    if evidence.get('request_id') != request_id:
        return None
    line = next((item for item in evidence['lines'] if item['line_id'] == line_id and item['unit'] == unit), None)
    if not line or not line['parts']:
        return None
    if any(part.get('operation_id') and part['operation_id'] not in batch_ids for part in line['parts']):
        return None

    counts = ('counted_quantity', 'damaged_quantity', 'rejected_quantity', 'other_unusable_quantity')
    parts = [{**{field: part[field] for field in (*counts, 'accepted_quantity')},
              'location': part.get('location', ''), 'dye_lot': part.get('lot', ''),
              'roll_no': part.get('roll_no', '')} for part in line['parts']]
    # Some bins can be posted by entering net quantity alone. Missing physical counts
    # in those bins do not establish zero discrepancies or a complete receipt total.
    complete = len(parts) == sum(part['line_id'] == line_id for part in detail['selections']['lines'])
    totals = {field: receiving.decimal_text(sum(Decimal(part[field]) for part in parts))
              for field in counts} if complete else {}
    return dict(parts=parts, complete=complete, **totals,
                delivered_quantity=line.get('delivered_quantity'), shortage_quantity=line.get('shortage_quantity'))


def handover_receipt_detail(db, receipt_id):
    """Read one original delivery line in one posting, keeping each correction independent."""
    operations.ensure_schema(db)
    ledger = select(WarehouseOperation).where(WarehouseOperation.factory_id == receiving.source.FACTORY,
                                               WarehouseOperation.warehouse == 'fabric')
    receipts = ledger.where(WarehouseOperation.kind == 'RECEIPT')
    row = db.scalar(receipts.where(WarehouseOperation.id == receipt_id))
    if not row:
        raise HTTPException(404, '找不到这笔送货单入库记录')
    anchor = operations.entry_data(row)
    key = handover_post_key(anchor)
    document_id, request_id, line_id = key
    if not document_id:
        raise HTTPException(404, '找不到这笔送货单入库记录')
    unit = anchor['data']['unit']

    entries = [anchor]
    posting = None
    if request_id and line_id and inspect(db.get_bind()).has_table(HandoverEvent.__tablename__):
        events = db.scalars(select(HandoverEvent.detail_json).where(
            HandoverEvent.factory_id == receiving.source.FACTORY, HandoverEvent.document_id == document_id,
            HandoverEvent.request_id == request_id, HandoverEvent.kind == 'POST'))
        for raw in events:
            detail = json.loads(raw)
            operation_ids = detail.get('operation_ids') or []
            if receipt_id not in operation_ids:
                continue
            posting = detail
            rows = db.scalars(receipts.where(WarehouseOperation.id.in_(operation_ids)).order_by(WarehouseOperation.sequence))
            entries = [entry for entry in map(operations.entry_data, rows)
                       if handover_post_key(entry) == key and entry['data']['unit'] == unit]
            break

    batch_ids = {entry['id'] for entry in entries}
    reversals = {}
    for correction in db.scalars(ledger.where(WarehouseOperation.kind == 'CORRECTION',
                                               WarehouseOperation.sequence > entries[0]['sequence'])):
        entry = operations.entry_data(correction)
        original_id = entry['data'].get('original_id')
        if original_id in batch_ids:
            reversals[original_id] = correction_record(entry)
    batches = [{**operation_batch(entry), 'reversal': reversals.get(entry['id'])} for entry in entries]
    original_quantity = sum(Decimal(batch['quantity']) for batch in batches)
    effective_quantity = sum((Decimal(batch['quantity']) for batch in batches if not batch['reversal']), Decimal(0))
    return dict(batches=batches, original_quantity=receiving.decimal_text(original_quantity),
                effective_quantity=receiving.decimal_text(effective_quantity), has_posting=posting is not None,
                observation=line_observation(posting, request_id, line_id, unit, batch_ids) if posting else None)


def list_receipts(db, search='', offset=0, limit=50, *, include_operations=False, channel='',
                  supplier='', category='', receipt_from='', receipt_to='', state='', sort='RECEIPT_DESC', purchase_status=''):
    receiving.ensure_schema(db)
    reversals = reversal_rows(db)
    originals = {}
    rows = []
    for model in db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == receiving.source.FACTORY)):
        originals[model.id] = model
        # Load physical split details only for the final page, not once per candidate.
        rows.append(dict(json.loads(model.payload_json), id=model.id,
            history_key='PROCUREMENT:' + model.id, receipt_origin='PROCUREMENT', facts=json.loads(model.source_json),
            quantity=model.quantity, unit=model.unit, receipt_date=model.receipt_date,
            actor_name=model.actor_name, occurred_at=model.occurred_at, reversed=model.id in reversals))
    if include_operations:
        from app.services.fabric_manual_receipts import history_record
        operations.ensure_schema(db)
        entries = {row['id']: row for row in operations.operation_entries(db, 'fabric')}
        corrections = {row['data'].get('original_id'): row for row in entries.values() if row['kind'] == 'CORRECTION'}
        rows.extend(operation_record(row, corrections.get(row['id'])) for row in entries.values()
                    if row['kind'] == 'RECEIPT' and not row['data'].get('manual_receipt_id'))
        rows.extend(history_record(row, entries, corrections) for row in entries.values() if row['kind'] == operations.MANUAL_RECEIPT_KIND)
    suppliers = sorted({row['facts'].get('supplier') for row in rows if row['facts'].get('supplier')}, key=str.casefold)
    needle = search.strip().casefold()
    def matches(row):
        return ((not channel or row['receipt_origin'] == channel
                 or (channel == 'MANUAL_ENTRY' and row['receipt_origin'] in {'PROCUREMENT', 'MANUAL'}))
            and (not supplier or row['facts'].get('supplier') == supplier)
            and (not category or row.get('material_category') == category)
            and (not receipt_from or row['receipt_date'] >= receipt_from)
            and (not receipt_to or row['receipt_date'] <= receipt_to)
            and (not state or row['reversed'] == (state == 'REVERSED'))
            and (not purchase_status or row.get('purchase_status') == purchase_status)
            and (not needle or needle in json.dumps([row['facts'], row['id'], row.get('delivery_reference', ''),
                row.get('source_line_id', ''), row.get('handover_document_id', ''), row['actor_name']], ensure_ascii=False).casefold()))
    rows = [row for row in rows if matches(row)]
    rows.sort(key=lambda row: row['history_key'])
    rows.sort(key=lambda row: row['occurred_at'], reverse=True)
    if sort != 'RECORDED_DESC':
        rows.sort(key=lambda row: row['receipt_date'], reverse=sort != 'RECEIPT_ASC')
    if sort == 'SUPPLIER':
        rows.sort(key=lambda row: row['facts'].get('supplier', '').casefold())
    items = []
    for row in rows[offset:offset + limit]:
        if row['receipt_origin'] == 'PROCUREMENT':
            row = {**receiving.receipt_data(db, originals[row['id']], reversals=reversals),
                   'history_key': row['history_key'], 'receipt_origin': 'PROCUREMENT'}
        items.append(row)
    return dict(total=len(rows), offset=offset, limit=limit, items=items,
                operations_included=include_operations, options={'suppliers': suppliers})
