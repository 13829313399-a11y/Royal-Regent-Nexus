"""One receipt for a warehouse-entered delivery whose purchase source is still unknown."""
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.core.time import business_now
from app.models.fabric_master import FabricMasterRecord
from app.models.warehouse_operations import WarehouseOperation
from app.schemas.warehouse_operations import WarehouseDocumentRequest
from app.services import fabric_master as master, fabric_receiving as receiving, warehouse_operations as wh
from app.services.fabric_receipt_pricing import evidence as price_evidence, purchase_price_reference
from app.services.fabric_supplier_identity import supplier_aliases
from app.services.material_handover_procurement import (
    guard_manual_delivery, prepare_purchase_link, purchase_choice, purchase_rows, reference_key,
)

PREFIX = 'FM-'


def _rows():
    return select(WarehouseOperation).where(WarehouseOperation.factory_id == wh.FACTORY,
        WarehouseOperation.warehouse == 'fabric')


def _existing_request(db, request_id, kind, signature):
    row = db.scalar(_rows().where(WarehouseOperation.request_id == str(request_id)))
    if row and (row.kind != kind or row.request_hash != signature):
        raise HTTPException(409, '该请求编号已用于其他内容，请先核对入库记录')
    return row


def _append(db, actor, state, identifier, kind, request_id, signature, sequence, day, body):
    row = WarehouseOperation(id=identifier, factory_id=wh.FACTORY, warehouse='fabric', kind=kind,
        request_id=str(request_id), request_hash=signature, sequence=sequence, business_date=day,
        actor_id=actor.id, actor_name=actor.display_name, occurred_at=business_now().isoformat(), payload_json=wh.dump(body))
    db.add(row)
    state.revision += 1
    db.flush()
    return wh.entry_data(row)


def read_header(db, identifier):
    row = db.scalar(_rows().where(WarehouseOperation.id == identifier, WarehouseOperation.kind == wh.MANUAL_RECEIPT_KIND))
    if not row:
        raise HTTPException(404, '找不到本仓入库记录')
    return wh.entry_data(row)


def receipt_group(db, operation_id):
    row = db.scalar(_rows().where(WarehouseOperation.id == operation_id, WarehouseOperation.kind == 'RECEIPT'))
    return json.loads(row.payload_json).get('manual_receipt_id') if row else None


def history_record(header, entries, corrections):
    body = header['data']
    ids = body['operation_ids']
    first = ids[0] if ids else ''
    purchase = entries.get(first, {}).get('data', {}).get('procurement_receipt') or {}
    correction = corrections.get(first)
    facts = {**(purchase.get('source_facts') or {}), **body['facts']}
    return dict(**{key: value for key, value in body.items() if key not in ('facts', 'operation_ids', 'supplier_id')},
        id=header['id'], history_key='MANUAL:' + header['id'], receipt_origin='MANUAL', operation_id=first,
        facts=facts, source_line_id=purchase.get('source_line_id', ''), source_revision=purchase.get('source_revision', 0),
        prior_received_quantity=None, difference_reason=purchase.get('difference_reason', ''),
        purchase_status=('LINKED' if purchase else 'PENDING') if first and not correction else '',
        purchase_price=purchase_price_reference(purchase.get('source_facts') or {}),
        actor_name=header['actor_name'], occurred_at=header['occurred_at'], stock_posted=bool(first),
        reversed=bool(correction), reversal=dict(id=correction['id'], date=correction['business_date'],
            reason=correction['data'].get('reason', ''), actor_name=correction['actor_name']) if correction else None)


def _same_delivery(receipt, reference, facts, supplier_id, aliases):
    if reference_key(receipt['reference']) != reference_key(reference) or (
            receipt['item_code'], receipt['unit']) != (facts['material_code'], facts['unit']):
        return False
    old_id = receipt.get('supplier_id')
    if supplier_id and old_id:
        return supplier_id == old_id
    return (
        receipt['counterparty'] == facts['supplier']
        or bool(supplier_id and supplier_id in aliases.get(receipt['counterparty'], ()))
        or bool(old_id and old_id in aliases.get(facts['supplier'], ()))
    )


