from typing import Literal
from datetime import date
from pydantic import TypeAdapter, ValidationError
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from app.services.customer_order_jobs import run_order_job, order_job_request

from app.api import customer_order as mapping
from app.db import get_db
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerSource as Source, OrderLedgerDispatch as Dispatch, OrderLedgerShipment as Shipment
from app.schemas.customer_order_ledger import AmendIn, DispatchIn, ReasonIn, ShipmentIn, HistorySelection, HistoryOpeningIn
from app.services.auth import AuthContext, get_current_user, now_text
from app.services.business_authz import ensure_permission_for_departments, has_permission_for_departments
from app.services import customer_order_ledger as ledger
from app.services import customer_order_history as history
from app.services import customer_order_schedule as schedule

router = APIRouter(prefix="/api/customer-order-ledger", tags=["customer-order-ledger"], dependencies=[Depends(order_job_request)])
FACTORIES = {"huaxing", "huadeng", "huakang-a", "huakang-b", "huakang-c", "huakang-d"}


def valid_factory(factory_id: str) -> str:
    if factory_id not in FACTORIES:
        raise HTTPException(400, "请明确选择有效厂区")
    return factory_id


def authorize(db, user, factory_id, permission="read", recipient=None):
    valid_factory(factory_id)
    departments = ledger.RECIPIENTS[recipient] if recipient else ("sales-business",)
    ensure_permission_for_departments(db, user, "customer_order:" + permission, factory_id, departments)


def transaction(db, operation):
    try:
        result = operation()
        db.commit()
        return result
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        # Constraint / concurrent retry failures are recoverable, never a partially saved batch.
        raise HTTPException(409, "订单正在被其他操作更新或存在重复记录，请刷新核对后重试") from exc
    except Exception:
        db.rollback()
        raise


