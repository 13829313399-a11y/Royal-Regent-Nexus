from urllib.parse import quote
from typing import Literal
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.carton_mark import CartonMarkAsset
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_portal import CommitmentSave, BatchCommitmentSave, ShipmentCreate, ShipmentReceive, ShipmentReceiptLink, SampleReceiptLink, ShipmentLineLink, SupplierMarkTemplateOut, SupplierDocumentExport
from app.services import carton_supplier_portal as service
from app.services import carton_supplier_delivery_import as delivery_import
from app.services import carton_supplier_receipt_link as receipt_link
from app.services import carton_supplier_settlement as settlement
from app.schemas.carton_supplier_settlement import SupplierSettlementReview
from app.schemas.carton_supplier_portal import SupplierMarkAssetOut, SupplierMarkCheckOut, SupplierMarkUploadOrderOut, SupplierMarkAssetUploadOut
from app.services import carton_supplier_mark_check as mark_check
from app.services import carton_supplier_mark_upload as mark_upload
from app.services.carton_mark import (MAX_DOCUMENT_FILE_BYTES, build_carton_mark_document_check,
    CartonMarkDocumentError, CartonMarkDocumentConfigurationError)
from app.services.carton_procurement import _lock_receipt_factory
import json

router = APIRouter(prefix="/api/carton-supplier", tags=["carton-supplier"])

@router.get("/memberships")
def memberships(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return [{"factory_id": supplier.factory_id, "supplier_name": supplier.supplier_name}
        for supplier in service.supplier_factories(db, user)]


@router.get("/settlements/workspace")
def settlement_workspace(factory_id: str, period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), currency: str = "CNY",
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return settlement.supplier_workspace(db, user, factory_id, period, currency)


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


@router.get("/carton-mark/assets/{asset_id}/document")
def carton_mark_asset_document(asset_id: str, factory_id: str, preview: bool = False,
                              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    asset = service.supplier_mark_asset_document(db, user, factory_id, asset_id)
    disposition = "inline" if preview and asset.kind in {"pdf", "image"} else "attachment"
    return Response(asset.content, media_type=asset.content_type, headers={
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(asset.file_name, safe=""),
        "Content-Length": str(asset.size_bytes), "X-Content-SHA256": asset.sha256,
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/carton-mark/upload-orders", response_model=list[SupplierMarkUploadOrderOut])
def carton_mark_upload_orders(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return mark_upload.upload_orders(db, user, factory_id)


@router.post("/carton-mark/assets/upload", response_model=list[SupplierMarkAssetUploadOut], status_code=201)
async def upload_carton_mark_assets(request: Request, factory_id: str = Form(..., max_length=64),
        order_id: str = Form("", max_length=96), issue_id: str = Form("", max_length=96),
        files: list[UploadFile] = File(...), db: Session = Depends(get_db),
        user: AuthContext = Depends(get_current_user)):
    orders = mark_upload.upload_orders(db, user, factory_id)
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
    _lock_receipt_factory(db, factory_id)
    return mark_upload.save_batch(db, get_current_user(request, db), factory_id, parsed, orders, order_id, issue_id)


@router.get("/carton-mark/templates", response_model=list[SupplierMarkTemplateOut])
def carton_mark_templates(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_mark_templates(db, user, factory_id)


@router.get("/carton-mark/checks", response_model=list[SupplierMarkCheckOut])
def carton_mark_checks(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return [record for record, _ in mark_check.visible_checks(db, user, factory_id)]


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
async def preview_shipment_import(file: UploadFile = File(...), db: Session = Depends(get_db),
                                  user: AuthContext = Depends(get_current_user)):
    return delivery_import.preview(db, user, file.filename or "", await file.read(service.MAX_FILE + 1))


@router.post("/shipments/import-confirm")
async def confirm_shipment_import(file: UploadFile = File(...), sha256: str = Form(...),
                                  selections: str = Form(...), db: Session = Depends(get_db),
                                  user: AuthContext = Depends(get_current_user)):
    try:
        raw = json.loads(selections)
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise ValueError()
        keys = [(item["factory_id"], item["delivery_note_no"], item.get("registration_mode", "SHIPMENT")) for item in raw]
        if any(not isinstance(factory, str) or not isinstance(note, str) or mode not in {"SHIPMENT", "EXISTING_RECEIPT"}
            for factory, note, mode in keys):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "所选送货单格式无效") from None
    return delivery_import.confirm(db, user, file.filename or "", await file.read(service.MAX_FILE + 1), sha256, keys)

@router.get("/attachments/{attachment_id}")
def download(attachment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    row = service.attachment_download(db, user, factory_id, attachment_id)
    return file_response(row)

@router.get("/internal/workspace")
def internal_workspace(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, internal=True)

@router.get("/internal/shipments/pending")
def internal_pending_shipments(factory_id: str, limit: int = Query(default=3, ge=1, le=100),
                              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.pending_shipments(db, user, factory_id, limit=limit)

@router.post("/internal/shipments/{shipment_id}/receive")
def receive(shipment_id: str, payload: ShipmentReceive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.receive_shipment(db, user, shipment_id, payload)


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
