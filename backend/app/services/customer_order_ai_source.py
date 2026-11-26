"""Bounded PO evidence for AI. Never reads the uploaded historical schedule."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

MAX_CELLS = 6000
MAX_CHARS = 70000
MAX_PAGES = 8


class AIRecognitionError(ValueError):
    """Safe, application-authored message suitable for the preview UI."""


def _text(value):
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def collect(filename, content):
    """Return complete bounded evidence or reject; never silently truncate."""
    if not 0 < len(content) <= 12 * 1024 * 1024:
        raise AIRecognitionError('文件大小超出 AI 识别范围')
    evidence, images, notes = {}, [], []
    chars = 0

    def add(identifier, value):
        nonlocal chars
        value = _text(value)
        if not value:
            return
        chars += len(value)
        if len(evidence) >= MAX_CELLS or chars > MAX_CHARS:
            raise AIRecognitionError('文件内容超过单份 AI 识别范围，已保留原识别结果')
        evidence[identifier] = value

    suffix = Path(filename).suffix.lower()
    if suffix in {'.xlsx', '.xlsm'}:
        import openpyxl
        with ZipFile(BytesIO(content)) as archive:
            if sum(z.file_size for z in archive.infolist()) > 64 * 1024 * 1024:
                raise AIRecognitionError('Excel 解压内容超过 AI 识别范围')
        book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            for index, sheet in enumerate(book.worksheets, 1):
                if sheet.sheet_state != 'visible':
                    notes.append('隐藏工作表未发送给 AI')
                    continue
                from app.services.order_workbook_bounds import worksheet_bounds
                sheet.reset_dimensions()  # Inspect stored coordinates, including damaged dimension hints.
                rows, cols = worksheet_bounds(book, sheet, 6000, 160, 'PO 超过 AI 识别范围')
                add(f'S{index}', '工作表：' + sheet.title)
                for row in sheet.iter_rows(max_row=rows, max_col=cols):
                    for cell in row:
                        value = cell.value
                        # Preserve common numeric identifiers displayed with zeros.
                        fmt = getattr(cell, 'number_format', '')
                        if isinstance(value, (int, float)) and fmt and set(fmt) == {'0'} and len(fmt) > 1:
                            if int(value) == value:
                                value = str(int(value)).zfill(len(fmt))
                        if value is not None:
                            add(f'S{index}!{cell.coordinate}', value)
        finally:
            book.close()
    elif suffix == '.xls':
        import xlrd
        book = xlrd.open_workbook(file_contents=content, on_demand=True, formatting_info=True)
        try:
            for index in range(book.nsheets):
                sheet = book.sheet_by_index(index)
                if sheet.visibility:
                    notes.append('隐藏工作表未发送给 AI')
                    continue
                if sheet.nrows > 6000 or sheet.ncols > 160:
                    raise AIRecognitionError('PO 超过 AI 识别范围')
                add(f'S{index+1}', '工作表：' + sheet.name)
                for row in range(sheet.nrows):
                    for col in range(sheet.ncols):
                        cell = sheet.cell(row, col)
                        value = xlrd.xldate_as_datetime(cell.value, book.datemode) if cell.ctype == xlrd.XL_CELL_DATE else cell.value
                        if cell.ctype == xlrd.XL_CELL_NUMBER:
                            fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                            if fmt and set(fmt) == {'0'} and len(fmt) > 1 and int(value) == value:
                                value = str(int(value)).zfill(len(fmt))
                        add(f'S{index+1}!R{row+1}C{col+1}', value)
        finally:
            book.release_resources()
    elif suffix == '.pdf':
        import pdfplumber
        import pypdfium2 as pdfium
        with pdfplumber.open(BytesIO(content)) as book:
            if not 0 < len(book.pages) <= MAX_PAGES:
                raise AIRecognitionError(f'AI 单份 PO 最多 {MAX_PAGES} 页，原识别结果保留')
            for index, page in enumerate(book.pages, 1):
                for line, text in enumerate((page.extract_text() or '').splitlines(), 1):
                    add(f'P{index}L{line}', text)
        book = pdfium.PdfDocument(content)
        try:
            for index in range(len(book)):
                page = book[index]
                try:
                    width, height = page.get_size()
                    bitmap = page.render(scale=min(2, 1800 / max(width, height)))
                    try:
                        picture = bitmap.to_pil()
                        output = BytesIO()
                        picture.save(output, format='PNG')
                        images.append({'id': f'P{index+1}', 'png': output.getvalue()})
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        finally:
            book.close()
    else:
        raise AIRecognitionError('本次 AI 识别支持 Excel 和 PDF；其他格式沿用原识别')
    if not evidence and not images:
        raise AIRecognitionError('原单没有可读取内容')
    return {'evidence': evidence, 'images': images, 'notes': list(dict.fromkeys(notes))}
