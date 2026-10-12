"""Link actual handover receipts to purchase chase without posting stock twice."""
import json
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models.fabric_master import FabricMasterRecord, FabricMasterChange
from app.models.fabric_procurement import FabricProcurementLine
from app.models.fabric_receiving import FabricReceipt
from app.models.material_handover import HandoverDocument, HandoverSupplierBinding
from app.models.warehouse_operations import WarehouseOperation
from app.services.auth import can

FACTORY = 'huakang-c'


def supplier_aliases(db):
    aliases = defaultdict(set)
    suppliers = list(db.scalars(select(FabricMasterRecord).where(
        FabricMasterRecord.factory_id == FACTORY, FabricMasterRecord.kind == 'SUPPLIER')))
    ids = {row.id for row in suppliers}
    for row in suppliers:
        aliases[row.name].add(row.id)
    for row in db.scalars(select(FabricMasterChange).where(FabricMasterChange.factory_id == FACTORY)):
        if row.record_id in ids:
            for value in (row.before_json, row.after_json):
                name = json.loads(value).get('name')
                if name:
                    aliases[name].add(row.record_id)
    if HandoverSupplierBinding.__tablename__ in inspect(db.get_bind()).get_table_names():
        for row in db.scalars(select(HandoverSupplierBinding).where(HandoverSupplierBinding.factory_id == FACTORY)):
            name = json.loads(row.supplier_snapshot_json).get('name')
            if name:
                aliases[name].add(row.supplier_id)
    return aliases


def purchase_rows(db, supplier_id, line, aliases):
    rows = db.scalars(select(FabricProcurementLine).where(
        FabricProcurementLine.factory_id == FACTORY, FabricProcurementLine.status != 'WITHDRAWN',
        FabricProcurementLine.material_code == line.item_code).order_by(FabricProcurementLine.order_no, FabricProcurementLine.id))
    return [(row, facts) for row in rows if (facts := json.loads(row.payload_json)).get('unit') == line.unit
        and aliases.get(facts.get('supplier'), set()) == {supplier_id}]


def suggested(data, line, facts):
    refs = ((line.contract_no or data.contract_no, ('contract_no',)),
            (line.production_no or data.production_no, ('production_no', 'plan_no')),
            (line.product_no or data.product_no, ('style_no',)))
    return all(not value or value in {facts.get(key, '') for key in keys} for value, keys in refs)


def source_choices(db, actor, row):
    from app.schemas.material_handover import HandoverData
    from app.services.material_handover import supplier_identity
    from app.services.fabric_receiving import receipt_context, receipt_progress
    if not can(actor, 'fabric_warehouse:read', FACTORY, 'pmc-warehouse'):
        raise HTTPException(403, '关联待收料需要布料仓采购来源查询权限')
    data = HandoverData.model_validate_json(row.data_json)
    if data.kind != 'DELIVERY':
        return {'document_revision': row.revision, 'lines': {}}
    aliases = supplier_aliases(db)
    supplier_id = supplier_identity(db, row, data.model_dump(mode='json'))
    context = receipt_context(db)
    result = {}
    for line in data.lines:
        result[line.id] = [dict(id=source.id, revision=source.revision,
            receipt_count=progress['receipt_count'], remaining=progress['warehouse_outstanding_quantity'],
            received=progress['warehouse_received_quantity'], order_no=facts.get('order_no', ''),
            production_no=facts.get('production_no', ''), plan_no=facts.get('plan_no', ''),
            contract_no=facts.get('contract_no', ''), supplier=facts.get('supplier', ''),
            item_code=facts.get('material_code', ''), item_name=facts.get('material_name', ''), unit=facts.get('unit', ''),
            can_receive=not progress['receipt_identity_review_required'] and not progress['receipt_quantity_conflict']
                and can(actor, 'fabric_warehouse:receive', FACTORY, 'pmc-warehouse'),
            suggested=suggested(data, line, facts))
            for source, facts in purchase_rows(db, supplier_id, line, aliases)
            for progress in [receipt_progress(facts, context.get(source.id))]]
    return {'document_revision': row.revision, 'lines': result}


