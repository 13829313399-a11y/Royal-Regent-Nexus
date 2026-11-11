"""Load bounded, same-factory evidence for authorized supplier list reads."""
from collections import defaultdict

from sqlalchemy import select

from app.models.carton_procurement import CartonOrderLine, CartonPurchaseOrderIssue
from app.models.carton_supplier_portal import SupplierCommitment

BATCH_SIZE = 200


def batches(rows):
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start:start + BATCH_SIZE]


def order_inputs(db, orders):
    from app.services.carton_procurement import _purchase_order_snapshot
    from app.services.carton_supplier_changes import response_states

    if not orders:
        return {}
    factory = orders[0].factory_id
    if len(orders) > BATCH_SIZE or any(order.factory_id != factory for order in orders):
        raise ValueError("Supplier read inputs require one factory and at most 200 orders")

    order_ids = [order.id for order in orders]
    lines, issues = defaultdict(list), defaultdict(list)
    for line in db.scalars(select(CartonOrderLine).where(
            CartonOrderLine.factory_id == factory, CartonOrderLine.order_id.in_(order_ids)
    ).order_by(CartonOrderLine.line_no)):
        lines[line.order_id].append(line)

    issue_ids = {"REGULAR": [], "REPLENISHMENT": []}
    for issue in db.scalars(select(CartonPurchaseOrderIssue).where(
            CartonPurchaseOrderIssue.factory_id == factory, CartonPurchaseOrderIssue.order_id.in_(order_ids)
    ).order_by(CartonPurchaseOrderIssue.issue_sequence.desc())):
        issues[issue.order_id].append(issue)
        kind = "REPLENISHMENT" if _purchase_order_snapshot(issue).get("replenishment") else "REGULAR"
        issue_ids[kind].append(issue.id)

    commitments = {}
    for line_ids in batches([line.id for own in lines.values() for line in own]):
        for row in db.scalars(select(SupplierCommitment).where(
                SupplierCommitment.factory_id == factory, SupplierCommitment.order_line_id.in_(line_ids))):
            commitments[row.order_line_id] = row

    states = {kind: {} for kind in issue_ids}
    for kind, identifiers in issue_ids.items():
        for part in batches(identifiers):
            states[kind].update(response_states(db, factory, kind, part))

    return {
        order.id: {
            "lines": lines[order.id],
            "issues": issues[order.id],
            "commitments": [commitments[line.id] for line in lines[order.id] if line.id in commitments],
            "supplier_change_states": states["REGULAR"],
            "replacement_states": states["REPLENISHMENT"],
        }
        for order in orders
    }
