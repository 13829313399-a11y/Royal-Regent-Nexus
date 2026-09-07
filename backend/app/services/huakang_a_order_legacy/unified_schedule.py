"""Huakang A's customer extensions to the September unified schedule."""
from __future__ import annotations

from copy import copy
from decimal import Decimal, ROUND_CEILING
import re

from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import CellRange
from openpyxl.worksheet.formula import ArrayFormula


TARGET_TEMPLATE = "HEYUAN_BUSINESS_UNIFIED_HUAKANG_A_V4"

ITEM_TAILS = {
    "360": ("条码", "MS Container Type (FCL/LCL)", "Consolidated ID", "Port of Discharge", "备注"),
    "green-toys": (
        "走货国家", "落货港", "完成状态", "走货方式", "单价US", "货价总金额US$",
        "PO单价HK$", "货价总金额HK$", "装好纸箱报库存价HK$", "出厂总金额HK$",
        "走货时间", "柜号", "走货方式", "发票", "打票单价", "打票总金额", "备注",
    ),
    "headstart": (
        "条码", "印字要求", "走货国家", "订单状态（是否齐物料）", "订单单价USD",
        "总金额USD", "单价HK$", "总金额HK$", "装好纸箱报库存价HK$", "走货日期",
        "走货方式", "车头注明", "PDQ差价", "发票单价", "发票金额", "打票日期",
        "发票号码", "CBM", "请款金额", "装箱清单", "备注",
    ),
}
EXTRA_HEADERS = {
    "360": {
        "barcode": "条码", "container_type": "MS Container Type (FCL/LCL)",
        "consolidated_id": "Consolidated ID", "port": "Port of Discharge",
    },
    "green-toys": {
        "country": "走货国家", "port": "落货港", "transportation_mode": "走货方式",
        "unit_price_usd": "单价US", "amount_usd": "货价总金额US$",
        "unit_price_hkd": "PO单价HK$", "amount_hkd": "货价总金额HK$",
    },
    "headstart": {
        "barcode": "条码", "printing_requirement": "印字要求", "country": "走货国家",
        "unit_price_usd": "订单单价USD", "amount_usd": "总金额USD",
        "unit_price_hkd": "单价HK$", "amount_hkd": "总金额HK$",
    },
}


def extra_columns(sheet, customer_code):
    """Resolve only known, unambiguous customer fields outside the common area."""
    from app.services.customer_order_unified import _normalized_header
    found = {}
    for field, label in EXTRA_HEADERS.get(customer_code, {}).items():
        found[field] = [c.column for c in sheet[3] if c.column > 28
                        and _normalized_header(c.value) == _normalized_header(label)]
    # Green Toys has a planned mode before prices and an actual shipping mode
    # later. Only use that established distinction when it remains unambiguous.
    if customer_code == "green-toys":
        prices = found.get("unit_price_usd", [])
        ports = found.get("port", [])
        if len(prices) == len(ports) == 1:
            found["transportation_mode"] = [c for c in found["transportation_mode"] if ports[0] < c < prices[0]]
        else:
            found["transportation_mode"] = []
    return {field: columns[0] for field, columns in found.items() if len(columns) == 1}


def enabled(factory_id, customer_code):
    return factory_id == "huakang-a" and customer_code in ITEM_TAILS


def history_reference(customer_code, contract, reference, po):
    if customer_code in {"360", "green-toys"}:
        return reference or po or contract
    return reference or contract or po


def identity(customer_code, reference, product):
    from app.services.customer_order_unified import _key
    if customer_code == "green-toys":
        reference = re.sub(r"-\d+$", "", str(reference or ""))
    elif customer_code == "headstart":
        from app.services.huakang_a_order_legacy.green_toys_headstart import _headstart_contract_key
        reference = _headstart_contract_key(reference)
    return _key(reference), _key(product)


