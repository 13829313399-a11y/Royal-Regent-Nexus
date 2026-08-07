from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonOrder, CartonOrderLine


MAX_IMPORT_ROWS = 5_000
MAX_PREVIEW_ROWS = 500
PACKAGING_TYPES = (
    "压线卡",
    "半亦箱",
    "全亦箱",
    "滑板纸",
    "展示盒",
    "内箱",
    "外箱",
    "平卡",
    "压卡",
    "啤卡",
    "刀卡",
    "卡纸",
    "天盖",
    "地盖",
    "纸箱",
)


WEEKLY_ALIASES = {
    "contract_no": {"reference", "合同号", "合同", "sc", "参考号"},
    "po_numbers": {"pono", "po", "po号", "客户po", "订单号"},
    "customer_name": {"客名国家", "客名", "客户", "国家", "customer"},
    "item_no": {"产品编号", "货号", "客货号", "itemno", "item"},
    "product_name": {"产品名称", "品名", "description", "productname"},
    "quantity": {"数量", "订单数量", "qty", "quantity"},
    "carton_rule": {"装箱", "包装", "装箱方式", "pack", "packing"},
    "inspection_window": {"验货期请提前准备好货物", "验货期", "查货期", "inspectiondate"},
}

DELIVERY_ALIASES = {
    "delivery_date": {"日期", "送货日期", "入库日期", "date"},
    "delivery_note_no": {"入库单号", "送货单号", "送货单", "dnno", "dn"},
    "contract_no": {"po", "合同号", "合同", "pono", "订单编号"},
    "item_no": {"货号", "产品编号", "itemno", "item"},
    "quantity": {"外箱", "送货数量", "数量", "入库数量", "qty", "quantity"},
    "paper_quality": {"纸质", "材质", "paperquality", "description"},
    "length": {"长", "l", "length"},
    "width": {"宽", "w", "width"},
    "height": {"高", "h", "height"},
    "unit_price": {"单价", "unitprice", "price"},
    "location": {"仓位", "库位", "location"},
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", _text(value).lower())


def _identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _number(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _json_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _date_text(value: Any, datemode: int = 0) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 20_000 <= float(value) <= 80_000:
        if datemode:
            try:
                import xlrd  # type: ignore

                return xlrd.xldate_as_datetime(float(value), datemode).date().isoformat()
            except Exception:
                pass
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    return ""


def _sheet_rows(filename: str, content: bytes) -> list[tuple[str, list[list[Any]], int]]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook  # type: ignore

            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"无法读取 Excel 文件：{exc}") from exc
        result: list[tuple[str, list[list[Any]], int]] = []
        try:
            for sheet in workbook.worksheets:
                rows = [list(row) for row in sheet.iter_rows(values_only=True, max_row=MAX_IMPORT_ROWS)]
                result.append((sheet.title, rows, 0))
        finally:
            workbook.close()
        return result
    if suffix == ".xls":
        try:
            import xlrd  # type: ignore

            workbook = xlrd.open_workbook(file_contents=content, formatting_info=False)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"无法读取旧版 XLS 文件：{exc}") from exc
        return [
            (
                sheet.name,
                [sheet.row_values(index) for index in range(min(sheet.nrows, MAX_IMPORT_ROWS))],
                workbook.datemode,
            )
            for sheet in workbook.sheets()
        ]
    raise HTTPException(status_code=422, detail="该导入类型需要 Excel 文件")


def _header_mapping(rows: list[list[Any]], aliases: dict[str, set[str]]) -> tuple[int, dict[str, int]] | None:
    normalized_aliases = {
        field: {_header_key(alias) for alias in names}
        for field, names in aliases.items()
    }
    best: tuple[int, dict[str, int]] | None = None
    for row_index, row in enumerate(rows[:20]):
        mapping: dict[str, int] = {}
        for column_index, value in enumerate(row):
            key = _header_key(value)
            if not key:
                continue
            for field, names in normalized_aliases.items():
                if field not in mapping and key in names:
                    mapping[field] = column_index
        if best is None or len(mapping) > len(best[1]):
            best = row_index, mapping
    return best