def guard_same_receipt(db, reference, facts, day, *, supplier_id='', include_purchase=False, entries=None):
    """Prevent posting the same physical receipt through the two manual paths."""
    if not inspect(db.connection()).has_table(WarehouseOperation.__tablename__):
        return
    from app.services import material_handover_receipts as prior
    if entries is None:
        entries = {row['id']: row for row in wh.operation_entries(db, 'fabric')}
    corrections = prior.reversals_by_receipt(entries)
    aliases = supplier_aliases(db)
    links = None
    for original in prior.manual_receipts(db, entries, include_purchase=include_purchase):
        if not _same_delivery(original, reference, facts, supplier_id, aliases):
            continue
        corrected = corrections.get(original['id'])
        if not corrected:
            raise HTTPException(409, '同一供应商、物料和送货依据已有入库记录。请先核对原单；采购待核对可从原记录补关联。')
        if day < corrected['business_date']:
            raise HTTPException(409, '重新登记日期不能早于原入库的冲销日期')
        if links is None:
            links = prior.receipt_links(db)
        if original['id'] in links:
            raise HTTPException(409, '原入库已关联送货单，冲销后请在对应送货单按实重收')


def receive(db, actor, payload):
    wh.ensure_schema(db)
    master.ensure_schema(db)
    request_body = payload.model_dump(mode='json')
    signature = wh.digest([wh.MANUAL_RECEIPT_KIND, actor.id, request_body])
    try:
        state = wh.procurement.lock_factory(db)
        previous = _existing_request(db, payload.request_id, wh.MANUAL_RECEIPT_KIND, signature)
        if previous:
            from app.services.material_handover_receipts import reversals_by_receipt
            entries = {row['id']: row for row in wh.operation_entries(db, 'fabric')}
            result = history_record(entries[previous.id], entries, reversals_by_receipt(entries))
            db.rollback()
            return result
        if not payload.confirmed:
            raise HTTPException(422, '请核实本次实物数量并确认入库')
        if payload.receipt_date > business_now().date():
            raise HTTPException(422, '实际收货日期不能晚于今天')
        reference, day = payload.delivery_reference.strip(), payload.receipt_date.isoformat()
        if not reference:
            raise HTTPException(422, '请填写送货单号或手工收料依据编号')
        masters = {row.id: row for row in db.scalars(select(FabricMasterRecord).where(
            FabricMasterRecord.factory_id == wh.FACTORY, FabricMasterRecord.id.in_((payload.material_id, payload.supplier_id)))
            .execution_options(populate_existing=True))}
        item, supplier = masters.get(payload.material_id), masters.get(payload.supplier_id)
        if not item or item.kind != 'MATERIAL' or item.status != 'ACTIVE':
            raise HTTPException(422, '请选择已启用的物料')
        if not supplier or supplier.kind != 'SUPPLIER' or supplier.status != 'ACTIVE':
            raise HTTPException(422, '请选择已启用的供应商')
        if (item.revision, supplier.revision) != (payload.material_revision, payload.supplier_revision):
            raise HTTPException(409, '物料或供应商资料已变化，请刷新并重新核对')
        item_fields = json.loads(item.data_json)
        if not item_fields.get('unit') or item_fields.get('category') != payload.material_category:
            raise HTTPException(422, '请先在基础资料核对该物料的分类和单位')
        facts = dict(material_code=item.code, material_name=item.name, supplier=supplier.name, unit=item_fields['unit'])
        batches, totals, delivered, shortage, _ = receiving.prepare_receipt(db, facts, payload, supplier=supplier)
        total = totals['accepted_quantity']
        pending = payload.procurement_pending_reason.strip() if total else ''
        if total and not pending:
            raise HTTPException(422, '请填写采购待核对原因，便于之后补关联')
        entries = {row['id']: row for row in wh.operation_entries(db, 'fabric')}
        guard_same_receipt(db, reference, facts, day, supplier_id=supplier.id, include_purchase=True, entries=entries)
        guard_manual_delivery(db, reference, item.code, facts['unit'], supplier.name, operation={'receipt_supplier_id': supplier.id})
        pricing = price_evidence(total, facts['unit'], request_body)
        identifier, revision = PREFIX + uuid4().hex, max((row['sequence'] for row in entries.values()), default=0)
        body = dict(facts=facts, supplier_id=supplier.id, material_category=payload.material_category, unit=facts['unit'],
            quantity=receiving.decimal_text(total), receipt_date=day, accounting_month=day[:7], delivery_reference=reference,
            delivery_note_date=request_body['delivery_note_date'], note=payload.note.strip(), procurement_pending_reason=pending,
            delivered_quantity=receiving.decimal_text(delivered), shortage_quantity=shortage,
            receipt_lines=[], batches=[], operation_ids=[], **pricing,
            **{key: receiving.decimal_text(value) for key, value in totals.items()})
        detail_key = wh.digest([supplier.id, item.id])[:24]
        for index, batch in enumerate(batches):
            evidence = receiving.line_evidence(batch, payload.material_category, facts['unit'], shortage)
            body['receipt_lines'].append(evidence)
            if not Decimal(batch['quantity']):
                continue
            request = WarehouseDocumentRequest(factory_id=wh.FACTORY, request_id=uuid5(payload.request_id, f'receipt:{index}'),
                expected_revision=revision, kind='RECEIPT', business_date=payload.receipt_date, source_no=reference,
                source_line=f'{detail_key}:{index + 1}', item_code=item.code, item_name=item.name, unit=facts['unit'],
                counterparty=supplier.name, material_category=payload.material_category, location_id=evidence['location_id'],
                lot=evidence['dye_lot'], roll_no=evidence['roll_no'], quantity=batch['quantity'], reason=payload.note.strip()[:1000])
            part_price = price_evidence(Decimal(batch['quantity']), facts['unit'], request_body)
            operation = wh.post(db, actor, 'fabric', request, _state=state, _commit=False, _metadata={
                'manual_receipt_id': identifier, 'receipt_supplier_id': supplier.id, 'procurement_pending_reason': pending, **part_price})
            revision = operation['sequence']
            evidence['batch_id'] = operation['id']
            body['operation_ids'].append(operation['id'])
            body['batches'].append(dict(id=operation['id'], quantity=batch['quantity'], location=evidence['location'],
                location_id=evidence['location_id'], dye_lot=evidence['dye_lot'], roll_no=evidence['roll_no'], quality_status='PENDING_INSPECTION'))
        header = _append(db, actor, state, identifier, wh.MANUAL_RECEIPT_KIND, payload.request_id, signature, revision + 1, day, body)
        db.commit()
        return history_record(header, {}, {})
    except Exception:
        db.rollback()
        raise


