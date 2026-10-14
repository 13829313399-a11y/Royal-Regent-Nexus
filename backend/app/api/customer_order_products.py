from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import ensure_permission_for_departments, has_permission_for_departments
from app.services.customer_order_ledger import actor_name
from app.api.customer_order_ledger import transaction
from app.schemas.customer_order_products import ProductSave
from app.services import customer_order_products as service
from app.models.customer_order_products import OrderProductChange as Change, OrderProductExportEvidence as Evidence

router = APIRouter(prefix="/api/customer-order-product-rules", tags=["customer-order-product-rules"])


def guard(db, user, factory, customer, action="read"):
    if (factory, customer) != (service.FACTORY, service.CUSTOMER):
        raise HTTPException(400, "新货号维护仅支持华兴 Dickie")
    ensure_permission_for_departments(db, user, "customer_order:" + action, factory, ("sales-business",))


@router.get("")
def catalog(factory_id: str, customer_code: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id, customer_code)
    result = service.snapshot(db)
    result["can_write"] = result["available"] and has_permission_for_departments(user, "customer_order:write", factory_id, ("sales-business",))
    return result


@router.post("")
def save(factory_id: str, customer_code: str, body: ProductSave, request: Request,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    if request.headers.get("X-Order-Product-Rules") != "1":
        raise HTTPException(403, "请从订单中心的新货号维护页面操作")
    guard(db, user, factory_id, customer_code)
    guard(db, user, factory_id, customer_code, "write")
    return transaction(db, lambda: service.save(db, body, actor_name(user)))


@router.get("/history")
def history(factory_id: str, customer_code: str, product_no: str = "", page: int = 1,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id, customer_code)
    if not service.ready(db):
        raise HTTPException(503, "新货号维护尚未执行迁移 20261014_0161")
    if not 1 <= page <= 10000 or len(product_no) > 80:
        raise HTTPException(400, "页码或货号无效")
    query = select(Change).where(Change.factory_id == factory_id, Change.customer_code == customer_code)
    if product_no:
        query = query.where(Change.product_key == service.key(product_no))
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Change.revision.desc()).offset((page - 1) * 20).limit(20))
    return {"total": count, "items": [{"revision": r.revision, "product_key": r.product_key, "actor": r.actor, "created_at": r.created_at, "data": r.data} for r in rows]}


@router.get("/exports/{audit_id}")
def evidence(audit_id: str, factory_id: str, customer_code: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    guard(db, user, factory_id, customer_code, "audit_read")
    if not service.ready(db):
        raise HTTPException(503, "新货号维护尚未执行迁移 20261014_0161")
    item = db.scalar(select(Evidence).where(Evidence.audit_id == audit_id, Evidence.factory_id == factory_id, Evidence.customer_code == customer_code))
    if not item:
        raise HTTPException(404, "未找到产品规则导出证据")
    return item.data