def prepare_links(db, actor, row, data, selections):
    """Check every allocation under the factory lock before the first stock write."""
    from app.services.material_handover import supplier_identity
    from app.services.fabric_receiving import receipt_context, receipt_progress, valid_reference, quantity
    if data.kind != 'DELIVERY':
        if any(part.purchase_source_id or part.expected_source_revision is not None or part.expected_receipt_count is not None
               or part.difference_reason for part in selections):
            raise HTTPException(422, '领料出库不能扣减采购待收料')
        return [{} for part in selections]
    aliases = supplier_aliases(db)
    supplier_id = supplier_identity(db, row, data.model_dump(mode='json'))
    context = receipt_context(db)
    lines = {line.id: line for line in data.lines}
    totals, reasons, limits = defaultdict(Decimal), defaultdict(list), {}
    results = []
    for part in selections:
        line = lines[part.line_id]
        guard_prior_manual_receipt(db, data, line, supplier_id, aliases)
        choices = {source.id: (source, facts) for source, facts in purchase_rows(db, supplier_id, line, aliases)}
        if not part.purchase_source_id:
            if choices:
                raise HTTPException(422, '请为本次实收选择对应采购待收明细，避免库存与欠货不同步')
            if part.expected_source_revision is not None or part.expected_receipt_count is not None or part.difference_reason:
                raise HTTPException(422, '没有采购来源时不能提交采购版本或超收说明')
            results.append({})
            continue
        if not all(can(actor, permission, FACTORY, 'pmc-warehouse') for permission in
                   ('fabric_warehouse:read', 'fabric_warehouse:receive')):
            raise HTTPException(403, '同步采购待收料需要布料仓收料权限')
        if part.purchase_source_id not in choices:
            raise HTTPException(422, '采购来源不存在、已撤销，或供应商、物料编码和单位不一致')
        source, facts = choices[part.purchase_source_id]
        progress = receipt_progress(facts, context.get(source.id))
        if source.revision != part.expected_source_revision or progress['receipt_count'] != part.expected_receipt_count:
            raise HTTPException(409, '采购来源或实收进度已变化，请刷新单据后重新核对')
        if progress['receipt_identity_review_required'] or progress['receipt_quantity_conflict']:
            raise HTTPException(409, '采购来源身份或数量存在冲突，请先核对待收料')
        if db.scalar(select(FabricReceipt.id).where(FabricReceipt.factory_id == FACTORY,
                FabricReceipt.source_line_id == source.id, FabricReceipt.delivery_reference == data.source_no)):
            raise HTTPException(409, '这张送货单已在采购收料入口登记，请核对原入库记录，不能重复入库')
        totals[source.id] += quantity(part.quantity, '本次数量')
        reasons[source.id].append(part.difference_reason)
        limits[source.id] = valid_reference(progress['warehouse_outstanding_quantity'])
        original = context.get(source.id, {})
        results.append({'procurement_receipt': dict(source_line_id=source.id, source_revision=source.revision,
            source_facts=facts, prior_received_quantity=progress['prior_received_quantity'],
            baseline_known=progress['prior_received_quantity'] is not None,
            chase_reference=original.get('chase_reference'), starting_chase_quantity=progress['starting_chase_quantity'],
            chase_resolution=progress['chase_resolution'], delivery_reference=data.source_no,
            difference_reason=part.difference_reason)})
    for identifier, total in totals.items():
        if limits[identifier] is not None and total > limits[identifier] and not all(reasons[identifier]):
            raise HTTPException(422, '本次合计实收超过采购待收数量，请填写超收说明')
    return results


def guard_prior_manual_receipt(db, data, line, supplier_id, aliases):
    def same_item(body, *, procurement=False):
        party = body.get('supplier' if procurement else 'counterparty', '')
        return body.get('material_code' if procurement else 'item_code') == line.item_code and body.get('unit') == line.unit \
            and (supplier_id in aliases.get(party, set()) or party == data.counterparty)
    from app.services.fabric_receipt_corrections import same_reference_receipts
    for receipt in same_reference_receipts(db, data.source_no):
        if same_item(json.loads(receipt.source_json), procurement=True):
            raise HTTPException(409, '这张送货单已在采购收料入口登记，请核对原入库记录，不能重复入库')
    for operation in db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.kind == 'RECEIPT')):
        body = json.loads(operation.payload_json)
        if not body.get('handover_document_id') and body.get('source_no') == data.source_no and same_item(body):
            raise HTTPException(409, '这张送货单已手工登记实收，请核对原入库记录，不能从送货单入口重复入库')


