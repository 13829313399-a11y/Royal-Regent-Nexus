from __future__ import annotations

from copy import copy
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.utils.exceptions import InvalidFileException

from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteAttachment,
    InternalQuoteSection,
)


P3_TEMPLATE_VERSION = "internal-quote-p3-v1"
P4_TEMPLATE_VERSION = "internal-quote-p4-v2"
WORKBOOK_LAYOUT_VERSION = "internal-quote-unified-desk-v6"
TEMPLATE_VERSION = P3_TEMPLATE_VERSION
STRUCTURED_DATA_SCHEMA_VERSION = "internal-quote-structured-data-v1"
STRUCTURED_DATA_CHUNK_SIZE = 30000
SECTION_ORDER = (
    "sales",
    "engineering",
    "electronic",
    "molding",
    "painting",
    "slush",
    "sewing",
    "assembly",
)

NAVY = "17324D"
TEAL = "0F766E"
PALE_TEAL = "DFF4F1"
PALE_BLUE = "E8F1F8"
SLATE = "334155"
WHITE = "FFFFFF"
THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

TEMPLATE_RED = "FF0000"
TEMPLATE_BLUE = "0000FF"
TEMPLATE_BLACK = "000000"
TEMPLATE_YELLOW = "FFF2CC"
TEMPLATE_ORANGE = "FCE4D6"
TEMPLATE_SKY = "DDEBF7"
TEMPLATE_GREEN = "E2F0D9"
TEMPLATE_GRAY = "E7E6E6"
TEMPLATE_THIN = Side(style="thin", color=TEMPLATE_BLACK)
TEMPLATE_MEDIUM = Side(style="medium", color=TEMPLATE_BLACK)
TEMPLATE_BORDER = Border(
    left=TEMPLATE_THIN,
    right=TEMPLATE_THIN,
    top=TEMPLATE_THIN,
    bottom=TEMPLATE_THIN,
)


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_text(value: object) -> str:
    result = "" if value is None else str(value)
    if result.startswith(("=", "+", "-", "@")):
        return f"'{result}"
    return result


def _json_text(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rendered[:32000]


def _canonical_json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_chunks(value: object) -> list[str]:
    rendered = _canonical_json_text(value)
    return [
        rendered[index:index + STRUCTURED_DATA_CHUNK_SIZE]
        for index in range(0, len(rendered), STRUCTURED_DATA_CHUNK_SIZE)
    ] or [""]


def _number(value: object) -> float | str:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return ""


def _float_value(value: object, default: float = 0.0) -> float:
    parsed = _number(value)
    return parsed if isinstance(parsed, float) else default


def _price_number(value: object) -> float | str:
    parsed = _number(value)
    if isinstance(parsed, float):
        return parsed
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value or ""))
    return float(match.group(0).replace(",", "")) if match else ""


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _section_payload(section: InternalQuoteSection | None) -> dict[str, Any]:
    return _json_object(section.payload_json) if section is not None else {}


def _section_calculation(section: InternalQuoteSection | None) -> dict[str, Any]:
    return _json_object(section.calculation_json) if section is not None else {}


def _calculation_lines(section: InternalQuoteSection | None, kind: str | None = None) -> list[dict[str, Any]]:
    rows = _list_of_dicts(_section_calculation(section).get("line_breakdown", []))
    return [row for row in rows if row.get("kind") == kind] if kind else rows


def _rr2_values(summary: dict[str, Any], table: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in _list_of_dicts(summary.get(table, [])):
        key = str(row.get("key") or "")
        if key:
            result[key] = _float_value(row.get("value"))
    return result


def _rr2_tax_rows(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("key")): row
        for row in _list_of_dicts(summary.get("t4", []))
        if row.get("key")
    }


def _material_label(raw_key: object) -> str:
    parts = [part.strip() for part in str(raw_key or "").split("|") if part.strip()]
    if not parts:
        return ""
    material = parts[0]
    grade = parts[1] if len(parts) > 1 else ""
    label = f"{grade}{material}" if grade else material
    return label if label.endswith("料") else f"{label}料"


def _reference_materials(snapshot: dict[str, Any]) -> list[tuple[str, float | str]]:
    source = snapshot.get("material_prices", {})
    rows: list[tuple[str, float | str]] = []
    if isinstance(source, dict):
        for key, value in source.items():
            if isinstance(value, dict):
                price = value.get("price_hkd_lb", value.get("price_hkd", value.get("price", "")))
                label = value.get("label") or _material_label(key)
            else:
                price = value
                label = _material_label(key)
            rows.append((_safe_text(label), _number(price)))
    elif isinstance(source, list):
        for value in _list_of_dicts(source):
            key = value.get("label") or f"{value.get('material', '')}|{value.get('grade', '')}"
            price = value.get("price_hkd_lb", value.get("price_hkd", value.get("price", "")))
            rows.append((_material_label(key), _number(price)))
    return rows


def _reference_machines(snapshot: dict[str, Any]) -> list[tuple[str, float | str]]:
    source = snapshot.get("machine_prices", [])
    rows: list[tuple[str, float | str]] = []
    if isinstance(source, dict):
        source = [{"machine_code": key, "shift_price_hkd": value} for key, value in source.items()]
    for value in _list_of_dicts(source):
        label = (
            value.get("machine_range")
            or value.get("range")
            or value.get("machine_name")
            or value.get("name")
            or value.get("machine_code")
            or value.get("code")
            or ""
        )
        price = value.get("shift_price_hkd", value.get("price_hkd", value.get("price", "")))
        rows.append((_safe_text(label), _number(price)))
    return rows


def _tax_rate(snapshot: dict[str, Any], key: str, default: float) -> float:
    return _float_value(_dict_value(snapshot.get("tax_rates", {})).get(key), default)


def _template_cell(
    sheet,
    row: int,
    column: int,
    value: object = None,
    *,
    bold: bool = False,
    color: str = TEMPLATE_BLACK,
    fill: str | None = None,
    horizontal: str = "center",
    vertical: str = "center",
    wrap_text: bool = True,
    size: int = 10,
    number_format: str | None = None,
    border: Border | None = TEMPLATE_BORDER,
    font_name: str = "宋体",
) -> None:
    cell = sheet.cell(row, column, value)
    cell.font = Font(name=font_name, size=size, bold=bold, color=color)
    cell.alignment = Alignment(
        horizontal=horizontal,
        vertical=vertical,
        wrap_text=wrap_text,
    )
    cell.border = border or Border()
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    if number_format:
        cell.number_format = number_format


def _percent_fraction(value: object) -> float:
    """Normalize persisted percent-points to an Excel percentage fraction."""

    numeric = _float_value(value)
    return numeric / 100 if abs(numeric) > 0.5 else numeric


def _template_style_range(
    sheet,
    min_row: int,
    max_row: int,
    min_column: int,
    max_column: int,
    *,
    fill: str | None = None,
    bold: bool = False,
    color: str = TEMPLATE_BLACK,
) -> None:
    for row in range(min_row, max_row + 1):
        for column in range(min_column, max_column + 1):
            _template_cell(
                sheet,
                row,
                column,
                sheet.cell(row, column).value,
                fill=fill,
                bold=bold,
                color=color,
            )


def _replace_border_sides(
    cell,
    *,
    left: Side | None = None,
    right: Side | None = None,
    top: Side | None = None,
    bottom: Side | None = None,
) -> None:
    current = cell.border
    cell.border = Border(
        left=current.left if left is None else left,
        right=current.right if right is None else right,
        top=current.top if top is None else top,
        bottom=current.bottom if bottom is None else bottom,
    )


def _apply_outline_border(
    sheet,
    min_row: int,
    max_row: int,
    min_column: int,
    max_column: int,
    side: Side,
) -> None:
    for column in range(min_column, max_column + 1):
        _replace_border_sides(sheet.cell(min_row, column), top=side)
        _replace_border_sides(sheet.cell(max_row, column), bottom=side)
    for row in range(min_row, max_row + 1):
        _replace_border_sides(sheet.cell(row, min_column), left=side)
        _replace_border_sides(sheet.cell(row, max_column), right=side)


def _positive_integer(value: object) -> int | None:
    numeric = _float_value(value)
    if numeric <= 0 or not numeric.is_integer():
        return None
    return int(numeric)


def _moq_label(value: object) -> str:
    moq = _positive_integer(value)
    if moq is None:
        return "MOQ"
    if moq % 1000 == 0:
        return f"MOQ{moq // 1000}K"
    return f"MOQ{moq:,}"


