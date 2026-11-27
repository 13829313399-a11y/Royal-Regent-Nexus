"""Column policy uses 1-based Excel positions on the final, scoped detail rows."""
from fastapi import HTTPException
from openpyxl.utils import get_column_letter
from app.services.qc_monthly_overview_excel import re_number


ALLOWED = {
    'daily': (7, 8, 10, 11, 12, 13),
    'detail': (15, 16, 17, 18),
    'tracking': (6, 7, 9, 10, 13, 14, 15, 16, 17, 18, 19),
    'orders': (5, 8, 12, 13, 14, 16, 17, 18, 19, 20, 21),
    'caixing': (11, 12, 13, 14, 15),
    'quality-detail': (4, 5, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18),
}


def split_option(body):
    if not isinstance(body, dict) or not isinstance(body.get('hideEmptyCols', False), bool):
        raise HTTPException(422, 'hideEmptyCols 必须是布尔值')
    return {k: v for k, v in body.items() if k != 'hideEmptyCols'}, body.get('hideEmptyCols', False)


def blank(v):
    return v is None or isinstance(v, str) and not v.strip()


def formula_boxes(values):
    qty, pack, boxes = values[6:9]
    return boxes == '' and re_number(qty) and re_number(pack) and float(pack) > 0


def hidden(kind, rows):
    def populated(row, column):
        if kind == 'tracking' and column == 13:
            return bool(row.get('photos'))
        values = row['values']
        if kind == 'quality-detail' and column == 9 and formula_boxes(values):
            return True
        return not blank(values[column - 1])
    return [c for c in ALLOWED.get(kind, ()) if not any(populated(row, c) for row in rows)]


def hide_sheet(sheet, kind, rows):
    columns = hidden(kind, rows)
    for c in columns:
        sheet.column_dimensions[get_column_letter(c)].hidden = True
    for region in list(sheet.merged_cells.ranges):
        if region.min_row != 5 or region.max_row != 5:
            continue
        start, end = region.min_col, region.max_col
        if not any(start <= c <= end for c in columns):
            continue
        anchor = sheet.cell(5, start)
        title, style = anchor.value, anchor._style
        sheet.unmerge_cells(str(region))
        visible = [c for c in range(start, end + 1) if c not in columns]
        if visible:
            anchor.value = None
            dest = sheet.cell(5, visible[0])
            dest.value, dest._style = title, style
            if len(visible) > 1:
                sheet.merge_cells(start_row=5, end_row=5, start_column=visible[0], end_column=visible[-1])
    return [sheet.cell(6, c).value for c in columns]
