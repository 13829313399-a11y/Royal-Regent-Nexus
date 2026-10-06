from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, HTTPException, Query
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.carton_feedback import CartonFeedbackImage
from app.schemas.carton_feedback import FeedbackReplyRequest, FeatureUpdateRequest
from app.services.auth import AuthContext, get_current_user
from app.services import carton_feedback as service

router = APIRouter(prefix="/api/carton-feedback")


@router.get("")
def workspace(factory_id: str, all_feedback: bool = False, search: str = Query(default="", max_length=128),
              portal: Literal["internal", "supplier"] = "internal", updates_audience: Literal["INTERNAL", "SUPPLIER"] = "INTERNAL",
              status: Literal["", "OPEN", "FIXED", "DECLINED"] = "", date_from: str = "", date_to: str = "",
              sort: Literal["ASC", "DESC"] = "DESC", limit: int = Query(default=100, ge=1, le=100),
              offset: int = Query(default=0, ge=0), updates_offset: int = Query(default=0, ge=0),
              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = service.scope(user, factory_id, db=db, supplier=portal == "supplier")
    return service.workspace(db, user, factory, all_feedback, supplier=portal == "supplier", updates_audience=updates_audience, search=search.strip(), status=status,
        date_from=date_from, date_to=date_to, sort=sort, limit=limit, offset=offset, updates_offset=updates_offset)


@router.post("")
async def create(factory_id: str = Form(...), title: str = Form(...), description: str = Form(...),
    context_path: str = Form(...), request_key: str = Form(...), files: list[UploadFile] | None = File(None),
    portal: Literal["internal", "supplier"] = Form("internal"),
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = service.scope(user, factory_id, db=db, supplier=portal == "supplier")
    if len(files or []) > 3:
        raise HTTPException(422, "最多上传 3 张截图")
    images = [service.normalize_image(await file.read(service.MAX_IMAGE_BYTES + 1)) for file in files or []]
    return service.create(db, user, factory, title, description, context_path, request_key, images, supplier=portal == "supplier")


@router.get("/{feedback_id}")
def detail(feedback_id: str, factory_id: str, portal: Literal["internal", "supplier"] = "internal", db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.detail(db, user, service.scope(user, factory_id, db=db, supplier=portal == "supplier"), feedback_id, supplier=portal == "supplier")


@router.post("/{feedback_id}/reply")
def reply(feedback_id: str, payload: FeedbackReplyRequest, factory_id: str,
    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.reply(db, user, service.scope(user, factory_id), feedback_id, payload)


@router.get("/{feedback_id}/images/{image_id}")
def image(feedback_id: str, image_id: str, factory_id: str, portal: Literal["internal", "supplier"] = "internal", db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = service.scope(user, factory_id, db=db, supplier=portal == "supplier")
    service.feedback_row(db, user, factory, feedback_id, supplier=portal == "supplier")
    row = db.scalar(select(CartonFeedbackImage).where(CartonFeedbackImage.feedback_id == feedback_id,
        CartonFeedbackImage.factory_id == factory, CartonFeedbackImage.id == image_id))
    if row is None:
        raise HTTPException(404, "截图不存在")
    return Response(row.content, media_type="image/png", headers={"Cache-Control": "private, no-store",
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})


@router.post("/updates/publish")
def publish(payload: FeatureUpdateRequest, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.publish(db, user, service.scope(user, factory_id), payload)
