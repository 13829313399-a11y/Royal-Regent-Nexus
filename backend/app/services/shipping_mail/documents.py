"""Extract machine-readable text and rows from shipping attachments."""
import io
import threading
from dataclasses import dataclass

import openpyxl
import pdfplumber

# 扫描件整份几乎提取不到字符时，不能当作"空内容"处理，必须提示人工录入。
SCANNED_TEXT_THRESHOLD = 40


@dataclass
class DocumentText:
    text: str
    pages: int
    scanned: bool


def read_pdf_text(data: bytes) -> DocumentText:
    """Extract text fast with pypdf, falling back to pdfplumber for layout-heavy PDFs."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        fast_texts = [((page.extract_text() or '') if hasattr(page, 'extract_text') else '').strip() for page in reader.pages]
        fast_text = '\n'.join(item for item in fast_texts if item).strip()
        lines = [line.strip() for line in fast_text.splitlines() if line.strip()]
        short_ratio = (sum(1 for line in lines if len(line) <= 2) / len(lines)) if lines else 1
        if len(fast_text) >= SCANNED_TEXT_THRESHOLD and short_ratio < 0.15:
            return DocumentText(text=fast_text, pages=len(fast_texts), scanned=False)
    except Exception:  # noqa: BLE001 - fall back to the layout-aware extractor
        pass
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        texts = [(page.extract_text() or '').strip() for page in pdf.pages]
    text = '\n'.join(item for item in texts if item).strip()
    return DocumentText(text=text, pages=len(texts), scanned=bool(texts) and len(text) < SCANNED_TEXT_THRESHOLD)


_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()


def read_pdf_ocr_text(data: bytes, resolution: int = 180, max_pages: int = 3) -> DocumentText:
    """OCR a scanned PDF page-by-page with RapidOCR (offline ONNX models)."""
    global _OCR_ENGINE
    lines: list[str] = []
    pages = 0
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            from rapidocr import RapidOCR

            _OCR_ENGINE = RapidOCR()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                image = page.to_image(resolution=resolution).original
                result = _OCR_ENGINE(image)
                for text in getattr(result, 'txts', None) or []:
                    if text and str(text).strip():
                        lines.append(str(text).strip())
    return DocumentText(text='\n'.join(lines).strip(), pages=pages, scanned=False)


def read_pdf_tables(data: bytes) -> list[list[list]]:
    tables: list[list[list]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            tables.extend(page.extract_tables() or [])
    return tables


def read_xlsx_rows(data: bytes) -> list[list]:
    workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def read_xls_rows(data: bytes) -> list[list]:
    import xlrd

    workbook = xlrd.open_workbook(file_contents=data)
    sheet = workbook.sheet_by_index(0)
    return [[sheet.cell_value(row, col) for col in range(sheet.ncols)] for row in range(sheet.nrows)]


def read_docx_text(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(' | '.join(cell.text.strip() for cell in row.cells))
    return '\n'.join(line for line in lines if line).strip()
