"""Bounded, call-local inputs for existing supplier business readers.

Only list callers opt in. Mutation paths keep their fresh canonical reads; no
session/global cache, permission decision or response is reused across requests.
"""
from collections import defaultdict

from sqlalchemy import select

from app.models.carton_procurement import CartonOrderLine, CartonPurchaseOrderIssue
from app.models.carton_supplier_portal import SupplierAttachment, SupplierCommitment


def batches(rows, size=200):
    for offset in range(0, len(rows), size):
        yield rows[offset:offset + size]


def order_inputs(db, orders, *, receiving=False):
    from app.services import carton_procurement as core
    from app.services.carton_supplier_changes import response_states

    if not orders:
        return {}
    factory = orders[0].factory_id
    if len(orders) > 200 or any(order.factory_id != factory for order in orders):
        raise ValueError("Supplier read inputs require one factory and at most 200 orders")
    ids = [order.id for order in orders]
    lines = list(db.scalars(select(CartonOrderLine).where(
        CartonOrderLine.factory_id == factory, CartonOrderLine.order_id.in_(ids))
        .order_by(CartonOrderLine.line_no)))
    issues = list(db.scalars(select(CartonPurchaseOrderIssue).where(
        CartonPurchaseOrderIssue.factory_id == factory, CartonPurchaseOrderIssue.order_id.in_(ids))
        .order_by(CartonPurchaseOrderIssue.issue_sequence.desc())))
    by_line, by_issue, by_commitment = defaultdict(list), defaultdict(list), defaultdict(list)
    for line in lines:
        by_line[line.order_id].append(line)
    for issue in issues:
        by_issue[issue.order_id].append(issue)
    line_ids = [line.id for line in lines]
    commitments = []
    for part in batches(line_ids):
        commitments.extend(db.scalars(select(SupplierCommitment).where(
            SupplierCommitment.factory_id == factory, SupplierCommitment.order_line_id.in_(part))))
    line_orders = {line.id: line.order_id for line in lines}
    for item in commitments:
        by_commitment[line_orders[item.order_line_id]].append(item)
    states = {}
    for part in batches([issue.id for issue in issues]):
        states.update(response_states(db, factory, "REGULAR", part))
    shared = {"supplier_change_states": states}
    if receiving:
        from app.services import carton_supplier_portal as portal, carton_replenishment_supplier as replacement
        from app.services.carton_material_correction import records, HOLD
        from app.services.carton_order_split import plans
        from app.services.carton_order_split_trace import schedule_split_sources
        from app.services.carton_replenishment_receipts import options_by_line, legacy_review_lines

        corrections = records(db, factory)
        split_plans = plans(db, factory)
        attachments = defaultdict(list)
        for row in db.scalars(select(SupplierAttachment).where(SupplierAttachment.factory_id == factory, SupplierAttachment.order_id.in_(ids))
                              .order_by(SupplierAttachment.created_at.desc())):
            attachments[row.order_id].append(row)
        shared.update(fulfilled={}, pending={}, outstanding={}, options={}, reserved={}, legacy=set(),
                      material_holds={r['order_line_id']: r for r in corrections if r['status'] in HOLD})
        for part in batches(line_ids):
            shared['fulfilled'].update(core.fulfilled_by_line(db, part))
            shared['pending'].update(core._pending_received_by_line(db, part))
            shared['outstanding'].update(portal.outstanding(db, part))
            shared['options'].update(options_by_line(db, factory, part))
            shared['reserved'].update(replacement.reservations(db, factory, part))
            shared['legacy'].update(legacy_review_lines(db, factory, part))
        split_sources = schedule_split_sources(db, orders)
    result = {}
    for order in orders:
        own = dict(shared, lines=by_line[order.id], issues=by_issue[order.id], commitments=by_commitment[order.id])
        if receiving:
            own.update(corrections=[r for r in corrections if r['order_id'] == order.id],
                       plans=[p for p in split_plans if p['order_id'] == order.id],
                       attachments=attachments[order.id], schedule_split_source=split_sources.get(order.id))
        result[order.id] = own
    return result
