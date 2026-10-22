"""Per-acceptance payable agreement without rewriting vendor or stock evidence."""
import json
from decimal import Decimal, DecimalException
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt, CartonReceiptLine, CartonInventoryMovement
from app.services import carton_procurement as core


def original_price(source, source_kind):
    snapshot = json.loads(source.snapshot_json)
    if snapshot.get("source_origin") == "WAREHOUSE_MANUAL":
        return None, False
    raw = snapshot.get("delivery_unit_price") if source_kind == "REGULAR" and hasattr(source, "order_line_id") else snapshot.get("unit_price")
    try:
        value = Decimal(str(raw)) if raw not in (None, "") else None
        if value is not None and (not value.is_finite() or value < 0 or value >= Decimal("1000000000000") or value.normalize().as_tuple().exponent < -6):
            value = None
    except (DecimalException, ValueError, TypeError):
        value = None
    free = snapshot.get("free_confirmed") is True or snapshot.get("pricing_kind") == "FREE"
    return value, free


def record_line(db, user, receipt_line, source, shipment, acceptance, *, source_kind):
    """Called inside the existing receipt transaction after physical posting.

    Matching explicit vendor prices are immediately agreed. Every new receipt
    retains one agreement for its exact physical batch, including free lines.
    """
    original, free = original_price(source, source_kind)
    frozen = json.loads(source.snapshot_json)
    replacement_free = bool(frozen.get("replenishment_issue_id") and frozen.get("responsibility") == "SUPPLIER")
    supplied_value = getattr(acceptance, "unit_price", None)
    value = Decimal(supplied_value) if supplied_value is not None else Decimal(receipt_line.unit_price)
    action = getattr(acceptance, "price_action", "MATCH")
    kind = getattr(acceptance, "zero_price_kind", None)
    # Legacy gift corrections already carry an explicit free classification.
    # It permits recording zero; supplier agreement still follows matched below.
    if kind is None and getattr(acceptance, "no_order_decision", None) == "GIFT":
        kind = "FREE"
    reason = getattr(acceptance, "price_reason", "") or getattr(acceptance, "difference_reason", "")
    if replacement_free:
        value = Decimal(0)
        reason = "供应商责任补单按已确认责任免费换补；库存恢复原出库成本，不计应付"
    if action == "FREE" and value != 0:
        raise HTTPException(422, "确认免费必须明确填写零单价")
    if action == "PROPOSE" and supplied_value is None:
        raise HTTPException(422, "提出价格更正须填写明确单价")
    if receipt_line.effective_quantity <= 0:
        return
    matched = replacement_free or (action in {"MATCH", "FREE"} and original is not None and value == original and (original > 0 or free) and kind != "PENDING")
    if not matched and value == 0 and kind not in {"FREE", "PENDING"} and action not in {"FREE", "PENDING"}:
        raise HTTPException(422, "零单价须明确选择免费或待核价")
    pending = not replacement_free and (action == "PENDING" or kind == "PENDING")
    if not matched and action in {"PROPOSE", "FREE"} and len(reason.strip()) < 4:
        raise HTTPException(422, "价格更正须填写至少四字原因")
    review = CartonPriceReview(id="CPR-" + uuid4().hex, factory_id=receipt_line.factory_id,
        supplier_id=shipment.supplier_id, receipt_line_id=receipt_line.id, source_kind=source_kind,
        shipment_id=shipment.id, shipment_line_id=source.id, original_unit_price=original,
        proposed_unit_price=None if pending else value, status="CONFIRMED" if matched else "PENDING" if pending else "PROPOSED",
        revision=1, reason=reason or ("按供应商原价核实收货" if matched else "仓库验收价格与供应商凭证不一致，待双方核实"),
        created_by=user.id, updated_by=user.id, updated_at=core.now_text())
    db.add(review)
    db.flush()
    core._audit(db, user, review.factory_id, "PRICE_REVIEW_CREATED", "carton_price_review", review.id,
        {"revision": 1, "status": review.status, "original_unit_price": original, "original_free_confirmed": free,
         "proposed_unit_price": review.proposed_unit_price, "reason": review.reason})


