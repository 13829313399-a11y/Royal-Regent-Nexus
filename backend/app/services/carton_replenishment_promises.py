"""Warehouse follow-up for independent B promises, using existing immutable evidence."""
import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonOrder, CartonPurchaseOrderIssue
from app.services import carton_replenishment_supplier as replacements


def notices(db, factory, acknowledged):
    events = db.execute(select(CartonAuditEvent, CartonPurchaseOrderIssue, CartonOrder)
        .join(CartonPurchaseOrderIssue, CartonPurchaseOrderIssue.id == CartonAuditEvent.entity_id)
        .join(CartonOrder, CartonOrder.id == CartonPurchaseOrderIssue.order_id)
        .where(CartonAuditEvent.factory_id == factory, CartonAuditEvent.event_type == replacements.EVENT,
            CartonPurchaseOrderIssue.factory_id == factory, CartonOrder.factory_id == factory,
            CartonOrder.deleted_at.is_(None))
        .order_by(CartonAuditEvent.sequence.desc()))
    contexts, current, late, changes = {}, set(), [], []
    for event, issue, order in events:
        try:
            detail = json.loads(event.detail_json)
            if not isinstance(detail, dict):
                continue
            line_id = str(detail.get("line_id") or "")
            promised = str(detail.get("promised_date") or "")
            previous = str(detail.get("previous_promised_date") or "")
            date.fromisoformat(promised)
        except (ValueError, TypeError):
            continue
        if detail.get("issue_id", issue.id) != issue.id or previous == promised:
            continue  # Saving an unchanged date never creates another follow-up.
        if order.id not in contexts:
            contexts[order.id] = {source["issue_id"]: source for source in replacements.sources(db, order)}
        source = contexts[order.id].get(issue.id)
        paper = next((row for row in source["lines"] if row["id"] == line_id), None) if source else None
        if not paper:
            continue
        common = {"id": event.id, "source_kind": "REPLENISHMENT", "issue_id": issue.id,
            "document_no": issue.document_no, "order_id": order.id, "order_no": order.order_no,
            "order_line_id": line_id, "customer_name": order.customer_name,
            "packaging_type": paper["packaging_type"], "line_no": paper["line_no"],
            "planned_date": source["planned_date"], "promised_date": promised,
            "actor_name": event.actor_name, "created_at": event.created_at}
        if previous and f"CHANGE:{event.id}" not in acknowledged:
            changes.append({**common, "key": f"CHANGE:{event.id}", "previous_promised_date": previous})
        # Unacknowledged changes remain visible after completion or dispute.
        # Only the current late-delivery reminder requires outstanding goods.
        if (order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"} or not paper["accepted"]
                or Decimal(paper["remaining_to_ship"]) + Decimal(paper["in_transit_quantity"]) <= 0):
            continue
        pair = (issue.id, line_id)
        if pair in current:
            continue
        current.add(pair)
        # Bind acknowledgement to the latest actual date change. A later return
        # to an earlier date is new evidence; repeated saves of that date are not.
        key = f"B_LATE:{event.id}"
        try:
            days = (date.fromisoformat(paper["promised_date"]) - date.fromisoformat(source["planned_date"])).days
        except (ValueError, TypeError):
            continue
        if days > 0 and key not in acknowledged:
            late.append({**common, "key": key, "promised_date": paper["promised_date"], "difference_days": days})
    return late, changes
