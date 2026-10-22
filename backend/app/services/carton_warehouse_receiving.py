"""One warehouse note, typed sources, one atomic physical receipt command."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonOrderLine, CartonOrder, CartonReceipt, CartonPurchaseOrderIssue
from app.models.carton_supplier_portal import SupplierShipment, SupplierShipmentLine
from app.models.carton_special_requests import UnifiedDelivery, SpecialShipment
from app.schemas import carton_special_requests as ss, carton_supplier_portal as ps
from app.services import carton_special_requests as special, carton_special_manual_receiving as manual
from app.services.carton_unified_deliveries import child_key, authorize, project


def receive(db, user, payload, *, refresh_actor):
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
            special.ensure_customer_operation(db, user, payload.factory_id, order.customer_code)
            regular.append((item, line, order))
        for item in payload.special_requests:
            row = special.access(db, user, payload.factory_id, item.id)
            if row.supplier_id != vendor:
                raise HTTPException(409, '所选订单供应商不一致')
            specials.append((item, row))
        digest, saved = special.replay(db, user, payload, 'WAREHOUSE_BATCH_RECEIVE')
        if saved:
            return saved
        from app.services.carton_supplier_evidence_guard import ensure_evidence_open
        ensure_evidence_open(db, payload.factory_id, vendor, payload.delivery_date)
        for model in (UnifiedDelivery, SupplierShipment, SpecialShipment, CartonReceipt):
            if db.scalar(select(model.id).where(model.factory_id == payload.factory_id,
                    model.supplier_id == vendor, model.delivery_note_no == payload.delivery_note_no)):
                raise HTTPException(409, '原送货单号已登记，请沿原送货单核实，不能重复入库')
        formal_sources, replacement_links = [], {}
        from app.services import carton_supplier_portal as portal
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
            else:
                portal.executable(db, order, issue.id)
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
            if manual.pending_deliveries(db, row)[0]:
                raise HTTPException(409, '所选样板或杂单已有待收或冲销待更正送货，请沿原单验收')
            papers = {line.id: line for line in special.lines(db, row)}
            totals = special.state_counts(db, row)[3]
            if len({line.line_id for line in item.lines}) != len(item.lines):
                raise HTTPException(422, '本次收料纸品不能重复')
            for line in item.lines:
                if line.line_id not in papers or line.received_quantity > papers[line.line_id].quantity - totals.get(line.line_id, Decimal(0)):
                    raise HTTPException(409, '样板或杂单纸品来源或剩余数量已变化')
        formal = None
        formal_acceptance = []
        if formal_sources:
            formal = SupplierShipment(id=special.uid('CSS-'), factory_id=payload.factory_id, supplier_id=vendor,
                delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
                status='SENT', revision=1, request_id=child_key(payload.request_id, 'FORMAL'), fingerprint=digest,
                created_by=user.id, created_at=special.core.now_text())
            db.add(formal); db.flush()
            for index, (item, line, order, issue) in enumerate(formal_sources):
                replacement = replacement_links.get(line.id)
                source = SupplierShipmentLine(id=f'{formal.id}-{index+1:03d}', factory_id=payload.factory_id,
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
        for item, row in specials:
            command = ss.ManualReceive(factory_id=payload.factory_id, request_id=child_key(payload.request_id, row.id),
                expected_revision=row.revision, delivery_note_no=payload.delivery_note_no,
                delivery_date=payload.delivery_date, acceptance_date=payload.acceptance_date, lines=item.lines)
            shipment, acceptance = manual.build_shipment(db, user, row, command)
            children.append((row.id, row.revision, shipment.id, acceptance))
        group = UnifiedDelivery(id=special.uid('CUD-'), factory_id=payload.factory_id, supplier_id=vendor,
            delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
            children_json=special.pack(dict(formal_id=formal.id if formal else '', special_ids=[value[2] for value in children], source_origin='WAREHOUSE_MANUAL')),
            request_key=payload.request_id, fingerprint=digest, created_by=user.id, created_at=special.core.now_text())
        db.add(group); db.flush()
        if formal:
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
        result = dict(delivery_id=group.id, receipts=[special.core.receipt_out(db, db.get(CartonReceipt, identifier)).model_dump(mode='json') for identifier in ids if identifier])
        event = special.core._audit(db, user, payload.factory_id, 'WAREHOUSE_BATCH_RECEIVED', 'carton_unified_delivery', group.id,
            dict(fingerprint=digest, response=result))
        event.id = special.replay_id(user, payload)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
