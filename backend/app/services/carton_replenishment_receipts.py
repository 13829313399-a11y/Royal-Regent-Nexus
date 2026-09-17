"""Immutable receipt-to-replacement links, reservations and payable treatment."""
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine

EVENT = "RECEIPT_REPLENISHMENT_LINKED"
NORMAL_EVENT = "RECEIPT_ORDINARY_CLASSIFIED"


def receipt_links(db, factory):
    return {event.entity_id: json.loads(event.detail_json) for event in db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory, CartonAuditEvent.event_type == EVENT))}


def legacy_review_lines(db, factory, line_ids):
    """Never guess the responsibility of old, unlinked receipts after a B issue."""
    movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory,
        CartonInventoryMovement.order_line_id.in_(line_ids), CartonInventoryMovement.source_type == "ORDER_REPLENISHMENT")))
    if not movements:
        return set()
    events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type.in_([EVENT, NORMAL_EVENT, "INVENTORY_MOVEMENT_CREATED", "RECEIPT_CONFIRMED"]))))
    classified = {e.entity_id for e in events if e.event_type in {EVENT, NORMAL_EVENT}}
    sequence = {e.entity_id: e.sequence for e in events if e.event_type in {"INVENTORY_MOVEMENT_CREATED", "RECEIPT_CONFIRMED"}}
    first = {}
    for movement in movements:
        first[movement.order_line_id] = min(first.get(movement.order_line_id, float("inf")), sequence.get(movement.id, 0))
    if not first:
        return set()
    return {line.order_line_id for line, receipt in db.execute(select(CartonReceiptLine, CartonReceipt).join(
        CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id).where(CartonReceipt.factory_id == factory,
        CartonReceipt.status == "POSTED", CartonReceiptLine.order_line_id.in_(list(first)), CartonReceiptLine.effective_quantity > 0))
        if line.id not in classified and (receipt.id not in sequence or sequence[receipt.id] > first[line.order_line_id])}


def options_by_line(db, factory, line_ids, *, exclude_receipt=None):
    movements = list(db.scalars(select(CartonInventoryMovement).where(
        CartonInventoryMovement.factory_id == factory, CartonInventoryMovement.order_line_id.in_(line_ids),
        CartonInventoryMovement.source_type == "ORDER_REPLENISHMENT")))
    if not movements:
        return {}
    blocked = legacy_review_lines(db, factory, line_ids)
    links = receipt_links(db, factory)
    used = defaultdict(Decimal)
    for line, receipt in db.execute(select(CartonReceiptLine, CartonReceipt).join(
        CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id).where(
        CartonReceipt.factory_id == factory, CartonReceipt.status.in_(["PENDING_CONFIRMATION", "POSTED"]),
        CartonReceiptLine.order_line_id.in_(line_ids))):
        if receipt.id != exclude_receipt and line.id in links:
            used[(links[line.id]["replenishment_issue_id"], line.order_line_id)] += line.effective_quantity
    grouped = defaultdict(list)
    for movement in movements:
        grouped[(movement.source_id, movement.order_line_id)].append(movement)
    result = defaultdict(list)
    for (issue_id, line_id), rows in grouped.items():
        if line_id in blocked:
            continue
        issue = db.get(CartonPurchaseOrderIssue, issue_id)
        if not issue or issue.factory_id != factory:
            raise HTTPException(409, "补单出库缺少采购单依据，请核实")
        evidence = json.loads(issue.snapshot_json)["replenishment"]
        total = -sum((r.quantity for r in rows), Decimal(0))
        remaining = total - used[(issue_id, line_id)]
        if remaining > 0:
            result[line_id].append({"replenishment_issue_id": issue_id, "document_no": issue.document_no,
                "responsibility": evidence["responsibility"], "remaining_quantity": str(remaining)})
    return dict(result)


def select_link(db, factory, order_line, qty, issue_id, *, exclude_receipt=None):
    from app.services import carton_procurement as core
    if order_line.id in legacy_review_lines(db, factory, [order_line.id]):
        raise HTTPException(409, "历史补单后存在未关联的收料，不能判断责任及剩余额度；请核对原收料并通过冲销重录关联补单")
    options = options_by_line(db, factory, [order_line.id], exclude_receipt=exclude_receipt).get(order_line.id, [])
    if not options and not issue_id:
        return None  # Ordinary receipts remain governed by the shared total-capacity guard.
    pending = core._pending_received_by_line(db, [order_line.id]).get(order_line.id, Decimal(0))
    if exclude_receipt:
        pending -= sum((line.effective_quantity for line in core._receipt_lines(db, exclude_receipt)
                        if line.order_line_id == order_line.id), Decimal(0))
    ordinary = max(Decimal(0), order_line.required_quantity - core.fulfilled_by_line(db, [order_line.id])[order_line.id]
                   - pending - sum((Decimal(o["remaining_quantity"]) for o in options), Decimal(0)))
    if not issue_id and qty > ordinary:
        # Backward-compatible only when there is exactly one possible source.
        if len(options) == 1 and ordinary == 0:
            issue_id = options[0]["replenishment_issue_id"]
        else:
            raise HTTPException(409, "本次收料涉及补单，请选择具体补单；普通采购与补单请分开登记")
    if not issue_id:
        return None
    option = next((o for o in options if o["replenishment_issue_id"] == issue_id), None)
    if not option or qty > Decimal(option["remaining_quantity"]):
        raise HTTPException(409, "补单不属于当前纸品或可收数量不足，请刷新核对")
    result = {**option, "quantity": str(qty)}
    if option["responsibility"] == "SUPPLIER":
        from app.services.carton_inventory_valuation import load_valuation, cost_key
        movements = list(db.scalars(select(CartonInventoryMovement).where(
            CartonInventoryMovement.factory_id == factory, CartonInventoryMovement.source_type == "ORDER_REPLENISHMENT",
            CartonInventoryMovement.source_id == issue_id, CartonInventoryMovement.order_line_id == order_line.id)))
        valuation = load_valuation(db, factory)
        if any(m.id in valuation.unpriced_movements or any(cost_key(r) == cost_key(m) for r, _ in valuation.errors) for m in movements):
            raise HTTPException(409, "原补单出库成本待核实，请先核价后登记免费补货")
        total = -sum((m.quantity for m in movements), Decimal(0))
        amount = -sum((valuation.amounts[m.id] for m in movements), Decimal(0))
        result["inventory_unit_price"] = str((amount / total).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        result["settlement_unit_price"] = "0"
    return result


def public_link(link):
    if not link:
        return {}
    return {**{key: link.get(key) for key in ("replenishment_issue_id", "document_no", "responsibility")},
            "settlement_unit_price": Decimal(link["settlement_unit_price"])}
