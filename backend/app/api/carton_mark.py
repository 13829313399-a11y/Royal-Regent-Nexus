from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.schemas.carton_mark import (
    CartonMarkAutoCheckResponse,
    CartonMarkBatchCheckResponse,
    CartonMarkDocumentCheckResponse,
    CartonMarkTemplateOut,
)
from app.services.auth import AuthContext, ensure_permission, get_current_user
from app.services.carton_mark import (
    CartonMarkDocumentConfigurationError,
    CartonMarkDocumentError,
    MAX_DOCUMENT_FILE_BYTES,
    build_carton_mark_auto_check,
    build_carton_mark_batch_auto_check,
    build_carton_mark_document_check,
)
from app.services.carton_mark_library import (
    CARTON_MARK_READ_DEPARTMENTS,
    CARTON_MARK_WRITE_DEPARTMENTS,
    archive_carton_mark_template,
    create_carton_mark_template,
    ensure_carton_mark_scope,
    get_authorized_carton_mark_document,
    get_carton_mark_template,
    list_carton_mark_templates,
)

router = APIRouter()


async def _read_document_upload(upload: UploadFile, label: str) -> bytes:
    if upload.size is not None and upload.size > MAX_DOCUMENT_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{label}不能超过 20 MB")
    content = await upload.read(MAX_DOCUMENT_FILE_BYTES + 1)
    if len(content) > MAX_DOCUMENT_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{label}不能超过 20 MB")
    if not content:
        raise HTTPException(status_code=400, detail=f"{label}不能为空")
    return content


@router.post(
    "/api/carton-mark/document-content-check",
    response_model=CartonMarkDocumentCheckResponse,
)
async def check_carton_mark_document_content(
    excel_contract: UploadFile = File(...),
    print_pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "carton_mark:template_upload")
    excel_bytes = await _read_document_upload(excel_contract, "客户 Excel")
    pdf_bytes = await _read_document_upload(print_pdf, "打印 PDF")
    try:
        return await run_in_threadpool(
            build_carton_mark_document_check,
            excel_file_name=excel_contract.filename or "",
            excel_bytes=excel_bytes,
            pdf_file_name=print_pdf.filename or "",
            pdf_bytes=pdf_bytes,
        )
    except CartonMarkDocumentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CartonMarkDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/carton-mark/templates",
    response_model=CartonMarkTemplateOut,
    status_code=201,
)
async def create_persisted_carton_mark_template(
    factory_id: str = Form(...),
    customer_name: str = Form(...),
    po: str = Form(""),
    item: str = Form(...),
    contract_number: str = Form(...),
    excel_contract: UploadFile = File(...),
    print_pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = ensure_carton_mark_scope(
        db,
        current_user,
        "carton_mark:template_upload",
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    excel_bytes = await _read_document_upload(excel_contract, "客户 Excel")
    pdf_bytes = await _read_document_upload(print_pdf, "打印 PDF")
    try:
        check_result = await run_in_threadpool(
            build_carton_mark_document_check,
            excel_file_name=excel_contract.filename or "",
            excel_bytes=excel_bytes,
            pdf_file_name=print_pdf.filename or "",
            pdf_bytes=pdf_bytes,
        )
    except CartonMarkDocumentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CartonMarkDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return create_carton_mark_template(
        db,
        current_user,
        factory_id=factory_id,
        customer_name=customer_name,
        po=po,
        item=item,
        contract_number=contract_number,
        excel_file_name=excel_contract.filename or "",
        excel_bytes=excel_bytes,
        pdf_file_name=print_pdf.filename or "",
        pdf_bytes=pdf_bytes,
        check_result=check_result,
    )


@router.get("/api/carton-mark/templates", response_model=list[CartonMarkTemplateOut])
def get_persisted_carton_mark_templates(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = ensure_carton_mark_scope(
        db,
        current_user,
        "carton_mark:read",
        factory_id,
        CARTON_MARK_READ_DEPARTMENTS,
    )
    return list_carton_mark_templates(db, factory_id)


@router.get(
    "/api/carton-mark/templates/{template_id}",
    response_model=CartonMarkTemplateOut,
)
def get_persisted_carton_mark_template(
    template_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = ensure_carton_mark_scope(
        db,
        current_user,
        "carton_mark:read",
        factory_id,
        CARTON_MARK_READ_DEPARTMENTS,
    )
    return get_carton_mark_template(db, factory_id, template_id)


@router.get("/api/carton-mark/templates/{template_id}/documents/{kind}")
def download_persisted_carton_mark_document(
    template_id: str,
    kind: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    document = get_authorized_carton_mark_document(
        db,
        current_user,
        factory_id=factory_id,
        template_id=template_id,
        kind=kind,
    )
    encoded_name = url_quote(document.file_name)
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="carton-mark-document"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
            "Content-Length": str(document.size_bytes),
            "ETag": f'"{document.sha256}"',
            "X-Content-SHA256": document.sha256,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/api/carton-mark/templates/{template_id}", status_code=204)
def delete_persisted_carton_mark_template(
    template_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = ensure_carton_mark_scope(
        db,
        current_user,
        "carton_mark:template_upload",
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    archive_carton_mark_template(
        db,
        current_user,
        factory_id=factory_id,
        template_id=template_id,
    )
    return Response(status_code=204)


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
    ensure_permission(db, current_user, "carton_mark:photo_upload")

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
    ensure_permission(db, current_user, "carton_mark:photo_upload")

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
