"""One read model for actual receipts, retaining each posting system's identity."""
import json

from sqlalchemy import select

from app.models.fabric_receiving import FabricReceipt
from app.services import fabric_receiving as receiving
from app.services import warehouse_operations as operations
from app.services.fabric_receipt_corrections import reversal_rows


def operation_record(entry, reversal):
    body = entry['data']
    purchase = body.get('procurement_receipt') or {}
    facts = dict(purchase.get('source_facts') or {})
    facts.update(material_code=body.get('item_code', ''), material_name=body.get('item_name', ''),
                 supplier=body.get('counterparty', ''))
    facts['production_no'] = body.get('production_no') or facts.get('production_no', '')
    facts.setdefault('order_no', '')
    facts['contract_no'] = facts.get('contract_no') or body.get('handover_contract_no', '')
    line = body.get('handover_line_snapshot') or {}
    return dict(id=entry['id'], history_key='OPERATION:' + entry['id'], operation_id=entry['id'],
        receipt_origin='HANDOVER' if body.get('handover_document_id') else 'MANUAL',
        handover_document_id=body.get('handover_document_id', ''),
        source_line_id=purchase.get('source_line_id') or body.get('source_line', ''),
        source_revision=purchase.get('source_revision', 0), source_version=body.get('source_version', ''),
        facts=facts, quantity=body['quantity'], unit=body['unit'], prior_received_quantity=None,
        receipt_date=entry['business_date'], accounting_month=entry['business_date'][:7],
        delivery_reference=body.get('source_no', ''), material_category=body.get('material_category', ''),
        difference_reason=purchase.get('difference_reason', ''), note=body.get('reason', ''),
        actor_name=entry['actor_name'], occurred_at=entry['occurred_at'], stock_posted=True,
        unit_price=line.get('unit_price', ''), price_unit=line.get('price_unit', ''),
        currency=line.get('currency', ''), price_basis='原送货单参考价格；本页不推算金额或应付金额',
        reversed=bool(reversal), reversal=dict(id=reversal['id'], date=reversal['business_date'],
            reason=reversal['data'].get('reason', ''), actor_name=reversal['actor_name']) if reversal else None,
        batches=[dict(id=entry['id'], quantity=body['quantity'], location=body.get('location', ''),
            dye_lot=body.get('lot', ''), roll_no=body.get('roll_no', ''), quality_status='PENDING_INSPECTION')])


def list_receipts(db, search='', offset=0, limit=50, *, include_operations=False, channel='',
                  supplier='', category='', receipt_from='', receipt_to='', state='', sort='RECEIPT_DESC'):
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
        operations.ensure_schema(db)
        entries = [operations.entry_data(row) for row in operations.documents(db, 'fabric')]
        corrections = {row['data'].get('original_id'): row for row in entries if row['kind'] == 'CORRECTION'}
        rows.extend(operation_record(row, corrections.get(row['id'])) for row in entries if row['kind'] == 'RECEIPT')
    suppliers = sorted({row['facts'].get('supplier') for row in rows if row['facts'].get('supplier')}, key=str.casefold)
    needle = search.strip().casefold()
    def matches(row):
        return ((not channel or row['receipt_origin'] == channel)
            and (not supplier or row['facts'].get('supplier') == supplier)
            and (not category or row.get('material_category') == category)
            and (not receipt_from or row['receipt_date'] >= receipt_from)
            and (not receipt_to or row['receipt_date'] <= receipt_to)
            and (not state or row['reversed'] == (state == 'REVERSED'))
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
