"""Append a user-maintained extension without moving existing workbook cells."""
from copy import copy
import re

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import CellRange


SHEETS = ("ITEM表", "接单表", "正单评审表")


def manual_value_columns(sheet):
    """Existing manual status/provenance must not become a new order's value."""
    common_end = 19 if sheet.title in ('接单表', '正单评审表') else 28
    return {c.column for c in sheet._cells.values()
            if c.row == 3 and c.column > common_end and c.data_type != 'f'
            and re.sub(r'\s+', '', str(c.value or '')) in {'纸箱', '紙箱', '拆单来源', '拆單來源'}}


def unified_manual_sheets(workbook, factory_id, customer_code):
    """Use only the selected customer's registered unified detail sheets."""
    from .customer_order_unified import _factory_allowed
    from . import customer_order_huaxing_unified as huaxing
    if not _factory_allowed(customer_code, factory_id):
        return ()
    if huaxing.enabled(factory_id, customer_code):
        return (*huaxing.item_sheets(workbook, customer_code), '接单表', '正单评审表')
    return SHEETS


def ensure_manual_columns(workbook, *, factory_id, customer_code, label, aliases,
                          scopes=(("huakang-a", "360"),), sheets=SHEETS):
    """Append headers only; never infer carton status or rewrite existing cells.

    Reuse existing simplified/traditional headers even if repeated: there is no
    automated value writer that needs to choose between user-owned columns.
    Preflight all sheets so an unsupported layout cannot be partially changed.
    """
    report = {"applied": False, "columns": {}, "added": []}
    if (factory_id, customer_code) not in scopes:
        return report
    from app.services.customer_order_unified import CustomerOrderUnifiedError
    customer_label = customer_code

    plans = []
    for name in sheets:
        if name not in workbook:
            raise CustomerOrderUnifiedError(f"{customer_label} {label}栏：缺少 {name}")
        sheet = workbook[name]
        found = sorted(c.column for c in sheet._cells.values()
                       if c.row == 3 and c.data_type != "f"
                       and re.sub(r"\s+", "", str(c.value or "")) in aliases)
        if found:
            report["columns"][name] = [get_column_letter(c) for c in found]
            continue
        # Validation/table ranges may extend beyond instantiated cells. Never
        # put this manual field into such an existing user-owned column.
        # Old templates can have formatting-only cells far to the right. Those
        # are not data columns; putting the header after them creates a gap.
        right = max([19 if name in ('接单表', '正单评审表') else 28,
                     *(c.column for c in sheet._cells.values()
                       if c.value is not None or c.data_type == "f"
                       or c.comment is not None or c.hyperlink is not None),
                     *(r.max_col for r in sheet.merged_cells.ranges),
                     *(r.max_col for v in sheet.data_validations.dataValidation for r in v.sqref.ranges),
                     *(CellRange(t.ref).max_col for t in sheet.tables.values())])
        if right >= 16384:
            raise CustomerOrderUnifiedError(f"{customer_label} {label}栏：{name} 最右列已占用，无法安全追加，请先核对排期")
        plans.append((sheet, right + 1))
        report["columns"][name] = [get_column_letter(right + 1)]

    for sheet, column in plans:
        common_end = 19 if sheet.title in ('接单表', '正单评审表') else 28
        source = max((c for c in sheet._cells.values() if c.row == 3 and c.column < column
                      and c.value not in (None, "")), key=lambda c: c.column,
                     default=sheet.cell(3, common_end))
        header = sheet.cell(3, column, label)
        header._style = copy(source._style)
        alignment = copy(header.alignment)
        alignment.wrap_text = True
        header.alignment = alignment
        sheet.column_dimensions[get_column_letter(column)].width = 18
        report["added"].append(sheet.title)
    report["applied"] = True
    return report
