"""Attach a supplier's late document to one posted receipt without posting goods again."""
import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonOrderLine, CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierShipment
from app.services.carton_material_identity import material_conflicts
from app.services.carton_procurement_imports import _dongkang_identity

EVENT = "SUPPLIER_SHIPMENT_RECEIPT_LINKED"


def link_only(shipment):
    return not shipment.receipt_id and json.loads(shipment.acceptance_json or "{}").get("registration_mode") == "EXISTING_RECEIPT"


def matching_receipts(db, factory, supplier, papers, *, note_no="", reversed_ids=(), include_linked=False):
    """Whole-note, one-to-one matching; never infer a partial or mixed receipt association."""
    from app.services.carton_replenishment_receipts import receipt_links, legacy_review_lines
    if not papers or any(not paper.get("order_line_id") for paper in papers):
        return []
    ids = {paper["order_line_id"] for paper in papers}
    if len(ids) != len(papers):
        return []
    replacement = receipt_links(db, factory)
    ambiguous = legacy_review_lines(db, factory, list(ids))
    linked = set(db.scalars(select(SupplierShipment.receipt_id).where(
        SupplierShipment.factory_id == factory, SupplierShipment.receipt_id.is_not(None))))
    receipts = db.scalars(select(CartonReceipt).where(CartonReceipt.factory_id == factory,
        CartonReceipt.supplier_id == supplier, CartonReceipt.status.in_(["POSTED", "REVERSED"] if reversed_ids else ["POSTED"]),
        CartonReceipt.id.in_(select(CartonReceiptLine.receipt_id).where(CartonReceiptLine.factory_id == factory,
            CartonReceiptLine.order_line_id.in_(ids))))
        .order_by(CartonReceipt.acceptance_date.desc(), CartonReceipt.id)).all()
    same_number_ids = set(db.scalars(select(CartonReceipt.id).where(CartonReceipt.factory_id == factory,
        CartonReceipt.supplier_id == supplier, CartonReceipt.delivery_note_no == note_no))) if note_no else set()
    candidates = []
    for receipt in receipts:
        if same_number_ids and receipt.id not in same_number_ids:
            continue
        if receipt.id in linked and not include_linked:
            continue
        if receipt.status == "REVERSED":
            if receipt.id not in reversed_ids:
                continue  # Only a candidate saved when this late document was registered may be recovered.
            reversal = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
                CartonAuditEvent.entity_id == receipt.id, CartonAuditEvent.event_type == "RECEIPT_REVERSED")
                .order_by(CartonAuditEvent.sequence.desc()).limit(1))
            if not reversal or json.loads(reversal.detail_json).get("previous_status") != "POSTED":
                continue  # Voiding an unposted draft is not reversal of already received goods.
        lines = list(db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == receipt.id,
            CartonReceiptLine.factory_id == factory).order_by(CartonReceiptLine.line_no)))
        if len(lines) != len(papers) or {line.order_line_id for line in lines} != ids:
            continue
        by_id = {line.order_line_id: line for line in lines}
        receipt_event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.entity_id == receipt.id, CartonAuditEvent.event_type == "RECEIPT_DRAFT_CREATED"))
        valid = True
        for paper in papers:
            line = by_id[paper["order_line_id"]]
            saved = {key: getattr(line, key) for key in ("packaging_type", "paper_quality", "specification", "unit", "currency")}
            # Receipt rows predate a separate dimension-unit column. Recover the frozen
            # unit from the issued paper that existed when this receipt was created.
            from app.services.carton_procurement import _purchase_order_issues, _purchase_order_snapshot
            order_line = db.get(CartonOrderLine, line.order_line_id)
            if order_line and receipt_event:
                for issue in _purchase_order_issues(db, order_line.order_id):
                    issued = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
                        CartonAuditEvent.entity_id == issue.id, CartonAuditEvent.event_type == "PURCHASE_ORDER_ISSUED",
                        CartonAuditEvent.sequence < receipt_event.sequence))
                    snapshot = _purchase_order_snapshot(issue)
                    if issued and not snapshot.get("replenishment"):
                        frozen = next((item for item in snapshot.get("lines", []) if item.get("id") == line.order_line_id), {})
                        saved["dimension_unit"] = frozen.get("dimension_unit", "")
                        break
            quantity = Decimal(str(paper["quantity"]))
            if (line.source_type != "FORMAL_ORDER" or line.id in replacement or line.order_line_id in ambiguous
                or material_conflicts(paper, saved)
                or any(paper.get(key) and _dongkang_identity(paper[key]) != _dongkang_identity(getattr(line, key))
                    for key in ("contract_no", "item_no"))
                or paper.get("unit") != line.unit or paper.get("currency", "CNY") != line.currency
                or quantity not in {line.delivered_quantity, line.received_quantity}):
                valid = False
                break
        if valid:
            candidates.append((receipt, lines))
    return candidates


def acceptance_day(receipt):
    from app.services.carton_supplier_settlement import _posting_date
    if receipt.acceptance_date:
        return receipt.acceptance_date
    if receipt.confirmed_at:
        return _posting_date(receipt.confirmed_at)
    raise HTTPException(409, "原入库缺少可核实的验收时间，请先核对原记录，不能猜测月结月份")


def reversed_candidates(shipment):
    return json.loads(shipment.acceptance_json or "{}").get("candidate_receipt_ids", []) if link_only(shipment) else []