def linked_operations(db):
    if WarehouseOperation.__tablename__ not in inspect(db.get_bind()).get_table_names():
        return []
    rows = list(db.scalars(select(WarehouseOperation).where(
        WarehouseOperation.factory_id == FACTORY, WarehouseOperation.warehouse == 'fabric').order_by(WarehouseOperation.sequence)))
    reversed_ids = {json.loads(row.payload_json).get('original_id') for row in rows if row.kind == 'CORRECTION'}
    return [(row, body, body['procurement_receipt'], row.id in reversed_ids)
        for row in rows if row.kind == 'RECEIPT' and (body := json.loads(row.payload_json)).get('procurement_receipt')]


def guard_manual_delivery(db, reference, item_code, unit, counterparty, *, source_id=None, operation=None, entries=None):
    """A confirmed portal note has one receiving path, even before its first post."""
    if operation is not None and entries is not None:
        identity = ('source_system', 'source_no', 'source_line', 'item_code', 'unit', 'counterparty')
        originals = [entry for entry in entries.values() if entry['kind'] == 'RECEIPT'
            and not entry['data'].get('handover_document_id')
            and all(entry['data'].get(key, '') == operation.get(key, '') for key in identity)]
        if originals and all(entry.get('reversed') for entry in originals):
            original_ids = {entry['id'] for entry in originals}
            if any(entry['kind'] == 'CORRECTION' and entry['data'].get('original_id') in original_ids
                   and operation['business_date'] < entry['business_date'] for entry in entries.values()):
                raise HTTPException(409, '更正重收日期不能早于原入库的冲销日期')
            return  # Retain the original standalone manual path and replacement lineage.
    if HandoverDocument.__tablename__ not in inspect(db.get_bind()).get_table_names():
        return
    if source_id:
        from app.services.fabric_receipt_corrections import same_reference_receipts, reversal_rows
        originals = same_reference_receipts(db, reference.strip(), source_id)
        reversed_originals = reversal_rows(db)
        if originals and all(receipt.id in reversed_originals for receipt in originals):
            return  # Continue the original manual receipt's correction path.
    from app.services.material_handover import supplier_identity
    aliases = supplier_aliases(db)
    for row in db.scalars(select(HandoverDocument).where(
            HandoverDocument.factory_id == FACTORY, HandoverDocument.status == 'CONFIRMED')):
        data = json.loads(row.data_json)
        if data['kind'] != 'DELIVERY' or data['source_no'] != reference.strip():
            continue
        supplier_id = supplier_identity(db, row, data)
        same_party = supplier_id in aliases.get(counterparty, set()) or data.get('counterparty') == counterparty
        if same_party and any(line['item_code'] == item_code and line['unit'] == unit for line in data['lines']):
            raise HTTPException(409, '这张送货单已由供应商上传，请从送货单入库或扫码入口办理，不能重复手工登记')


def guard_withdrawal(db, line_ids):
    if line_ids and any(link['source_line_id'] in line_ids for _, _, link, _ in linked_operations(db)):
        raise HTTPException(409, '本次导入涉及已登记送货单实收的来源，不能撤销；请保留采购与入库证据')


def advance_corrected_source(db, body, entries):
    """Invalidate old procurement dialogs when an effective receipt is reversed."""
    link = {'source_line_id': body['procurement_original_source_id']} if body.get('procurement_original_source_id') else entries[body['original_id']]['data'].get('procurement_receipt')
    if not link:
        return
    source = db.scalar(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == FACTORY,
        FabricProcurementLine.id == link['source_line_id']).execution_options(populate_existing=True))
    if source is None:
        raise HTTPException(409, '关联采购来源缺失，请先核对原入库证据')
    source.revision += 1
    body['corrected_procurement_source'] = {'id': source.id, 'revision': source.revision}