def _cell(row: list[Any], mapping: dict[str, int], field: str) -> Any:
    index = mapping.get(field)
    return row[index] if index is not None and index < len(row) else None


def _split_paper(value: Any) -> tuple[str, str]:
    text = _text(value)
    for packaging_type in PACKAGING_TYPES:
        if text.lower().endswith(packaging_type.lower()):
            quality = text[: -len(packaging_type)].strip(" /-")
            return quality or "待复核", packaging_type
    return text or "待复核", "待复核"


def _specification(row: list[Any], mapping: dict[str, int]) -> str:
    dimensions = [_number(_cell(row, mapping, field)) for field in ("length", "width", "height")]
    present = [str(value.normalize()) for value in dimensions if value is not None]
    return " × ".join(present) + (" in" if present else "")


def _parse_weekly(filename: str, content: bytes) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for sheet_name, rows, _ in _sheet_rows(filename, content):
        header = _header_mapping(rows, WEEKLY_ALIASES)
        if header is None or not {"contract_no", "quantity"}.issubset(header[1]):
            if any(any(_text(cell) for cell in row) for row in rows[:20]):
                warnings.append(f"工作表“{sheet_name}”未找到可识别的排期表头")
            continue
        header_index, mapping = header
        for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            contract_no = _text(_cell(row, mapping, "contract_no"))
            item_no = _text(_cell(row, mapping, "item_no"))
            amount = _number(_cell(row, mapping, "quantity"))
            if not contract_no and not item_no:
                continue
            if amount is None or amount <= 0:
                warnings.append(f"{sheet_name} 第 {source_row} 行数量无效，已跳过")
                continue
            parsed.append(
                {
                    "source_sheet": sheet_name,
                    "source_row": source_row,
                    "reference": contract_no,
                    "contract_no": contract_no,
                    "po_numbers": _text(_cell(row, mapping, "po_numbers")),
                    "customer_name": _text(_cell(row, mapping, "customer_name")),
                    "item_no": item_no,
                    "product_name": _text(_cell(row, mapping, "product_name")),
                    "quantity": _json_number(amount),
                    "carton_rule": _text(_cell(row, mapping, "carton_rule")),
                    "inspection_window": _text(_cell(row, mapping, "inspection_window")),
                }
            )
            if len(parsed) >= MAX_PREVIEW_ROWS:
                warnings.append(f"导入预览最多显示 {MAX_PREVIEW_ROWS} 行，其余行未进入本批次")
                return {"rows": parsed, "warnings": warnings, "engine": "excel-header-mapping"}
    if not parsed:
        raise HTTPException(status_code=422, detail="未在文件中找到可识别的每周查货排期明细")
    return {"rows": parsed, "warnings": warnings, "engine": "excel-header-mapping"}


