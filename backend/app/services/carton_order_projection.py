"""Request-local, page-bounded inputs for the existing order business projection."""
from collections import defaultdict

from sqlalchemy import select

from app.models.carton_procurement import (
    CartonAuditEvent, CartonInventoryMovement, CartonOrderLine,
    CartonPurchaseOrderIssue, CartonReceiptLine,
)
from app.models.carton_supplier_portal import SupplierAttachment, SupplierCommitment, SupplierShipmentLine


def order_page_out(db, orders, *, usage=None):
    from app.services import carton_procurement as core
    from app.services.carton_order_split import plans
    from app.services.carton_replenishment_receipts import options_by_line, legacy_review_lines
    from app.services.carton_usage import usage_by_key

    if not orders:
        return []
    factory = orders[0].factory_id
    if any(order.factory_id != factory for order in orders):
        raise ValueError("A projection must belong to one factory")
    order_ids = [order.id for order in orders]
    lines = list(db.scalars(select(CartonOrderLine).where(
        CartonOrderLine.order_id.in_(order_ids)).order_by(CartonOrderLine.line_no)))
    by_order = defaultdict(list)
    for line in lines:
        by_order[line.order_id].append(line)
    line_ids = [line.id for line in lines]
    issues = list(db.scalars(select(CartonPurchaseOrderIssue).where(
        CartonPurchaseOrderIssue.factory_id == factory,
        CartonPurchaseOrderIssue.order_id.in_(order_ids)).order_by(CartonPurchaseOrderIssue.issue_sequence.desc())))
    by_issue_order = defaultdict(list)
    for issue in issues:
        by_issue_order[issue.order_id].append(issue)
    split_by_order = defaultdict(list)
    for plan in plans(db, factory):
        if plan["order_id"] in order_ids:
            split_by_order[plan["order_id"]].append(plan)
    events = list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory, CartonAuditEvent.entity_id.in_(order_ids),
        CartonAuditEvent.event_type.in_(["HISTORY_ORDER_IMPORTED", "ORDER_APPENDED"])
    ).order_by(CartonAuditEvent.sequence.desc())))
    history, append_details = set(), defaultdict(list)
    for event in events:
        if event.event_type == "HISTORY_ORDER_IMPORTED":
            history.add(event.entity_id)
        elif event.entity_type == "carton_order":
            append_details[event.entity_id].append(event.detail_json)
    business_lines = set(db.scalars(select(CartonReceiptLine.order_line_id).where(CartonReceiptLine.order_line_id.in_(line_ids))))
    business_lines.update(db.scalars(select(CartonInventoryMovement.order_line_id).where(CartonInventoryMovement.order_line_id.in_(line_ids))))
    supplier_lines = set(db.scalars(select(SupplierShipmentLine.order_line_id).where(SupplierShipmentLine.order_line_id.in_(line_ids))))
    commitments = list(db.scalars(select(SupplierCommitment).where(
        SupplierCommitment.factory_id == factory, SupplierCommitment.order_line_id.in_(line_ids))))
    supplier_lines.update(row.order_line_id for row in commitments)
    commitment_by_line = defaultdict(list)
    for row in commitments:
        commitment_by_line[row.order_line_id].append(row)
    attachments = set(db.scalars(select(SupplierAttachment.order_id).where(SupplierAttachment.order_id.in_(order_ids))))
    shared = {
        "options": options_by_line(db, factory, line_ids),
        "review": legacy_review_lines(db, factory, line_ids),
        "protected": core.protected_by_line(db, line_ids),
        "received": core.fulfilled_by_line(db, line_ids),
        "replenished": core.replenished_by_line(db, line_ids),
        "pending": core._pending_received_by_line(db, line_ids),
    }
    usage = usage if usage is not None else usage_by_key(db, factory)
    result = []
    for order in orders:
        own_lines = by_order[order.id]
        own_ids = {line.id for line in own_lines}
        projection = {**shared, "lines": own_lines, "issues": by_issue_order[order.id],
            "plans": split_by_order[order.id], "history_imported": order.id in history,
            "append_details": append_details[order.id],
            "business_activity": bool(own_ids & business_lines),
            "supplier_evidence": bool(own_ids & supplier_lines) or order.id in attachments,
            "commitments": [row for identifier in own_ids for row in commitment_by_line[identifier]]}
        result.append(core.order_out(db, order, usage=usage, projection=projection))
    return result