def reconcile_green_po(record, history, assigned):
    from app.services.customer_order_unified import _key
    base = str(record.get("contract_no") or "")
    key = (base, _key(record.get("item_no")))
    matching = {h.po_no for h in history if h.po_no and identity("green-toys", h.po_no, h.product_no) == identity("green-toys", base, record.get("item_no"))}
    if len(matching) == 1:
        assigned[key] = next(iter(matching))
    if key not in assigned:
        used = [h.po_no for h in history] + list(assigned.values())
        suffixes = [int(m.group(1)) for value in used if (m := re.fullmatch(re.escape(base) + r"-(\d+)", value))]
        assigned[key] = f"{base}-{max(suffixes, default=0) + 1}" if base else ""
    record["customer_po"] = assigned[key]


def map_record(row, record, customer_code):
    """Separate actual business fields from the legacy 17-column display strings."""
    row["standard"] = record.get("standard") or ""
    row["packaging"] = record.get("product_packaging") or ""
    row["unit_price_usd"] = record.get("unit_price_usd")
    row["_huakang_customer"] = customer_code
    for field in EXTRA_HEADERS[customer_code]:
        if field not in {"amount_usd", "unit_price_hkd", "amount_hkd"}:
            row[field] = record.get(field) if record.get(field) is not None else ""
    if customer_code == "360":
        row["contract_no"] = record.get("customer_release") or ""
        row["po_no"] = record.get("contract_no") or ""
        row["reference_no"] = record.get("contract_no") or record.get("customer_po") or ""
        row["customer_name"] = record.get("customer_name") or "ThreeSixty"
        row.setdefault("lineage", {}).update({
            "contract_no": "PO · Customer Release No.",
            "reference_no": "PO · PURCHASE ORDER RELEASE 的 RL 编号",
            "po_no": "PO · PURCHASE ORDER RELEASE 的 RL 编号",
            "customer_po_number": f"PO · Customer PO Number: {record.get('customer_po') or ''}",
        })
    elif customer_code == "green-toys":
        row["reference_no"] = record.get("customer_po") or record.get("contract_no") or ""
        row["transportation_mode"] = "40'YT"
    else:
        row["po_no"] = record.get("contract_no") or ""
        row["reference_no"] = record.get("contract_no") or ""
    row["customer_country"] = " / ".join(str(v) for v in (row.get("customer_name"), row.get("country")) if v)
    row.setdefault("lineage", {})["mapping_rule"] = (
        "华康A 2026-09-04统一排期：客户专属字段按表头映射，三表分别在取消单前追加。"
    )
    for field in EXTRA_HEADERS[customer_code]:
        if row.get(field) not in (None, ""):
            row["lineage"][field] = "固定运输规则 40'YT" if customer_code == "green-toys" and field == "transportation_mode" else f"{row.get('source_po_file_name', 'PO')} · {field}"
    return row


def round_cartons(row):
    from app.services.customer_order_unified import _number, _number_text
    quantity, units = _number(row.get("quantity")), _number(row.get("units_per_carton"))
    if quantity is not None and units is not None and units > 0:
        row["carton_count"] = _number_text((quantity / units).to_integral_value(rounding=ROUND_CEILING))


def copy_array_formula(value, source_coordinate, target_coordinate):
    moved = copy(value)
    moved.text = Translator(value.text, origin=source_coordinate).translate_formula(target_coordinate)
    moved.ref = Translator("=" + value.ref, origin=source_coordinate).translate_formula(target_coordinate)[1:]
    return moved


def _insert_rows(workbook, target, start, amount):
    from app.services.huaxing_order_legacy.new_order_excel import (
        _rewrite_formula_for_insert, _shift_target_sheet_structures,
    )
    formulas = [
        (sheet, cell.row, cell.column, copy(cell.value))
        for sheet in workbook for cell in sheet._cells.values()
        if cell.data_type == "f"
    ]
    merges = [CellRange(str(r)) for r in target.merged_cells.ranges if r.max_row >= start]
    for merged in merges:
        target.unmerge_cells(str(merged))
    target.insert_rows(start, amount)
    _shift_target_sheet_structures(target, start, amount, merges)
    for sheet, old_row, column, value in formulas:
        new_row = old_row + amount if sheet is target and old_row >= start else old_row
        formula = value.text if isinstance(value, ArrayFormula) else value
        rewritten = _rewrite_formula_for_insert(
            formula, formula_sheet=sheet.title, target_sheet=target.title,
            formula_row=old_row, insert_row=start, amount=amount,
        )
        if isinstance(value, ArrayFormula):
            value.text = rewritten
            if sheet is target:
                ref = CellRange(value.ref)
                if ref.min_row >= start:
                    ref.shift(row_shift=amount)
                elif ref.max_row >= start:
                    ref.max_row += amount
                value.ref = str(ref)
        else:
            value = rewritten
        sheet.cell(new_row, column).value = value