def _pending_batch(db, group):
    header = read_header(db, group)
    body = header['data']
    entries = {row['id']: row for row in wh.operation_entries(db, 'fabric')}
    from app.services.material_handover_receipts import reversals_by_receipt
    corrected = reversals_by_receipt(entries)
    ids = body['operation_ids']
    if not ids or not body.get('procurement_pending_reason') or any(
            key in corrected or entries[key]['data'].get('procurement_receipt') for key in ids):
        raise HTTPException(409, '这笔入库已冲销、无库存或已补采购，请刷新入库记录')
    return header, entries, dict(operation_ids=ids, quantity=body['quantity'], unit=body['unit'],
        reference=body['delivery_reference'], reason=body['procurement_pending_reason'], expected_revision=header['sequence'],
        locations=list(dict.fromkeys(batch['location'] for batch in body['batches'])))


def _purchase_rows(db, header):
    body = header['data']
    return purchase_rows(db, body['supplier_id'], SimpleNamespace(item_code=body['facts']['material_code'], unit=body['unit']), supplier_aliases(db))


def purchase_review(db, group):
    header, _, batch = _pending_batch(db, group)
    context = receiving.receipt_context(db)
    choices = [purchase_choice(source, facts, receiving.receipt_progress(facts, context.get(source.id)))
               for source, facts in _purchase_rows(db, header)]
    return {**batch, 'sources': choices, 'match_status': 'REVIEW' if choices else 'NONE'}


def link_purchase(db, actor, group, payload):
    signature = wh.digest([wh.MANUAL_PURCHASE_LINK_KIND, actor.id, group, payload.model_dump(mode='json')])
    try:
        state = wh.procurement.lock_factory(db)
        previous = _existing_request(db, payload.request_id, wh.MANUAL_PURCHASE_LINK_KIND, signature)
        if previous:
            result = json.loads(previous.payload_json)['result']
            db.rollback()
            return result
        header, entries, batch = _pending_batch(db, group)
        if payload.expected_revision != batch['expected_revision'] or payload.operation_ids != batch['operation_ids']:
            raise HTTPException(409, '本批有效入库已变化，请刷新后重新核对数量')
        choice = next(((source, facts) for source, facts in _purchase_rows(db, header) if source.id == payload.purchase_source_id), None)
        if not choice:
            raise HTTPException(422, '采购来源不存在、已撤销，或供应商、物料编码和单位不一致')
        source, facts = choice
        context = receiving.receipt_context(db)
        link, outstanding = prepare_purchase_link(source, facts, context.get(source.id), payload, batch['reference'])
        if outstanding is not None and Decimal(batch['quantity']) > Decimal(outstanding) and not payload.difference_reason:
            raise HTTPException(422, '本次合计实收超过采购待收数量，请填写超收说明')
        result = {**batch, 'purchase_source_id': source.id, 'purchase_order_no': facts.get('order_no', '')}
        _append(db, actor, state, 'FL-' + uuid4().hex, wh.MANUAL_PURCHASE_LINK_KIND, payload.request_id, signature,
            max(row['sequence'] for row in entries.values()) + 1, business_now().date().isoformat(),
            dict(operation_ids=batch['operation_ids'], procurement_receipt=link, result=result, manual_receipt_id=group))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
