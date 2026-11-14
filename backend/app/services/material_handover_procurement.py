"""Link actual handover receipts to purchase chase without posting stock twice."""
import json
import unicodedata
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models.fabric_procurement import FabricProcurementLine
from app.models.material_handover import HandoverDocument, HandoverEvent
from app.models.warehouse_operations import WarehouseOperation
from app.services.auth import can
from app.services.fabric_procurement_parser import number
from app.services.fabric_receipt_pricing import purchase_price_reference
from app.services.fabric_supplier_identity import supplier_aliases
from app.services.warehouse_operations import MANUAL_PURCHASE_LINK_KIND

FACTORY = 'huakang-c'
PURCHASE_LINK_KIND = 'LINK_PURCHASE'


def purchase_rows(db, supplier_id, line, aliases):
    rows = db.scalars(select(FabricProcurementLine).where(
        FabricProcurementLine.factory_id == FACTORY, FabricProcurementLine.status != 'WITHDRAWN',
        FabricProcurementLine.material_code == line.item_code).order_by(FabricProcurementLine.order_no, FabricProcurementLine.id))
    return [(row, facts) for row in rows if (facts := json.loads(row.payload_json)).get('unit') == line.unit
        and aliases.get(facts.get('supplier'), set()) == {supplier_id}]


def reference_key(value):
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()


def purchase_choice(source, facts, progress, *, can_receive=True, exact=False, quantity_match=False, suggested=False):
    return dict(id=source.id, revision=source.revision,
        receipt_count=progress['receipt_count'], remaining=progress['warehouse_outstanding_quantity'],
        received=progress['warehouse_received_quantity'], order_no=facts.get('order_no', ''),
        production_no=facts.get('production_no', ''), plan_no=facts.get('plan_no', ''),
        contract_no=facts.get('contract_no', ''), supplier=facts.get('supplier', ''),
        item_code=facts.get('material_code', ''), item_name=facts.get('material_name', ''), unit=facts.get('unit', ''),
        purchase_price=purchase_price_reference(facts), ordered_quantity=facts.get('ordered_quantity'),
        ordered_quantity_matches=quantity_match, primary_match=exact, suggested=suggested,
        can_receive=can_receive and not progress['receipt_identity_review_required'] and not progress['receipt_quantity_conflict'])


def prepare_purchase_link(source, facts, context, part, reference):
    from app.services.fabric_receiving import receipt_progress
    progress = receipt_progress(facts, context)
    if source.revision != part.expected_source_revision or progress['receipt_count'] != part.expected_receipt_count:
        raise HTTPException(409, '采购来源或实收进度已变化，请刷新单据后重新核对')
    if progress['receipt_identity_review_required'] or progress['receipt_quantity_conflict']:
        raise HTTPException(409, '采购来源身份或数量存在冲突，请先核对待收料')
    return dict(source_line_id=source.id, source_revision=source.revision,
        source_facts=facts, prior_received_quantity=progress['prior_received_quantity'],
        baseline_known=progress['prior_received_quantity'] is not None,
        chase_reference=(context or {}).get('chase_reference'), starting_chase_quantity=progress['starting_chase_quantity'],
        chase_resolution=progress['chase_resolution'], delivery_reference=reference,
        difference_reason=part.difference_reason), progress['warehouse_outstanding_quantity']


def rank_purchase_choices(data, line, choices, *, known_system_ids=()):
    """Rank already scoped candidates. Only an unambiguous primary reference can preselect."""
    detail_id = reference_key(line.purchase_detail_id)
    references = {field: value for field, raw in (
        ('order_no', line.purchase_order_no or data.purchase_order_no),
        ('contract_no', line.contract_no or data.contract_no),
        ('production_no', line.production_no or data.production_no),
    ) if (value := reference_key(raw))}
    required = len(references) + bool(detail_id)
    system_id_matches = {source.id for source, _ in choices if reference_key(source.id) == detail_id}
    system_id_known = bool(system_id_matches) or detail_id in known_system_ids
    ordered = number(line.ordered_quantity)
    plan = reference_key(line.plan_no or line.production_no or data.production_no)
    style = reference_key(line.product_no or data.product_no)
    ranked = []
    for source, facts in choices:
        # An exact system ID takes precedence over any imported detail ID of the same spelling.
        id_match = bool(detail_id) and (source.id in system_id_matches if system_id_known
            else reference_key(facts.get('source_line_id')) == detail_id)
        hits = int(id_match) + sum(reference_key(facts.get(field)) == value for field, value in references.items())
        quantity_match = ordered is not None and ordered > 0 and ordered == number(facts.get('ordered_quantity'))
        hints = int(bool(plan) and plan == reference_key(facts.get('plan_no'))) + int(bool(style) and style == reference_key(facts.get('style_no')))
        ranked.append((source, facts, hits, quantity_match, hints))
    ranked.sort(key=lambda item: (item[2], item[3], item[4]), reverse=True)
    matched = sum(bool(required) and hits == required for _, _, hits, _, _ in ranked)
    if matched:
        status = 'MATCHED'
    elif not required:
        status = 'NO_REFERENCE'
    elif ranked and ranked[0][2]:
        status = 'CONFLICT'
    else:
        status = 'NOT_FOUND'
    return status, [(source, facts, bool(required) and hits == required, quantity_match)
        for source, facts, hits, quantity_match, _ in ranked], matched


