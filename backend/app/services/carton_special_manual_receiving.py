"""Warehouse-recorded physical notes, using the existing shipment/receipt ledgers."""
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_special_requests import UnifiedDelivery, SpecialShipment, SpecialShipmentLine
from app.models.carton_supplier_portal import SupplierShipment
from app.models.carton_procurement import CartonReceipt
from app.schemas import carton_special_requests as schema
from app.services import carton_special_requests as special


def pending_deliveries(db, row):
    shipped, _, consumed, _, _ = special.state_counts(db, row)
    shipment_ids = sorted({paper.shipment_id for paper in shipped
        if paper.quantity > consumed.get(paper.id, Decimal(0))})
    groups = list(db.scalars(select(UnifiedDelivery).where(
        UnifiedDelivery.factory_id == row.factory_id, UnifiedDelivery.supplier_id == row.supplier_id)))
    delivery_ids = []
    grouped = set()
    for group in groups:
        matching = set(json.loads(group.children_json)["special_ids"]) & set(shipment_ids)
        if matching:
            delivery_ids.append(group.id)
            grouped.update(matching)
    delivery_ids.extend("SPECIAL:" + identifier for identifier in shipment_ids if identifier not in grouped)
    return shipment_ids, delivery_ids


def receive(db, user, identifier, payload: schema.ManualReceive):
    try:
        user = special.locked_actor(db, user, payload.factory_id)
        row = special.access(db, user, payload.factory_id, identifier)
        if not special.can_receive(user, row.factory_id):
            raise HTTPException(403, "手动收料须同时具备本厂收料及库存权限")
        if special.portal.fixed_supplier(db, row.factory_id).id != row.supplier_id:
            raise HTTPException(409, "订单供应商与当前厂区供应商不一致，请先核实")
        digest, saved = special.replay(db, user, payload, "MANUAL_RECEIVE", identifier)
        if saved:
            return saved
        special.require_revision(row, payload)
        if not special.flags(db, user, row, False)["can_manual_receive"]:
            raise HTTPException(409, "请先确认并锁定样板或杂单，再登记实际收料")
        shipment_ids, delivery_ids = pending_deliveries(db, row)
        if shipment_ids:
            raise HTTPException(409, dict(code="EXISTING_DELIVERY_PENDING",
                message="已有待收或冲销待更正送货，请沿原送货单核实，不能另建手动收料",
                shipment_ids=shipment_ids, delivery_ids=delivery_ids))
        if len({item.line_id for item in payload.lines}) != len(payload.lines):
            raise HTTPException(422, "本次收料纸品不能重复")
        for model in (UnifiedDelivery, SupplierShipment, SpecialShipment, CartonReceipt):
            if db.scalar(select(model.id).where(model.factory_id == row.factory_id,
                model.supplier_id == row.supplier_id, model.delivery_note_no == payload.delivery_note_no)):
                raise HTTPException(409, "供应商原送货单号已登记，请核对原单")
        papers = {paper.id: paper for paper in special.lines(db, row)}
        totals = special.state_counts(db, row)[3]
        for item in payload.lines:
            paper = papers.get(item.line_id)
            if paper is None:
                raise HTTPException(422, "收料纸品不属于当前订单")
            # Warehouse records physical acceptance or rejection independently
            # of printing approval; the source mark state stays in the snapshot.
            if item.received_quantity > paper.quantity - totals.get(paper.id, Decimal(0)):
                raise HTTPException(409, "本次收料数量超过订单剩余需求，请先核实需求")
        shipment, receipt_lines = build_shipment(db, user, row, payload)
        group = UnifiedDelivery(id=special.uid("CUD-"), factory_id=row.factory_id, supplier_id=row.supplier_id,
            delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
            children_json=special.pack({"formal_id": "", "special_ids": [shipment.id],
                "source_origin": "WAREHOUSE_MANUAL"}), request_key=payload.request_id,
            fingerprint=digest, created_by=user.id, created_at=special.core.now_text())
        db.add(group)
        db.flush()
        special.core._audit(db, user, row.factory_id, "SPECIAL_MANUAL_DELIVERY_RECORDED",
            "carton_special_request", row.id, {"shipment_id": shipment.id, "delivery_id": group.id,
                "source_origin": "WAREHOUSE_MANUAL", "supplier_price_confirmed": False})
        from app.services.carton_unified_deliveries import child_key
        special.receive(db, user, row.id, shipment.id, schema.Receive(factory_id=row.factory_id,
            request_id=child_key(payload.request_id, "MANUAL_RECEIVE"), expected_revision=row.revision,
            acceptance_date=payload.acceptance_date, lines=receipt_lines), commit=False)
        response = special.finish(db, user, payload, row, "MANUAL_RECEIVE", digest, commit=False,
            response_extra={"manual_delivery_id": group.id})
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def build_shipment(db, user, row, payload):
    """Trusted builder after the caller validates and locks every source."""
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    ensure_evidence_open(db, row.factory_id, row.supplier_id, payload.delivery_date)
    papers = {paper.id: paper for paper in special.lines(db, row)}
    shipment = SpecialShipment(id=special.uid("CSSP-"), factory_id=row.factory_id,
        supplier_id=row.supplier_id, request_id=row.id, version_id=row.current_version_id,
        delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
        created_by=user.id, created_at=special.core.now_text())
    db.add(shipment)
    db.flush()
    receipt_lines = []
    manifest = special.snapshot(db, row)["material_manifest"]
    from app.services.carton_special_stock import replacement
    stock_source = replacement(db, row)
    free_replacement = bool(stock_source and stock_source["responsibility"] == "SUPPLIER")
    for item in payload.lines:
        paper = papers[item.line_id]
        # The physical ledger requires a cost value. Zero is only a pending
        # stock-cost placeholder; the payable price remains unknown.
        stock_price = item.unit_price if item.unit_price is not None else Decimal(0)
        if free_replacement and stock_price != 0:
            raise HTTPException(422, "供应商责任补单免费，不可填收费单价")
        source = SpecialShipmentLine(id=special.uid("CSSPL-"), factory_id=row.factory_id,
            shipment_id=shipment.id, request_line_id=paper.id, quantity=item.received_quantity,
            snapshot_json=special.pack(special.line_out(paper) | {
                "unit_price": str(stock_price), "pricing_kind": "FREE" if free_replacement else "PENDING_QUOTE",
                "source_origin": "WAREHOUSE_MANUAL", "supplier_price_confirmed": False,
                "warehouse_unit_price": str(item.unit_price) if item.unit_price is not None else None,
                "customer_code": row.customer_code, "customer_name": row.customer_name,
                "kind": row.kind, "request_no": row.request_no,
                "material_manifest": [file for file in manifest if file["line_id"] == paper.id]}))
        db.add(source)
        receipt_lines.append(schema.ReceiveLine(shipment_line_id=source.id,
            received_quantity=item.received_quantity, damaged_quantity=item.damaged_quantity,
            rejected_quantity=item.rejected_quantity, unusable_quantity=item.unusable_quantity,
            location_allocations=item.location_allocations, unit_price=item.unit_price,
            price_action="PENDING" if item.unit_price is None else "PROPOSE",
            zero_price_kind="FREE" if free_replacement else "PENDING" if item.unit_price is None else "FREE" if item.unit_price == 0 else None,
            price_reason="仓库依据实际到货代录，待供应商核实价格"))
    db.flush()
    return shipment, receipt_lines
