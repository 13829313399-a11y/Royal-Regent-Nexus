from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.pricing import PricingContext, PricingQuoteCreate, PricingQuoteOut, QuoteDescriptionTranslationRequest
from app.core.config import settings
from app.services.quote_translation import translate_quote_descriptions
from app.schemas.quote_recognition import QuoteRecognitionRequest
from app.services.quote_recognition import QuoteRecognitionError, recognition_status, recognize_quote_fields
from typing import Literal
from app.services.auth import AuthContext, ensure_permission_in_scope, get_current_user
from app.services.pricing import create_quote, get_pricing_context, list_quotes


router = APIRouter(prefix="/api/pricing")


@router.get("/yinhui-recognition/status")
def yinhui_recognition_status(response: Response, factory_id: Literal["huaxing"] = "huaxing", db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    ensure_permission_in_scope(db, current_user, "customer_price:import_internal_quote", factory_id, "sales-business")
    response.headers["Cache-Control"] = "no-store"
    return recognition_status()


@router.post("/yinhui-recognition")
def yinhui_recognition(payload: QuoteRecognitionRequest, response: Response, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    ensure_permission_in_scope(db, current_user, "customer_price:import_internal_quote", payload.factory_id, "sales-business")
    response.headers["Cache-Control"] = "no-store"
    try:
        return recognize_quote_fields(payload)
    except QuoteRecognitionError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error), headers={"Cache-Control": "no-store"}) from None


@router.post("/translate-descriptions")
def translate_pricing_descriptions(
    payload: QuoteDescriptionTranslationRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "customer_price:import_internal_quote", payload.factory_id, "sales-business")
    if not settings.document_tools_enabled:
        raise HTTPException(status_code=503, detail="本地翻译已被管理员关闭。")
    response.headers["Cache-Control"] = "no-store"
    return translate_quote_descriptions(payload.texts, model_dir=settings.document_translation_model_dir, device=settings.document_translation_device)


@router.get("/context", response_model=PricingContext)
def read_pricing_context(
    customer_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "customer_price:read", factory_id, "sales-business")
    return get_pricing_context(customer_id)


@router.get("/quotes", response_model=list[PricingQuoteOut])
def read_pricing_quotes(
    factory_id: str,
    customer_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "customer_price:read", factory_id, "sales-business")
    return list_quotes(db, factory_id, customer_id)


@router.post("/quotes", response_model=PricingQuoteOut, status_code=status.HTTP_201_CREATED)
def submit_pricing_quote(
    payload: PricingQuoteCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_scope(db, current_user, "customer_price:export_customer_quote", payload.factory_id, "sales-business")
    return create_quote(db, payload, current_user.id)
