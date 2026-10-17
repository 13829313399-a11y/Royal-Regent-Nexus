"""Huakang B only: references, enquiry preview, audited Kintable exports."""
from datetime import date
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response, Request
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import ensure_permission_for_departments, has_permission_for_departments
from app.services.customer_order_jobs import order_job_request, run_order_job
from app.api.customer_order_ledger import transaction
from app.services.customer_order_ledger import actor_name
from app.schemas.huakang_b_jp import QuantitySelection, RowOverride
from app.services.huakang_b_jp import intake
from app.models.huakang_b_jp import JPExport

router = APIRouter(prefix="/api/huakang-b-jp", tags=["huakang-b-jp"], dependencies=[Depends(order_job_request)])
refresh_user = get_current_user
TABLES = {"jp_intake_references", "jp_intake_reference_events", "jp_intake_counters", "jp_intake_exports", "jp_intake_export_identities"}


def require_page_header(request):
    # Non-simple request header: cross-origin forms cannot submit protected
    # writes with session cookies. No permissive CORS route is introduced.
    if request.headers.get("X-JP-Intake") != "1":
        raise HTTPException(403, "请从华康B问单页面重新操作")


def guard(db, user, factory, action="read"):
    if factory != intake.FACTORY:
        raise HTTPException(400, "JP问单录入仅支持华康B")
    ensure_permission_for_departments(db, user, "customer_order:" + action, factory, ("sales-business",))
    if not TABLES.issubset(set(inspect(db.connection()).get_table_names())):
        raise HTTPException(503, "华康B问单模块尚未执行迁移 20261017_0167，请联系管理员部署")