def output_slots(workbook, count):
    from app.services.customer_order_unified import SHEETS, _marker_row, _copy_template_row
    result = {}
    for name in SHEETS:
        sheet = workbook[name]
        marker = _marker_row(sheet)
        # Any literal value is user-owned, including notes without order keys.
        occupied = [r for r in range(4, marker) if any(
            c.value not in (None, "") and c.data_type != "f" for c in sheet[r]
        )]
        start = max(occupied, default=3) + 1
        template_row = next((r for r in range(start - 1, 3, -1) if any(
            c.data_type == "f" for c in sheet[r]
        )), 4)
        if name != "ITEM表":
            template_row = next((r for r in range(start, marker) if sum(
                c.data_type == "f" for c in sheet[r]
            ) >= 8), template_row)
        free = marker - start
        if count > free:
            _insert_rows(workbook, sheet, marker, count - free)
        slots = list(range(start, start + count))
        # Existing reserved formulas are authoritative. Only new rows need a copy.
        for row in slots:
            if row >= marker:
                _copy_template_row(sheet, template_row, row)
            # Some 360 reserved rows have styles but no lookup formulas.
            # Fill only missing formulas, retaining every existing template formula.
            for source in list(sheet[template_row]):
                target = sheet.cell(row, source.column)
                if target.value is None and source.data_type == "f":
                    target._style = copy(source._style)
                    target.value = (
                        copy_array_formula(source.value, source.coordinate, target.coordinate)
                        if isinstance(source.value, ArrayFormula)
                        else Translator(source.value, origin=source.coordinate).translate_formula(target.coordinate)
                    )
        result[name] = slots
    return result


def write_extras(sheet, row_number, row, customer_code):
    from app.services.customer_order_unified import _number, _excel_value
    columns = extra_columns(sheet, customer_code)
    for field, column in columns.items():
        if field in {"amount_usd", "unit_price_hkd", "amount_hkd"}:
            continue
        value = row.get(field)
        if field == "unit_price_usd":
            value = _excel_value(_number(value))
        sheet.cell(row_number, column).value = value if value not in (None, "") else None
    if customer_code in {"green-toys", "headstart"}:
        r = row_number
        usd = _number(row.get("unit_price_usd"))
        hkd = _number(row.get("unit_price_hkd"))
        usd_cell = f"{get_column_letter(columns['unit_price_usd'])}{r}" if 'unit_price_usd' in columns else None
        hkd_cell = f"{get_column_letter(columns['unit_price_hkd'])}{r}" if 'unit_price_hkd' in columns else None
        if 'unit_price_hkd' in columns:
            sheet.cell(r, columns['unit_price_hkd']).value = (
                f'=IF({usd_cell}="","",ROUND({usd_cell}*7.8,4))'
                if usd_cell and usd is not None and hkd == (usd * Decimal("7.8")).quantize(Decimal("0.0001"))
                else _excel_value(hkd)
            )
        for field, price_cell, price in (("amount_usd", usd_cell, usd), ("amount_hkd", hkd_cell, hkd)):
            if field in columns:
                quantity = _number(row.get("quantity"))
                sheet.cell(r, columns[field]).value = (
                    f'=IF(OR(K{r}="",{price_cell}=""),"",K{r}*{price_cell})'
                    if price_cell else _excel_value(quantity * price) if quantity is not None and price is not None else None
                )
