from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.services.auth import AuthContext, get_current_user
from app.services.pdf_to_excel import PdfToExcelConversionError, convert_pdf_to_excel
from app.services.pdf_split import PdfSplitError, split_pdf
from app.services.pdf_to_word import PdfToWordConversionError, convert_pdf_to_word


router = APIRouter(prefix="/api/tools")

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ZIP_MEDIA_TYPE = "application/zip"


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
