"""Bounded, request-local evidence for supplier reads; never used by write guards.

Authorization selects the orders before entering here. Quantities still come from
the canonical receipt/replenishment functions, with no cache across requests.
"""
from collections import defaultdict

from sqlalchemy import select

from app.models.carton_procurement import CartonOrderLine, CartonPurchaseOrderIssue, CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierAttachment, SupplierCommitment

CHUNK = 200


def evidence(db, orders):
    from app.services.carton_supplier_changes import response_states
    if not orders:
        return {}
    factory = orders[0].factory_id
    if any(order.factory_id != factory for order in orders):
        raise ValueError("Supplier projection must belong to one factory")
    identifiers = [order.id for order in orders]
    lines, issues = defaultdict(list), defaultdict(list)
    for row in db.scalars(select(CartonOrderLine).where(CartonOrderLine.factory_id == factory,
            CartonOrderLine.order_id.in_(identifiers)).order_by(CartonOrderLine.line_no)):
        lines[row.order_id].append(row)
    for row in db.scalars(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.factory_id == factory,
            CartonPurchaseOrderIssue.order_id.in_(identifiers)).order_by(CartonPurchaseOrderIssue.issue_sequence.desc())):
        issues[row.order_id].append(row)
    line_ids = [line.id for own in lines.values() for line in own]
    commitments = {}
    for start in range(0, len(line_ids), CHUNK):
        commitments.update({row.order_line_id: row for row in db.scalars(select(SupplierCommitment).where(
            SupplierCommitment.factory_id == factory, SupplierCommitment.order_line_id.in_(line_ids[start:start + CHUNK])))})
    issue_ids = [row.id for own in issues.values() for row in own]
    states = {kind: {} for kind in ("REGULAR", "REPLENISHMENT")}
    for start in range(0, len(issue_ids), CHUNK):
        for kind in states:
            states[kind].update(response_states(db, factory, kind, issue_ids[start:start + CHUNK]))
    return {order.id: {"lines": lines[order.id], "issues": issues[order.id],
        "commitments": [commitments[line.id] for line in lines[order.id] if line.id in commitments],
        "supplier_change_states": states["REGULAR"], "replacement_states": states["REPLENISHMENT"]}
        for order in orders}


def order_page_out(db, orders, *, internal=False):
    from app.services import carton_supplier_portal as portal
    from app.services import carton_replenishment_supplier as replacement
    from app.services.carton_replenishment_receipts import legacy_review_lines, options_by_line, receipt_links
    from app.services.carton_material_correction import records
    from app.services.carton_order_split import plans
    from app.services.carton_order_split_trace import schedule_split_sources
    result = []
    for start in range(0, len(orders), CHUNK):
        batch = orders[start:start + CHUNK]
        projected = evidence(db, batch)
        # Match order_out's early return before evaluating any quantity evidence.
        batch = [order for order in batch if internal or portal.latest_issue(db, order, projection=projected[order.id])]
        if not batch:
            continue
        factory = batch[0].factory_id
        line_ids = [line.id for order in batch for line in projected[order.id]["lines"]]
        fulfilled, pending, shipped, options, reserved, blocked, posted = {}, {}, {}, {}, {}, set(), defaultdict(int)
        links = receipt_links(db, factory)
        for offset in range(0, len(line_ids), CHUNK):
            ids = line_ids[offset:offset + CHUNK]
            fulfilled.update(portal.fulfilled_by_line(db, ids))
            pending.update(portal._pending_received_by_line(db, ids))
            shipped.update(portal.outstanding(db, ids))
            options.update(options_by_line(db, factory, ids))
            blocked.update(legacy_review_lines(db, factory, ids))
            reserved.update(replacement.reservations(db, factory, ids))
            for paper in db.scalars(select(CartonReceiptLine).join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
                    .where(CartonReceipt.factory_id == factory, CartonReceipt.status == "POSTED", CartonReceiptLine.order_line_id.in_(ids))):
                if paper.id in links:
                    posted[(links[paper.id]["replenishment_issue_id"], paper.order_line_id)] += paper.effective_quantity
        corrections, splits = records(db, factory), plans(db, factory)
        traces = schedule_split_sources(db, batch)
        attachments = defaultdict(list)
        for row in db.scalars(select(SupplierAttachment).where(SupplierAttachment.factory_id == factory,
                SupplierAttachment.order_id.in_([order.id for order in batch])).order_by(SupplierAttachment.created_at.desc())):
            attachments[row.order_id].append(row)
        for order in batch:
            own = projected[order.id]
            own.update(fulfilled=fulfilled, pending=pending, outstanding=shipped, options=options,
                reserved=reserved, legacy_review=blocked, replacement_posted=posted,
                corrections=[row for row in corrections if row["order_id"] == order.id],
                split_records=[row for row in splits if row["order_id"] == order.id],
                schedule_source=traces.get(order.id), attachments=attachments[order.id])
            result.append(portal.order_out(db, order, internal=internal, projection=own))
    return result
