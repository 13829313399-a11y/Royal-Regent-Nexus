from typing import Annotated, Any
from fastapi import APIRouter, Body, Depends, File, Query, UploadFile, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import spray_production as m
from app.services import spray_production as s
from app.services.auth import AuthContext, get_current_user, ensure_permission_in_scope, has_permission_in_scope
from app.services.spray_imports import store_source, apply_source, MAX_BYTES
from app.services.spray_scheduling import suggest
from app.services.spray_exports import EXPORTS, workbook_bytes

router = APIRouter(prefix="/api/spray-production", tags=["spray-production"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]
PERMISSIONS = {"orders": "order_write", "order-update": "order_write", "prepare": "plan", "resources": "master_write", "receipts": "logistics",
               "schedule-preview": "plan", "schedule-apply": "plan", "task-state": "report", "reports": "report", "report-correct": "quality", "quality": "quality",
               "rates": "cost_write", "rate-activate": "cost_write", "shipments": "logistics", "returns": "logistics", "returnables": "logistics",
               "settlements": "settlement", "purchases": "cost_write", "material-events": "cost_write", "import-apply": "import"}
s.ACTIONS["import-apply"] = apply_source
s.ACTIONS["schedule-suggest"] = suggest
PERMISSIONS["schedule-suggest"] = "plan"
PERMISSIONS["price-set"] = "cost_write"


def authorize(db, user, factory, permission="read"):
    if factory not in s.FACTORIES:
        s.fail("请选择华兴、华康 A、华康 B 或华登；集团不记库存")
    ensure_permission_in_scope(db, user, "spray_production:" + permission, factory, "production")


def cost_allowed(user, factory):
    return has_permission_in_scope(user, "spray_production:cost_read", factory, "production")


@router.get('/exports/{kind}')
def export(kind: str, factory_id: str, db: Db, user: User):
    authorize(db, user, factory_id, 'read')
    authorize(db, user, factory_id, 'export')
    if kind not in EXPORTS:
        raise HTTPException(404, '未提供该类报表')
    if EXPORTS[kind][2]:
        authorize(db, user, factory_id, 'cost_read')
    return Response(workbook_bytes(db, factory_id, kind), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="spray-{factory_id}-{kind}.xlsx"'})


@router.post("/commands/{action}")
def command(action: str, db: Db, user: User, payload: Annotated[dict[str, Any], Body()]):
    if action not in PERMISSIONS:
        raise HTTPException(404, "未找到此业务操作")
    factory = payload.get("factory_id")
    authorize(db, user, factory, PERMISSIONS[action])
    try:
        if action in ("reports", "report-correct") and any(v.get("rate_id") for v in s.rows(payload.get("lines"))):
            authorize(db, user, factory, "cost_write")
        if action == "orders" and any(v.get("price") not in (None, "") for v in s.rows(payload.get("lines"))):
            authorize(db, user, factory, "cost_write")
        result = s.execute(db, factory, user.id, action, payload)
        db.commit()
        return result
    except (IntegrityError, OperationalError):
        db.rollback()
        raise HTTPException(409, "单据重复或并发状态已变化，请刷新核对后重试")
    except (KeyError, TypeError, ValueError):
        db.rollback()
        raise HTTPException(422, "明细字段不完整或格式错误，请检查输入")
    except Exception:
        db.rollback()
        raise


COLLECTIONS = {"orders": m.SprayOrder, "lines": m.SprayOrderLine, "steps": m.SprayStep, "resources": m.SprayResource,
               "batches": m.SprayBatch, "tasks": m.SprayTask, "reports": m.SprayReport, "report-lines": m.SprayReportLine,
               "shipments": m.SprayShipment, "shipment-lines": m.SprayShipmentLine, "returnables": m.SprayReturnable,
               "rates": m.SprayRate, "settlements": m.SpraySettlement, "purchases": m.SprayPurchase, "material-events": m.SprayMaterialEvent,
               "imports": m.SprayImport}
COST_COLLECTIONS = {"rates", "settlements", "purchases", "material-events", "imports"}


def output(item, cost):
    excluded = ["content"]
    if not cost:
        excluded += ["price", "currency", "price_reference", "calculation", "people", "amount"]
    return s.serial(item, exclude=excluded)


@router.get("/collections/{kind}")
def collection(kind: str, factory_id: str, db: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000), q: str = Query("", max_length=128)):
    authorize(db, user, factory_id)
    if kind not in COLLECTIONS:
        raise HTTPException(404, "未找到此业务列表")
    cost = cost_allowed(user, factory_id)
    if kind in COST_COLLECTIONS:
        authorize(db, user, factory_id, "cost_read")
    cls = COLLECTIONS[kind]
    query = select(cls).where(cls.factory_id == factory_id)
    if q:
        search_column = getattr(cls, "document_no", getattr(cls, "product_no", getattr(cls, "name", cls.id)))
        query = query.where(search_column.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    data = list(db.scalars(query.order_by(cls.created_at.desc(), cls.id).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [output(item, cost) for item in data], "total": total, "page": page, "page_size": page_size}


@router.get("/summary")
def summary(factory_id: str, db: Db, user: User):
    authorize(db, user, factory_id)
    counts = {}
    for key, cls, condition in [("orders", m.SprayOrder, m.SprayOrder.status == "active"), ("running", m.SprayTask, m.SprayTask.status == "running"),
                                ("planned", m.SprayTask, m.SprayTask.status == "planned"), ("resources", m.SprayResource, m.SprayResource.id != "")]:
        counts[key] = db.scalar(select(func.count()).select_from(cls).where(cls.factory_id == factory_id, condition))
    return {"factory_id": factory_id, "revision": s.revision(db, factory_id), "as_of": m.now(), "data_mode": "live",
            "coverage": "no_data" if counts["orders"] == 0 else "production_records", "counts": counts,
            "permissions": [p for p in set(PERMISSIONS.values()) | {"read", "cost_read", "export"} if has_permission_in_scope(user, "spray_production:" + p, factory_id, "production")]}


@router.get("/batches/{batch_id}/trace")
def trace(batch_id: str, factory_id: str, db: Db, user: User):
    authorize(db, user, factory_id)
    batch = s.find(db, m.SprayBatch, factory_id, batch_id)
    movements = db.scalars(select(m.SprayMovement).where(m.SprayMovement.factory_id == factory_id, m.SprayMovement.batch_id == batch.id).order_by(m.SprayMovement.created_at))
    return {"batch": s.serial(batch), "balances": {k: str(v) for k, v in s.stock(db, factory_id, batch.id).items()}, "movements": [s.serial(v) for v in movements]}


@router.get("/balances")
def balances(factory_id: str, db: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(1000, ge=1, le=1000)):
    authorize(db, user, factory_id)
    ids = list(db.scalars(select(m.SprayBatch.id).where(m.SprayBatch.factory_id == factory_id).order_by(m.SprayBatch.created_at.desc(), m.SprayBatch.id).offset((page - 1) * page_size).limit(page_size)))
    # One grouped ledger query, without N+1 per-batch SQL.
    result = {i: {} for i in ids}
    for column, sign in [(m.SprayMovement.from_state, -1), (m.SprayMovement.to_state, 1)]:
        query = select(m.SprayMovement.batch_id, column, func.sum(m.SprayMovement.quantity)).where(m.SprayMovement.factory_id == factory_id, m.SprayMovement.batch_id.in_(ids)).group_by(m.SprayMovement.batch_id, column)
        for ident, state, qty in db.execute(query):
            if state:
                result[ident][state] = result[ident].get(state, s.D(0)) + sign * qty
    return {ident: {state: str(qty) for state, qty in states.items()} for ident, states in result.items()}


@router.post("/settlements/preview")
def preview_settlement(db: Db, user: User, payload: Annotated[dict[str, Any], Body()]):
    authorize(db, user, payload.get("factory_id"), "settlement")
    authorize(db, user, payload.get("factory_id"), "cost_read")
    return {**s.settlement_preview(db, payload["factory_id"], payload), "revision": s.revision(db, payload["factory_id"])}


@router.post("/imports")
async def upload(factory_id: str, db: Db, user: User, file: UploadFile = File(...)):
    authorize(db, user, factory_id, "import")
    authorize(db, user, factory_id, "cost_read")
    content = await file.read(MAX_BYTES + 1)
    try:
        result = store_source(db, factory_id, user.id, file.filename or "source", content)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "来源文件已存在，请刷新来源列表")


@router.get("/imports/{import_id}")
def import_rows(import_id: str, factory_id: str, db: Db, user: User, sheet: str = "", page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    authorize(db, user, factory_id, "cost_read")
    authorize(db, user, factory_id, "import")
    item = s.find(db, m.SprayImport, factory_id, import_id)
    names = list(db.scalars(select(m.SprayImportRow.sheet).where(m.SprayImportRow.import_id == item.id).distinct()))
    query = select(m.SprayImportRow).where(m.SprayImportRow.import_id == item.id)
    if sheet:
        query = query.where(m.SprayImportRow.sheet == sheet)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {"source": output(item, True), "sheets": names, "total": total,
            "rows": [s.serial(v) for v in db.scalars(query.order_by(m.SprayImportRow.sheet, m.SprayImportRow.row_number).offset((page - 1) * page_size).limit(page_size))]}