def reviews_by_line(db, factory):
    return {row.receipt_line_id: row for row in db.scalars(select(CartonPriceReview).where(CartonPriceReview.factory_id == factory))}


def review_out(db, row, *, external=False):
    paper = db.get(CartonReceiptLine, row.receipt_line_id)
    receipt = db.get(CartonReceipt, paper.receipt_id)
    history = [dict(json.loads(event.detail_json), actor_user_id=event.actor_user_id,
                    occurred_at=event.created_at, action=event.event_type)
        for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == row.factory_id,
            CartonAuditEvent.entity_type == "carton_price_review", CartonAuditEvent.entity_id == row.id)
            .order_by(CartonAuditEvent.sequence))]
    if external:
        history = [{key: value for key, value in event.items() if key not in {"manual_unit_price", "amount_difference"}}
            for event in history if event["action"] != "PRICE_REVIEW_CORRECTION_APPLIED"]
    from app.models.carton_supplier_settlement import CartonSupplierSettlement
    period = (receipt.acceptance_date or receipt.confirmed_at[:10])[:7]
    locked = bool(db.scalar(select(CartonSupplierSettlement.id).where(
        CartonSupplierSettlement.factory_id == row.factory_id, CartonSupplierSettlement.supplier_id == row.supplier_id,
        CartonSupplierSettlement.period == period, CartonSupplierSettlement.status == "CONFIRMED")))
    full_correction = correction_needed(db, row)
    return {key: getattr(row, key) for key in ("id", "factory_id", "supplier_id", "receipt_line_id", "source_kind",
        "shipment_id", "shipment_line_id", "status", "revision", "reason", "updated_at")} | {
        "original_unit_price": str(row.original_unit_price) if row.original_unit_price is not None else None,
        "proposed_unit_price": str(row.proposed_unit_price) if row.proposed_unit_price is not None else None,
        "effective_unit_price": str(row.proposed_unit_price) if row.status == "CONFIRMED" else None,
        "currency": paper.currency, "document_no": receipt.delivery_note_no, "item_no": paper.item_no,
        "packaging_type": paper.packaging_type, "specification": paper.specification, "unit": paper.unit,
        "quantity": str(paper.effective_quantity), "receipt_status": receipt.status,
        "original_free_confirmed": bool(history and history[0].get("original_free_confirmed")),
        "history": history, "locked": locked, "need_full_correction": full_correction,
        "can_propose": receipt.status == "POSTED" and not locked and not full_correction,
        "actionable": receipt.status == "POSTED" and not locked and not full_correction}


def correction_needed(db, row, target=None, *, checking_target=False):
    """Known cost changes need bilateral price plus supervisor valuation review."""
    from app.services.carton_price_correction import effective_price, events, COST_EVENT
    from app.services.carton_replenishment_receipts import receipt_links
    if receipt_links(db,row.factory_id).get(row.receipt_line_id,{}).get("responsibility") == "SUPPLIER": return False
    movement = db.scalar(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == row.factory_id,
        CartonInventoryMovement.source_type == "RECEIPT", CartonInventoryMovement.source_line_id == row.receipt_line_id))
    if not movement: return False
    records=events(db,row.factory_id); price,_,known=effective_price(movement,records)
    applied=any(event.event_type==COST_EVENT and event.entity_id==movement.id for event in records)
    if applied: return True
    if not known: return False
    if checking_target: return target != price if target is not None else row.status == "CONFIRMED"
    return bool(applied or row.status == "CONFIRMED" or row.proposed_unit_price is not None and row.proposed_unit_price != price)


def free_contract(db,row):
    from app.services.carton_replenishment_receipts import receipt_links
    if receipt_links(db,row.factory_id).get(row.receipt_line_id,{}).get("responsibility")=="SUPPLIER": return True
    if row.source_kind=="SPECIAL":
        from app.models.carton_special_requests import SpecialShipment,SpecialRequest
        shipment=db.get(SpecialShipment,row.shipment_id)
        request=db.get(SpecialRequest,shipment.request_id) if shipment else None
        return bool(request and request.kind=="SUPPLIER_GIFT")
    return False