def source_choices(db, actor, row, *, line_id=None):
    from app.schemas.material_handover import HandoverData
    from app.services.material_handover import supplier_identity
    from app.services.fabric_receiving import receipt_context, receipt_progress
    if not can(actor, 'fabric_warehouse:read', FACTORY, 'pmc-warehouse'):
        raise HTTPException(403, '关联待收料需要布料仓采购来源查询权限')
    data = HandoverData.model_validate_json(row.data_json)
    if data.kind != 'DELIVERY':
        return {'document_revision': row.revision, 'lines': {}, 'match_status': {}}
    aliases = supplier_aliases(db)
    supplier_id = supplier_identity(db, row, data.model_dump(mode='json'))
    context = receipt_context(db)
    explicit_ids = {reference_key(line.purchase_detail_id) for line in data.lines if line.purchase_detail_id}
    known_system_ids = set(db.scalars(select(FabricProcurementLine.id).where(
        FabricProcurementLine.factory_id == FACTORY, FabricProcurementLine.id.in_(explicit_ids)))) if explicit_ids else set()
    result, match_status = {}, {}
    can_link = can(actor, 'fabric_warehouse:receive', FACTORY, 'pmc-warehouse')
    for line in data.lines:
        if line_id is not None and line.id != line_id:
            continue
        status, ranked, matched = rank_purchase_choices(data, line, purchase_rows(db, supplier_id, line, aliases),
                                                       known_system_ids=known_system_ids)
        match_status[line.id] = status
        result[line.id] = [purchase_choice(source, facts, receipt_progress(facts, context.get(source.id)),
            can_receive=can_link, exact=exact, quantity_match=quantity_match, suggested=exact and matched == 1)
            for source, facts, exact, quantity_match in ranked
        ]
    return {'document_revision': row.revision, 'lines': result, 'match_status': match_status}


def prepare_links(db, actor, row, data, selections):
    """Check every allocation under the factory lock before the first stock write."""
    from app.services.material_handover import supplier_identity
    from app.services.fabric_receiving import receipt_context, valid_reference, quantity
    if data.kind != 'DELIVERY':
        if any(part.purchase_source_id or part.expected_source_revision is not None or part.expected_receipt_count is not None
               or part.difference_reason or part.procurement_pending_reason for part in selections):
            raise HTTPException(422, '领料出库不能扣减采购待收料')
        return [{} for part in selections]
    aliases = supplier_aliases(db)
    supplier_id = supplier_identity(db, row, data.model_dump(mode='json'))
    context = receipt_context(db)
    lines = {line.id: line for line in data.lines}
    totals, reasons, limits = defaultdict(Decimal), defaultdict(list), {}
    source_per_line = {}
    results = []
    for part in selections:
        line = lines[part.line_id]
        attribution = (part.purchase_source_id, part.procurement_pending_reason)
        if source_per_line.setdefault(line.id, attribution) != attribution:
            raise HTTPException(422, '同一送货明细的各仓位须使用同一条采购来源，或填写相同的采购待核对原因')
        if part.procurement_pending_reason:
            if not can(actor, 'fabric_warehouse:read', FACTORY, 'pmc-warehouse'):
                raise HTTPException(403, '登记采购待核对需要布料仓采购来源查询权限')
            if (part.purchase_source_id or part.expected_source_revision is not None
                    or part.expected_receipt_count is not None or part.difference_reason):
                raise HTTPException(422, '采购待核对请只填写待核对原因')
            results.append({'procurement_pending_reason': part.procurement_pending_reason})
            continue
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
        link, outstanding = prepare_purchase_link(source, facts, context.get(source.id), part, data.source_no)
        totals[source.id] += quantity(part.quantity, '本次数量')
        reasons[source.id].append(part.difference_reason)
        limits[source.id] = valid_reference(outstanding)
        results.append({'procurement_receipt': link})
    for identifier, total in totals.items():
        if limits[identifier] is not None and total > limits[identifier] and not all(reasons[identifier]):
            raise HTTPException(422, '本次合计实收超过采购待收数量，请填写超收说明')
    return results


