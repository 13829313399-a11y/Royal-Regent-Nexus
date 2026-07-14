from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.carton_mark import CartonMarkAutoCheckResponse, CartonMarkBatchCheckResponse
from app.services.auth import AuthContext, ensure_permission, get_current_user
from app.services.carton_mark import build_carton_mark_auto_check, build_carton_mark_batch_auto_check

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


@router.post("/api/carton-mark/batch-auto-check", response_model=CartonMarkBatchCheckResponse)
async def batch_auto_check_carton_mark(
    customer_name: str = Form(""),
    po: str = Form(""),
    item: str = Form(""),
    pdf_template: UploadFile = File(...),
    front_photos: list[UploadFile] = File(default=[]),
    side_photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "carton_mark:review")

    pdf_bytes = await pdf_template.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 模板不能为空。")
    if not front_photos and not side_photos:
        raise HTTPException(status_code=400, detail="请至少上传一张正唛或侧唛图片。")

    async def read_images(files: list[UploadFile], side_label: str) -> list[tuple[str, bytes]]:
        images: list[tuple[str, bytes]] = []
        for index, photo in enumerate(files):
            image_bytes = await photo.read()
            if not image_bytes:
                raise HTTPException(status_code=400, detail=f"{side_label}第 {index + 1} 张图片为空。")
            images.append((photo.filename or f"{side_label}-{index + 1}", image_bytes))
        return images

    front_images = await read_images(front_photos, "正唛")
    side_images = await read_images(side_photos, "侧唛")
    return build_carton_mark_batch_auto_check(
        pdf_bytes=pdf_bytes,
        front_images=front_images,
        side_images=side_images,
        customer_name=customer_name,
        po=po,
        item=item,
    )
