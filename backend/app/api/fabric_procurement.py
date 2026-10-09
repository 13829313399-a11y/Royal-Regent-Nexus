from pathlib import PurePath
from typing import Literal
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
import json

from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user
from app.services import fabric_procurement as service
from app.services import fabric_procurement_tracking as tracking
from app.services import fabric_receiving as receiving
from app.services.fabric_procurement_parser import MAX_FILE_BYTES, parse_workbook, parse_source_feed
from app.schemas.fabric_procurement import SourcePreviewRequest, SourceApplyRequest, ReviewChangesRequest, WithdrawImportRequest
from app.schemas.fabric_receiving import ReceiveSourceRequest, ReceiveSourcesRequest
from app.schemas.fabric_master import ResolveChaseRequest

router = APIRouter(prefix="/api/fabric-warehouse/procurement", tags=["fabric-warehouse"])


def authorize(db, actor, factory_id, action):
    service.require_factory(factory_id)
    permissions = ["fabric_warehouse:read"] + ([f"fabric_warehouse:{action}"] if action in {"import", "receive"} else [])
    if not all(can(actor, permission, factory_id, "pmc-warehouse") for permission in permissions):
        raise HTTPException(403, "无华康 C 布料仓当前操作权限，请核对仓库身份与授权")


def read_source(file):
    content = file.file.read(MAX_FILE_BYTES + 1)
    filename = PurePath((file.filename or "采购来源.xlsx").replace("\\", "/")).name
    if len(filename) > 255:
        raise HTTPException(422, "文件名过长")
    return filename, content


@router.post("/imports/preview")
def preview_import(factory_id: str = Form(...), scope: Literal["PENDING", "RETURNED", "ALL", "TRACKING"] = Form("TRACKING"),
                         offset: int = Form(0, ge=0), limit: int = Form(100, ge=1, le=200),
                         action: Literal["ALL", "NEW", "UPDATE", "UNCHANGED", "BLOCKED"] = Form("ALL"), file: UploadFile = File(...),
                         db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "import")
    filename, content = read_source(file)
    parsed = parse_workbook(filename, content, scope)
    return service.preview(db, parsed, actor.id, offset=offset, limit=limit, action=action)


@router.post("/imports/apply")
def apply_import(factory_id: str = Form(...), scope: Literal["PENDING", "RETURNED", "ALL", "TRACKING"] = Form("TRACKING"),
                       preview_token: str = Form(..., min_length=64, max_length=64), request_id: UUID = Form(...),
                       confirmed: bool = Form(False), acknowledge_excluded: bool = Form(False), file: UploadFile = File(...),
                       db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "import")
    filename, content = read_source(file)
    return service.apply(db, parse_workbook(filename, content, scope), actor, filename, str(request_id), preview_token,
                         confirmed=confirmed, acknowledge_excluded=acknowledge_excluded)