def authorize(db, user, factory, *, external=False, write=False):
    from app.services import carton_supplier_portal as portal
    core.require_carton_factory(factory)
    if external:
        # Fixed supplier is independent of whether a formal purchase exists.
        if not portal.supplier_permission(user, "carton_supplier:read", factory) or (write and not portal.supplier_permission(user, "carton_supplier:approve", factory)):
            raise HTTPException(403, "没有本厂供应商核价权限")
        return portal.fixed_supplier(db, factory).id
    from app.services.carton_special_requests import allowed
    if not all(allowed(user, factory, permission) for permission in ("read", "receipt_write", "inventory_write")):
        raise HTTPException(403, "没有本厂收料核价权限")
    return None


def customer_access(db, user, row):
    from app.services.carton_special_requests import ensure_customer_operation
    paper = db.get(CartonReceiptLine, row.receipt_line_id)
    ensure_customer_operation(db, user, row.factory_id, paper.customer_code)


def workspace(db, user, factory, *, external=False, shipment_id=None):
    supplier = authorize(db, user, factory, external=external)
    rows = db.scalars(select(CartonPriceReview).where(CartonPriceReview.factory_id == factory)
        .order_by(CartonPriceReview.updated_at.desc(), CartonPriceReview.id)).all()
    result = []
    for row in rows:
        if (supplier and row.supplier_id != supplier) or (shipment_id and row.shipment_id != shipment_id):
            continue
        if not external:
            try:
                customer_access(db, user, row)
            except HTTPException as exc:
                if exc.status_code != 403: raise
                continue
        result.append(review_out(db, row, external=external))
    return {"items": result}


def act(db, user, identifier, payload, *, external=False):
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_supplier_portal import fingerprint
    from app.services.carton_supplier_settlement import receipt_guard
    user = locked_actor(db, user, payload.factory_id)
    supplier = authorize(db, user, payload.factory_id, external=external, write=True)
    row = db.scalar(select(CartonPriceReview).where(CartonPriceReview.id == identifier,
        CartonPriceReview.factory_id == payload.factory_id))
    if row is None or (supplier and row.supplier_id != supplier):
        raise HTTPException(404, "未找到此厂区的核价记录")
    if not external: customer_access(db, user, row)
    digest = fingerprint(payload)
    action = "PRICE_REVIEW_DECIDED" if external else "PRICE_REVIEW_PROPOSED"
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == row.factory_id,
        CartonAuditEvent.entity_type == "carton_price_review", CartonAuditEvent.entity_id == row.id,
        CartonAuditEvent.actor_user_id == user.id, CartonAuditEvent.event_type == action)):
        detail = json.loads(event.detail_json)
        if detail.get("request_id") == payload.request_id:
            if detail.get("fingerprint") != digest: raise HTTPException(409, "提交标识已用于其他核价内容")
            return review_out(db, row, external=external)
    paper = db.get(CartonReceiptLine, row.receipt_line_id)
    receipt = db.get(CartonReceipt, paper.receipt_id)
    if receipt.status != "POSTED": raise HTTPException(409, "原收料已冲销，不可更改价格")
    receipt_guard(db, receipt)
    if row.revision != payload.expected_revision: raise HTTPException(409, "价格版本已更新，请刷新后核对")
    candidate = row.proposed_unit_price if external else payload.proposed_unit_price
    if free_contract(db,row) and candidate is not None and candidate != 0:
        raise HTTPException(422,"供应商责任免费补货或赠送不能通过核价变成收费采购")
    if correction_needed(db,row,candidate,checking_target=True):
        raise HTTPException(409,"此单价会改变已知入库成本，请使用原收料批次的三方单价更正流程，由主管核实成本影响后生效")
    before = review_out(db, row)
    if external:
        if row.status != "PROPOSED" or row.proposed_unit_price is None:
            raise HTTPException(409, "请先由仓库提出明确价格，再确认")
        if payload.decision == "REJECT" and len(payload.reason.strip()) < 4:
            raise HTTPException(422, "退回须填写至少四字原因")
        row.status = "CONFIRMED" if payload.decision == "CONFIRM" else "PENDING"
    else:
        row.proposed_unit_price = payload.proposed_unit_price
        row.status = "PENDING" if payload.proposed_unit_price is None else "PROPOSED"
    row.reason = payload.reason or row.reason
    row.revision += 1
    row.updated_by = user.id
    row.updated_at = core.now_text()
    core._audit(db, user, row.factory_id, action, "carton_price_review", row.id,
        {"request_id": payload.request_id, "fingerprint": digest, "revision": row.revision,
         "previous_status": before["status"], "status": row.status, "decision": getattr(payload, "decision", ""),
         "proposed_unit_price": row.proposed_unit_price, "reason": row.reason})
    db.commit()
    return review_out(db, row, external=external)


