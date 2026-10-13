from urllib.parse import quote as url_quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.schemas.carton_mark import (
    CartonMarkAutoCheckResponse,
    CartonMarkBatchCheckResponse,
    CartonMarkCustomerCreateRequest,
    CartonMarkCustomerOptionOut,
    CartonMarkCustomerOut,
    CartonMarkCustomerUpdateRequest,
    CartonMarkDocumentCheckResponse,
    CartonMarkTemplateManualReleaseRequest,
    CartonMarkTemplateOut,
    CartonMarkManualReviewRequest,
    CartonMarkAssetOut,
    CartonMarkAssetBindingRequest,
    CartonMarkAssetOrderOut,
    CartonMarkPhotoGroupRequest,
    CartonMarkPhotoGroupMembers,
    CartonMarkAssetUploadResult,
    CartonMarkCustomerRecognitionRequest,
    CartonMarkCustomerRecognitionOut,
    CartonMarkCustomerInitializationCandidate,
    CartonMarkCustomerInitializationRequest,
    CartonMarkCustomerInitializationOut,
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
    get_carton_mark_document_recheck_source,
    get_carton_mark_template,
    list_carton_mark_customer_options,
    list_carton_mark_templates,
    manually_release_carton_mark_template,
    update_carton_mark_document_check_result,
)
from app.services.carton_mark_customers import (
    create_carton_mark_customer,
    delete_carton_mark_customer,
    list_carton_mark_customers,
    update_carton_mark_customer,
)
from app.services import carton_mark_assets as assets
from app.services import carton_mark_customer_matching as customer_matching
from app.services import carton_mark_manual_review as manual_review

router = APIRouter()


def _asset_scope(db, user, factory, write=False):
    return ensure_carton_mark_scope(db, user,
        "carton_mark:template_upload" if write else "carton_mark:read", factory,
        CARTON_MARK_WRITE_DEPARTMENTS if write else CARTON_MARK_READ_DEPARTMENTS)


@router.get("/api/carton-mark/assets", response_model=list[CartonMarkAssetOut])
def get_assets(factory_id: str, order_id: str | None = None,
               db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id)
    return assets.list_assets(db, factory, order_id)


