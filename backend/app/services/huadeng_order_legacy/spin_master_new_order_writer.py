from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common_new_order_excel import create_new_order_workbook
from .spin_master_parser import parse_po_file


FIELD_ALIASES = {
    "order_date": ("来单期", "订单日期", "DATE"),
    "contact": ("联系人",),
    "customer_po": ("客PO", "Customer PO"),
    "contract_no": ("合同号", "NUMBER"),
    "customer": ("客名", "Customer"),
    "version": ("版本",),
    "item_no": ("货号/SI", "货号", "SI"),
    "product_name": ("产品名称",),
    "quantity": ("数量", "QTY"),
    "inner_pack": ("内箱", "内装箱"),
    "outer_pack": ("外箱",),
    "cartons": ("总箱数",),
    "special_notes": ("特别备注",),
    "inspection_date": ("验货期",),
    "ship_date": ("PO走货期", "走货期", "Delivery Date"),
    "unit_price_hkd": ("单价港币", "单价(港币)", "港币单价"),
    "unit_price_usd": ("单价美金", "单价(美金)", "USD单价"),
    "total_hkd": ("总货价港币", "总价HKD", "总金额HKD"),
    "total_usd": ("总货价美金", "总价USD", "总金额USD"),
    "english_name": ("英文名称", "英文品名"),
    "source_file": ("来源文件",),
}
HKD_RATE = 7.75


def _version(description: str) -> str:
    match = re.search(r"\b([A-Z]{3,5})\s*\d+\s*pkSLD\b", description or "", re.I)
    return f"{match.group(1).upper()}版本" if match else ""


def _outer_pack(description: str) -> int | str:
    match = re.search(r"\bGML\s*(\d+)\s*pkSLD\b", description or "", re.I)
    return int(match.group(1)) if match else ""


def _records(order: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in order.get("items", []):
        sales_suffix = f"/{item.get('line_no')}" if item.get("line_no") not in (None, "") else ""
        item_parts = [
            item.get("material_group"),
            item.get("material_no"),
            item.get("sales_material"),
            f"{item.get('sales_order') or ''}-{item.get('sales_line_item') or ''}".strip("-"),
        ]
        quantity = float(item.get("quantity") or 0)
        outer_pack = _outer_pack(item.get("description") or "")
        unit_usd = (
            round(float(item.get("price_per_1000_usd") or 0) / 1000, 6)
            if item.get("price_per_1000_usd") not in (None, "") else ""
        )
        result.append({
            "order_date": order.get("order_date"),
            "contact": order.get("buyer") or "",
            "customer_po": item.get("customer_po"),
            "contract_no": f"{order.get('po_number') or ''}{sales_suffix}",
            "customer": item.get("customer"),
            "version": _version(item.get("description") or ""),
            "item_no": "/".join(str(value) for value in item_parts if value),
            "product_name": item.get("description"),
            "quantity": quantity,
            "inner_pack": "",
            "outer_pack": outer_pack,
            "cartons": (
                int(quantity / outer_pack)
                if outer_pack and (quantity / outer_pack).is_integer()
                else round(quantity / outer_pack, 2) if outer_pack else ""
            ),
            "special_notes": "",
            "inspection_date": "",
            "ship_date": item.get("delivery_date"),
            "unit_price_hkd": round(unit_usd * HKD_RATE, 6) if unit_usd != "" else "",
            "unit_price_usd": unit_usd,
            "total_hkd": round(float(item.get("net_usd") or 0) * HKD_RATE, 2)
            if item.get("net_usd") not in (None, "") else "",
            "total_usd": item.get("net_usd"),
            "english_name": item.get("description"),
            "source_file": Path(order.get("source") or "").name,
        })
    return result


def generate_new_order(schedule_path: str | Path, po_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    order = parse_po_file(Path(po_path))
    records = _records(order)
    if not records:
        raise ValueError("PO 已读取，但没有识别到产品明细。")
    result = create_new_order_workbook(
        Path(schedule_path),
        Path(output_path),
        records,
        FIELD_ALIASES,
        filename=Path(schedule_path).name,
        sheet_names=("SPIN排期", "SPIN总汇"),
        sheet_title="新单",
    )
    return {"order": order, "records": records, "export": result}


def generate_new_order_batch(
    schedule_path: str | Path,
    po_paths: list[str | Path],
    output_path: str | Path,
) -> dict[str, Any]:
    orders: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    duplicate_count = 0
    for po_path in po_paths:
        order = parse_po_file(Path(po_path))
        order_records = _records(order)
        if not order_records:
            raise ValueError(f"{Path(po_path).name} 已读取，但没有识别到产品明细。")
        orders.append(order)
        for record in order_records:
            key = tuple(
                str(record.get(field) or "").strip().upper()
                for field in (
                    "contract_no",
                    "customer_po",
                    "item_no",
                    "quantity",
                    "ship_date",
                    "unit_price_usd",
                    "total_usd",
                )
            )
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            records.append(record)
    if not records:
        raise ValueError("本批文件没有可生成的新单明细。")
    result = create_new_order_workbook(
        Path(schedule_path),
        Path(output_path),
        records,
        FIELD_ALIASES,
        filename=Path(schedule_path).name,
        sheet_names=("SPIN排期", "SPIN总汇"),
        sheet_title="新单",
    )
    return {
        "orders": orders,
        "records": records,
        "duplicate_count": duplicate_count,
        "export": result,
    }
