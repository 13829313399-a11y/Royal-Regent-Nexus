"""Bounded, request-local evidence for supplier reads; never used by write guards.

Authorization selects the orders before entering here. Quantities still come from
the canonical receipt/replenishment functions, with no cache across requests.
"""
from collections import defaultdict

from sqlalchemy import select

from app.models.carton_procurement import CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierAttachment
from app.services.carton_supplier_read_inputs import batches, order_inputs


def order_page_out(db, orders, *, internal=False):
    from app.services import carton_supplier_portal as portal
    from app.services import carton_replenishment_supplier as replacement
    from app.services.carton_replenishment_receipts import legacy_review_lines, options_by_line, receipt_links
    from app.services.carton_material_correction import records
    from app.services.carton_order_split import plans
    from app.services.carton_order_split_trace import schedule_split_sources
    result = []
    for batch in batches(orders):
        projected = order_inputs(db, batch)
        # Match order_out's early return before evaluating any quantity evidence.
        batch = [order for order in batch if internal or portal.latest_issue(db, order, projection=projected[order.id])]
        if not batch:
            continue
        factory = batch[0].factory_id
        line_ids = [line.id for order in batch for line in projected[order.id]["lines"]]
        fulfilled, pending, shipped, options, reserved, blocked, posted = {}, {}, {}, {}, {}, set(), defaultdict(int)
        links = receipt_links(db, factory) if projected[batch[0].id]["replacement_states"] else {}
        for ids in batches(line_ids):
            fulfilled.update(portal.fulfilled_by_line(db, ids))
            pending.update(portal._pending_received_by_line(db, ids))
            shipped.update(portal.outstanding(db, ids))
            options.update(options_by_line(db, factory, ids))
            blocked.update(legacy_review_lines(db, factory, ids))
            reserved.update(replacement.reservations(db, factory, ids))
            if not links:
                continue
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