@router.post("/api/carton-mark/assets/batch", response_model=list[CartonMarkAssetUploadResult])
async def upload_assets(factory_id: str = Form(...), files: list[UploadFile] = File(...),
                        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    if not 1 <= len(files) <= 50:
        raise HTTPException(422, "每批请选择 1–50 个文件")
    if sum(file.size or 0 for file in files) > 100 * 1024 * 1024:
        raise HTTPException(413, "每批文件合计不能超过 100 MB")
    known = sorted({o.contract_no for o in assets.available_orders(db, factory) if o.contract_no})
    results = []
    total = 0
    for file in files:
        try:
            content = await _read_document_upload(file, "箱唛文件")
            total += len(content)
            if total > 100 * 1024 * 1024:
                raise HTTPException(413, "每批文件合计不能超过 100 MB")
            recognition = await run_in_threadpool(assets.recognize_asset, file.filename or "", content, known)
            asset, result = assets.save_asset(db, user, factory, content, recognition)
            results.append(CartonMarkAssetUploadResult(file_name=file.filename or "", status=result, asset=asset))
        except (HTTPException, CartonMarkDocumentError, CartonMarkDocumentConfigurationError) as exc:
            db.rollback()
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            results.append(CartonMarkAssetUploadResult(file_name=file.filename or "", status="failed", message=message))
    return results


@router.get("/api/carton-mark/assets/binding-orders", response_model=list[CartonMarkAssetOrderOut])
def asset_binding_orders(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id)
    _asset_scope(db, user, factory_id, True)
    return assets.binding_orders(db, factory)


@router.post("/api/carton-mark/assets/photo-groups", response_model=list[CartonMarkAssetOut])
def create_photo_group(payload: CartonMarkPhotoGroupRequest, factory_id: str,
                       db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    _asset_scope(db, user, factory_id)
    return assets.change_photo_group(db, user, factory, payload)


@router.put("/api/carton-mark/assets/photo-groups/{group_id}/binding", response_model=list[CartonMarkAssetOut])
def bind_photo_group(group_id: str, payload: CartonMarkPhotoGroupRequest, factory_id: str,
                     db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    _asset_scope(db, user, factory_id)
    return assets.change_photo_group(db, user, factory, payload, group_id=group_id)


@router.post("/api/carton-mark/assets/photo-groups/{group_id}/ungroup", response_model=list[CartonMarkAssetOut])
def ungroup_photos(group_id: str, payload: CartonMarkPhotoGroupMembers, factory_id: str,
                   db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    _asset_scope(db, user, factory_id)
    return assets.change_photo_group(db, user, factory, payload, group_id=group_id, ungroup=True)


@router.put("/api/carton-mark/assets/{asset_id}/binding", response_model=CartonMarkAssetOut)
def bind_asset(asset_id: str, payload: CartonMarkAssetBindingRequest, factory_id: str,
               db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    return assets.change_binding(db, user, factory, asset_id, payload)


@router.get("/api/carton-mark/assets/{asset_id}/document")
def download_asset(asset_id: str, factory_id: str, preview: bool = False,
                   db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id)
    asset = assets.active_asset(db, factory, asset_id)
    disposition = "inline" if preview and asset.kind in {"pdf", "image"} else "attachment"
    return Response(content=asset.content, media_type=asset.content_type, headers={
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{url_quote(asset.file_name, safe='')}",
        "X-Content-SHA256": asset.sha256, "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


@router.delete("/api/carton-mark/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, factory_id: str, revision: int = Query(..., ge=1),
                 db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _asset_scope(db, user, factory_id, True)
    assets.archive_asset(db, user, factory, asset_id, revision)


async def _template_source(db, user, factory, upload, asset_id, kind):
    if upload is not None and asset_id:
        raise HTTPException(422, "原文件与仓库资料只能选择一种来源")
    if asset_id:
        _asset_scope(db, user, factory)
        asset = assets.active_asset(db, factory, asset_id)
        if asset.kind != kind:
            raise HTTPException(422, "仓库资料的文件类型不符")
        return asset.file_name, asset.content
    if upload is None:
        raise HTTPException(422, "请选择 Excel 与 PDF 原文件或仓库资料")
    return upload.filename or "", await _read_document_upload(upload, "箱唛文件")


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
    excel_contract: UploadFile | None = File(None),
    print_pdf: UploadFile | None = File(None),
    excel_asset_id: str | None = Form(None),
    pdf_asset_id: str | None = Form(None),
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
    excel_name, excel_bytes = await _template_source(db, current_user, factory_id, excel_contract, excel_asset_id, "excel")
    pdf_name, pdf_bytes = await _template_source(db, current_user, factory_id, print_pdf, pdf_asset_id, "pdf")
    try:
        check_result = await run_in_threadpool(
            build_carton_mark_document_check,
            excel_file_name=excel_name,
            excel_bytes=excel_bytes,
            pdf_file_name=pdf_name,
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
        excel_file_name=excel_name,
        excel_bytes=excel_bytes,
        pdf_file_name=pdf_name,
        pdf_bytes=pdf_bytes,
        check_result=check_result,
    )


@router.get(
    "/api/carton-mark/customer-options",
    response_model=list[CartonMarkCustomerOptionOut],
)
def get_carton_mark_customer_options(
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
    return list_carton_mark_customer_options(db, factory_id)


@router.get(
    "/api/carton-mark/customers",
    response_model=list[CartonMarkCustomerOut],
)
def get_carton_mark_customers(
    factory_id: str = Query(min_length=1, max_length=64),
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
    return list_carton_mark_customers(db, factory_id=factory_id)


@router.post("/api/carton-mark/customer-recognition", response_model=CartonMarkCustomerRecognitionOut)
def recognize_carton_mark_customer(
    payload: CartonMarkCustomerRecognitionRequest,
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return customer_matching.recognize_customer(db, current_user, factory_id, payload)


@router.get("/api/carton-mark/customers/initialization-candidates", response_model=list[CartonMarkCustomerInitializationCandidate])
def get_carton_mark_customer_initialization_candidates(
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return customer_matching.initialization_candidates(db, current_user, factory_id)


@router.post("/api/carton-mark/customers/initialize", response_model=CartonMarkCustomerInitializationOut)
def initialize_carton_mark_customers(
    payload: CartonMarkCustomerInitializationRequest,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return customer_matching.initialize_customers(db, current_user, factory_id, payload, request)


@router.post(
    "/api/carton-mark/customers",
    response_model=CartonMarkCustomerOut,
    status_code=status.HTTP_201_CREATED,
)
def post_carton_mark_customer(
    payload: CartonMarkCustomerCreateRequest,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_carton_mark_customer(
        db,
        current_user,
        factory_id=factory_id,
        payload=payload,
        request=request,
    )


@router.put(
    "/api/carton-mark/customers/{customer_id}",
    response_model=CartonMarkCustomerOut,
)
def put_carton_mark_customer(
    customer_id: str,
    payload: CartonMarkCustomerUpdateRequest,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_carton_mark_customer(
        db,
        current_user,
        factory_id=factory_id,
        customer_id=customer_id,
        payload=payload,
        request=request,
    )


@router.delete(
    "/api/carton-mark/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_carton_mark_customer(
    customer_id: str,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    revision: int = Query(ge=1),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    delete_carton_mark_customer(
        db,
        current_user,
        factory_id=factory_id,
        customer_id=customer_id,
        revision=revision,
        request=request,
    )
    return None


@router.post("/api/carton-mark/manual-reviews", response_model=CartonMarkTemplateOut, status_code=201)
async def submit_manual_review(payload: CartonMarkManualReviewRequest, request: Request,
                               db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return await manual_review.create_review(request, db, user, payload)


@router.get("/api/carton-mark/templates/{template_id}/sources/{asset_id}")
def review_original(template_id: str, asset_id: str, factory_id: str,
                    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    manual_review.scope(user, factory_id, "carton_mark:read")
    record = get_carton_mark_template(db, factory_id, template_id)
    document = manual_review.original_source(db, factory_id, record.check_result.source_assets, asset_id)
    return Response(document.content, media_type=document.content_type, headers={
        "Content-Disposition": "inline; filename*=UTF-8''" + url_quote(document.file_name, safe=""),
        "X-Content-SHA256": document.sha256, "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"})


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


@router.post(
    "/api/carton-mark/templates/{template_id}/recheck",
    response_model=CartonMarkTemplateOut,
)
async def recheck_persisted_carton_mark_template(
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
    source = get_carton_mark_document_recheck_source(db, factory_id, template_id)
    try:
        check_result = await run_in_threadpool(
            build_carton_mark_document_check,
            excel_file_name=source.excel_file_name,
            excel_bytes=source.excel_bytes,
            pdf_file_name=source.pdf_file_name,
            pdf_bytes=source.pdf_bytes,
        )
    except CartonMarkDocumentConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CartonMarkDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return update_carton_mark_document_check_result(
        db,
        current_user,
        factory_id=factory_id,
        template_id=template_id,
        check_result=check_result,
    )


@router.post(
    "/api/carton-mark/templates/{template_id}/manual-release",
    response_model=CartonMarkTemplateOut,
)
def manually_release_persisted_carton_mark_template(
    template_id: str,
    payload: CartonMarkTemplateManualReleaseRequest,
    request: Request,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, factory_id)
    current_user = get_current_user(request, db)
    factory_id = ensure_carton_mark_scope(
        db,
        current_user,
        "carton_mark:template_release",
        factory_id,
        CARTON_MARK_WRITE_DEPARTMENTS,
    )
    return manually_release_carton_mark_template(
        db,
        current_user,
        factory_id=factory_id,
        template_id=template_id,
        reason=payload.reason,
        confirmed_checks=payload.confirmed_checks,
    )


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
