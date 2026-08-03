from __future__ import annotations

import io
import math
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from .new_order_excel import create_new_order_workbook


EXCHANGE_RATE = 7.75

FIELD_TITLES = {
    "order_date": "出单日期",
    "so_no": "SO",
    "contract_no": "银辉合同号",
    "customer": "客名",
    "item_no": "产品编号",
    "product_name": "产品名称",
    "spec": "规格",
    "quantity": "PO数量",
    "case_pack": "装箱数量",
    "cartons": "总箱数",
    "manual": "说明书",
    "artwork": "彩盒",
    "customer_label": "客贴纸",
    "date_code": "日期码",
    "memo": "备注",
    "shipping_mark": "箱唛资料",
    "inspection_date": "验货日期",
    "factory_review_date": "华兴复期",
    "po_ship_date": "走货期",
    "unit_price_usd": "订单单价USD",
    "unit_price_hkd": "单价HK$",
    "total_hkd": "总金额HK$",
    "total_usd": "总金额USD",
    "factory_unit_price_hkd": "出厂价HK$",
    "factory_total_hkd": "出厂价总金额HK$",
}
EXPORT_FIELDS = list(FIELD_TITLES)


def normalize_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("（", "(").replace("）", ")")
    return re.sub(r"[\s/\\_()]+", "", text)


ALIASES = {
    normalize_label(title): field for field, title in FIELD_TITLES.items()
}
ALIASES.update({
    "来单日期": "order_date",
    "po号": "contract_no",
    "產品編號": "item_no",
    "產品名稱": "product_name",
    "裝箱數量": "case_pack",
    "裝箱隻數": "case_pack",
    "箱数": "cartons",
    "验货期": "inspection_date",
    "订单单价usd": "unit_price_usd",
    "单价hk$": "unit_price_hkd",
    "总金额hk$": "total_hkd",
    "总金额usd": "total_usd",
    "出厂价": "factory_unit_price_hkd",
    "出厂单价": "factory_unit_price_hkd",
})

DATE_FIELDS = {"order_date", "inspection_date", "factory_review_date", "po_ship_date"}
NUMBER_FIELDS = {
    "quantity", "case_pack", "cartons", "unit_price_usd", "unit_price_hkd",
    "total_hkd", "total_usd", "factory_unit_price_hkd", "factory_total_hkd",
}


@dataclass(frozen=True)
class SourceRef:
    kind: str
    path: Path
    member: str | None = None


def open_source_bytes(ref: SourceRef) -> bytes:
    if ref.kind == "zip":
        if not ref.member:
            raise ValueError("压缩包内文件名不能为空")
        with zipfile.ZipFile(ref.path) as archive:
            return archive.read(ref.member)
    return ref.path.read_bytes()


