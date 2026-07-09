from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_schedule import (
    InjectionScheduleImportPreviewResponse,
    InjectionScheduleMachineOut,
)
from app.services.auth import AuthContext, ensure_permission, ensure_permission_in_scope, get_current_user
from app.services.injection_schedule import (
    create_daily_schedule_import,
    get_import_preview,
    get_machine_status,
)
from app.services.injection_schedule_excel import XLSX_MIME

router = APIRouter(prefix="/api/injection-scheduling")


@router.post(
    "/imports/daily-schedule",
    response_model=InjectionScheduleImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_daily_schedule(
    factory_id: str = Form("huaxing"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    ensure_permission_in_scope(db, current_user, "injection_schedule:import", normalized_factory_id)

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 xlsx 日排版表")
    if file.content_type and file.content_type not in {XLSX_MIME, "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="文件类型不是 xlsx 日排版表")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    return create_daily_schedule_import(
        db,
        content,
        file.filename,
        normalized_factory_id,
        current_user.id,
    )


@router.get("/imports/{batch_id}/preview", response_model=InjectionScheduleImportPreviewResponse)
def read_import_preview(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "injection_schedule:read")
    return get_import_preview(db, batch_id)


@router.get("/machines/status", response_model=list[InjectionScheduleMachineOut])
def read_machine_status(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "injection_schedule:read")
    return get_machine_status(db, batch_id)
