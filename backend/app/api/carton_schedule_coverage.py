from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services import carton_schedule_coverage as service
from app.schemas.carton_schedule_coverage import MissingReview

router = APIRouter(prefix="/api/carton-procurement/schedule-coverage", tags=["carton-schedule-coverage"])


@router.get("/workspace")
def workspace(factory_id: str, customer_code: str = "", status: str = "PENDING", keyword: str = Query("", max_length=128),
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.workspace(db, user, factory_id, customer_code=customer_code, status=status, keyword=keyword, limit=limit, offset=offset)


@router.get("/missing/{identifier}")
def detail(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.detail(db, user, factory_id, identifier)


@router.post("/missing/{identifier}/review")
def review(identifier: str, payload: MissingReview, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.review(db, user, identifier, payload)