def source_bytes(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if hasattr(source, "read"):
        return source.read()
    return Path(source).read_bytes()


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def number_value(value: Any) -> float | int | None:
    if value in (None, "", "-") or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else round(number, 4)


def date_value(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def as_date(value: Any) -> date | None:
    normalized = date_value(value)
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def decode_date_code(value: Any, reference_year: int | None = None) -> date | None:
    match = re.fullmatch(r"(\d{3})B(\d)RR", text_value(value) or "", re.I)
    if not match:
        return None
    ordinal, year_digit = int(match.group(1)), int(match.group(2))
    if ordinal < 1 or ordinal > 366:
        return None
    decade = ((reference_year or date.today().year) // 10) * 10
    year = decade + year_digit
    try:
        return date(year, 1, 1) + timedelta(days=ordinal - 1)
    except ValueError:
        return None


def make_date_code(value: Any) -> str | None:
    target = as_date(value)
    if not target:
        return None
    return f"{target.timetuple().tm_yday:03d}B{target.year % 10}RR"


def add_derived_fields(record: dict[str, Any], today: date | None = None) -> None:
    for field in DATE_FIELDS:
        record[field] = date_value(record.get(field))
    for field in NUMBER_FIELDS:
        record[field] = number_value(record.get(field))
    for field in set(FIELD_TITLES) - DATE_FIELDS - NUMBER_FIELDS:
        record[field] = text_value(record.get(field))

    quantity = record.get("quantity")
    pack = record.get("case_pack")
    usd = record.get("unit_price_usd")
    hkd = record.get("unit_price_hkd")
    factory = record.get("factory_unit_price_hkd")
    if record.get("cartons") is None and quantity is not None and pack:
        record["cartons"] = round(float(quantity) / float(pack), 2)
    if hkd is None and usd is not None:
        hkd = record["unit_price_hkd"] = round(float(usd) * EXCHANGE_RATE, 4)
    if record.get("total_usd") is None and quantity is not None and usd is not None:
        record["total_usd"] = round(float(quantity) * float(usd), 2)
    if record.get("total_hkd") is None and quantity is not None and hkd is not None:
        record["total_hkd"] = round(float(quantity) * float(hkd), 2)
    if record.get("factory_total_hkd") is None and quantity is not None and factory is not None:
        record["factory_total_hkd"] = round(float(quantity) * float(factory), 2)
    if not record.get("inspection_date") and record.get("po_ship_date"):
        ship = as_date(record["po_ship_date"])
        if ship:
            record["inspection_date"] = (ship - timedelta(days=5)).isoformat()

    ref = as_date(record.get("inspection_date")) or as_date(record.get("order_date"))
    decoded = decode_date_code(record.get("date_code"), ref.year if ref else None)
    record["date_code_date"] = decoded.isoformat() if decoded else None
    record["flags"] = build_flags(record, today=today)
    record["risk_level"] = (
        "high" if any(flag["level"] == "high" for flag in record["flags"])
        else "medium" if record["flags"] else "normal"
    )


def build_flags(record: dict[str, Any], today: date | None = None) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    required = {
        "so_no": "缺SO", "contract_no": "缺银辉合同号", "customer": "缺客名",
        "item_no": "缺产品编号", "product_name": "缺产品名称", "quantity": "缺PO数量",
        "case_pack": "缺装箱数量", "inspection_date": "缺验货日期",
        "po_ship_date": "缺走货期", "unit_price_usd": "缺订单单价USD",
    }
    for field, message in required.items():
        if record.get(field) in (None, "", 0):
            flags.append({"level": "high", "code": f"missing_{field}", "text": message})

    code = record.get("date_code")
    if not code:
        flags.append({"level": "medium", "code": "missing_date_code", "text": "日期码待填写"})
    elif not record.get("date_code_date"):
        flags.append({"level": "high", "code": "invalid_date_code", "text": "日期码格式应为日期序号+B年码+RR（例：183B6RR）"})

    quantity, pack, cartons = record.get("quantity"), record.get("case_pack"), record.get("cartons")
    if quantity is not None and pack and cartons is not None and abs(float(cartons) - float(quantity) / float(pack)) > 0.02:
        flags.append({"level": "high", "code": "carton_mismatch", "text": "总箱数与PO数量/装箱数量不一致"})

    ship = as_date(record.get("po_ship_date"))
    inspection = as_date(record.get("inspection_date"))
    if ship and inspection and inspection != ship - timedelta(days=5):
        flags.append({"level": "medium", "code": "inspection_review", "text": "验货日期不是走货期前5天，请复核"})
    reference = today or date.today()
    if ship and ship < reference:
        flags.append({"level": "high", "code": "overdue", "text": "走货期已过"})
    elif ship and (ship - reference).days <= 14:
        flags.append({"level": "medium", "code": "ship_soon", "text": "14天内走货"})

    for field, label in (("shipping_mark", "箱唛资料"), ("manual", "说明书"), ("artwork", "彩盒")):
        if not record.get(field):
            flags.append({"level": "medium", "code": f"missing_{field}", "text": f"{label}待确认"})
    return flags


def find_header(ws) -> tuple[int, dict[int, str]]:
    best_row, best_map = 0, {}
    for row in range(1, min(ws.max_row, 15) + 1):
        mapping: dict[int, str] = {}
        for col in range(1, min(ws.max_column, 100) + 1):
            field = ALIASES.get(normalize_label(ws.cell(row, col).value))
            if field:
                mapping[col] = field
        score = len(mapping) + (10 if {"item_no", "quantity", "customer"}.issubset(mapping.values()) else 0)
        best_score = len(best_map) + (10 if {"item_no", "quantity", "customer"}.issubset(best_map.values()) else 0)
        if score > best_score:
            best_row, best_map = row, mapping
    if len(best_map) < 6:
        raise ValueError(f"工作表“{ws.title}”未找到银辉排期表头")
    return best_row, best_map


def read_schedule(source: str | Path | bytes | BinaryIO, filename: str | None = None) -> dict[str, Any]:
    data = source_bytes(source)
    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    candidates = sorted(workbook.worksheets, key=lambda ws: (ws.title.strip() not in {"Iteam表", "ITEM表"}, ws.title))
    last_error: Exception | None = None
    for ws in candidates:
        try:
            header_row, mapping = find_header(ws)
        except ValueError as exc:
            last_error = exc
            continue
        records: list[dict[str, Any]] = []
        for row in range(header_row + 1, ws.max_row + 1):
            record = {field: ws.cell(row, col).value for col, field in mapping.items()}
            identity = any(record.get(field) not in (None, "") for field in ("so_no", "contract_no", "item_no", "product_name"))
            if not identity:
                continue
            if text_value(record.get("item_no")) in {"合计", "总计", "小计"}:
                continue
            record["source_sheet"] = ws.title
            record["source_row"] = row
            add_derived_fields(record)
            records.append(record)
        if records:
            return {
                "filename": filename or "银辉排期.xlsx",
                "sheet": ws.title,
                "records": records,
                "summary": summarize_records(records),
                "meta": {"header_row": header_row, "columns": len(mapping), "sheet_names": workbook.sheetnames},
                "warnings": [],
            }
    raise ValueError(str(last_error or "Excel中未找到可识别的银辉排期明细"))


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    customers = Counter(str(row.get("customer") or "待确认") for row in rows)
    months: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        ship = as_date(row.get("po_ship_date"))
        if ship:
            months[ship.strftime("%Y-%m")] += float(row.get("quantity") or 0)
    return {
        "orders": len(rows),
        "contracts": len({row.get("contract_no") for row in rows if row.get("contract_no")}),
        "quantity": round(sum(float(row.get("quantity") or 0) for row in rows), 2),
        "cartons": round(sum(float(row.get("cartons") or 0) for row in rows), 2),
        "total_usd": round(sum(float(row.get("total_usd") or 0) for row in rows), 2),
        "total_hkd": round(sum(float(row.get("total_hkd") or 0) for row in rows), 2),
        "high_risk": sum(row.get("risk_level") == "high" for row in rows),
        "flagged": sum(row.get("risk_level") != "normal" for row in rows),
        "top_customers": customers.most_common(8),
        "monthly_quantity": sorted(months.items()),
    }


def create_export(
    records: list[dict[str, Any]],
    output_path: Path,
    template_source: bytes | BinaryIO | str | Path | None = None,
) -> Path:
    if template_source is not None:
        prepared = []
        for source in records:
            record = dict(source)
            add_derived_fields(record)
            prepared.append(record)
        aliases = {
            field: tuple(
                dict.fromkeys(
                    [title] + [alias for alias, target in ALIASES.items() if target == field]
                )
            )
            for field, title in FIELD_TITLES.items()
        }
        create_new_order_workbook(
            template_source,
            output_path,
            prepared,
            aliases,
            filename="schedule.xlsx",
            sheet_title="新单",
        )
        return output_path
    wb = Workbook()
    summary = summarize_records(records)
    ws = wb.active
    ws.title = "汇总"
    ws.append(["指标", "数值"])
    for label, key in (("订单行", "orders"), ("合同数", "contracts"), ("PO数量", "quantity"),
                       ("总箱数", "cartons"), ("总金额USD", "total_usd"),
                       ("总金额HK$", "total_hkd"), ("需复核", "flagged"), ("高风险", "high_risk")):
        ws.append([label, summary[key]])
    detail = wb.create_sheet("Iteam明细")
    detail.append([FIELD_TITLES[field] for field in EXPORT_FIELDS] + ["系统校验"])
    for record in records:
        detail.append([record.get(field) for field in EXPORT_FIELDS] + ["；".join(flag["text"] for flag in record.get("flags", []))])
    header_fill = PatternFill("solid", fgColor="27364B")
    risk_fill = PatternFill("solid", fgColor="FCE8E6")
    for sheet in (ws, detail):
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.freeze_panes = "A2"
        for col in range(1, sheet.max_column + 1):
            width = max(len(str(sheet.cell(row, col).value or "")) for row in range(1, sheet.max_row + 1))
            sheet.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 10), 32)
    for index, record in enumerate(records, start=2):
        if record.get("risk_level") == "high":
            for cell in detail[index]:
                cell.fill = risk_fill
    detail.auto_filter.ref = detail.dimensions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
