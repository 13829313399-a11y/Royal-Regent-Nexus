from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.schemas.indonesia_invoice import RriInvoiceReconciliationResponse
from app.services.auth import AuthContext, get_current_user
from app.services.indonesia_invoice import RriInvoiceParseError, reconcile_rri_invoice_pdfs as reconcile_rri_invoice_pdf_bytes

router = APIRouter(prefix="/api/indonesia-invoices")

MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024


@router.post("/rri/reconcile", response_model=RriInvoiceReconciliationResponse)
async def reconcile_rri_invoice_pdfs(
    invoice_a: UploadFile = File(...),
    invoice_b: UploadFile = File(...),
    _current_user: AuthContext = Depends(get_current_user),
):
    invoice_a_bytes = await invoice_a.read()
    invoice_b_bytes = await invoice_b.read()

    if not invoice_a_bytes or not invoice_b_bytes:
        raise HTTPException(status_code=400, detail="请同时上传 PDF 文件 A 与 PDF 文件 B。")
    if len(invoice_a_bytes) > MAX_PDF_SIZE_BYTES or len(invoice_b_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="单个 PDF 不可超过 20MB。")

    try:
        return reconcile_rri_invoice_pdf_bytes(invoice_a_bytes, invoice_b_bytes)
    except RriInvoiceParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
