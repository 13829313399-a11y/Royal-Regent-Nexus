"""Extract machine-readable text and rows from shipping attachments."""
import io
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
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        texts = [(page.extract_text() or '').strip() for page in pdf.pages]
    text = '\n'.join(item for item in texts if item).strip()
    return DocumentText(text=text, pages=len(texts), scanned=bool(texts) and len(text) < SCANNED_TEXT_THRESHOLD)


def read_xlsx_rows(data: bytes) -> list[list]:
    workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def read_docx_text(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(' | '.join(cell.text.strip() for cell in row.cells))
    return '\n'.join(line for line in lines if line).strip()
