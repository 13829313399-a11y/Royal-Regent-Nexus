"""Authorized combined order ledger; paginate only after merging both source sets."""
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services import carton_order_queries as queries

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
    return queries.ledger(db, user, factory_id, responsibility_scope=responsibility_scope,
        kind=kind, search=search, customer_name=customer_name, status_filter=status_filter,
        order_from=order_from, order_to=order_to, due_filter=due_filter, sort=sort,
        collaboration_filter=collaboration_filter, limit=limit, offset=offset)
