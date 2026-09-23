from urllib.parse import quote
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_portal import MemberSave, CommitmentSave, ShipmentCreate, ShipmentReceive
from app.services import carton_supplier_portal as service

router = APIRouter(prefix="/api/carton-supplier", tags=["carton-supplier"])

@router.get("/memberships")
def memberships(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from sqlalchemy import select
    from app.models.carton_supplier_portal import SupplierMember
    from app.models.carton_procurement import CartonSupplier
    return [{"factory_id": member.factory_id, "supplier_name": supplier.supplier_name} for member, supplier in db.execute(
        select(SupplierMember, CartonSupplier).join(CartonSupplier, CartonSupplier.id == SupplierMember.supplier_id).where(
            SupplierMember.user_id == user.id, SupplierMember.status == "ACTIVE", CartonSupplier.status == "ACTIVE",
            CartonSupplier.factory_id == SupplierMember.factory_id)).all()]

@router.get("/workspace")
def workspace(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id)

@router.put("/papers/{line_id}/commitment")
def accept(line_id: str, payload: CommitmentSave, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.accept_line(db, user, line_id, payload)

@router.post("/shipments", status_code=201)
def ship(payload: ShipmentCreate, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.create_shipment(db, user, payload)

@router.get("/attachments/{attachment_id}")
def download(attachment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    row = service.attachment_download(db, user, factory_id, attachment_id)
    return file_response(row)

@router.get("/internal/workspace")
def internal_workspace(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, internal=True)

@router.get("/internal/members")
def members(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.members(db, user, factory_id)

@router.put("/internal/members")
def save_member(payload: MemberSave, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.save_member(db, user, payload)

@router.post("/internal/shipments/{shipment_id}/receive")
def receive(shipment_id: str, payload: ShipmentReceive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.receive_shipment(db, user, shipment_id, payload)

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
