from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.api.carton_procurement import _ensure_permission
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_settlement import SettlementSave, SettlementAction, AcceptanceDateUpdate
from app.services import carton_supplier_settlement as service

router = APIRouter(prefix="/api/carton-procurement", tags=["carton-supplier-settlement"])


@router.get("/supplier-settlements/workspace")
def workspace(factory_id: str, period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
              supplier_id: str | None = None, currency: str = "CNY",
              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return service.workspace(db, factory_id, supplier_id, period, currency)


@router.post("/supplier-settlements")
def save(payload: SettlementSave, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:closing_manage", payload.factory_id)
    return service.save(db, payload, user)


@router.post("/supplier-settlements/{identifier}/confirm")
def confirm(identifier: str, payload: SettlementAction, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:closing_manage", payload.factory_id)
    _ensure_permission(db, user, "carton_procurement:order_adjust", payload.factory_id)
    return service.act(db, identifier, payload, user)


@router.post("/supplier-settlements/{identifier}/reopen")
def reopen(identifier: str, payload: SettlementAction, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:closing_manage", payload.factory_id)
    _ensure_permission(db, user, "carton_procurement:order_adjust", payload.factory_id)
    return service.act(db, identifier, payload, user, reopen=True)


@router.post("/receipts/{identifier}/acceptance-date")
def acceptance_date(identifier: str, payload: AcceptanceDateUpdate, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:closing_manage", payload.factory_id)
    return service.set_acceptance_date(db, identifier, payload, user)
