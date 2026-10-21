from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from typing import Literal
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas import carton_unified_deliveries as schema
from app.services import carton_unified_deliveries as service


def make_router(external=False):
    router = APIRouter(prefix="/api/carton-supplier/unified-deliveries" if external else "/api/carton-unified-deliveries",
                       tags=["carton-unified-deliveries"])

    @router.get("")
    def workspace(factory_id: str, responsibility_scope: Literal["OWN", "ALL"] = "OWN", db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.workspace(db, user, factory_id, external=external, responsibility_scope=responsibility_scope)

    if external:
        @router.post("", status_code=201)
        def dispatch(payload: schema.Dispatch, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.dispatch(db, user, payload)
    else:
        @router.post('/warehouse-receive')
        def warehouse_receive(payload: schema.WarehouseReceive, request: Request,
                              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            from app.services.carton_warehouse_receiving import receive
            return receive(db, user, payload, refresh_actor=lambda: get_current_user(request, db))

        @router.post("/{identifier}/receive")
        def receive(identifier: str, payload: schema.Receive, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.receive(db, user, identifier, payload)

        @router.post("/{identifier}/reopen-shortfall")
        def reopen_shortfall(identifier: str, payload: schema.ReopenShortfall, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
            return service.reopen_shortfall(db, user, identifier, payload)

    @router.get("/{identifier}")
    def detail(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.project(db, user, factory_id, identifier, external=external)

    return router


router = make_router()
supplier_router = make_router(True)