def _shipping_markup_tiers(
    shipping: dict[str, Any],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in _list_of_dicts(shipping.get("markup_tiers", [])):
        moq = _positive_integer(source.get("moq"))
        markup = _float_value(source.get("markup"), _float_value(source.get("markup_x")))
        if moq is None or markup <= 0:
            continue
        rows.append(
            {
                "moq": moq,
                "markup": markup,
                "is_active": bool(source.get("is_active")),
            }
        )
    if not rows:
        rows = [
            {
                "moq": _positive_integer(shipping.get("active_markup_moq")) or 10000,
                "markup": _float_value(shipping.get("markup"), 1.2),
                "is_active": True,
            }
        ]
    rows.sort(key=lambda row: int(row["moq"]))
    if not any(bool(row["is_active"]) for row in rows):
        active_moq = _positive_integer(shipping.get("active_markup_moq"))
        selected = next((row for row in rows if row["moq"] == active_moq), rows[-1])
        selected["is_active"] = True
    return rows


def _testing_fee_values(
    sales_section: InternalQuoteSection | None,
    sales_payload: dict[str, Any],
) -> tuple[float, list[dict[str, object]]]:
    totals = _dict_value(_section_calculation(sales_section).get("totals", {}))
    total_usd = _float_value(
        totals.get(
            "testing_fee_total_usd",
            sales_payload.get("testing_fee_total_usd"),
        )
    )
    rows = _list_of_dicts(totals.get("testing_fee_tiers", []))
    if not rows:
        raw_moqs = sales_payload.get("testing_fee_moqs")
        if not isinstance(raw_moqs, list):
            legacy_moq = sales_payload.get("testing_fee_moq")
            raw_moqs = [] if legacy_moq in (None, "") else [legacy_moq]
        rows = [
            {
                "moq": value,
                "unit_price_usd": (
                    total_usd / moq
                    if (moq := _positive_integer(value)) is not None
                    else 0
                ),
            }
            for value in raw_moqs
        ]
    result: list[dict[str, object]] = []
    seen: set[int] = set()
    for source in rows:
        moq = _positive_integer(source.get("moq"))
        if moq is None or moq in seen:
            continue
        seen.add(moq)
        result.append(
            {
                "moq": moq,
                "unit_price_usd": _float_value(
                    source.get("unit_price_usd"),
                    total_usd / moq if total_usd else 0.0,
                ),
            }
        )
    result.sort(key=lambda row: int(row["moq"]))
    return total_usd, result


def _dimensions(value: object) -> tuple[float | str, float | str, float | str]:
    source = _dict_value(value)
    return (
        _number(source.get("length", source.get("length_cm", ""))),
        _number(source.get("width", source.get("width_cm", ""))),
        _number(source.get("height", source.get("height_cm", ""))),
    )


def _dimension_unit(value: object) -> str:
    return "cm" if str(value or "").strip().lower() == "cm" else "inch"


def _inch_value_for_unit(value: object, unit: str) -> float | str:
    parsed = _number(value)
    if not isinstance(parsed, float):
        return ""
    return round(parsed * 2.54, 4) if unit == "cm" else parsed


def _dimensions_for_unit(value: object, unit: str) -> tuple[float | str, float | str, float | str]:
    return tuple(_inch_value_for_unit(item, unit) for item in _dimensions(value))


def _style_title(sheet, title: str, end_column: int) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
    cell = sheet.cell(1, 1, title)
    cell.font = Font(name="Microsoft YaHei", size=17, bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 30


def _header_row(sheet, row: int, headers: Iterable[str]) -> None:
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row, column, header)
        cell.font = Font(name="Microsoft YaHei", bold=True, color=SLATE)
        cell.fill = PatternFill("solid", fgColor=PALE_TEAL)
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _body_row(
    sheet,
    row: int,
    values: Iterable[object],
    *,
    amount_columns: set[int] | None = None,
    text_columns: set[int] | None = None,
) -> None:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row, column, value)
        cell.font = Font(name="Microsoft YaHei", color=SLATE)
        cell.border = BORDER
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if text_columns and column in text_columns:
            cell.data_type = "s"
        if amount_columns and column in amount_columns and isinstance(value, (int, float)):
            cell.number_format = "#,##0.0000"