def purchase_attributions(db):
    """Read later purchase attribution without updating the original stock operation."""
    result = {}
    inspector = inspect(db.connection())
    streams = []
    if inspector.has_table(HandoverEvent.__tablename__):
        streams.append(select(HandoverEvent.detail_json).where(
            HandoverEvent.factory_id == FACTORY, HandoverEvent.kind == PURCHASE_LINK_KIND))
    if inspector.has_table(WarehouseOperation.__tablename__):
        streams.append(select(WarehouseOperation.payload_json).where(WarehouseOperation.factory_id == FACTORY,
            WarehouseOperation.warehouse == 'fabric', WarehouseOperation.kind == MANUAL_PURCHASE_LINK_KIND))
    for raw in (raw for stream in streams for raw in db.scalars(stream)):
        event = json.loads(raw)
        for identifier in event['operation_ids']:
            result[identifier] = event['procurement_receipt']
    return result


def linked_operations(db):
    if WarehouseOperation.__tablename__ not in inspect(db.connection()).get_table_names():
        return []
    rows = list(db.scalars(select(WarehouseOperation).where(
        WarehouseOperation.factory_id == FACTORY, WarehouseOperation.warehouse == 'fabric').order_by(WarehouseOperation.sequence)))
    reversed_ids = {json.loads(row.payload_json).get('original_id') for row in rows if row.kind == 'CORRECTION'}
    links = purchase_attributions(db)
    receipts = []
    for row in rows:
        if row.kind != 'RECEIPT':
            continue
        body = json.loads(row.payload_json)
        if link := body.get('procurement_receipt') or links.get(row.id):
            receipts.append((row, body, link, row.id in reversed_ids))
    return receipts


def guard_manual_delivery(db, reference, item_code, unit, counterparty, *, source_id=None, operation=None, entries=None):
    """A confirmed portal note has one receiving path, even before its first post."""
    original_ids = set()
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
    tables = set(inspect(db.get_bind()).get_table_names())
    if HandoverDocument.__tablename__ not in tables:
        return
    if source_id:
        from app.services.fabric_receipt_corrections import PREFIX, same_reference_receipts, reversal_rows
        originals = same_reference_receipts(db, reference.strip(), source_id)
        reversed_originals = reversal_rows(db)
        if originals and all(receipt.id in reversed_originals for receipt in originals):
            original_ids = {PREFIX + receipt.id for receipt in originals}
    from app.services import material_handover as handover, material_handover_receipts as receipts
    if original_ids and HandoverEvent.__tablename__ in tables and original_ids.intersection(receipts.receipt_links(db)):
        raise HTTPException(409, '原入库已关联送货单，冲销后请在对应送货单按实重收')
    aliases = supplier_aliases(db)
    explicit_supplier = (operation or {}).get('receipt_supplier_id')
    for row in db.scalars(select(HandoverDocument).where(
            HandoverDocument.factory_id == FACTORY, HandoverDocument.status == 'CONFIRMED')):
        data = json.loads(row.data_json)
        if data['kind'] != 'DELIVERY' or reference_key(data['source_no']) != reference_key(reference):
            continue
        supplier_id = handover.supplier_identity(db, row, data)
        same_party = supplier_id == explicit_supplier if explicit_supplier else (
            supplier_id in aliases.get(counterparty, set()) or data.get('counterparty') == counterparty)
        line_ids = {line['id'] for line in data['lines'] if line['item_code'] == item_code and line['unit'] == unit}
        if not same_party or not line_ids:
            continue
        if original_ids:
            amounts, _ = handover.progress(db, row.id, entries=entries)
            if not any(amounts.get(line_id) for line_id in line_ids):
                continue  # Keep the original correction path while the delivery has no effective receipt.
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
