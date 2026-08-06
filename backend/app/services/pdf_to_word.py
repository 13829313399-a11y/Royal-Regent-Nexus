from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pdfplumber
from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.services import pdf_to_excel as pdf_extraction


MAX_PDF_PAGES = 80
_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 4,
    "join_tolerance": 4,
    "intersection_tolerance": 5,
}


class PdfToWordConversionError(ValueError):
    pass


@dataclass(frozen=True)
class PdfToWordResult:
    content: bytes
    page_count: int
    table_count: int
    text_page_count: int
    ocr_page_count: int
    output_file_name: str


@dataclass(frozen=True)
class _PageBlock:
    top: float
    kind: str
    value: str | list[list[str]]


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value).replace("\x00", " ")).strip()


def _normalize_table(rows: list[list[object]]) -> list[list[str]]:
    normalized = [[_clean_text(cell) for cell in row] for row in rows]
    normalized = [row for row in normalized if any(row)]
    if not normalized:
        return []
    width = max(len(row) for row in normalized)
    return [row + [""] * (width - len(row)) for row in normalized]


def _join_words(words: list[dict]) -> str:
    text = ""
    for word in words:
        token = _clean_text(word.get("text", ""))
        if not token:
            continue
        if not text:
            text = token
        elif token[0] in ",.;:!?%)]}>，。：；、）》】" or text[-1] in "([{</《【":
            text += token
        elif pdf_extraction._is_cjk_character(text[-1]) and pdf_extraction._is_cjk_character(token[0]):
            text += token
        else:
            text += f" {token}"
    return text


def _word_inside_table(word: dict, table_boxes: list[tuple[float, float, float, float]]) -> bool:
    try:
        center_x = (float(word["x0"]) + float(word["x1"])) / 2
        center_y = (float(word["top"]) + float(word["bottom"])) / 2
    except (KeyError, TypeError, ValueError):
        return False
    return any(x0 <= center_x <= x1 and top <= center_y <= bottom for x0, top, x1, bottom in table_boxes)


def _paragraph_blocks(words: list[dict], table_boxes: list[tuple[float, float, float, float]]) -> list[_PageBlock]:
    usable = [
        word
        for word in words
        if _clean_text(word.get("text", "")) and not _word_inside_table(word, table_boxes)
    ]
    lines: list[list[dict]] = []
    line_tops: list[float] = []
    for word in sorted(usable, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))):
        top = float(word.get("top", 0))
        if lines and abs(top - line_tops[-1]) <= 3.5:
            lines[-1].append(word)
            line_tops[-1] = sum(float(item.get("top", 0)) for item in lines[-1]) / len(lines[-1])
        else:
            lines.append([word])
            line_tops.append(top)

    blocks: list[_PageBlock] = []
    for top, line in zip(line_tops, lines):
        text = _join_words(sorted(line, key=lambda item: float(item.get("x0", 0))))
        if text:
            blocks.append(_PageBlock(top=top, kind="paragraph", value=text))
    return blocks


def _extract_native_blocks(page) -> tuple[list[_PageBlock], int, str]:
    native_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    tables: list[tuple[tuple[float, float, float, float], list[list[str]]]] = []
    try:
        for table in page.find_tables(table_settings=_TABLE_SETTINGS) or []:
            rows = _normalize_table(table.extract() or [])
            if rows:
                tables.append((tuple(float(value) for value in table.bbox), rows))
    except Exception:
        tables = []

    table_boxes = [bbox for bbox, _rows in tables]
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False) or []
    except Exception:
        words = []

    blocks = _paragraph_blocks(words, table_boxes)
    blocks.extend(
        _PageBlock(top=bbox[1], kind="table", value=rows)
        for bbox, rows in tables
    )
    blocks.sort(key=lambda block: block.top)

    if not blocks and native_text.strip():
        blocks = [
            _PageBlock(top=float(index), kind="paragraph", value=line.strip())
            for index, line in enumerate(native_text.splitlines())
            if line.strip()
        ]
    return blocks, len(tables), native_text


def _set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _configure_document(document: Document) -> None:
    for section in document.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(1.6)
        section.right_margin = Cm(1.6)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def _append_paragraph(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.line_spacing = 1.05
    run = paragraph.add_run(text)
    run.font.name = "Arial"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def _append_table(document: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    column_count = max(len(row) for row in rows)
    table = document.add_table(rows=len(rows), cols=column_count)
    table.style = "Table Grid"
    table.autofit = True
    for row_index, row in enumerate(rows):
        for column_index in range(column_count):
            value = row[column_index] if column_index < len(row) else ""
            cell = table.cell(row_index, column_index)
            cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(8.5)
                    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
                    run.bold = row_index == 0
            if row_index == 0:
                _set_cell_shading(cell, "DFF5F2")
    document.add_paragraph().paragraph_format.space_after = Pt(1)


def _output_file_name(source_file_name: str) -> str:
    source_name = Path(source_file_name or "PDF文件.pdf").name
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(source_name).stem).strip(" .") or "PDF文件"
    return f"{stem}_转换结果.docx"


def convert_pdf_to_word(pdf_bytes: bytes, source_file_name: str) -> PdfToWordResult:
    try:
        pdf = pdfplumber.open(BytesIO(pdf_bytes))
    except Exception as exc:
        raise PdfToWordConversionError("PDF 无法读取；请确认文件未加密、未损坏。") from exc

    document = Document()
    _configure_document(document)
    document.core_properties.title = Path(source_file_name or "PDF文件.pdf").name
    table_count = 0
    text_page_count = 0
    ocr_page_count = 0
    converted_page_count = 0

    try:
        page_count = len(pdf.pages)
        if page_count == 0:
            raise PdfToWordConversionError("PDF 中没有可转换的页面。")
        if page_count > MAX_PDF_PAGES:
            raise PdfToWordConversionError(f"单次最多转换 {MAX_PDF_PAGES} 页 PDF。")

        for page_index, page in enumerate(pdf.pages):
            blocks, page_table_count, native_text = _extract_native_blocks(page)
            if pdf_extraction._native_text_is_unreliable(native_text):
                blocks = []
                page_table_count = 0

            used_ocr = False
            if not blocks:
                ocr_rows = pdf_extraction._ocr_page(pdf_bytes, page_index)
                blocks = [
                    _PageBlock(float(index), "paragraph", " ".join(cell for cell in row if cell))
                    for index, row in enumerate(ocr_rows)
                    if any(row)
                ]
                used_ocr = bool(blocks)

            if not blocks:
                continue
            if converted_page_count:
                document.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)

            for block in blocks:
                if block.kind == "table":
                    _append_table(document, block.value)  # type: ignore[arg-type]
                else:
                    _append_paragraph(document, str(block.value))

            converted_page_count += 1
            table_count += page_table_count
            if used_ocr:
                ocr_page_count += 1
            else:
                text_page_count += 1
    finally:
        pdf.close()

    if converted_page_count == 0:
        raise PdfToWordConversionError(
            "未识别到可写入 Word 的文字或表格；如果是扫描件，请确认服务器已安装 OCR 引擎并尝试更清晰的 PDF。",
        )

    output = BytesIO()
    document.save(output)
    return PdfToWordResult(
        content=output.getvalue(),
        page_count=page_count,
        table_count=table_count,
        text_page_count=text_page_count,
        ocr_page_count=ocr_page_count,
        output_file_name=_output_file_name(source_file_name),
    )