def shipment_papers(db, shipment):
    from app.services import carton_supplier_portal as portal
    formal, unmatched = portal._shipment_sources(db, shipment)
    if unmatched:
        return []
    papers = []
    for line in formal:
        snapshot = json.loads(line.snapshot_json)
        if not snapshot.get("dimension_unit"):
            issue = db.get(portal.CartonPurchaseOrderIssue, line.issue_id)
            frozen = next((item for item in portal._purchase_order_snapshot(issue).get("lines", [])
                if item.get("id") == line.order_line_id), {}) if issue else {}
            snapshot["dimension_unit"] = frozen.get("dimension_unit", "")
        papers.append(snapshot | {"order_line_id": line.order_line_id, "quantity": str(line.quantity)})
    return papers


def options(db, user, factory, shipment_id):
    from app.services import carton_supplier_portal as portal
    portal.internal_permission(user, factory, "carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write")
    portal._lock_receipt_factory(db, factory)
    shipment = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == factory, SupplierShipment.id == shipment_id))
    if shipment is None:
        raise HTTPException(404, "未找到此厂区的发货单")
    if shipment.status != "SENT" or shipment.receipt_id:
        return []
    return [{"id": receipt.id, "revision": receipt.revision, "receipt_no": receipt.receipt_no,
        "already_linked": bool(db.scalar(select(SupplierShipment.id).where(SupplierShipment.factory_id == factory,
            SupplierShipment.receipt_id == receipt.id).limit(1))),
        "status": receipt.status,
        "delivery_note_no": receipt.delivery_note_no, "delivery_date": receipt.delivery_date,
        "acceptance_date": acceptance_day(receipt),
        "lines": [{key: str(getattr(line, key)) for key in ("order_line_id", "contract_no", "item_no", "packaging_type",
            "paper_quality", "specification", "received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity",
            "effective_quantity", "unit", "unit_price", "currency")} for line in lines]}
        for receipt, lines in matching_receipts(db, factory, shipment.supplier_id, shipment_papers(db, shipment),
            note_no=shipment.delivery_note_no, reversed_ids=reversed_candidates(shipment), include_linked=True)]


def associate(db, user, shipment_id, payload):
    from app.services import carton_supplier_portal as portal, carton_supplier_settlement as settlement
    portal.internal_permission(user, payload.factory_id, "carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write")
    portal._lock_receipt_factory(db, payload.factory_id)
    shipment = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == payload.factory_id, SupplierShipment.id == shipment_id))
    if shipment is None:
        raise HTTPException(404, "未找到此厂区的发货单")
    digest = hashlib.sha256((shipment_id + "|" + portal.fingerprint(payload)).encode()).hexdigest()
    event_id = "CAE-RECEIPT-LINK-" + hashlib.sha256(f"{payload.factory_id}|{user.id}|{payload.request_id}".encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id,
        CartonAuditEvent.factory_id == payload.factory_id))
    if previous:
        if json.loads(previous.detail_json).get("request_fingerprint") != digest:
            raise HTTPException(409, "此关联提交标识已用于其他内容")
        return portal.shipment_out(db, shipment, internal=True)
    if shipment.status != "SENT" or shipment.receipt_id or shipment.revision != payload.expected_revision:
        raise HTTPException(409, "送货单状态或版本已变更，请刷新；已关联或已冲销单据不能重复关联")
    match = next(((receipt, lines) for receipt, lines in matching_receipts(db, payload.factory_id,
        shipment.supplier_id, shipment_papers(db, shipment), note_no=shipment.delivery_note_no,
        reversed_ids=reversed_candidates(shipment)) if receipt.id == payload.receipt_id), None)
    if match is None:
        raise HTTPException(409, "原收料不符合整单关联条件：须同厂区、供应商、纸品与数量，已入库且未冲销、未关联")
    receipt, receipt_lines = match
    if receipt.revision != payload.expected_receipt_revision:
        raise HTTPException(409, "原收料版本已变更，请刷新")
    day = acceptance_day(receipt)
    settlement.ensure_open(db, payload.factory_id, shipment.supplier_id, day[:7])
    settlement.ensure_open(db, payload.factory_id, shipment.supplier_id, shipment.delivery_date[:7])
    formal, _ = portal._shipment_sources(db, shipment)
    by_id = {line.order_line_id: line for line in receipt_lines}
    accepted = {"acceptance_date": day, "linked_existing_receipt": True,
        "registration_mode": "EXISTING_RECEIPT", "lines": [{"shipment_line_id": source.id,
            **{key: str(getattr(by_id[source.order_line_id], key)) for key in ("received_quantity", "damaged_quantity", "rejected_quantity", "unusable_quantity")},
            "difference_reason": payload.reason, "no_order_decision": ""} for source in formal]}
    shipment.receipt_id = receipt.id
    shipment.status = "RECEIVED"
    shipment.revision += 1
    shipment.confirmed_by = user.id
    shipment.confirmed_at = portal.now_text()
    shipment.confirmation_request_id = payload.request_id
    shipment.confirmation_fingerprint = digest
    shipment.acceptance_json = json.dumps(accepted, ensure_ascii=False)
    event = portal._audit(db, user, payload.factory_id, EVENT, "supplier_shipment", shipment.id,
        {"request_fingerprint": digest, "request_id": payload.request_id, "receipt_id": receipt.id,
         "receipt_revision": receipt.revision, "reason": payload.reason, "acceptance": accepted})
    event.id = event_id
    if receipt.status == "REVERSED":
        # Candidate may have been reversed after the vendor uploaded its late document.
        # Bind the original lineage, then use the existing reasoned correction flow.
        portal.reopen_reversed_shipment(db, receipt, user, payload.reason)
    else:
        portal.shipment_notifications.handle_notification(db, shipment)
    db.commit()
    return portal.shipment_out(db, shipment, internal=True)
