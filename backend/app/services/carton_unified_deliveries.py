"""Atomic dispatch and receipt orchestration over the existing source ledgers."""
import hashlib
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_, case, literal, union_all
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierShipment
from app.models.carton_special_requests import UnifiedDelivery, SpecialRequest, SpecialLine, SpecialShipment, SpecialShipmentLine, SpecialReceiptLink
from app.schemas import carton_special_requests as ss, carton_supplier_portal as ps
from app.services import carton_special_requests as special, carton_supplier_portal as portal


def child_key(root, suffix):
    return hashlib.sha256((root + ":" + suffix).encode()).hexdigest()


def authorize(db, user, factory, external=False):
    if external: return special.supplier(db, user, factory).id
    special.core.require_carton_factory(factory)
    if not all(special.allowed(user, factory, permission) for permission in ("read", "receipt_write", "inventory_write")):
        raise HTTPException(403, "没有本厂统一收料权限")
    return portal.fixed_supplier(db, factory).id


def descriptors(db, user, factory, identifier, *, external=False, read_only_all=False):
    vendor = authorize(db, user, factory, external)
    group = db.get(UnifiedDelivery, identifier)
    if group:
        if group.factory_id != factory or group.supplier_id != vendor: raise HTTPException(404, "送货单不存在")
        data = json.loads(group.children_json)
        formal_id, special_ids = data["formal_id"], data["special_ids"]
        note, day, created = group.delivery_note_no, group.delivery_date, group.created_at
    elif identifier.startswith("FORMAL:"):
        formal_id, special_ids = identifier[7:], []
        formal = db.get(SupplierShipment, formal_id)
        if not formal or formal.factory_id != factory or formal.supplier_id != vendor: raise HTTPException(404, "送货单不存在")
        note, day, created = formal.delivery_note_no, formal.delivery_date, formal.created_at
    elif identifier.startswith("SPECIAL:"):
        formal_id, special_ids = "", [identifier[8:]]
        shipment = db.get(SpecialShipment, special_ids[0])
        if not shipment or shipment.factory_id != factory or shipment.supplier_id != vendor: raise HTTPException(404, "送货单不存在")
        note, day, created = shipment.delivery_note_no, shipment.delivery_date, shipment.created_at
    else: raise HTTPException(404, "送货单不存在")
    formal = db.get(SupplierShipment, formal_id) if formal_id else None
    if formal and not external and not read_only_all: portal.ensure_shipment_customers(db, user, formal)
    specials = []
    for shipment_id in special_ids:
        shipment = db.get(SpecialShipment, shipment_id)
        if not shipment or shipment.factory_id != factory or shipment.supplier_id != vendor:
            raise HTTPException(409, "送货来源关联异常，请核对原单")
        special.access(db, user, factory, shipment.request_id, external=external)
        specials.append(shipment)
    return formal, specials, note, day, created