def _parse_delivery_spreadsheet(filename: str, content: bytes) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for sheet_name, rows, datemode in _sheet_rows(filename, content):
        header = _header_mapping(rows, DELIVERY_ALIASES)
        if header is None or not {"item_no", "quantity"}.issubset(header[1]):
            continue
        header_index, mapping = header
        for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            delivery_note_no = _text(_cell(row, mapping, "delivery_note_no"))
            contract_no = _text(_cell(row, mapping, "contract_no"))
            item_no = _text(_cell(row, mapping, "item_no"))
            amount = _number(_cell(row, mapping, "quantity"))
            if not any((delivery_note_no, contract_no, item_no)):
                continue
            if amount is None or amount <= 0:
                continue
            paper_quality, packaging_type = _split_paper(_cell(row, mapping, "paper_quality"))
            parsed.append(
                {
                    "source_sheet": sheet_name,
                    "source_row": source_row,
                    "delivery_note_no": delivery_note_no,
                    "delivery_date": _date_text(_cell(row, mapping, "delivery_date"), datemode),
                    "contract_no": contract_no,
                    "item_no": item_no,
                    "packaging_type": packaging_type,
                    "paper_quality": paper_quality,
                    "specification": _specification(row, mapping),
                    "delivered_quantity": _json_number(amount),
                    "unit_price": _json_number(_number(_cell(row, mapping, "unit_price"))) or 0,
                    "location": _text(_cell(row, mapping, "location")),
                }
            )
            if len(parsed) >= MAX_PREVIEW_ROWS:
                warnings.append(f"导入预览最多显示 {MAX_PREVIEW_ROWS} 行，其余行未进入本批次")
                return {"rows": parsed, "warnings": warnings, "engine": "excel-header-mapping"}
    if not parsed:
        raise HTTPException(status_code=422, detail="未在文件中找到可识别的送货或入库明细")
    return {"rows": parsed, "warnings": warnings, "engine": "excel-header-mapping"}


def _document_text(suffix: str, content: bytes) -> tuple[str, str, str]:
    if suffix == ".pdf":
        from app.services.carton_mark import extract_pdf_text

        text, status = extract_pdf_text(content)
    else:
        from app.services.carton_mark import extract_image_text

        text, status = extract_image_text(content, source="delivery_note")
    return text, status.engine, status.message


def _parse_delivery_document(filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    text, engine, message = _document_text(suffix, content)
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not compact:
        raise HTTPException(status_code=422, detail=message or "未能从送货单中识别文字")
    delivery_note_match = re.search(r"\bDN\s*[-.:]?\s*([A-Z0-9/-]{5,})", compact, re.IGNORECASE)
    delivery_note_no = f"DN{delivery_note_match.group(1)}" if delivery_note_match else ""
    date_match = re.search(r"\b(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})", compact)
    delivery_date = (
        date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))).isoformat()
        if date_match
        else ""
    )
    contract_tokens = re.findall(r"\b(?:SC\d{6,}(?:[/.-]\d+)?|[A-Z]{1,4}\d{5,}(?:-\d+)?)\b", compact, re.IGNORECASE)
    item_tokens = re.findall(r"\b(?:W?[0-9]{4,}[A-Z0-9]*|[A-Z]\d{4,}[A-Z0-9-]*)\b", compact, re.IGNORECASE)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, contract_no in enumerate(contract_tokens[:50]):
        nearby = item_tokens[index] if index < len(item_tokens) else ""
        key = (_identity(contract_no), _identity(nearby))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_sheet": "OCR",
                "source_row": index + 1,
                "delivery_note_no": delivery_note_no,
                "delivery_date": delivery_date,
                "contract_no": contract_no,
                "item_no": nearby,
                "packaging_type": "待复核",
                "paper_quality": "待复核",
                "specification": "",
                "delivered_quantity": 0,
                "unit_price": 0,
                "location": "",
            }
        )
    warnings = ["图片/PDF 仅作为 OCR 预览，数量和纸品字段必须逐行人工复核"]
    if message:
        warnings.append(message)
    return {
        "rows": rows,
        "warnings": warnings,
        "engine": engine,
        "document": {
            "delivery_note_no": delivery_note_no,
            "delivery_date": delivery_date,
            "raw_text_excerpt": compact[:3000],
        },
    }


