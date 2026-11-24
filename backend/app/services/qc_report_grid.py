"""Engine-independent screen preview of generated QC workbooks (not an Excel writer)."""
import base64
from collections import defaultdict
from datetime import datetime
from html import escape
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import xlrd


def display(value, fmt):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if '%' in fmt:
            return f'{value:.1%}'
        return str(int(value)) if value == int(value) else str(value)
    return str(value)


def table(rows, cols, widths, merges, value_at, images):
    letters = [get_column_letter(i) for i in range(1, cols+1)]
    parts = ['<table class="wb-simple"><colgroup width="38"></colgroup>']
    parts.extend(f'<colgroup width="{width}"></colgroup>' for width in widths)
    parts.append('<thead><tr><th class="col-num"></th>')
    parts.extend(f'<th class="col-num">{letter}</th>' for letter in letters)
    parts.append('</tr></thead><tbody>')
    anchors = {(r,c):(h,w) for r,c,h,w in merges}
    covered = {(y,x) for r,c,h,w in merges for y in range(r,r+h) for x in range(c,c+w) if (y,x)!=(r,c)}
    for row in range(1, rows+1):
        parts.append(f'<tr><th class="row-num">{row}</th>')
        for col, letter in enumerate(letters, 1):
            key = row,col
            if key in covered:
                continue
            value, fmt = value_at(row,col)
            text = escape(display(value,fmt))
            attrs = ''
            if key in anchors:
                h,w = anchors[key]
                attrs = f' rowspan="{h}" colspan="{w}"'
            photos = ''.join(images.get(key, ()))
            parts.append(f'<td data-addr="{letter}{row}"{attrs}>{text}{photos}</td>')
        parts.append('</tr>')
    return ''.join(parts) + '</tbody></table>'


def xlsx_images(sheet):
    images = defaultdict(list)
    for image in sheet._images:
        marker = getattr(image.anchor, '_from', None)
        mime = {'png':'png', 'jpeg':'jpeg', 'jpg':'jpeg', 'gif':'gif'}.get(image.format.lower())
        if marker is None or not mime:
            continue
        try:
            raw = image._data()
        except (ValueError, OSError):
            continue
        source = base64.b64encode(raw).decode('ascii')
        width = int(min(90, image.width))
        height = max(1, round(image.height * width / image.width))
        images[marker.row+1, marker.col+1].append(
            f'<img src="data:image/{mime};base64,{source}" width="{width}" height="{height}" alt="">')
    return images


def render_grid(content, legacy):
    sheets = []
    if legacy:
        book = xlrd.open_workbook(file_contents=content, formatting_info=True)
        for sheet in book.sheets():
            def value_at(row,col):
                if col>sheet.row_len(row-1):
                    return None, ''
                cell = sheet.cell(row-1,col-1)
                xf = book.xf_list[cell.xf_index]
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate_as_datetime(value, book.datemode)
                return value, book.format_map[xf.format_key].format_str
            merges = [(r+1,c+1,rr-r,cc-c) for r,rr,c,cc in sheet.merged_cells]
            widths = [max(64, round(sheet.colinfo_map[c].width / 256 * 8))
                      if c in sheet.colinfo_map else 96 for c in range(sheet.ncols)]
            sheets.append(dict(name=sheet.name, html=table(sheet.nrows,sheet.ncols,widths,merges,value_at,{})))
        return sheets
    book = load_workbook(BytesIO(content), data_only=True, keep_links=False)
    try:
        for sheet in book.worksheets:
            def value_at(row,col):
                cell = sheet.cell(row,col)
                return cell.value, cell.number_format or ''
            merges = [(m.min_row,m.min_col,m.max_row-m.min_row+1,m.max_col-m.min_col+1)
                      for m in sheet.merged_cells.ranges]
            widths = [max(64, round(sheet.column_dimensions[letter].width * 8))
                      if (letter := get_column_letter(c)) in sheet.column_dimensions else 96
                      for c in range(1,sheet.max_column+1)]
            sheets.append(dict(name=sheet.title, html=table(sheet.max_row,sheet.max_column,widths,merges,value_at,
                                                            xlsx_images(sheet))))
        return sheets
    finally:
        book.close()
