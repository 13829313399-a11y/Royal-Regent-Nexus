from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.pricing import PricingContext, PricingQuoteCreate, PricingQuoteOut
from app.services.auth import AuthContext, ensure_permission_in_scope, get_current_user
from app.services.pricing import create_quote, get_pricing_context, list_quotes


router = APIRouter(prefix="/api/pricing")


@router.get("/context", response_model=PricingContext)
def read_pricing_context(
    customer_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "internal_pricing:read", factory_id, "sales-business")
    return get_pricing_context(customer_id)


@router.get("/quotes", response_model=list[PricingQuoteOut])
def read_pricing_quotes(
    factory_id: str,
    customer_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "internal_pricing:read", factory_id, "sales-business")
    return list_quotes(db, factory_id, customer_id)


@router.post("/quotes", response_model=PricingQuoteOut, status_code=status.HTTP_201_CREATED)
def submit_pricing_quote(
    payload: PricingQuoteCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "internal_pricing:create", payload.factory_id, "sales-business")
    return create_quote(db, payload, current_user.id)
