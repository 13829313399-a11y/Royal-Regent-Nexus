from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

import pdfplumber
from openpyxl import load_workbook

from app.services.carton_mark import configure_tesseract

from .yinhui_schedule import add_derived_fields, read_schedule


def _source_bytes(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    try:
        source.seek(0)
    except (AttributeError, OSError):
        pass
    data = source.read()
    if not isinstance(data, bytes):
        raise ValueError("银辉 PO 不是有效的二进制文件")
    return data


def _ocr_pdf_text(data: bytes) -> str:
    try:
        import pypdfium2 as pdfium  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise ValueError(
            "银辉扫描版 PDF 需要服务器 OCR 组件（pypdfium2、Pillow、pytesseract）"
        ) from exc
    tesseract_cmd, language = configure_tesseract(pytesseract)
    if not tesseract_cmd:
        raise ValueError("未找到 Tesseract，无法识别银辉扫描版 PDF")
    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise ValueError("银辉 PO 不是有效的 PDF 文件") from exc
    if len(document) == 0 or len(document) > 20:
        document.close()
        raise ValueError("银辉 PO 页数必须在 1 至 20 页之间")
    pages: list[str] = []
    try:
        for page in document:
            image = page.render(scale=3.0).to_pil().convert("RGB")
            try:
                text = pytesseract.image_to_string(
                    image,
                    lang=language,
                    config="--oem 3 --psm 6",
                    timeout=60,
                )
            except Exception as exc:
                raise ValueError(f"银辉 PDF OCR 失败：{exc}") from exc
            pages.append(text.strip())
            page.close()
    finally:
        document.close()
    return "\n<<OCR_PAGE_BREAK>>\n".join(pages).strip()


def _pdf_text(source: str | Path | bytes | BinaryIO) -> tuple[str, int, bool]:
    data = _source_bytes(source)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
        pages = len(pdf.pages)
    if text:
        return text, pages, False
    return _ocr_pdf_text(data), pages, True


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else None


def _converted_item_match(value: Any) -> re.Match[str] | None:
    """匹配 WPS 转换件中“5位行号+PART#”合并后的首列。"""
    return re.match(r"^(\d{4}0)([A-Z0-9][A-Z0-9-]{3,})$", str(value or "").strip())


def _row_text(ws, row: int) -> str:
    return " ".join(
        str(ws.cell(row, column).value).strip()
        for column in range(1, ws.max_column + 1)
        if ws.cell(row, column).value is not None
    )


def _rows_text(ws, start_row: int, end_row: int) -> str:
    return "\n".join(_row_text(ws, row) for row in range(start_row, end_row + 1))


def _remarks_text(all_text: str) -> str:
    match = re.search(
        r"(?:^|\n)\s*Remarks\s*[:：]\s*(.*?)"
        r"(?=\n\s*(?:Terms\s+and\s+Conditions\s*[:：]|<<OCR_PAGE_BREAK>>)|\Z)",
        all_text,
        re.I | re.S,
    )
    return match.group(1).strip() if match else ""


def _remarks_line(remarks: str, *patterns: str) -> str | None:
    for line in remarks.splitlines():
        value = line.strip().lstrip(">").strip()
        if value and any(re.search(pattern, value, re.I) for pattern in patterns):
            return value
    return None


def _shipping_mark_from_remarks(remarks: str) -> str | None:
    markers = (
        r"箱唛", r"箱嘜", r"印唛", r"印嘜",
        r"外箱资料", r"外箱資料", r"外箱.*(?:唛|嘜)",
    )
    sections = re.split(r"(?=\n?\s*R\d+\s*\))", remarks, flags=re.I)
    for section in sections:
        value = section.strip()
        if value and any(re.search(pattern, value, re.I) for pattern in markers):
            return value
    return None


def _so_no(text: str) -> str | None:
    """Return the schedule SO, excluding Silverlit's line suffix (-780/-790)."""
    match = re.search(r"\bS(?:O|0O|0)\s*[:：]\s*([A-Z0-9]+)", text, re.I)
    return match.group(1).strip() if match else None


def _pdf_customer(text: str) -> str | None:
    known = _find(r"\bName\s*[:：]\s*(SILVERLIT\s+NORDIC\s+AB)\b", text)
    if known:
        return re.sub(r"\s+", " ", known).strip()
    value = _find(r"\bName\s*[:：]\s*([^\r\n]+)", text)
    return re.sub(r"\s+", " ", value).strip() if value else None


def _declared_page_total(text: str) -> int | None:
    values = [
        int(value)
        for value in re.findall(r"\bPage\s*[:：]\s*\d+\s+of\s+(\d+)\b", text, re.I)
    ]
    return max(values) if values else None


def _case_pack(text: str) -> float | int | None:
    direct = re.search(r"\bPCS\s*/\s*CTN\s*[:：]?\s*([\d,.]+)", text, re.I)
    if direct:
        value = float(direct.group(1).replace(",", ""))
        return int(value) if value.is_integer() else value
    inner_outer = re.search(
        r"Packing\s*\(\s*Inner\s*/\s*Outer\s*\)\s*[:：]?.{0,160}?"
        r"[\d,.]+\s*/\s*([\d,.]+)",
        text,
        re.I | re.S,
    )
    if inner_outer:
        value = float(inner_outer.group(1).replace(",", ""))
        return int(value) if value.is_integer() else value
    return None


def _case_pack_from_rows(ws, start_row: int, end_row: int) -> float | int | None:
    """读取明细区装箱数，并处理 WPS 把 0/6 误存成日期 2000-06-01 的情况。"""
    for row in range(start_row, end_row + 1):
        row_text = _row_text(ws, row)
        if not re.search(r"Packing\s*\(\s*[Il]nner\s*/\s*Outer\s*\)", row_text, re.I):
            continue
        direct = _case_pack(row_text)
        if direct is not None:
            return direct
        for scan_row in range(row, min(row + 1, end_row) + 1):
            for column in range(1, ws.max_column + 1):
                value = ws.cell(scan_row, column).value
                if isinstance(value, (datetime, date)) and value.year == 2000:
                    return value.month
                direct = _case_pack(str(value or ""))
                if direct is not None:
                    return direct
    return None


_WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_WORD_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}


