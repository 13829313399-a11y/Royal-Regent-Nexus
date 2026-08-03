# -*- coding: utf-8 -*-
"""Spin Master PO parser for Royal Regent purchase orders."""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable

import openpyxl
import pdfplumber


def normalize_date(value: Any) -> str:
    """Return YYYY-MM-DD for common Spin Master PO date formats."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip().replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def _num(value: Any) -> float:
    """兼容美式(1,096.00)与欧洲(1.096,00)两种数字格式。

    Spin Master 不同下单主体的 PO 会混用两种格式；只按美式处理会把
    4.273,96 截成 4.273，造成金额错误。
    """
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        if len(tail) == 2 and head:
            text = head.replace(",", "").replace(".", "") + "." + tail
        else:
            text = text.replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _field(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return default
    return re.sub(r"\s+", " ", m.group(1)).strip()


@dataclass
class SpinLine:
    line_no: str
    qty: float
    unit: str
    material_number: str
    description_en: str = ""
    sales_material: str = ""
    material_group: str = ""
    price_per: float = 0.0
    price_per_qty: float = 1.0
    currency: str = "USD"
    ship_date: str = ""
    net_value_pdf: float = 0.0
    sales_order: str = ""
    line_item: str = ""
    customer: str = ""
    customer_po: str = ""
    components: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unit_price_usd(self) -> float:
        base = self.price_per_qty or 1.0
        return self.price_per / base if self.price_per else 0.0

    @property
    def total_usd(self) -> float:
        return self.qty * self.unit_price_usd

    def to_dict(self) -> dict:
        data = asdict(self)
        data["unit_price"] = round(self.unit_price_usd, 6)
        data["total_usd"] = round(self.total_usd, 6)
        data["contract_suffix"] = self.line_no
        data["item_key"] = "/".join(
            part for part in (self.material_group, self.material_number, self.sales_material) if part
        )
        return data


class SpinPOParser:
    """Parse Spin Master PDF POs and converted Excel text dumps."""

    # 数字兼容美式 1,096.00 与欧洲 1.096,00 两种写法，交给 _num 归一化。
    LINE_RE = re.compile(r"^(\d+)\s+(\d[\d.,]*)\s+([A-Z]+)\s+(\d{5,})$")
    SALES_MATERIAL_RE = re.compile(
        r"Sales\s+Material:\s*(\d+)\s+(\d[\d.,]*)\s+([A-Z]{3})\s+Per\s+"
        r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d[\d.,]*)",
        re.IGNORECASE,
    )
    MATERIAL_GROUP_RE = re.compile(r"Material\s+Group:\s*(\d+)\s+(\d[\d.,]*)\s+([A-Z]+)", re.I)
    SALES_ORDER_RE = re.compile(r"Sales\s+Order:\s*(\d+)\s+Line\s+Item:\s*(\d+)", re.I)
    CUSTOMER_PO_RE = re.compile(r"Customer\s+PO:\s*(.+)", re.I)

    def parse(self, path: str) -> dict:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            text = self._text_from_pdf(path)
        elif ext in (".xlsx", ".xlsm"):
            text = self._text_from_excel(path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

        header = self._parse_header(text)
        lines = [line.to_dict() for line in self._parse_lines(text)]
        if not lines:
            raise ValueError("未识别到 PO 明细行")
        return {**header, "lines": lines, "raw_text": text[:10000]}

    def _text_from_pdf(self, path: str) -> str:
        chunks = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
        return "\n".join(chunks)

    def _text_from_excel(self, path: str) -> str:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            rows = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(max_row=1000, max_col=80, values_only=True):
                    vals = [_clean(v) for v in row if _clean(v)]
                    if vals:
                        rows.append(" ".join(vals))
            return "\n".join(rows)
        finally:
            wb.close()

    def _parse_header(self, text: str) -> dict:
        po = _field(r"NUMBER\s+PAGE\s*\n\s*(\d{6,})\s+Page", text)
        if not po:
            po = _field(r"\b(?:PURCHASE\s+ORDER\s+)?(?:NUMBER|NO\.?)\s*:?\s*(\d{6,})", text)
        po_date = normalize_date(_field(r"\bDATE\b[\s\S]{0,220}?(\d{1,2}/\d{1,2}/\d{4})", text))
        buyer = _field(r"\bBUYER\b.*?\n\s*\d+\s+\S+.*?\n\s*([A-Za-z][A-Za-z ]+)", text)
        if not buyer:
            buyer = _field(r"\b(Karen\s+Sun|Nina\s+Xie|Michelle\s+Fang|Luse\s+Zhou|Ivy\s+Deng)\b", text)
        incoterms = _field(r"\bINCOTERMS\b.*?\n.*?\b(FCA|FOB|EXW|CIF|CFR)\b", text)
        return {
            "po_number": po,
            "po_date": po_date,
            "buyer": buyer,
            "contact": buyer,
            "incoterms": incoterms,
            "customer": "SPIN MASTER",
        }

    def _parse_lines(self, text: str) -> list[SpinLine]:
        lines = list(self._candidate_lines(text))
        starts = [i for i, line in enumerate(lines) if self.LINE_RE.match(line)]
        parsed: list[SpinLine] = []
        for pos, start in enumerate(starts):
            end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
            block = lines[start:end]
            product = self._parse_product_block(block)
            if product:
                parsed.append(product)
        return parsed

    @staticmethod
    def _candidate_lines(text: str) -> Iterable[str]:
        for raw in text.splitlines():
            line = re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip()
            if line:
                yield line

    def _parse_product_block(self, block: list[str]) -> SpinLine | None:
        if not block:
            return None
        m = self.LINE_RE.match(block[0])
        if not m:
            return None

        line = SpinLine(
            line_no=m.group(1),
            qty=_num(m.group(2)),
            unit=m.group(3),
            material_number=m.group(4),
        )
        desc_parts = []
        customer_parts = []
        collecting_customer = False
        current_component: dict[str, Any] | None = None

        for raw in block[1:]:
            if self._is_header_noise(raw):
                continue

            sales = self.SALES_MATERIAL_RE.search(raw)
            if sales:
                line.sales_material = sales.group(1)
                line.price_per = _num(sales.group(2))
                line.currency = sales.group(3).upper()
                line.ship_date = normalize_date(sales.group(4))
                line.net_value_pdf = _num(sales.group(5))
                continue

            group = self.MATERIAL_GROUP_RE.search(raw)
            if group:
                line.material_group = group.group(1)
                line.price_per_qty = _num(group.group(2)) or 1.0
                continue

            order = self.SALES_ORDER_RE.search(raw)
            if order:
                line.sales_order = order.group(1)
                line.line_item = order.group(2)
                collecting_customer = False
                continue

            po = self.CUSTOMER_PO_RE.search(raw)
            if po:
                line.customer_po = po.group(1).strip()
                collecting_customer = False
                continue

            if raw.lower().startswith("customer:"):
                customer_parts = [raw.split(":", 1)[1].strip()]
                collecting_customer = True
                continue

            if collecting_customer:
                if raw.startswith(("Line ", "No ", "TOTAL", "TERMS", "COMMENTS")):
                    collecting_customer = False
                else:
                    customer_parts.append(raw)
                    continue

            component_code = re.fullmatch(r"8\d{5}", raw)
            if component_code:
                current_component = {"code": raw, "description": "", "qty": "", "unit": ""}
                line.components.append(current_component)
                continue

            if current_component and not raw.startswith(("Sales Order:", "Customer:")):
                cm = re.match(r"(.+?)\s+([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)?$", raw)
                if cm:
                    current_component["description"] = cm.group(1).strip()
                    current_component["qty"] = _num(cm.group(2))
                    if cm.group(3):
                        current_component["unit"] = cm.group(3)
                    continue
                if raw.lower() == "piece":
                    current_component["unit"] = "Piece"
                    continue

            if not line.sales_material and not raw.startswith(("We provide", "Material Group:")):
                desc_parts.append(raw)

        line.description_en = "\n".join(desc_parts).strip()
        line.customer = " / ".join(p for p in customer_parts if p).strip()
        return line

    @staticmethod
    def _is_header_noise(line: str) -> bool:
        prefixes = (
            "PURCHASE ORDER",
            "Spin Master Toys",
            "Rm 1113",
            "Tsim Sha Tsui",
            "Phone ",
            "Fax ",
            "Company FSC",
            "ORDERED FROM:",
            "ROYAL REGENT",
            "UNIT 07-08",
            "CONCORDIA PLAZA",
            "NO.1 SCIENCE",
            "HONG KONG",
            "BUYER ",
            "Line QUANTITY",
            "No ORDERED",
            "NUMBER PAGE",
            "DATE",
            "SHIP TO",
            "TERMS AND CONDITIONS",
            "By accepting",
            "agreed otherwise",
            "COMMENTS",
            "This PO is electronically",
        )
        return line.startswith(prefixes) or bool(re.fullmatch(r"\d{6,}\s+Page\s+\d+\s+of\s+\d+", line))


def validate(parsed: dict, filename: str = "") -> list[str]:
    warnings = []
    if not parsed.get("po_number"):
        warnings.append(f"{filename}: 未识别到 PO 号码")
    if not parsed.get("po_date"):
        warnings.append(f"{filename}: 未识别到 PO 日期")
    for line in parsed.get("lines", []):
        label = f"{filename} Line {line.get('line_no', '')}".strip()
        if not line.get("ship_date"):
            warnings.append(f"{label}: 未识别到交期")
        if not line.get("sales_order"):
            warnings.append(f"{label}: 未识别到 Sales Order")
        if not line.get("customer_po"):
            warnings.append(f"{label}: 未识别到 Customer PO")
        # 自洽校验：数量 × 单价 ÷ 计价基数(如 Per 1000 PC) = NET VALUE（容差2分钱）
        qty = line.get("qty") or 0
        price = line.get("price_per") or 0
        per = line.get("price_per_qty") or 1
        net = line.get("net_value_pdf") or 0
        if qty > 0 and price > 0 and net > 0:
            expect = round(qty * price / per, 2)
            if abs(expect - net) > 0.021:
                warnings.append(
                    f"{label}: 数量×单价校验不符（{qty}×{price}/{per}={expect} ≠ NET {net}），"
                    "可能存在金额识别错误，请人工核对"
                )
    return warnings
