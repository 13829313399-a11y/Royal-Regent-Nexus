from urllib.parse import quote
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.carton_mark import CartonMarkAsset
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_portal import CommitmentSave, BatchCommitmentSave, ShipmentCreate, ShipmentReceive, CancellationAcknowledge, RushAcknowledge, ShipmentStatusChange, ShipmentReceiptLink, SampleReceiptLink, ShipmentLineLink, SupplierMarkTemplateOut, SupplierDocumentExport
from app.services import carton_supplier_portal as service
from app.services import carton_supplier_delivery_import as delivery_import
from app.services import carton_supplier_receipt_link as receipt_link
from app.services import carton_supplier_settlement as settlement
from app.schemas.carton_supplier_settlement import SupplierSettlementReview, MonthlySettlementAction
from app.schemas.carton_supplier_portal import SupplierMarkAssetOut, SupplierMarkCheckOut, SupplierMarkUploadOrderOut, SupplierMarkAssetUploadOut
from app.services import carton_supplier_mark_check as mark_check
from app.services import carton_supplier_mark_upload as mark_upload
from app.services import carton_supplier_mark_pdf as mark_pdf
from app.services import carton_supplier_mark_layout as mark_layout
from app.schemas.carton_supplier_portal import SupplierMarkPdfRequest, SupplierMarkPdfOut, SupplierMarkLayoutOut, MarkLayoutConfig
from app.services.carton_mark import (MAX_DOCUMENT_FILE_BYTES, build_carton_mark_document_check,
    CartonMarkDocumentError, CartonMarkDocumentConfigurationError)
from app.services.carton_procurement import _lock_receipt_factory
import json

router = APIRouter(prefix="/api/carton-supplier", tags=["carton-supplier"])

from app.schemas.carton_supplier_changes import SupplierChangeResponse
from app.services import carton_supplier_changes as changes