def _words_to_number(text: str) -> float | None:
    """把英文大写金额段落转成数字（如 ONE HUNDRED NINETEEN → 119）。"""
    total, current = 0, 0
    tokens = re.split(r"[\s-]+", text.strip().lower())
    seen = False
    for tok in tokens:
        if not tok or tok == "and":
            continue
        if tok in _WORD_NUMS:
            current += _WORD_NUMS[tok]
            seen = True
        elif tok == "hundred":
            current = (current or 1) * 100
        elif tok in _WORD_SCALES and tok != "hundred":
            total += (current or 1) * _WORD_SCALES[tok]
            current = 0
        else:
            return None  # 出现不认识的词，放弃校验而不是猜
    return float(total + current) if seen or total else None


def check_amount_in_words(text: str, line_sum: float) -> str | None:
    """自洽校验：单据大写金额（SAY: USD ... ONLY）与行合计比对。"""
    m = re.search(
        r"SAY\s*[:：]?\s*USD?\s+(.+?)\s+DOLLARS?(?:\s+AND\s+(.+?)\s+CENTS?)?\s+ONLY",
        text, re.I | re.S,
    )
    if not m:
        return None
    dollars = _words_to_number(m.group(1))
    cents = _words_to_number(m.group(2)) if m.group(2) else 0.0
    if dollars is None or cents is None:
        return None
    say_total = round(dollars + cents / 100, 2)
    if abs(say_total - round(line_sum, 2)) > 0.011:
        return (
            f"大写金额校验不符：单据大写为 {say_total}，行金额合计为 {round(line_sum, 2)}，"
            "可能有明细行漏识别或金额识别错误，请人工核对"
        )
    return None


