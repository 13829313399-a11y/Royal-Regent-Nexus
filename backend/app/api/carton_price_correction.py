from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_price_correction import Action, Preview
from app.services import carton_price_correction as service

router = APIRouter(tags=["carton-price-corrections"])


def register(prefix, external):
    @router.get(prefix + "/workspace")
    def workspace(factory_id: str, status: str = "PENDING", keyword: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=200),
                  offset: int = Query(default=0, ge=0), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.workspace(db,user,factory_id,external=external,status=status,keyword=keyword,limit=limit,offset=offset)

    @router.get(prefix + "/{receipt_line_id}")
    def detail(receipt_line_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.detail(db,user,factory_id,receipt_line_id,external=external)

    @router.post(prefix + "/{receipt_line_id}/actions")
    def action(receipt_line_id: str, payload: Action, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.act(db,user,receipt_line_id,payload,external=external)


register("/api/carton-procurement/price-corrections",False)
register("/api/carton-supplier/price-corrections",True)


@router.post("/api/carton-procurement/price-corrections/{receipt_line_id}/preview")
def preview(receipt_line_id: str, payload: Preview, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.preview(db,user,receipt_line_id,payload)