@router.get("/changes")
def supplier_changes(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.workspace(db, user, factory_id)


@router.get("/internal/changes")
def internal_supplier_changes(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.workspace(db, user, factory_id, internal=True)


@router.post("/changes/respond")
def respond_supplier_change(payload: SupplierChangeResponse, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return changes.respond(db, user, payload)

@router.get("/memberships")
def memberships(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return [{"factory_id": supplier.factory_id, "supplier_name": supplier.supplier_name}
        for supplier in service.supplier_factories(db, user)]


@router.get("/settlements/workspace")
def settlement_workspace(factory_id: str, period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), currency: str = "CNY",
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return settlement.supplier_workspace(db, user, factory_id, period, currency)


@router.get("/monthly-settlements/workspace")
def monthly_settlement_workspace(factory_id: str, period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                                 currency: str = "CNY", db: Session = Depends(get_db),
                                 user: AuthContext = Depends(get_current_user)):
    """Read-only copy of the internal simplified month, without internal blockers."""
    from app.services import carton_monthly_settlement as monthly
    if not service.supplier_permission(user, "carton_supplier:read", factory_id):
        raise HTTPException(403, "没有本厂供应商月结查看权限")
    data = monthly.workspace(db, factory_id, period, currency)
    keys = ("source_key", "kind", "document_no", "acceptance_date", "customer_name", "contract_no",
            "item_no", "packaging_type", "paper_quality", "specification", "unit", "quantity",
            "unit_price", "amount", "currency")
    return {
        "factory_id": data["factory_id"], "supplier_name": data["supplier_name"],
        "period": data["period"], "currency": data["currency"], "read_only": True,
        "status": data["status"], "stale": data["stale"],
        "submitted_at": data["submitted_at"], "supplier_confirmed_at": data["supplier_confirmed_at"],
        "disputed_reason": data["disputed_reason"], "locked_at": data["locked_at"],
        "can_confirm": False,
        "can_dispute": False,
        "totals": data["totals"],
        "lines": [{key: line.get(key) for key in keys} for line in data["lines"]],
    }


@router.post("/monthly-settlements/confirm")
def monthly_settlement_confirm(payload: MonthlySettlementAction, db: Session = Depends(get_db),
                               user: AuthContext = Depends(get_current_user)):
    raise HTTPException(410, "新月结确认已停用；本月对账仅供核对，请按原月结流程办理")


@router.post("/monthly-settlements/dispute")
def monthly_settlement_dispute(payload: MonthlySettlementAction, db: Session = Depends(get_db),
                               user: AuthContext = Depends(get_current_user)):
    raise HTTPException(410, "新月结异议已停用；本月对账仅供核对，请按原月结流程办理")


@router.post("/settlements/{identifier}/review")
def settlement_review(identifier: str, payload: SupplierSettlementReview,
                      db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return settlement.supplier_review(db, identifier, payload, user)

@router.get("/workspace")
def workspace(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id)

@router.get("/documents")
def documents(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.documents(db, user, factory_id)

@router.post("/documents/export.xlsx")
def export_documents(payload: SupplierDocumentExport, db: Session = Depends(get_db),
                     user: AuthContext = Depends(get_current_user)):
    content = service.export_documents(db, user, payload)
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote("供应商单据.xlsx"),
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.post("/documents/order-import.xlsx")
def export_supplier_order_import(payload: SupplierDocumentExport, db: Session = Depends(get_db),
                                 user: AuthContext = Depends(get_current_user)):
    content = service.export_supplier_order_import(db, user, payload)
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote("东康订单导入模板.xlsx"),
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.get("/activity")
def activity(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_activity(db, user, factory_id)


@router.get("/activity-page")
def activity_page(factory_id: str = "", search: str = Query(default="", max_length=128),
                  event_type: str = Query(default="", max_length=64),
                  date_from: str = "", date_to: str = "", sort: Literal["ASC", "DESC"] = "DESC",
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_activity_page(db, user, factory_id, search=search.strip(), event_type=event_type,
        date_from=date_from, date_to=date_to, sort=sort, limit=limit, offset=offset)

@router.get("/carton-mark/assets", response_model=list[SupplierMarkAssetOut])
def carton_mark_assets(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_mark_assets(db, user, factory_id)


from app.schemas.carton_supplier_portal import SupplierMarkAssetClassification


@router.put('/carton-mark/assets/{asset_id}/classification', response_model=SupplierMarkAssetOut)
def classify_supplier_mark_asset(asset_id: str, factory_id: str, payload: SupplierMarkAssetClassification,
                                request: Request, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_supplier_asset_status import classify
    return classify(db, user, factory_id, asset_id, payload, lambda: get_current_user(request, db))


@router.get("/carton-mark/assets/{asset_id}/document")
def carton_mark_asset_document(asset_id: str, factory_id: str, preview: bool = False,
                              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    asset = service.supplier_mark_asset_document(db, user, factory_id, asset_id)
    disposition = "inline" if preview and asset.kind in {"pdf", "image"} else "attachment"
    return Response(asset.content, media_type=asset.content_type, headers={
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(asset.file_name, safe=""),
        "Content-Length": str(asset.size_bytes), "X-Content-SHA256": asset.sha256,
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


from app.schemas.carton_mark import CartonMarkSupplierBinding, CartonMarkAssociations, CartonMarkAssociationTarget


@router.get('/carton-mark/binding-targets')
def mark_binding_targets(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_mark_sharing import binding_targets
    return binding_targets(db, user, factory_id, external=True)


@router.put('/carton-mark/assets/{asset_id}/binding', response_model=SupplierMarkAssetOut)
def propose_mark_binding(asset_id: str, factory_id: str, payload: CartonMarkSupplierBinding,
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_mark_sharing import propose
    return propose(db, user, factory_id, asset_id, payload)


@router.put('/carton-mark/assets/{asset_id}/associations', response_model=SupplierMarkAssetOut)
def associate_mark_asset(asset_id: str, factory_id: str, payload: CartonMarkAssociations,
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_mark_associations import save
    return save(db, user, factory_id, asset_id, payload, external=True)


@router.get("/carton-mark/upload-orders", response_model=list[SupplierMarkUploadOrderOut])
def carton_mark_upload_orders(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return mark_upload.upload_orders(db, user, factory_id)


@router.post("/carton-mark/assets/upload", response_model=list[SupplierMarkAssetUploadOut], status_code=201)
async def upload_carton_mark_assets(request: Request, factory_id: str = Form(..., max_length=64),
        order_id: str = Form("", max_length=96), issue_id: str = Form("", max_length=96),
        shared_unbound: bool = Form(False),
        request_id: str = Form('', max_length=96, pattern=r'^[A-Za-z0-9_-]*$'), targets_json: str = Form(''),
        files: list[UploadFile] = File(...), db: Session = Depends(get_db),
        user: AuthContext = Depends(get_current_user)):
    orders = mark_upload.upload_orders(db, user, factory_id)
    from pydantic import TypeAdapter, ValidationError
    try:
        targets = TypeAdapter(list[CartonMarkAssociationTarget]).validate_json(targets_json) if targets_json else None
        if targets is not None and len(targets) > 100: raise ValueError()
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, '关联目标参数不正确') from exc
    if targets is not None and (order_id or issue_id): raise HTTPException(422, '请仅选择一种关联参数')
    if not 1 <= len(files) <= 50:
        raise HTTPException(413, "每批须为 1–50 个箱唛文件")
    if bool(order_id) != bool(issue_id):
        raise HTTPException(422, "请选择当前版本的采购订单")
    if order_id and not any(order["id"] == order_id and order["issue_id"] == issue_id for order in orders):
        raise HTTPException(404, "未找到可上传资料的采购订单")
    contents, total = [], 0
    for file in files:
        if file.size is not None and file.size > MAX_DOCUMENT_FILE_BYTES:
            raise HTTPException(413, "单个箱唛文件不能超过 20 MB")
        content = await file.read(MAX_DOCUMENT_FILE_BYTES + 1)
        total += len(content)
        if len(content) > MAX_DOCUMENT_FILE_BYTES or total > 100 * 1024 * 1024:
            raise HTTPException(413, "单个文件最多 20 MB，每批合计最多 100 MB")
        contents.append((file.filename or "", content))
    db.rollback()
    parsed = await run_in_threadpool(mark_upload.recognize_batch, contents, orders)
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, get_current_user(request, db), factory_id)
    return mark_upload.save_batch(db, user, factory_id, parsed, orders, order_id, issue_id,
        shared_unbound=shared_unbound, targets=targets, request_id=request_id)


@router.get("/carton-mark/templates", response_model=list[SupplierMarkTemplateOut])
def carton_mark_templates(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_mark_templates(db, user, factory_id)


@router.post("/carton-mark/generate-pdf", response_model=SupplierMarkPdfOut, status_code=201)
async def generate_carton_mark_pdf(payload: SupplierMarkPdfRequest, request: Request,
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    original = mark_pdf.source(db, user, payload)
    db.rollback()
    prepared = await run_in_threadpool(mark_pdf.prepare_pdf, original)
    _lock_receipt_factory(db, payload.factory_id)
    return mark_pdf.save_pdf(db, get_current_user(request, db), payload, original, prepared)


@router.get("/carton-mark/layouts", response_model=list[SupplierMarkLayoutOut])
def carton_mark_layouts(factory_id: str, order_id: str, issue_id: str,
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    scope = mark_layout.context(db, user, factory_id, order_id, issue_id)
    return [mark_layout.output(row) for row in mark_layout.rows(db, scope)]


@router.get("/carton-mark/pdf-ai-status")
def carton_mark_pdf_ai_status(factory_id: str, order_id: str, issue_id: str,
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    mark_layout.context(db, user, factory_id, order_id, issue_id, write=True)
    from app.services import carton_supplier_mark_ai
    return carton_supplier_mark_ai.status()


@router.get("/carton-mark/pdf-draft-status")
def carton_mark_pdf_draft_status(factory_id: str = "", db: Session = Depends(get_db),
        user: AuthContext = Depends(get_current_user)):
    from app.services import carton_supplier_mark_draft as draft
    draft.access(db, user, factory_id)
    result=draft.ai.status()
    try:
        from app.services import carton_mark_customer_template as customer
        draft.ai.provider_configuration();customer.logo_bytes();customer.reference_image()
        result['customer_template_available']=True
    except (draft.ai.pilot.PilotError,OSError,ValueError,KeyError,HTTPException):
        result['customer_template_available']=False
    return result


@router.post("/carton-mark/generate-pdf-draft")
async def generate_carton_mark_pdf_draft(request: Request,
        engine: Literal["excel_original", "deepseek_zumiez"] = Form("excel_original"),
        factory_id: str = Form(""), excel_asset_id: str = Form(""),
        expected_revision: int = Form(0, ge=0), ai_consent: bool = Form(False),
        supplements_json: str = Form("{}", max_length=1024), excel: UploadFile | None = File(None),
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services import carton_supplier_mark_draft as draft
    scope = draft.access(db, user, factory_id)
    if bool(excel) == bool(excel_asset_id):
        raise HTTPException(422, "请选择一个新 Excel 或一份资料库原稿")
    stored = draft.source(db, user, factory_id, excel_asset_id, expected_revision) if excel_asset_id else None
    content = stored["content"] if stored else await excel.read(MAX_DOCUMENT_FILE_BYTES + 1)
    name = stored["name"] if stored else excel.filename or "document.xlsx"
    try:
        supplements = json.loads(supplements_json)
        if not isinstance(supplements, dict):
            raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(422, "补齐内容格式无效") from None
    original = draft.original(name, content, engine, ai_consent, supplements)
    db.rollback()
    pdf, pages, warnings = await run_in_threadpool(draft.prepare, original, engine)
    current_user = get_current_user(request, db)
    if scope != draft.access(db, current_user, factory_id):
        raise HTTPException(409, "资料权限范围已变化，请刷新后重新生成")
    if stored and stored != draft.source(db, current_user, factory_id, excel_asset_id, expected_revision):
        raise HTTPException(409, "Excel 原稿已变化，请刷新后重新生成")
    filename = Path(original["excel_file_name"]).stem[:180] + "_审阅稿.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Cache-Control": "private, no-store",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Carton-Pdf-Pages": str(pages), "X-Carton-Pdf-Warnings": quote(json.dumps(warnings, ensure_ascii=False))})


async def _carton_review_input(db,user,factory_id,excel_asset_id,expected_revision,excel):
    from app.services import carton_supplier_mark_draft as draft
    scope=draft.access(db,user,factory_id)
    if bool(excel)==bool(excel_asset_id):raise HTTPException(422,"请选择一个新Excel或一份资料库原稿")
    stored=draft.source(db,user,factory_id,excel_asset_id,expected_revision) if excel_asset_id else None
    content=stored["content"] if stored else await excel.read(MAX_DOCUMENT_FILE_BYTES+1)
    name=stored["name"] if stored else excel.filename or "document.xlsx"
    original=draft.original(name,content,"excel_original",False,{})
    owner=user.id+json.dumps([user.authorization_version,factory_id,excel_asset_id,expected_revision,scope],ensure_ascii=True)
    db.rollback()
    return scope,stored,original,owner


def _carton_review_recheck(request,db,scope,stored,factory_id,excel_asset_id,expected_revision):
    from app.services import carton_supplier_mark_draft as draft
    user=get_current_user(request,db)
    if scope!=draft.access(db,user,factory_id):raise HTTPException(409,"资料权限范围已变化，请重新读取")
    if stored and stored!=draft.source(db,user,factory_id,excel_asset_id,expected_revision):
        raise HTTPException(409,"Excel原稿已变化，请重新读取")
    return user


@router.post("/carton-mark/read-pdf-draft")
async def read_carton_mark_draft(request:Request,factory_id:str=Form(""),excel_asset_id:str=Form(""),
        expected_revision:int=Form(0,ge=0),ai_consent:bool=Form(False),worksheets_json:str=Form("[]",max_length=10000),excel:UploadFile|None=File(None),
        image_consent:bool=Form(False),customer_template_id:str=Form("",max_length=96),
        db:Session=Depends(get_db),user:AuthContext=Depends(get_current_user)):
    from app.services import carton_mark_workbench as workbench
    scope,stored,original,owner=await _carton_review_input(db,user,factory_id,excel_asset_id,expected_revision,excel)
    original.update(image_consent=image_consent,customer_template_id=customer_template_id)
    try:
        original["worksheets"]=json.loads(worksheets_json)
        if not isinstance(original["worksheets"],list) or len(original["worksheets"])>50 or any(not isinstance(s,str) for s in original["worksheets"]):raise ValueError()
    except (ValueError,TypeError):raise HTTPException(422,"工作表选择无效") from None
    result=await run_in_threadpool(workbench.read,original,owner,ai_consent)
    current=_carton_review_recheck(request,db,scope,stored,factory_id,excel_asset_id,expected_revision)
    if current.id!=user.id or current.authorization_version!=user.authorization_version:raise HTTPException(409,"账号授权已变化，请重新读取")
    return Response(json.dumps(result,ensure_ascii=False),media_type="application/json",headers={"Cache-Control":"private, no-store"})


@router.post("/carton-mark/inspect-pdf-draft")
async def inspect_carton_mark_draft(request:Request,factory_id:str=Form(""),excel_asset_id:str=Form(""),
        expected_revision:int=Form(0,ge=0),excel:UploadFile|None=File(None),
        db:Session=Depends(get_db),user:AuthContext=Depends(get_current_user)):
    from app.services import carton_mark_workbench as workbench
    scope,stored,original,_=await _carton_review_input(db,user,factory_id,excel_asset_id,expected_revision,excel)
    result=await run_in_threadpool(workbench.inspect,original)
    _carton_review_recheck(request,db,scope,stored,factory_id,excel_asset_id,expected_revision)
    return Response(json.dumps(result,ensure_ascii=False),media_type="application/json",headers={"Cache-Control":"private, no-store"})


@router.post("/carton-mark/render-reviewed-draft")
async def render_reviewed_carton_mark_draft(request:Request,factory_id:str=Form(""),excel_asset_id:str=Form(""),
        expected_revision:int=Form(0,ge=0),excel:UploadFile|None=File(None),
        review_payload:str=Form(...,max_length=500000),review_signature:str=Form(...,max_length=64),
        edits_json:str=Form("{}",max_length=50000),reviewed_notes_json:str=Form("[]",max_length=30000),
        additions_json:str=Form("[]",max_length=50000),omissions_json:str=Form("[]",max_length=5000),
        graphics_json:str=Form("[]",max_length=10000),
        ignored_changes_json:str=Form("[]",max_length=1000),
        include_sources:bool=Form(True),
        paper:Literal["A3","A4"]=Form("A3"),orientation:Literal["portrait","landscape"]=Form("landscape"),
        db:Session=Depends(get_db),user:AuthContext=Depends(get_current_user)):
    from app.services import carton_mark_workbench as workbench
    scope,stored,original,owner=await _carton_review_input(db,user,factory_id,excel_asset_id,expected_revision,excel)
    try:edits=json.loads(edits_json);reviewed=json.loads(reviewed_notes_json);additions=json.loads(additions_json);omissions=json.loads(omissions_json);graphics=json.loads(graphics_json);ignored_changes=json.loads(ignored_changes_json)
    except (ValueError,TypeError):raise HTTPException(422,"核对内容格式无效") from None
    pdf,pages,warnings=await run_in_threadpool(workbench.render,original,owner,review_payload,review_signature,edits,reviewed,paper,orientation,additions,omissions,graphics,include_sources,ignored_changes)
    current=_carton_review_recheck(request,db,scope,stored,factory_id,excel_asset_id,expected_revision)
    if current.id!=user.id or current.authorization_version!=user.authorization_version:raise HTTPException(409,"账号授权已变化，请重新读取")
    filename=Path(original["excel_file_name"]).stem[:180]+"_审阅稿.pdf"
    return Response(pdf,media_type="application/pdf",headers={"Cache-Control":"private, no-store",
        "Content-Disposition":f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Carton-Pdf-Pages":str(pages),"X-Carton-Pdf-Warnings":quote(json.dumps(warnings,ensure_ascii=False))})


@router.post("/carton-mark/layout-reference-preview")
async def preview_layout_reference(factory_id: str = Form(...), order_id: str = Form(...), issue_id: str = Form(...),
        reference_pdf: UploadFile = File(...), page: int = Form(0, ge=0, le=19),
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    mark_layout.context(db, user, factory_id, order_id, issue_id, write=True)
    content = await reference_pdf.read(MAX_DOCUMENT_FILE_BYTES + 1)
    db.rollback()
    return await run_in_threadpool(mark_layout.reference_image, content, page)


@router.get("/carton-mark/layouts/{identifier}/preview")
async def preview_saved_layout(identifier: str, factory_id: str, order_id: str, issue_id: str,
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    scope = mark_layout.context(db, user, factory_id, order_id, issue_id)
    row = next((row for row in mark_layout.rows(db, scope) if row.id == identifier), None)
    if not row:
        raise HTTPException(404, "未找到此客户排版模板")
    frozen = mark_layout.frozen(row)
    db.rollback()
    return await run_in_threadpool(mark_layout.reference_image, frozen["reference_bytes"], frozen["config"]["reference_page"])


@router.post("/carton-mark/layouts", response_model=SupplierMarkLayoutOut, status_code=201)
async def save_layout(request: Request, factory_id: str = Form(..., max_length=64),
        order_id: str = Form(..., max_length=96), issue_id: str = Form(..., max_length=96),
        name: str = Form(..., min_length=1, max_length=128), config: str = Form(..., max_length=12000),
        expected_version: int = Form(0, ge=0), base_template_id: str = Form("", max_length=96),
        reference_pdf: UploadFile | None = File(None), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    scope = mark_layout.context(db, user, factory_id, order_id, issue_id, write=True)
    try:
        parsed = MarkLayoutConfig.model_validate_json(config)
    except ValueError as exc:
        raise HTTPException(422, "客户版式设置无效，请检查字段位置和选取区域") from exc
    if reference_pdf:
        if not (reference_pdf.filename or "").lower().endswith(".pdf"):
            raise HTTPException(422, "请上传客户历史 PDF")
        reference = (reference_pdf.filename, await reference_pdf.read(MAX_DOCUMENT_FILE_BYTES + 1))
    else:
        current = mark_layout.current(db, user, factory_id, order_id, issue_id, base_template_id)
        row = next(row for row in mark_layout.rows(db, scope) if row.id == current["id"])
        reference = (row.reference_name, current["reference_bytes"])
    db.rollback()
    await run_in_threadpool(mark_layout.validate_reference, reference[1], parsed)
    _lock_receipt_factory(db, factory_id)
    fresh = get_current_user(request, db)
    if mark_layout.context(db, fresh, factory_id, order_id, issue_id, write=True) != scope:
        raise HTTPException(409, "采购订单客户或供应商已变更，请刷新后重新配置模板")
    return mark_layout.save(db, fresh, scope, name, parsed, reference, expected_version)


@router.get("/carton-mark/checks", response_model=list[SupplierMarkCheckOut])
def carton_mark_checks(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return [record for record, _ in mark_check.visible_checks(db, user, factory_id)]


from app.schemas.carton_mark import CartonMarkManualReviewRequest
from app.services import carton_mark_manual_review as manual_review


@router.post("/carton-mark/manual-reviews", response_model=SupplierMarkCheckOut, status_code=201)
async def submit_manual_review(payload: CartonMarkManualReviewRequest, request: Request,
                               db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return await manual_review.create_review(request, db, user, payload, supplier=True)


@router.post("/carton-mark/checks", response_model=SupplierMarkCheckOut, status_code=201)
async def create_carton_mark_check(request: Request, factory_id: str = Form(..., max_length=64),
        order_id: str = Form(..., max_length=96), issue_id: str = Form(..., max_length=96),
        excel_asset_id: str = Form(..., max_length=96), expected_revision: int = Form(..., ge=1),
        print_pdf: UploadFile | None = File(None), pdf_asset_id: str = Form("", max_length=96),
        expected_pdf_revision: int | None = Form(None, ge=1), db: Session = Depends(get_db),
        user: AuthContext = Depends(get_current_user)):
    source = mark_check.check_source(db, user, factory_id, order_id, issue_id, excel_asset_id, expected_revision)
    if bool(print_pdf) == bool(pdf_asset_id) or bool(pdf_asset_id) != (expected_pdf_revision is not None):
        raise HTTPException(422, "请上传一个 PDF，或选择资料库中当前版本的 PDF")
    if pdf_asset_id:
        source.update(mark_check.check_pdf_source(db, user, factory_id, order_id, issue_id, pdf_asset_id, expected_pdf_revision))
        pdf_bytes, pdf_name = source["pdf_bytes"], source["pdf_file_name"]
    else:
        if print_pdf.size is not None and print_pdf.size > MAX_DOCUMENT_FILE_BYTES:
            raise HTTPException(413, "打印 PDF 不能超过 20 MB")
        pdf_bytes, pdf_name = await print_pdf.read(MAX_DOCUMENT_FILE_BYTES + 1), print_pdf.filename or ""
        if len(pdf_bytes) > MAX_DOCUMENT_FILE_BYTES:
            raise HTTPException(413, "打印 PDF 不能超过 20 MB")
        if not pdf_bytes:
            raise HTTPException(400, "打印 PDF 不能为空")
    # Do not hold a business transaction while parsing documents.
    db.rollback()
    try:
        result = await run_in_threadpool(build_carton_mark_document_check,
            excel_file_name=source["excel_file_name"], excel_bytes=source["excel_bytes"],
            pdf_file_name=pdf_name, pdf_bytes=pdf_bytes)
    except CartonMarkDocumentConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except CartonMarkDocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    _lock_receipt_factory(db, factory_id)
    fresh_user = get_current_user(request, db)
    # Lock both originals in deterministic order before rechecking visibility.
    list(db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory_id,
        CartonMarkAsset.id.in_([excel_asset_id, pdf_asset_id])).order_by(CartonMarkAsset.id).with_for_update()))
    current = mark_check.check_source(db, fresh_user, factory_id, order_id, issue_id, excel_asset_id, expected_revision)
    if pdf_asset_id:
        current.update(mark_check.check_pdf_source(db, fresh_user, factory_id, order_id, issue_id, pdf_asset_id, expected_pdf_revision))
    if source != current:
        raise HTTPException(409, "订单或 Excel 资料已变更，请刷新后重新选择")
    return mark_check.save_check(db, fresh_user, current, pdf_bytes, result)


@router.get("/carton-mark/checks/{identifier}/documents/{kind}")
def carton_mark_check_document(identifier: str, kind: str, factory_id: str, preview: bool = False,
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    document = mark_check.check_document(db, user, factory_id, identifier, kind)
    return Response(document.content, media_type=document.content_type, headers={
        "Content-Disposition": ("inline" if preview and kind == "print_pdf" else "attachment")
            + "; filename*=UTF-8''" + quote(document.file_name, safe=""),
        "Content-Length": str(document.size_bytes), "X-Content-SHA256": document.sha256,
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.get("/carton-mark/templates/{template_id}/documents/{kind}")
def carton_mark_document(template_id: str, kind: str, factory_id: str, preview: bool = False,
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    document = service.supplier_mark_document(db, user, factory_id, template_id, kind)
    disposition = "inline" if preview and kind == "print_pdf" else "attachment"
    return Response(document.content, media_type=document.content_type, headers={
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(document.file_name, safe=""),
        "Content-Length": str(document.size_bytes), "X-Content-SHA256": document.sha256,
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.post("/orders/{order_id}/cancellation-ack")
def acknowledge_cancellation(order_id: str, payload: CancellationAcknowledge, db: Session = Depends(get_db),
                             user: AuthContext = Depends(get_current_user)):
    return service.acknowledge_cancellation(db, user, order_id, payload)


@router.post("/orders/{order_id}/rush-ack")
def acknowledge_rush(order_id: str, payload: RushAcknowledge, db: Session = Depends(get_db),
                     user: AuthContext = Depends(get_current_user)):
    return service.acknowledge_rush(db, user, order_id, payload)


@router.put("/papers/{line_id}/commitment")
def accept(line_id: str, payload: CommitmentSave, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.accept_line(db, user, line_id, payload)

@router.put("/commitments/batch")
def accept_batch(payload: BatchCommitmentSave, db: Session = Depends(get_db),
                 user: AuthContext = Depends(get_current_user)):
    return {"order_ids": service.accept_lines(db, user, payload)}

@router.post("/shipments", status_code=201)
def ship(payload: ShipmentCreate, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.create_shipment(db, user, payload)


@router.post("/shipments/import-preview")
async def preview_shipment_import(file: UploadFile = File(...), row_selections: str = Form("[]"), db: Session = Depends(get_db),
                                  user: AuthContext = Depends(get_current_user)):
    try:
        choices = json.loads(row_selections)
    except (ValueError, TypeError):
        raise HTTPException(422, "送货明细订单选择格式无效") from None
    return delivery_import.preview(db, user, file.filename or "", await file.read(service.MAX_FILE + 1), choices)


@router.post("/shipments/import-confirm")
async def confirm_shipment_import(file: UploadFile = File(...), sha256: str = Form(...),
                                  selections: str = Form(...), row_selections: str = Form("[]"), db: Session = Depends(get_db),
                                  user: AuthContext = Depends(get_current_user)):
    try:
        choices = json.loads(row_selections)
        raw = json.loads(selections)
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise ValueError()
        keys = [(item["factory_id"], item["delivery_note_no"], item.get("registration_mode", "SHIPMENT")) for item in raw]
        if any(not isinstance(factory, str) or not isinstance(note, str) or mode not in {"SHIPMENT", "EXISTING_RECEIPT"}
            for factory, note, mode in keys):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "所选送货单格式无效") from None
    return delivery_import.confirm(db, user, file.filename or "", await file.read(service.MAX_FILE + 1), sha256, keys, choices)

@router.get("/attachments/{attachment_id}")
def download(attachment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    row = service.attachment_download(db, user, factory_id, attachment_id)
    return file_response(row)

@router.get("/internal/workspace")
def internal_workspace(factory_id: str, responsibility_scope: str = Query("OWN", pattern="^(OWN|ALL)$"), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, internal=True, responsibility_scope=responsibility_scope)

@router.get("/internal/shipments/pending")
def internal_pending_shipments(factory_id: str, limit: int = Query(default=3, ge=1, le=100),
                              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.pending_shipments(db, user, factory_id, limit=limit)

@router.post("/internal/shipments/{shipment_id}/receive")
def receive(shipment_id: str, payload: ShipmentReceive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.receive_shipment(db, user, shipment_id, payload)


@router.post("/internal/shipments/{shipment_id}/defer")
def defer_shipment(shipment_id: str, payload: ShipmentStatusChange, db: Session = Depends(get_db),
                   user: AuthContext = Depends(get_current_user)):
    return service.change_non_arrival(db, user, shipment_id, payload)


@router.post("/internal/shipments/{shipment_id}/reopen")
def reopen_shipment(shipment_id: str, payload: ShipmentStatusChange, db: Session = Depends(get_db),
                    user: AuthContext = Depends(get_current_user)):
    return service.change_non_arrival(db, user, shipment_id, payload, reopen=True)


@router.get("/internal/shipments/{shipment_id}/receipt-options")
def shipment_receipt_options(shipment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return receipt_link.options(db, user, factory_id, shipment_id)


@router.post("/internal/shipments/{shipment_id}/link-receipt")
def link_shipment_receipt(shipment_id: str, payload: ShipmentReceiptLink, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return receipt_link.associate(db, user, shipment_id, payload)

@router.post("/internal/receipt-lines/{receipt_line_id}/link-order")
def link_sample_receipt(receipt_line_id: str, payload: SampleReceiptLink,
                        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.link_sample_receipt(db, user, receipt_line_id, payload)


@router.post("/internal/shipments/{shipment_id}/lines/{line_id}/link-order")
def link_shipment_line(shipment_id: str, line_id: str, payload: ShipmentLineLink,
                       db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.link_shipment_line(db, user, shipment_id, line_id, payload)

@router.post("/internal/orders/{order_id}/attachments", status_code=201)
async def upload(order_id: str, factory_id: str = Form(...), file: UploadFile = File(...),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    service.internal_permission(user, factory_id, "carton_procurement:order_write")
    content = await file.read(service.MAX_FILE + 1)
    return service.upload_attachment(db, user, factory_id, order_id, file.filename or "", content)

@router.get("/internal/attachments/{attachment_id}")
def internal_download(attachment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return file_response(service.attachment_download(db, user, factory_id, attachment_id, internal=True))

def file_response(row):
    return Response(row.content, media_type=row.media_type, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename, safe=""),
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


from app.schemas.carton_material_correction import MaterialCorrectionAction
from app.services import carton_material_correction as material_corrections

@router.get("/material-corrections")
def supplier_material_corrections(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return material_corrections.supplier_records(db, user, factory_id)

@router.post("/material-corrections/{identifier}/actions")
def decide_material_correction(identifier: str, payload: MaterialCorrectionAction, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return material_corrections.act(db, user, identifier, payload, supplier=True)

@router.get('/print-splits/{identifier}/files/{asset_id}')
def print_split_file(identifier: str, asset_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_print_split import download
    asset, frozen = download(db, current_user, factory_id, identifier, asset_id, supplier=True)
    return Response(asset.content, media_type=frozen['content_type'],
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(frozen['file_name'])})