def parse_pdf(source: str | Path | bytes | BinaryIO, filename: str) -> dict[str, Any]:
    text, pages, used_ocr = _pdf_text(source)
    if not text:
        return {
            "filename": filename, "type": "pdf", "rows": [],
            "meta": {"pages": pages, "text_chars": 0, "used_ocr": used_ocr},
            "warnings": ["银辉 PO 没有可识别文字；本地 OCR 已执行但未能读取订单内容。"],
        }
    po_no = _find(r"PURCHASE\s+ORDER\s*[:：]\s*([A-Z0-9-]+)", text)
    order_date = _find(r"Date\s*\(YMD\)\s*[:：]\s*([0-9.\/-]+)", text)
    remarks = _remarks_text(text)
    customer = _pdf_customer(text)
    artwork = _remarks_line(remarks, r"彩盒", r"客盒")
    manual = _remarks_line(remarks, r"说明书", r"說明書", r"説明書")
    customer_label = _remarks_line(remarks, r"客贴", r"客貼", r"贴纸", r"貼紙", r"入口商")
    shipping_mark = _shipping_mark_from_remarks(remarks)
    row_pattern = re.compile(
        r"^\s*\d+\s+([A-Z0-9-]+)\s+(.+?)\s+(\d{4}[.\/-]\d{2}[.\/-]\d{2})\s+"
        r"([\d,]+)\s+(?:PCS|PC|EA|SET)\s+([\d.]+)\s+([\d,.]+)\s*$", re.I | re.M,
    )
    rows = []
    warnings = [
        "扫描版 PDF 已使用本地 OCR；合同号、SO、货号、数量、日期和金额已做结构及算术校验，仍请在预览中人工复核。",
        "扫描件中文备注不可靠，系统未把 OCR 乱码写入排期；说明书、彩盒、箱唛等内容保留为待确认。",
    ] if used_ocr else []
    matches = list(row_pattern.finditer(text))
    for index, match in enumerate(matches):
        item, description, delivery, qty, price, amount = match.groups()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        item_block = text[match.end():next_start]
        case_pack = _case_pack(item_block)
        row = {
            "contract_no": po_no, "item_no": item, "product_name": description,
            "po_ship_date": delivery.replace(".", "-"), "quantity": qty,
            "unit_price_usd": price, "total_usd": amount, "order_date": order_date,
            "so_no": _so_no(item_block), "customer": customer,
            "case_pack": case_pack if case_pack else None,
            "artwork": artwork, "manual": manual,
            "customer_label": customer_label, "shipping_mark": shipping_mark,
            "memo": None if used_ocr else (remarks or None),
            "source_sheet": "PDF OCR" if used_ocr else "PDF",
        }
        add_derived_fields(row)
        rows.append(row)
        # 自洽校验：数量×单价 = 行金额
        q, p, a = float(qty.replace(",", "")), float(price), float(amount.replace(",", ""))
        if q > 0 and p > 0 and abs(round(q * p, 2) - a) > 0.05:
            warnings.append(f"{po_no} {item}: 数量×单价({q}×{p})与金额({a})不符，请人工核对（注意是否有折扣）")
    if rows:
        say_warn = check_amount_in_words(text, sum(float(str(r["total_usd"]).replace(",", "")) for r in rows))
        if say_warn:
            warnings.append(f"{po_no}: {say_warn}")
    else:
        warnings.append("已读取PO文字，但未识别到标准明细行，请人工复核或使用排期表Excel。")
    declared_pages = _declared_page_total(text)
    if declared_pages and declared_pages != pages:
        warnings.append(
            f"PDF 文件实际为 {pages} 页，但单据页码标注总计 {declared_pages} 页；"
            "请确认是否缺页后再正式放行。"
        )
    return {"filename": filename, "type": "pdf", "rows": rows,
            "meta": {"pages": pages, "text_chars": len(text), "po_no": po_no,
                     "used_ocr": used_ocr}, "warnings": warnings}


