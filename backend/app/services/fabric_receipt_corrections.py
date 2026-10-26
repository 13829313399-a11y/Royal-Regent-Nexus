"""Whole original receipt reversals recorded in the existing immutable ledger."""
import copy
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.models.fabric_receiving import FabricReceipt
from app.models.warehouse_operations import WarehouseOperation

FACTORY = 'huakang-c'
PREFIX = 'FR-'
ZERO_RECEIPT_MESSAGE = '零入库差异单没有库存可冲销，请走差异处理'


def ensure_stock_reversible(db, receipt_id):
    receipt = db.scalar(select(FabricReceipt).where(FabricReceipt.factory_id == FACTORY, FabricReceipt.id == receipt_id))
    if receipt is None:
        raise HTTPException(404, '找不到本仓入库记录')
    if Decimal(receipt.quantity) == 0:
        raise HTTPException(422, ZERO_RECEIPT_MESSAGE)
    return receipt


def reversal_rows(db):
    if WarehouseOperation.__tablename__ not in inspect(db.get_bind()).get_table_names():
        return {}
    result = {}
    for row in db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.kind == 'CORRECTION').order_by(WarehouseOperation.sequence)):
        body = json.loads(row.payload_json)
        identifier = body.get('procurement_original_receipt_id')
        if identifier and body.get('original_id') == PREFIX + identifier:
            result[identifier] = row
    return result


def display_reference(receipt):
    return json.loads(receipt.payload_json).get('delivery_reference', receipt.delivery_reference)


def same_reference_receipts(db, reference, source_id=None):
    query = select(FabricReceipt).where(FabricReceipt.factory_id == FACTORY)
    if source_id:
        query = query.where(FabricReceipt.source_line_id == source_id)
    return [receipt for receipt in db.scalars(query) if display_reference(receipt) == reference]


def apply_original_reversal(stock, entries, entry):
    body, ref = entry['data'], entry['data']['original_id']
    identifier = ref.removeprefix(PREFIX)
    if not body.get('confirmed') or not body.get('reason', '').strip():
        raise HTTPException(422, '请填写原因并确认整单冲销原采购实收')
    if any(row['kind'] == 'CORRECTION' and row['data'].get('original_id') == ref for row in entries.values()):
        raise HTTPException(409, '原入库单已冲销，请查看冲销记录，不能重复办理')
    batches = [batch for batch in stock.values() if batch.get('receipt_origin', {}).get('id') == identifier
        and batch['id'] == batch.get('original_batch_id')]
    if not batches:
        raise HTTPException(404, '找不到本仓原始入库单及完整批次')
    origin = batches[0]['receipt_origin']
    ids = {batch['id'] for batch in batches}
    if entry['business_date'] < origin['receipt_date']:
        raise HTTPException(422, '冲销日期不能早于原收货日期')
    for later in entries.values():
        if later['data'].get('batch_id') in ids:
            if later['kind'] != 'LOCATION_BIND':
                raise HTTPException(409, '原入库批次已有出库、调仓、质检等后续业务，不能直接整单冲销')
            if entry['business_date'] < later['business_date']:
                raise HTTPException(409, '冲销日期早于原批次最近的仓位核对日期')
    if sum((Decimal(batch['inbound_quantity']) for batch in batches), Decimal(0)) != Decimal(origin['quantity']):
        raise HTTPException(409, '原入库批次与整单数量不一致，请先核对原证据')
    for batch in batches:
        if Decimal(batch['quantity']) != Decimal(batch['inbound_quantity']):
            raise HTTPException(409, '原批次库存已变化，不能整单冲销')
    first = batches[0]
    for key in ('item_code', 'item_name', 'unit', 'material_category', 'counterparty', 'production_no'):
        body[key] = first.get(key, '')
    body.update(quantity=origin['quantity'], reversed_kind='RECEIPT', source_system='PROCUREMENT_RECEIVING',
        source_no=origin['delivery_reference'], source_line=origin['source_line_id'],
        procurement_original_receipt_id=identifier, procurement_original_source_id=origin['source_line_id'],
        receipt_snapshot=copy.deepcopy(origin), location=' / '.join(sorted({batch['location'] for batch in batches})))
    body.update(origin.get('pricing', {}))
    body['price_note'] = origin.get('pricing', {}).get('price_basis', '')
    for batch in batches:
        batch.update(quantity='0', inbound_quantity='0', last_business_date=entry['business_date'])
    entries[entry['id']] = entry


def preview(db, receipt_id):
    from app.services import warehouse_operations as operations
    operations.ensure_schema(db)
    operations.procurement.lock_factory(db)
    receipt = db.scalar(select(FabricReceipt).where(FabricReceipt.factory_id == FACTORY, FabricReceipt.id == receipt_id))
    if receipt is None:
        raise HTTPException(404, '找不到本仓入库记录')
    stock, entries = operations.projection(db, 'fabric')
    revision = max((row['sequence'] for row in entries.values()), default=0)
    from app.core.time import business_now
    probe = dict(id='preview', kind='CORRECTION', sequence=revision + 1, business_date=business_now().date().isoformat(),
        data=dict(original_id=PREFIX + receipt_id, reason='preview', confirmed=True))
    blocked = ''
    try:
        ensure_stock_reversible(db, receipt_id)
        apply_original_reversal(copy.deepcopy(stock), copy.deepcopy(entries), probe)
    except HTTPException as error:
        blocked = error.detail
    return dict(receipt_id=receipt_id, expected_revision=revision, quantity=receipt.quantity, unit=receipt.unit,
        delivery_reference=display_reference(receipt), can_reverse=not blocked, blocked_reason=blocked)