def _finish_sheet(sheet, widths: tuple[int, ...]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A4"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25


def _line_amount(line: dict[str, Any]) -> float | str:
    for key in (
        "amount_hkd",
        "line_hkd",
        "per_piece_hkd",
        "amount_hkd_pcs",
        "deduction_hkd",
        "total_usd",
    ):
        if key in line and line[key] is not None:
            return _number(line[key])
    return ""


def _build_summary_sheet(
    workbook: Workbook,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    reference_snapshot: dict[str, Any],
    rr2_cost_summary: dict[str, Any],
    cost_context: dict[str, Any],
) -> None:
    """Render the current internal-quote template with dynamic detail anchors."""

    sheet = workbook.active
    sheet.title = "报价明细"
    sheet.sheet_view.showGridLines = True
    by_code = {section.department: section for section in sections}
    sales_section = by_code.get("sales")
    sales_payload = _section_payload(sales_section)
    shipping = _dict_value(rr2_cost_summary.get("shipping_pricing", {}))
    t1 = _rr2_values(rr2_cost_summary, "t1")
    t2 = _rr2_values(rr2_cost_summary, "t2")
    t3 = _rr2_values(rr2_cost_summary, "t3")
    t4 = _rr2_tax_rows(rr2_cost_summary)
    markup_tiers = _shipping_markup_tiers(shipping)
    active_tier = next((row for row in markup_tiers if row.get("is_active")), markup_tiers[-1])
    testing_fee_total_usd, testing_fee_tiers = _testing_fee_values(
        sales_section,
        sales_payload,
    )

    all_shipping_rows = _list_of_dicts(shipping.get("rows", []))
    if all_shipping_rows and str(all_shipping_rows[0].get("name") or "") == "出厂价":
        route_rows = all_shipping_rows[1:]
    else:
        route_rows = all_shipping_rows
    route_start_column = 5
    route_end_column = route_start_column + len(route_rows) - 1
    side_start_column = max(14, route_end_column + 2)
    side_end_column = side_start_column + 3
    outer_right_column = max(18, side_end_column)

    # A1:R6 — latest frozen materials/machines, tax references, carton factors
    # and exchange values.  The extra R column keeps HKD/USD and selected MOQ
    # visible and auditable without crowding the reference template's C:Q grid.
    materials = _reference_materials(reference_snapshot)[:18]
    machines = _reference_machines(reference_snapshot)[:10]
    for row in range(1, 7):
        for column in range(3, outer_right_column + 1):
            _template_cell(
                sheet,
                row,
                column,
                "",
                color=TEMPLATE_RED if row % 2 == 1 else TEMPLATE_BLUE,
                size=10,
                wrap_text=False,
                border=None,
            )
        sheet.row_dimensions[row].height = 12.75 if row < 6 else 13.5

    for header_row, start_index, end_index, start_column in (
        (1, 0, 10, 4),
        (3, 10, 18, 4),
        (5, 0, 10, 4),
    ):
        source = machines if header_row == 5 else materials
        rows = source[start_index:end_index]
        sheet.cell(header_row, 3).value = "机型" if header_row == 5 else "料型"
        sheet.cell(header_row + 1, 3).value = "单价/元" if header_row == 5 else "单价/P"
        for offset, (label, price) in enumerate(rows, start=start_column):
            sheet.cell(header_row, offset).value = label
            sheet.cell(header_row + 1, offset).value = price
            sheet.cell(header_row + 1, offset).number_format = (
                "#,##0" if header_row == 5 else "0.0"
            )

    fx = _dict_value(reference_snapshot.get("fx", {}))
    sheet["L3"] = "汇率"
    sheet["L4"] = _float_value(fx.get("rmb_hkd"), 0.85)
    sheet["L4"].number_format = "0.00"
    sheet["M3"] = "人工"
    sheet["M4"] = _float_value(reference_snapshot.get("assembly_labor_base_hkd"), 260)
    sheet["M4"].number_format = "#,##0"
    top_tax_rows = (
        (
            1,
            (
                ("含税1%", _tax_rate(reference_snapshot, "tax_1_percent", 0.0099)),
                ("搪胶类3%", _tax_rate(reference_snapshot, "slush", 0.03)),
                ("车发类5%", _tax_rate(reference_snapshot, "sewing_hair", 0.05)),
                ("车衣类", _tax_rate(reference_snapshot, "sewing_clothes", 0.0)),
            ),
        ),
        (
            3,
            (
                ("吸塑类4%", _tax_rate(reference_snapshot, "blister", 0.04)),
                ("运费含税9%", _tax_rate(reference_snapshot, "freight_tax_9", 0.0826)),
                ("含税13%类", _tax_rate(reference_snapshot, "tax_13_percent", 0.115)),
                ("纸箱类", ""),
            ),
        ),
    )
    for header_row, rows in top_tax_rows:
        for column, (label, value) in enumerate(rows, start=14):
            sheet.cell(header_row, column).value = label
            sheet.cell(header_row + 1, column).value = value
            sheet.cell(header_row + 1, column).number_format = "0.00%"

    paper_factor = _float_value(
        sales_payload.get("paper_price_factor"),
        _float_value(reference_snapshot.get("paper_price_factor"), 2.7),
    )
    flat_card_factor = _float_value(
        sales_payload.get("flat_card_price_factor"),
        _float_value(reference_snapshot.get("carton_b3b_factor"), 1.65),
    )
    for column, (label, value, number_format) in enumerate(
        (
            ("纸箱（B=B）", paper_factor, "0.00"),
            ("纸箱（B3B）", flat_card_factor, "0.00"),
            ("纸箱（B1B）", _float_value(reference_snapshot.get("carton_b1b_factor"), 3.2), "0.00"),
            ("杂项", _float_value(shipping.get("misc_ratio"), 0.02), "0.00%"),
        ),
        start=14,
    ):
        sheet.cell(5, column).value = label
        sheet.cell(6, column).value = value
        sheet.cell(6, column).number_format = number_format
    sheet["R3"] = "港币兑美元"
    sheet["R4"] = _float_value(shipping.get("hkd_usd"), _float_value(fx.get("hkd_usd"), 7.8))
    sheet["R4"].number_format = "0.00"
    sheet["R5"] = "本单MOQ"
    sheet["R6"] = int(active_tier["moq"])
    sheet["R6"].number_format = "#,##0"

    # A7:R7 — product quotation title.
    sheet.merge_cells(
        start_row=7,
        start_column=1,
        end_row=7,
        end_column=outer_right_column,
    )
    title = sheet.cell(7, 1)
    title.value = f"{quote.product_name or quote.quote_no}报价"
    title.font = Font(name="宋体", size=14, bold=False, color=TEMPLATE_BLUE)
    title.alignment = Alignment(horizontal="center", vertical="center")
    title.border = Border(
        left=TEMPLATE_MEDIUM,
        right=TEMPLATE_MEDIUM,
        top=TEMPLATE_MEDIUM,
        bottom=TEMPLATE_MEDIUM,
    )
    sheet.row_dimensions[7].height = 27

    # A8:L — molding/injection detail.  At least six rows are kept so the
    # sparse-product sample remains easy to inspect and can be adjusted later.
    mold_headers = (
        "",
        "",
        "名称",
        "料型",
        "料重(G)",
        "料价(G)",
        "机型",
        "1出几套",
        "目标数",
        "啤工",
        "料金额",
        "报价啤工",
    )
    for column, header in enumerate(mold_headers, start=1):
        _template_cell(
            sheet,
            8,
            column,
            header,
            color=TEMPLATE_RED if column not in {1, 2} else TEMPLATE_BLACK,
            wrap_text=False,
        )
    mold_lines = _calculation_lines(by_code.get("molding"), "injection")
    if not mold_lines:
        mold_lines = _list_of_dicts(
            _section_payload(by_code.get("engineering")).get("molds", [])
        )
    mold_slots = max(6, len(mold_lines))
    mold_start_row = 9
    mold_end_row = mold_start_row + mold_slots - 1
    for index in range(mold_slots):
        row_index = mold_start_row + index
        line = mold_lines[index] if index < len(mold_lines) else {}
        values = (
            index + 1 if line else "",
            "",
            _safe_text(line.get("item") or line.get("chinese_name") or line.get("mold_no") or ""),
            _safe_text(line.get("material") or line.get("material_type") or ""),
            _number(line.get("loss_weight_g", line.get("net_weight_g", ""))),
            _number(line.get("material_price_hkd_g", "")),
            _safe_text(line.get("machine_code") or line.get("machine_name") or ""),
            _number(line.get("sets", line.get("cavity", ""))),
            _number(line.get("target_output", "")),
            _number(line.get("molding_cost_hkd", "")),
            _number(line.get("material_cost_hkd", "")),
            _number(line.get("customer_price_hkd", "")),
        )
        for column, value in enumerate(values, start=1):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                horizontal="left" if column in {2, 3, 4} else "center",
                wrap_text=False,
                number_format=(
                    "0"
                    if column == 1 and value != ""
                    else "0.0000_ "
                    if column in {6, 10, 12}
                    else "0.000_ "
                    if column == 11
                    else None
                ),
                font_name="Times New Roman" if column in {1, 5, 6, 8, 9, 10, 11, 12} else "宋体",
            )
        if line and values[11] == "":
            sheet.cell(row_index, 12).value = f"=J{row_index}*1.15"
            sheet.cell(row_index, 12).number_format = "0.0000_ "
        sheet.row_dimensions[row_index].height = 15
    mold_total_row = mold_end_row + 1
    for column in range(1, 13):
        _template_cell(sheet, mold_total_row, column, "", color=TEMPLATE_RED, wrap_text=False)
    sheet.cell(mold_total_row, 3).value = "模具合计"
    sheet.cell(mold_total_row, 3).font = Font(
        name="宋体",
        size=10,
        bold=True,
        color=TEMPLATE_BLUE,
    )
    for column in (5, 10, 11, 12):
        letter = get_column_letter(column)
        sheet.cell(mold_total_row, column).value = (
            f"=SUM({letter}{mold_start_row}:{letter}{mold_end_row})"
        )
        sheet.cell(mold_total_row, column).number_format = (
            "0.0000_ " if column in {10, 12} else "0.000_ "
        )
    _apply_outline_border(sheet, 8, mold_total_row, 1, 12, TEMPLATE_MEDIUM)

    # A:D — sorted authoritative cost detail.
    detail_rows: list[tuple[str, str, str, float]] = []

    def add_detail(tax_tag: str, category: str, description: str, amount: object) -> None:
        numeric = _float_value(amount)
        if abs(numeric) >= 0.0005:
            detail_rows.append((tax_tag, category, description, numeric))

    molding_material = t1.get("imp_mat", 0.0) + t1.get("dom_mat", 0.0)
    molding_labor = t3.get("injection_labor", 0.0)
    molding_blow = t1.get("blow", 0.0)
    molding_adjustment = (
        _float_value(cost_context.get("molding_hkd"))
        - molding_material
        - molding_labor
        - molding_blow
    )
    painting_labor = t3.get("painting_labor", 0.0)
    paint_material = t3.get("paint_material", 0.0)
    painting_adjustment = (
        _float_value(cost_context.get("painting_hkd"))
        - painting_labor
        - paint_material
    )
    sewing_hair = t1.get("sewing_hair", 0.0)
    sewing_cloth = t1.get("sewing_cloth", 0.0)
    sewing_adjustment = (
        _float_value(cost_context.get("sewing_hkd"))
        - sewing_hair
        - sewing_cloth
    )
    packaging_total = _float_value(cost_context.get("packaging_material_hkd"))
    color_box_amount = min(
        max(t2.get("color_box", 0.0), 0.0),
        max(packaging_total, 0.0),
    )
    packaging_auxiliary = packaging_total - color_box_amount

    add_detail("¥13%", "料价", "料价", molding_material)
    add_detail("", "啤工", "啤工", molding_labor)
    add_detail("", "啤工", "注塑未分类成本", molding_adjustment)
    add_detail("", "装配工", "装工", cost_context.get("assembly_hkd"))
    add_detail("", "装配工", "包装", cost_context.get("packing_labor_hkd"))
    add_detail("", "喷油工", "喷油人工", painting_labor)
    add_detail("", "喷油工", "喷油未分类成本", painting_adjustment)
    add_detail("¥13%", "油漆", "油漆", paint_material)
    add_detail("¥3%", "搪胶", "搪胶", cost_context.get("slush_hkd"))
    add_detail("", "吹气", "吹气", molding_blow)
    add_detail("¥13%", "五金", "五金", cost_context.get("hardware_hkd"))
    add_detail("¥13%", "其他外购", "电子", cost_context.get("electronic_hkd"))
    add_detail("¥13%", "其他外购", "车发", sewing_hair)
    add_detail("¥13%", "其他外购", "车衣", sewing_cloth)
    add_detail("", "其他外购", "车缝未分类成本", sewing_adjustment)
    add_detail("¥13%", "其他外购", "工程辅料/外购", cost_context.get("auxiliary_hkd"))
    add_detail("¥13%", "其他外购", "包装辅材", packaging_auxiliary)
    add_detail("¥13%", "彩盒/内卡", "彩盒/内卡", color_box_amount)
    add_detail("", "纸箱", "纸箱", cost_context.get("carton_hkd"))

    detail_start_row = mold_total_row + 4
    detail_slots = max(1, len(detail_rows))
    detail_data_end_row = detail_start_row + detail_slots - 1
    for index in range(detail_slots):
        row_index = detail_start_row + index
        values = detail_rows[index] if index < len(detail_rows) else ("", "", "", "")
        for column, value in enumerate(values, start=1):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                horizontal="left" if column in {2, 3} else "center",
                wrap_text=False,
                size=11 if column in {2, 4} else 10,
                number_format="0.000" if column == 4 else None,
                border=Border(left=TEMPLATE_MEDIUM) if column == 1 else None,
                font_name="Times New Roman" if column == 1 else "宋体",
            )
        sheet.row_dimensions[row_index].height = 15

    # Adaptive right-side packaging/function/color-box/test blocks.  Short
    # details move these blocks upward; full details retain the reference's
    # seven-row visual offset.
    packaging_offset = min(7, max(0, len(detail_rows) - 8))
    packaging_start_row = detail_start_row + packaging_offset
    cartons = _list_of_dicts(sales_payload.get("cartons", []))
    carton = cartons[0] if cartons else {}
    carton_unit = _dimension_unit(carton.get("size_unit"))
    color_box_unit = _dimension_unit(sales_payload.get("color_box_size_unit"))
    carton_dimensions = tuple(
        _inch_value_for_unit(carton.get(field, ""), carton_unit)
        for field in ("length_in", "width_in", "height_in")
    )
    dimension_columns = [side_start_column + offset for offset in range(1, 4)]
    dimension_letters = [get_column_letter(column) for column in dimension_columns]
    carton_inputs = [
        f"{dimension_letters[index]}{packaging_start_row}"
        + ("/2.54" if carton_unit == "cm" else "")
        for index in range(3)
    ]
    packaging_rows = (
        (f"外箱 ({carton_unit}):", *carton_dimensions),
        (
            f"彩盒尺寸 ({color_box_unit})",
            *_dimensions_for_unit(
                sales_payload.get("color_box_size_in")
                or sales_payload.get("color_box_size_cm"),
                color_box_unit,
            ),
        ),
        (
            "产品尺寸 (in)",
            *_dimensions(
                sales_payload.get("product_size_in")
                or sales_payload.get("product_size_cm")
            ),
        ),
        (
            "CUFT:",
            f"={carton_inputs[0]}*{carton_inputs[1]}*{carton_inputs[2]}/1728",
            "",
            "",
        ),
        (
            "纸板价",
            f"={carton_inputs[0]}*{carton_inputs[1]}*3.5/1000",
            "",
            "",
        ),
        (
            "箱价：",
            f"=({carton_inputs[0]}+{carton_inputs[1]}+2)"
            f"*({carton_inputs[1]}+{carton_inputs[2]}+1)*$N$6*2/1000",
            "",
            "",
        ),
        ("装箱：", _number(carton.get("qty_per_carton", "")), "PCS/1CTN", ""),
        (
            "合计",
            f"=IFERROR({dimension_letters[0]}{packaging_start_row + 5}"
            f"/{dimension_letters[0]}{packaging_start_row + 6},0)",
            "",
            "",
        ),
    )
    for offset, values in enumerate(packaging_rows):
        row_index = packaging_start_row + offset
        for column, value in enumerate(values, start=side_start_column):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_BLUE if column == side_start_column and offset == 7 else TEMPLATE_BLACK,
                horizontal="left" if column in {side_start_column, side_start_column + 1} and offset >= 3 else "center",
                wrap_text=False,
                size=11 if column in dimension_columns and offset < 3 else 10,
                number_format=(
                    "0.000_ "
                    if column == side_start_column + 1 and offset in {3, 4, 5, 7}
                    else None
                ),
                font_name="Times New Roman" if column in dimension_columns and offset < 3 else "宋体",
            )

    function_start_row = packaging_start_row + len(packaging_rows) + 1
    function_end_row = function_start_row + 7
    _template_style_range(
        sheet,
        function_start_row,
        function_end_row,
        side_start_column,
        side_end_column,
    )
    sheet.merge_cells(
        start_row=function_start_row,
        start_column=side_start_column,
        end_row=function_end_row,
        end_column=side_end_column,
    )
    function_cell = sheet.cell(function_start_row, side_start_column)
    function_cell.value = f"功能介绍：{quote.remark or ''}"
    function_cell.font = Font(name="宋体", size=12, color=TEMPLATE_RED)
    function_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
        wrap_text=True,
    )
    function_cell.border = TEMPLATE_BORDER

    color_box = _dict_value(
        _dict_value(sales_payload.get("customer_quote_fields", {})).get("buzzbee", {})
    )
    color_tiers = _list_of_dicts(color_box.get("color_box_tiers", []))[:2]
    # Match the reference template: keep one completely blank row between
    # the function-introduction box and the color-box quotation block.
    color_title_row = function_end_row + 2
    sheet.merge_cells(
        start_row=color_title_row,
        start_column=side_start_column,
        end_row=color_title_row,
        end_column=side_start_column + 2,
    )
    _template_cell(
        sheet,
        color_title_row,
        side_start_column,
        "彩盒价格",
        wrap_text=False,
    )
    color_header_row = color_title_row + 1
    for column, label in enumerate(
        ("报客彩盒", "报客彩盒FSC", "MOQ数量"),
        start=side_start_column,
    ):
        _template_cell(sheet, color_header_row, column, label, wrap_text=False)
    for offset in range(2):
        row_index = color_header_row + 1 + offset
        tier = color_tiers[offset] if offset < len(color_tiers) else {}
        for column, value in enumerate(
            (
                _number(tier.get("quote_price_hkd", "")),
                _number(tier.get("fsc_price_hkd", "")),
                _safe_text(tier.get("moq", "")),
            ),
            start=side_start_column,
        ):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_RED,
                wrap_text=False,
                number_format=(
                    "0.00_);[Red]\\(0.00\\)"
                    if column in {side_start_column, side_start_column + 1}
                    else None
                ),
            )
    color_end_row = color_header_row + 2

    testing_display_rows = testing_fee_tiers or [
        {"moq": int(tier["moq"]), "unit_price_usd": 0.0}
        for tier in markup_tiers
    ]
    test_header_row = color_end_row + 3
    _template_cell(
        sheet,
        test_header_row,
        side_start_column,
        "测试费用",
        wrap_text=False,
    )
    _template_cell(
        sheet,
        test_header_row,
        side_start_column + 1,
        testing_fee_total_usd,
        wrap_text=False,
        number_format='"US$"#,##0.00',
    )
    _template_cell(
        sheet,
        test_header_row,
        side_start_column + 2,
        "",
        wrap_text=False,
    )

    misc_row = detail_data_end_row + 1
    for column, value in enumerate(
        (
            "",
            "杂项",
            "杂项",
            _float_value(cost_context.get("indonesia_freight_hkd"))
            + _float_value(shipping.get("additional_tax_hkd")),
        ),
        start=1,
    ):
        _template_cell(
            sheet,
            misc_row,
            column,
            value,
            horizontal="left" if column in {2, 3} else "center",
            wrap_text=False,
            number_format="0.000" if column == 4 else None,
            border=Border(left=TEMPLATE_MEDIUM) if column == 1 else None,
        )
    for offset, route in enumerate(route_rows):
        _template_cell(
            sheet,
            misc_row,
            route_start_column + offset,
            _safe_text(route.get("name") or route.get("item") or f"运输方案{offset + 1}"),
            wrap_text=False,
            border=None,
        )
    freight_row = misc_row + 1
    lifting_row = misc_row + 2
    for row_index, label, value_key in (
        (freight_row, "运费", "freight_hkd"),
        (lifting_row, "吊柜费", "lift_hkd"),
    ):
        _template_cell(
            sheet,
            row_index,
            2,
            label,
            horizontal="left",
            wrap_text=False,
            border=Border(left=TEMPLATE_MEDIUM),
        )
        _template_cell(
            sheet,
            row_index,
            3,
            label,
            horizontal="left",
            wrap_text=False,
            border=None,
        )
        _template_cell(sheet, row_index, 4, "", border=None)
        for offset, route in enumerate(route_rows):
            _template_cell(
                sheet,
                row_index,
                route_start_column + offset,
                _number(route.get(value_key, "")),
                wrap_text=False,
                number_format="0.00",
                border=None,
            )

    subtotal_row = lifting_row + 1
    price_columns = [4, *range(route_start_column, route_end_column + 1)]
    for column in price_columns:
        _template_cell(
            sheet,
            subtotal_row,
            column,
            "",
            bold=True,
            wrap_text=False,
            number_format="0.00",
            border=Border(bottom=TEMPLATE_THIN),
        )
    sheet.cell(subtotal_row, 4).value = f"=SUM(D{detail_start_row}:D{misc_row})"
    for column in range(route_start_column, route_end_column + 1):
        letter = get_column_letter(column)
        sheet.cell(subtotal_row, column).value = (
            f"=$D${subtotal_row}+{letter}{freight_row}+{letter}{lifting_row}"
        )

    settlement = _float_value(shipping.get("settlement"), 0.98)
    pricing_rows: list[dict[str, int | float]] = []
    pricing_start_row = subtotal_row + 1
    for index, tier in enumerate(markup_tiers):
        markup_row = pricing_start_row + index * 6
        settlement_row = markup_row + 1
        quote_row = markup_row + 2
        usd_row = markup_row + 3
        included_row = markup_row + 4
        pricing_rows.append(
            {
                "moq": int(tier["moq"]),
                "markup": float(tier["markup"]),
                "markup_row": markup_row,
                "settlement_row": settlement_row,
                "quote_row": quote_row,
                "usd_row": usd_row,
                "included_row": included_row,
            }
        )
        _template_cell(sheet, markup_row, 3, "×", border=None, horizontal="right")
        _template_cell(sheet, settlement_row, 3, "÷", border=None, horizontal="right")
        _template_cell(
            sheet,
            quote_row,
            2,
            f"报价（{_moq_label(tier['moq'])}）",
            horizontal="left",
            wrap_text=False,
            border=Border(bottom=TEMPLATE_THIN),
        )
        _template_cell(
            sheet,
            included_row,
            2,
            "包含测试费用（US）：",
            horizontal="left",
            wrap_text=False,
            border=None,
        )
        for column in price_columns:
            letter = get_column_letter(column)
            _template_cell(
                sheet,
                markup_row,
                column,
                float(tier["markup"]),
                wrap_text=False,
                number_format="0.00",
                border=None,
            )
            _template_cell(
                sheet,
                settlement_row,
                column,
                settlement,
                wrap_text=False,
                number_format="0.00",
                border=Border(bottom=TEMPLATE_THIN),
            )
            _template_cell(
                sheet,
                quote_row,
                column,
                f"={letter}{subtotal_row}*{letter}{markup_row}/{letter}{settlement_row}",
                bold=True,
                wrap_text=False,
                number_format="0.00",
                border=Border(bottom=TEMPLATE_THIN),
            )
            _template_cell(
                sheet,
                usd_row,
                column,
                f"={letter}{quote_row}/$R$4",
                bold=True,
                wrap_text=False,
                number_format="0.00",
                border=None,
            )
            _template_cell(
                sheet,
                included_row,
                column,
                f"={letter}{usd_row}",
                bold=True,
                wrap_text=False,
                number_format="0.00",
                border=None,
            )
    pricing_end_row = pricing_rows[-1]["included_row"]
    pricing_by_moq = {int(row["moq"]): row for row in pricing_rows}
    active_pricing = pricing_by_moq.get(int(active_tier["moq"]), pricing_rows[-1])

    test_adjusted_cells: dict[int, str] = {}
    for offset, test_tier in enumerate(testing_display_rows, start=1):
        row_index = test_header_row + offset
        moq = int(test_tier["moq"])
        _template_cell(
            sheet,
            row_index,
            side_start_column,
            moq,
            wrap_text=False,
            number_format="#,##0",
        )
        _template_cell(
            sheet,
            row_index,
            side_start_column + 1,
            _float_value(test_tier.get("unit_price_usd")),
            wrap_text=False,
            number_format='"US$"0.00',
        )
        pricing = pricing_by_moq.get(moq)
        if pricing is not None:
            adjusted_formula = (
                f"={get_column_letter(side_start_column + 1)}{row_index}"
                f"*D{pricing['markup_row']}"
            )
        else:
            adjusted_formula = (
                f"={get_column_letter(side_start_column + 1)}{row_index}"
                f"*D{active_pricing['markup_row']}"
            )
        _template_cell(
            sheet,
            row_index,
            side_start_column + 2,
            adjusted_formula,
            wrap_text=False,
            number_format='"US$"0.00',
        )
        test_adjusted_cells[moq] = (
            f"${get_column_letter(side_start_column + 2)}${row_index}"
        )
    test_end_row = test_header_row + len(testing_display_rows)
    for pricing in pricing_rows:
        adjusted_reference = test_adjusted_cells.get(int(pricing["moq"]))
        if adjusted_reference is None:
            continue
        for column in price_columns:
            letter = get_column_letter(column)
            sheet.cell(int(pricing["included_row"]), column).value = (
                f"={letter}{pricing['usd_row']}+{adjusted_reference}"
            )

    # C:P — formula-driven summary, anchored below whichever of the adaptive
    # left/right regions is longer.
    summary_start_row = max(
        int(pricing_end_row),
        test_end_row,
        color_end_row,
        function_end_row,
    ) + 2
    amount_format = "0.00_);[Red]\\(0.00\\)"
    detail_category_range = f"$B${detail_start_row}:$B${misc_row}"
    detail_description_range = f"$C${detail_start_row}:$C${misc_row}"
    detail_amount_range = f"$D${detail_start_row}:$D${misc_row}"

    def sum_category(label_cell: str) -> str:
        return f"=SUMIF({detail_category_range},{label_cell},{detail_amount_range})"

    def sum_description(description: str) -> str:
        return f'=SUMIF({detail_description_range},"{description}",{detail_amount_range})'

    def sum_category_or_authoritative(label_cell: str, fallback: object) -> str:
        fallback_value = format(_float_value(fallback), ".10g")
        return (
            f"=IF(COUNTIF({detail_category_range},{label_cell})>0,"
            f"SUMIF({detail_category_range},{label_cell},{detail_amount_range}),{fallback_value})"
        )

    def style_summary_pair(
        header_row: int,
        headers: list[object],
        values: list[object],
        *,
        first_header_fill: str | None = None,
    ) -> None:
        for column in range(3, 17):
            index = column - 3
            header = headers[index] if index < len(headers) else ""
            value = values[index] if index < len(values) else ""
            fill = None
            if column == 3:
                fill = first_header_fill
            elif column <= 14:
                fill = "FFFF00"
            _template_cell(
                sheet,
                header_row,
                column,
                header,
                bold=column == 4,
                color=TEMPLATE_BLACK,
                fill=fill,
                size=10,
                wrap_text=False,
                number_format=amount_format,
            )
            _template_cell(
                sheet,
                header_row + 1,
                column,
                value,
                bold=column == 4,
                color=TEMPLATE_BLACK,
                size=10,
                wrap_text=False,
                number_format=amount_format,
            )

    first_header_row = summary_start_row
    first_value_row = first_header_row + 1
    style_summary_pair(
        first_header_row,
        ["旺季价", "货价", "料价", "吹气", "搪胶", "车发", "车衣", "五金", "电子", "马达", "吸塑", "彩盒/内卡"],
        [
            "按出厂货价核",
            f"=D{active_pricing['quote_row']}",
            sum_category(f"E{first_header_row}"),
            sum_category(f"F{first_header_row}"),
            sum_category(f"G{first_header_row}"),
            sum_description("车发"),
            sum_description("车衣"),
            sum_category(f"J{first_header_row}"),
            sum_description("电子"),
            t1.get("motor", 0.0),
            t1.get("suction", 0.0),
            sum_category(f"N{first_header_row}"),
        ],
        first_header_fill="FFC000",
    )

    second_header_row = summary_start_row + 3
    second_value_row = second_header_row + 1
    third_header_row = summary_start_row + 6
    third_value_row = third_header_row + 1
    tax_header_row = summary_start_row + 9
    deduction_row = tax_header_row + 3
    style_summary_pair(
        second_header_row,
        ["ABS料价成本", "未减税前码数", "减税后码数", "电池", "利宝/说明书", "电镀", "其他外购", "纸箱", "运费", "吊柜费", "杂项", "不含人工成本"],
        [
            f'=SUMIF($D${mold_start_row}:$D${mold_end_row},"*ABS*",$K${mold_start_row}:$K${mold_end_row})',
            f"=IFERROR(D{first_value_row}/N{third_value_row},0)",
            f"=IFERROR(D{first_value_row}/P{deduction_row},0)",
            sum_category_or_authoritative(f"F{second_header_row}", t2.get("battery", 0.0)),
            sum_category_or_authoritative(f"G{second_header_row}", t2.get("libao", 0.0)),
            t2.get("plating", 0.0),
            t2.get("other_buy", 0.0),
            sum_category(f"J{second_header_row}"),
            0.0,
            0.0,
            f"=D{first_value_row}*$Q$6",
            f"=SUM(E{first_value_row}:N{first_value_row},F{second_value_row}:M{second_value_row},G{third_value_row})",
        ],
    )
    sheet.cell(second_header_row, 3).fill = PatternFill(fill_type=None)
    sheet.cell(second_header_row, 4).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_BLUE)
    sheet.cell(second_header_row, 5).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_RED)
    sheet.cell(second_value_row, 4).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_BLUE)
    sheet.cell(second_value_row, 5).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_RED)

    style_summary_pair(
        third_header_row,
        ["ABS占货价%", "", "啤工", "喷油工", "油漆", "装配工", "人工比例", "毛利", "毛利率", "利润", "利润率", "总成本"],
        [
            f"=IFERROR(C{second_value_row}/D{first_value_row},0)",
            "",
            sum_category(f"E{third_header_row}"),
            sum_category(f"F{third_header_row}"),
            sum_category(f"G{third_header_row}"),
            sum_category(f"H{third_header_row}"),
            f"=IFERROR((E{third_value_row}+F{third_value_row}+H{third_value_row})/D{first_value_row},0)",
            f"=D{first_value_row}-N{second_value_row}",
            f"=IFERROR(J{third_value_row}/D{first_value_row},0)",
            f"=D{first_value_row}-N{third_value_row}",
            f"=IFERROR(L{third_value_row}/D{first_value_row},0)",
            f"=N{second_value_row}+E{third_value_row}+F{third_value_row}+H{third_value_row}",
            f"=D{subtotal_row}+M{second_value_row}",
        ],
    )
    sheet.cell(third_header_row, 3).fill = PatternFill(fill_type=None)
    sheet.cell(third_value_row, 3).number_format = "0.0%"
    for column in (9, 11, 13):
        sheet.cell(third_value_row, column).number_format = "0.0%"
    sheet.cell(third_header_row, 14).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_BLUE)
    sheet.cell(third_value_row, 14).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_BLUE)

    tax_keys = (
        "tax1",
        "slush3",
        "sewhair13",
        "sewcloth13",
        "suction6",
        "freight9",
        "tax13b",
        "carton",
        "labor13",
    )
    tax_headers = ["人民币外购件成本", "含税13%类成本", ""] + [
        _safe_text(t4.get(key, {}).get("label", "")) for key in tax_keys
    ]
    for column in range(3, 17):
        value = tax_headers[column - 3] if column - 3 < len(tax_headers) else ""
        _template_cell(
            sheet,
            tax_header_row,
            column,
            value,
            color=TEMPLATE_BLACK,
            fill=TEMPLATE_SKY if 6 <= column <= 14 else None,
            size=10,
            wrap_text=False,
        )

    tax_amount_row = tax_header_row + 1
    domestic_material_literal = format(_float_value(t1.get("dom_mat", 0.0)), ".10g")
    glue_bag_literal = format(_float_value(t1.get("glue_bag", 0.0)), ".10g")
    rmb_purchase_formula = (
        f"=SUM({domestic_material_literal},H{first_value_row},I{first_value_row},"
        f"J{first_value_row},K{first_value_row},L{first_value_row},N{first_value_row},"
        f"F{second_value_row},G{second_value_row},H{second_value_row},I{second_value_row},"
        f"J{second_value_row},M{second_value_row},G{third_value_row},{glue_bag_literal})"
    )
    tax_13_formula = (
        f"=SUM({domestic_material_literal},J{first_value_row},L{first_value_row},"
        f"N{first_value_row},F{second_value_row},G{second_value_row},I{second_value_row},"
        f"G{third_value_row},{glue_bag_literal})"
    )
    for column in range(3, 17):
        if column == 3:
            value: object = rmb_purchase_formula
            number_format = amount_format
        elif column == 4:
            value = tax_13_formula
            number_format = amount_format
        elif column == 5:
            value = ""
            number_format = amount_format
        elif 6 <= column <= 14:
            key = tax_keys[column - 6]
            rate_percent = t4.get(key, {}).get("rate_percent")
            value = (
                ""
                if key == "carton"
                else _percent_fraction(rate_percent)
            )
            number_format = "0.00%"
        elif column == 15:
            value = "合计减税"
            number_format = amount_format
        else:
            value = "减税后成本"
            number_format = amount_format
        _template_cell(
            sheet,
            tax_amount_row,
            column,
            value,
            bold=column in {15, 16},
            color=TEMPLATE_RED if column in {15, 16} else TEMPLATE_BLACK,
            fill=TEMPLATE_SKY if 6 <= column <= 14 else None,
            size=9 if column in {15, 16} else 10,
            wrap_text=False,
            number_format=number_format,
        )

    for column in range(3, 17):
        _template_cell(
            sheet,
            deduction_row,
            column,
            "",
            bold=column in {15, 16},
            color=TEMPLATE_RED if column in {15, 16} else TEMPLATE_BLACK,
            fill=TEMPLATE_SKY if 6 <= column <= 14 else None,
            size=9 if column in {15, 16} else 10,
            wrap_text=False,
            number_format=amount_format,
        )
    tax_amount_references = {
        "tax1": f"H{second_value_row}",
        "slush3": f"G{first_value_row}",
        "sewhair13": f"H{first_value_row}",
        "sewcloth13": f"I{first_value_row}",
        "suction6": f"M{first_value_row}",
        "freight9": f"K{second_value_row}",
        "tax13b": f"D{tax_amount_row}",
        "carton": f"J{second_value_row}",
        "labor13": f"SUM(E{third_value_row}:F{third_value_row},H{third_value_row})",
    }
    for column, key in enumerate(tax_keys, start=6):
        if key == "carton":
            sheet.cell(deduction_row, column).value = ""
        else:
            amount_reference = tax_amount_references[key]
            sheet.cell(deduction_row, column).value = (
                f"={amount_reference}*{get_column_letter(column)}{tax_amount_row}"
            )
    sheet.cell(deduction_row, 15).value = f"=SUM(F{deduction_row}:N{deduction_row})"
    sheet.cell(deduction_row, 16).value = f"=N{third_value_row}-O{deduction_row}"

    # Workbook presentation/printing settings.
    widths = {
        "A": 3.5833333333,
        "B": 7.5,
        "C": 26.5,
        "D": 10.3333333333,
        "E": 12.625,
        "F": 16.75,
        "G": 13,
        "H": 13,
        "I": 13,
        "J": 13,
        "K": 11.0833333333,
        "L": 13,
        "M": 13,
        "N": 10.3333333333,
        "O": 8.25,
        "P": 13,
        "Q": 13,
        "R": 13,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for column in range(19, outer_right_column + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 13
    for row in range(summary_start_row, deduction_row + 1):
        sheet.row_dimensions[row].height = 15
    for row in (summary_start_row + 2, summary_start_row + 5, summary_start_row + 8):
        sheet.row_dimensions[row].height = 7
    sheet.row_dimensions[tax_header_row + 2].height = 6
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    sheet.freeze_panes = "A8"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins.left = 0.2
    sheet.page_margins.right = 0.2
    sheet.page_margins.top = 0.35
    sheet.page_margins.bottom = 0.35
    _apply_outline_border(
        sheet,
        1,
        deduction_row,
        1,
        outer_right_column,
        TEMPLATE_MEDIUM,
    )
    _apply_outline_border(
        sheet,
        7,
        7,
        1,
        outer_right_column,
        TEMPLATE_MEDIUM,
    )
    sheet.print_area = (
        f"A1:{get_column_letter(outer_right_column)}{deduction_row}"
    )
    sheet.sheet_properties.outlinePr.summaryBelow = True


def _walk_components(rows: list[dict[str, Any]], parent: str = ""):
    for row in rows:
        if not isinstance(row, dict):
            continue
        yield parent, row
        children = row.get("children", [])
        if isinstance(children, list):
            yield from _walk_components(children, str(row.get("item", "")))


def _build_electronic_sheet(
    workbook: Workbook,
    section: InternalQuoteSection | None,
    reference_snapshot: dict[str, Any],
) -> None:
    sheet = workbook.create_sheet("电子明细")
    _style_title(sheet, "电子报价明细", 10)
    _header_row(sheet, 3, ("父项", "零件名称", "规格", "用量", "单价RMB", "单价HKD", "金额HKD", "税点%", "备注", "来源"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    fx_value = _number(reference_snapshot.get("fx", {}).get("rmb_hkd"))
    fx = fx_value if isinstance(fx_value, float) and fx_value > 0 else 0.85
    components = payload.get("components", [])
    for parent, row in _walk_components(components if isinstance(components, list) else []):
        quantity = _number(row.get("quantity"))
        unit_price_rmb = _number(row.get("unit_price_rmb"))
        unit_price_hkd = _number(row.get("unit_price_hkd"))
        if not isinstance(unit_price_rmb, float) and isinstance(unit_price_hkd, float):
            unit_price_rmb = unit_price_hkd * fx
        if not isinstance(unit_price_hkd, float) and isinstance(unit_price_rmb, float):
            unit_price_hkd = unit_price_rmb / fx
        amount_hkd = quantity * unit_price_hkd if isinstance(quantity, float) and isinstance(unit_price_hkd, float) else ""
        _body_row(
            sheet,
            row_index,
            (
                _safe_text(parent),
                _safe_text(row.get("item", "")),
                _safe_text(row.get("specification", "")),
                quantity,
                unit_price_rmb,
                unit_price_hkd,
                amount_hkd,
                _number(row.get("tax_rate_percent")),
                _safe_text(row.get("remark", row.get("note", ""))),
                _safe_text(f"{row.get('source_currency', '')} row {row.get('source_row', '')}"),
            ),
            amount_columns={5, 6, 7, 8},
        )
        row_index += 1
    calculation = _json_object(section.calculation_json) if section else {}
    totals = calculation.get("totals", {}) if isinstance(calculation.get("totals", {}), dict) else {}
    row_index += 1
    _header_row(sheet, row_index, ("电子成本汇总", "RMB", "HKD", "公式口径"))
    row_index += 1
    for label, rmb_key, hkd_key, formula in (
        ("零件成本", "component_rmb", "component_hkd", "用量 × 单价"),
        ("成本合计（不含税）", "pre_tax_rmb", "pre_tax_hkd", "零件 + 邦定/贴片/人工/测试/包装"),
        ("含利润价", "with_profit_rmb", "with_profit_hkd", "不含税成本 × (1 + 利润率)"),
        ("抵税差额", "tax_credit_difference_rmb", "tax_credit_difference_hkd", "含利润价 × 13% - 零件进项抵扣"),
        ("应交税负", "tax_payable_rmb", "tax_payable_hkd", "抵税差额 × 10%"),
        ("含税报价", "total_rmb", "total_hkd", "含利润价 + 抵税差额 + 应交税负"),
    ):
        _body_row(sheet, row_index, (label, _number(totals.get(rmb_key)), _number(totals.get(hkd_key)), formula), amount_columns={2, 3})
        row_index += 1
    _finish_sheet(sheet, (20, 28, 28, 12, 15, 15, 15, 12, 28, 20))


def _build_sewing_sheet(workbook: Workbook, section: InternalQuoteSection | None) -> None:
    sheet = workbook.create_sheet("车缝明细")
    _style_title(sheet, "车缝报价明细", 14)
    _header_row(sheet, 3, ("产品组", "类型", "#", "布料名称", "部位", "工艺", "裁片数", "用量/码", "物料价(RMB)", "价钱(RMB)", "码点", "总价钱(RMB)", "备注", "来源行"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    for group in payload.get("groups", []) if isinstance(payload.get("groups", []), list) else []:
        if not isinstance(group, dict):
            continue
        for item_index, row in enumerate(group.get("materials", []) if isinstance(group.get("materials", []), list) else [], start=1):
            if not isinstance(row, dict):
                continue
            usage = _number(row.get("usage"))
            unit_price = _number(row.get("unit_price_rmb"))
            markup = _number(row.get("markup")) or 1
            _body_row(
                sheet,
                row_index,
                (
                    _safe_text(group.get("name", "")),
                    _safe_text(group.get("category", "")),
                    item_index,
                    _safe_text(row.get("item", "")),
                    _safe_text(row.get("part", "")),
                    _safe_text(row.get("craft", "")),
                    _number(row.get("pieces")),
                    usage,
                    unit_price,
                    usage * unit_price,
                    markup,
                    usage * unit_price * markup,
                    _safe_text(row.get("remark") or row.get("note") or ""),
                    row.get("source_row", ""),
                ),
                amount_columns={8, 9, 10, 11, 12},
            )
            sheet.cell(row_index, 10).value = f"=H{row_index}*I{row_index}"
            sheet.cell(row_index, 10).number_format = "#,##0.0000"
            sheet.cell(row_index, 12).value = f"=J{row_index}*K{row_index}"
            sheet.cell(row_index, 12).number_format = "#,##0.0000"
            row_index += 1
    _finish_sheet(sheet, (24, 12, 7, 30, 16, 12, 12, 14, 16, 16, 12, 18, 30, 12))


def _build_assembly_sheet(workbook: Workbook, section: InternalQuoteSection | None) -> None:
    sheet = workbook.create_sheet("装配明细")
    _style_title(sheet, "装配排拉工序明细", 8)
    _header_row(sheet, 3, ("产品组", "分类", "工序", "人数", "小组数", "生产量", "备注", "来源行"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    for group in payload.get("groups", []) if isinstance(payload.get("groups", []), list) else []:
        if not isinstance(group, dict):
            continue
        for process in group.get("processes", []) if isinstance(group.get("processes", []), list) else []:
            if not isinstance(process, dict):
                continue
            _body_row(
                sheet,
                row_index,
                (
                    _safe_text(group.get("name", "")),
                    _safe_text(group.get("category", "")),
                    _safe_text(process.get("name", "")),
                    _number(process.get("persons")),
                    _number(process.get("teams")),
                    _number(process.get("production_qty")),
                    _safe_text(process.get("note", "")),
                    process.get("source_row", ""),
                ),
            )
            row_index += 1
    _finish_sheet(sheet, (24, 14, 30, 12, 12, 15, 32, 12))


def _build_structured_data_sheet(
    workbook: Workbook,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    reference_snapshot: dict[str, Any],
) -> None:
    sheet = workbook.create_sheet("结构化数据")
    _style_title(sheet, "P4 客价转换结构化数据", 12)
    _body_row(
        sheet,
        2,
        (
            "结构版本",
            STRUCTURED_DATA_SCHEMA_VERSION,
            "说明",
            "按记录类型、分段和分片序号重组 JSON；禁止从展示明细反推原始参数",
        ),
    )
    _header_row(
        sheet,
        3,
        (
            "记录类型",
            "分段代码",
            "分段名称",
            "状态",
            "revision",
            "计算状态",
            "依赖状态",
            "计算hash",
            "分片序号",
            "分片总数",
            "JSON分片",
            "是否参与",
        ),
    )
    row_index = 4
    snapshot_chunks = _json_chunks(reference_snapshot)
    for chunk_index, chunk in enumerate(snapshot_chunks, start=1):
        _body_row(
            sheet,
            row_index,
            (
                "reference_snapshot",
                "quote",
                "报价参考快照",
                "frozen",
                quote.header_revision,
                "valid",
                "current",
                quote.reference_snapshot_id,
                chunk_index,
                len(snapshot_chunks),
                chunk,
                "是",
            ),
            text_columns={11},
        )
        row_index += 1
    by_code = {section.department: section for section in sections}
    for code in SECTION_ORDER:
        section = by_code.get(code)
        if section is None:
            continue
        records = (
            ("payload", _json_object(section.payload_json)),
            ("calculation", _json_object(section.calculation_json)),
        )
        for record_type, value in records:
            chunks = _json_chunks(value)
            for chunk_index, chunk in enumerate(chunks, start=1):
                _body_row(
                    sheet,
                    row_index,
                    (
                        record_type,
                        section.department,
                        _safe_text(section.department_name),
                        section.status,
                        section.revision,
                        section.calculation_status,
                        section.dependency_status,
                        section.calculation_hash,
                        chunk_index,
                        len(chunks),
                        chunk,
                        "是" if section.is_required else "否",
                    ),
                    text_columns={11},
                )
                row_index += 1
    _finish_sheet(sheet, (16, 16, 20, 18, 10, 16, 16, 66, 10, 10, 76, 12))


def _build_approval_sheet(
    workbook: Workbook,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    manifest: dict[str, Any],
) -> None:
    sheet = workbook.create_sheet("审批与版本")
    _style_title(sheet, "审批、公式与版本清单", 8)
    is_final_release = manifest.get("release_stage") == "p4_final_approved"
    template_version = str(manifest.get("template_version") or P3_TEMPLATE_VERSION)
    release_label = "P4 最终业务放行" if is_final_release else "P3 分段审批后内部成本快照"
    boundary_label = (
        "最终业务放行完成，可交接客价转换台"
        if is_final_release
        else "最终业务放行与客价交接在 P4 实施"
    )
    summary = (
        ("模板版本", template_version, "公式版本", quote.formula_version),
        ("参考快照", quote.reference_snapshot_id, "报价头revision", quote.header_revision),
        ("导出阶段", release_label, "清单SHA-256", manifest.get("manifest_sha256", "")),
        ("边界说明", boundary_label, "", ""),
        (
            "最终提交人",
            manifest.get("final_submitted_by_name", ""),
            "最终放行人/时间",
            f"{manifest.get('final_reviewed_by_name', '')} {manifest.get('final_reviewed_at', '')}".strip(),
        ),
    )
    for row_index, values in enumerate(summary, start=2):
        _body_row(sheet, row_index, (_safe_text(value) for value in values))
    _header_row(sheet, 7, ("分段", "是否必需", "状态", "revision", "计算状态", "依赖状态", "审核人", "审核时间"))
    row_index = 8
    by_code = {section.department: section for section in sections}
    for code in SECTION_ORDER:
        section = by_code.get(code)
        if section is None:
            continue
        _body_row(
            sheet,
            row_index,
            (
                _safe_text(section.department_name),
                "是" if section.is_required else "否",
                section.status,
                section.revision,
                section.calculation_status,
                section.dependency_status,
                _safe_text(section.reviewed_by),
                section.reviewed_at,
            ),
        )
        row_index += 1
    row_index += 1
    _header_row(sheet, row_index, ("清单字段", "值"))
    row_index += 1
    for key, value in manifest.items():
        _body_row(sheet, row_index, (_safe_text(key), _safe_text(_json_text(value) if isinstance(value, (dict, list)) else value)))
        row_index += 1
    _finish_sheet(sheet, (24, 24, 20, 16, 18, 18, 20, 22))


def _unique_sheet_title(raw_title: str, used_titles: set[str]) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\\x00-\x1f]", " ", raw_title).strip().strip("'")
    cleaned = re.sub(r"\s+", " ", cleaned) or "上传表格"
    base = cleaned[:31]
    candidate = base
    suffix = 2
    while candidate.casefold() in used_titles:
        marker = f"-{suffix}"
        candidate = f"{base[:31 - len(marker)]}{marker}"
        suffix += 1
    used_titles.add(candidate.casefold())
    return candidate


def _rewrite_attachment_formula(
    formula: object,
    sheet_names: dict[str, str],
) -> object:
    if not isinstance(formula, str) or not formula.startswith("="):
        return formula
    rendered = formula
    for old_name, new_name in sheet_names.items():
        if old_name == new_name:
            continue
        old_quoted = f"{quote_sheetname(old_name)}!"
        new_quoted = f"{quote_sheetname(new_name)}!"
        rendered = rendered.replace(old_quoted, new_quoted)
        rendered = rendered.replace(f"{old_name}!", new_quoted)
    return rendered


def _copy_attachment_worksheet(
    source,
    target,
    sheet_names: dict[str, str],
) -> None:
    for row in source.iter_rows():
        for source_cell in row:
            target_cell = target.cell(source_cell.row, source_cell.column)
            target_cell.value = _rewrite_attachment_formula(
                source_cell.value,
                sheet_names,
            )
            if source_cell.has_style:
                # Style-array indexes are workbook-local.  Copy the concrete
                # objects so openpyxl registers them in the destination book.
                target_cell.font = copy(source_cell.font)
                target_cell.fill = copy(source_cell.fill)
                target_cell.border = copy(source_cell.border)
                target_cell.alignment = copy(source_cell.alignment)
                target_cell.protection = copy(source_cell.protection)
                target_cell.number_format = source_cell.number_format
            if source_cell.hyperlink is not None:
                target_cell._hyperlink = copy(source_cell.hyperlink)
            if source_cell.comment is not None:
                target_cell.comment = copy(source_cell.comment)

    for merged_range in source.merged_cells.ranges:
        target.merge_cells(str(merged_range))
    for index, dimension in source.row_dimensions.items():
        target_dimension = target.row_dimensions[index]
        target_dimension.height = dimension.height
        target_dimension.hidden = dimension.hidden
        target_dimension.outlineLevel = dimension.outlineLevel
        target_dimension.collapsed = dimension.collapsed
    for index, dimension in source.column_dimensions.items():
        target_dimension = target.column_dimensions[index]
        target_dimension.width = dimension.width
        target_dimension.hidden = dimension.hidden
        target_dimension.bestFit = dimension.bestFit
        target_dimension.outlineLevel = dimension.outlineLevel
        target_dimension.collapsed = dimension.collapsed

    target.freeze_panes = source.freeze_panes
    target.sheet_view.showGridLines = source.sheet_view.showGridLines
    target.sheet_view.zoomScale = source.sheet_view.zoomScale
    target.sheet_format.defaultRowHeight = source.sheet_format.defaultRowHeight
    target.sheet_format.defaultColWidth = source.sheet_format.defaultColWidth
    target.page_margins = copy(source.page_margins)
    target.page_setup = copy(source.page_setup)
    target.print_options = copy(source.print_options)
    target.sheet_properties = copy(source.sheet_properties)
    target.auto_filter.ref = source.auto_filter.ref
    target.data_validations = copy(source.data_validations)
    target.conditional_formatting = copy(source.conditional_formatting)

    for image in getattr(source, "_images", []):
        try:
            copied_image = copy(image)
            copied_image.anchor = copy(image.anchor)
            target.add_image(copied_image)
        except Exception:
            # Cell values and styles remain authoritative even when a source
            # drawing uses a format that openpyxl cannot clone across books.
            continue
    for chart in getattr(source, "_charts", []):
        try:
            copied_chart = copy(chart)
            copied_chart.anchor = copy(chart.anchor)
            target.add_chart(copied_chart)
        except Exception:
            continue


def _append_spreadsheet_attachment_sheets(
    workbook: Workbook,
    attachments: list[InternalQuoteAttachment],
) -> list[str]:
    appended_titles: list[str] = []
    used_titles = {sheet.title.casefold() for sheet in workbook.worksheets}
    supported_suffixes = {".xlsx", ".xlsm"}
    seen_hashes: set[str] = set()
    for attachment in attachments:
        suffix = Path(attachment.file_name).suffix.lower()
        if suffix not in supported_suffixes or attachment.sha256 in seen_hashes:
            continue
        seen_hashes.add(attachment.sha256)
        try:
            source_workbook = load_workbook(
                BytesIO(attachment.content),
                data_only=False,
                read_only=False,
                keep_links=False,
            )
        except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError):
            title = _unique_sheet_title(
                f"{Path(attachment.file_name).stem}-附件异常",
                used_titles,
            )
            sheet = workbook.create_sheet(title)
            _style_title(sheet, "上传表格未能嵌入", 4)
            _body_row(
                sheet,
                3,
                (
                    "文件名",
                    _safe_text(attachment.file_name),
                    "SHA-256",
                    _safe_text(attachment.sha256),
                ),
            )
            _body_row(
                sheet,
                4,
                ("说明", "该文件仍保留在系统附件中，请重新另存为有效 xlsx 后上传。"),
            )
            _finish_sheet(sheet, (18, 56, 18, 66))
            appended_titles.append(title)
            continue

        try:
            source_sheets = list(source_workbook.worksheets)
            stem = Path(attachment.file_name).stem
            sheet_names: dict[str, str] = {}
            for source_sheet in source_sheets:
                raw_title = (
                    stem
                    if len(source_sheets) == 1
                    else f"{stem}-{source_sheet.title}"
                )
                sheet_names[source_sheet.title] = _unique_sheet_title(
                    raw_title,
                    used_titles,
                )
            for source_sheet in source_sheets:
                target = workbook.create_sheet(sheet_names[source_sheet.title])
                _copy_attachment_worksheet(source_sheet, target, sheet_names)
                target.sheet_state = "visible"
                appended_titles.append(target.title)
        finally:
            source_workbook.close()
    return appended_titles


def build_internal_quote_workbook(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    manifest: dict[str, Any],
    reference_snapshot: dict[str, Any] | None = None,
    rr2_cost_summary: dict[str, Any] | None = None,
    cost_context: dict[str, Any] | None = None,
    attachments: list[InternalQuoteAttachment] | None = None,
) -> bytes:
    workbook = Workbook()
    workbook.properties.creator = "Royal Regent Nexus"
    workbook.properties.title = f"{quote.quote_no} 内部报价"
    _build_summary_sheet(
        workbook,
        quote,
        sections,
        reference_snapshot or {},
        rr2_cost_summary or {},
        cost_context or {},
    )
    by_code = {section.department: section for section in sections}
    _build_electronic_sheet(workbook, by_code.get("electronic"), reference_snapshot or {})
    _build_sewing_sheet(workbook, by_code.get("sewing"))
    _build_assembly_sheet(workbook, by_code.get("assembly"))
    if manifest.get("release_stage") == "p4_final_approved":
        _build_structured_data_sheet(workbook, quote, sections, reference_snapshot or {})
    _build_approval_sheet(workbook, quote, sections, manifest)
    for technical_sheet in workbook.worksheets[1:]:
        technical_sheet.sheet_state = "veryHidden"
    _append_spreadsheet_attachment_sheets(workbook, attachments or [])
    workbook.active = 0
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
