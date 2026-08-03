from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO

import pdfplumber
from openpyxl import load_workbook

from .yinhui_schedule import add_derived_fields, read_schedule


def _pdf_text(source: str | Path | bytes | BinaryIO) -> tuple[str, int]:
    stream: Any = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(stream) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip(), len(pdf.pages)


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
        r"(?:^|\n)\s*Remarks\s*[:：]\s*(.*?)(?=\n\s*Terms\s+and\s+Conditions\s*[:：]|\Z)",
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
    text, pages = _pdf_text(source)
    if not text:
        return {
            "filename": filename, "type": "pdf", "rows": [],
            "meta": {"pages": pages, "text_chars": 0},
            "warnings": ["该PO是扫描图片版，系统已识别文件但无法可靠读取文字；请用排期表Excel导入，或上传可选中文字的PO。"],
        }
    po_no = _find(r"PURCHASE\s+ORDER\s*[:：]\s*([A-Z0-9-]+)", text)
    order_date = _find(r"Date\s*\(YMD\)\s*[:：]\s*([0-9.\/-]+)", text)
    row_pattern = re.compile(
        r"^\s*\d+\s+([A-Z0-9-]+)\s+(.+?)\s+(\d{4}[.\/-]\d{2}[.\/-]\d{2})\s+"
        r"([\d,]+)\s+(?:PCS|PC|EA|SET)\s+([\d.]+)\s+([\d,.]+)\s*$", re.I | re.M,
    )
    rows = []
    warnings = []
    for match in row_pattern.finditer(text):
        item, description, delivery, qty, price, amount = match.groups()
        row = {
            "contract_no": po_no, "item_no": item, "product_name": description,
            "po_ship_date": delivery.replace(".", "-"), "quantity": qty,
            "unit_price_usd": price, "total_usd": amount, "order_date": order_date,
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
    return {"filename": filename, "type": "pdf", "rows": rows,
            "meta": {"pages": pages, "text_chars": len(text), "po_no": po_no}, "warnings": warnings}


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