@router.get("/capabilities")
def capabilities(factory_id: str, recipient: Literal["pmc", "warehouse", "injection"] = "pmc",
                 db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    valid_factory(factory_id)
    from app.core.config import settings
    from app.services import cutting_orders
    result = {action: has_permission_for_departments(current_user, "customer_order:" + action, factory_id,
            ledger.RECIPIENTS[recipient] if action.startswith("inbox_") else ("sales-business",))
            for action in ("read", "write", "dispatch", "shipment_confirm", "inbox_read", "inbox_receive")}
    result['cutting_dispatch_enabled'] = bool(factory_id == 'huakang-c' and result['dispatch'] and
        settings.cutting_ops_enabled and cutting_orders.schema_ready(db.connection()))
    return result


@router.get("/history/customers")
def history_customers(factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    return {"items": [{"code": code, "name": mapping.CUSTOMER_NAMES[code]}
                      for code, factories in mapping.CUSTOMER_FACTORY_OPTIONS.items() if factory_id in factories]}


async def history_parse(db, user, factory, customer, upload):
    authorize(db, user, factory)
    mapping._ensure_customer_factory(customer, factory)
    content = await upload.read(history.MAX_BYTES + 1)
    workbook = await run_order_job(history.parse_workbook, content, db=db)
    parsed = history.preview(db, content, upload.filename or "", factory, customer, mapping.CUSTOMER_NAMES[customer], workbook=workbook)
    return content, parsed


@router.post("/history/preview")
async def history_preview(factory_id: str = Form(...), customer_code: str = Form(...), schedule_file: UploadFile = File(...),
                          db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _, parsed = await history_parse(db, current_user, factory_id, customer_code, schedule_file)
    return parsed


@router.post("/history/confirm")
async def history_confirm(factory_id: str = Form(...), customer_code: str = Form(...), schedule_file: UploadFile = File(...),
                          fingerprint: str = Form(...), cutoff_date: date = Form(...), reason: str = Form(...),
                          selections: str = Form(...), confirmed: bool = Form(...),
                          db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "write")
    authorize(db, current_user, factory_id, "shipment_confirm")
    if not confirmed or not 4 <= len(reason.strip()) <= 500:
        raise HTTPException(400, "请确认所选订单的数量、状态及期初口径，并填写 4 至 500 字核对说明")
    if len(selections) > 150000:
        raise HTTPException(400, "单批最多选择 500 条订单")
    try:
        selected = TypeAdapter(list[HistorySelection]).validate_json(selections)
    except ValidationError as exc:
        raise HTTPException(400, "所选订单或期初走货数量格式不正确") from exc
    if not 1 <= len(selected) <= 500:
        raise HTTPException(400, "请选择 1 至 500 条订单")
    content, parsed = await history_parse(db, current_user, factory_id, customer_code, schedule_file)
    return transaction(db, lambda: history.confirm(db, parsed=parsed, content=content, selections=selected,
        fingerprint=fingerprint, cutoff_date=cutoff_date, reason=reason.strip(), actor=ledger.actor_name(current_user)))


@router.post("/lines/{line_id}/history-opening")
def correct_history_opening(line_id: str, factory_id: str, body: HistoryOpeningIn,
                            db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "write")
    if db.scalar(select(Dispatch.id).where(Dispatch.line_id == line_id, Dispatch.factory_id == factory_id).limit(1)):
        authorize(db, current_user, factory_id, "dispatch")
    return mutate(db, current_user, factory_id, line_id, history.correct_opening, body, "shipment_confirm")


def schedule_customer_options(db, factory_id):
    options = {code: mapping.CUSTOMER_NAMES[code] for code, factories in mapping.CUSTOMER_FACTORY_OPTIONS.items()
               if factory_id in factories}
    for code, name in db.execute(select(Line.customer_code, Line.customer_name).where(Line.factory_id == factory_id).distinct()):
        options.setdefault(code, name or code)
    return [{"code": code, "name": options[code]} for code in sorted(options)]


@router.get("/schedule/customers")
def schedule_customers(factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    return {"factory_id": factory_id, "items": schedule_customer_options(db, factory_id)}


@router.get("/schedule")
def customer_schedule(factory_id: str, customer_code: str = Query(..., min_length=1, max_length=64),
                      q: str = Query("", max_length=255), date_from: date | None = None, date_to: date | None = None,
                      unshipped_page: int = Query(1, ge=1), shipped_page: int = Query(1, ge=1),
                      cancelled_page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                      db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    names = {item["code"]: item["name"] for item in schedule_customer_options(db, factory_id)}
    if customer_code not in names:
        raise HTTPException(400, "请选择本厂区的客户")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "交期开始日期不能晚于结束日期")
    return schedule.read_schedule(db, factory=factory_id, customer=customer_code, customer_name=names[customer_code],
        q=q, date_from=date_from, date_to=date_to,
        pages={"unshipped": unshipped_page, "shipped": shipped_page, "cancelled": cancelled_page}, page_size=page_size)


@router.get("/lines")
def list_lines(factory_id: str, customer_code: str = "", view: Literal["all", "unshipped", "shipped", "cancelled"] = "all",
               q: str = Query("", max_length=255), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    query = select(Line).where(Line.factory_id == factory_id)
    if customer_code:
        query = query.where(Line.customer_code == customer_code)
    if view == "unshipped":
        query = query.where(Line.status == "active", or_(Line.quantity.is_(None), Line.quantity > Line.shipped_quantity))
    elif view == "shipped":
        query = query.where(Line.shipped_quantity > 0)
    elif view == "cancelled":
        query = query.where(Line.status == "cancelled")
    if q.strip():
        query = query.where(or_(Line.reference_no.contains(q.strip(), autoescape=True), Line.product_no.contains(q.strip(), autoescape=True),
                               Line.data["po_no"].as_string().contains(q.strip(), autoescape=True),
                               Line.data["contract_no"].as_string().contains(q.strip(), autoescape=True),
                               Line.customer_name.contains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Line.updated_at.desc(), Line.id).offset((page - 1) * page_size).limit(page_size)).all()
    customers = db.execute(select(Line.customer_code, Line.customer_name).where(Line.factory_id == factory_id).distinct()).all()
    return {"items": [ledger.line_out(db, item) for item in items], "total": total, "page": page, "page_size": page_size,
            "customers": [{"code": code, "name": name} for code, name in customers]}


@router.get("/lines/{line_id}")
def line_detail(line_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    return ledger.detail(db, ledger.get_line(db, factory_id, line_id))


@router.get("/sources/{source_id}")
def source_download(source_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id)
    source = db.scalar(select(Source).where(Source.id == source_id, Source.factory_id == factory_id))
    if not source:
        raise HTTPException(404, "原件不存在")
    return Response(source.content, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(source.file_name), "X-Content-Type-Options": "nosniff"})


@router.post("/imports/{customer_code}")
async def import_orders(customer_code: str, factory_id: str = Form(...), received_date: str = Form(...),
    confirmed: bool = Form(...), skipped_issue_keys: str = Form("[]"), manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(...), confirmation_reason: str = Form(""),
    source_kind: Literal["formal", "supplementary"] = Form("formal"),
    reconcile_line_id: str = Form(""), expected_revision: int | None = Form(None), reconciliation_reason: str = Form(""),
    po_files: list[UploadFile] = File(...), schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "write")
    authorize(db, current_user, factory_id, "read")
    mapping._ensure_customer_factory(customer_code, factory_id)
    reconcile_line = ledger.get_line(db, factory_id, reconcile_line_id) if reconcile_line_id else None
    if reconcile_line:
        if len(reconciliation_reason.strip()) < 4 or len(reconciliation_reason) > 500:
            raise HTTPException(400, "关联原因需要 4 至 500 个字")
        if db.scalar(select(Dispatch.id).where(Dispatch.line_id == reconcile_line.id).limit(1)):
            authorize(db, current_user, factory_id, "dispatch")
    if not confirmed:
        raise HTTPException(400, "请先核对预览并确认保存订单")
    keys = mapping._parse_skipped_issue_keys(skipped_issue_keys)
    overrides = mapping._parse_manual_overrides(manual_overrides)
    resolution_keys = keys | {item["issue_key"] for item in overrides}
    reason = mapping._prepare_export_confirmation(db, current_user, factory_id, resolution_keys, confirmation_reason)
    special = customer_code in {"buzzbee", "dickie", "caixing"}
    extensions = ((".xls", ".xlsx") if customer_code == "buzzbee" else (".pdf",)) if special else mapping._get_mapped_customer_spec(customer_code, factory_id).po_extensions
    mapping._validate_upload(schedule_file, kind="客户排期", supported=(".xlsx",))
    files = await mapping._read_po_uploads(po_files, supported=extensions)
    schedule_content = await schedule_file.read(mapping.MAX_SCHEDULE_BYTES + 1)
    if not schedule_content or len(schedule_content) > mapping.MAX_SCHEDULE_BYTES:
        raise HTTPException(400, "客户排期为空或超过 35MB 限制")
    kwargs = dict(customer_code=customer_code, factory_id=factory_id, received_date=received_date,
        po_files=files, schedule_file_name=schedule_file.filename or "", schedule_content=schedule_content)
    try:
        create_preview = mapping._create_special_batch_preview if special else mapping._create_mapped_customer_preview
        preview = await run_order_job(create_preview, db=db, **kwargs)
        mapping._finalize_preview(preview, received_date=received_date, current_user=current_user, factory_id=factory_id)
        mapping._ensure_preview_fingerprint(preview, received_date, preview_fingerprint)
        actual_keys = mapping._actual_confirmed_issue_keys(preview, resolution_keys)
        mapping._actual_manual_overrides(preview, overrides)
        # Validate and apply manual inputs using the exact existing writer. Its source files remain unchanged.
        export = mapping._export_special_batch_schedule if special else mapping._export_mapped_customer_schedule
        _, _, resolved = await run_order_job(export, db=db, **kwargs, skipped_issue_keys=actual_keys, manual_overrides=overrides)
    except (mapping.CustomerOrderWorkbookError, mapping.HuaxingCustomerOrderError,
            mapping.HuadengCustomerOrderError, mapping.HuakangACustomerOrderError, mapping.HuakangCCustomerOrderError) as exc:
        raise HTTPException(400, str(exc)) from exc
    resolved["customer_name"] = mapping.CUSTOMER_NAMES.get(customer_code, customer_code)
    return transaction(db, lambda: ledger.import_preview(db, preview=resolved,
        files=[(name, content, source_kind) for name, content in files] + [(schedule_file.filename or "schedule.xlsx", schedule_content, "schedule")],
        source_kind=source_kind, actor=ledger.actor_name(current_user), reason=reconciliation_reason.strip() if reconcile_line else reason,
        reconcile_line=reconcile_line, expected_revision=expected_revision,
        controls={"preview_fingerprint": preview_fingerprint, "confirmed_issue_keys": sorted(actual_keys), "manual_overrides": overrides, "reason": reason}))


def mutate(db, user, factory, line_id, action, body, permission):
    authorize(db, user, factory, permission)
    line = ledger.get_line(db, factory, line_id)
    def perform():
        action(db, line, body, ledger.actor_name(user))
        return ledger.line_out(db, line)
    return transaction(db, perform)


@router.post("/lines/{line_id}/amend")
def amend(line_id: str, factory_id: str, body: AmendIn, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    # A sent order's changes notify the original recipients, so dispatch authority remains required.
    if db.scalar(select(Dispatch.id).where(Dispatch.line_id == line_id, Dispatch.factory_id == factory_id).limit(1)):
        authorize(db, current_user, factory_id, "dispatch")
    return mutate(db, current_user, factory_id, line_id, ledger.amend, body, "write")


@router.post("/lines/{line_id}/cancel")
def cancel(line_id: str, factory_id: str, body: ReasonIn, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    if db.scalar(select(Dispatch.id).where(Dispatch.line_id == line_id, Dispatch.factory_id == factory_id).limit(1)):
        authorize(db, current_user, factory_id, "dispatch")
    return mutate(db, current_user, factory_id, line_id, ledger.cancel, body, "write")


@router.post("/lines/{line_id}/dispatch")
def dispatch(line_id: str, factory_id: str, body: DispatchIn, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return mutate(db, current_user, factory_id, line_id, ledger.dispatch, body, "dispatch")


@router.post("/lines/{line_id}/shipments")
def ship(line_id: str, factory_id: str, body: ShipmentIn, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return mutate(db, current_user, factory_id, line_id, ledger.ship, body, "shipment_confirm")


@router.post("/shipments/{shipment_id}/reverse")
def reverse(shipment_id: str, factory_id: str, body: ReasonIn, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "shipment_confirm")
    shipment = db.scalar(select(Shipment).where(Shipment.id == shipment_id, Shipment.factory_id == factory_id))
    if not shipment:
        raise HTTPException(404, "走货记录不存在")
    line = ledger.get_line(db, factory_id, shipment.line_id)
    def perform():
        ledger.reverse_shipment(db, line, shipment, body, ledger.actor_name(current_user))
        return ledger.line_out(db, line)
    return transaction(db, perform)


@router.get("/inbox")
def inbox(factory_id: str, recipient: Literal["pmc", "warehouse", "injection"], page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
          db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "inbox_read", recipient)
    query = select(Dispatch).where(Dispatch.factory_id == factory_id, Dispatch.recipient == recipient)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Dispatch.created_at.desc(), Dispatch.id).offset((page - 1) * page_size).limit(page_size)).all()
    latest = dict(db.execute(select(Line.id, Line.version).where(Line.factory_id == factory_id, Line.id.in_([item.line_id for item in items]))).all())
    return {"items": [ledger.dispatch_out(item) | {"latest_version": latest[item.line_id]} for item in items], "total": total, "page": page, "page_size": page_size}


@router.post("/inbox/{dispatch_id}/receive")
def receive(dispatch_id: str, factory_id: str, recipient: Literal["pmc", "warehouse", "injection"],
            db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    authorize(db, current_user, factory_id, "inbox_receive", recipient)
    item = db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id, Dispatch.factory_id == factory_id, Dispatch.recipient == recipient))
    if not item:
        raise HTTPException(404, "当前收件箱中没有此订单")
    def perform():
        db.execute(update(Dispatch).where(Dispatch.id == item.id, Dispatch.received_at == "").values(
            received_at=now_text(), received_by=ledger.actor_name(current_user)), execution_options={"synchronize_session": False})
        db.refresh(item)
        return ledger.dispatch_out(item) | {"latest_version": ledger.get_line(db, factory_id, item.line_id).version}
    return transaction(db, perform)
