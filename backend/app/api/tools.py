import json
from pathlib import Path
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.auth import AuthContext, get_current_user
from app.services.document_translation import (
    DocumentTranslationError,
    DocumentTranslationUnavailableError,
    document_translation_status,
    translate_document,
)
from app.services.pdf_to_excel import PdfToExcelConversionError, convert_pdf_to_excel
from app.services.pdf_split import PdfSplitError, split_pdf
from app.services.pdf_to_word import PdfToWordConversionError, convert_pdf_to_word


router = APIRouter(prefix="/api/tools")

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZIP_MEDIA_TYPE = "application/zip"


async def _read_office_document(document_file: UploadFile) -> tuple[bytes, str]:
    file_name = document_file.filename or "文档.docx"
    extension = Path(file_name).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".docx"}:
        raise HTTPException(status_code=400, detail="只支持上传 .xlsx、.xlsm 或 .docx 文件。")

    document_bytes = await document_file.read()
    if not document_bytes:
        raise HTTPException(status_code=400, detail="Office 文档不能为空。")
    if len(document_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="单个 Office 文档不可超过 20MB。")
    if not document_bytes.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 Office 文档。")
    return document_bytes, file_name


async def _read_pdf(pdf_file: UploadFile) -> tuple[bytes, str]:
    file_name = pdf_file.filename or "PDF文件.pdf"
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持上传 .pdf 文件。")

    pdf_bytes = await pdf_file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 文件不能为空。")
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="单个 PDF 不可超过 20MB。")
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF。")
    return pdf_bytes, file_name


@router.get("/document-translation/status")
def document_translation_service_status(
    _current_user: AuthContext = Depends(get_current_user),
):
    return document_translation_status(settings.document_translation_model_dir)


@router.post("/document-translation")
async def document_translation(
    document_file: UploadFile = File(...),
    direction: str = Form(...),
    sheet_names: str = Form(""),
    _current_user: AuthContext = Depends(get_current_user),
):
    document_bytes, file_name = await _read_office_document(document_file)
    if direction not in {"zh_to_en", "en_to_zh"}:
        raise HTTPException(status_code=400, detail="翻译方向无效，只支持中译英或英译中。")

    selected_sheet_names: list[str] | None = None
    if sheet_names.strip():
        try:
            parsed_sheet_names = json.loads(sheet_names)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="工作表选择参数格式不正确。") from exc
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
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-Translation-Unit-Count": str(result.translated_unit_count),
            "X-Translation-Skipped-Count": str(result.skipped_unit_count),
            "X-Translation-Part-Count": str(result.processed_part_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-to-excel")
async def pdf_to_excel(
    pdf_file: UploadFile = File(...),
    _current_user: AuthContext = Depends(get_current_user),
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)

    try:
        result = await run_in_threadpool(convert_pdf_to_excel, pdf_bytes, file_name)
    except PdfToExcelConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        },
    )


@router.post("/pdf-to-word")
async def pdf_to_word(
    pdf_file: UploadFile = File(...),
    _current_user: AuthContext = Depends(get_current_user),
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        result = await run_in_threadpool(convert_pdf_to_word, pdf_bytes, file_name)
    except PdfToWordConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Table-Count": str(result.table_count),
            "X-PDF-Image-Count": str(result.image_count),
            "X-PDF-Text-Page-Count": str(result.text_page_count),
            "X-PDF-OCR-Page-Count": str(result.ocr_page_count),
            "Cache-Control": "no-store",
        },
    )


@router.post("/pdf-split")
async def pdf_split(
    pdf_file: UploadFile = File(...),
    split_mode: str = Form("each_page"),
    page_ranges: str = Form(""),
    _current_user: AuthContext = Depends(get_current_user),
):
    pdf_bytes, file_name = await _read_pdf(pdf_file)
    try:
        result = await run_in_threadpool(
            split_pdf,
            pdf_bytes,
            file_name,
            mode=split_mode,
            page_ranges=page_ranges,
        )
    except PdfSplitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(result.output_file_name)}",
            "X-PDF-Page-Count": str(result.page_count),
            "X-PDF-Split-File-Count": str(result.file_count),
            "Cache-Control": "no-store",
        },
    )
