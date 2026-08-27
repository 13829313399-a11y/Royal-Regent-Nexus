import json
from pathlib import Path
from typing import Annotated
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.auth import AuthContext, get_current_user
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficePdfRenderError,
    render_docx_to_pdf,
)
from app.services.document_tools.capabilities import (
    document_tool_capabilities,
    document_tool_diagnostics,
)
from app.services.document_tools.contracts import DocumentToolError, ProcessingMode
from app.services.document_translation import (
    DocumentTranslationError,
    DocumentTranslationUnavailableError,
    document_translation_status,
    translate_document,
)
from app.services.pdf_split import PdfSplitError, split_pdf
from app.services.pdf_to_excel import PdfToExcelConversionError, convert_pdf_to_excel
from app.services.pdf_to_word import (
    PdfToWordConversionError,
    convert_pdf_to_word,
    convert_pdf_to_word_layout,
)
from app.services.pdf_translation import (
    PdfTranslationConversionError,
    convert_pdf_translation,
)

router = APIRouter(prefix="/api/tools")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
ZIP_MEDIA_TYPE = "application/zip"


def _tool_error(exc: DocumentToolError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "action": exc.action,
            "retryable": exc.retryable,
        },
    )


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


def _processing_headers(
    *,
    mode: ProcessingMode,
    page_count: int,
    warnings: tuple[str, ...] = (),
) -> dict[str, str]:
    headers = {
        "X-Processing-Mode": mode.value,
        "X-Local-Page-Count": str(page_count),
        "X-Low-Confidence-Count": "0",
        "X-Document-Warning-Count": str(len(warnings)),
    }
    if warnings:
        headers["X-Document-Warnings"] = url_quote(
            json.dumps(warnings, ensure_ascii=False)
        )
    return headers


def _require_document_tools() -> None:
    if not settings.document_tools_enabled:
        raise _stable_error(
            "DOCUMENT_TOOLS_DISABLED",
            "文档工具已被管理员关闭。",
            action="请联系管理员启用 DOCUMENT_TOOLS_ENABLED。",
            status_code=503,
        )


async def _read_office_document(document_file: UploadFile) -> tuple[bytes, str]:
    file_name = document_file.filename or "文档.docx"
    extension = Path(file_name).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".docx"}:
        raise _stable_error(
            "DOCUMENT_FILE_TYPE_UNSUPPORTED",
            "只支持上传 .xlsx、.xlsm 或 .docx 文件。",
            action="请重新选择受支持的 Office 文档。",
            status_code=400,
        )
    document_bytes = await document_file.read()
    if not document_bytes:
        raise _stable_error(
            "DOCUMENT_FILE_EMPTY",
            "Office 文档不能为空。",
            action="请选择包含内容的 Office 文档。",
            status_code=400,
        )
    if len(document_bytes) > settings.document_tool_max_file_bytes:
        raise _stable_error(
            "DOCUMENT_FILE_TOO_LARGE",
            "Office 文档超过服务器允许的大小。",
            action=(
                f"请将单个文件控制在 "
                f"{settings.document_tool_max_file_bytes // 1024 // 1024} MB 以内。"
            ),
            status_code=413,
        )
    if not document_bytes.startswith(b"PK"):
        raise _stable_error(
            "DOCUMENT_FILE_SIGNATURE_INVALID",
            "文件内容不是有效的 Office 文档。",
            action="请重新导出文档，不要只修改文件扩展名。",
            status_code=400,
        )
    return document_bytes, file_name


async def _read_word_document(document_file: UploadFile) -> tuple[bytes, str]:
    document_bytes, file_name = await _read_office_document(document_file)
    if Path(file_name).suffix.lower() != ".docx":
        raise _stable_error(
            "DOCUMENT_FILE_TYPE_UNSUPPORTED",
            "Word 转 PDF 只支持上传 .docx 文件。",
            action="请将文档另存为 DOCX 后重试。",
            status_code=400,
        )
    return document_bytes, file_name


