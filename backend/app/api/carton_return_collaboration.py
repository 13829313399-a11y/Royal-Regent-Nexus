from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_return_collaboration import ReturnAction
from app.services import carton_return_collaboration as service


def make_router(external=False):
    router = APIRouter(prefix="/api/carton-supplier/returns" if external else "/api/carton-procurement/returns", tags=["carton-return-collaboration"])

    @router.get("/workspace")
    def workspace(factory_id: str, status: str | None = None, keyword: str = "", limit: int = Query(50, ge=1, le=100),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.workspace(db, user, factory_id, external=external, status=status, keyword=keyword, limit=limit, offset=offset)

    @router.get("/{identifier}")
    def detail(identifier: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.detail(db, user, factory_id, identifier, external=external)

    @router.post("/{identifier}/actions")
    def action(identifier: str, payload: ReturnAction, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.act(db, user, identifier, payload, external=external)

    return router


router = make_router()
supplier_router = make_router(True)