def apply_sources(db, factory, rows):
    """Price agreement changes payables only; stock costs are separate facts."""
    reviews = reviews_by_line(db, factory)
    for row in rows:
        review = reviews.get(row["source_key"].removeprefix("RECEIPT:")) if row["kind"] == "RECEIPT" else None
        if not review: continue
        row["price_review"] = {"id": review.id, "status": review.status, "revision": review.revision}
        row["issues"] = [issue for issue in row["issues"] if issue != "入库单价待核实"]
        price = review.proposed_unit_price if review.status == "CONFIRMED" else None
        row["unit_price"] = str(price) if price is not None else None
        from app.services.carton_supplier_settlement import money
        row["amount"] = str(money(Decimal(row["quantity"]) * price)) if price is not None else None
        if price is None: row["issues"].append("送货价格待双方核实，不能完成月结确认")
    from app.services.carton_supplier_manual_evidence import updates
    adopted = updates(db, factory)
    for row in rows:
        if row["kind"] == "RECEIPT" and row["source_key"].removeprefix("RECEIPT:") in adopted:
            row["supplier_price_update"] = adopted[row["source_key"].removeprefix("RECEIPT:")]
    corrections = applied_corrections(db,factory)
    for row in rows:
        correction = corrections.get(row["source_key"].removeprefix("RECEIPT:")) if row["kind"] == "RECEIPT" else None
        if correction:
            from app.services.carton_supplier_settlement import money
            row.update(unit_price=correction["unit_price"],amount=str(money(Decimal(row["quantity"])*Decimal(correction["unit_price"]))),price_correction=correction)
            row["issues"] = [issue for issue in row["issues"] if issue not in {"入库单价待核实","送货价格待双方核实，不能完成月结确认"}]


def applied_corrections(db,factory):
    result={}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id==factory,
        CartonAuditEvent.event_type=="INVENTORY_PRICE_CORRECTED").order_by(CartonAuditEvent.sequence)):
        data=json.loads(event.detail_json)
        result[data["receipt_line_id"]]=dict(id=data["correction_id"],event_id=event.id,unit_price=str(data["unit_price"]))
    return result


def apply_vendor(db, factory, receipt_line_id, vendor, effective_quantity):
    review = db.scalar(select(CartonPriceReview).where(CartonPriceReview.factory_id == factory,
        CartonPriceReview.receipt_line_id == receipt_line_id))
    correction=applied_corrections(db,factory).get(receipt_line_id)
    if not review and not correction: return vendor
    from app.services.carton_supplier_settlement import money
    value = dict(vendor or {})
    if correction and "original_unit_price" not in value: value["original_unit_price"] = vendor.get("unit_price") if vendor else None
    price = Decimal(correction["unit_price"]) if correction else review.proposed_unit_price if review.status == "CONFIRMED" else None
    value.update(unit_price=str(price) if price is not None else None,
        amount=str(money(Decimal(effective_quantity) * price)) if price is not None else None,
        quantity=str(effective_quantity), price_difference="0" if price is not None else None,
        price_warning="" if price is not None else (value.get("price_warning") or "送货价格待双方核实"))
    if review: value.update(price_review_id=review.id,price_review_status=review.status,price_review_revision=review.revision)
    from app.services.carton_supplier_manual_evidence import updates
    adopted = updates(db, factory).get(receipt_line_id)
    if adopted:
        value.update(original_unit_price=adopted["supplier_unit_price"])
    if correction: value["price_correction"]=correction
    return value
