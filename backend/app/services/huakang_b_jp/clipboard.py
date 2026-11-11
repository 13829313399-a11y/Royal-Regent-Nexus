"""Read immutable JP exports as bounded, spreadsheet-safe 44-column TSV."""
from contextlib import contextmanager
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import re

import openpyxl

from .intake import COLUMNS, MAX_FILE, MAX_ROWS, archive

COLUMN_COUNT = 44
NUMERIC_TEXT = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')


@contextmanager
def _export_workbook(content):
    # Keep formulas visible for rejection, and own the underlying stream even
    # if an exception retains an unfinished read-only worksheet iterator.
    with BytesIO(content) as source:
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=False)
        try:
            yield workbook
        finally:
            workbook.close()


def _cell_text(cell):
    if cell.data_type in {'f', 'e'}:
        raise ValueError('已生成问单含公式或错误单元格，不能直接复制，请联系提供者核对。')
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, datetime):
        if value.time().isoformat() != '00:00:00':
            return value.strftime('%Y/%m/%d %H:%M:%S')
        return value.strftime('%Y/%m/%d')
    if isinstance(value, date):
        return value.strftime('%Y/%m/%d')
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float, Decimal)):
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError('已生成问单含无效数字，不能复制。') from exc
        if not number.is_finite():
            raise ValueError('已生成问单含无效数字，不能复制。')
        return format(number, 'f')
    if not isinstance(value, str):
        raise ValueError('已生成问单含不支持的单元格类型，不能复制。')
    # Preserve text identifiers (including leading zeros/long digits) as text.
    # Never construct ="..." formulas. Formula-looking email text is escaped
    # even when whitespace precedes its trigger; tabs/newlines are CSV-quoted.
    stripped = value.lstrip()
    if stripped.startswith(('=', '+', '-', '@', "'")) or NUMERIC_TEXT.fullmatch(value.strip()):
        return "'" + value
    return value


def export_clipboard(content: bytes) -> dict:
    if not content or len(content) > MAX_FILE:
        raise ValueError('已生成问单文件为空或超出复制范围。')
    try:
        with archive(content, xlsx=True):
            pass
        with _export_workbook(content) as workbook:
            if len(workbook.worksheets) != 1:
                raise ValueError('仅支持已生成的单页44列金山问单。')
            sheet = workbook.worksheets[0]
            if (sheet.max_column and sheet.max_column > COLUMN_COUNT) or (sheet.max_row and sheet.max_row > MAX_ROWS + 1):
                raise ValueError('已生成问单超出44列或250行复制范围。')
            declared_rows, declared_columns = sheet.max_row, sheet.max_column
            # A damaged dimension must not hide real cells after row/column 44.
            # Reset the hint, then inspect actual rows with bounded iteration.
            sheet.reset_dimensions()
            header = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
            if list(header) != COLUMNS:
                raise ValueError('已生成问单表头不是原44列金山格式，不能复制。')
            output = StringIO(newline='')
            writer = csv.writer(output, delimiter='\t', lineterminator='\r\n')
            count = 0
            for index, row in enumerate(sheet.iter_rows(min_row=2), start=1):
                if index > MAX_ROWS or len(row) > COLUMN_COUNT:
                    raise ValueError('已生成问单超出44列或250行复制范围。')
                if (declared_rows is not None and index + 1 > declared_rows) or (declared_columns is not None and len(row) > declared_columns):
                    raise ValueError('已生成问单的工作表范围与实际单元格不一致，不能复制。')
                values = [_cell_text(cell) for cell in row]
                values.extend([''] * (COLUMN_COUNT - len(values)))
                if not any(values):
                    raise ValueError('已生成问单含空白明细行，不能复制。')
                writer.writerow(values)
                count += 1
            if not count:
                raise ValueError('已生成问单没有可复制的明细。')
            return {'text': output.getvalue(), 'row_count': count, 'column_count': COLUMN_COUNT}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('已生成问单无法读取，请下载原文件核对或联系提供者。') from exc