def _parse_converted_po_excel(source: str | Path | bytes | BinaryIO, filename: str) -> dict[str, Any] | None:
    """解析"扫描PO转换成Excel"的银辉采购单（表头 ITEM#PART#/DESCRIPTION/QTY/PRICE/AMOUNT）。

    转换工具会把行号和货号并进一个单元格（如 00010886380NS00101），需要拆开。
    """
    data = source if isinstance(source, bytes) else (
        Path(source).read_bytes() if isinstance(source, (str, Path)) else source.read()
    )
    wb = load_workbook(io.BytesIO(data), data_only=True)
    try:
        ws = wb.active
        all_text = "\n".join(
            str(c.value) for row in ws.iter_rows() for c in row if c.value is not None
        )
        po_no = _find(r"PURCHASE\s+ORDER\s*[:：]\s*([A-Z0-9-]+)", all_text)
        order_date = _find(r"Date\s*\(YMD\)\s*[:：]?\s*([0-9.\/-]{8,})", all_text)
        # 表头 "ITEM#" 可能被转换工具识别残缺（如 "TEM#"），只要求 PO 号存在，
        # 是否为转换版 PO 由下面能否找到数据行决定。
        if not po_no:
            return None
        remarks = _remarks_text(all_text)
        customer = _find(r"(?:客户|客戶)\s*[:：]\s*([^\r\n]+)", remarks)
        if not customer:
            # Word 规则以 Remarks“客户：”为准；仅在该行缺失时才使用 PO 明细中的 Name 兜底。
            customer = _find(r"(?:^|\n)\s*Name\s*[:：]\s*([^\r\n]+)", all_text)
        artwork = _remarks_line(remarks, r"彩盒", r"客盒")
        manual = _remarks_line(remarks, r"说明书", r"說明書", r"説明書")
        customer_label = _remarks_line(
            remarks, r"客贴", r"客貼", r"贴纸", r"貼紙", r"入口商"
        )
        shipping_mark = _shipping_mark_from_remarks(remarks)

        item_rows: list[tuple[int, re.Match[str]]] = []
        for row_number in range(1, ws.max_row + 1):
            match = _converted_item_match(ws.cell(row_number, 1).value)
            if match:
                item_rows.append((row_number, match))

        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        for item_index, (r, m) in enumerate(item_rows):
            # 转换工具把 5 位行号(00010/00020…)与货号并进一个单元格，行号定长切分，
            # 贪婪匹配会把货号切错位（886380NS00101 变 86380NS00101）。货号可为纯数字。
            cells = [str(ws.cell(r, c).value).strip() for c in range(2, ws.max_column + 1)
                     if ws.cell(r, c).value is not None]
            row_text = " ".join(cells)
            desc = next((c for c in cells if re.search(r"[A-Za-z]{3}", c) and not re.search(r"\d{4}[./-]\d{2}", c)), "")
            # 日期与数量可能同格（"2026.07.01  708 PCS"）也可能分格，分别查找。
            date_m = next((re.search(r"(\d{4}[./-]\d{2}[./-]\d{2})", c) for c in cells
                           if re.search(r"\d{4}[./-]\d{2}[./-]\d{2}", c)), None)
            qty_m = next((re.search(r"([\d,]+)\s*(?:PCS|PC|EA|SET)\b", c, re.I) for c in cells
                          if re.search(r"[\d,]+\s*(?:PCS|PC|EA|SET)\b", c, re.I)), None)
            nums = [c for c in cells if re.fullmatch(r"[\d,]+(?:\.\d+)?", c)]
            if not (date_m and qty_m):
                continue
            qty = float(qty_m.group(1).replace(",", ""))
            price_m = re.search(
                r"(?:PCS|PC|EA|SET)\b\s+([\d,]+(?:\.\d+)?)",
                row_text,
                re.I,
            )
            price = (
                float(price_m.group(1).replace(",", ""))
                if price_m
                else float(nums[-2].replace(",", "")) if len(nums) >= 2 else None
            )
            amount = float(nums[-1].replace(",", "")) if nums else None
            next_item_row = item_rows[item_index + 1][0] if item_index + 1 < len(item_rows) else ws.max_row + 1
            item_block = _rows_text(ws, r + 1, next_item_row - 1)
            so_no = _find(r"\bSO\s*[:：]\s*([A-Z0-9-]+)", item_block)
            if so_no in {"0", "-0"}:
                so_no = None
            case_pack = (
                _case_pack_from_rows(ws, r + 1, next_item_row - 1)
                or _case_pack(item_block)
                or _case_pack(remarks)
            )
            # 银辉样板/促销单会把折扣放在明细行下方，例如：
            #   Dist.pct
            #   -20.00%
            # 金额应按 数量×单价×(1+折扣) 核对，不能误报为金额不一致。
            discount_rate: float | None = None
            for lookahead in range(r + 1, min(r + 5, ws.max_row + 1)):
                lookahead_values = [
                    ws.cell(lookahead, c).value for c in range(1, ws.max_column + 1)
                ]
                lookahead_text = " ".join(
                    str(value) for value in lookahead_values if value is not None
                )
                if "dist.pct" in lookahead_text.lower():
                    continue
                numeric_values = [
                    float(value) for value in lookahead_values
                    if isinstance(value, (int, float)) and -1 < float(value) < 1
                ]
                if numeric_values:
                    discount_rate = numeric_values[-1]
                    break
                if _converted_item_match(lookahead_values[0]):
                    break
            if price is not None and amount is not None:
                expected_amount = qty * price * (1 + (discount_rate or 0))
                if abs(expected_amount - amount) > 0.05:
                    discount_note = (
                        f"，含折扣{discount_rate:.2%}" if discount_rate is not None else ""
                    )
                    warnings.append(
                        f"{po_no} {m.group(2)}: 数量×单价{discount_note}"
                        f"核算为{round(expected_amount, 2)}，与金额({amount})不符，请人工核对"
                    )
            if price is None and amount is not None:
                price = round(amount / qty, 6) if qty else None
                warnings.append(
                    f"{po_no} {m.group(2)}: 转换件缺失单价列，已按金额÷数量反算单价 {price}，请人工复核"
                )
            row = {
                "contract_no": po_no, "item_no": m.group(2), "product_name": desc,
                "po_ship_date": date_m.group(1).replace(".", "-").replace("/", "-"),
                "quantity": qty, "unit_price_usd": price, "total_usd": amount,
                "order_date": order_date, "source_sheet": "转换PO",
                "discount_rate": discount_rate,
                "so_no": so_no,
                "customer": customer,
                "case_pack": case_pack,
                "artwork": artwork,
                "manual": manual,
                "customer_label": customer_label,
                "memo": remarks or None,
                "shipping_mark": shipping_mark,
            }
            add_derived_fields(row)
            rows.append(row)
        if not rows:
            return None
        missing_fields = []
        for field, label in (
            ("customer", "客名"),
            ("so_no", "SO"),
            ("case_pack", "装箱数量"),
        ):
            missing_count = sum(not row.get(field) for row in rows)
            if missing_count:
                missing_fields.append(f"{label}{missing_count}行")
        if missing_fields:
            warnings.append(
                f"{po_no}: PO原文未提供或以0表示 {'、'.join(missing_fields)}；"
                "系统已保持为空并标记复核，没有套用其他客户数据"
            )
        say_warn = check_amount_in_words(all_text, sum(r.get("total_usd") or 0 for r in rows))
        if say_warn:
            warnings.append(f"{po_no}: {say_warn}")
        warnings.insert(0, "已按扫描转换版PO解析；转换件可能有识别误差，关键数量/金额请人工核对。")
        return {"filename": filename, "type": "excel", "rows": rows,
                "meta": {"po_no": po_no, "converted": True}, "warnings": warnings}
    finally:
        wb.close()


def parse_po(source: str | Path | bytes | BinaryIO, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(source, filename)
    if suffix in {".xlsx", ".xlsm"}:
        if isinstance(source, (str, Path)):
            source = Path(source).read_bytes()
        try:
            parsed = read_schedule(source, filename=filename)
            return {"filename": filename, "type": "excel", "rows": parsed["records"],
                    "summary": parsed["summary"], "meta": parsed["meta"], "warnings": []}
        except ValueError:
            converted = _parse_converted_po_excel(source, filename)
            if converted:
                return converted
            raise
    raise ValueError("PO仅支持PDF、XLSX或XLSM")
