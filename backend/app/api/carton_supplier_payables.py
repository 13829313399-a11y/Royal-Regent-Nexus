from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.schemas.carton_supplier_payables import PayablesAction
from app.services import carton_supplier_payables as service

router = APIRouter(tags=["carton-supplier-payables"])


def _routes(prefix, external):
    @router.get(prefix + "/workspace")
    def workspace(factory_id: str, supplier_id: str | None = None, currency: str = "CNY", kind: str = "ALL", status: str = "ALL", keyword: str = Query(default="", max_length=200),
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.workspace(db, user, factory_id, supplier_id, currency, external=external, kind=kind, status=status, keyword=keyword, limit=limit, offset=offset)

    @router.get(prefix + "/records/{record_id}")
    def detail(record_id: str, factory_id: str, supplier_id: str | None = None, currency: str = "CNY", db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.detail(db, user, factory_id, record_id, supplier_id, currency, external=external)

    @router.post(prefix + "/actions")
    def actions(payload: PayablesAction, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return service.act(db, user, payload, external=external)

    @router.get(prefix + "/export")
    def export(factory_id: str, supplier_id: str | None = None, currency: str = "CNY", db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
        return Response(service.export_csv(db, user, factory_id, supplier_id, currency, external=external), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=supplier-payables.csv"})


_routes("/api/carton-procurement/payables", False)
_routes("/api/carton-supplier/payables", True)
