"""Independent B-source promises and shipment capacity; ordinary demand is separate."""
import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierShipment, SupplierShipmentLine

EVENT = "SUPPLIER_REPLENISHMENT_ACCEPTED"


def commitment(db, factory, issue_id, line_id):
    rows = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type == EVENT, CartonAuditEvent.entity_id == issue_id)
        .order_by(CartonAuditEvent.sequence.desc()))
    return next((json.loads(row.detail_json) for row in rows if json.loads(row.detail_json)["line_id"] == line_id), {})


def validate_issue(db, order, issue_id, *, allow_dispute=False):
    issue = db.get(CartonPurchaseOrderIssue, issue_id)
    if not issue or issue.factory_id != order.factory_id or issue.order_id != order.id or not json.loads(issue.snapshot_json).get("replenishment"):
        raise HTTPException(409, "补单版本不属于当前订单，请刷新核对")
    if order.deleted_at or order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        raise HTTPException(409, "原订单已结束或删除，不能执行补单")
    from app.services.carton_supplier_changes import response_state
    if not allow_dispute and response_state(db, order.factory_id, "REPLENISHMENT", issue.id).get("status") == "DISPUTED":
        raise HTTPException(409, "此补单存在供应商异议，请从变更待办重新整单确认")
    return issue


def reservations(db, factory, line_ids):
    from app.services import carton_supplier_portal as portal, carton_shipment_receiving as receiving
    result, projections = {}, {}
    for paper, shipment in db.execute(select(SupplierShipmentLine, SupplierShipment).join(SupplierShipment,
        SupplierShipment.id == SupplierShipmentLine.shipment_id).where(SupplierShipment.factory_id == factory,
        SupplierShipmentLine.order_line_id.in_(line_ids))):
        if portal.receipt_link.link_only(shipment): continue
        if shipment.id not in projections:
            formal, unmatched = portal._shipment_sources(db, shipment)
            projections[shipment.id] = receiving.progress(db, shipment, formal + unmatched)[2]
        key = (paper.issue_id, paper.order_line_id)
        result[key] = result.get(key, Decimal(0)) + projections[shipment.id][paper.id]["reserved_quantity"]
    return result


def sources(db, order):
    from app.services import carton_procurement as core
    from app.services.carton_supplier_changes import response_states
    from app.services.carton_replenishment_receipts import options_by_line, receipt_links
    ids = [line.id for line in core.get_order_lines(db, order.id)]
    options = options_by_line(db, order.factory_id, ids)
    reserved = reservations(db, order.factory_id, ids)
    links, posted = receipt_links(db, order.factory_id), {}
    for paper in db.scalars(select(CartonReceiptLine).join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(CartonReceipt.factory_id == order.factory_id, CartonReceipt.status == "POSTED", CartonReceiptLine.order_line_id.in_(ids))):
        if paper.id in links:
            key = (links[paper.id]["replenishment_issue_id"], paper.order_line_id)
            posted[key] = posted.get(key, Decimal(0)) + paper.effective_quantity
    result = []
    issues = list(core._purchase_order_issues(db, order.id))
    states = response_states(db, order.factory_id, "REPLENISHMENT", [issue.id for issue in issues
        if core._purchase_order_snapshot(issue).get("replenishment")])
    for issue in issues:
        snapshot = core._purchase_order_snapshot(issue)
        replacement = snapshot.get("replenishment")
        if not replacement: continue
        disputed = states[issue.id]["status"] == "DISPUTED"
        papers = []
        for line in snapshot.get("lines", []):
            required = Decimal(str(line.get("required_quantity_delta", "0")))
            if required <= 0: continue
            promise = commitment(db, order.factory_id, issue.id, line["id"])
            quota = next((Decimal(item["remaining_quantity"]) for item in options.get(line["id"], []) if item["replenishment_issue_id"] == issue.id), Decimal(0))
            shipping = reserved.get((issue.id, line["id"]), Decimal(0))
            papers.append({**{key: line.get(key, "") for key in ("id", "line_no", "packaging_type", "paper_quality", "specification", "dimension_unit", "unit")},
                "order_line_id": line["id"], "child_no": f"{issue.document_no}/{int(line['line_no']):02d}",
                "required_quantity": str(required), "remaining_to_ship": str(max(Decimal(0), quota-shipping)) if not order.deleted_at and order.status != "CANCELLED" else "0",
                "received_quantity": str(posted.get((issue.id, line["id"]), Decimal(0))), "in_transit_quantity": str(shipping),
                "accepted": bool(promise) and not disputed, "commitment_revision": promise.get("revision", 0), "promised_date": promise.get("promised_date", ""),
                "shipping_blocked_reason": "供应商有异议，请在变更待办重新确认" if disputed else "", "responsibility": replacement["responsibility"]})
        result.append({"issue_id": issue.id, "document_no": issue.document_no, "responsibility": replacement["responsibility"],
            "planned_date": snapshot.get("after_due_date", ""), "lines": papers})
    return result


def ordinary_capacity(db, order, line_id):
    from app.services import carton_procurement as core, carton_supplier_portal as portal
    from app.services.carton_replenishment_receipts import options_by_line, legacy_review_lines
    if line_id in legacy_review_lines(db, order.factory_id, [line_id]): return Decimal(0)
    line = next(line for line in core.get_order_lines(db, order.id) if line.id == line_id)
    options = options_by_line(db, order.factory_id, [line_id]).get(line_id, [])
    replacement_ids = {item["replenishment_issue_id"] for item in options}
    reserved = reservations(db, order.factory_id, [line_id])
    ordinary_reserved = sum((value for (issue_id, _), value in reserved.items() if issue_id not in replacement_ids), Decimal(0))
    return max(Decimal(0), line.required_quantity - portal.fulfilled_by_line(db, [line_id]).get(line_id, 0)
        - core._pending_received_by_line(db, [line_id]).get(line_id, 0)
        - sum((Decimal(item["remaining_quantity"]) for item in options), Decimal(0)) - ordinary_reserved)


def acceptance(source):
    count = sum(line["accepted"] for line in source["lines"])
    total = len(source["lines"])
    status = "ACCEPTED" if total and count == total else "PARTIAL" if count else "NOT_ACCEPTED"
    return dict(status=status, label="补单已确认接单" if status == "ACCEPTED" else "补单待确认接单", accepted_line_count=count,
        total_line_count=total, accepted_at="", delivery_differences=[], issue_id=source["issue_id"], document_no=source["document_no"])