def project(db, user, factory, identifier, *, external=False, read_only_all=False):
    formal, shipments, note, day, created = descriptors(db, user, factory, identifier, external=external, read_only_all=read_only_all)
    formal_out = portal.shipment_out(db, formal, internal=not external) if formal else None
    output, papers, receipts = [], [], []
    if formal_out:
        # Unified notes share the supplier's own frozen price with both sides.
        # Do not substitute the separate internal order cost for missing evidence,
        # or change the legacy portal's intentionally restricted projection.
        formal_sources, _ = portal._shipment_sources(db, formal)
        original_by_id = {line.id: json.loads(line.snapshot_json) for line in formal_sources}
        for line in formal_out["lines"]:
            original = original_by_id.get(line["id"])
            if original is not None:
                line.update(delivery_unit_price=original.get("delivery_unit_price"),
                    free_confirmed=bool(original.get("free_confirmed")), currency=original.get("currency", "CNY"),
                    source_origin=original.get("source_origin"), warehouse_unit_price=original.get("warehouse_unit_price"))
            papers.append(dict(line, source_kind="FORMAL", formal_shipment_id=formal.id))
        receipts.extend(formal_out.get("acceptance_history", []))
    correction = bool(formal_out and formal_out["requires_correction"])
    for shipment in shipments:
        detail = special.detail(db, user, factory, shipment.request_id, external=external)
        chosen = next(value for value in detail["shipments"] if value["id"] == shipment.id)
        detail["shipments"] = [chosen]
        output.append(detail)
        receipts.extend(chosen["receipts"])
        correction = correction or any(item["status"] == "REVERSED" for item in chosen["receipts"])
        for line in chosen["lines"]:
            frozen = line["snapshot"]
            papers.append({**frozen, "id": line["id"], "quantity": line["quantity"],
                "source_kind": "SPECIAL", "source_type": "SPECIAL_REQUEST", "order_line_id": None,
                "special_request_id": detail["id"], "special_shipment_id": shipment.id,
                "special_request_revision": detail["revision"], "original_special_line_id": line["request_line_id"],
                "origin": detail["origin"], "requester_name": detail["requester_name"], "workshop_id": detail["workshop_id"],
                "purpose": detail["purpose"], "customer_name": frozen.get("customer_name", ""), "customer_code": frozen.get("customer_code", ""),
                "order_no": detail["request_no"], "child_no": str(frozen["line_no"]),
                "contract_no": "", "customer_po": "", "currency": "CNY",
                "delivery_unit_price": None if frozen.get("source_origin") == "WAREHOUSE_MANUAL" else frozen["unit_price"],
                "free_confirmed": frozen["pricing_kind"] == "FREE",
                "remaining_quantity": line["remaining_quantity"], "receivable_quantity": line["remaining_quantity"],
                "received_quantity": line["gross_received_quantity"], "effective_quantity": line["effective_received_quantity"]})
    pending = any(Decimal(str(paper.get("receivable_quantity", paper.get("remaining_quantity", "0")))) > 0 for paper in papers)
    correction = correction and pending
    status = formal_out["status"] if formal_out and not shipments else "RECEIPT_REVERSED" if correction else "SENT" if pending else "RECEIVED"
    return {"id": identifier, "factory_id": factory, "delivery_note_no": note, "delivery_date": day, "created_at": created,
        "formal": formal_out, "special": output, "lines": papers, "receipts": receipts,
        "requires_correction": correction, "can_operate": external or not formal or portal.visible_shipment(db, user, formal),
        "status": status,
        "revision": formal_out["revision"] if formal_out else max((item["revision"] for item in output), default=1)}


def workspace(db, user, factory, *, external=False, responsibility_scope="OWN"):
    if responsibility_scope not in {"OWN", "ALL"}: raise HTTPException(422, "客户范围无效")
    vendor = authorize(db, user, factory, external)
    groups = list(db.scalars(select(UnifiedDelivery).where(UnifiedDelivery.factory_id == factory, UnifiedDelivery.supplier_id == vendor)))
    linked_formal, linked_special = set(), set()
    identifiers = []
    for group in groups:
        children = json.loads(group.children_json)
        linked_formal.add(children["formal_id"]); linked_special.update(children["special_ids"])
        identifiers.append(group.id)
    identifiers.extend("FORMAL:" + row.id for row in db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory, SupplierShipment.supplier_id == vendor)) if row.id not in linked_formal)
    identifiers.extend("SPECIAL:" + row.id for row in db.scalars(select(SpecialShipment).where(
        SpecialShipment.factory_id == factory, SpecialShipment.supplier_id == vendor)) if row.id not in linked_special)
    items = []
    for identifier in identifiers:
        try: items.append(project(db, user, factory, identifier, external=external, read_only_all=not external and responsibility_scope == "ALL"))
        except HTTPException as exc:
            if exc.status_code not in {403, 404}: raise
    items.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    options = {"workshops": []}
    if not external:
        from app.models.carton_master import CartonMasterRecord
        options["workshops"] = [{"id": row.id, "name": row.code} for row in db.scalars(select(CartonMasterRecord).where(
            CartonMasterRecord.factory_id == factory, CartonMasterRecord.kind == "WORKSHOP", CartonMasterRecord.status == "ACTIVE"))]
    return {"items": items, "total": len(items), "options": options}


