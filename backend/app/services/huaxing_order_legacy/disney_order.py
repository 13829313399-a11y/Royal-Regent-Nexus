from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import posixpath
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

from pypdf import PdfReader


ITEM_SHEET = "ITEM表"
ALIASES: dict[str, tuple[str, ...]] = {
    "order_date": ("客出单日期",),
    "po_no": ("PO号",),
    "customer": ("客名",),
    "item_no": ("產品編號", "产品编号"),
    "product_name_en": ("产品名称",),
    "product_name_zh": ("产品名称中文",),
    "quantity": ("PO数量",),
    "outer_pack": ("外箱装箱数",),
    "manual": ("说明书",),
    "artwork": ("彩盒",),
    "date_code": ("日期码",),
    "inspection_date": ("验货日期",),
    "ship_date": ("走货期",),
    "sticker": ("贴纸",),
    "carton_sticker": ("外箱贴纸",),
    "shipping_mark": ("箱唛",),
    "notes": ("备注",),
    "invoice_no": ("发票号",),
    "inspection_result": ("验货结果",),
    "unit_price_usd": ("订单单价USD",),
    "unit_price_hkd": ("单价HK$",),
    "factory_price_hkd": ("出厂价",),
    "total_usd": ("总金额USD",),
    "total_hkd": ("总金额HK$",),
    "factory_total_hkd": ("出厂价总金额HK$",),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value)).strip()


def _number(value: Any) -> float | int | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _date(value: str) -> str:
    normalized = _text(value)
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(normalized, pattern).date().isoformat()
        except ValueError:
            pass
    return ""


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    # Every supported Disney family keeps the PO identity, dates and detail lines
    # on its face page.  The remaining pages are legal terms; extracting them can
    # be hundreds of times slower for some source PDFs and adds no order data.
    face_text = reader.pages[0].extract_text() or ""
    if re.search(r"\b[WL]-\d{7}\b", face_text, re.I) and len(reader.pages) > 1:
        return f"{face_text}\n{reader.pages[1].extract_text() or ''}"
    return face_text


def _document_identity(text: str, filename: str) -> tuple[str, str, str]:
    probe = f"{filename}\n{text[:5000]}"
    for pattern, customer, country in (
        (r"\b([WL]-\d{7})\b", "DISNEY THEME PARK MERCHANDISE", "美国"),
        (r"\b(F\d{14})\b", "DISNEY MERCH SOURCE & DISTRIBUTION", "英国"),
        (r"\b(W\d{4,})\b", "THE DISNEY STORE LTD", "英国"),
        (r"\b(V\d{4,})\b", "DISNEY JAPAN", "日本"),
    ):
        found = re.search(pattern, probe, re.I)
        if found:
            po_no = found.group(1).upper()
            if po_no.startswith("L-"):
                customer = "DISNEYLAND RESORT MERCHANDISE"
            return po_no, customer, country
    return "", "DISNEY", ""


def _document_dates(text: str, po_no: str) -> tuple[str, str]:
    if re.match(r"[WL]-", po_no):
        found = re.search(
            rf"{re.escape(po_no)}\s+(\d{{1,2}}/\d{{1,2}}/\d{{4}})\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})\s+\d+",
            text,
            re.I,
        )
        order = re.search(
            r"EARLIEST SHIP DATE LATEST SHIP DATE ORDER DATE.*?\n"
            r"(?:.*?\n){0,4}?(\d{1,2}/\d{1,2}/\d{4})\s+"
            r"\d{1,2}/\d{1,2}/\d{4}\s+(\d{1,2}/\d{1,2}/\d{4})",
            text,
            re.I,
        )
        return (_date(order.group(2)) if order else "", _date(found.group(1)) if found else "")
    if po_no.startswith("F"):
        found = re.search(
            r"ORDERED\s*SHIP ON\s*ANTICIPATE\s*CANCEL AFTER\s*\n\s*"
            r"(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})",
            text,
            re.I,
        )
        return (_date(found.group(1)), _date(found.group(2))) if found else ("", "")
    if po_no.startswith("W"):
        found = re.search(
            r"OrderDate\s+ShipDate\s+Anticipate\s+Cancel Date\s*\n\s*"
            r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(\d{1,2}-[A-Za-z]{3}-\d{4})",
            text,
            re.I,
        )
        return (_date(found.group(1)), _date(found.group(2))) if found else ("", "")
    if po_no.startswith("V"):
        found = re.search(
            r"ORIGINAL\s+1\s+V\d+\s*\n\s*"
            r"(\d{1,2}/\d{1,2}/\d{2})\s+(\d{1,2}/\d{1,2}/\d{2})",
            text,
            re.I,
        )
        return (_date(found.group(1)), _date(found.group(2))) if found else ("", "")
    return "", ""


