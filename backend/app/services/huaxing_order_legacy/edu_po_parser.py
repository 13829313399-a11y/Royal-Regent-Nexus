from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable

import pdfplumber

from .edu_schedule import add_derived_fields, read_schedule


def _read_bytes(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if hasattr(source, "read"):
        return source.read()
    return Path(source).read_bytes()


def _date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _number(value: str | None) -> float | int | None:
    if not value:
        return None
    result = float(value.replace(",", ""))
    return int(result) if result.is_integer() else result


def read_pdf_text(source: str | Path | bytes | BinaryIO) -> tuple[str, int]:
    data = _read_bytes(source)
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
        return "\n".join(pages), len(pdf.pages)


def _search(pattern: str, text: str, flags: int = re.I) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _infer_pack(item_no: str, block_pack: int | None) -> int | None:
    match = re.search(r"E(\d+)(?:-|$)", item_no, re.I)
    if match:
        return int(match.group(1))
    return block_pack


def parse_caixing_pdf(source: str | Path | bytes | BinaryIO, filename: str = "po.pdf") -> dict[str, Any]:
    text, pages = read_pdf_text(source)
    if not text.strip():
        return {"filename": filename, "type": "pdf", "customer_type": "彩星", "rows": [],
                "meta": {"pages": pages}, "warnings": ["PDF 未提取到文字，可能是扫描件。"]}

    po = _search(r"PURCHASE ORDER NO\.\s*([^\s]+)", text)
    order_date = _date(_search(r"PURCHASE ORDER NO\.[^\n]*?DATE:\s*([\d/.-]+)", text))
    revision = _search(r"REV NO\.:\s*([^\s]+)", text)
    revision_date = _date(_search(r"REV\. DATE:\s*([\d/.-]+)", text))
    customer = _search(r"CUSTOMER:\s*([^\n]+)", text)
    contract = _search(r"OUR CONF NO:\s*([^\n]+)", text)
    if contract:
        contract = re.split(r"\s{2,}|ATTN:|PAYMENT", contract)[0].strip()

    standards = []
    packaging = []
    for raw in text.splitlines():
        line = raw.strip(" -")
        upper = line.upper()
        if any(key in upper for key in ("STANDARD", "REGULATION", "ASTM", "EN TOY", "3C")):
            standards.append(line)
        if any(key in upper for key in ("PACKAGING", "INSTRUCTION SHEET", "SHIPPING MARK")):
            packaging.append(line)
    standards_text = "；".join(dict.fromkeys(standards))[:1200] or None
    packaging_text = "；".join(dict.fromkeys(packaging))[:1200] or None

    # Each product group ends at its carton statement; keeping blocks makes the
    # delivery date and mixed-carton information available to every item row.
    upper_text = text.upper()
    boundaries = [match.start() for match in re.finditer(r"(?m)^\d+[A-Z0-9-]*\s+.*?/ PRODUCT LINE:", upper_text)]
    boundaries.append(len(text))
    rows: list[dict[str, Any]] = []
    item_pattern = re.compile(
        r"(?m)^\s*(\d[A-Z0-9-]{3,})\s+(.+?)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+\.\d{2})\s*$"
    )
    consumed: set[tuple[str, int | float | None]] = set()
    for index in range(max(0, len(boundaries) - 1)):
        block = text[boundaries[index]:boundaries[index + 1]]
        delivery = _date(_search(r"DELIVERY DATE:\s*([\d/.-]+)", block))
        pack_text = _search(r"(\d+)PCS/CTN", block)
        block_pack = int(pack_text) if pack_text else None
        for match in item_pattern.finditer(block):
            item_no, description, quantity, price, amount = match.groups()
            key = (item_no, _number(quantity))
            if key in consumed:
                continue
            consumed.add(key)
            row = {
                "customer_type": "彩星", "order_date": revision_date or order_date,
                "customer_po": po, "contract_no": contract, "customer": customer,
                "item_no": item_no, "product_name": description.strip(),
                "quantity": _number(quantity), "case_pack": _infer_pack(item_no, block_pack),
                "ship_date": delivery, "packaging": packaging_text, "standards": standards_text,
                "unit_price": _number(price), "amount": _number(amount),
                "notes": f"PO REV {revision}" if revision else None,
            }
            add_derived_fields(row)
            rows.append(row)

    # Standalone product lines can sit outside a PRODUCT LINE block.
    for match in item_pattern.finditer(text):
        item_no, description, quantity, price, amount = match.groups()
        key = (item_no, _number(quantity))
        if key in consumed:
            continue
        preceding = text[max(0, match.start() - 450):match.start()]
        deliveries = re.findall(r"DELIVERY DATE:\s*([\d/.-]+)", preceding, re.I)
        row = {
            "customer_type": "彩星", "order_date": revision_date or order_date,
            "customer_po": po, "contract_no": contract, "customer": customer,
            "item_no": item_no, "product_name": description.strip(), "quantity": _number(quantity),
            "case_pack": _infer_pack(item_no, None), "ship_date": _date(deliveries[-1]) if deliveries else None,
            "packaging": packaging_text, "standards": standards_text,
            "unit_price": _number(price), "amount": _number(amount),
            "notes": f"PO REV {revision}" if revision else None,
        }
        add_derived_fields(row)
        rows.append(row)

    standalone_pattern = re.compile(
        r"(?m)^\s*(\d[A-Z0-9-]{3,})\s+([^\n]+)\n"
        r"\s*DELIVERY DATE:\s*([\d/.-]+)\s+CHN\s+PC\s+([\d,]+)\s+([\d.]+)\s+([\d,]+\.\d{2})\s*$",
        re.I,
    )
    for match in standalone_pattern.finditer(text):
        item_no, description, delivery, quantity, price, amount = match.groups()
        key = (item_no, _number(quantity))
        if key in consumed:
            continue
        consumed.add(key)
        row = {
            "customer_type": "彩星", "order_date": revision_date or order_date,
            "customer_po": po, "contract_no": contract, "customer": customer,
            "item_no": item_no, "product_name": description.strip(), "quantity": _number(quantity),
            "case_pack": _infer_pack(item_no, None), "ship_date": _date(delivery),
            "packaging": packaging_text, "standards": standards_text,
            "unit_price": _number(price), "amount": _number(amount),
            "notes": f"PO REV {revision}" if revision else None,
        }
        add_derived_fields(row)
        rows.append(row)

    warnings: list[str] = []
    if not rows:
        warnings.append("已读取 PDF，但未识别到彩星产品明细，请核对文件格式。")
    for row in rows:
        if not row.get("case_pack"):
            warnings.append(f"{row.get('item_no')}: 混装或装箱数未能自动确定，请人工确认。")
    return {
        "filename": filename, "type": "pdf", "customer_type": "彩星", "document_type": "purchase_order",
        "meta": {"pages": pages, "po_number": po, "contract_no": contract, "customer": customer,
                 "revision": revision, "row_count": len(rows)},
        "rows": rows, "warnings": list(dict.fromkeys(warnings)), "text_preview": text[:1600],
    }


def parse_excel_po(source: str | Path | bytes | BinaryIO, filename: str = "order.xlsx") -> dict[str, Any]:
    parsed = read_schedule(source, filename=filename)
    rows = parsed["records"]
    sheet_names = parsed.get("meta", {}).get("sheet_names", [])
    customer_type = (
        "EDU"
        if (
            "EDU" in filename.upper()
            or any("EDU" in str(name).upper() for name in sheet_names)
            or any(row.get("customer_type") == "EDU" for row in rows)
        )
        else rows[0].get("customer_type", "彩星")
    )
    for row in rows:
        row["customer_type"] = customer_type
        add_derived_fields(row)
    return {
        "filename": filename, "type": "excel", "customer_type": customer_type, "document_type": "order",
        "meta": parsed["meta"], "rows": rows, "warnings": [], "text_preview": "",
    }


def parse_po_file(source: str | Path | bytes | BinaryIO, filename: str | None = None) -> dict[str, Any]:
    name = filename or (Path(source).name if isinstance(source, (str, Path)) else "upload")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return parse_caixing_pdf(source, name)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return parse_excel_po(source, name)
    raise ValueError(f"不支持的文件类型：{suffix or '未知'}")


def revision_number(filename: str, meta: dict[str, Any] | None = None) -> int:
    values = [filename, str((meta or {}).get("revision") or "")]
    best = 0
    for value in values:
        # Windows 副本后缀 (1)/(2) 不是版本号，先剥掉再匹配。
        value = re.sub(r"\(\d+\)\s*(?=\.\w+$|$)", "", str(value)).strip()
        for match in re.finditer(r"(?:REV|R|V)[ ._-]?(\d+)", value, re.I):
            best = max(best, int(match.group(1)))
        if value.isdigit():
            best = max(best, int(value))
    if best == 0 and re.search(r"\bREV\b", str(filename), re.I):
        # 裸 "(REV)" 不带数字也是改单，必须比原版新，否则同传时会错留原版。
        best = 1
    return best


def merge_po_results(results: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    chosen: dict[str, dict[str, Any]] = {}
    without_po: list[dict[str, Any]] = []
    report: list[str] = []
    for result in results:
        po = str(result.get("meta", {}).get("po_number") or "").strip()
        if not po and result.get("rows"):
            po = str(result["rows"][0].get("customer_po") or "").strip()
        if not po:
            without_po.append(result)
            continue
        current = chosen.get(po)
        if current is None or revision_number(result.get("filename", ""), result.get("meta")) >= revision_number(current.get("filename", ""), current.get("meta")):
            if current:
                report.append(f"PO {po}：保留 {result['filename']}，忽略较旧版本 {current['filename']}")
            chosen[po] = result
        else:
            report.append(f"PO {po}：保留 {current['filename']}，忽略较旧版本 {result['filename']}")
    rows = [row for result in [*without_po, *chosen.values()] for row in result.get("rows", [])]
    return rows, report
