"""Explicit PMC source evidence for a cutting promise, without stock allocation."""
import json
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import inspect, select

from app.models.fabric_procurement import FabricProcurementLine
from app.services import cutting_ops as c, fabric_procurement as procurement
from app.services.auth import can


def source_access(user):
    return can(user, 'fabric_warehouse:read', c.FACTORY, 'pmc-warehouse')


def require_source_access(user):
    c.require(source_access(user), '关联采购明细需要华康 C 布料仓采购查询权限', 403)


def source_query():
    return select(FabricProcurementLine).where(FabricProcurementLine.factory_id == c.FACTORY)


def matches(line, facts, demand, reference, supplier):
    return (line.order_no == reference and line.supplier == supplier
            and line.material_code == demand['material']['code'] and facts.get('unit') == demand['unit'])


def batch_signature(batches):
    return sha256(json.dumps(batches, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def display_batches(data):
    batches = data.get('batches', [])
    links = data.get('purchase_links')
    if (not links or links['requisition_version'] != (data.get('requisition') or {}).get('version')
            or links['batch_signature'] != batch_signature(batches)):
        return batches
    return [dict(batch, purchase_source=dict(links['sources'][str(index)])) if str(index) in links['sources'] else batch
            for index, batch in enumerate(batches)]


def include_detail_numbers(db, data_items):
    refs = [batch['purchase_source'] for data in data_items if data
            for batch in data.get('batches', []) if batch.get('purchase_source') and not batch['purchase_source'].get('detail_no')]
    ids = sorted({ref['id'] for ref in refs})
    if not ids or not inspect(db.connection()).has_table(FabricProcurementLine.__tablename__):
        return
    labels = {}
    for start in range(0, len(ids), 200):
        for line in db.scalars(source_query().where(FabricProcurementLine.id.in_(ids[start:start + 200]))):
            labels[line.id, line.revision] = json.loads(line.payload_json).get('source_line_id')
    for ref in refs:
        if label := labels.get((ref['id'], ref['revision'])):
            ref['detail_no'] = label


def save_batches(db, data, batches, previous):
    plain = [b.model_dump(mode='json', exclude={'purchase_source'}) for b in batches]
    sources = {str(index): b.purchase_source.model_dump(mode='json') for index, b in enumerate(batches) if b.purchase_source}
    data['batches'] = plain
    if sources:
        prior = {(ref['id'], ref['revision']): ref.get('detail_no') for batch in previous if (ref := batch.get('purchase_source'))}
        for ref in sources.values():
            if label := prior.get((ref['id'], ref['revision'])):
                ref['detail_no'] = label
        include_detail_numbers(db, [{'batches': [{'purchase_source': ref} for ref in sources.values()]}])
        data['purchase_links'] = dict(requisition_version=data['requisition']['version'],
                                      batch_signature=batch_signature(plain), sources=sources)
    else:
        data.pop('purchase_links', None)


def candidates(db, data, row_index, reference, supplier):
    demand = next((r for r in (data.get('requisition') or {}).get('lines', [])
                   if r['row'] == row_index and r.get('purchase_mode') != 'no_purchase'), None)
    c.require(demand is not None and not data.get('purchase_reconciliation_required'), '请选择当前有效的采购需求行', 409)
    procurement.ensure_schema(db)
    query = source_query().where(FabricProcurementLine.status != 'WITHDRAWN',
        FabricProcurementLine.order_no == reference, FabricProcurementLine.supplier == supplier,
        FabricProcurementLine.material_code == demand['material']['code']).order_by(FabricProcurementLine.id)
    choices = []
    for line in db.scalars(query.execution_options(yield_per=25)):
        facts = json.loads(line.payload_json)
        if matches(line, facts, demand, reference, supplier):
            choices.append(dict(id=line.id, revision=line.revision, detail_no=facts.get('source_line_id', ''),
                                production_no=line.production_no, quantity=facts.get('ordered_quantity'), unit=demand['unit']))
        if len(choices) > 50:
            c.require(False, '匹配的采购明细过多，请先由 PMC 核对采购来源', 422)
    return {'items': choices}


def validate_sources(db, user, requisition, batches, previous):
    preserved = {(b['row'], b['purchase_reference'], b['supplier'], b['purchase_source']['id'], b['purchase_source']['revision'])
                 for b in previous if b.get('purchase_source')}
    linked = [batch for batch in batches if batch.purchase_source is not None and (
        batch.row, batch.purchase_reference, batch.supplier, batch.purchase_source.id, batch.purchase_source.revision) not in preserved]
    if not linked:
        return
    require_source_access(user)
    procurement.ensure_schema(db)
    demands = {row['row']: row for row in requisition['lines']}
    ids = sorted({batch.purchase_source.id for batch in linked})
    lines = {}
    # Share the purchase-source writer lock. Imports can update several
    # lines in workbook order, so acquire the factory lock before reading them.
    procurement.lock_factory(db)
    for start in range(0, len(ids), 200):
        query = source_query().where(FabricProcurementLine.id.in_(ids[start:start + 200]))
        lines.update((line.id, line) for line in db.scalars(query))
    for batch in linked:
        ref = batch.purchase_source
        line = lines.get(ref.id)
        c.require(line is not None and line.status != 'WITHDRAWN' and line.revision == ref.revision,
                  '采购明细已变化或失效，请重新查找并选择', 409)
        c.require(matches(line, json.loads(line.payload_json), demands[batch.row], batch.purchase_reference, batch.supplier),
                  '采购明细的单号、供应商、物料编码或单位与本批交期不符', 422)


def progress(db, line_id, data):
    from app.services import cutting_materials, fabric_receiving

    refs = [b for b in display_batches(data) if b.get('purchase_source')]
    if not refs:
        return {'sources': [], 'cutting': []}
    demands = {row['row']: row for row in data['requisition']['lines']}
    keys = sorted({(b['row'], b['purchase_source']['id']) for b in refs})
    by_key = {(b['row'], b['purchase_source']['id']): b for b in refs}
    ids = sorted({identifier for _, identifier in keys})
    fabric_receiving.ensure_schema(db)
    lines = {}
    for start in range(0, len(ids), 200):
        lines.update((line.id, line) for line in db.scalars(
            source_query().where(FabricProcurementLine.id.in_(ids[start:start + 200]))))
    context = fabric_receiving.receipt_context(db, source_ids=ids)
    sources = []
    for row, identifier in keys:
        batch = by_key[row, identifier]
        line = lines.get(identifier)
        facts = json.loads(line.payload_json) if line else {}
        item = dict(row=row, id=identifier, order_no=batch['purchase_reference'], unit=demands[row]['unit'],
                    linked_revision=batch['purchase_source']['revision'], current_revision=line.revision if line else None,
                    status='unavailable', detail_no='', received_quantity=None, outstanding_quantity=None)
        if line and line.status != 'WITHDRAWN':
            if matches(line, facts, demands[row], batch['purchase_reference'], batch['supplier']):
                receipts = fabric_receiving.receipt_progress(facts, context.get(identifier))
                if receipts['receipt_identity_review_required']:
                    item['status'] = 'identity_changed'
                else:
                    item.update(status='active', detail_no=facts.get('source_line_id') or '',
                                received_quantity=receipts['warehouse_received_quantity'],
                                outstanding_quantity=receipts['warehouse_outstanding_quantity'])
            else:
                item['status'] = 'identity_changed'
        sources.append(item)

    # Signed and returned quantities cover this order's current BOM row. They
    # may include existing stock, so never attribute these totals to a PO.
    signed, returned = defaultdict(Decimal), defaultdict(Decimal)
    bom = data['bom']
    for total in cutting_materials.read(db, line_id)['totals']:
        if (total['row'] in demands and total['dispatch_id'] == data['dispatch_id']
                and total['bom_id'] == bom['id'] and total['bom_version'] == bom['version']
                and total['unit'] == demands[total['row']]['unit']):
            signed[total['row']] += Decimal(total['received_quantity'])
            returned[total['row']] += Decimal(total['returned_quantity'])
    cutting = [dict(row=row, unit=demands[row]['unit'], signed_quantity=str(signed[row]),
                    returned_quantity=str(returned[row])) for row in sorted({row for row, _ in keys})]
    return {'sources': sources, 'cutting': cutting}