def pending(db, user, factory, *, limit=3):
    """One SQL source snapshot for the count and bounded original-note preview."""
    vendor = authorize(db, user, factory)
    consumed = select(SpecialReceiptLink.shipment_line_id.label("line_id"),
        func.sum(CartonReceiptLine.received_quantity).label("quantity")).join(CartonReceiptLine,
            CartonReceiptLine.id == SpecialReceiptLink.receipt_line_id).join(CartonReceipt,
            CartonReceipt.id == CartonReceiptLine.receipt_id).where(SpecialReceiptLink.factory_id == factory,
            CartonReceipt.status == "POSTED").group_by(SpecialReceiptLink.shipment_line_id).subquery()
    reversed_special = (select(SpecialShipmentLine.shipment_id.label("shipment_id")).join(SpecialReceiptLink,
        SpecialReceiptLink.shipment_line_id == SpecialShipmentLine.id).join(CartonReceiptLine,
        CartonReceiptLine.id == SpecialReceiptLink.receipt_line_id).join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(SpecialShipmentLine.factory_id == factory, CartonReceipt.status == "REVERSED").distinct().subquery())

    def source_columns(model, prefix, correction):
        return [func.coalesce(UnifiedDelivery.id, literal(prefix) + model.id).label("identifier"),
            model.delivery_note_no.label("note"), model.delivery_date.label("day"),
            func.coalesce(UnifiedDelivery.created_at, model.created_at).label("created"), correction.label("correction")]

    def group_join(model):
        return and_(UnifiedDelivery.factory_id == model.factory_id, UnifiedDelivery.supplier_id == model.supplier_id,
                    UnifiedDelivery.delivery_note_no == model.delivery_note_no)

    formal = select(*source_columns(SupplierShipment, "FORMAL:", case((CartonReceipt.status == "REVERSED", 1), else_=0)))\
        .select_from(SupplierShipment).outerjoin(CartonReceipt, CartonReceipt.id == SupplierShipment.receipt_id)\
        .outerjoin(UnifiedDelivery, group_join(SupplierShipment)).where(SupplierShipment.factory_id == factory,
            SupplierShipment.supplier_id == vendor, or_(SupplierShipment.status == "SENT", CartonReceipt.status == "REVERSED"))
    other = select(*source_columns(SpecialShipment, "SPECIAL:", case((reversed_special.c.shipment_id.is_not(None), 1), else_=0)))\
        .select_from(SpecialShipment).join(SpecialShipmentLine, SpecialShipmentLine.shipment_id == SpecialShipment.id)\
        .outerjoin(consumed, consumed.c.line_id == SpecialShipmentLine.id)\
        .outerjoin(reversed_special, reversed_special.c.shipment_id == SpecialShipment.id)\
        .outerjoin(UnifiedDelivery, group_join(SpecialShipment)).where(SpecialShipment.factory_id == factory,
            SpecialShipment.supplier_id == vendor, SpecialShipmentLine.quantity > func.coalesce(consumed.c.quantity, 0))
    all_notes = union_all(formal, other).subquery()
    query = select(all_notes.c.identifier, all_notes.c.note, all_notes.c.day,
        func.max(all_notes.c.created).label("created"), func.max(all_notes.c.correction).label("correction"))\
        .group_by(all_notes.c.identifier, all_notes.c.note, all_notes.c.day)\
        .order_by(func.max(all_notes.c.created).desc(), all_notes.c.identifier.desc())
    result = []
    for row in db.execute(query):
        try: descriptors(db, user, factory, row.identifier)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}: raise
            continue
        result.append({"id": row.identifier.removeprefix("FORMAL:"), "delivery_note_no": row.note,
                       "delivery_date": row.day, "requires_correction": bool(row.correction)})
    return {"factory_id": factory, "total": len(result), "items": result[:limit]}


def extra_request(db, user, factory, supplier_id, item, date):
    if item.unit_price == 0 and not item.free_confirmed: raise HTTPException(422, "额外送货零单价须明确确认免费")
    row = SpecialRequest(id=special.uid("CSR-"), factory_id=factory, supplier_id=supplier_id,
        request_no=special.uid("EX-"), kind="WORKSHOP_MISC", origin="SUPPLIER_EXTRA", title="", requester_name="",
        workshop_id="", customer_code="", customer_name="", purpose=item.purpose, required_date=date.isoformat(),
        status="SENT", revision=1, current_version_id="", quote_version_id="", pricing_kind="PENDING_QUOTE",
        promised_date="", created_by=user.id, created_at=special.core.now_text(), updated_at=special.core.now_text())
    db.add(row); db.flush()
    special.core._unordered_specification(item.specification, item.dimension_unit)
    line = SpecialLine(id=special.uid("CSL-"), factory_id=factory, request_id=row.id, line_no=1,
        **item.model_dump(exclude={"id", "unit_price", "free_confirmed", "purpose"}), unit_price=0)
    db.add(line); special.version(db, user, row, "SUPPLIER_EXTRA", execution=True)
    return row, line


