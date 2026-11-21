"""The native combined ledger, shared by HTTP and read-only consumers.

Authorization, responsibility, sorting and statistics are applied before pagination.
A None limit is reserved for server-side full-scope aggregation.
"""
from collections import defaultdict
from datetime import timedelta
from sqlalchemy import func, select
from app.models.carton_special_requests import SpecialLine, SpecialRequest
from app.services import carton_procurement as core, carton_special_requests as special
from app.services.carton_order_projection import order_page_out
from app.services.carton_supplier_changes import special_confirmations


ORDER_STATUS_GROUPS = {
    "UNLOCKED": ("DRAFT", "CONFIRMED", "SUBMITTED"),
    "LOCKED": ("PENDING_SUPPLIER", "SENT", "QUOTED", "READY"),
    "FOLLOW_UP": ("DRAFT", "CONFIRMED", "SUBMITTED", "PENDING_SUPPLIER", "SENT", "QUOTED", "READY", "PARTIALLY_RECEIVED"),
}


def _matches_special_confirmation(row, requested, confirmation):
    if row.status == "CANCELLED":
        return requested == "CANCELLED"
    if row.origin == "SUPPLIER_EXTRA" or row.kind == "SUPPLIER_GIFT":
        return requested == "NOT_REQUIRED"
    if row.status == "SUBMITTED" or not row.current_version_id:
        return requested == "NOT_ISSUED"
    if confirmation["status"] == "ACCEPTED":
        if requested == "LATE_PROMISE":
            return bool(row.required_date and (confirmation.get("promised_date") or "") > row.required_date)
        return requested == "ACCEPTED"
    if row.status == "COMPLETED":
        return requested == "NOT_REQUIRED"
    return requested in {"PENDING", "AWAITING_ACCEPTANCE"}


def _special_order_query(user, factory, scope, customer, statuses, kind="ALL", first="", last=""):
    query = special.internal_request_query(user, factory, scope)
    if kind != "ALL":
        query = query.where(SpecialRequest.kind == kind)
    if customer:
        query = query.where(SpecialRequest.customer_name == customer)
    if statuses:
        query = query.where(SpecialRequest.status.in_(statuses))
    if first:
        query = query.where(SpecialRequest.created_at >= first)
    if last:
        query = query.where(func.substr(SpecialRequest.created_at, 1, 10) <= last)
    return query


def _matching_special_orders(db, query, factory, search, collaboration):
    orders = list(db.scalars(query))
    needle = search.strip().casefold()
    for start in range(0, len(orders), 400):
        batch = orders[start:start + 400]
        materials = defaultdict(list)
        if needle:
            fields = (SpecialLine.packaging_type, SpecialLine.paper_quality, SpecialLine.specification, SpecialLine.item_no)
            for request_id, *paper in db.execute(select(SpecialLine.request_id, *fields).where(
                    SpecialLine.factory_id == factory, SpecialLine.request_id.in_([row.id for row in batch]))
                    .order_by(SpecialLine.request_id, SpecialLine.line_no)):
                materials[request_id].extend(paper)
        confirmations = special_confirmations(db, factory, batch) if collaboration != "ALL" else {}
        for row in batch:
            if needle:
                values = [row.request_no, row.requester_name, row.customer_name, row.purpose, row.status, *materials[row.id]]
                if needle not in " ".join(values).casefold():
                    continue
            if collaboration == "ALL" or _matches_special_confirmation(row, collaboration, confirmations[row.id]):
                yield row


def follow_up_count(db, user, factory, *, responsibility_scope, customer, search):
    """Count the dashboard's ledger filter without expanding any order details."""
    special.access(db, user, factory)
    statuses = ORDER_STATUS_GROUPS["FOLLOW_UP"]
    total = 0
    if special.allowed(user, factory, "read"):
        total, _ = core.list_orders(db, factory, user=user if responsibility_scope == "OWN" else None,
                                     customer_name=customer, status_filter=statuses, search=search.strip(), limit=0)
    query = _special_order_query(user, factory, responsibility_scope, customer, statuses)
    if search.strip():
        return total + sum(1 for _ in _matching_special_orders(db, query, factory, search, "ALL"))
    return total + db.scalar(select(func.count()).select_from(query.with_only_columns(SpecialRequest.id).subquery()))


