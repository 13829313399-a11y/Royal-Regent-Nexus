from __future__ import annotations

import io
import math
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable

import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import from_excel
from .common_new_order_excel import create_new_order_workbook


FIELD_TITLES: dict[str, str] = {
    "line_name": "拉名",
    "order_date": "来单日期",
    "change_date": "最终改单日期",
    "contact": "合同联系人",
    "customer_po": "客户PO",
    "contract_no": "合同号",
    "customer": "客名",
    "version": "版本",
    "item_no": "货号",
    "product_name": "产品名称",
    "quantity": "数量",
    "inner_pack": "内装箱",
    "outer_pack": "外装箱",
    "cartons": "总箱数",
    "special_remark": "特别备注",
    "shipping_mark": "箱唛",
    "customer_label": "客供标签/利宝",
    "customer_material": "客供物料",
    "material_ready_date": "来料复期",
    "plastic_ready_date": "胶件复期",
    "carton_ready_date": "纸箱复期",
    "injection_ready_date": "注料复期",
    "line_start_date": "上拉期",
    "finish_date": "完成期",
    "date_code": "日期码",
    "inspection_date": "验货期",
    "customer_inspection_date": "客验货期",
    "po_ship_date": "PO走货期",
    "unit_price_hkd": "单价(港币)",
    "unit_price_usd": "单价(美金)",
    "total_hkd": "总价HK$",
    "total_usd": "总货价（美金）",
    "assembly_cost_hkd": "报价装配工HK$",
    "brand": "品牌名",
    "pre_chase_material_date": "预追客供物料期",
    "certificate": "证书",
    "outer_length_cm": "外箱长cm",
    "outer_width_cm": "外箱宽cm",
    "outer_height_cm": "外箱高cm",
    "cbf": "立方尺",
    "gross_weight_kg": "毛重KG",
    "net_weight_kg": "净重KG",
    "total_cbf": "总立方尺",
    "ship_country": "走货国家",
    "so_close_time": "SO结关时间",
    "confirmation_no": "确认号SH",
    "material_order_no": "备料单号",
    "invoice_date": "发票日期",
    "invoice_no": "发票号码",
    "barcode_item_no": "包装条码货号",
    "entered_system": "是否入系统",
    "shipping_info": "走货信息",
    "terminal": "码头",
    "truck_no": "车次",
    "memo": "备注",
    "so_no": "SO号",
    "etd_eta": "ETD ETA",
    "original_inspection_date": "原验货期",
    "english_name": "英文名称",
    "label_status": "客利宝情况",
    "battery_included": "是否含电池",
    "shipping_followup": "跟进船务",
    "finished_goods": "是否成品",
    "order_status": "目前订单情况",
    "plastic_amount": "塑胶金额",
    "material_amount": "来料金额",
    "material_note": "来料物料备注",
    "unreturned_material_amount": "来料下单未回金额",
    "tail_note": "备注",
}

EXPORT_FIELDS = list(FIELD_TITLES.keys())

DATE_FIELDS = {
    "order_date",
    "change_date",
    "material_ready_date",
    "plastic_ready_date",
    "carton_ready_date",
    "injection_ready_date",
    "line_start_date",
    "finish_date",
    "inspection_date",
    "customer_inspection_date",
    "po_ship_date",
    "pre_chase_material_date",
    "invoice_date",
    "original_inspection_date",
}

NUMBER_FIELDS = {
    "quantity",
    "inner_pack",
    "outer_pack",
    "cartons",
    "unit_price_hkd",
    "unit_price_usd",
    "total_hkd",
    "total_usd",
    "assembly_cost_hkd",
    "outer_length_cm",
    "outer_width_cm",
    "outer_height_cm",
    "cbf",
    "gross_weight_kg",
    "net_weight_kg",
    "total_cbf",
    "plastic_amount",
    "material_amount",
    "unreturned_material_amount",
}

