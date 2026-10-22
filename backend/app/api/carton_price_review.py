from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_price_review import Propose, Decide
from app.services import carton_price_review as service

router = APIRouter(prefix="/api/carton-price-reviews", tags=["carton-price-reviews"])


@router.get("/internal")
def internal(factory_id: str, shipment_id: str | None = None, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, shipment_id=shipment_id)


@router.get("/supplier")
def supplier(factory_id: str, shipment_id: str | None = None, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, external=True, shipment_id=shipment_id)


@router.post("/internal/{identifier}/propose")
def propose(identifier: str, payload: Propose, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.act(db, user, identifier, payload)


@router.post("/supplier/{identifier}/decide")
def decide(identifier: str, payload: Decide, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.act(db, user, identifier, payload, external=True)
