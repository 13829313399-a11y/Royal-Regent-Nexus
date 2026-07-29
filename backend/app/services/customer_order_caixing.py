from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from typing import Any
import re

from lxml import etree

from app.services.customer_order_buzzbee import (
    MAX_BATCH_PO_BYTES,
    MAX_BATCH_PO_FILES,
    MAX_PO_BYTES,
    MAX_SCHEDULE_BYTES,
    NS,
    CustomerOrderWorkbookError,
    OoxmlSchedule,
    _clean_text,
    _decimal,
    _decimal_text,
    _decrypt_schedule,
    _encrypt_schedule,
)


PREVIEW_SCHEMA_VERSION = "customer-order-caixing-preview-v1"
INPUT_TEMPLATE = "CAIXING_PLAYMATES_PO_PDF_V1"
TARGET_TEMPLATE = "CAIXING_PURCHASE_ORDER_SCHEDULE_24COL_V1"

# The legacy Caixing utility writes these columns, in this exact order, to the
# active worksheet after ws.max_row. "客出单日" is backed by the parser key
# "证出单日" in the original utility.
EXPORT_COLUMNS = (
    "客出单日",
    "S/C NO",
    "PO.NO",
    "客名/国家",
    "产品编号",
    "产品名称",
    "数量",
    "装箱数",
    "箱数",
    "外尺",
    "CUFT",
    "G.W.",
    "N.W.",
    "行Q",
    "客Q",
    "日期码",
    "要求走货柜",
    "包装要求",
    "国家标",
    "备注",
    "生产车间",
    "上系统",
    "单价",
    "金额HKD",
)
EXPORT_COLUMN_LETTERS = tuple(
    chr(ord("A") + index) for index in range(len(EXPORT_COLUMNS))
)

PO_NUMBER_PATTERN = re.compile(r"\b([A-Z]{1,4}-[A-Z0-9]{4,})\b", re.IGNORECASE)
PRODUCT_CODE_PATTERN = re.compile(r"^\d{4,}[A-Z0-9]*$", re.IGNORECASE)
DIRECT_PRODUCT_PATTERN = re.compile(
    r"^\s*(\d{4,}[A-Z0-9]*)\s{2,}(.+?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s*$",
    re.IGNORECASE,
)
PRODUCT_HEADER_PATTERN = re.compile(
    r"^\s*(\d{4,}[A-Z0-9]*)\s+(.+?)\s*$",
    re.IGNORECASE,
)
DELIVERY_VALUES_PATTERN = re.compile(
    r"DELIVERY\s+DATE\s*:.*?\b(?:PC|PCS|SET)\b\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)",
    re.IGNORECASE,
)
NOISE_PATTERN = re.compile(
    r"^(Page\s*:|PRODUCT\s+NO|DESCRIPTION|REF|C\.O\.|U/M|ORDER\s+QTY|"
    r"UNIT\s+PRICE|AMOUNT|HKD|PURCHASE\s+ORDER|ASSORTMENT|TOTAL|Ship\s+to|"
    r"REMARKS|SHIPPING\s+MARKS|VENDOR\s+CONF|Playmates\s+International|"
    r"9th\s+Floor|Tel:|This\s+is\s+a|Ultimate\s+Consignee|SELLER|BUYER|"
    r"REV\s+NO|REV\.\s+DATE|DELIVERY\s+DATE|MIX:|Customer\s+Item|"
    r"PAYMENT\s+TERM|TERMS\s+OF\s+SALE|OUR\s+REF|ATTN|EX-FTY|FCA)",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"^[\d,]+\.?\d*$")
STANDALONE_PRODUCT_PATTERN = re.compile(r"^([A-Z0-9]{4,15})$", re.IGNORECASE)
NOT_PRODUCT_PATTERN = re.compile(
    r"^(\d{4}/\d{2}/\d{2}|\d{1,3}$|\d+\s+PCS/CTN|"
    r"[A-Z]{1,4}-[A-Z0-9]+|20\d{2}$)",
    re.IGNORECASE,
)


