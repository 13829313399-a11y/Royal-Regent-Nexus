from io import BytesIO
from io import BytesIO
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.internal_quote import (
    InternalQuoteCreateRequest,
    InternalQuoteDetailOut,
    InternalQuoteAttachmentOut,
    InternalQuoteExportFileOut,
    InternalQuoteImportConfirmRequest,
    InternalQuoteImportPreviewOut,
    InternalQuoteReviewRequest,
    InternalQuoteSectionUpdateRequest,
    InternalQuoteSummaryOut,
    InternalQuoteWorkshopOut,
)
from app.services.auth import AuthContext, ensure_permission_in_scope, get_current_user
from app.services.internal_quote import (
    add_quote_audit,
    create_quote,
    get_quote_detail,
    get_quote_or_404,
    list_quotes,
    list_workshops,
    mark_quote_exported,
    review_section,
    update_section,
)
from app.services.internal_quote_artifacts import (
    create_attachment,
    create_export_file,
    create_import_preview,
    confirm_import_batch,
    get_attachment,
    get_export_file,
    list_attachments,
    list_export_files,
    list_import_batches,
)
from app.services.internal_quote_excel import build_internal_quote_workbook


router = APIRouter(prefix="/api/internal-quotes")
INTERNAL_QUOTE_DEPARTMENT_SCOPE = "sales-business"


def ensure_quote_permission(
    db: Session,
    current_user: AuthContext,
    permission: str,
    factory_id: str,
) -> None:
    ensure_permission_in_scope(
        db,
        current_user,
        permission,
        factory_id,
        INTERNAL_QUOTE_DEPARTMENT_SCOPE,
    )


@router.get("/workshops", response_model=list[InternalQuoteWorkshopOut])
def get_internal_quote_workshops(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_quote_permission(db, current_user, "internal_pricing:read", factory_id)
    return list_workshops(factory_id)


@router.post("/{quote_id}/imports/{import_type}/preview", response_model=InternalQuoteImportPreviewOut)
async def preview_internal_quote_import(
    quote_id: str,
    import_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:edit", quote.factory_id)
    content = await file.read()
    return create_import_preview(
        db,
        quote,
        import_type,
        file.filename or "",
        content,
        current_user,
    )


@router.get("/{quote_id}/imports", response_model=list[InternalQuoteImportPreviewOut])
def get_internal_quote_imports(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:read", quote.factory_id)
    return list_import_batches(db, quote.id)


@router.post("/{quote_id}/imports/{batch_id}/confirm", response_model=InternalQuoteDetailOut)
def confirm_internal_quote_import(
    quote_id: str,
    batch_id: str,
    payload: InternalQuoteImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:edit", quote.factory_id)
    return confirm_import_batch(db, quote, batch_id, payload, current_user)


@router.post("/{quote_id}/attachments", response_model=InternalQuoteAttachmentOut)
async def upload_internal_quote_attachment(
    quote_id: str,
    department: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:edit", quote.factory_id)
    return create_attachment(
        db,
        quote,
        department.strip(),
        file.filename or "",
        file.content_type or "application/octet-stream",
        await file.read(),
        current_user,
    )


@router.get("/{quote_id}/attachments", response_model=list[InternalQuoteAttachmentOut])
def get_internal_quote_attachments(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:read", quote.factory_id)
    return list_attachments(db, quote.id)


@router.get("/{quote_id}/attachments/{attachment_id}/download")
def download_internal_quote_attachment(
    quote_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:read", quote.factory_id)
    row = get_attachment(db, quote.id, attachment_id)
    filename = url_quote(row.file_name)
    return StreamingResponse(
        BytesIO(row.content),
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-SHA256": row.sha256,
        },
    )


@router.get("/{quote_id}/exports", response_model=list[InternalQuoteExportFileOut])
def get_internal_quote_exports(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:export", quote.factory_id)
    return list_export_files(db, quote.id)


@router.get("/{quote_id}/exports/{export_id}/download")
def download_retained_internal_quote_export(
    quote_id: str,
    export_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:export", quote.factory_id)
    row = get_export_file(db, quote.id, export_id)
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "download_export",
        department="sales",
        detail=f"{row.file_name} · {row.sha256[:12]}",
    )
    db.commit()
    filename = url_quote(row.file_name)
    return StreamingResponse(
        BytesIO(row.content),
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-SHA256": row.sha256,
            "X-Export-Status": row.status,
        },
    )


@router.get("", response_model=list[InternalQuoteSummaryOut])
def get_internal_quotes(
    factory_id: str,
    workshop_code: str | None = None,
    status_filter: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_quote_permission(db, current_user, "internal_pricing:read", factory_id)
    return list_quotes(
        db,
        factory_id,
        workshop_code=workshop_code,
        status=status_filter,
        keyword=keyword,
    )


@router.post("", response_model=InternalQuoteDetailOut, status_code=status.HTTP_201_CREATED)
def post_internal_quote(
    payload: InternalQuoteCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_quote_permission(db, current_user, "internal_pricing:create", payload.factory_id)
    return create_quote(db, payload, current_user)


@router.get("/{quote_id}", response_model=InternalQuoteDetailOut)
def get_internal_quote(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:read", quote.factory_id)
    return get_quote_detail(db, quote_id)


@router.put("/{quote_id}/sections/{department}", response_model=InternalQuoteDetailOut)
def put_internal_quote_section(
    quote_id: str,
    department: str,
    payload: InternalQuoteSectionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:edit", quote.factory_id)
    return update_section(db, quote, department, payload, current_user)


@router.post("/{quote_id}/sections/{department}/review", response_model=InternalQuoteDetailOut)
def post_internal_quote_review(
    quote_id: str,
    department: str,
    payload: InternalQuoteReviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:review", quote.factory_id)
    return review_section(db, quote, department, payload, current_user)


@router.get("/{quote_id}/export")
def export_internal_quote(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    quote = get_quote_or_404(db, quote_id)
    ensure_quote_permission(db, current_user, "internal_pricing:export", quote.factory_id)
    detail = get_quote_detail(db, quote.id)
    workbook = build_internal_quote_workbook(detail)
    raw_filename = f"{quote.quote_no}_{quote.workshop_name}_内部报价明细.xlsx"
    export_row = create_export_file(db, quote, detail, raw_filename, workbook, current_user)
    mark_quote_exported(db, quote, current_user)
    filename = url_quote(raw_filename)
    return StreamingResponse(
        BytesIO(workbook),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Content-SHA256": export_row.sha256,
            "X-Export-Id": export_row.id,
        },
    )