def dispatch(db, user, payload):
    try:
        user = special.locked_actor(db, user, payload.factory_id)
        vendor = special.supplier(db, user, payload.factory_id, "carton_supplier:edit")
        digest = portal.fingerprint(payload)
        old = db.scalar(select(UnifiedDelivery).where(UnifiedDelivery.factory_id == payload.factory_id,
            UnifiedDelivery.created_by == user.id, UnifiedDelivery.request_key == payload.request_id))
        if old:
            if old.fingerprint != digest: raise HTTPException(409, "提交标识已用于其他送货内容")
            return project(db, user, payload.factory_id, old.id, external=True)
        for model in (UnifiedDelivery, SupplierShipment, SpecialShipment, CartonReceipt):
            if db.scalar(select(model.id).where(model.factory_id == payload.factory_id, model.supplier_id == vendor.id,
                model.delivery_note_no == payload.delivery_note_no)):
                raise HTTPException(409, "供应商原送货单号已登记，请核对原单")
        formal_id, special_ids = "", []
        if payload.formal_lines:
            result = portal.create_shipment(db, user, ps.ShipmentCreate(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, "FORMAL"), delivery_note_no=payload.delivery_note_no,
                delivery_date=payload.delivery_date, lines=payload.formal_lines), commit=False)
            formal_id = result["id"]
        entries = [(item.id, item.expected_revision, item.version_id, item.lines) for item in payload.special_requests]
        for item in payload.extra_lines:
            row, line = extra_request(db, user, payload.factory_id, vendor.id, item, payload.delivery_date)
            entries.append((row.id, row.revision, row.current_version_id, [ss.ShipLine(line_id=line.id,
                quantity=item.quantity, unit_price=item.unit_price, free_confirmed=item.free_confirmed)]))
        for identifier, revision, version, lines in entries:
            result = special.ship(db, user, identifier, ss.Ship(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, identifier), expected_revision=revision, version_id=version,
                delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date, lines=lines),
                commit=False, allow_shared_note=True)
            special_ids.append(next(item["id"] for item in result["shipments"] if item["delivery_note_no"] == payload.delivery_note_no))
        group = UnifiedDelivery(id=special.uid("CUD-"), factory_id=payload.factory_id, supplier_id=vendor.id,
            delivery_note_no=payload.delivery_note_no, delivery_date=payload.delivery_date.isoformat(),
            children_json=special.pack({"formal_id": formal_id, "special_ids": special_ids}), request_key=payload.request_id,
            fingerprint=digest, created_by=user.id, created_at=special.core.now_text())
        db.add(group); db.flush()
        result = project(db, user, payload.factory_id, group.id, external=True)
        db.commit()
        return result
    except Exception:
        db.rollback(); raise


def receive(db, user, identifier, payload):
    try:
        user = special.locked_actor(db, user, payload.factory_id)
        formal, shipments, _, _, _ = descriptors(db, user, payload.factory_id, identifier)
        digest, saved = special.replay(db, user, payload, "UNIFIED_RECEIVE", identifier)
        if saved: return saved
        if payload.formal:
            if formal is None: raise HTTPException(422, "此送货单没有正单明细")
            portal.receive_shipment(db, user, formal.id, ps.ShipmentReceive(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, "FORMAL"), acceptance_date=payload.acceptance_date,
                **payload.formal.model_dump()), commit=False)
        available = {shipment.id: shipment for shipment in shipments}
        for item in payload.special:
            shipment = available.get(item.shipment_id)
            if not shipment or shipment.request_id != item.request_id:
                raise HTTPException(422, "样板或杂单明细不属于此原送货单")
            special.receive(db, user, shipment.request_id, shipment.id, ss.Receive(factory_id=payload.factory_id,
                request_id=child_key(payload.request_id, shipment.id), expected_revision=item.expected_revision,
                acceptance_date=payload.acceptance_date, lines=item.lines, received_kind=item.received_kind,
                workshop_id=item.workshop_id, requester_name=item.requester_name), commit=False)
        result = project(db, user, payload.factory_id, identifier)
        event = special.core._audit(db, user, payload.factory_id, "UNIFIED_RECEIVED", "carton_unified_delivery", identifier,
            {"fingerprint": digest, "request_id": payload.request_id, "response": result})
        event.id = special.replay_id(user, payload)
        db.commit()
        return result
    except Exception:
        db.rollback(); raise