async def _read_pdf(pdf_file: UploadFile) -> tuple[bytes, str]:
    file_name = pdf_file.filename or "PDF文件.pdf"
    if not file_name.lower().endswith(".pdf"):
        raise _stable_error(
            "DOCUMENT_FILE_TYPE_UNSUPPORTED",
            "只支持上传 .pdf 文件。",
            action="请重新选择 PDF 文件。",
            status_code=400,
        )
    pdf_bytes = await pdf_file.read()
    if not pdf_bytes:
        raise _stable_error(
            "DOCUMENT_FILE_EMPTY",
            "PDF 文件不能为空。",
            action="请选择包含页面的 PDF 文件。",
            status_code=400,
        )
    if len(pdf_bytes) > settings.document_tool_max_file_bytes:
        raise _stable_error(
            "DOCUMENT_FILE_TOO_LARGE",
            "PDF 超过服务器允许的大小。",
            action=(
                f"请将单个文件控制在 "
                f"{settings.document_tool_max_file_bytes // 1024 // 1024} MB 以内。"
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


@router.get("/capabilities")
def tools_capabilities(
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    return document_tool_capabilities(settings)


@router.get("/diagnostics")
def tools_diagnostics(
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    if settings.app_env.strip().casefold() not in {"development", "dev", "test"} and (
        "admin" not in current_user.role_codes
    ):
        raise _stable_error(
            "DOCUMENT_DIAGNOSTICS_ADMIN_REQUIRED",
            "只有系统管理员可以查看文档工具诊断。",
            action="请联系系统管理员执行诊断。",
            status_code=403,
        )
    return document_tool_diagnostics(settings)


@router.get("/document-translation/status")
def document_translation_service_status(
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    local_status = document_translation_status(settings.document_translation_model_dir)
    return {
        **local_status,
        "modes": {
            "local_private": {
                "available": local_status["available"],
                "label": "Local Private",
            },
        },
    }


@router.post("/document-translation")
async def document_translation(
    document_file: Annotated[UploadFile, File()],
    direction: Annotated[str, Form()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    sheet_names: Annotated[str, Form()] = "",
    mode: Annotated[str, Form()] = "local_private",
):
    _require_document_tools()
    document_bytes, file_name = await _read_office_document(document_file)
    if direction not in {"zh_to_en", "en_to_zh"}:
        raise HTTPException(
            status_code=400, detail="翻译方向无效，只支持中译英或英译中。"
        )
    if mode != "local_private":
        raise HTTPException(status_code=400, detail="翻译模式无效，只支持本地翻译。")

    selected_sheet_names: list[str] | None = None
    if sheet_names.strip():
        try:
            parsed_sheet_names = json.loads(sheet_names)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="工作表选择参数格式不正确。"
            ) from exc
        if not isinstance(parsed_sheet_names, list) or any(
            not isinstance(name, str) for name in parsed_sheet_names
        ):
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。")
        selected_sheet_names = parsed_sheet_names

    try:
        result = await run_in_threadpool(
            translate_document,
            document_bytes,
            file_name,
            direction=direction,
            model_dir=settings.document_translation_model_dir,
            device=settings.document_translation_device,
            selected_sheet_names=selected_sheet_names,
        )
    except DocumentTranslationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DocumentTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-Translation-Unit-Count": str(result.translated_unit_count),
            "X-Translation-Skipped-Count": str(result.skipped_unit_count),
            "X-Translation-Part-Count": str(result.processed_part_count),
            "X-Translation-Mode": "local_private",
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-to-excel")
async def pdf_to_excel(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    processing_mode: Annotated[str, Form()] = "AUTO",
):
    _require_document_tools()
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        mode = ProcessingMode.parse(processing_mode)
        result = await run_in_threadpool(
            convert_pdf_to_excel,
            pdf_bytes,
            file_name,
        )
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except PdfToExcelConversionError as exc:
        raise _stable_error(
            "PDF_TO_EXCEL_FAILED",
            str(exc),
            action="请确认 PDF 未加密且包含可识别的文字或表格。",
        ) from exc
    return Response(
        content=result.content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Table-Count": str(result.table_count),
            "X-PDF-Text-Page-Count": str(result.text_page_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
            **_processing_headers(mode=mode, page_count=result.page_count),
        },
    )


@router.post("/pdf-to-word")
async def pdf_to_word(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    processing_mode: Annotated[str, Form()] = "AUTO",
    output_mode: Annotated[str, Form()] = "EDITABLE",
):
    _require_document_tools()
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        mode = ProcessingMode.parse(processing_mode)
        converter = (
            convert_pdf_to_word_layout
            if output_mode == "LAYOUT_PRESERVING"
            else convert_pdf_to_word
        )
        if output_mode not in {"EDITABLE", "LAYOUT_PRESERVING"}:
            raise PdfToWordConversionError("PDF 转 Word 输出模式无效。")
        result = await run_in_threadpool(converter, pdf_bytes, file_name)
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except PdfToWordConversionError as exc:
        raise _stable_error(
            "PDF_TO_WORD_FAILED",
            str(exc),
            action="请确认 PDF 未加密且包含可识别内容。",
        ) from exc
    return Response(
        content=result.content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Table-Count": str(result.table_count),
            "X-PDF-Image-Count": str(result.image_count),
            "X-PDF-Text-Page-Count": str(result.text_page_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
            **_processing_headers(mode=mode, page_count=result.page_count),
        },
    )


@router.post("/word-to-pdf")
async def word_to_pdf(
    document_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    processing_mode: Annotated[str, Form()] = "AUTO",
):
    _require_document_tools()
    document_bytes, file_name = await _read_word_document(document_file)
    try:
        mode = ProcessingMode.parse(processing_mode)
        result = await run_in_threadpool(
            render_docx_to_pdf,
            document_bytes,
            file_name,
            command=settings.document_office_renderer_command,
            timeout_seconds=settings.document_office_renderer_timeout_seconds,
            network_isolation_command=(
                settings.document_office_renderer_network_isolation_command
                if settings.document_office_renderer_network_isolation_verified
                else None
            ),
        )
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except OfficePdfRenderError as exc:
        status_code = (
            503
            if exc.retryable
            or exc.code
            in {
                "LIBREOFFICE_NOT_INSTALLED",
                "DOCUMENT_OFFICE_RENDERER_UNAVAILABLE",
            }
            else 422
        )
        raise _stable_error(
            exc.code,
            exc.public_message,
            action=(
                "请管理员安装 LibreOffice 并确认命令路径。"
                if exc.code == "LIBREOFFICE_NOT_INSTALLED"
                else "请重试；若持续失败，请将错误码提供给管理员。"
            ),
            status_code=status_code,
        ) from exc
    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-Word-Page-Count": str(result.page_count),
            "X-Word-Blank-Page-Count": str(result.blank_page_count),
            "Cache-Control": "no-store",
            **_processing_headers(
                mode=mode,
                page_count=result.page_count,
                warnings=result.warnings,
            ),
        },
    )


@router.post("/pdf-translation")
async def pdf_translation(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    direction: Annotated[str, Form()] = "AUTO",
    layout: Annotated[str, Form()] = "TRANSLATED_ONLY",
    protected_tokens: Annotated[str, Form()] = "[]",
    include_editable_docx: Annotated[bool, Form()] = False,
    processing_mode: Annotated[str, Form()] = "AUTO",
):
    _require_document_tools()
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        mode = ProcessingMode.parse(processing_mode)
        parsed_tokens = json.loads(protected_tokens)
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except json.JSONDecodeError as exc:
        raise _stable_error(
            "DOCUMENT_TRANSLATION_OPTIONS_INVALID",
            "保护词参数格式不正确。",
            action="请检查保护词列表后重试。",
            status_code=400,
        ) from exc
    if (
        not isinstance(parsed_tokens, list)
        or len(parsed_tokens) > 100
        or any(
            not isinstance(token, str) or len(token) > 200
            for token in parsed_tokens
        )
    ):
        raise _stable_error(
            "DOCUMENT_TRANSLATION_OPTIONS_INVALID",
            "保护词参数格式不正确。",
            action="保护词最多 100 个，每个不超过 200 个字符。",
            status_code=400,
        )
    try:
        result = await run_in_threadpool(
            convert_pdf_translation,
            pdf_bytes,
            file_name,
            settings=settings,
            requested_direction=direction,
            layout=layout,
            protected_tokens=tuple(
                dict.fromkeys(
                    token.strip() for token in parsed_tokens if token.strip()
                )
            ),
            include_editable_docx=include_editable_docx,
        )
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except PdfTranslationConversionError as exc:
        raise _stable_error(
            "PDF_TRANSLATION_FAILED",
            str(exc),
            action="请确认文档包含可识别文字，并检查翻译方向和版式设置。",
        ) from exc
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Page-Count": str(result.page_count),
            "X-Translation-Unit-Count": str(result.translated_unit_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
            **_processing_headers(mode=mode, page_count=result.page_count),
        },
    )


@router.post("/pdf-split")
async def pdf_split(
    pdf_file: Annotated[UploadFile, File()],
    _current_user: Annotated[AuthContext, Depends(get_current_user)],
    split_mode: Annotated[str, Form()] = "each_page",
    page_ranges: Annotated[str, Form()] = "",
    processing_mode: Annotated[str, Form()] = "AUTO",
):
    _require_document_tools()
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        mode = ProcessingMode.parse(processing_mode)
        result = await run_in_threadpool(
            split_pdf,
            pdf_bytes,
            file_name,
            mode=split_mode,
            page_ranges=page_ranges,
        )
    except DocumentToolError as exc:
        raise _tool_error(exc) from exc
    except PdfSplitError as exc:
        raise _stable_error(
            "PDF_SPLIT_FAILED",
            str(exc),
            action="请检查页段格式，例如 1-3,5,8-10。",
        ) from exc
    return Response(
        content=result.content,
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}"
            ),
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Split-File-Count": str(result.file_count),
            "Cache-Control": "no-store",
            **_processing_headers(mode=mode, page_count=result.page_count),
        },
    )