@dataclass
class CaixingParsedLine:
    source_date: str = ""
    contract_no: str = ""
    po_no: str = ""
    customer_name: str = ""
    product_no: str = ""
    product_name_en: str = ""
    quantity: Decimal | None = None
    unit_price_hkd: Decimal | None = None
    amount_hkd: Decimal | None = None
    packaging: str = ""
    lineage: dict[str, str] | None = None


def _slash_date(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw or "").strip()
    match = re.search(r"(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    if match:
        first, second, third = match.groups()
        if len(first) == 4:
            return f"{first}/{int(second):02d}/{int(third):02d}"
        if len(third) == 4:
            return f"{third}/{int(second):02d}/{int(first):02d}"
    english = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not english:
        return ""
    month = datetime.strptime(english.group(1)[:3], "%b").month
    return f"{english.group(3)}/{month:02d}/{int(english.group(2)):02d}"


def _iso_date(slash_date: str) -> str:
    if not slash_date:
        return ""
    try:
        return datetime.strptime(slash_date, "%Y/%m/%d").date().isoformat()
    except ValueError:
        return ""


def _normalize_contract(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _normalize_product_code(value: str) -> str:
    code = re.sub(r"\s+", "", value or "").upper()
    match = re.match(r"^(\d+)([A-Z].*)$", code, re.IGNORECASE)
    return f"{match.group(1)} {match.group(2).upper()}" if match else code


def _extract_header(text: str) -> dict[str, str]:
    date_match = re.search(
        r"\bDATE\s*:\s*(?:\n\s*)?([^\n]+)",
        text,
        re.IGNORECASE,
    )
    source_date = _slash_date(date_match.group(1) if date_match else "")

    contract_match = re.search(
        r"OUR\s+CONF\s+NO\s*:\s*(?:\n\s*)?([^\n]+)",
        text,
        re.IGNORECASE,
    )
    contract_no = ""
    if contract_match:
        contract_no = re.split(
            r"\s{2,}(?:ATTN|PAYMENT|OUR\s+REF|TERMS)",
            contract_match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        contract_no = _normalize_contract(contract_no)

    page_po_match = re.search(
        r"Page\s*:\s*\d+\s+of\s+\d+\s*(?:\n|\s)+"
        r"([A-Z]{1,4}-[A-Z0-9]{4,})",
        text,
        re.IGNORECASE,
    )
    po_match = page_po_match or PO_NUMBER_PATTERN.search(text[:800])
    po_no = po_match.group(1).upper() if po_match else ""

    customer_match = re.search(
        r"CUSTOMER\s*:\s*(?:\n\s*)?([^\n]+)",
        text,
        re.IGNORECASE,
    )
    customer_name = ""
    if customer_match:
        customer_name = re.split(
            r"\s{2,}(?:OUR\s+CONF|ATTN|PAYMENT|OUR\s+REF)",
            customer_match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    if not customer_name:
        fallback = re.search(
            r"(?:SOLD\s+TO|BUYER)\s*:\s*(?:\n\s*)?"
            r"([A-Z][A-Z\s&',.]{3,40})",
            text,
            re.IGNORECASE,
        )
        customer_name = fallback.group(1) if fallback else ""
    customer_name = re.sub(r"\s*\(.*?\)", "", customer_name).strip()
    customer_name = re.sub(
        r"\s+Playmates.*$",
        "",
        customer_name,
        flags=re.IGNORECASE,
    ).strip()

    upper = text.upper()
    packaging = ""
    if "US STANDARD" in upper or "USA STANDARD" in upper:
        packaging = "美国包装"
    elif "EU STANDARD" in upper or "EUROPEAN STANDARD" in upper:
        packaging = "欧洲包装"

    return {
        "source_date": source_date,
        "contract_no": contract_no,
        "po_no": po_no,
        "customer_name": customer_name,
        "packaging": packaging,
    }


def _product_from_values(
    code: str,
    description: str,
    quantity: str,
    unit_price: str,
    amount: str,
) -> dict[str, Any]:
    normalized_quantity = _decimal(quantity)
    normalized_price = _decimal(unit_price)
    normalized_amount = _decimal(amount)
    if (
        normalized_amount is None
        and normalized_quantity is not None
        and normalized_price is not None
    ):
        normalized_amount = (normalized_quantity * normalized_price).quantize(
            Decimal("0.01")
        )
    return {
        "product_no": _normalize_product_code(code),
        "product_name_en": _clean_text(description),
        "quantity": normalized_quantity,
        "unit_price_hkd": normalized_price,
        "amount_hkd": normalized_amount,
    }


def _extract_products_from_table_lines(text: str) -> list[dict[str, Any]]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    products: list[dict[str, Any]] = []
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        direct = DIRECT_PRODUCT_PATTERN.match(line)
        if direct:
            products.append(_product_from_values(*direct.groups()))
            continue

        header = PRODUCT_HEADER_PATTERN.match(line)
        if not header:
            continue
        code, description = header.groups()
        if NOT_PRODUCT_PATTERN.match(code) or len(code) < 4:
            continue

        # A single-product PO places quantity, unit price and amount on its
        # DELIVERY DATE line. Assortment parent rows have no trailing values
        # and are intentionally ignored, matching the legacy utility's
        # _is_real_product filter.
        for candidate in lines[index + 1:index + 8]:
            if DIRECT_PRODUCT_PATTERN.match(candidate.strip()):
                break
            next_header = PRODUCT_HEADER_PATTERN.match(candidate.strip())
            if next_header and PRODUCT_CODE_PATTERN.match(next_header.group(1)):
                break
            delivery = DELIVERY_VALUES_PATTERN.search(candidate)
            if delivery:
                products.append(
                    _product_from_values(
                        code,
                        description,
                        delivery.group(1),
                        delivery.group(2),
                        delivery.group(3),
                    )
                )
                break
    return products


def _extract_products_legacy_lines(text: str) -> list[dict[str, Any]]:
    """Fallback for PyMuPDF-style text where each table cell is its own line."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    raw_products: list[dict[str, str | None]] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        matched = STANDALONE_PRODUCT_PATTERN.match(line)
        if not matched or NOT_PRODUCT_PATTERN.match(line):
            index += 1
            continue
        code = matched.group(1)
        if len(code) < 4 or re.match(r"^20\d{2}$", code):
            index += 1
            continue
        cursor = index + 1
        description: str | None = None
        quantity: str | None = None
        unit_price: str | None = None
        amount: str | None = None
        while cursor < len(lines) and not (
            description is not None
            and quantity is not None
            and unit_price is not None
        ):
            candidate = lines[cursor].strip()
            next_product = STANDALONE_PRODUCT_PATTERN.match(candidate)
            if (
                next_product
                and not NOT_PRODUCT_PATTERN.match(candidate)
                and len(candidate) >= 4
            ):
                break
            if NOISE_PATTERN.match(candidate):
                cursor += 1
                continue
            if NUMBER_PATTERN.match(candidate):
                value = candidate.replace(",", "")
                if quantity is None:
                    quantity = value
                elif unit_price is None:
                    unit_price = value
                elif amount is None:
                    amount = value
            elif (
                description is None
                and len(candidate) > 4
                and not candidate.startswith("Page")
                and re.search(r"[A-Za-z]", candidate)
            ):
                description = candidate
            cursor += 1
        raw_products.append(
            {
                "code": code,
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
            }
        )
        index = cursor

    normalized = [
        _product_from_values(
            str(product["code"] or ""),
            str(product["description"] or ""),
            str(product["quantity"] or ""),
            str(product["unit_price"] or ""),
            str(product["amount"] or ""),
        )
        for product in raw_products
    ]
    real = [
        product
        for product in normalized
        if product["quantity"] is not None
        and "PCS/CTN" not in product["product_name_en"].upper()
        and "TOTAL" not in product["product_name_en"].upper()
        and not (
            product["quantity"] <= 9 and not product["product_name_en"]
        )
    ]
    return real or normalized


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise CustomerOrderWorkbookError(f"彩星 PDF 无法读取：{exc}") from exc
    text = "\n".join(pages)
    if not text.strip():
        raise CustomerOrderWorkbookError(
            "彩星 PDF 没有可读取的文本层；当前映射对应旧插件的 Playmates 文本型 PDF"
        )
    return text


def parse_caixing_pdf(file_name: str, content: bytes) -> list[CaixingParsedLine]:
    if not file_name.lower().endswith(".pdf"):
        raise CustomerOrderWorkbookError("彩星 PO 只支持 .pdf")
    text = _extract_pdf_text(content)
    header = _extract_header(text)
    products = _extract_products_from_table_lines(text)
    if not products:
        products = _extract_products_legacy_lines(text)
    if not products:
        raise CustomerOrderWorkbookError("未从彩星 Playmates PDF 识别到产品明细")

    return [
        CaixingParsedLine(
            source_date=header["source_date"],
            contract_no=header["contract_no"],
            po_no=header["po_no"],
            customer_name=header["customer_name"],
            product_no=product["product_no"],
            product_name_en=product["product_name_en"],
            quantity=product["quantity"],
            unit_price_hkd=product["unit_price_hkd"],
            amount_hkd=product["amount_hkd"],
            packaging=header["packaging"],
            lineage={
                "received_date": f"{file_name} · DATE",
                "po_no": f"{file_name} · Page / PO.NO",
                "contract_no": f"{file_name} · OUR CONF NO",
                "customer_country": f"{file_name} · CUSTOMER",
                "product_no": f"{file_name} · PRODUCT NO",
                "product_name_en": f"{file_name} · DESCRIPTION",
                "quantity": f"{file_name} · ORDER QTY",
                "unit_price_hkd": f"{file_name} · UNIT PRICE HKD",
                "amount_hkd": f"{file_name} · AMOUNT HKD",
                "packaging": f"{file_name} · REMARKS / STANDARD PACKAGING",
            },
        )
        for product in products
    ]


class CaixingSchedule(OoxmlSchedule):
    active_sheet_name: str

    def _validate_template(self) -> None:
        if not self.sheet_paths:
            raise CustomerOrderWorkbookError("彩星排期没有可写入的工作表")
        workbook = etree.fromstring(self.parts["xl/workbook.xml"])
        sheets = workbook.findall("m:sheets/m:sheet", NS)
        view = workbook.find("m:bookViews/m:workbookView", NS)
        try:
            active_index = int(view.get("activeTab", "0")) if view is not None else 0
        except ValueError:
            active_index = 0
        active_index = min(max(active_index, 0), len(sheets) - 1)
        self.active_sheet_name = sheets[active_index].get("name", "")
        if self.active_sheet_name not in self.sheet_paths:
            raise CustomerOrderWorkbookError("彩星排期的当前活动工作表无法写入")

    def find_legacy_header_row(self) -> int | None:
        for row_number, values in self.read_rows(self.active_sheet_name).items():
            if row_number > 50:
                break
            if tuple(values.get(letter, "").strip() for letter in EXPORT_COLUMN_LETTERS) == EXPORT_COLUMNS:
                return row_number
        return None

    def append_records(self, records: list[dict[str, Any]]) -> None:
        rows = self.read_rows(self.active_sheet_name)
        if not rows:
            raise CustomerOrderWorkbookError(
                "彩星排期当前活动工作表为空，没有可复用的表头或数据行样式"
            )
        append_row = max(rows) + 1
        for offset, record in enumerate(records):
            row_number = append_row + offset
            reference_row = row_number - 1
            values: dict[str, dict[str, Any]] = {}
            for letter, column in zip(
                EXPORT_COLUMN_LETTERS,
                EXPORT_COLUMNS,
                strict=True,
            ):
                value = record.get(column)
                values[letter] = {
                    "value": value,
                    "inline": isinstance(value, str),
                }
            self.insert_row_at(
                self.active_sheet_name,
                insert_row=row_number,
                reference_row_number=reference_row,
                values=values,
            )


def _make_issue(
    severity: str,
    code: str,
    field: str,
    message: str,
    *,
    can_skip: bool = False,
    skip_label: str = "",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "field": field,
        "message": message,
        "can_skip": can_skip,
        "skip_key": "",
        "skip_label": skip_label,
    }


def _export_record(parsed: CaixingParsedLine, fallback_received_date: str) -> dict[str, Any]:
    amount = parsed.amount_hkd
    if (
        amount is None
        and parsed.quantity is not None
        and parsed.unit_price_hkd is not None
    ):
        amount = (parsed.quantity * parsed.unit_price_hkd).quantize(Decimal("0.01"))
    return {
        "客出单日": parsed.source_date
        or fallback_received_date.replace("-", "/"),
        "S/C NO": parsed.contract_no or None,
        "PO.NO": parsed.po_no or None,
        "客名/国家": parsed.customer_name or None,
        "产品编号": parsed.product_no or None,
        "产品名称": parsed.product_name_en or None,
        "数量": parsed.quantity,
        "装箱数": None,
        "箱数": None,
        "外尺": None,
        "CUFT": None,
        "G.W.": None,
        "N.W.": None,
        "行Q": None,
        "客Q": None,
        "日期码": None,
        "要求走货柜": None,
        "包装要求": parsed.packaging or None,
        "国家标": None,
        "备注": None,
        "生产车间": None,
        "上系统": None,
        "单价": parsed.unit_price_hkd,
        "金额HKD": amount,
    }


def _preview_row(
    parsed: CaixingParsedLine,
    *,
    file_name: str,
    row_index: int,
    fallback_received_date: str,
    active_sheet_name: str,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    required = {
        "po_no": ("P/O#", parsed.po_no),
        "product_no": ("产品编号", parsed.product_no),
        "product_name_en": ("产品名称", parsed.product_name_en),
        "quantity": (
            "数量",
            _decimal_text(parsed.quantity) if parsed.quantity is not None else "",
        ),
    }
    for field_name, (label, value) in required.items():
        if not value:
            issues.append(
                _make_issue(
                    "blocked",
                    "missing_required_field",
                    field_name,
                    f"{label} 未能从彩星 PDF 提取",
                )
            )
    if not parsed.contract_no:
        issues.append(
            _make_issue(
                "blocked",
                "missing_contract_no",
                "contract_no",
                "S/C NO 未能从彩星 PDF 提取",
                can_skip=True,
                skip_label="S/C NO 留空，稍后由跟客补充",
            )
        )
    if not parsed.customer_name:
        issues.append(
            _make_issue(
                "blocked",
                "missing_customer",
                "customer_country",
                "客名/国家未能从彩星 PDF 提取",
                can_skip=True,
                skip_label="客名/国家留空，稍后由跟客补充",
            )
        )
    if parsed.unit_price_hkd is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_unit_price",
                "unit_price_hkd",
                "单价及金额未能从彩星 PDF 提取",
                can_skip=True,
                skip_label="单价及金额留空，稍后由跟客补充",
            )
        )
    if not parsed.packaging:
        issues.append(
            _make_issue(
                "warning",
                "missing_packaging",
                "packaging",
                "未在备注中识别到 US/EU STANDARD 包装要求，将按旧插件规则留空",
            )
        )

    status = (
        "blocked"
        if any(issue["severity"] == "blocked" for issue in issues)
        else "warning"
        if issues
        else "valid"
    )
    row_id = (
        f"caixing-{parsed.po_no or row_index}-"
        f"{parsed.product_no.replace(' ', '') or row_index}-{row_index}"
    )
    for issue in issues:
        if issue["can_skip"]:
            issue["skip_key"] = f"{row_id}|{issue['code']}|{issue['field']}"

    received = _iso_date(parsed.source_date) or fallback_received_date
    amount = parsed.amount_hkd
    if (
        amount is None
        and parsed.quantity is not None
        and parsed.unit_price_hkd is not None
    ):
        amount = parsed.quantity * parsed.unit_price_hkd
    lineage = dict(parsed.lineage or {})
    lineage.update(
        {
            "product_name_zh": "旧插件未映射 · 留空待跟客补充",
            "units_per_carton": "旧插件固定空列 · 装箱数",
            "carton_count": "旧插件固定空列 · 箱数",
            "standard": "旧插件固定空列 · 国家标",
            "line_q": "旧插件固定空列 · 行Q",
            "customer_q": "旧插件固定空列 · 客Q",
            "requested_ship_date": "旧插件固定空列 · 要求走货柜",
        }
    )
    return {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "有效", "warning": "警告", "blocked": "阻断"}[status],
        "received_date": received,
        "po_no": parsed.po_no,
        "contract_no": parsed.contract_no,
        "customer_country": parsed.customer_name,
        "customer_name": parsed.customer_name,
        "country": "",
        "product_no": parsed.product_no,
        "product_name_zh": "",
        "product_name_en": parsed.product_name_en,
        "quantity": _decimal_text(parsed.quantity),
        "units_per_carton": "",
        "carton_count": "",
        "standard": "",
        "unit_price_hkd": _decimal_text(parsed.unit_price_hkd),
        "amount_hkd": _decimal_text(amount),
        "packaging": parsed.packaging,
        "line_q": "",
        "customer_q": "",
        "requested_ship_date": "",
        "input_template": INPUT_TEMPLATE,
        "target_template": TARGET_TEMPLATE,
        "item_sheet_name": active_sheet_name,
        "source_po_file_name": file_name,
        "lineage": lineage,
        "issues": issues,
        "_export_record": _export_record(parsed, fallback_received_date),
    }


def _combined_hash(file_names: list[str], hashes: list[str]) -> str:
    if len(hashes) == 1:
        return hashes[0]
    return sha256(
        "\n".join(
            f"{name}:{digest}"
            for name, digest in zip(file_names, hashes, strict=True)
        ).encode("utf-8")
    ).hexdigest()


def create_caixing_batch_preview(
    *,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> dict[str, Any]:
    if factory_id != "huaxing":
        raise CustomerOrderWorkbookError("彩星只属于华兴厂区，不能导入其他厂区")
    if not po_files:
        raise CustomerOrderWorkbookError("请至少上传一份彩星 PDF")
    if len(po_files) > MAX_BATCH_PO_FILES:
        raise CustomerOrderWorkbookError(
            f"单批最多上传 {MAX_BATCH_PO_FILES} 份彩星 PDF"
        )
    if sum(len(content) for _, content in po_files) > MAX_BATCH_PO_BYTES:
        raise CustomerOrderWorkbookError("本批彩星 PDF 合计超过 80MB 限制")
    if any(len(content) > MAX_PO_BYTES for _, content in po_files):
        raise CustomerOrderWorkbookError("单份彩星 PDF 不能超过 12MB")
    if len(schedule_content) > MAX_SCHEDULE_BYTES:
        raise CustomerOrderWorkbookError("彩星客户排期超过 35MB 限制")
    try:
        normalized_received_date = date.fromisoformat(received_date).isoformat()
    except ValueError as exc:
        raise CustomerOrderWorkbookError("来单日期必须是 YYYY-MM-DD") from exc

    plain_schedule, encrypted = _decrypt_schedule(schedule_content)
    schedule = CaixingSchedule(plain_schedule)
    header_row = schedule.find_legacy_header_row()
    rows: list[dict[str, Any]] = []
    row_index = 0
    for file_name, content in po_files:
        try:
            parsed_lines = parse_caixing_pdf(file_name, content)
        except CustomerOrderWorkbookError as exc:
            raise CustomerOrderWorkbookError(f"{file_name}：{exc}") from exc
        for parsed in parsed_lines:
            row_index += 1
            rows.append(
                _preview_row(
                    parsed,
                    file_name=file_name,
                    row_index=row_index,
                    fallback_received_date=normalized_received_date,
                    active_sheet_name=schedule.active_sheet_name,
                )
            )

    summary = {
        "total": len(rows),
        "valid": sum(row["status"] == "valid" for row in rows),
        "warning": sum(row["status"] == "warning" for row in rows),
        "blocked": sum(row["status"] == "blocked" for row in rows),
    }
    file_names = [name for name, _ in po_files]
    po_hashes = [sha256(content).hexdigest() for _, content in po_files]
    warnings = [
        "彩星映射来自旧 Playmates PO 工具：固定24列追加到目标Excel的当前活动工作表末行。",
        "旧工具不提取中文名称、装箱数、箱数、行Q、客Q、要求走货柜及生产字段；本次保持为空，不代替跟客补录。",
        (
            f"已在活动工作表“{schedule.active_sheet_name}”第 {header_row} 行识别旧插件24列表头。"
            if header_row is not None
            else f"活动工作表“{schedule.active_sheet_name}”未识别到完整24列表头，将按旧插件规则直接追加到现有末行。"
        ),
        (
            "上传排期已加密；输出保留 2026 打开密码。"
            if encrypted
            else "上传排期未加密；输出保持未加密。"
        ),
    ]
    return {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "customer_code": "caixing",
        "factory_id": factory_id,
        "po_file_name": file_names[0] if len(file_names) == 1 else f"{len(file_names)}个PDF",
        "po_file_names": file_names,
        "po_file_count": len(file_names),
        "schedule_file_name": schedule_file_name,
        "source_po_sha256": _combined_hash(file_names, po_hashes),
        "source_po_sha256s": po_hashes,
        "source_schedule_sha256": sha256(schedule_content).hexdigest(),
        "input_template": INPUT_TEMPLATE,
        "target_template": TARGET_TEMPLATE,
        "output_file_name": schedule_file_name,
        "summary": summary,
        "rows": rows,
        "warnings": warnings,
        "_schedule_encrypted": encrypted,
    }


def _validate_skips(preview: dict[str, Any], requested_skips: set[str]) -> None:
    available = {
        issue["skip_key"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["can_skip"]
    }
    if requested_skips - available:
        raise CustomerOrderWorkbookError(
            "所选跳过项已失效或不允许跳过，请重新解析后再确认"
        )
    remaining = [
        issue["message"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["severity"] == "blocked"
        and issue["skip_key"] not in requested_skips
    ]
    if remaining:
        raise CustomerOrderWorkbookError("仍有阻断项：" + "；".join(remaining))


def export_caixing_batch_schedule(
    *,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
    skipped_issue_keys: set[str] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    preview = create_caixing_batch_preview(
        factory_id=factory_id,
        received_date=received_date,
        po_files=po_files,
        schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
    )
    _validate_skips(preview, skipped_issue_keys or set())
    plain_schedule, encrypted = _decrypt_schedule(schedule_content)
    workbook = CaixingSchedule(plain_schedule)
    workbook.append_records(
        [row["_export_record"] for row in preview["rows"]]
    )
    workbook.set_recalculation()
    output = workbook.to_bytes()
    if encrypted:
        output = _encrypt_schedule(output)
    return output, schedule_file_name, preview
