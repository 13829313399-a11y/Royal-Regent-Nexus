"""One warehouse note, typed sources, one atomic physical receipt command."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrderLine, CartonOrder, CartonPurchaseOrderIssue, CartonReceipt
from app.models.carton_supplier_portal import SupplierShipment, SupplierShipmentLine
from app.models.carton_special_requests import UnifiedDelivery, SpecialShipment, SpecialShipmentLine
from app.schemas import carton_special_requests as ss, carton_supplier_portal as ps
from app.services import carton_special_requests as special, carton_special_manual_receiving as manual
from app.services import carton_supplier_portal as portal
from app.services.carton_source_links import MANUAL_PAPERS_ADDED, delivery_children
from app.services.carton_unified_deliveries import child_key, authorize, descriptors, project


def note_record(db, model, payload, vendor):
    return db.scalar(select(model).where(model.factory_id == payload.factory_id, model.supplier_id == vendor,
        model.delivery_note_no == payload.delivery_note_no).limit(1))


def formal_shipment(db, user, payload, vendor, digest):
    shipment = SupplierShipment(id=special.uid('CSS-'), factory_id=payload.factory_id, supplier_id=vendor,
        delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
        status='SENT', revision=1, request_id=child_key(payload.request_id, 'FORMAL'), fingerprint=digest,
        created_by=user.id, created_at=special.core.now_text())
    db.add(shipment)
    db.flush()
    return shipment


def link_legacy_receipt(db, user, payload, receipt, digest, papers):
    """Represent an already posted manual note as the first acceptance, without reposting it."""
    from app.services import carton_shipment_receiving as receiving, carton_supplier_receipt_link as receipt_link
    from app.services.carton_replenishment_receipts import receipt_links, legacy_review_lines
    from app.services.carton_supplier_settlement import receipt_guard
    replacement_links = receipt_links(db, receipt.factory_id)
    if (receipt.status != 'POSTED' or receipt.import_batch_id or not papers or
            any(not paper.order_line_id or paper.received_quantity <= 0 or paper.id in replacement_links for paper in papers) or
            legacy_review_lines(db, receipt.factory_id, [paper.order_line_id for paper in papers]) or
            receiving.owner(db, receipt.factory_id, receipt.id)):
        raise HTTPException(409, '该送货单有历史记录需核实，请在收料历史查看原单后处理')
    special.core.ensure_receipt_operation(db, user, receipt.factory_id, papers)
    receipt_guard(db, receipt)
    creation = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == receipt.factory_id,
        CartonAuditEvent.entity_id == receipt.id, CartonAuditEvent.event_type == 'RECEIPT_DRAFT_CREATED'))
    shipment = formal_shipment(db, user, payload, receipt.supplier_id, digest)
    acceptance, delivered = [], {}
    for index, paper in enumerate(papers, 1):
        line = db.get(CartonOrderLine, paper.order_line_id)
        order = db.get(CartonOrder, line.order_id)
        issued_ids = set(db.scalars(select(CartonAuditEvent.entity_id).where(
            CartonAuditEvent.factory_id == receipt.factory_id, CartonAuditEvent.event_type == 'PURCHASE_ORDER_ISSUED',
            CartonAuditEvent.sequence < (creation.sequence if creation else 0),
            CartonAuditEvent.entity_id.in_(select(CartonPurchaseOrderIssue.id).where(CartonPurchaseOrderIssue.order_id == order.id)))))
        issue = next((issue for issue in special.core._purchase_order_issues(db, order.id) if issue.id in issued_ids
            and any(row.get('id') == line.id for row in special.core._purchase_order_snapshot(issue).get('lines', []))), None)
        if not issue or order.supplier_id != receipt.supplier_id:
            raise HTTPException(409, '原收料缺少可核实的采购来源，请在收料历史核对原单')
        source = SupplierShipmentLine(id=f'{shipment.id}-{index:03d}', factory_id=receipt.factory_id, shipment_id=shipment.id,
            order_line_id=line.id, issue_id=issue.id, quantity=paper.delivered_quantity,
            snapshot_json=special.pack(dict(order_no=order.order_no, contract_no=paper.contract_no,
                customer_po=special.core._purchase_order_snapshot(issue).get('customer_po', order.customer_po),
                customer_name=paper.customer_name, item_no=paper.item_no, child_no=f'{order.order_no}/{line.line_no:02d}',
                source_origin='WAREHOUSE_MANUAL', supplier_price_confirmed=False, warehouse_unit_price=str(paper.unit_price),
                dimension_unit=next(row.get('dimension_unit', '') for row in special.core._purchase_order_snapshot(issue)['lines'] if row.get('id') == line.id),
                **{key: str(getattr(paper, key)) for key in ('packaging_type', 'paper_quality', 'specification', 'unit', 'unit_price', 'currency')})))
        db.add(source)
        delivered[source.id] = str(source.quantity)
        acceptance.append(dict(shipment_line_id=source.id, **{key: str(getattr(paper, key)) for key in receiving.QUANTITIES}))
    day = receipt_link.acceptance_day(receipt)
    shipment.receipt_id = receipt.id
    shipment.status = 'RECEIVED'
    shipment.confirmed_by = receipt.confirmed_by
    shipment.confirmed_at = receipt.confirmed_at
    shipment.acceptance_json = special.pack(dict(acceptance_date=day, lines=acceptance))
    special.core._audit(db, user, receipt.factory_id, receipt_link.EVENT, 'supplier_shipment', shipment.id,
        dict(receipt_id=receipt.id, warehouse_legacy_lines=dict(zip(delivered, [paper.id for paper in papers])), delivery_quantities=delivered,
            acceptance=dict(acceptance_date=day, lines=acceptance)))
    db.flush()
    return shipment


def receive(db, user, payload, *, refresh_actor, commit=True):
    try:
        user = special.locked_actor(db, user, payload.factory_id)
        user = refresh_actor()
        vendor = authorize(db, user, payload.factory_id)
        regular, specials = [], []
        # Recheck all current source scopes even when replaying a saved command.
        for item in payload.formal_lines:
            line = db.get(CartonOrderLine, item.order_line_id)
            order = db.get(CartonOrder, line.order_id) if line else None
            if not order or line.factory_id != payload.factory_id or order.factory_id != payload.factory_id or order.supplier_id != vendor or order.deleted_at:
                raise HTTPException(404, '未找到本厂可收料纸品')
            from app.services.carton_customer_assignment import ensure_receipt_customer
            ensure_receipt_customer(db, user, payload.factory_id, order.customer_code)
            regular.append((item, line, order))
        for item in payload.special_requests:
            row = special.access(db, user, payload.factory_id, item.id, receiving=True)
            if row.supplier_id != vendor:
                raise HTTPException(409, '所选订单供应商不一致')
            specials.append((item, row))
        digest, saved = special.replay(db, user, payload, 'WAREHOUSE_BATCH_RECEIVE')
        if saved:
            return saved
        from app.services.carton_supplier_evidence_guard import ensure_evidence_open
        ensure_evidence_open(db, payload.factory_id, vendor, payload.delivery_date)
        from app.services.carton_supplier_manual_evidence import DOCUMENT_EVENT
        group = note_record(db, UnifiedDelivery, payload, vendor)
        formal, previous_specials, old_receipt_ids = None, [], set()
        legacy = None
        if group:
            if delivery_children(db, group).get('source_origin') != 'WAREHOUSE_MANUAL' or db.scalar(select(CartonAuditEvent.id).where(
                    CartonAuditEvent.factory_id == payload.factory_id, CartonAuditEvent.entity_id == group.id,
                    CartonAuditEvent.event_type == DOCUMENT_EVENT)):
                raise HTTPException(409, '此送货单已有供应商原单，请在供应商送货记录核实并沿原单验收')
            if group.delivery_date != payload.delivery_date.isoformat():
                raise HTTPException(409, '此送货单号已登记，送货日期与原单不同，请先核对纸面送货单')
            formal, previous_specials, _, _, _ = descriptors(db, user, payload.factory_id, group.id)
            original = project(db, user, payload.factory_id, group.id)
            if original['status'] != 'RECEIVED' or original['requires_correction']:
                raise HTTPException(409, '此送货单仍有待收或待更正的纸品，请先处理原单')
            old_receipt_ids = {value.get('id') or value.get('receipt_id') for value in original['receipts']}
        else:
            if note_record(db, SupplierShipment, payload, vendor) or note_record(db, SpecialShipment, payload, vendor):
                raise HTTPException(409, '此送货单已登记，请在供应商送货记录核实并沿原单验收')
            legacy = note_record(db, CartonReceipt, payload, vendor)
            if legacy and legacy.delivery_date != payload.delivery_date.isoformat():
                raise HTTPException(409, '此送货单号已登记，送货日期与原单不同，请先核对纸面送货单')

        legacy_papers = special.core._receipt_lines(db, legacy.id) if legacy else []
        previous_formal, _ = portal._shipment_sources(db, formal) if formal else ([], [])
        recorded_formal = {paper.order_line_id for paper in [*previous_formal, *legacy_papers]}
        recorded_special = set(db.scalars(select(SpecialShipmentLine.request_line_id).where(
            SpecialShipmentLine.shipment_id.in_([shipment.id for shipment in previous_specials])))) if previous_specials else set()
        if (recorded_formal.intersection(line.id for _, line, _ in regular) or
                recorded_special.intersection(line.line_id for item, _ in specials for line in item.lines)):
            raise HTTPException(409, '所选纸品已在此送货单登记。请只勾选尚未登记的纸品；数量或仓位录错请在收料历史处理原记录')
        formal_sources, replacement_links = [], {}
        for item, line, order in regular:
            if payload.order_revisions.get(order.order_no) != order.revision:
                raise HTTPException(409, '所选正单已变化，请刷新后核实')
            if order.status not in {'PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'}:
                raise HTTPException(409, '正单须已确认锁定且仍有待收数量')
            issue = portal.latest_issue(db, order)
            if not issue:
                raise HTTPException(409, '正单缺少原采购版本，请先核实采购单')
            from app.services.carton_replenishment_receipts import select_link
            effective = item.received_quantity - item.damaged_quantity - item.rejected_quantity - item.unusable_quantity
            link = select_link(db, payload.factory_id, line, effective, item.replenishment_issue_id)
            if link:
                from app.services.carton_replenishment_supplier import validate_issue, sources
                issue = validate_issue(db, order, link['replenishment_issue_id'])
                source = next(source for source in sources(db, order) if source['issue_id'] == issue.id)
                capacity = next(paper for paper in source['lines'] if paper['id'] == line.id)['remaining_to_ship']
                if item.delivered_quantity > Decimal(capacity):
                    raise HTTPException(409, '本次送货数量超过所选补单版本的可送额度，请分清普通采购与补单')
                replacement_links[line.id] = link
            # Physical receipt uses the locked demand. Supplier dispatch alone
            # requires the latest change to be issued and agreed.
            from app.services.carton_material_correction import guard_lines
            guard_lines(db, payload.factory_id, [line.id])
            outstanding = portal.outstanding(db, [line.id]).get(line.id, Decimal(0))
            if outstanding > 0:
                raise HTTPException(409, '所选纸品已有待收或冲销待更正送货，请沿原单验收')
            if item.delivered_quantity > line.required_quantity - portal.fulfilled_by_line(db, [line.id]).get(line.id, 0) - portal._pending_received_by_line(db, [line.id]).get(line.id, 0):
                raise HTTPException(409, '本次送货数量超过当前待收需求')
            formal_sources.append((item, line, order, issue))
        for item, row in specials:
            if item.expected_revision != row.revision or not special.flags(db, user, row, False)['can_manual_receive']:
                raise HTTPException(409, '样板或杂单已变化，请核对锁单状态和版本')
            shipment_ids, delivery_ids = manual.pending_deliveries(db, row, {line.line_id for line in item.lines})
            if shipment_ids:
                raise HTTPException(409, dict(code='EXISTING_DELIVERY_PENDING',
                    message='所选样板或杂单纸品已有待收或冲销待更正送货，请沿原单验收',
                    shipment_ids=shipment_ids, delivery_ids=delivery_ids))
            papers = {line.id: line for line in special.lines(db, row)}
            totals = special.state_counts(db, row)[3]
            if len({line.line_id for line in item.lines}) != len(item.lines):
                raise HTTPException(422, '本次收料纸品不能重复')
            for line in item.lines:
                if line.line_id not in papers or line.received_quantity > papers[line.line_id].quantity - totals.get(line.line_id, Decimal(0)):
                    raise HTTPException(409, '样板或杂单纸品来源或剩余数量已变化')
        if legacy:
            formal = link_legacy_receipt(db, user, payload, legacy, digest, legacy_papers)
            previous_formal, _ = portal._shipment_sources(db, formal)
            old_receipt_ids.add(legacy.id)
        new_formal = None
        formal_acceptance = []
        if formal_sources:
            if len(previous_formal) + len(formal_sources) > 200:
                raise HTTPException(422, '同一送货单的正单纸品不能超过 200 行，请核对原送货明细')
            if formal is None:
                formal = new_formal = formal_shipment(db, user, payload, vendor, digest)
            formal.status = 'SENT'
            formal_acceptance.extend(ps.ReceiveLine(shipment_line_id=paper.id, received_quantity=0, unit_price=0)
                for paper in previous_formal)
            for index, (item, line, order, issue) in enumerate(formal_sources, len(previous_formal) + 1):
                replacement = replacement_links.get(line.id)
                source = SupplierShipmentLine(id=f'{formal.id}-{index:03d}', factory_id=payload.factory_id,
                    shipment_id=formal.id, order_line_id=line.id, issue_id=issue.id, quantity=item.delivered_quantity,
                    snapshot_json=special.pack(dict(order_no=order.order_no, contract_no=order.contract_no,
                        customer_po=order.customer_po, customer_name=order.customer_name, item_no=order.item_no,
                        child_no=f'{order.order_no}/{line.line_no:02d}', source_origin='WAREHOUSE_MANUAL',
                        supplier_price_confirmed=False, warehouse_unit_price=str(item.unit_price) if item.unit_price is not None else None,
                        **(dict(replenishment_issue_id=issue.id, replenishment_document_no=issue.document_no,
                            responsibility=replacement['responsibility']) if replacement else {}),
                        **{key: str(getattr(line, key)) for key in ('packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit', 'unit_price', 'currency')})))
                db.add(source)
                price = Decimal(0) if replacement and replacement['responsibility'] == 'SUPPLIER' else item.unit_price if item.unit_price is not None else Decimal(0)
                formal_acceptance.append(ps.ReceiveLine(shipment_line_id=source.id, received_quantity=item.received_quantity,
                    damaged_quantity=item.damaged_quantity, rejected_quantity=item.rejected_quantity,
                    unusable_quantity=item.unusable_quantity, unit_price=price, price_action='PENDING' if item.unit_price is None or price == 0 and item.zero_price_kind != 'FREE' else 'PROPOSE',
                    zero_price_kind=('FREE' if item.zero_price_kind == 'FREE' else 'PENDING') if price == 0 else None, price_reason='仓库依据实际到货代录，待供应商核实价格',
                    difference_reason=item.feedback_note or '仓库按实际到货核实数量', paper_quality=item.paper_quality,
                    specification=item.specification, replenishment_issue_id=issue.id if replacement else None,
                    location_allocations=item.location_allocations))
        children = []
        new_special_ids = []
        special_by_request = {shipment.request_id: shipment for shipment in previous_specials}
        for item, row in specials:
            command = ss.ManualReceive(factory_id=payload.factory_id, request_id=child_key(payload.request_id, row.id),
                expected_revision=row.revision, delivery_note_no=payload.delivery_note_no,
                delivery_date=payload.delivery_date, acceptance_date=payload.acceptance_date, lines=item.lines)
            existing = special_by_request.get(row.id)
            if existing and existing.version_id != row.current_version_id:
                raise HTTPException(409, '该样板或杂单的采购版本已变化，请核对原送货单及本次到货来源')
            shipment, acceptance = manual.build_shipment(db, user, row, command, shipment=existing)
            if existing is None:
                new_special_ids.append(shipment.id)
            children.append((row.id, row.revision, shipment.id, acceptance))
        if group is None:
            group = UnifiedDelivery(id=special.uid('CUD-'), factory_id=payload.factory_id, supplier_id=vendor,
                delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
                children_json=special.pack(dict(formal_id=formal.id if formal else '', special_ids=new_special_ids, source_origin='WAREHOUSE_MANUAL')),
                request_key=payload.request_id, fingerprint=digest, created_by=user.id, created_at=special.core.now_text())
            db.add(group)
        elif new_formal or new_special_ids:
            special.core._audit(db, user, payload.factory_id, MANUAL_PAPERS_ADDED, 'carton_unified_delivery', group.id,
                dict(formal_id=new_formal.id if new_formal else '', special_ids=new_special_ids))
        db.flush()
        if formal_acceptance:
            portal.receive_shipment(db, user, formal.id, ps.ShipmentReceive(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, 'FORMAL_RECEIVE'), expected_revision=formal.revision,
                acceptance_date=payload.acceptance_date, remaining_action='WAIT', new_delivery_confirmation=True,
                split_confirmation=payload.split_confirmation, lines=formal_acceptance), commit=False)
            db.flush()
        for identifier, revision, shipment_id, acceptance in children:
            special.receive(db, user, identifier, shipment_id, ss.Receive(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, shipment_id), expected_revision=revision,
                acceptance_date=payload.acceptance_date, lines=acceptance), commit=False)
            db.flush()
        projected = project(db, user, payload.factory_id, group.id)
        ids = list(dict.fromkeys(value.get('id') or value.get('receipt_id') for value in projected['receipts']))
        result = dict(delivery_id=group.id, receipts=[special.core.receipt_out(db, db.get(CartonReceipt, identifier)).model_dump(mode='json')
            for identifier in ids if identifier and identifier not in old_receipt_ids])
        event = special.core._audit(db, user, payload.factory_id, 'WAREHOUSE_BATCH_RECEIVED', 'carton_unified_delivery', group.id,
            dict(fingerprint=digest, response=result))
        event.id = special.replay_id(user, payload)
        if commit:
            db.commit()
        else:
            db.flush()
        return result
    except Exception:
        db.rollback()
        raise
