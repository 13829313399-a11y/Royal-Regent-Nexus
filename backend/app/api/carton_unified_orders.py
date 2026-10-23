"""Authorized combined order ledger; paginate only after merging both source sets."""
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services import carton_procurement as core, carton_special_requests as special
from app.services.carton_order_projection import order_page_out

router = APIRouter(prefix="/api/carton-unified-orders", tags=["carton-procurement"])

from app.schemas.carton_unified_orders import Selection, BatchAction
from app.services import carton_unified_order_actions as actions


@router.post("/selected")
def selected(payload: Selection, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return actions.selected(db, user, payload)


@router.post("/batch-actions")
def batch_actions(payload: BatchAction, request: Request, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return actions.perform(db, user, payload, refresh_actor=lambda: get_current_user(request, db))


@router.get("")
def ledger(factory_id: str, responsibility_scope: Literal["OWN", "ALL"] = "OWN",
           kind: Literal["ALL", "PURCHASE", "SAMPLE", "WORKSHOP_MISC", "SUPPLIER_GIFT"] = "ALL",
           search: str = Query("", max_length=128), customer_name: str = Query("", max_length=128),
           status_filter: str = Query("", max_length=32),
           order_from: str = Query("", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
           order_to: str = Query("", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
           due_filter: Literal["ALL", "OVERDUE", "TODAY", "DUE_SOON", "UPCOMING"] = "ALL",
           sort: Literal["ORDER_DESC", "DUE_ASC", "DUE_DESC"] = "DUE_ASC",
           collaboration_filter: Literal["ALL", "NOT_ISSUED", "PENDING_CHANGE", "PENDING", "PARTIAL", "ACCEPTED", "NOT_REQUIRED", "CANCELLED", "LATE_PROMISE"] = "ALL",
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
           db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    special.access(db, user, factory_id)
    rows = []
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
            status_filter=status_filter, order_from=order_from, order_to=order_to, due_filter=due_filter,
            sort=sort, collaboration_filter=collaboration_filter)
        rows.extend({"kind": "PURCHASE", "model": row, "date": row.order_date, "due": row.due_date or "", "number": row.order_no,
                     "level": due_level(row.status, row.due_date)} for row in regular)
    if kind != "PURCHASE":
        for row in special.workspace(db, user, factory_id, responsibility_scope=responsibility_scope)["items"]:
            if kind != "ALL" and row["kind"] != kind: continue
            if customer_name and row["customer_name"] != customer_name: continue
            date = row.get("created_at", "")[:10]
            if order_from and date < order_from or order_to and date > order_to: continue
            status = row["status"]
            if status_filter and status_filter != status: continue
            collaboration = "NOT_ISSUED" if status == "SUBMITTED" else "CANCELLED" if status == "CANCELLED" else "NOT_REQUIRED"
            if collaboration_filter != "ALL" and collaboration_filter != collaboration: continue
            level = due_level(status, row["required_date"])
            if due_filter != "ALL" and level != {"OVERDUE": 0, "TODAY": 1, "DUE_SOON": 2, "UPCOMING": 3}[due_filter]: continue
            values = [row.get(key, "") for key in ("request_no", "requester_name", "customer_name", "purpose", "status")]
            values.extend(str(line.get(key, "")) for line in row["lines"] for key in ("packaging_type", "paper_quality", "specification", "item_no"))
            if search.strip().casefold() not in " ".join(values).casefold(): continue
            rows.append({"kind": row["kind"], "special": row, "date": date, "due": row["required_date"], "number": row["request_no"], "level": level})
    if sort == "DUE_ASC": rows.sort(key=lambda row: (row["level"], row["due"], row["number"]))
    elif sort == "DUE_DESC":
        rows.sort(key=lambda row: row["number"])
        rows.sort(key=lambda row: row["due"], reverse=True)
    else: rows.sort(key=lambda row: (row["date"], row["number"]), reverse=True)
    page = rows[offset:offset + limit]
    projected = {row.order_no: row for row in order_page_out(db, [item["model"] for item in page if item["kind"] == "PURCHASE"])}
    return {"items": [{"kind": item["kind"], "order": projected[item["number"]]} if item["kind"] == "PURCHASE"
                      else {"kind": item["kind"], "special": item["special"]} for item in page],
            "total": len(rows), "can_create": special.can_submit(user, factory_id),
            "statistics": {"overdue": sum(item["level"] == 0 for item in rows), "today": sum(item["level"] == 1 for item in rows),
                           "dueSoon": sum(item["level"] == 2 for item in rows), "pending": sum(item["level"] != 5 for item in rows)}}
