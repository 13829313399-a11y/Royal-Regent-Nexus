"""Resolve the purchase source of a posted receipt without moving its stock again."""
from decimal import Decimal

from fastapi import HTTPException

from app.schemas.material_handover import HandoverData, PostingLine
from app.services import material_handover as handover
from app.services.material_handover_procurement import PURCHASE_LINK_KIND, prepare_links, source_choices


def can_link_purchase(actor):
    return all(handover.can(actor, permission, handover.FACTORY, 'pmc-warehouse') for permission in
               ('fabric_operations:read', 'fabric_operations:operate', 'fabric_warehouse:read', 'fabric_warehouse:receive'))


def pending_batch(db, operation_id):
    _, entries = handover.inventory.projection(db, 'fabric')
    original = entries.get(operation_id)
    if not original or original['kind'] != 'RECEIPT' or not original['data'].get('procurement_pending_reason'):
        raise HTTPException(404, '找不到这笔采购待核对入库')
    body = original['data']
    if original.get('reversed') or body.get('procurement_receipt'):
        raise HTTPException(409, '这笔入库已冲销或已补采购，请刷新入库记录')
    keys = ('handover_document_id', 'handover_line_id', 'handover_request_id')
    identity = tuple(body.get(key) for key in keys)
    batch = [entry for entry in entries.values() if entry['kind'] == 'RECEIPT' and not entry.get('reversed')
             and tuple(entry['data'].get(key) for key in keys) == identity]
    if any(entry['data'].get('procurement_receipt') or
           entry['data'].get('procurement_pending_reason') != body['procurement_pending_reason'] for entry in batch):
        raise HTTPException(409, '本批采购归属已变化，请刷新后核对')
    quantity = handover.inventory.text(sum((Decimal(entry['data']['quantity']) for entry in batch), Decimal(0)))
    return body, dict(operation_ids=[entry['id'] for entry in batch], quantity=quantity, unit=body['unit'],
                      reference=body['source_no'], reason=body['procurement_pending_reason'],
                      locations=list(dict.fromkeys(entry['data'].get('location', '') for entry in batch)))


def purchase_review(db, actor, operation_id):
    access = handover.staff(actor)
    if not can_link_purchase(actor):
        raise HTTPException(403, '补关联采购需要布料仓收料权限')
    from app.services import fabric_manual_receipts as manual
    if group := manual.receipt_group(db, operation_id):
        return manual.purchase_review(db, group)
    body, batch = pending_batch(db, operation_id)
    row = handover.document(db, access, body['handover_document_id'])
    line_id = body['handover_line_id']
    candidates = source_choices(db, actor, row, line_id=line_id)
    return {**batch, 'expected_revision': row.revision,
            'sources': candidates['lines'][line_id], 'match_status': candidates['match_status'][line_id]}


def link_purchase(db, actor, operation_id, payload):
    access = handover.staff(actor, 'operate')
    if not can_link_purchase(actor):
        raise HTTPException(403, '补关联采购需要布料仓收料权限')
    from app.services import fabric_manual_receipts as manual
    if group := manual.receipt_group(db, operation_id):
        return manual.link_purchase(db, actor, group, payload)
    handover.inventory.procurement.lock_factory(db)
    signature = handover.request_signature(PURCHASE_LINK_KIND, operation_id, payload)
    previous = handover.replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    body, batch = pending_batch(db, operation_id)
    row = handover.document(db, access, body['handover_document_id'], lock=True)
    handover.check_revision(row, payload.expected_revision)
    if payload.operation_ids != batch['operation_ids']:
        raise HTTPException(409, '本批有效入库已变化，请刷新后重新核对数量')
    data = HandoverData.model_validate_json(row.data_json)
    # Each warehouse split retains its original quantity. The whole effective batch
    # is checked against the current purchase remainder in one transaction.
    selection = PostingLine(line_id=body['handover_line_id'], quantity=batch['quantity'],
        purchase_source_id=payload.purchase_source_id, expected_source_revision=payload.expected_source_revision,
        expected_receipt_count=payload.expected_receipt_count, difference_reason=payload.difference_reason)
    link = prepare_links(db, actor, row, data, [selection])[0]['procurement_receipt']
    row.revision += 1
    row.updated_at = handover.business_now().isoformat()
    detail = {**batch, 'line_id': body['handover_line_id'], 'procurement_receipt': link}
    result = {**batch, 'purchase_source_id': link['source_line_id'], 'purchase_order_no': link['source_facts'].get('order_no', '')}
    handover.event(db, access, row, PURCHASE_LINK_KIND, payload.request_id, signature, detail, result)
    db.commit()
    return result
