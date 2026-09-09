from typing import Annotated
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.auth import AuthContext, get_current_user
from app.services.pdf_rename import (
    MAX_PDF_RENAME_BATCH_BYTES,
    MAX_PDF_RENAME_FILES,
    PdfRenameServiceError,
    PdfRenameSource,
    execute_registered_pdf_rename_batch,
    list_pdf_rename_rules,
    preview_registered_pdf_rename_batch,
)
from app.services.pdf_rename.registry import get_pdf_rename_rule
from app.services.pdf_rename.service import parse_manual_overrides

router = APIRouter(prefix="/api/tools")
ZIP_MEDIA_TYPE = "application/zip"
MAX_PDF_RENAME_FILE_BYTES = 20 * 1024 * 1024


def _stable_error(
    code: str,
    message: str,
    *,
    action: str,
    status_code: int = 422,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "action": action,
            "retryable": status_code >= 500,
        },
    )


def _require_document_tools() -> None:
    if not settings.document_tools_enabled:
        raise _stable_error(
            "DOCUMENT_TOOLS_DISABLED",
            "文档工具已被管理员关闭。",
            action="请联系管理员启用 DOCUMENT_TOOLS_ENABLED。",
            status_code=503,
        )


async def _read_pdf(pdf_file: UploadFile) -> tuple[bytes, str]:
    file_name = pdf_file.filename or "PDF文件.pdf"
    if not file_name.lower().endswith(".pdf"):
        raise _stable_error(
            "DOCUMENT_FILE_TYPE_UNSUPPORTED",
            "只支持上传 .pdf 文件。",
            action="请重新选择 PDF 文件。",
            status_code=400,
        )
    pdf_bytes = await pdf_file.read(MAX_PDF_RENAME_FILE_BYTES + 1)
    if not pdf_bytes:
        raise _stable_error(
            "DOCUMENT_FILE_EMPTY",
            "PDF 文件不能为空。",
            action="请选择包含页面的 PDF 文件。",
            status_code=400,
        )
    if len(pdf_bytes) > MAX_PDF_RENAME_FILE_BYTES:
        raise _stable_error(
            "DOCUMENT_FILE_TOO_LARGE",
            "PDF 超过服务器允许的大小。",
            action=(
                f"请将单个文件控制在 "
                f"{MAX_PDF_RENAME_FILE_BYTES // 1024 // 1024} MB 以内。"
            ),
            status_code=413,
        )
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise _stable_error(
            "DOCUMENT_FILE_SIGNATURE_INVALID",
            "文件内容不是有效的 PDF。",
            action="请重新导出 PDF，不要只修改文件扩展名。",
            status_code=400,
        )
    return pdf_bytes, file_name


async def _read_pdf_rename_batch(
    pdf_files: list[UploadFile],
) -> tuple[PdfRenameSource, ...]:
    if not pdf_files:
        raise _stable_error(
            "PDF_RENAME_FILES_REQUIRED",
            "请至少上传一份 PDF。",
            action="请选择需要批量改名的 PDF 文件。",
            status_code=400,
        )
    if len(pdf_files) > MAX_PDF_RENAME_FILES:
        raise _stable_error(
            "PDF_RENAME_TOO_MANY_FILES",
            f"单批最多处理 {MAX_PDF_RENAME_FILES} 份 PDF。",
            action="请拆分成多个批次处理。",
            status_code=413,
        )

    sources: list[PdfRenameSource] = []
    total_bytes = 0
    for pdf_file in pdf_files:
        content, file_name = await _read_pdf(pdf_file)
        total_bytes += len(content)
        if total_bytes > MAX_PDF_RENAME_BATCH_BYTES:
            raise _stable_error(
                "PDF_RENAME_BATCH_TOO_LARGE",
                "单批 PDF 总大小不能超过 200 MB。",
                action="请减少本批文件数量或压缩扫描件后重试。",
                status_code=413,
            )
        sources.append(PdfRenameSource(file_name, content))
    return tuple(sources)


def _pdf_rename_error(exc: PdfRenameServiceError) -> HTTPException:
    return _stable_error(
        exc.code,
        exc.message,
        action=exc.action,
        status_code=exc.status_code,
    )


@router.get("/pdf-rename/rules")
def pdf_rename_rules(
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    factory_id: Annotated[str, Query()],
):
    _require_document_tools()
    try:
        rules = list_pdf_rename_rules(factory_id)
    except PdfRenameServiceError as exc:
        raise _pdf_rename_error(exc) from exc
    return {
        "rules": rules,
        "limits": {
            "max_files": MAX_PDF_RENAME_FILES,
            "max_batch_bytes": MAX_PDF_RENAME_BATCH_BYTES,
            "max_file_bytes": MAX_PDF_RENAME_FILE_BYTES,
        },
    }


@router.post("/pdf-rename/preview")
async def pdf_rename_preview(
    pdf_files: Annotated[list[UploadFile], File()],
    rule_id: Annotated[str, Form()],
    factory_id: Annotated[str, Form()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    manual_overrides: Annotated[str, Form()] = "[]",
):
    _require_document_tools()
    try:
        get_pdf_rename_rule(rule_id, factory_id)
        sources = await _read_pdf_rename_batch(pdf_files)
        result = await run_in_threadpool(
            preview_registered_pdf_rename_batch,
            rule_id,
            sources,
            factory_id=factory_id,
            manual_overrides=parse_manual_overrides(manual_overrides),
        )
    except PdfRenameServiceError as exc:
        raise _pdf_rename_error(exc) from exc
    return result.as_dict()


@router.post("/pdf-rename/execute")
async def pdf_rename_execute(
    pdf_files: Annotated[list[UploadFile], File()],
    rule_id: Annotated[str, Form()],
    factory_id: Annotated[str, Form()],
    preview_token: Annotated[str, Form()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    ocr_review_confirmed: Annotated[bool, Form()] = False,
    manual_overrides: Annotated[str, Form()] = "[]",
):
    _require_document_tools()
    try:
        get_pdf_rename_rule(rule_id, factory_id)
        sources = await _read_pdf_rename_batch(pdf_files)
        result = await run_in_threadpool(
            execute_registered_pdf_rename_batch,
            rule_id,
            sources,
            factory_id=factory_id,
            expected_preview_token=preview_token,
            ocr_review_confirmed=ocr_review_confirmed,
            manual_overrides=parse_manual_overrides(manual_overrides),
        )
    except PdfRenameServiceError as exc:
        raise _pdf_rename_error(exc) from exc
    return Response(
        content=result.content,
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Rename-File-Count": str(result.file_count),
            "X-PDF-Rename-Rule": result.preview.rule.rule_id,
            "X-PDF-Rename-Rule-Version": result.preview.rule.version,
            "Cache-Control": "no-store",
        },
    )
