from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.services.auth import AuthContext, get_current_user
from app.services.pdf_to_excel import PdfToExcelConversionError, convert_pdf_to_excel


router = APIRouter(prefix="/api/tools")

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/pdf-to-excel")
async def pdf_to_excel(
    pdf_file: UploadFile = File(...),
    _current_user: AuthContext = Depends(get_current_user),
):
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
