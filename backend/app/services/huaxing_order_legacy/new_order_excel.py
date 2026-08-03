# -*- coding: utf-8 -*-
"""Generate standalone new-order workbooks while preserving schedule formats.

The source schedule is treated as a read-only template.  Only header rows and one
representative data-row style are copied into the result, so no historical order
data can leak into the exported workbook.
"""
from __future__ import annotations

import re
from copy import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

import openpyxl
import xlrd
from openpyxl import Workbook
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter


def _normalise(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().lower()
    return re.sub(r"[\s\u3000_／/()（）【】\[\]：:·.,，。-]+", "", text)


def _copy_style(source, target) -> None:
    if not source.has_style:
        return
    target.font = copy(source.font)
    target.fill = copy(source.fill)
    target.border = copy(source.border)
    target.alignment = copy(source.alignment)
    target.number_format = source.number_format
    target.protection = copy(source.protection)


_SHEET_REFERENCE = re.compile(
    r"(?P<sheet>'(?:[^']|'')+'|[A-Za-z0-9_\u4e00-\u9fff]+)!"
    r"(?P<cell>\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)"
)


def _safe_header_value(value: Any, target_sheet: str) -> Any:
    """Remove references to sheets that are intentionally absent from new-order files."""
    if not isinstance(value, str) or not value.startswith("="):
        return value

    target_key = target_sheet.replace("'", "").strip().casefold()

    def replace(match: re.Match[str]) -> str:
        sheet = match.group("sheet").strip("'").replace("''", "'").strip().casefold()
        return match.group(0) if sheet == target_key else "0"

    return _SHEET_REFERENCE.sub(replace, value)


def _xls_colour(book, colour_index: int | None, default: str = "000000") -> str:
    if colour_index is None:
        return default
    rgb = getattr(book, "colour_map", {}).get(colour_index)
    return default if not rgb else "".join(f"{part:02X}" for part in rgb)


def _load_xls(
    path_or_bytes: str | Path | bytes,
    sheet_names: Sequence[str] = (),
) -> Workbook:
    kwargs = {"formatting_info": True}
    if isinstance(path_or_bytes, bytes):
        book = xlrd.open_workbook(file_contents=path_or_bytes, **kwargs)
    else:
        book = xlrd.open_workbook(str(path_or_bytes), **kwargs)
    result = Workbook()
    result.remove(result.active)
    selected = [sheet for sheet in book.sheets() if not sheet_names or sheet.name in sheet_names]
    if not selected:
        selected = book.sheets()
    for source in selected:
        ws = result.create_sheet((source.name or "Sheet")[:31])
        for row_index in range(source.nrows):
            row_info = source.rowinfo_map.get(row_index)
            if row_info and row_info.height:
                ws.row_dimensions[row_index + 1].height = row_info.height / 20
            for col_index in range(source.ncols):
                old = source.cell(row_index, col_index)
                value = old.value
                if old.ctype == xlrd.XL_CELL_DATE:
                    try:
                        value = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                    except (TypeError, ValueError):
                        pass
                cell = ws.cell(row_index + 1, col_index + 1, value)
                try:
                    xf = book.xf_list[old.xf_index]
                    font = book.font_list[xf.font_index]
                    cell.font = Font(
                        name=font.name or "Arial",
                        size=(font.height or 200) / 20,
                        bold=bool(font.bold),
                        italic=bool(font.italic),
                        underline="single" if font.underline_type else None,
                        color=_xls_colour(book, font.colour_index),
                    )
                    background = book.colour_map.get(xf.background.pattern_colour_index)
                    if background:
                        cell.fill = PatternFill(
                            "solid",
                            fgColor="".join(f"{part:02X}" for part in background),
                        )
                    border = xf.border
                    side = lambda style, colour: Side(
                        style="thin" if style else None,
                        color=_xls_colour(book, colour),
                    )
                    cell.border = Border(
                        left=side(border.left_line_style, border.left_colour_index),
                        right=side(border.right_line_style, border.right_colour_index),
                        top=side(border.top_line_style, border.top_colour_index),
                        bottom=side(border.bottom_line_style, border.bottom_colour_index),
                    )
                    alignment = xf.alignment
                    horizontal = {
                        1: "left", 2: "center", 3: "right", 4: "fill",
                        5: "justify", 6: "centerContinuous", 7: "distributed",
                    }.get(alignment.hor_align)
                    vertical = {0: "top", 1: "center", 2: "bottom", 3: "justify", 4: "distributed"}.get(
                        alignment.vert_align
                    )
                    cell.alignment = Alignment(
                        horizontal=horizontal,
                        vertical=vertical,
                        wrap_text=bool(alignment.text_wrapped),
                    )
                    cell.number_format = book.format_map[xf.format_key].format_str or "General"
                    cell.protection = Protection(
                        locked=bool(xf.protection.cell_locked),
                        hidden=bool(xf.protection.formula_hidden),
                    )
                except (AttributeError, IndexError, KeyError, TypeError):
                    pass
        for col_index, info in source.colinfo_map.items():
            if info.width:
                ws.column_dimensions[get_column_letter(col_index + 1)].width = max(1, info.width / 256)
        for row_low, row_high, col_low, col_high in source.merged_cells:
            ws.merge_cells(
                start_row=row_low + 1,
                end_row=row_high,
                start_column=col_low + 1,
                end_column=col_high,
            )
    return result


def load_workbook_compatible(
    source: str | Path | bytes | BinaryIO,
    *,
    filename: str = "",
    data_only: bool = False,
    sheet_names: Sequence[str] = (),
) -> Workbook:
    """Load xlsx/xlsm/xls from a path, bytes, or file-like object."""
    suffix = Path(filename or str(source) if not isinstance(source, bytes) else filename).suffix.lower()
    if suffix == ".xls":
        if hasattr(source, "read"):
            source = source.read()
        return _load_xls(source, sheet_names)
    if hasattr(source, "read"):
        payload = source.read()
        return openpyxl.load_workbook(BytesIO(payload), data_only=data_only)
    if isinstance(source, bytes):
        return openpyxl.load_workbook(BytesIO(source), data_only=data_only)
    return openpyxl.load_workbook(source, data_only=data_only)


def _alias_lookup(field_aliases: Mapping[str, Sequence[str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for field, aliases in field_aliases.items():
        for alias in (field, *aliases):
            normalised = _normalise(alias)
            if normalised:
                lookup[normalised] = field
    return lookup


def detect_header(
    ws,
    field_aliases: Mapping[str, Sequence[str]],
    *,
    scan_rows: int = 20,
) -> tuple[int, dict[int, str]]:
    """Return the highest-scoring header row and its column-to-field map."""
    aliases = _alias_lookup(field_aliases)
    best_row = 1
    best_map: dict[int, str] = {}
    for row in range(1, min(ws.max_row or 1, scan_rows) + 1):
        current: dict[int, str] = {}
        for col in range(1, (ws.max_column or 1) + 1):
            value = _normalise(ws.cell(row, col).value)
            if not value:
                continue
            field = aliases.get(value)
            if not field:
                field = next(
                    (
                        candidate
                        for alias, candidate in aliases.items()
                        if len(alias) >= 2 and (alias in value or value in alias)
                    ),
                    "",
                )
            if field and field not in current.values():
                current[col] = field
        if len(current) > len(best_map):
            best_row, best_map = row, current
    return best_row, best_map


def select_sheet(
    workbook: Workbook,
    field_aliases: Mapping[str, Sequence[str]],
    sheet_names: Sequence[str] = (),
) -> tuple[Any, int, dict[int, str]]:
    for name in sheet_names:
        if name in workbook.sheetnames:
            ws = workbook[name]
            header_row, column_map = detect_header(ws, field_aliases)
            return ws, header_row, column_map
    best = None
    for ws in workbook.worksheets:
        header_row, column_map = detect_header(ws, field_aliases)
        candidate = (len(column_map), ws, header_row, column_map)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        raise ValueError("模板中没有可用工作表")
    return best[1], best[2], best[3]


def _copy_headers(source, target, header_rows: int, max_col: int) -> None:
    for row in range(1, header_rows + 1):
        if source.row_dimensions[row].height:
            target.row_dimensions[row].height = source.row_dimensions[row].height
        for col in range(1, max_col + 1):
            old = source.cell(row, col)
            new = target.cell(
                row,
                col,
                _safe_header_value(old.value, target.title),
            )
            _copy_style(old, new)
    for col in range(1, max_col + 1):
        letter = get_column_letter(col)
        dimension = source.column_dimensions[letter]
        target.column_dimensions[letter].width = dimension.width
        target.column_dimensions[letter].hidden = dimension.hidden
    for merged in source.merged_cells.ranges:
        if merged.max_row <= header_rows and merged.max_col <= max_col:
            target.merge_cells(str(merged))
    target.freeze_panes = source.freeze_panes or f"A{header_rows + 1}"
    target.sheet_view.showGridLines = source.sheet_view.showGridLines


def _style_source_row(ws, header_rows: int, max_col: int, requested: int | None) -> int:
    if requested and requested <= ws.max_row:
        return requested
    candidates = range(header_rows + 1, min(ws.max_row or header_rows + 1, header_rows + 30) + 1)
    return max(
        candidates,
        key=lambda row: sum(1 for col in range(1, max_col + 1) if ws.cell(row, col).has_style),
        default=header_rows,
    )


def _safe_value(value: Any) -> Any:
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (dict, list, tuple, set)):
        return " / ".join(str(item) for item in value)
    return value


ITEM_FIELD_CANDIDATES = ("item_no", "item", "sku", "product_no", "material_no")
PRODUCT_FIELD_CANDIDATES = (
    "product_name",
    "product",
    "description",
    "english_name",
)


def _item_key(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    return re.sub(r"[^A-Z0-9]", "", text)


def _display_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def inherit_product_names(
    source,
    header_row: int,
    column_map: Mapping[int, str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use the schedule's unique item-to-name mapping as the product master.

    A source item may occur on many historical rows.  The name is inherited only
    when those rows resolve to one non-empty normalized name.  Conflicting source
    names are reported and never guessed.  A PO-provided English description is
    preserved; schedule English names only fill blanks.
    """
    field_columns = {field: col for col, field in column_map.items()}
    item_field = next((field for field in ITEM_FIELD_CANDIDATES if field in field_columns), "")
    product_fields = [
        field for field in PRODUCT_FIELD_CANDIDATES if field in field_columns
    ]
    if not item_field or not product_fields:
        return {
            "item_field": item_field,
            "product_fields": product_fields,
            "mapped_items": 0,
            "applied": 0,
            "conflicts": [],
        }

    source_values: dict[str, dict[str, dict[str, str]]] = {}
    item_col = field_columns[item_field]
    for row_no in range(header_row + 1, (source.max_row or header_row) + 1):
        key = _item_key(source.cell(row_no, item_col).value)
        if not key:
            continue
        per_item = source_values.setdefault(key, {})
        for field in product_fields:
            value = _display_text(source.cell(row_no, field_columns[field]).value)
            if not value or value.startswith("="):
                continue
            normalized = _normalise(value)
            if normalized:
                per_item.setdefault(field, {})[normalized] = value

    unique_map: dict[str, dict[str, str]] = {}
    conflicts: list[dict[str, Any]] = []
    for item, fields in source_values.items():
        for field, values in fields.items():
            if len(values) == 1:
                unique_map.setdefault(item, {})[field] = next(iter(values.values()))
            elif len(values) > 1:
                conflicts.append({
                    "item": item,
                    "field": field,
                    "values": list(values.values())[:8],
                })

    applied = 0
    inherited_rows: list[dict[str, str]] = []
    for record in rows:
        key = _item_key(record.get(item_field))
        inherited = unique_map.get(key, {})
        if not inherited:
            continue
        for field, value in inherited.items():
            old = _display_text(record.get(field))
            if _normalise(old) == _normalise(value):
                continue
            # 英文品名在有 PO DESCRIPTION 时以本次 PO 为准；排期只用于补空。
            # 中文“产品名称”仍按用户要求由货号对应的排期产品主数据覆盖。
            if field == "english_name" and old:
                continue
            record[field] = value
            if field in {"product_name", "product"} and "product_name_source" in record:
                record["product_name_source"] = "最新排期按货号唯一继承"
            applied += 1
            inherited_rows.append({
                "item": key,
                "field": field,
                "po_value": old,
                "schedule_value": value,
            })

    return {
        "item_field": item_field,
        "product_fields": product_fields,
        "mapped_items": len(unique_map),
        "applied": applied,
        "inherited_rows": inherited_rows,
        "conflicts": conflicts,
        "rule": "same_schedule_same_item_unique_name",
    }


def create_new_order_workbook(
    template: str | Path | bytes | BinaryIO,
    output_path: str | Path | BinaryIO,
    records: Iterable[Mapping[str, Any]],
    field_aliases: Mapping[str, Sequence[str]],
    *,
    filename: str = "",
    sheet_names: Sequence[str] = (),
    header_rows: int | None = None,
    style_row: int | None = None,
    max_col: int | None = None,
    sheet_title: str = "新单",
    audit_sheet: bool = True,
    field_formats: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new-order-only workbook from the corresponding schedule template."""
    source_book = load_workbook_compatible(
        template,
        filename=filename,
        sheet_names=sheet_names,
    )
    rows = [dict(record) for record in records]
    try:
        source, detected_header, column_map = select_sheet(source_book, field_aliases, sheet_names)
        header_rows = header_rows or detected_header
        if not column_map:
            _, column_map = detect_header(source, field_aliases, scan_rows=max(20, header_rows))
        if not column_map:
            raise ValueError(f"{source.title} 未识别到任何可写入列")
        if max_col is None:
            header_last_col = max(
                (
                    col
                    for row in range(1, header_rows + 1)
                    for col in range(1, (source.max_column or 1) + 1)
                    if source.cell(row, col).value not in (None, "")
                ),
                default=max(column_map),
            )
            max_col = max(max(column_map), header_last_col)
        style_row = _style_source_row(source, header_rows, max_col, style_row)
        inheritance = inherit_product_names(
            source,
            header_rows,
            column_map,
            rows,
        )

        result = Workbook()
        output = result.active
        output.title = sheet_title[:31]
        _copy_headers(source, output, header_rows, max_col)

        for offset, record in enumerate(rows, start=header_rows + 1):
            if source.row_dimensions[style_row].height:
                output.row_dimensions[offset].height = source.row_dimensions[style_row].height
            for col in range(1, max_col + 1):
                old = source.cell(style_row, col)
                new = output.cell(offset, col)
                _copy_style(old, new)
                if isinstance(old.value, str) and old.value.startswith("="):
                    # Standalone exports intentionally omit historical/reference
                    # sheets.  Keep row-local formulas only; cross-sheet/external
                    # formulas would become broken links in the new workbook.
                    if "!" not in old.value and "[" not in old.value:
                        try:
                            new.value = Translator(old.value, origin=old.coordinate).translate_formula(new.coordinate)
                        except (TypeError, ValueError):
                            new.value = old.value
            for col, field in column_map.items():
                value = record.get(field, "")
                cell = output.cell(offset, col)
                cell.value = _safe_value(value)
                if field_formats and field in field_formats:
                    # 模板空白行有时残留了错误的日期/数字格式。字段语义应高于
                    # 样式行的 number_format，否则数量 800 会显示成 1902 年日期。
                    cell.number_format = field_formats[field]

        if audit_sheet:
            audit = result.create_sheet("识别明细")
            fields = list(field_aliases)
            for col, field in enumerate(fields, 1):
                cell = audit.cell(1, col, field)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F4E78")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            for row_index, record in enumerate(rows, 2):
                for col, field in enumerate(fields, 1):
                    cell = audit.cell(row_index, col, _safe_value(record.get(field, "")))
                    if field_formats and field in field_formats:
                        cell.number_format = field_formats[field]
            audit.freeze_panes = "A2"
            for col, field in enumerate(fields, 1):
                width = max(
                    [len(str(field))]
                    + [len(str(rows[index].get(field, ""))) for index in range(min(len(rows), 100))]
                )
                audit.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 10), 42)

        if inheritance["applied"] or inheritance["conflicts"]:
            inherited = result.create_sheet("排期继承检查")
            headers = ("状态", "货号", "字段", "PO原值", "排期标准值 / 冲突值")
            for col, title in enumerate(headers, 1):
                cell = inherited.cell(1, col, title)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="2F6B5F")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            row_no = 2
            for detail in inheritance["inherited_rows"]:
                values = (
                    "已按货号继承",
                    detail["item"],
                    detail["field"],
                    detail["po_value"],
                    detail["schedule_value"],
                )
                for col, value in enumerate(values, 1):
                    inherited.cell(row_no, col, _safe_value(value))
                row_no += 1
            for conflict in inheritance["conflicts"]:
                values = (
                    "排期存在冲突，未自动继承",
                    conflict["item"],
                    conflict["field"],
                    "",
                    " / ".join(conflict["values"]),
                )
                for col, value in enumerate(values, 1):
                    inherited.cell(row_no, col, _safe_value(value))
                row_no += 1
            inherited.freeze_panes = "A2"
            for col, width in enumerate((24, 20, 18, 36, 60), 1):
                inherited.column_dimensions[get_column_letter(col)].width = width

        if hasattr(output_path, "write"):
            result.save(output_path)
            output_reference = "<memory>"
        else:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            result.save(output_file)
            output_reference = str(output_file)
        result.close()
        return {
            "path": output_reference,
            "template_sheet": source.title,
            "header_rows": header_rows,
            "style_row": style_row,
            "rows": len(rows),
            "mapped_columns": {str(col): field for col, field in column_map.items()},
            "inheritance": inheritance,
            "mode": "new_order_only",
        }
    finally:
        source_book.close()
