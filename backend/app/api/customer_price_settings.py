from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.customer_price_settings import (
    CustomerPriceSettingsOut, CustomerPriceSettingsRevision,
    CustomerPriceSettingsSnapshotOut, CustomerPriceSettingsUpdate,
)
from app.services.auth import AuthContext, get_current_user
from app.services import customer_price_settings as service


router = APIRouter(prefix="/api/customer-price/settings", tags=["customer-price-settings"])


@router.get("", response_model=CustomerPriceSettingsOut)
def get_settings(factory_id: str = Query(...), customer_id: str = Query(...),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.get_settings(db, factory_id, customer_id, user)


@router.put("", response_model=CustomerPriceSettingsOut)
def put_settings(payload: CustomerPriceSettingsUpdate, request: Request,
                 factory_id: str = Query(...), customer_id: str = Query(...),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.update_settings(db, factory_id, customer_id, payload, user, request)


@router.post("/snapshots", response_model=CustomerPriceSettingsSnapshotOut)
def post_snapshot(payload: CustomerPriceSettingsRevision, request: Request,
                  factory_id: str = Query(...), customer_id: str = Query(...),
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.create_snapshot(db, factory_id, customer_id, payload.revision, user, request)


@router.get("/snapshots/{snapshot_id}", response_model=CustomerPriceSettingsSnapshotOut)
def get_snapshot(snapshot_id: str, db: Session = Depends(get_db),
                 user: AuthContext = Depends(get_current_user)):
    return service.get_snapshot(db, snapshot_id, user)