def _match_rows(db: Session, factory_id: str, import_type: str, rows: list[dict[str, Any]]) -> None:
    joined = list(
        db.execute(
            select(CartonOrderLine, CartonOrder)
            .join(CartonOrder, CartonOrder.id == CartonOrderLine.order_id)
            .where(
                CartonOrder.factory_id == factory_id,
                CartonOrder.status != "CANCELLED",
            )
        ).all()
    )
    for row in rows:
        contract_key = _identity(row.get("contract_no"))
        item_key = _identity(row.get("item_no"))
        exact = [
            (line, order)
            for line, order in joined
            if contract_key
            and item_key
            and _identity(order.contract_no) == contract_key
            and _identity(order.item_no) == item_key
        ]
        candidates = exact
        basis = "合同号 + 货号" if exact else ""
        if not candidates and contract_key:
            by_contract = [(line, order) for line, order in joined if _identity(order.contract_no) == contract_key]
            if len({order.id for _, order in by_contract}) == 1:
                candidates = by_contract
                basis = "合同号"
        if not candidates and item_key:
            by_item = [(line, order) for line, order in joined if _identity(order.item_no) == item_key]
            if len({order.id for _, order in by_item}) == 1:
                candidates = by_item
                basis = "唯一货号"

        if import_type == "DELIVERY_NOTE" and candidates:
            packaging = _text(row.get("packaging_type"))
            paper_quality = _text(row.get("paper_quality"))
            narrowed = [
                pair
                for pair in candidates
                if packaging not in {"", "待复核"}
                and pair[0].packaging_type == packaging
                and (paper_quality in {"", "待复核"} or pair[0].paper_quality.lower() == paper_quality.lower())
            ]
            if narrowed:
                candidates = narrowed
                basis += " + 纸品"

        unique_orders = {order.id: order for _, order in candidates}
        if import_type == "WEEKLY_SCHEDULE":
            if len(unique_orders) == 1:
                order = next(iter(unique_orders.values()))
                row.update(
                    {
                        "order_id": order.id,
                        "order_no": order.order_no,
                        "customer_code": order.customer_code,
                        "customer_name": order.customer_name,
                        "match_basis": basis,
                    }
                )
                schedule_quantity = _number(row.get("quantity")) or Decimal(0)
                if schedule_quantity != Decimal(order.product_order_quantity):
                    row["match_status"] = "QUANTITY_MISMATCH"
                    row["suggestion"] = f"排期数量 {schedule_quantity} 与订单数量 {order.product_order_quantity} 不一致，请人工确认"
                else:
                    row["match_status"] = "MATCHED"
                    row["suggestion"] = "已匹配正式纸箱订单"
            else:
                row["match_status"] = "AMBIGUOUS" if candidates else "MISSING_ORDER"
                row["suggestion"] = "找到多个候选订单，请人工选择" if candidates else "未找到正式纸箱订单，仅生成异常待办"
            continue

        if len(candidates) == 1:
            line, order = candidates[0]
            row.update(
                {
                    "order_line_id": line.id,
                    "order_id": order.id,
                    "order_no": order.order_no,
                    "customer_code": order.customer_code,
                    "customer_name": order.customer_name,
                    "contract_no": order.contract_no,
                    "item_no": order.item_no,
                    "packaging_type": line.packaging_type,
                    "paper_quality": line.paper_quality,
                    "specification": line.specification,
                    "unit": line.unit,
                    "match_basis": basis,
                    "match_status": "MATCHED",
                }
            )
        else:
            row["match_status"] = "AMBIGUOUS" if candidates else "MISSING_ORDER"
            row["suggestion"] = "找到多条纸品明细，请人工选择" if candidates else "未找到可关联的正式订单明细"


def parse_carton_import(
    db: Session,
    factory_id: str,
    import_type: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if import_type == "WEEKLY_SCHEDULE":
        parsed = _parse_weekly(filename, content)
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        parsed = _parse_delivery_spreadsheet(filename, content)
    else:
        parsed = _parse_delivery_document(filename, content)
    rows = parsed.get("rows", [])
    _match_rows(db, factory_id, import_type, rows)
    matched = sum(1 for row in rows if row.get("match_status") == "MATCHED")
    issues = len(rows) - matched
    parsed.update(
        {
            "message": "导入内容已解析并生成待复核预览；不会自动创建订单或库存",
            "creates_order": False,
            "creates_inventory": False,
            "row_count": len(rows),
            "matched_count": matched,
            "issue_count": issues,
        }
    )
    return parsed
