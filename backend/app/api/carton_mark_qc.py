import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.schemas.carton_mark_qc import QcAction, QcRecordOut
from app.services.auth import AuthContext, get_current_user
from app.services import carton_mark_qc as qc
from app.services.carton_mark_assets import IMAGE_CONTENT_TYPES, validate_asset_image
from app.services.carton_mark import CartonMarkDocumentError
from app.services.transaction_lock import lock_transaction

router = APIRouter(prefix="/api/carton-mark/qc-records")


@router.get("/{identifier}/sources/{asset_id}")
def qc_review_original(identifier: str, asset_id: str, factory_id: str,
                       db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_mark_manual_review import original_source
    factory = qc.scope(user, factory_id)
    record = qc.record(db, factory, identifier)
    snapshot = json.loads(record.template_snapshot_json)
    document = original_source(db, factory, snapshot.get("source_assets", []), asset_id)
    return Response(document.content, media_type=document.content_type, headers={
        "Content-Disposition": "inline; filename*=UTF-8''" + quote(document.file_name, safe=""),
        "X-Content-SHA256": document.sha256, "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


@router.get("")
def list_records(factory_id: str, limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0),
                 contract_number: str = Query("", max_length=128), item: str = Query("", max_length=128),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = qc.scope(user, factory_id)
    return qc.list_records(db, factory, limit, offset, contract_number, item)


async def read_photos(front, side, mode):
    uploads = [("front", file) for file in front] + [("side", file) for file in side]
    if not uploads or len(uploads) > 20 or (mode == "single" and (len(front) > 1 or len(side) > 1)):
        raise HTTPException(422, "请上传 1–20 张图片；单次正侧唛核对每面最多 1 张")
    result, total = [], 0
    for face, file in uploads:
        name = Path((file.filename or "").replace("\\", "/")).name
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_CONTENT_TYPES or len(name) > 255:
            raise HTTPException(422, "照片仅支持 JPG、PNG、WebP，文件名不能超过 255 字")
        content = await file.read(20 * 1024 * 1024 + 1)
        total += len(content)
        if total > 100 * 1024 * 1024:
            raise HTTPException(413, "每次上传总大小不能超过 100 MB")
        try:
            await run_in_threadpool(validate_asset_image, name, content)
        except CartonMarkDocumentError as error:
            raise HTTPException(422, str(error)) from error
        result.append(qc.PhotoInput(face, name, content, IMAGE_CONTENT_TYPES[suffix]))
    return result


@router.post("", response_model=list[QcRecordOut])
async def create_records(request: Request, factory_id: str = Form(...), template_id: str = Form(..., max_length=96),
                         request_id: str = Form(..., min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_-]+$"),
                         mode: Literal["single", "batch"] = Form("batch"), note: str = Form("", max_length=1000),
                         corrects_record_id: str | None = Form(None, max_length=96),
                         front_photos: list[UploadFile] = File(default=[]), side_photos: list[UploadFile] = File(default=[]),
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = qc.scope(user, factory_id, "carton_mark:photo_upload")
    db.rollback()
    inputs = await read_photos(front_photos, side_photos, mode)
    user = get_current_user(request, db)
    qc.scope(user, factory, "carton_mark:photo_upload")
    request_hash = qc.submission_hash(template_id, mode, note, corrects_record_id, inputs)
    previous = qc.replay(db, user, factory, request_id, request_hash)
    if previous is not None:
        return previous
    snapshot, pdf, _ = qc.template_source(db, factory, template_id)
    qc.validate_correction(db, factory, corrects_record_id, snapshot, note)
    db.rollback()
    results = await run_in_threadpool(qc.compute, pdf, snapshot, inputs, mode)
    user = get_current_user(request, db)
    qc.scope(user, factory, "carton_mark:photo_upload")
    lock_transaction(db, "carton-mark-qc", factory)
    # Refresh identity under the transaction lock as permission bindings may have changed during OCR.
    user = get_current_user(request, db)
    qc.scope(user, factory, "carton_mark:photo_upload")
    previous = qc.replay(db, user, factory, request_id, request_hash)
    if previous is not None:
        return previous
    current, _, _ = qc.template_source(db, factory, template_id)
    if current != snapshot:
        raise HTTPException(409, "核对期间资料版本或放行状态已变化，请重新选择后提交")
    qc.validate_correction(db, factory, corrects_record_id, snapshot, note)
    try:
        return qc.persist_submission(db, user, factory, template_id, request_id, request_hash, mode, note,
            corrects_record_id, inputs, snapshot, results)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "其他操作正在保存，请使用相同提交编号重试") from error


@router.get("/{record_id}", response_model=QcRecordOut)
def get_record(record_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return qc.output(db, qc.record(db, qc.scope(user, factory_id), record_id))


def file_response(content, name, content_type):
    return Response(content, media_type=content_type, headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{record_id}/photos/{photo_id}")
def download_photo(record_id: str, photo_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    value = qc.record(db, qc.scope(user, factory_id), record_id)
    photo = next((p for p in qc.photos(db, value.id) if p.id == photo_id), None)
    if photo is None:
        raise HTTPException(404, "未找到留档照片")
    if qc.digest(photo.content) != photo.sha256:
        raise HTTPException(409, "照片原件完整性校验失败")
    return file_response(photo.content, photo.file_name, photo.content_type)


@router.get("/{record_id}/template")
def download_template(record_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    content, name = qc.original_pdf(db, qc.record(db, qc.scope(user, factory_id), record_id))
    return file_response(content, name, "application/pdf")


@router.post("/{record_id}/actions", response_model=QcRecordOut)
async def action(request: Request, record_id: str, factory_id: str, payload: QcAction,
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = qc.scope(user, factory_id, "carton_mark:review")
    value = qc.record(db, factory, record_id)
    request_hash, previous = qc.action_replay(db, user, value, payload)
    if previous is not None:
        return previous
    result, error = None, ""
    if payload.action == "重新自动核对":
        if qc.manual_images(json.loads(value.template_snapshot_json)):
            raise HTTPException(422, "图片资料暂仅支持人工对照，请查看原稿后复核")
        pdf, _ = qc.original_pdf(db, value)
        inputs = [qc.PhotoInput(p.side, p.file_name, bytes(p.content), p.content_type) for p in qc.photos(db, value.id)]
        snapshot = json.loads(value.template_snapshot_json)
        db.rollback()
        [(result, error)] = await run_in_threadpool(qc.compute, pdf, snapshot, inputs, "single")
    else:
        db.rollback()
    lock_transaction(db, "carton-mark-qc", factory)
    user = get_current_user(request, db)
    qc.scope(user, factory, "carton_mark:review")
    value = qc.record(db, factory, record_id)
    request_hash, previous = qc.action_replay(db, user, value, payload)
    if previous is not None:
        return previous
    kind = "AUTO_CHECK" if payload.action == "重新自动核对" else "VOID" if payload.action == "作废" else "REVIEW"
    status = "待复核" if kind == "AUTO_CHECK" else "已作废" if kind == "VOID" else payload.action
    qc.append_event(db, user, value, payload.expected_revision + 1, kind, status, payload.request_id,
        request_hash, result, error, payload.note.strip())
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "记录已被其他人复核，请刷新") from exc
    return qc.output(db, value)
