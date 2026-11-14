"""Warehouse-recorded physical notes, using the existing shipment/receipt ledgers."""
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_special_requests import SpecialShipment, SpecialShipmentLine
from app.schemas import carton_special_requests as schema
from app.services import carton_special_requests as special


def pending_deliveries(db, row, selected_line_ids=None):
    shipped, _, consumed, _, _ = special.state_counts(db, row)
    shipment_ids = sorted({paper.shipment_id for paper in shipped
        if (not selected_line_ids or paper.request_line_id in selected_line_ids)
        and paper.quantity > consumed.get(paper.id, Decimal(0))})
    if not shipment_ids:
        return [], []
    from app.services.carton_source_links import delivery_ids as group_by_source
    groups = group_by_source(db, row.factory_id)
    delivery_ids = list(dict.fromkeys(groups.get(identifier, 'SPECIAL:' + identifier) for identifier in shipment_ids))
    return shipment_ids, delivery_ids


def receive(db, user, identifier, payload: schema.ManualReceive):
    try:
        user = special.locked_actor(db, user, payload.factory_id)
        row = special.access(db, user, payload.factory_id, identifier, receiving=True)
        if not special.can_receive(user, row.factory_id):
            raise HTTPException(403, "手动收料须同时具备本厂收料及库存权限")
        if special.portal.fixed_supplier(db, row.factory_id).id != row.supplier_id:
            raise HTTPException(409, "订单供应商与当前厂区供应商不一致，请先核实")
        digest, saved = special.replay(db, user, payload, "MANUAL_RECEIVE", identifier)
        if saved:
            return saved
        from app.schemas.carton_unified_deliveries import WarehouseReceive, WarehouseSpecial
        from app.services import carton_warehouse_receiving as warehouse
        from app.services.carton_unified_deliveries import child_key
        result = warehouse.receive(db, user, WarehouseReceive(factory_id=payload.factory_id,
            request_id=child_key(payload.request_id, 'WAREHOUSE_MANUAL'), delivery_note_no=payload.delivery_note_no,
            delivery_date=payload.delivery_date, acceptance_date=payload.acceptance_date,
            special_requests=[WarehouseSpecial(id=row.id, expected_revision=payload.expected_revision, lines=payload.lines)]),
            refresh_actor=lambda: user, commit=False)
        response = special.finish(db, user, payload, row, "MANUAL_RECEIVE", digest, commit=False,
            response_extra={"manual_delivery_id": result['delivery_id']}, receiving=True)
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def build_shipment(db, user, row, payload, *, shipment=None):
    """Trusted builder after the caller validates and locks every source."""
    from app.services.carton_supplier_evidence_guard import ensure_evidence_open
    ensure_evidence_open(db, row.factory_id, row.supplier_id, payload.delivery_date)
    papers = {paper.id: paper for paper in special.lines(db, row)}
    if shipment is None:
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