@router.get("/lines")
def lines(factory_id: str, status: Literal["PENDING", "RETURNED", "ALL"] = "PENDING", search: str = Query("", max_length=128),
          view: Literal["OUTSTANDING", "NOT_ARRIVED", "PARTIAL", "ARRIVAL_REVIEW", "CHANGED", "OVERDUE", "DUE_TODAY", "AWAITING_DATE", "QUANTITY_REVIEW"] | None = None,
          offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
          supplier: str = Query("", max_length=255), unit: str = Query("", max_length=32),
          source_category: Literal["", "PURCHASE", "SUPPLEMENT"] = "", category: Literal["", "FABRIC", "ACCESSORY", "THREAD", "UNCLASSIFIED"] = "",
          promise_from: date | None = None, promise_to: date | None = None,
          order_no: str = Query("", max_length=128), production_no: str = Query("", max_length=128), material_code: str = Query("", max_length=128), style_no: str = Query("", max_length=128),
          import_batch: str = Query("", max_length=64), quantity_review: Literal["", "REVIEW", "KNOWN"] = "",
          sort: Literal["UPDATED", "OVERDUE", "PROMISE", "ORDER", "SUPPLIER", "QUANTITY_ASC", "QUANTITY_DESC"] = "UPDATED",
          db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    filters = {"supplier": supplier, "unit": unit, "source_category": source_category, "category": category,
        "promise_from": promise_from.isoformat() if promise_from else None, "promise_to": promise_to.isoformat() if promise_to else None,
        "order_no": order_no, "production_no": production_no, "material_code": material_code, "style_no": style_no, "import_batch": import_batch, "quantity_review": quantity_review}
    return {**service.list_lines(db, status, search, offset, limit, view, filters, sort), "can_receive": receiving.schema_ready(db) and can(actor, "fabric_warehouse:receive", factory_id, "pmc-warehouse")}


@router.get("/lines/{line_id}")
def detail(line_id: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    data = service.line_detail(db, line_id)
    return {**data, "can_review": can(actor, "fabric_warehouse:import", factory_id, "pmc-warehouse"),
            "can_receive": receiving.schema_ready(db) and data["active"] and not data["receipt_identity_review_required"] and not data["receipt_quantity_conflict"] and (data["master_material"] or {}).get("status") != "INACTIVE" and can(actor, "fabric_warehouse:receive", factory_id, "pmc-warehouse")}


@router.post("/lines/{line_id}/resolve-chase")
def resolve_chase(line_id: str, payload: ResolveChaseRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return receiving.resolve_chase(db, actor, line_id, payload)


@router.post("/lines/{line_id}/receive")
def receive_source(line_id: str, payload: ReceiveSourceRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "receive")
    return receiving.receive(db, actor, line_id, payload)


@router.post("/receipts/batch")
def receive_sources(payload: ReceiveSourcesRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "receive")
    return receiving.receive_many(db, actor, payload)


@router.get("/receipts")
def receipt_history(factory_id: str, search: str = Query("", max_length=128), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                    db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return receiving.list_receipts(db, search, offset, limit)


@router.get("/stock")
def stock(factory_id: str, search: str = Query("", max_length=128), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
          db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    return receiving.list_stock(db, search, offset, limit)


@router.get("/imports")
def imports(factory_id: str, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "read")
    service.ensure_schema(db)
    batches = tracking.batches(db)
    latest = next((batch.id for batch in batches if not json.loads(batch.result_json).get("withdrawal")), None)
    return {"items": [{**json.loads(batch.result_json), "can_withdraw": batch.id == latest and can(actor, "fabric_warehouse:import", factory_id, "pmc-warehouse")} for batch in batches[offset:offset + limit]], "offset": offset, "limit": limit}


@router.get("/imports/{batch_id}/withdraw-preview")
def withdraw_preview(batch_id: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, factory_id, "import")
    return tracking.withdrawal_preview(db, batch_id)


@router.post("/imports/{batch_id}/withdraw")
def withdraw_import(batch_id: str, payload: WithdrawImportRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return tracking.withdraw(db, actor, batch_id, payload.preview_token, payload.reason, payload.confirmed)


@router.post("/lines/{line_id}/review-changes")
def review_changes(line_id: str, payload: ReviewChangesRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return tracking.review_changes(db, actor, line_id, payload.expected_revision)


@router.post("/sources/preview")
def preview_source(payload: SourcePreviewRequest, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                   action: Literal["ALL", "NEW", "UPDATE", "UNCHANGED", "BLOCKED"] = "ALL",
                   db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return service.preview(db, parse_source_feed(payload.feed), actor.id, offset=offset, limit=limit, action=action)


@router.post("/sources/apply")
def apply_source(payload: SourceApplyRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    authorize(db, actor, payload.factory_id, "import")
    return service.apply(db, parse_source_feed(payload.feed), actor, "金蝶采购来源-" + payload.feed.snapshot_id,
                         str(payload.request_id), payload.preview_token, confirmed=payload.confirmed, acknowledge_excluded=payload.acknowledge_excluded)
