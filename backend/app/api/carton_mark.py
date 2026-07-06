from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.carton_mark import CartonMarkAutoCheckResponse
from app.services.auth import AuthContext, ensure_permission, get_current_user
from app.services.carton_mark import build_carton_mark_auto_check

router = APIRouter()


@router.post("/api/carton-mark/auto-check", response_model=CartonMarkAutoCheckResponse)
async def auto_check_carton_mark(
    customer_name: str = Form(""),
    po: str = Form(""),
    item: str = Form(""),
    pdf_template: UploadFile = File(...),
    front_photo: UploadFile = File(...),
    side_photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "carton_mark:review")

    pdf_bytes = await pdf_template.read()
    front_image_bytes = await front_photo.read()
    side_image_bytes = await side_photo.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 模板不能为空。")
    if not front_image_bytes:
        raise HTTPException(status_code=400, detail="正唛图片不能为空。")
    if not side_image_bytes:
        raise HTTPException(status_code=400, detail="侧唛图片不能为空。")

    return build_carton_mark_auto_check(
        pdf_bytes=pdf_bytes,
        front_image_bytes=front_image_bytes,
        side_image_bytes=side_image_bytes,
        customer_name=customer_name,
        po=po,
        item=item,
    )
