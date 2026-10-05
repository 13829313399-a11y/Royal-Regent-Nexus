from urllib.parse import quote
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_portal import CommitmentSave, BatchCommitmentSave, ShipmentCreate, ShipmentReceive, SampleReceiptLink, ShipmentLineLink, SupplierMarkTemplateOut, SupplierDocumentExport
from app.services import carton_supplier_portal as service
from app.services import carton_supplier_delivery_import as delivery_import
from app.services import carton_supplier_settlement as settlement
from app.schemas.carton_supplier_settlement import SupplierSettlementReview
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

@router.get("/carton-mark/templates", response_model=list[SupplierMarkTemplateOut])
def carton_mark_templates(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.supplier_mark_templates(db, user, factory_id)

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
        keys = [(item["factory_id"], item["delivery_note_no"]) for item in raw]
        if any(not isinstance(factory, str) or not isinstance(note, str)
            for factory, note in keys):
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
