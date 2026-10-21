"""Internal and supplier entry points for the same versioned request contract."""
from urllib.parse import quote
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, UploadFile, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas import carton_special_requests as schema
from app.services import carton_special_requests as service


def make_router(external=False):
    router = APIRouter(prefix="/api/carton-supplier/special-requests" if external else "/api/carton-special-requests", tags=["carton-special-requests"])

    @router.get("/{identifier}/purchase-orders")
    def purchase_context(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        from app.services import carton_special_purchase
        return carton_special_purchase.context(db, user, factory_id, identifier, external=external)

    @router.get("/{identifier}/purchase-orders/{version_id}/export")
    def purchase_export(identifier: str, version_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        from app.services import carton_special_purchase
        from app.services.carton_procurement_export import XLSX_MEDIA_TYPE
        content, filename = carton_special_purchase.export(db, user, factory_id, identifier, version_id, external=external)
        return Response(content, media_type=XLSX_MEDIA_TYPE, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)})

    @router.get("")
    def workspace(factory_id: str, responsibility_scope: Literal["OWN", "ALL"] = "OWN",
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.workspace(db, user, factory_id, external=external, responsibility_scope=responsibility_scope)

    if external:
        @router.get('/mark-options')
        def supplier_mark_options(factory_id: str, request_id: str = '', db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_special_marks import options
            return options(db, user, factory_id, request_id=request_id, external=True)

        @router.post('/{identifier}/lines/{line_id}/mark')
        def supplier_propose_mark(identifier: str, line_id: str, payload: schema.MarkSet,
                                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_special_marks import propose_mark
            return propose_mark(db, user, identifier, line_id, payload)

    if external:
        @router.get("/factories")
        def factories(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from sqlalchemy import select
            from app.models.carton_procurement import CartonSupplier
            return [{"factory_id": item.factory_id, "supplier_name": item.supplier_name}
                for item in db.scalars(select(CartonSupplier).where(CartonSupplier.supplier_code == "HEYUAN-DONGKANG", CartonSupplier.status == "ACTIVE").order_by(CartonSupplier.factory_id))
                if service.portal.supplier_permission(user, "carton_supplier:read", item.factory_id)]

        @router.post("/gifts", status_code=201)
        def gift(payload: schema.Create, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.create(db, user, payload, external=True)

        @router.post("/{identifier}/quote")
        def quote_request(identifier: str, payload: schema.Quote, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.action(db, user, identifier, payload, "QUOTE", external=True)

        @router.post("/{identifier}/ship")
        def ship(identifier: str, payload: schema.Ship, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.ship(db, user, identifier, payload)
    else:
        @router.get("/{identifier}/stock-actions")
        def stock_preview(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services import carton_special_stock
            return carton_special_stock.preview(db, user, factory_id, identifier)

        @router.post("/{identifier}/stock-actions")
        def stock_action(identifier: str, payload: schema.StockAction, request: Request,
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services import carton_special_stock
            return carton_special_stock.submit(db, user, identifier, payload, refresh_actor=lambda: get_current_user(request, db))

        @router.post("/{identifier}/stock-actions/undo")
        def stock_undo(identifier: str, payload: schema.Delete, request: Request,
                       db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services import carton_special_stock
            return carton_special_stock.undo(db, user, identifier, payload, refresh_actor=lambda: get_current_user(request, db))

        @router.get("/mark-options")
        def mark_options(factory_id: str, request_id: str = '', db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_special_marks import options
            return options(db, user, factory_id, request_id=request_id)

        @router.post("/{identifier}/lines/{line_id}/mark")
        def set_mark(identifier: str, line_id: str, payload: schema.MarkSet,
                     db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_special_marks import set_mark as save
            return save(db, user, identifier, line_id, payload)

        @router.post("", status_code=201)
        def create(payload: schema.Create, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.create(db, user, payload)

        @router.put("/{identifier}")
        def update(identifier: str, payload: schema.Create, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.update(db, user, identifier, payload)

        @router.post("/{identifier}/send")
        def send(identifier: str, payload: schema.Command, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.action(db, user, identifier, payload, "SEND")

        @router.post("/{identifier}/confirm")
        def confirm(identifier: str, payload: schema.Command, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.action(db, user, identifier, payload, "SEND")

        @router.post("/{identifier}/adjust")
        def adjust(identifier: str, payload: schema.Adjust, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.update(db, user, identifier, payload, adjusting=True)

        @router.post("/{identifier}/delete")
        def delete(identifier: str, payload: schema.Delete, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.delete_request(db, user, identifier, payload)

        @router.post("/{identifier}/manual-receive")
        def manual_receive(identifier: str, payload: schema.ManualReceive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_special_manual_receiving import receive
            return receive(db, user, identifier, payload)

        @router.post("/{identifier}/approve")
        def approve(identifier: str, payload: schema.Approve, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.action(db, user, identifier, payload, "APPROVE")

        @router.post("/{identifier}/cancel")
        def cancel(identifier: str, payload: schema.Command, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.action(db, user, identifier, payload, "CANCEL")

        @router.post("/{identifier}/shipments/{shipment_id}/receive")
        def receive(identifier: str, shipment_id: str, payload: schema.Receive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.receive(db, user, identifier, shipment_id, payload)

    @router.get("/{identifier}")
    def detail(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.detail(db, user, factory_id, identifier, external=external)

    @router.post("/{identifier}/attachments", status_code=201)
    async def attachment(identifier: str, factory_id: str = Form(...), request_id: str = Form(...), expected_revision: int = Form(...),
        role: Literal["REFERENCE", "DRAFT", "CONFIRMED"] = Form(...), file: UploadFile = File(...), line_id: str = Form(default=""),
        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        content = await file.read(10 * 1024 * 1024 + 1)
        return service.attachment(db, user, identifier, schema.Command(factory_id=factory_id, request_id=request_id,
            expected_revision=expected_revision), role, file.filename or "attachment", content, external=external, line_id=line_id)

    @router.get("/{identifier}/attachments/{attachment_id}")
    def download(identifier: str, attachment_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        file = service.download(db, user, factory_id, identifier, attachment_id, external=external)
        return Response(file.content, media_type=file.media_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename)}",
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @router.post("/{identifier}/messages")
    def message(identifier: str, payload: schema.Message, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.message(db, user, identifier, payload, external=external)

    return router


router = make_router()
supplier_router = make_router(True)