FIELD_ALIASES = {
    "拉名": "line_name",
    "来单日期": "order_date",
    "来单期": "order_date",
    "改单期": "change_date",
    "最终改单日期": "change_date",
    "联系人": "contact",
    "合同联系人": "contact",
    "客户PO": "customer_po",
    "客PO": "customer_po",
    "合同号": "contract_no",
    "客名": "customer",
    "版本": "version",
    "货号": "item_no",
    "产品名称": "product_name",
    "数量": "quantity",
    "内箱": "inner_pack",
    "内装箱": "inner_pack",
    "外箱": "outer_pack",
    "外装箱": "outer_pack",
    "总箱数": "cartons",
    "特别备注": "special_remark",
    "箱唛": "shipping_mark",
    "客供利宝": "customer_label",
    "客供标签利宝": "customer_label",
    "客供标签": "customer_label",
    "客供物料": "customer_material",
    "来料复期": "material_ready_date",
    "胶件复期": "plastic_ready_date",
    "胶件改动": "plastic_ready_date",
    "纸箱复期": "carton_ready_date",
    "注料复期": "injection_ready_date",
    "上拉期": "line_start_date",
    "完成期": "finish_date",
    "日期码": "date_code",
    "验货期": "inspection_date",
    "客验货期": "customer_inspection_date",
    "客验期": "customer_inspection_date",
    "PO走货期": "po_ship_date",
    "单价港币": "unit_price_hkd",
    "单价美金": "unit_price_usd",
    "总价HK$": "total_hkd",
    "总货价美金": "total_usd",
    "报价装配工HK$": "assembly_cost_hkd",
    "品牌名": "brand",
    "预追客供物料期": "pre_chase_material_date",
    "证书": "certificate",
    "外箱长cm": "outer_length_cm",
    "外箱宽cm": "outer_width_cm",
    "外箱高cm": "outer_height_cm",
    "立方尺": "cbf",
    "毛重KG": "gross_weight_kg",
    "净重KG": "net_weight_kg",
    "总立方尺": "total_cbf",
    "走货国家": "ship_country",
    "SO结关时间": "so_close_time",
    "确认号SH": "confirmation_no",
    "备料单号": "material_order_no",
    "发票日期": "invoice_date",
    "发票号码": "invoice_no",
    "包装条码货号": "barcode_item_no",
    "是否入系统": "entered_system",
    "走货信息": "shipping_info",
    "码头": "terminal",
    "车次": "truck_no",
    "备注": "memo",
    "SO号": "so_no",
    "ETDETA": "etd_eta",
    "原验货期": "original_inspection_date",
    "英文名称": "english_name",
    "客利宝情况": "label_status",
    "是否含电池": "battery_included",
    "跟进船务": "shipping_followup",
    "是否成品": "finished_goods",
    "目前订单情况": "order_status",
    "塑胶金额": "plastic_amount",
    "来料金额": "material_amount",
    "来料物料备注": "material_note",
    "来料下单未回金额": "unreturned_material_amount",
}


@dataclass(frozen=True)
class SourceRef:
    kind: str
    path: Path
    member: str | None = None


def normalize_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"[\s/\\]+", "", text)
    text = text.replace("(", "").replace(")", "")
    return text


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return str(value).strip()


