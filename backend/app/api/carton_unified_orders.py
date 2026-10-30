"""Authorized combined order ledger; paginate only after merging both source sets."""
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request, File, Form, UploadFile, HTTPException
from fastapi.responses import Response
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services import carton_order_queries as queries

router = APIRouter(prefix="/api/carton-unified-orders", tags=["carton-procurement"])

from app.schemas.carton_unified_orders import Selection, BatchAction, BatchAppend
from app.services import carton_unified_order_actions as actions


@router.post("/selected")
def selected(payload: Selection, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return actions.selected(db, user, payload)


@router.post("/batch-actions")
def batch_actions(payload: BatchAction, request: Request, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return actions.perform(db, user, payload, refresh_actor=lambda: get_current_user(request, db))


@router.post("/batch-append")
def batch_append(payload: BatchAppend, request: Request, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_batch_append import append
    return append(db, user, payload, refresh_actor=lambda: get_current_user(request, db))


@router.get("/demand-import/template")
def demand_template(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_demand_import import authorize
    authorize(db, user, factory_id)
    path = Path(__file__).resolve().parents[1] / "templates" / "carton-demand-template.xlsx"
    return Response(path.read_bytes(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="carton-demand-template.xlsx"', "Cache-Control": "private, no-store"})


def demand_file(file):
    from app.services.carton_demand_import import MAX_BYTES
    from app.services.carton_file_jobs import run_file_job
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "请使用新建需求模板 .xlsx")
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES: raise HTTPException(422, "文件不能超过 5 MiB")
    return run_file_job("demand_parse", content)


@router.post("/demand-import/preview")
def demand_preview(factory_id: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_demand_import import authorize
    authorize(db, user, factory_id)
    return demand_file(file)


@router.post("/demand-import/confirm")
def demand_confirm(request: Request, body: str = Form(..., max_length=2_000_000), file: UploadFile = File(...),
                   db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services import carton_demand_import as demand
    try: payload = demand.Confirm.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(422, "导入内容不完整，请核对分组、字段长度和所选行") from exc
    demand.authorize(db, user, payload.factory_id)
    original = demand_file(file)
    return demand.confirm(db, user, payload, original, (file.filename or "")[:255], refresh_actor=lambda: get_current_user(request, db))


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