@router.get("/capabilities")
def capabilities(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    if factory_id != intake.FACTORY:
        raise HTTPException(400, "JP问单录入仅支持华康B")
    readable = has_permission_for_departments(user, "customer_order:read", factory_id, ("sales-business",))
    return {"read": readable, "write": readable and has_permission_for_departments(user, "customer_order:write", factory_id, ("sales-business",)),
            "export": readable and has_permission_for_departments(user, "customer_order:export", factory_id, ("sales-business",)),
            "available": readable and TABLES.issubset(set(inspect(db.connection()).get_table_names())),
            "creator_name": (user.display_name or user.username) if readable else ""}


@router.get("/references")
def references(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id)
    return intake.reference_state(db)


async def read_file(file, extensions, limit=intake.MAX_FILE):
    name = Path((file.filename or "").replace("\\", "/")).name
    if not name or name.startswith("._") or len(name) > 240 or not name.lower().endswith(extensions):
        raise HTTPException(400, "文件类型或文件名不支持")
    content = await file.read(limit + 1)
    if not content or len(content) > limit:
        raise HTTPException(400, "文件为空或超过 20MB")
    return name, content


@router.post("/references/{kind}")
async def upload_reference(kind: Literal["schedule", "price", "confirmed"], request: Request, factory_id: str = Form(...),
    expected_revision: int = Form(..., ge=0), file: UploadFile = File(...),
    currency: Literal["", "HKD", "USD"] = Form(""),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    require_page_header(request)
    guard(db, user, factory_id, "write")
    guard(db, user, factory_id)
    name, content = await read_file(file, (".xlsx",))
    if kind != "confirmed" and currency:
        raise HTTPException(400, "只有确认价表可指定确认价格币种")
    options = {"currency": currency} if currency else {}
    await run_order_job(intake._jp_validate_reference, kind, content, options, db=db)
    # Recheck authorization after the file worker, before any writes.
    user = refresh_user(request, db)
    guard(db, user, factory_id)
    guard(db, user, factory_id, "write")
    return transaction(db, lambda: intake.save_reference(db, kind, name, content, expected_revision, actor_name(user), options))


@router.post("/references/confirmed/clear")
def clear_confirmed(request: Request, factory_id: str = Form(...), expected_revision: int = Form(..., ge=0),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    require_page_header(request)
    guard(db, user, factory_id)
    guard(db, user, factory_id, "write")
    return transaction(db, lambda: intake.save_reference(db, "confirmed", "JP-confirmed-cleared.xlsx",
        intake.empty_confirmed(), expected_revision, actor_name(user)))


def json_values(raw, type, maximum=250):
    if len(raw) > 250000:
        raise HTTPException(400, "核对内容过大")
    try:
        result = TypeAdapter(list[type]).validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(400, "数量列或人工更正格式错误") from exc
    if len(result) > maximum:
        raise HTTPException(400, "核对内容数量过多")
    return [v.model_dump() if hasattr(v, "model_dump") else v for v in result]


async def prepare(db, user, files, html, subject, received_date, choices, merchandiser="", identity_overrides=()):
    if len(files) > 100 or len(html.encode()) > 2 * 1024**2 or len(subject) > 500:
        raise HTTPException(400, "邮件数量或正文过大")
    uploads = [await read_file(file, (".eml", ".zip")) for file in files]
    if sum(len(c) for _, c in uploads) > intake.MAX_TOTAL:
        raise HTTPException(400, "邮件文件合计不可超过 50MB")
    refs = intake.snapshots(db)
    preview = await run_order_job(intake._jp_preview, uploads, html, subject, received_date.isoformat(), refs,
        json_values(choices, QuantitySelection, 200), user.id, merchandiser, identity_overrides, db=db)
    return uploads, refs, preview


@router.post("/preview")
async def preview(request: Request, factory_id: str = Form(...), received_date: date = Form(...),
    files: list[UploadFile] = File(default=[]), html: str = Form(""), subject: str = Form(""),
    quantity_selections: str = Form("[]"), merchandiser: str = Form("", max_length=128),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    require_page_header(request)
    guard(db, user, factory_id)
    merchandiser = merchandiser.strip()
    _, _, result = await prepare(db, user, files, html, subject, received_date, quantity_selections, merchandiser)
    user = refresh_user(request, db)
    guard(db, user, factory_id)
    return result


@router.post("/export")
async def export(request: Request, factory_id: str = Form(...), received_date: date = Form(...),
    files: list[UploadFile] = File(default=[]), html: str = Form(""), subject: str = Form(""),
    quantity_selections: str = Form("[]"), fingerprint: str = Form(...), selected: str = Form(...),
    overrides: str = Form("[]"), reason: str = Form(...), confirmed: bool = Form(...),
    merchandiser: str = Form("", max_length=128),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    require_page_header(request)
    guard(db, user, factory_id)
    guard(db, user, factory_id, "export")
    if not confirmed or not 4 <= len(reason.strip()) <= 500:
        raise HTTPException(400, "请确认核对结果并填写 4 至 500 个字的原因")
    merchandiser = merchandiser.strip()
    if not 1 <= len(merchandiser) <= 128:
        raise HTTPException(400, "请按金山人员名称填写业务跟单")
    changes = json_values(overrides, RowOverride, 2750)
    uploads, refs, result = await prepare(db, user, files, html, subject, received_date, quantity_selections, merchandiser, changes)
    user = refresh_user(request, db)
    guard(db, user, factory_id)
    if fingerprint != result["fingerprint"]:
        raise HTTPException(409, "原件、参照或数量列选择已变化，请重新预览核对")
    guard(db, user, factory_id, "export")
    record = transaction(db, lambda: intake.save_export(db, result, json_values(selected, str),
        changes, refs, uploads, html, reason.strip(), actor_name(user), user.display_name or user.username))
    return {"id": record.id, "first_number": record.first_number, "last_number": record.last_number,
            "row_count": len(record.data["rows"])}


@router.get("/exports")
def exports(factory_id: str, page: int = 1, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id)
    if not 1 <= page <= 10000:
        raise HTTPException(400, "页码不正确")
    query = select(JPExport).where(JPExport.factory_id == factory_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(JPExport.created_at.desc(), JPExport.id).offset((page - 1) * 20).limit(20)).all()
    return {"total": total, "items": [{"id": row.id, "actor": row.actor, "created_at": row.created_at,
        "first_number": row.first_number, "last_number": row.last_number,
        "row_count": len(row.data["rows"]), "prefix": row.data["prefix"]} for row in rows]}


@router.get("/exports/{id}/download")
def download(id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id)
    guard(db, user, factory_id, "export")
    row = db.scalar(select(JPExport).where(JPExport.id == id, JPExport.factory_id == factory_id))
    if not row:
        raise HTTPException(404, "导出记录不存在")
    return Response(row.content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="jp-enquiry-{id}.xlsx"',
                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