def coerce_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value) if float(value).is_integer() else float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def normalize_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 25000 <= float(value) <= 70000:
        try:
            return from_excel(value).date().isoformat()
        except Exception:
            return None
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def normalize_value(field: str, value: Any) -> Any:
    if field in DATE_FIELDS:
        return normalize_date(value)
    if field in NUMBER_FIELDS:
        number = coerce_number(value)
        return number if number is not None else normalize_text(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return normalize_text(value)


def open_source_bytes(ref: SourceRef) -> bytes:
    if ref.kind == "zip":
        if not ref.member:
            raise ValueError("Zip source requires a member name.")
        with zipfile.ZipFile(ref.path) as archive:
            return archive.read(ref.member)
    return ref.path.read_bytes()


def load_openpyxl_workbook(source: str | Path | bytes | BinaryIO, data_only: bool = True):
    if isinstance(source, bytes):
        return load_workbook(io.BytesIO(source), data_only=data_only)
    return load_workbook(source, data_only=data_only)


def find_header_row(ws) -> tuple[int, dict[int, str], dict[int, str]]:
    best: tuple[int, dict[int, str], dict[int, str]] | None = None
    best_score = 0
    for row_idx in range(1, min(ws.max_row, 12) + 1):
        field_by_col: dict[int, str] = {}
        title_by_col: dict[int, str] = {}
        for col_idx in range(1, min(ws.max_column, 120) + 1):
            raw = ws.cell(row_idx, col_idx).value
            label = normalize_label(raw)
            field = FIELD_ALIASES.get(label)
            if field:
                field_by_col[col_idx] = field
                title_by_col[col_idx] = FIELD_TITLES[field]
        required = {"item_no", "product_name", "quantity"}
        score = len(field_by_col) + (8 if required.issubset(set(field_by_col.values())) else 0)
        if score > best_score:
            best_score = score
            best = (row_idx, field_by_col, title_by_col)
    if not best or best_score < 5:
        raise ValueError(f"Could not find a schedule header row in sheet {ws.title!r}.")
    return best


def is_total_row(record: dict[str, Any]) -> bool:
    product = normalize_text(record.get("product_name"))
    item_no = normalize_text(record.get("item_no"))
    contract_no = normalize_text(record.get("contract_no"))
    customer = normalize_text(record.get("customer"))
    if product.startswith("合计") or product in {"总计", "小计"}:
        return True
    return bool(record.get("quantity")) and not any([item_no, contract_no, customer])


def has_order_identity(record: dict[str, Any]) -> bool:
    return any(
        normalize_text(record.get(key))
        for key in ("contract_no", "customer_po", "customer", "item_no", "product_name")
    )


def add_derived_fields(record: dict[str, Any]) -> None:
    qty = coerce_number(record.get("quantity"))
    outer = coerce_number(record.get("outer_pack"))
    cartons = coerce_number(record.get("cartons"))
    if cartons is None and qty is not None and outer:
        calc = qty / outer
        record["cartons"] = int(calc) if float(calc).is_integer() else round(calc, 2)
    record["is_internal_mo"] = is_internal_mo(record)
    flags = build_flags(record)
    record["flags"] = flags
    record["risk_level"] = "high" if any(f["level"] == "high" for f in flags) else (
        "medium" if flags else "normal"
    )


def _business_key(value: Any) -> str:
    text = normalize_text(value).upper()
    if text.endswith(".0"):
        text = text[:-2]
    return re.sub(r"[^A-Z0-9]", "", text)


def enrich_rows_from_schedule(
    rows: list[dict[str, Any]],
    schedule_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Safely inherit confirmed schedule fields.

    Customer/contact fields require an exact contract+item match.  Product name
    may also be inherited from an item when the current schedule has one unique
    Chinese product name for that item.  Ambiguous item mappings are never guessed.
    """
    exact: dict[tuple[str, str], dict[str, Any]] = {}
    item_products: dict[str, dict[str, str]] = {}
    for source in schedule_records:
        contract_key = _business_key(source.get("contract_no"))
        item_key = _business_key(source.get("item_no"))
        if contract_key and item_key:
            exact[(contract_key, item_key)] = source
        product = normalize_text(source.get("product_name"))
        if item_key and product:
            item_products.setdefault(item_key, {})[_business_key(product)] = product

    exact_applied = 0
    product_applied = 0
    product_conflicts: set[str] = set()
    exact_fields = (
        "customer",
        "contact",
        "product_name",
        "shipping_mark",
        "customer_label",
        "ship_country",
    )
    for row in rows:
        contract_key = _business_key(row.get("contract_no"))
        item_key = _business_key(row.get("item_no"))
        source = exact.get((contract_key, item_key))
        if source:
            for field in exact_fields:
                if row.get(field) in (None, "") and source.get(field) not in (None, ""):
                    row[field] = source[field]
                    exact_applied += 1
        if row.get("product_name") in (None, "") and item_key:
            candidates = item_products.get(item_key, {})
            if len(candidates) == 1:
                row["product_name"] = next(iter(candidates.values()))
                product_applied += 1
            elif len(candidates) > 1:
                product_conflicts.add(str(row.get("item_no") or item_key))
        add_derived_fields(row)
    return {
        "exact_fields_applied": exact_applied,
        "product_names_applied": product_applied,
        "product_name_conflicts": sorted(product_conflicts),
    }


def parse_openpyxl_sheet(ws, include_totals: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    header_row, field_by_col, title_by_col = find_header_row(ws)
    records: list[dict[str, Any]] = []
    totals = 0
    for row_idx in range(header_row + 1, ws.max_row + 1):
        record: dict[str, Any] = {
            "row_number": row_idx,
            "source_sheet": ws.title,
        }
        raw: dict[str, Any] = {}
        for col_idx, field in field_by_col.items():
            value = ws.cell(row_idx, col_idx).value
            record[field] = normalize_value(field, value)
            raw[title_by_col[col_idx]] = normalize_value(field, value)
        if not has_order_identity(record):
            continue
        if is_total_row(record):
            totals += 1
            if not include_totals:
                continue
            record["is_total"] = True
        else:
            record["is_total"] = False
        add_derived_fields(record)
        record["raw"] = raw
        records.append(record)
    meta = {
        "sheet": ws.title,
        "header_row": header_row,
        "total_rows_skipped": totals,
        "columns": [FIELD_TITLES[field] for field in field_by_col.values()],
    }
    return records, meta


def pick_schedule_sheet(wb, preferred: str | None = None, allow_po_note: bool = False):
    if preferred and preferred in wb.sheetnames:
        return wb[preferred]
    candidates = []
    for ws in wb.worksheets:
        if not allow_po_note and "PO说明" in ws.title:
            continue
        try:
            header_row, field_by_col, _ = find_header_row(ws)
        except ValueError:
            continue
        score = len(field_by_col)
        if "排货" in ws.title:
            score += 10
        candidates.append((score, header_row, ws))
    if not candidates and not allow_po_note and "PO说明" in wb.sheetnames:
        return wb["PO说明"]
    if not candidates:
        raise ValueError("No usable schedule sheet was found.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][2]


def read_schedule(
    source: str | Path | bytes | BinaryIO,
    *,
    filename: str | None = None,
    sheet_name: str | None = None,
    include_totals: bool = False,
    allow_po_note: bool = False,
) -> dict[str, Any]:
    wb = load_openpyxl_workbook(source, data_only=True)
    ws = pick_schedule_sheet(wb, sheet_name, allow_po_note=allow_po_note)
    records, meta = parse_openpyxl_sheet(ws, include_totals=include_totals)
    summary = summarize_records(records)
    return {
        "filename": filename or "workbook.xlsx",
        "sheet": ws.title,
        "meta": meta,
        "records": records,
        "summary": summary,
        "warnings": [],
    }


def parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def is_internal_mo(record: dict[str, Any]) -> bool:
    remark = normalize_text(record.get("special_remark"))
    customer = normalize_text(record.get("customer"))
    contract = normalize_text(record.get("contract_no"))
    if "MO单" in remark or remark.upper() == "MO":
        return True
    return not customer and contract.startswith(("300", "500"))


def contains_pending(value: Any) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    return any(token in text for token in ("欠", "待", "未", "订购", "TBD", "tbd"))


def build_flags(record: dict[str, Any], today: date | None = None) -> list[dict[str, str]]:
    today = today or date.today()
    flags: list[dict[str, str]] = []
    internal_mo = bool(record.get("is_internal_mo")) or is_internal_mo(record)
    if contains_pending(record.get("customer_label")) or contains_pending(record.get("label_status")):
        flags.append({"level": "medium", "text": "客供标签/利宝待跟进"})
    if contains_pending(record.get("shipping_mark")):
        flags.append({"level": "medium", "text": "箱唛待确认"})
    ship_date = parse_iso_date(record.get("po_ship_date"))
    finish_date = parse_iso_date(record.get("finish_date"))
    if not internal_mo and ship_date and ship_date < today and not finish_date:
        flags.append({"level": "high", "text": "PO走货期已过且未填完成期"})
    if not internal_mo and not ship_date:
        flags.append({"level": "medium", "text": "缺PO走货期"})
    if not record.get("outer_pack") and record.get("quantity"):
        flags.append({"level": "medium", "text": "缺外装箱"})
    if record.get("source_sheet") in {"转换PO", "PDF"} and not normalize_text(record.get("customer")):
        flags.append({"level": "high", "text": "缺客名，禁止无确认写入"})
    if record.get("source_sheet") in {"转换PO", "PDF"} and not normalize_text(record.get("contact")):
        flags.append({"level": "medium", "text": "缺合同联系人"})
    return flags


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for r in records if not r.get("is_total")]
    quantity = sum(float(coerce_number(r.get("quantity")) or 0) for r in rows)
    cartons = sum(float(coerce_number(r.get("cartons")) or 0) for r in rows)
    customer_rows = [r for r in rows if not r.get("is_internal_mo") and normalize_text(r.get("customer"))]
    customers = Counter(normalize_text(r.get("customer")) for r in customer_rows)
    contacts = Counter(normalize_text(r.get("contact")) or "未填联系人" for r in rows)
    months: defaultdict[str, float] = defaultdict(float)
    for record in rows:
        ship_date = parse_iso_date(record.get("po_ship_date"))
        if ship_date:
            months[ship_date.strftime("%Y-%m")] += float(coerce_number(record.get("quantity")) or 0)
    flagged = [r for r in rows if r.get("flags")]
    high = [r for r in rows if r.get("risk_level") == "high"]
    return {
        "orders": len(rows),
        "quantity": int(quantity) if quantity.is_integer() else round(quantity, 2),
        "cartons": int(cartons) if cartons.is_integer() else round(cartons, 2),
        "contracts": len({normalize_text(r.get("contract_no")) for r in rows if normalize_text(r.get("contract_no"))}),
        "items": len({normalize_text(r.get("item_no")) for r in rows if normalize_text(r.get("item_no"))}),
        "customers": len(customers),
        "internal_mo": sum(1 for r in rows if r.get("is_internal_mo")),
        "flagged": len(flagged),
        "high_risk": len(high),
        "pending_label": sum(1 for r in rows if contains_pending(r.get("customer_label")) or contains_pending(r.get("label_status"))),
        "missing_ship_date": sum(1 for r in rows if not r.get("is_internal_mo") and not r.get("po_ship_date")),
        "top_customers": customers.most_common(8),
        "top_contacts": contacts.most_common(8),
        "monthly_quantity": sorted(months.items()),
    }


def autosize_columns(ws, max_width: int = 42) -> None:
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        width = 10
        for cell in ws[letter]:
            text = "" if cell.value is None else str(cell.value)
            width = max(width, min(max_width, len(text) + 2))
        ws.column_dimensions[letter].width = width


def write_records_sheet(ws, records: list[dict[str, Any]], *, yellow_rows: bool = False) -> None:
    headers = [FIELD_TITLES[field] for field in EXPORT_FIELDS]
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="233647")
    header_font = Font(color="FFFFFF", bold=True)
    yellow_fill = PatternFill("solid", fgColor="FFF2CC")
    risk_fill = PatternFill("solid", fgColor="F8CBAD")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for record in records:
        row = [record.get(field) for field in EXPORT_FIELDS]
        ws.append(row)
        fill = risk_fill if record.get("risk_level") == "high" else (yellow_fill if yellow_rows else None)
        if fill:
            for cell in ws[ws.max_row]:
                cell.fill = fill
        for cell in ws[ws.max_row]:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    autosize_columns(ws)


def create_summary_workbook(records: list[dict[str, Any]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_records(records)
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append(["指标", "数值"])
    rows = [
        ("订单行数", summary["orders"]),
        ("合同数", summary["contracts"]),
        ("货号数", summary["items"]),
        ("客户数", summary["customers"]),
        ("总数量", summary["quantity"]),
        ("总箱数", summary["cartons"]),
        ("需跟进", summary["flagged"]),
        ("高风险", summary["high_risk"]),
        ("缺PO走货期", summary["missing_ship_date"]),
        ("客供标签/利宝待跟进", summary["pending_label"]),
    ]
    for row in rows:
        ws.append(row)
    ws.append([])
    ws.append(["客户", "订单行数"])
    for customer, count in summary["top_customers"]:
        ws.append([customer, count])
    ws.append([])
    ws.append(["走货月份", "数量"])
    for month, qty in summary["monthly_quantity"]:
        ws.append([month, qty])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
    autosize_columns(ws)

    detail = wb.create_sheet("订单明细")
    write_records_sheet(detail, records)
    wb.save(output_path)
    return output_path


def create_import_workbook(
    rows: list[dict[str, Any]],
    output_path: Path,
    template_source: str | Path | bytes | BinaryIO | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if template_source is not None:
        prepared = []
        for source in rows:
            row = dict(source)
            add_derived_fields(row)
            prepared.append(row)
        create_new_order_workbook(
            template_source,
            output_path,
            prepared,
            {field: (title,) for field, title in FIELD_TITLES.items()},
            sheet_title="新单",
        )
        return output_path
    wb = Workbook()
    ws = wb.active
    ws.title = "新单"
    for row in rows:
        add_derived_fields(row)
    write_records_sheet(ws, rows, yellow_rows=True)
    wb.save(output_path)
    return output_path


def records_from_zip_member(zip_path: Path, member: str) -> dict[str, Any]:
    ref = SourceRef(kind="zip", path=zip_path, member=member)
    return read_schedule(open_source_bytes(ref), filename=f"{zip_path.name}!{member}")