def _item_blocks(text: str) -> list[tuple[str, str]]:
    starts = list(re.finditer(r"(?m)^\s*(?:\d+\s+)?(100\d{7})\b", text))
    blocks: list[tuple[str, str]] = []
    seen: set[tuple[str, int]] = set()
    for index, found in enumerate(starts):
        item = found.group(1)
        end = starts[index + 1].start() if index + 1 < len(starts) else min(len(text), found.start() + 1800)
        block = text[found.start():end]
        marker = (item, found.start() // 200)
        if marker not in seen:
            seen.add(marker)
            blocks.append((item, block))
    return blocks


def _parse_item_block(item_no: str, block: str) -> dict[str, Any] | None:
    quantity: float | int | None = None
    unit_price: float | int | None = None
    direct = re.search(
        rf"{re.escape(item_no)}\s+([\d,]+)\s+EA\s+1/EA\s+([\d.]+)",
        block,
        re.I,
    )
    if direct:
        quantity, unit_price = _number(direct.group(1)), _number(direct.group(2))
    if quantity is None:
        no_size = re.search(
            r"([\d.]+)\s+(?:NO SIZE|NOT SIZED)\s+([\d,]+)",
            block,
            re.I,
        )
        if no_size:
            unit_price, quantity = _number(no_size.group(1)), _number(no_size.group(2))
    if quantity is None and "Comments:" in block:
        tails = re.findall(r"(?m)^\s*([\d,]+)\s+([\d.]+)\s*$", block)
        if tails:
            quantity, unit_price = _number(tails[-1][0]), _number(tails[-1][1])
    if quantity is None or unit_price is None:
        return None
    pack = re.search(r"(?:CASE/PK|CASE PACK)\s*[:=]\s*(\d+)", block, re.I)
    if not pack:
        pack = re.search(r"\b(\d+)\s*/\s*1\b", block)
    name_match = re.match(r"\s*(?:\d+\s+)?100\d{7}\s+([^\n]+)", block)
    name = _text(name_match.group(1)) if name_match else ""
    return {
        "item_no": item_no,
        "product_name_en": name,
        "quantity": quantity,
        "outer_pack": _number(pack.group(1)) if pack else None,
        "unit_price_usd": unit_price,
        "total_usd": round(float(quantity) * float(unit_price), 2),
    }


def parse_po(content: bytes, filename: str) -> dict[str, Any]:
    text = _pdf_text(content)
    po_no, customer, country = _document_identity(text, filename)
    if not po_no:
        raise ValueError("未识别 Disney PO 号码")
    order_date, ship_date = _document_dates(text, po_no)
    rows: list[dict[str, Any]] = []
    seen_items: set[tuple[str, Any, Any]] = set()
    for item_no, block in _item_blocks(text):
        row = _parse_item_block(item_no, block)
        if not row:
            continue
        key = (item_no, row["quantity"], row["unit_price_usd"])
        if key in seen_items:
            continue
        seen_items.add(key)
        row.update({
            "po_no": po_no,
            "customer": customer,
            "country": country,
            "order_date": order_date,
            "ship_date": ship_date,
            "source_file": filename,
        })
        rows.append(row)
    if not rows:
        raise ValueError("未识别 Disney PO 产品明细")
    return {"filename": filename, "po_no": po_no, "rows": rows}


def parse_schedule(content: bytes, filename: str) -> dict[str, Any]:
    if Path(filename).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Disney 排期只支持 .xlsx/.xlsm")
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    relationship_namespace = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    )
    package_relationship_namespace = (
        "{http://schemas.openxmlformats.org/package/2006/relationships}"
    )
    with ZipFile(BytesIO(content)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheet_element = next(
            (
                element
                for element in workbook.iter(f"{namespace}sheet")
                if element.attrib.get("name") == ITEM_SHEET
            ),
            None,
        )
        if sheet_element is None:
            raise ValueError("Disney 排期缺少 ITEM表")
        relationship_id = sheet_element.attrib.get(f"{relationship_namespace}id")
        relationships = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        target = next(
            (
                element.attrib.get("Target", "")
                for element in relationships.iter(
                    f"{package_relationship_namespace}Relationship"
                )
                if element.attrib.get("Id") == relationship_id
            ),
            "",
        )
        if not target:
            raise ValueError("Disney ITEM表内部关系缺失")
        sheet_path = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for shared_item in shared_root.iter(f"{namespace}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in shared_item.iter(f"{namespace}t"))
                )
        rows: dict[int, dict[int, Any]] = {}
        sheet_root = ElementTree.fromstring(archive.read(sheet_path))
        for cell in sheet_root.iter(f"{namespace}c"):
            address = cell.attrib.get("r", "")
            coordinate = re.match(r"([A-Z]+)(\d+)", address)
            if not coordinate:
                continue
            column = 0
            for character in coordinate.group(1):
                column = column * 26 + ord(character) - 64
            row_no = int(coordinate.group(2))
            value_node = cell.find(f"{namespace}v")
            inline_node = cell.find(f"{namespace}is")
            raw_value = value_node.text if value_node is not None else ""
            if cell.attrib.get("t") == "s" and raw_value:
                try:
                    value: Any = shared_strings[int(raw_value)]
                except (IndexError, ValueError):
                    value = raw_value
            elif cell.attrib.get("t") == "inlineStr" and inline_node is not None:
                value = "".join(
                    node.text or "" for node in inline_node.iter(f"{namespace}t")
                )
            else:
                value = raw_value
            rows.setdefault(row_no, {})[column] = value
    header_row = next(
        (
            row_no
            for row_no, values in rows.items()
            if row_no <= 10
            and _text(values.get(3)) == "PO号"
            and "編號" in _text(values.get(5))
        ),
        None,
    )
    if header_row is None:
        raise ValueError("Disney ITEM表表头不匹配")
    records: list[dict[str, Any]] = []
    for row_no in sorted(row for row in rows if row > header_row):
        values = rows[row_no]
        item_no = _text(values.get(5))
        po_no = _text(values.get(3))
        if not item_no and not po_no:
            continue
        records.append({
            "po_no": po_no,
            "customer": _text(values.get(4)),
            "item_no": item_no,
            "product_name_en": _text(values.get(6)),
            "product_name_zh": _text(values.get(7)),
            "quantity": _number(values.get(9)),
            "outer_pack": _number(values.get(10)),
            "manual": _text(values.get(11)),
            "artwork": _text(values.get(12)),
            "date_code": _text(values.get(13)),
            "inspection_date": values.get(14),
            "ship_date": values.get(15),
            "unit_price_usd": _number(values.get(24)),
            "factory_price_hkd": _number(values.get(26)),
        })
    return {"sheet": ITEM_SHEET, "records": records}


def enrich_rows(rows: list[dict[str, Any]], schedule_records: list[dict[str, Any]]) -> list[str]:
    fields = ("product_name_en", "product_name_zh", "outer_pack", "manual", "artwork", "date_code")
    candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for record in schedule_records:
        key = _text(record.get("item_no"))
        if not key:
            continue
        for field in fields:
            value = record.get(field)
            if value not in (None, ""):
                candidates[key][field][_text(value).casefold()] = value
    warnings: list[str] = []
    for row in rows:
        key = _text(row.get("item_no"))
        for field in fields:
            values = candidates.get(key, {}).get(field, {})
            if row.get(field) in (None, "") and len(values) == 1:
                row[field] = next(iter(values.values()))
        flags = row.setdefault("flags", [])
        if not _text(row.get("product_name_zh")):
            flags.append({
                "level": "high", "code": "missing_product_name_zh",
                "field": "product_name_zh", "text": "Disney 中文名称未能从当前排期按货号唯一继承，请人工补录",
            })
        flags.append({
            "level": "high", "code": "missing_factory_price_hkd",
            "field": "factory_price_hkd", "text": "Disney 出厂价不从客户 PO 推算，请人工填写出厂价 HKD",
        })
    return warnings
