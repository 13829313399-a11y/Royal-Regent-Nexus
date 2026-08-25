# -*- coding: utf-8 -*-
"""华康C多客户采购单解析器。

把 INDEX、JAZWARES、MAXX、STROTTMAN 以及华康车衣中文采购单统一成同一份
订单结构，供排期写入模块使用。解析规则来自项目资料中的操作说明和标注样例。
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any, Callable

import openpyxl
import pdfplumber
import xlrd


class POParseError(ValueError):
    """文件可读取，但不属于当前支持的采购单版式。"""


CUSTOMERS = {
    "index": "INDEX",
    "jazwares": "JAZWARES",
    "maxx": "MAXX",
    "strottman": "STROTTMAN",
    "supplier": "华康车衣",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    text = str(value).replace(",", "").replace("$", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _int_number(value: Any) -> int:
    return int(round(_number(value)))


def _year(value: int) -> int:
    return value + 2000 if value < 100 else value


def normalize_date(value: Any, *, day_first: bool = False) -> str:
    """将资料里的常见日期统一为 YYYY-MM-DD。"""
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = _clean(value)
    chinese = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if chinese:
        return f"{int(chinese.group(1)):04d}-{int(chinese.group(2)):02d}-{int(chinese.group(3)):02d}"
    iso = re.search(r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", text)
    if iso:
        return f"{int(iso.group(1)):04d}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}"
    numeric = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if numeric:
        first, second, year = map(int, numeric.groups())
        day, month = (first, second) if day_first else (second, first)
        try:
            return date(_year(year), month, day).strftime("%Y-%m-%d")
        except ValueError:
            # 当版式判断和日期本身冲突时，自动尝试另一种顺序。
            try:
                return date(_year(year), first, second).strftime("%Y-%m-%d")
            except ValueError:
                return text
    month_name = re.search(
        r"\b(\d{1,2})[- ]([A-Za-z]{3,9})[- ,](\d{2,4})\b", text
    )
    if month_name:
        raw = "-".join(month_name.groups())
        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return text


def _match(pattern: str, text: str, default: str = "", flags: int = re.I) -> str:
    found = re.search(pattern, text, flags)
    return _clean(found.group(1)) if found else default


def _line(
    item_code: str,
    description: str,
    qty: int,
    *,
    unit: str = "PCS",
    unit_price_usd: float = 0.0,
    amount_usd: float = 0.0,
    pcs_per_carton: int = 0,
    carton_qty: int = 0,
    source_unit_price_usd: float = 0.0,
    unit_price_hkd: float = 0.0,
    version: str = "",
) -> dict[str, Any]:
    return {
        "item_code": _clean(item_code),
        "description": _clean(description),
        "qty": int(qty or 0),
        "unit": _clean(unit).upper(),
        "unit_price_usd": round(float(unit_price_usd or 0), 6),
        "amount_usd": round(float(amount_usd or 0), 4),
        "pcs_per_carton": int(pcs_per_carton or 0),
        "carton_qty": int(carton_qty or 0),
        "source_unit_price_usd": round(float(source_unit_price_usd or 0), 6),
        "unit_price_hkd": round(float(unit_price_hkd or 0), 6),
        "version": _clean(version),
    }


def _order(customer_code: str, **values: Any) -> dict[str, Any]:
    order = {
        "customer_code": customer_code,
        "customer_name": CUSTOMERS[customer_code],
        "po_number": "",
        "contract_no": "",
        "po_date": "",
        "ship_date": "",
        "ship_dates": [],
        "ship_to": "",
        "version": "",
        "contact": "",
        "lines": [],
        "warnings": [],
    }
    order.update(values)
    if order["ship_date"] and not order["ship_dates"]:
        order["ship_dates"] = [order["ship_date"]]
    return order


class HuakangPOParser:
    """自动识别并解析当前资料中出现的五类采购单。"""

    SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xlsm", ".xls"}

    def parse(self, path: str) -> dict[str, Any]:
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise POParseError(f"不支持的文件格式：{ext or '无扩展名'}")
        text = self._read_text(path, ext)
        if not text.strip():
            raise POParseError("文件中没有可识别文字")
        customer_code = self.detect_customer(text)
        parsers: dict[str, Callable[[str], dict[str, Any]]] = {
            "index": self._parse_index,
            "jazwares": self._parse_jazwares,
            "maxx": self._parse_maxx,
            "strottman": self._parse_strottman,
            "supplier": self._parse_supplier,
        }
        order = parsers[customer_code](text)
        order["filename"] = os.path.basename(path)
        order["raw_text"] = text[:8000]
        order["warnings"] = list(dict.fromkeys(order.get("warnings", []) + validate(order)))
        return order

    def parse_text(self, text: str, filename: str = "sample.pdf") -> dict[str, Any]:
        """测试和诊断入口，不经过文件读取。"""
        customer_code = self.detect_customer(text)
        parser = getattr(self, f"_parse_{customer_code}")
        order = parser(text)
        order["filename"] = filename
        order["raw_text"] = text[:8000]
        order["warnings"] = list(dict.fromkeys(order.get("warnings", []) + validate(order)))
        return order

    def detect_customer(self, text: str) -> str:
        upper = text.upper()
        if "JAZWARES" in upper:
            return "jazwares"
        if "MAXX MARKETING" in upper or "MAXX MAKES GREAT" in upper:
            return "maxx"
        if "STROTTMAN" in upper:
            return "strottman"
        if "INDEX PROMOTIONS" in upper:
            return "index"
        if "采购单编号" in text or "華康車衣" in text or "华康车衣" in text:
            return "supplier"
        raise POParseError("无法识别客户版式；目前支持 INDEX、JAZWARES、MAXX、STROTTMAN 和华康车衣采购单")

    def _read_text(self, path: str, ext: str) -> str:
        if ext == ".pdf":
            parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text(x_tolerance=2, y_tolerance=4) or "")
            return "\n".join(parts)
        if ext in {".xlsx", ".xlsm"}:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                rows = []
                for ws in wb.worksheets:
                    rows.append(f"SHEET {ws.title}")
                    for row in ws.iter_rows(
                        min_row=1,
                        max_row=min(ws.max_row or 1, 2000),
                        max_col=min(ws.max_column or 1, 80),
                        values_only=True,
                    ):
                        values = [_clean(value).replace("\n", " ") for value in row if value not in (None, "")]
                        if values:
                            rows.append(" ".join(values))
                return "\n".join(rows)
            finally:
                wb.close()
        book = xlrd.open_workbook(path)
        rows = []
        for sheet in book.sheets():
            rows.append(f"SHEET {sheet.name}")
            for row_index in range(min(sheet.nrows, 2000)):
                values = [_clean(sheet.cell_value(row_index, col)) for col in range(min(sheet.ncols, 80))]
                values = [value for value in values if value]
                if values:
                    rows.append(" ".join(values))
        return "\n".join(rows)

    def _parse_index(self, text: str) -> dict[str, Any]:
        po = _match(r"Purchase Order No\.\s*([A-Z0-9-]+)", text)
        po_date = normalize_date(_match(r"\bDate\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text))
        ship_date = normalize_date(_match(r"Ex-Factory\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text))
        block = _match(r"Qty\s+Units\s+Description\s+Unit Price\s+TOTAL\s*(.+?)\s*SubTotal", text, flags=re.I | re.S)
        qty_match = re.search(r"(?m)^\s*([\d,]+)\s+pcs\.\s+(.+?)\s+\$([\d,.]+)\s+\$([\d,.]+)\s*$", block)
        if not qty_match:
            raise POParseError("INDEX 采购单未识别到数量和价格行")
        qty = _int_number(qty_match.group(1))
        price = _number(qty_match.group(3))
        amount = _number(qty_match.group(4))
        header = ""
        for row in block.splitlines():
            row = _clean(row)
            if re.match(r"^\d+\s+.+", row) and "pcs" not in row.lower():
                header = row
                break
        item_match = re.match(r"^(\d+)\s+(.+)$", header)
        item_code = item_match.group(1) if item_match else po
        descriptions = []
        if item_match:
            descriptions.append(item_match.group(2))
        for row in block.splitlines():
            product = re.search(r"[\d,]+\s*pcs\s*-\s*(.+?)(?:\s+\$[\d,.]+\s+\$[\d,.]+)?$", row, re.I)
            if product:
                descriptions.append(_clean(product.group(1)))
        descriptions = list(dict.fromkeys(part for part in descriptions if part))
        pcs_per_carton = _int_number(_match(r"([\d,]+)\s*pcs\s*/\s*carton", block))
        lines = [_line(
            item_code,
            " / ".join(descriptions),
            qty,
            unit_price_usd=price,
            amount_usd=amount,
            pcs_per_carton=pcs_per_carton,
            carton_qty=round(qty / pcs_per_carton) if pcs_per_carton else 0,
        )]
        return _order(
            "index",
            po_number=po,
            contract_no=po,
            po_date=po_date,
            ship_date=ship_date,
            contact="Our contact（请人工确认）",
            lines=lines,
            warnings=["接单日期默认采用 PO 上的 Date；若邮件确认日期不同，请在页面覆盖。"],
        )

    def _parse_jazwares(self, text: str) -> dict[str, Any]:
        header = re.search(
            r"Date\s*:\s*PO\s*#\s*:\s*\n\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+([A-Z0-9-]+)",
            text,
            re.I,
        )
        if header:
            po_date, po = normalize_date(header.group(1)), header.group(2)
        else:
            po = _match(r"\b(JAZ\d{5,})\b", text)
            po_date = normalize_date(_match(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text))
        version = _match(r"PO Rev\.\s*([A-Z0-9.-]+)", text)
        shipping = re.search(
            r"60\s*DAYS\s*ROD\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+([A-Z0-9-]+)\s+([A-Za-z]+)",
            text,
            re.I,
        )
        ship_date = normalize_date(shipping.group(1)) if shipping else ""
        contract = shipping.group(2) if shipping else po
        ship_to = _match(r"VENDOR\s+SHIP TO\s*\n.+?\s+(JAZWARES\s*-\s*[^\n]+)", text, flags=re.I | re.S)
        lines = []
        product_start = re.compile(
            r"^([A-Z][A-Z0-9-]{4,})\s+([0-9][0-9-]{5,})\s+(.+)$",
            re.I,
        )
        product_tail = re.compile(
            r"^(.+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,.]+)\s+([\d,]+\.\d{2})$"
        )
        source_lines = [_clean(value) for value in text.splitlines()]
        for index, source_line in enumerate(source_lines):
            start = product_start.match(source_line)
            if not start:
                continue
            payload = start.group(3)
            found_tail = None
            # Long JAZWARES descriptions can wrap before the numeric columns.
            # Join only a small, bounded continuation window and stop at the
            # next product/section marker so unrelated footer text is excluded.
            for offset in range(0, 5):
                if offset:
                    candidate = source_lines[index + offset] if index + offset < len(source_lines) else ""
                    if not candidate or candidate.startswith("****") or product_start.match(candidate):
                        break
                    payload = f"{payload} {candidate}".strip()
                found_tail = product_tail.match(payload)
                if found_tail:
                    break
            if not found_tail:
                continue
            qty = _int_number(found_tail.group(2))
            pcs = _int_number(found_tail.group(3))
            lines.append(_line(
                start.group(1),
                found_tail.group(1),
                qty,
                unit_price_usd=_number(found_tail.group(4)),
                amount_usd=_number(found_tail.group(5)),
                pcs_per_carton=pcs,
                carton_qty=round(qty / pcs) if pcs else 0,
                version=version,
            ))
        if not lines:
            raise POParseError("JAZWARES 采购单未识别到产品行")
        return _order(
            "jazwares",
            po_number=po,
            contract_no=contract,
            po_date=po_date,
            ship_date=ship_date,
            ship_to=ship_to or "JAZWARES",
            version=version,
            contact="April",
            lines=lines,
            warnings=["接单日期默认采用 PO Date；系统按资料规则以 7.75 换算港币。"],
        )

    def _parse_maxx(self, text: str) -> dict[str, Any]:
        po = _match(r"P\.O\.\s*NO\.\s+([^\n(]+)", text)
        po_date = normalize_date(_match(r"P\.O\.\s*DATE\s+(\d{1,2}/\d{1,2}/\d{2,4})", text), day_first=True)
        ship_date = normalize_date(_match(r"\bDELIVERY\s+(\d{1,2}/\d{1,2}/\d{2,4})", text), day_first=True)
        contract = _match(r"S\.C\.\s*NO\.\s+([A-Z0-9-]+)", text)
        project = re.search(r"(?mi)^Project#\s*([A-Z0-9-]+)\s+(.+?)\s*$", text)
        project_no = _clean(project.group(1)) if project else ""
        project_name = _clean(project.group(2)) if project else ""
        delivery_term = _match(r"TERMS OF DELIVERY\s+([^\n]+)", text)
        lines = []
        pattern = re.compile(
            r"(?m)^([A-Z0-9]+-[A-Z0-9]+)\s+(.+?)\s+([\d,]+)\s+([A-Za-z]+)\s+"
            r"([\d,.]+)\s+([\d,]+\.\d{2})\s*$"
        )
        for found in pattern.finditer(text):
            lines.append(_line(
                found.group(1),
                found.group(2),
                _int_number(found.group(3)),
                unit=found.group(4),
                unit_price_usd=_number(found.group(5)),
                amount_usd=_number(found.group(6)),
            ))
        if not lines:
            raise POParseError("MAXX 采购单未识别到产品行")
        return _order(
            "maxx",
            po_number=po,
            contract_no=contract or po,
            po_date=po_date,
            ship_date=ship_date,
            project_no=project_no,
            project_name=project_name,
            delivery_term=delivery_term,
            contact="朱江",
            lines=lines,
            warnings=["装箱数未在 MAXX PO 中提供，导出时保留为空。"],
        )

    def _parse_strottman(self, text: str) -> dict[str, Any]:
        header = re.search(
            r"Date\s+Purchase Order\s*#\s+Terms\s*\n\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+([A-Z0-9-]+)",
            text,
            re.I,
        )
        po_date = normalize_date(header.group(1)) if header else ""
        po = header.group(2) if header else _match(r"\b(PO\d{3,})\b", text)
        product = re.search(
            r"(?m)^([0-9]{4}-[0-9]+(?:-[A-Z0-9]+)?)\s+([\d,]+)\s+([A-Za-z]+)\s+"
            r"\$([\d,.]+)\s+\$([\d,]+\.\d{2})\s*$",
            text,
        )
        if not product:
            raise POParseError("STROTTMAN 采购单未识别到产品行")
        after = text[product.end():].lstrip().splitlines()
        description = _clean(after[0]) if after else product.group(1)
        carton_qty = _int_number(product.group(2))
        source_price = _number(product.group(4))
        amount = _number(product.group(5))
        special_qty_match = re.search(r"\b(\d[\d,.]*)\s*K\b", text, re.I)
        special_qty = int(round(_number(special_qty_match.group(1)) * 1000)) if special_qty_match else 0
        qty = special_qty if special_qty >= carton_qty else carton_qty
        pcs_per_carton = round(qty / carton_qty) if carton_qty and qty != carton_qty else 0
        normalized_price = amount / qty if qty else source_price
        raw_ship_dates = re.findall(r"\b\d{1,2}-[A-Za-z]{3,9}-\d{2,4}\b", text)
        ship_dates = [normalize_date(value) for value in raw_ship_dates]
        warnings = []
        if special_qty and carton_qty:
            warnings.append(
                f"PO 数量为 {carton_qty} 箱；根据 Special Instructions 的 {special_qty:,} 件换算为每箱 {pcs_per_carton} 件。"
            )
        if len(ship_dates) > 1:
            warnings.append("PO 含多个走货截止日，排期主列先写最早日期，其余日期保留在备注。")
        return _order(
            "strottman",
            po_number=po,
            contract_no=po,
            po_date=po_date,
            ship_date=ship_dates[0] if ship_dates else "",
            ship_dates=ship_dates,
            ship_to="Hong Kong",
            contact="朱江",
            lines=[_line(
                re.sub(r"-F\d+$", "", product.group(1), flags=re.I),
                description,
                qty,
                unit="PCS" if special_qty else product.group(3),
                unit_price_usd=normalized_price,
                amount_usd=amount,
                pcs_per_carton=pcs_per_carton,
                carton_qty=carton_qty,
                source_unit_price_usd=source_price,
            )],
            warnings=warnings,
        )

    def _parse_supplier(self, text: str) -> dict[str, Any]:
        contract = _match(r"采购单编号\s*[:：]?\s*([A-Z0-9-]+)", text)
        po_date = normalize_date(_match(r"日\s*期\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)", text))
        ship_date = normalize_date(_match(r"(\d{4}年\d{1,2}月\d{1,2}日)\s*前交货", text))
        version = _match(r"\b(\d+L\s*布标)\b", text)
        lines = []
        pattern = re.compile(
            r"(?m)^\s*(\d{4,}(?:-[A-Z0-9]+)?)\s*([^\d\n]{1,40}?)\s+([\d,]+)\s*(PCS|套|件)\b",
            re.I,
        )
        for found in pattern.finditer(text):
            lines.append(_line(
                found.group(1),
                found.group(2),
                _int_number(found.group(3)),
                unit=found.group(4),
                version=version,
            ))
        price_amount = re.search(r"([\d,]+(?:\.\d+)?)\s+([\d,]+\.\d{2})", text)
        if lines and price_amount:
            lines[-1]["unit_price_hkd"] = _number(price_amount.group(1))
        if not lines:
            raise POParseError("华康车衣采购单未识别到产品行；扫描图片请先另存为带文字层的 PDF")
        return _order(
            "supplier",
            po_number=contract,
            contract_no=contract,
            po_date=po_date,
            ship_date=ship_date,
            contact="阿许",
            version=version,
            lines=lines,
            warnings=["中文采购单的出厂价只在原单明确提供时写入，其余价格留空待人工确认。"],
        )


def validate(order: dict[str, Any]) -> list[str]:
    """返回不阻断处理、但需要用户留意的数据质量提示。"""
    warnings = []
    if not order.get("po_number"):
        warnings.append("未识别到 PO/合同号。")
    if not order.get("po_date"):
        warnings.append("未识别到接单日期。")
    if not order.get("ship_date"):
        warnings.append("未识别到走货截止日期。")
    lines = order.get("lines") or []
    if not lines:
        warnings.append("未识别到产品行。")
    for line in lines:
        item = line.get("item_code") or "未命名产品"
        qty = _number(line.get("qty"))
        price = _number(line.get("unit_price_usd"))
        amount = _number(line.get("amount_usd"))
        if qty <= 0:
            warnings.append(f"{item}：数量为空或为 0。")
        if qty and price and amount:
            expected = qty * price
            tolerance = max(1.0, amount * 0.001)
            if abs(expected - amount) > tolerance:
                warnings.append(f"{item}：数量×单价与总金额不一致，请复核。")
    return warnings
