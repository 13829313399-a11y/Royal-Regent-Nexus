from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.internal_quote import InternalQuote, InternalQuoteSection


P3_TEMPLATE_VERSION = "internal-quote-p3-v1"
P4_TEMPLATE_VERSION = "internal-quote-p4-v2"
WORKBOOK_LAYOUT_VERSION = "internal-quote-unified-desk-v3"
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


def _dimensions(value: object) -> tuple[float | str, float | str, float | str]:
    source = _dict_value(value)
    return (
        _number(source.get("length", source.get("length_cm", ""))),
        _number(source.get("width", source.get("width_cm", ""))),
        _number(source.get("height", source.get("height_cm", ""))),
    )


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
    """Render the released internal quote in the established A:R desk layout.

    The system-facing JSON/revision sheets remain in the workbook for adapters,
    but this first sheet is the only visible business sheet and intentionally
    mirrors the long-used internal quotation template.
    """

    sheet = workbook.active
    sheet.title = "报价明细"
    sheet.sheet_view.showGridLines = True
    by_code = {section.department: section for section in sections}
    sales_payload = _section_payload(by_code.get("sales"))
    shipping = _dict_value(rr2_cost_summary.get("shipping_pricing", {}))
    t1 = _rr2_values(rr2_cost_summary, "t1")
    t2 = _rr2_values(rr2_cost_summary, "t2")
    t3 = _rr2_values(rr2_cost_summary, "t3")
    t4 = _rr2_tax_rows(rr2_cost_summary)
    summary_totals = _dict_value(rr2_cost_summary.get("totals", {}))

    # A1:R6 — frozen material, machine, tax, carton and exchange references.
    materials = _reference_materials(reference_snapshot)[:20]
    machines = _reference_machines(reference_snapshot)[:10]
    for row in range(1, 7):
        for column in range(3, 19):
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

    reference_blocks = ((1, materials[:10]), (3, materials[10:20]), (5, machines))
    for header_row, rows in reference_blocks:
        sheet.cell(header_row, 3).value = "机型" if header_row == 5 else "料型"
        sheet.cell(header_row + 1, 3).value = "单价/元" if header_row == 5 else "单价/P"
        for offset, (label, price) in enumerate(rows, start=4):
            sheet.cell(header_row, offset).value = label
            sheet.cell(header_row + 1, offset).value = price
            sheet.cell(header_row + 1, offset).number_format = (
                "#,##0" if header_row == 5 else "0.0"
            )

    fx = _dict_value(reference_snapshot.get("fx", {}))
    tax_reference_rows = (
        (
            1,
            (
                ("搪胶类3%", _tax_rate(reference_snapshot, "slush", 0.03)),
                ("车发类", _tax_rate(reference_snapshot, "sewing_hair", 0.115)),
                ("车衣类", _tax_rate(reference_snapshot, "sewing_clothes", 0.115)),
                ("吸塑类", _tax_rate(reference_snapshot, "blister", 0.06)),
                ("含税13%类", _tax_rate(reference_snapshot, "tax_13_percent", 0.115)),
            ),
        ),
        (
            3,
            (
                ("汇率", _float_value(fx.get("rmb_hkd"), 0.85)),
                ("纸箱系数", _float_value(reference_snapshot.get("paper_price_factor"), 2.7)),
                ("装工", _float_value(reference_snapshot.get("assembly_labor_base_hkd"), 260)),
                ("运费含税9%", _tax_rate(reference_snapshot, "freight_tax_9", 0.0826)),
                ("纸箱类", _tax_rate(reference_snapshot, "carton", 0.10)),
            ),
        ),
        (
            5,
            (
                ("港币兑美元", _float_value(fx.get("hkd_usd"), 7.8)),
                ("人民币兑美元", _float_value(fx.get("rmb_usd"), 7.0)),
                ("加价倍数", _float_value(shipping.get("markup"), _float_value(reference_snapshot.get("markup"), 1.2))),
                ("结算点数", _float_value(shipping.get("settlement"), _float_value(reference_snapshot.get("settlement"), 0.98))),
                ("杂项", _float_value(reference_snapshot.get("misc_ratio"), 0.02)),
            ),
        ),
    )
    for header_row, rows in tax_reference_rows:
        for column, (label, value) in enumerate(rows, start=14):
            sheet.cell(header_row, column).value = label
            sheet.cell(header_row + 1, column).value = value
            if header_row == 1:
                sheet.cell(header_row + 1, column).number_format = "0.00%"
            elif header_row == 3:
                sheet.cell(header_row + 1, column).number_format = (
                    "0.00%" if column in {17, 18} else ("#,##0" if column == 16 else "0.00")
                )
            else:
                sheet.cell(header_row + 1, column).number_format = (
                    "0.00%" if column == 18 else "0.00"
                )

    # A8:R8 — product quotation title.
    sheet.merge_cells("A8:R8")
    title = sheet["A8"]
    title.value = f"{quote.product_name or quote.quote_no}报价"
    title.font = Font(name="宋体", size=14, bold=False, color=TEMPLATE_BLUE)
    title.alignment = Alignment(horizontal="center", vertical="center")
    title.border = Border(
        left=TEMPLATE_MEDIUM,
        right=TEMPLATE_MEDIUM,
        top=TEMPLATE_MEDIUM,
        bottom=TEMPLATE_MEDIUM,
    )
    sheet.row_dimensions[8].height = 27

    # A9:M — molding/injection detail with at least six input rows.
    mold_headers = ("", "", "名称", "料型", "料重(G)", "料价(G)", "机型", "1出几套", "目标数", "啤工", "料金额", "", "报客价")
    for column, header in enumerate(mold_headers, start=1):
        _template_cell(
            sheet,
            9,
            column,
            header,
            bold=False,
            color=TEMPLATE_RED if column not in {1, 2, 12} else TEMPLATE_BLACK,
            wrap_text=False,
        )
    sheet.cell(9, 1).border = Border(
        left=TEMPLATE_MEDIUM,
        right=TEMPLATE_THIN,
        bottom=TEMPLATE_THIN,
    )
    sheet.cell(9, 13).border = Border(
        left=TEMPLATE_THIN,
        right=TEMPLATE_MEDIUM,
        bottom=TEMPLATE_THIN,
    )

    mold_lines = _calculation_lines(by_code.get("molding"), "injection")
    if not mold_lines:
        mold_lines = _list_of_dicts(_section_payload(by_code.get("engineering")).get("molds", []))
    mold_slots = max(6, len(mold_lines))
    mold_start_row = 10
    mold_end_row = mold_start_row + mold_slots - 1
    for index in range(mold_slots):
        row_index = mold_start_row + index
        line = mold_lines[index] if index < len(mold_lines) else {}
        material = _safe_text(line.get("material") or line.get("material_type") or "")
        values = (
            index + 1 if line else "",
            "",
            _safe_text(line.get("item") or line.get("chinese_name") or line.get("mold_no") or ""),
            material,
            _number(line.get("loss_weight_g", line.get("net_weight_g", ""))),
            _number(line.get("material_price_hkd_g", "")),
            _safe_text(line.get("machine_code") or line.get("machine_name") or ""),
            _number(line.get("sets", line.get("cavity", ""))),
            _number(line.get("target_output", "")),
            _number(line.get("molding_cost_hkd", "")),
            _number(line.get("material_cost_hkd", "")),
            "",
            _number(line.get("customer_price_hkd", line.get("unit_amount_hkd", ""))),
        )
        for column, value in enumerate(values, start=1):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_BLACK,
                horizontal="left" if column in {2, 3, 4} else "center",
                wrap_text=False,
                number_format=(
                    "0"
                    if column == 1 and value != ""
                    else "0.0000_ "
                    if column in {6, 10, 12}
                    else "0.000_ "
                    if column in {11, 13}
                    else None
                ),
                font_name="Times New Roman" if column in {1, 5, 6, 8, 9, 10, 11, 12, 13} else "宋体",
            )
        sheet.cell(row_index, 1).border = Border(
            left=TEMPLATE_MEDIUM,
            right=TEMPLATE_THIN,
            top=TEMPLATE_THIN,
            bottom=TEMPLATE_THIN,
        )
        sheet.cell(row_index, 13).border = Border(
            left=TEMPLATE_THIN,
            right=TEMPLATE_MEDIUM,
            top=TEMPLATE_THIN,
            bottom=TEMPLATE_THIN,
        )
        if line and values[12] == "":
            sheet.cell(row_index, 13).value = f"=SUM(J{row_index}:K{row_index})"
            sheet.cell(row_index, 13).number_format = "0.000_ "
        sheet.row_dimensions[row_index].height = 15

    mold_total_row = mold_end_row + 1
    for column in range(1, 14):
        _template_cell(
            sheet,
            mold_total_row,
            column,
            "",
            color=TEMPLATE_RED,
            wrap_text=False,
            font_name="Times New Roman" if column in {1, 5, 6, 8, 9, 10, 11, 12, 13} else "宋体",
        )
    sheet.cell(mold_total_row, 3).value = "模具合计"
    sheet.cell(mold_total_row, 3).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_BLUE)
    for column in (5, 10, 11, 13):
        letter = get_column_letter(column)
        sheet.cell(mold_total_row, column).value = f"=SUM({letter}{mold_start_row}:{letter}{mold_end_row})"
        sheet.cell(mold_total_row, column).number_format = "0.0000_ " if column == 10 else "0.000_ "
    sheet.cell(mold_total_row, 1).border = Border(
        left=TEMPLATE_MEDIUM,
        right=TEMPLATE_THIN,
        top=TEMPLATE_THIN,
        bottom=TEMPLATE_THIN,
    )
    sheet.cell(mold_total_row, 13).border = Border(
        left=TEMPLATE_THIN,
        right=TEMPLATE_MEDIUM,
        top=TEMPLATE_THIN,
        bottom=TEMPLATE_THIN,
    )

    shipping_header_row = mold_total_row + 1
    shipping_value_row = shipping_header_row + 1
    shipping_rows = _list_of_dicts(shipping.get("rows", []))
    for offset in range(5):
        column = 4 + offset
        source = shipping_rows[offset] if offset < len(shipping_rows) else {}
        label = source.get("name") or ("出厂价" if offset == 0 else "")
        _template_cell(
            sheet,
            shipping_header_row,
            column,
            _safe_text(label),
            color=TEMPLATE_RED,
            wrap_text=False,
            border=None,
        )
        _template_cell(
            sheet,
            shipping_value_row,
            column,
            _number(source.get("after_settlement_hkd", source.get("total_hkd", ""))),
            color=TEMPLATE_BLACK,
            number_format="0.00_);[Red]\\(0.00\\)",
            wrap_text=False,
            border=None,
        )

    # A:D cost detail, with the authoritative released amount in column D.
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
    color_box_amount = min(max(t2.get("color_box", 0.0), 0.0), max(packaging_total, 0.0))
    packaging_auxiliary = packaging_total - color_box_amount

    # Business ordering follows the desk template.  Sub-types omitted from the
    # category column remain identifiable in column C without introducing a
    # second, competing sort order.
    add_detail("¥13%", "料价", "料价", molding_material)
    add_detail("", "啤工", "啤工", molding_labor)
    add_detail(
        "",
        "啤工",
        "注塑未分类成本",
        molding_adjustment,
    )
    add_detail("", "装配工", "装工", cost_context.get("assembly_hkd"))
    add_detail("", "装配工", "包装", cost_context.get("packing_labor_hkd"))
    add_detail("", "喷油工", "喷油人工", painting_labor)
    add_detail(
        "",
        "喷油工",
        "喷油未分类成本",
        painting_adjustment,
    )
    add_detail("¥13%", "油漆", "油漆", paint_material)
    add_detail("¥3%", "搪胶", "搪胶", cost_context.get("slush_hkd"))
    add_detail("", "吹气", "吹气", molding_blow)
    add_detail("¥13%", "五金", "五金", cost_context.get("hardware_hkd"))

    # Other purchases: functional items first, packaging auxiliaries last.
    add_detail("¥13%", "其他外购", "电子", cost_context.get("electronic_hkd"))
    add_detail("¥13%", "其他外购", "车发", sewing_hair)
    add_detail("¥13%", "其他外购", "车衣", sewing_cloth)
    add_detail("", "其他外购", "车缝未分类成本", sewing_adjustment)
    add_detail("¥13%", "其他外购", "工程辅料/外购", cost_context.get("auxiliary_hkd"))
    add_detail("", "其他外购", "附加税/杂项", shipping.get("additional_tax_hkd"))
    add_detail("¥13%", "其他外购", "包装辅材", packaging_auxiliary)
    add_detail("¥13%", "彩盒/内卡", "彩盒/内卡", color_box_amount)
    add_detail("¥10%", "纸箱", "纸箱", cost_context.get("carton_hkd"))
    add_detail("¥9%", "运费", "印尼运费", cost_context.get("indonesia_freight_hkd"))

    detail_start_row = mold_total_row + 3
    detail_slots = max(19, len(detail_rows))
    detail_end_row = detail_start_row + detail_slots - 1
    for index in range(detail_slots):
        row_index = detail_start_row + index
        values = detail_rows[index] if index < len(detail_rows) else ("", "", "", "")
        for column, value in enumerate(values, start=1):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_BLACK,
                horizontal="left" if column in {2, 3} else "center",
                wrap_text=False,
                size=11 if column in {2, 4} else 10,
                number_format="0.000" if column == 4 else None,
                border=Border(left=TEMPLATE_MEDIUM) if column == 1 else None,
                font_name="Times New Roman" if column == 1 else "宋体",
            )
        sheet.row_dimensions[row_index].height = 15

    # J:M — size/carton/flat-card/packing details.
    cartons = _list_of_dicts(sales_payload.get("cartons", []))
    carton = cartons[0] if cartons else {}
    carton_line = next((row for row in _calculation_lines(by_code.get("sales"), "carton")), {})
    carton_dimensions = (
        _number(carton.get("length_in", "")),
        _number(carton.get("width_in", "")),
        _number(carton.get("height_in", "")),
    )
    packaging_start_row = detail_start_row
    carton_price_factor = _float_value(reference_snapshot.get("paper_price_factor"), 2.7)
    packaging_rows = (
        ("外箱:", *carton_dimensions),
        ("彩盒尺寸 (in)", *_dimensions(sales_payload.get("color_box_size_in") or sales_payload.get("color_box_size_cm"))),
        ("产品尺寸 (in)", *_dimensions(sales_payload.get("product_size_in") or sales_payload.get("product_size_cm"))),
        ("CUFT:", f"=K{packaging_start_row}*L{packaging_start_row}*M{packaging_start_row}/1728", "", ""),
        ("纸板价", f"=K{packaging_start_row}*L{packaging_start_row}*3.5/1000", "", ""),
        (
            "箱价：",
            f"=(K{packaging_start_row}+L{packaging_start_row}+2)*(L{packaging_start_row}+M{packaging_start_row}+1)*{carton_price_factor}*2/1000",
            "",
            "",
        ),
        ("", "", "", ""),
        ("装箱：", _number(carton.get("qty_per_carton", "")), "PCS/1CTN", ""),
        ("合计", f"=IFERROR(K{packaging_start_row + 5}/K{packaging_start_row + 7},0)", "", ""),
    )
    for offset, values in enumerate(packaging_rows):
        row_index = detail_start_row + offset
        for column, value in enumerate(values, start=10):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_BLUE if column == 10 and offset == 8 else TEMPLATE_BLACK,
                horizontal="left" if column in {10, 11} and offset >= 3 else "center",
                wrap_text=False,
                size=11 if column in {11, 12} and offset < 3 else (9 if offset == 5 else 10),
                number_format="0.000_ " if column == 11 and offset in {3, 4, 5, 8} else None,
                font_name="Times New Roman" if column in {11, 12, 13} and offset < 3 else "宋体",
            )

    subtotal_row = detail_end_row + 1
    markup_row = subtotal_row + 1
    settlement_row = subtotal_row + 2
    quote_row = subtotal_row + 3
    target_row = subtotal_row + 4
    difference_row = subtotal_row + 5
    difference_percent_row = subtotal_row + 6

    function_start_row = detail_start_row + 10
    function_end_row = subtotal_row
    _template_style_range(sheet, function_start_row, function_end_row, 10, 18)
    sheet.merge_cells(
        start_row=function_start_row,
        start_column=10,
        end_row=function_end_row,
        end_column=18,
    )
    function_cell = sheet.cell(function_start_row, 10)
    function_cell.value = f"功能介绍：{quote.remark or ''}"
    function_cell.font = Font(name="宋体", size=12, color=TEMPLATE_RED)
    function_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    function_cell.border = TEMPLATE_BORDER

    for row_index in (subtotal_row, markup_row, settlement_row, quote_row, target_row, difference_row, difference_percent_row):
        for column in range(3, 5):
            _template_cell(
                sheet,
                row_index,
                column,
                "",
                color=TEMPLATE_BLACK,
                wrap_text=False,
                border=None,
            )
    sheet.cell(subtotal_row, 4).value = f"=SUM(D{detail_start_row}:D{detail_end_row})"
    sheet.cell(markup_row, 3).value = "×"
    sheet.cell(markup_row, 4).value = _float_value(shipping.get("markup"), 1.2)
    sheet.cell(settlement_row, 3).value = "÷"
    sheet.cell(settlement_row, 4).value = _float_value(shipping.get("settlement"), 0.98)
    sheet.cell(quote_row, 3).value = "报客价："
    sheet.cell(quote_row, 4).value = f"=D{subtotal_row}*D{markup_row}/D{settlement_row}"
    sheet.cell(target_row, 3).value = "目标价："
    sheet.cell(target_row, 4).value = _price_number(quote.target_customer_price)
    sheet.cell(difference_row, 3).value = "相差金额："
    sheet.cell(difference_row, 4).value = f'=IF(D{target_row}="","",D{quote_row}-D{target_row})'
    sheet.cell(difference_percent_row, 3).value = "相差百分比："
    sheet.cell(difference_percent_row, 4).value = (
        f'=IF(OR(D{target_row}="",D{target_row}=0),"",D{difference_row}/D{target_row})'
    )
    for row_index in range(subtotal_row, difference_percent_row + 1):
        sheet.cell(row_index, 3).font = Font(name="宋体", size=10, color=TEMPLATE_BLACK)
        sheet.cell(row_index, 4).font = Font(name="宋体", size=11, color=TEMPLATE_BLACK)
        sheet.cell(row_index, 4).number_format = (
            "0.00%" if row_index == difference_percent_row else "0.00_);[Red]\\(0.00\\)"
        )
    sheet.cell(markup_row, 3).alignment = Alignment(horizontal="right", vertical="center")
    sheet.cell(settlement_row, 3).alignment = Alignment(horizontal="right", vertical="center")
    sheet.cell(settlement_row, 4).border = Border(bottom=TEMPLATE_THIN)
    sheet.cell(quote_row, 4).font = Font(name="宋体", size=11, color=TEMPLATE_RED)
    sheet.cell(target_row, 4).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_RED)
    sheet.cell(difference_percent_row, 4).font = Font(name="宋体", size=10, bold=True, color=TEMPLATE_RED)
    for row_index in (target_row, difference_row, difference_percent_row):
        sheet.row_dimensions[row_index].height = 24

    # Color-box tiers sit beside the customer/target price block.
    color_box = _dict_value(_dict_value(sales_payload.get("customer_quote_fields", {})).get("buzzbee", {}))
    color_tiers = _list_of_dicts(color_box.get("color_box_tiers", []))[:2]
    for column, label in enumerate(("报客彩盒", "报客彩盒FSC", "MOQ数量"), start=10):
        _template_cell(
            sheet,
            settlement_row,
            column,
            label,
            color=TEMPLATE_BLACK,
            size=9 if column == 11 else 10,
            wrap_text=False,
        )
    for offset in range(2):
        row_index = quote_row + offset
        tier = color_tiers[offset] if offset < len(color_tiers) else {}
        values = (
            _number(tier.get("quote_price_hkd", "")),
            _number(tier.get("fsc_price_hkd", "")),
            _safe_text(tier.get("moq", "")),
        )
        for column, value in enumerate(values, start=10):
            _template_cell(
                sheet,
                row_index,
                column,
                value,
                color=TEMPLATE_RED,
                size=11 if column == 11 else 10,
                wrap_text=False,
                number_format="0.00_);[Red]\\(0.00\\)" if column in {10, 11} else None,
            )

    # C:P — formula-driven summary bands, retaining the reference workbook's
    # compact yellow headers and thin black grid.
    summary_start_row = difference_percent_row + 2
    amount_format = "0.00_);[Red]\\(0.00\\)"
    detail_category_range = f"$B${detail_start_row}:$B${detail_end_row}"
    detail_description_range = f"$C${detail_start_row}:$C${detail_end_row}"
    detail_amount_range = f"$D${detail_start_row}:$D${detail_end_row}"

    def sum_category(label_cell: str) -> str:
        return f"=SUMIF({detail_category_range},{label_cell},{detail_amount_range})"

    def sum_description(description: str) -> str:
        return f'=SUMIF({detail_description_range},"{description}",{detail_amount_range})'

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
            f"=D{quote_row}",
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
            t2.get("battery", 0.0),
            t2.get("libao", 0.0),
            t2.get("plating", 0.0),
            t2.get("other_buy", 0.0),
            sum_category(f"J{second_header_row}"),
            t2.get("freight", 0.0),
            t2.get("cabinet", 0.0),
            f'=SUMIF({detail_category_range},"运费",{detail_amount_range})+SUMIF({detail_description_range},"附加税/杂项",{detail_amount_range})',
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
    for column in range(3, 17):
        if column == 3:
            value: object = _float_value(summary_totals.get("rmb_purchase_cost_hkd"))
            number_format = amount_format
        elif column == 4:
            value = _float_value(t4.get("tax13", {}).get("amount_hkd"))
            number_format = amount_format
        elif column == 5:
            value = ""
            number_format = amount_format
        elif 6 <= column <= 14:
            key = tax_keys[column - 6]
            value = _percent_fraction(t4.get(key, {}).get("rate_percent"))
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
    for column, key in enumerate(tax_keys, start=6):
        amount = _float_value(t4.get(key, {}).get("amount_hkd"))
        sheet.cell(deduction_row, column).value = f"={amount}*{get_column_letter(column)}{tax_amount_row}"
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
    for row in range(summary_start_row, deduction_row + 1):
        sheet.row_dimensions[row].height = 15
    for row in (summary_start_row + 2, summary_start_row + 5, summary_start_row + 8):
        sheet.row_dimensions[row].height = 7
    sheet.row_dimensions[tax_header_row + 2].height = 6
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    sheet.freeze_panes = "A9"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.page_margins.left = 0.2
    sheet.page_margins.right = 0.2
    sheet.page_margins.top = 0.35
    sheet.page_margins.bottom = 0.35
    sheet.print_area = f"A1:R{deduction_row}"
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


def build_internal_quote_workbook(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    manifest: dict[str, Any],
    reference_snapshot: dict[str, Any] | None = None,
    rr2_cost_summary: dict[str, Any] | None = None,
    cost_context: dict[str, Any] | None = None,
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
    workbook.active = 0
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
