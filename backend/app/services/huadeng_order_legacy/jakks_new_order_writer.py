from __future__ import annotations

from copy import copy
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .common_new_order_excel import create_new_order_workbook


ALIASES = {
    "order_date": ("来单日期",),
    "contact": ("合同联系人", "联系人"),
    "customer_po": ("客户PO", "客PO"),
    "confirmation_no": ("确认号", "Confirmation No"),
    "contract_no": ("合同号",),
    "customer": ("客名",),
    "version": ("版本",),
    "item_no": ("货号",),
    "product_name": ("产品名称",),
    "po_description": ("PO原始品名描述",),
    "product_name_source": ("产品名称来源",),
    "quantity": ("数量",),
    "unit": ("数量单位", "单位"),
    "inner_pack": ("内装箱",),
    "outer_pack": ("外装箱",),
    "cartons": ("总箱数",),
    "special_notes": ("特别备注", "备注"),
    "inspection_date": ("验货期",),
    "ship_date": ("PO走货期", "走货期"),
    "unit_price_hkd": ("单价（港币）", "单价港币"),
    "unit_price_usd": ("单价(美金)", "单价美金"),
    "total_hkd": ("总货价（港币）", "总货价港币"),
    "total_usd": ("总货价（美金）", "总货价美金"),
    "brand": ("品牌名",),
    "country": ("走货国家",),
    "source_file": ("来源文件",),
}


def records_from_order(
    order: dict[str, Any],
    exchange_rate: float = 7.75,
) -> list[dict[str, Any]]:
    rows = []
    for line in order.get("lines", []):
        usd = float(line.get("unit_price_usd") or 0)
        quantity = float(line.get("quantity") or 0)
        unit = str(line.get("unit") or "").upper()
        rows.append({
            "order_date": line.get("order_date") or order.get("order_date"),
            "contact": line.get("contact") or order.get("contact") or "",
            "customer_po": line.get("customer_po") or order.get("customer_po") or "",
            "confirmation_no": line.get("confirmation_no") or order.get("confirmation_no") or "",
            "contract_no": line.get("contract_no") or order.get("contract_no"),
            "customer": line.get("customer") or order.get("customer") or "",
            "version": "",
            "item_no": line.get("item_no"),
            "product_name": line.get("product_name"),
            "po_description": line.get("po_description") or line.get("product_name"),
            "product_name_source": line.get("product_name_source") or "PO品名",
            "quantity": quantity,
            "inner_pack": line.get("inner_pack") or "",
            "outer_pack": line.get("outer_pack") or "",
            "cartons": line.get("cartons") or "",
            "special_notes": line.get("special_note") or "",
            "inspection_date": "",
            "ship_date": line.get("ship_date") or order.get("ship_date"),
            "unit_price_hkd": round(usd * exchange_rate, 6) if usd else "",
            "unit_price_usd": usd,
            "total_hkd": round(quantity * usd * exchange_rate, 2) if usd else "",
            "total_usd": line.get("total_usd"),
            "brand": "",
            "country": line.get("country") or order.get("country") or "",
            "source_file": line.get("source_file") or order.get("filename"),
            "unit": unit,
        })
    return rows


def generate_new_order(
    template_path: str | Path,
    order: dict[str, Any],
    output_path: str | Path,
    exchange_rate: float = 7.75,
) -> dict[str, Any]:
    rows = records_from_order(order, exchange_rate)
    output_path = Path(output_path)
    result = create_new_order_workbook(
        Path(template_path),
        output_path,
        rows,
        ALIASES,
        filename=Path(template_path).name,
        sheet_names=("26-Jakks排货表总 Ai", "Sheet1"),
        sheet_title="新单",
    )
    # 原 Jakks 表的合同号列按 6 位数字设计，物料合同号更长。
    # 保持列宽不变，用自动缩小和换行确保合同号、产品名、单位备注可见。
    workbook = load_workbook(output_path)
    try:
        worksheet = workbook["新单"]
        worksheet.column_dimensions["F"].width = max(
            worksheet.column_dimensions["F"].width or 0,
            16,
        )
        worksheet.column_dimensions["J"].width = max(
            worksheet.column_dimensions["J"].width or 0,
            28,
        )
        for row_index in range(2, 2 + len(rows)):
            customer_po_cell = worksheet.cell(row_index, 5)
            customer_po_cell.number_format = "@"
            customer_po_cell.quotePrefix = True
            for column_index in (4, 6, 7, 9):
                cell = worksheet.cell(row_index, column_index)
                alignment = copy(cell.alignment)
                alignment.shrink_to_fit = True
                alignment.vertical = "center"
                cell.alignment = alignment
            for column_index in (10, 15):
                cell = worksheet.cell(row_index, column_index)
                alignment = copy(cell.alignment)
                alignment.wrap_text = True
                alignment.vertical = "center"
                cell.alignment = alignment
            worksheet.row_dimensions[row_index].height = max(
                worksheet.row_dimensions[row_index].height or 0,
                36,
            )
        workbook.save(output_path)
    finally:
        workbook.close()
    return result
