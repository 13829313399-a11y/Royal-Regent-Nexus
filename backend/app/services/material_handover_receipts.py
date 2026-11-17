"""Attribute an existing manual receipt to a delivery line without posting stock."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models.fabric_receiving import FabricReceipt
from app.models.material_handover import HandoverEvent
from app.schemas.material_handover import HandoverData
from app.services import material_handover as handover
from app.services.fabric_procurement_parser import digest
from app.services.fabric_receipt_corrections import PREFIX
from app.services.fabric_supplier_identity import supplier_aliases
from app.services.material_handover_procurement import reference_key

LINK_KIND = 'LINK_RECEIPT'
UNLINK_KIND = 'UNLINK_RECEIPT'
REVIEW_DAYS = 7


def receipt_links(db, document_ids=None):
    if not inspect(db.connection()).has_table(HandoverEvent.__tablename__):
        return {}
    query = select(HandoverEvent.document_id, HandoverEvent.kind, HandoverEvent.detail_json).where(
        HandoverEvent.factory_id == handover.FACTORY, HandoverEvent.kind.in_((LINK_KIND, UNLINK_KIND)))
    if document_ids is not None:
        query = query.where(HandoverEvent.document_id.in_(document_ids))
    links, revoked = [], set()
    for document_id, kind, raw in db.execute(query):
        detail = json.loads(raw)
        if kind == LINK_KIND:
            links.append({**detail, 'document_id': document_id})
        else:
            revoked.add(detail['link_id'])
    return {link['receipt_id']: link for link in links if link['id'] not in revoked}


def revoked_receipt_links(db, document_id):
    return [json.loads(raw) for raw in db.scalars(select(HandoverEvent.detail_json).where(
        HandoverEvent.factory_id == handover.FACTORY, HandoverEvent.document_id == document_id,
        HandoverEvent.kind == UNLINK_KIND).order_by(HandoverEvent.revision.desc()))]


def reversals_by_receipt(entries):
    return {entry['data']['original_id']: entry for entry in entries.values()
            if entry['kind'] == 'CORRECTION' and entry['data'].get('original_id')}


def manual_receipts(db, entries, *, include_purchase=True):
    for entry in entries.values():
        body = entry['data']
        if entry['kind'] == handover.inventory.MANUAL_RECEIPT_KIND:
            ids = body['operation_ids']
            if not ids:
                continue
            purchase = entries.get(ids[0], {}).get('data', {}).get('procurement_receipt', {})
            facts = purchase.get('source_facts', {})
            yield dict(id=ids[0], reference=body['delivery_reference'], date=entry['business_date'],
                counterparty=body['facts']['supplier'], supplier_id=body['supplier_id'], item_code=body['facts']['material_code'],
                unit=body['unit'], quantity=body['quantity'], production_no=facts.get('production_no', ''),
                contract_no=facts.get('contract_no', ''), order_no=facts.get('order_no', ''),
                purchase_ids=(purchase.get('source_line_id'), facts.get('source_line_id')),
                parts=[{'lot': part['dye_lot'], 'roll_no': part['roll_no'], 'location': part['location']} for part in body['batches']])
            continue
        if entry['kind'] != 'RECEIPT' or body.get('handover_document_id') or body.get('manual_receipt_id'):
            continue
        yield dict(id=entry['id'], reference=body.get('source_no', ''), date=entry['business_date'],
            counterparty=body.get('counterparty', ''), supplier_id='', item_code=body['item_code'], unit=body['unit'],
            quantity=body['quantity'], production_no=body.get('production_no', ''),
            contract_no=body.get('contract_no', ''), order_no='', purchase_ids=(), parts=[{
                'lot': body.get('lot', ''), 'roll_no': body.get('roll_no', ''), 'location': body.get('location', ''),
            }])
    if not include_purchase:
        return
    for row in db.scalars(select(FabricReceipt).where(FabricReceipt.factory_id == handover.FACTORY)):
        if Decimal(row.quantity) <= 0:
            continue
        facts, body = json.loads(row.source_json), json.loads(row.payload_json)
        supplier = (body.get('master_references') or {}).get('supplier') or {}
        parts = [{'lot': part.get('dye_lot', ''), 'roll_no': part.get('roll_no', ''), 'location': part.get('location', '')}
                 for part in (body.get('receipt_lines') or []) if part.get('batch_id')]
        yield dict(id=PREFIX + row.id, reference=body.get('delivery_reference', row.delivery_reference),
            date=row.receipt_date, counterparty=facts.get('supplier', ''), supplier_id=supplier.get('id', ''),
            item_code=facts.get('material_code', ''), unit=row.unit, quantity=row.quantity, parts=parts,
            production_no=facts.get('production_no', ''), contract_no=facts.get('contract_no', ''),
            order_no=facts.get('order_no', ''), purchase_ids=(row.source_line_id, facts.get('source_line_id')))


def match_candidate(receipt, data, line, supplier_id, aliases, outstanding, link):
    exact = reference_key(receipt['reference']) == reference_key(data.source_no)
    party = receipt['counterparty']
    ids = {receipt['supplier_id']} if receipt['supplier_id'] else aliases.get(party, set())
    if (ids and supplier_id not in ids) or (not ids and party != data.counterparty):
        return None
    ambiguous_supplier = len(ids) > 1
    lots = {reference_key(part['lot']) for part in receipt['parts'] if part['lot']}
    rolls = {reference_key(part['roll_no']) for part in receipt['parts'] if part['roll_no']}
    lot, roll = reference_key(line.lot), reference_key(line.roll_no)
    batch_conflict = bool((lot and lots and lots != {lot}) or (roll and rolls and rolls != {roll}))
    order_match = any(value and reference_key(value) == reference_key(receipt[key])
                      for key, value in (('order_no', line.purchase_order_no or data.purchase_order_no),
                                         ('production_no', line.production_no or data.production_no),
                                         ('contract_no', line.contract_no or data.contract_no)))
    detail_id = reference_key(line.purchase_detail_id)
    detail_match = detail_id and detail_id in map(reference_key, receipt['purchase_ids'])
    nearby = abs((date.fromisoformat(receipt['date']) - data.document_date).days) <= REVIEW_DAYS
    batch_clue = (roll and roll in rolls) or ((order_match or detail_match) and lot and lot in lots)
    if not exact and (batch_conflict or ambiguous_supplier or link or not (nearby or batch_clue)):
        return None
    reason = ''
    if link:
        reason = f"原入库已关联送货单 {link['document_reference']}"
    elif ambiguous_supplier:
        reason = '旧记录的供应商身份待核对'
    elif batch_conflict:
        reason = '原入库缸号或卷号与本行不符'
    elif Decimal(receipt['quantity']) > outstanding:
        reason = '原实收超过本行剩余数量'
    if link:
        blocks_posting = exact and reference_key(link['document_reference']) == reference_key(data.source_no)
    else:
        blocks_posting = exact and not (ambiguous_supplier or batch_conflict) and (not reason or bool(roll and roll in rolls))
    return {key: receipt[key] for key in ('id', 'reference', 'date', 'quantity', 'parts', 'production_no',
                                         'contract_no', 'order_no')} | {
        'exact_reference': exact,
        'blocks_posting': blocks_posting,
        'can_link': not reason, 'reason': reason,
    }


def prior_receipts(db, row, data, entries, amounts, links, *, line_ids=None, posting_date=None):
    """Block compatible exact originals and require review of other plausible receipts."""
    if row.status != 'CONFIRMED' or data.kind != 'DELIVERY' or not data.document_date:
        return {}
    lines = defaultdict(list)
    outstanding = {}
    for line in data.lines:
        if line_ids is not None and line.id not in line_ids:
            continue
        remaining = Decimal(line.quantity) - amounts.get(line.id, Decimal(0))
        if remaining > 0:
            outstanding[line.id] = remaining
            lines[line.item_code, line.unit].append(line)
    if not lines:
        return {}
    aliases = supplier_aliases(db)
    supplier_id = handover.supplier_identity(db, row, data.model_dump(mode='json'))
    reversals = reversals_by_receipt(entries)
    candidates = defaultdict(list)
    for receipt in manual_receipts(db, entries):
        linked = links.get(receipt['id'])
        if linked and linked['document_id'] == row.id:
            continue
        reversal = reversals.get(receipt['id'])
        if reversal and not posting_date:
            continue
        for line in lines[receipt['item_code'], receipt['unit']]:
            candidate = match_candidate(receipt, data, line, supplier_id, aliases, outstanding[line.id], linked)
            if not candidate:
                continue
            if reversal:
                if candidate['blocks_posting'] and posting_date < reversal['business_date']:
                    raise HTTPException(409, '重新收料日期不能早于原入库的冲销日期，请核对实际日期')
            else:
                candidates[line.id].append(candidate)
    result = {}
    for line_id, items in candidates.items():
        items.sort(key=lambda item: (item['exact_reference'], item['can_link'], item['date'], item['id']), reverse=True)
        result[line_id] = {'items': items, 'review_token': digest(items)}
    return result


def can_review(actor):
    return handover.can(actor, 'fabric_warehouse:read', handover.FACTORY, 'pmc-warehouse')


def guard_reposting(db, actor, row, data, entries, amounts, links, selections, payload):
    candidates = prior_receipts(db, row, data, entries, amounts, links,
                                line_ids={part.line_id for part in selections}, posting_date=payload.business_date.isoformat())
    if candidates and not can_review(actor):
        raise HTTPException(403, '已有可能对应的入库记录，请由有布料仓收料记录查询权限的仓管核对')
    for line_id, review in candidates.items():
        if any(item['blocks_posting'] for item in review['items']):
            raise HTTPException(409, '这张送货单已有手工入库，请先核对并关联原实收')
        if payload.manual_receipt_reviews.get(line_id) != review['review_token']:
            raise HTTPException(409, '请刷新并核对可能对应的旧入库，关联原实收或确认本批为新到货')


def link_receipt(db, actor, identifier, payload):
    access = handover.staff(actor, 'operate')
    handover.ensure_schema(db)
    if not can_review(actor):
        raise HTTPException(403, '补关联需要布料仓收料记录查询权限')
    handover.inventory.procurement.lock_factory(db)
    signature = handover.request_signature(LINK_KIND, identifier, payload)
    previous = handover.replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = handover.document(db, access, identifier, lock=True)
    handover.check_revision(row, payload.expected_revision)
    data = HandoverData.model_validate_json(row.data_json)
    if row.status != 'CONFIRMED' or data.kind != 'DELIVERY':
        raise HTTPException(409, '只能为已确认送货单关联实收')
    from app.services.material_handover_suppliers import supplier
    supplier(db, handover.supplier_identity(db, row, data.model_dump(mode='json')), active=False)
    _, entries = handover.inventory.projection(db, 'fabric')
    links = receipt_links(db)
    if payload.receipt_id in links:
        raise HTTPException(409, '这笔原入库已有关联，请刷新送货单')
    amounts, _ = handover.progress(db, identifier, entries=entries, links=links.values())
    reviews = prior_receipts(db, row, data, entries, amounts, links, line_ids={payload.line_id})
    candidate = next((item for item in reviews.get(payload.line_id, {}).get('items', [])
                      if item['id'] == payload.receipt_id), None)
    if not candidate or not candidate['can_link']:
        raise HTTPException(409, candidate['reason'] if candidate else '原入库已变化或与本行不符，请刷新后核对')
    detail = dict(id='MHRL-' + uuid4().hex, receipt_id=candidate['id'], line_id=payload.line_id,
                  document_reference=data.source_no,
                  quantity=candidate['quantity'], business_date=candidate['date'],
                  reference=candidate['reference'], actor_name=access.name)
    links[payload.receipt_id] = {**detail, 'document_id': row.id}
    row.revision += 1
    row.updated_at = handover.business_now().isoformat()
    db.flush()
    result = handover.output(db, row, with_receipt_observations=True, with_receipt_review=True,
                             entries=entries, manual_links=links)
    handover.event(db, access, row, LINK_KIND, payload.request_id, signature, detail, result)
    db.commit()
    return result


def unlink_receipt(db, actor, identifier, payload):
    access = handover.staff(actor, 'operate')
    handover.ensure_schema(db)
    if not can_review(actor):
        raise HTTPException(403, '撤回关联需要布料仓收料记录查询权限')
    handover.inventory.procurement.lock_factory(db)
    signature = handover.request_signature(UNLINK_KIND, identifier, payload)
    previous = handover.replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = handover.document(db, access, identifier, lock=True)
    handover.check_revision(row, payload.expected_revision)
    links = receipt_links(db)
    link = next((link for link in links.values() if link['document_id'] == identifier and link['id'] == payload.link_id), None)
    if row.status != 'CONFIRMED' or not link:
        raise HTTPException(409, '这笔关联已变化，请刷新单据后核对')
    _, entries = handover.inventory.projection(db, 'fabric')
    amounts, _ = handover.progress(db, identifier, entries=entries, links=links.values())
    if amounts.get(link['line_id'], Decimal(0)) != Decimal(payload.expected_processed):
        raise HTTPException(409, '本行实收已变化，请刷新后重新核对撤回数量')
    del links[link['receipt_id']]
    row.revision += 1
    row.updated_at = handover.business_now().isoformat()
    detail = dict(link_id=link['id'], line_id=link['line_id'], reference=link['reference'], quantity=link['quantity'],
                  business_date=link['business_date'], revoked_at=row.updated_at, revoked_by=access.name, reason=payload.reason)
    db.flush()
    result = handover.output(db, row, with_receipt_observations=True, with_receipt_review=True,
                             entries=entries, manual_links=links)
    result['revoked_receipt_links'] = [detail, *result.get('revoked_receipt_links', [])]
    handover.event(db, access, row, UNLINK_KIND, payload.request_id, signature, detail, result)
    db.commit()
    return result