def ledger(db, user, factory_id, *, responsibility_scope="OWN", kind="ALL", search="", customer_name="",
           status_filter="", order_from="", order_to="", due_filter="ALL", sort="DUE_ASC",
           collaboration_filter="ALL", limit=50, offset=0):
    special.access(db, user, factory_id)
    rows = []
    statuses = ORDER_STATUS_GROUPS.get(status_filter, (status_filter,) if status_filter else ())
    today = core.business_now().date()
    soon = (today + timedelta(days=3)).isoformat()
    today = today.isoformat()

    def due_level(status, due):
        if status in {"COMPLETED", "CANCELLED"}: return 5
        if not due: return 4
        return 0 if due < today else 1 if due == today else 2 if due <= soon else 3

    if special.allowed(user, factory_id, "read") and kind in {"ALL", "PURCHASE"}:
        # SQLAlchemy limit(None) leaves this authorized query untruncated. Only
        # the final combined page is projected into full purchase order outputs.
        _, regular = core.list_orders(db, factory_id, limit=None, offset=0,
            user=user if responsibility_scope == "OWN" else None, search=search.strip(), customer_name=customer_name,
            status_filter=statuses, order_from=order_from, order_to=order_to, due_filter=due_filter,
            sort=sort, collaboration_filter=collaboration_filter)
        rows.extend({"kind": "PURCHASE", "model": row, "date": row.order_date, "due": row.due_date or "", "number": row.order_no,
                     "level": due_level(row.status, row.due_date)} for row in regular)
    if kind != "PURCHASE":
        query = _special_order_query(user, factory_id, responsibility_scope, customer_name, statuses, kind, order_from, order_to)
        for row in _matching_special_orders(db, query, factory_id, search, collaboration_filter):
            level = due_level(row.status, row.required_date)
            if due_filter != "ALL" and level != {"OVERDUE": 0, "TODAY": 1, "DUE_SOON": 2, "UPCOMING": 3}[due_filter]: continue
            rows.append({"kind": row.kind, "model": row, "date": row.created_at[:10], "due": row.required_date,
                         "number": row.request_no, "level": level})
    if sort == "DUE_ASC": rows.sort(key=lambda row: (row["level"], row["due"], row["number"]))
    elif sort == "DUE_DESC":
        rows.sort(key=lambda row: row["number"])
        rows.sort(key=lambda row: row["due"], reverse=True)
    else: rows.sort(key=lambda row: (row["date"], row["number"]), reverse=True)
    page = rows[offset:] if limit is None else rows[offset:offset + limit]
    projected = {row.order_no: row for row in order_page_out(db, [item["model"] for item in page if item["kind"] == "PURCHASE"])}
    from app.services.carton_special_marks import associated_files
    special_ids = {item["model"].id for item in page if item["kind"] != "PURCHASE"}
    marks = associated_files(db, user, factory_id, request_ids=special_ids) if special_ids else {}
    return {"items": [{"kind": item["kind"], "order": projected[item["number"]]} if item["kind"] == "PURCHASE"
                      else {"kind": item["kind"], "special": special.detail(db, user, factory_id, item["model"].id,
                                                                            mark_assets_by_order=marks)} for item in page],
            "total": len(rows), "can_create": special.can_submit(user, factory_id),
            "statistics": {"overdue": sum(item["level"] == 0 for item in rows), "today": sum(item["level"] == 1 for item in rows),
                           "dueSoon": sum(item["level"] == 2 for item in rows), "pending": sum(item["level"] != 5 for item in rows)}}
