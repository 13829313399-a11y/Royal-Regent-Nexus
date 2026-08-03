from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from typing import Any
import re

from lxml import etree

from app.services.customer_order_buzzbee import (
    MAIN_NS,
    MAX_BATCH_PO_BYTES,
    MAX_BATCH_PO_FILES,
    MAX_PO_BYTES,
    MAX_SCHEDULE_BYTES,
    NS,
    SCHEDULE_PASSWORD,
    CustomerOrderWorkbookError,
    OoxmlSchedule,
    _clean_text,
    _decimal,
    _decimal_text,
    _decrypt_schedule,
    _encrypt_schedule,
)
from app.services.legacy_excel_bridge import (
    LegacyExcelConversionError,
    convert_legacy_xls_to_xlsx,
    convert_xlsx_to_legacy_xls,
    is_legacy_xls_workbook,
)


PREVIEW_SCHEMA_VERSION = "customer-order-caixing-preview-v2"
INPUT_TEMPLATE = "CAIXING_PLAYMATES_PO_PDF_V2"
TARGET_TEMPLATE = "CAIXING_PRODUCTION_SCHEDULE_REVIEW_ORDER_ITEM_V2"
PRICE_FACTOR = Decimal("0.955")

REVIEW_SHEET = "正单评审表"
ORDER_SHEET = "接单表"
ITEM_SHEET = "ITEM表"
REQUIRED_SHEETS = {REVIEW_SHEET, ORDER_SHEET, ITEM_SHEET}
CURRENT_ORDER_MARKER = "以下是2026年预备单"

PO_NUMBER_PATTERN = re.compile(r"\b([A-Z]{1,4}-[A-Z0-9]{4,})\b", re.IGNORECASE)
PRODUCT_CODE_PATTERN = re.compile(r"^\d{4,}[A-Z0-9-]*$", re.IGNORECASE)
PRODUCT_HEADER_PATTERN = re.compile(
    r"^\s*(\d{4,}[A-Z0-9-]*)\s+(.+?)\s*$",
    re.IGNORECASE,
)
DIRECT_PRODUCT_PATTERN = re.compile(
    r"^\s*(\d{4,}[A-Z0-9-]*)\s{2,}(.+?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s*$",
    re.IGNORECASE,
)
DELIVERY_DATE_PATTERN = re.compile(
    r"DELIVERY\s+DATE\s*:\s*(\d{4}[/.-]\d{1,2}[/.-]\d{1,2})",
    re.IGNORECASE,
)
DELIVERY_VALUES_PATTERN = re.compile(
    r"DELIVERY\s+DATE\s*:.*?\b(?:PC|PCS|SET)\b\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)",
    re.IGNORECASE,
)
ASSORTMENT_LINE_PATTERN = re.compile(
    r"^(?:ASSORTMENT\s*:\s*)?(\d{4,}[A-Z0-9-]*)\s+(\d+)\s*$",
    re.IGNORECASE,
)
PCS_PER_CARTON_PATTERN = re.compile(r"\b(\d+)\s+PCS/CTN\b", re.IGNORECASE)
PACK_SUFFIX_PATTERN = re.compile(r"E(\d+)$", re.IGNORECASE)

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
STANDALONE_PRODUCT_PATTERN = re.compile(r"^([A-Z0-9-]{4,15})$", re.IGNORECASE)
NOT_PRODUCT_PATTERN = re.compile(
    r"^(\d{4}/\d{2}/\d{2}|\d{1,3}$|\d+\s+PCS/CTN|"
    r"[A-Z]{1,4}-[A-Z0-9]+|20\d{2}$)",
    re.IGNORECASE,
)


@dataclass
class CaixingParsedLine:
    source_po_date: str = ""
    requested_ship_date: str = ""
    contract_no: str = ""
    po_no: str = ""
    customer_name: str = ""
    product_no: str = ""
    product_name_en: str = ""
    quantity: Decimal | None = None
    raw_unit_price_hkd: Decimal | None = None
    raw_amount_hkd: Decimal | None = None
    units_per_carton: Decimal | None = None
    parent_product_no: str = ""
    parent_product_name_en: str = ""
    parent_quantity: Decimal | None = None
    parent_units_per_carton: Decimal | None = None
    group_id: str = ""
    packaging: str = ""
    standard: str = ""
    lineage: dict[str, str] | None = None

    @property
    def unit_price_hkd(self) -> Decimal | None:
        if self.raw_unit_price_hkd is None:
            return None
        return self.raw_unit_price_hkd * PRICE_FACTOR

    @property
    def amount_hkd(self) -> Decimal | None:
        if self.quantity is None or self.unit_price_hkd is None:
            return None
        return self.quantity * self.unit_price_hkd


@dataclass(frozen=True)
class PreparedCaixingSchedule:
    ooxml_content: bytes
    encrypted: bool
    legacy_xls: bool


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


def _matrix_product_key(value: str) -> str:
    match = re.match(r"\s*(\d{4,})", str(value or ""))
    return match.group(1) if match else re.sub(r"\s+", "", str(value or "")).upper()


def _assortment_product_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _extract_metadata(text: str) -> dict[str, str]:
    date_match = re.search(r"\bDATE\s*:\s*(?:\n\s*)?([^\n]+)", text, re.IGNORECASE)
    source_po_date = _slash_date(date_match.group(1) if date_match else "")

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
    if "US STANDARD ENGLISH PACKAGING" in upper or "US STANDARD PACKAGING" in upper:
        packaging = "美版彩盒"
    elif "EU STANDARD" in upper or "EUROPEAN STANDARD" in upper:
        packaging = "EU盒包装"
    elif "GULLIVER PACKAGING" in upper and (
        "RUS/KZ" in upper or "RUSSIAN" in upper or "RUSSIA" in upper
    ):
        packaging = "俄罗斯彩盒包装"

    # 彩星的“国家标准”按 REMARKS 中的包装标准判断。ASTM/EN 玩具
    # 安全合规文字不是此排期字段的分类依据；例如同一份美国包装 PO
    # 同时出现 ASTM AND EN，国家标准仍只填“美国标准”。
    has_us_standard = "US STANDARD" in upper or "USA STANDARD" in upper
    has_eu_standard = "EU STANDARD" in upper or "EUROPEAN STANDARD" in upper
    standard = (
        "美国标准"
        if has_us_standard
        else "欧洲标准"
        if has_eu_standard
        else ""
    )

    return {
        "source_po_date": source_po_date,
        "contract_no": contract_no,
        "po_no": po_no,
        "customer_name": customer_name,
        "packaging": packaging,
        "standard": standard,
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
        normalized_amount = normalized_quantity * normalized_price
    return {
        "product_no": _normalize_product_code(code),
        "product_name_en": _clean_text(description),
        "quantity": normalized_quantity,
        "raw_unit_price_hkd": normalized_price,
        "raw_amount_hkd": normalized_amount,
    }


def _is_group_start(lines: list[str], index: int) -> bool:
    header = PRODUCT_HEADER_PATTERN.match(lines[index])
    if not header or not PRODUCT_CODE_PATTERN.match(header.group(1)):
        return False
    # A real parent row is followed immediately by MIX/DELIVERY, or by one
    # optional "Customer Item" line and then MIX/DELIVERY. Looking farther
    # ahead misclassifies the final ASSORTMENT child as a new parent because
    # the next real group's MIX line is three rows away.
    for candidate in lines[index + 1:index + 3]:
        if candidate.upper().startswith("MIX:") or DELIVERY_DATE_PATTERN.search(candidate):
            return True
    return False


def _infer_pack_from_product_code(product_no: str) -> Decimal | None:
    compact = re.sub(r"\s+", "", product_no or "").upper()
    match = PACK_SUFFIX_PATTERN.search(compact)
    return Decimal(match.group(1)) if match else None


def _extract_grouped_products(
    text: str,
    metadata: dict[str, str],
    file_name: str,
) -> list[CaixingParsedLine]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result: list[CaixingParsedLine] = []
    group_index = 0
    index = 0

    while index < len(lines):
        if not _is_group_start(lines, index):
            index += 1
            continue
        header = PRODUCT_HEADER_PATTERN.match(lines[index])
        parent_code_raw, parent_name = header.groups()
        end = index + 1
        while end < len(lines) and not _is_group_start(lines, end):
            if lines[end].upper().startswith("TOTAL"):
                break
            end += 1
        segment = lines[index:end]
        delivery_line = next(
            (line for line in segment if DELIVERY_DATE_PATTERN.search(line)),
            "",
        )
        requested_ship_date = _slash_date(
            DELIVERY_DATE_PATTERN.search(delivery_line).group(1)
            if delivery_line and DELIVERY_DATE_PATTERN.search(delivery_line)
            else ""
        )
        direct_values = DELIVERY_VALUES_PATTERN.search(delivery_line)
        products: list[dict[str, Any]] = []
        assortment: dict[str, Decimal] = {}
        parent_units_per_carton: Decimal | None = None

        if direct_values:
            parent_units_per_carton = _infer_pack_from_product_code(parent_code_raw)
            products.append(
                _product_from_values(
                    parent_code_raw,
                    parent_name,
                    direct_values.group(1),
                    direct_values.group(2),
                    direct_values.group(3),
                )
            )
        else:
            for line in segment[1:]:
                direct = DIRECT_PRODUCT_PATTERN.match(line)
                if direct:
                    products.append(_product_from_values(*direct.groups()))
                    continue
                assortment_line = ASSORTMENT_LINE_PATTERN.match(line)
                if assortment_line:
                    assortment[
                        _assortment_product_key(assortment_line.group(1))
                    ] = Decimal(assortment_line.group(2))
                carton_match = PCS_PER_CARTON_PATTERN.search(line)
                if carton_match:
                    parent_units_per_carton = Decimal(carton_match.group(1))

        if not products:
            index = max(end, index + 1)
            continue

        group_index += 1
        group_id = f"{metadata['po_no'] or file_name}:{group_index}"
        parent_product_no = _normalize_product_code(parent_code_raw)
        parent_quantity = sum(
            (product["quantity"] or Decimal("0") for product in products),
            Decimal("0"),
        )
        for product in products:
            product_key = _assortment_product_key(product["product_no"])
            units_per_carton = assortment.get(product_key)
            if units_per_carton is None and len(products) == 1:
                units_per_carton = _infer_pack_from_product_code(product["product_no"])
            result.append(
                CaixingParsedLine(
                    source_po_date=metadata["source_po_date"],
                    requested_ship_date=requested_ship_date,
                    contract_no=metadata["contract_no"],
                    po_no=metadata["po_no"],
                    customer_name=metadata["customer_name"],
                    product_no=product["product_no"],
                    product_name_en=product["product_name_en"],
                    quantity=product["quantity"],
                    raw_unit_price_hkd=product["raw_unit_price_hkd"],
                    raw_amount_hkd=product["raw_amount_hkd"],
                    units_per_carton=units_per_carton,
                    parent_product_no=parent_product_no,
                    parent_product_name_en=_clean_text(parent_name),
                    parent_quantity=parent_quantity,
                    parent_units_per_carton=parent_units_per_carton,
                    group_id=group_id,
                    packaging=metadata["packaging"],
                    standard=metadata["standard"],
                    lineage={
                        "received_date": "业务登记 · 客户确认下单邮件日期",
                        "po_no": f"{file_name} · Page / PURCHASE ORDER NO.",
                        "contract_no": f"{file_name} · OUR CONF NO.",
                        "customer_country": f"{file_name} · CUSTOMER",
                        "product_no": f"{file_name} · PRODUCT NO",
                        "product_name_en": f"{file_name} · DESCRIPTION",
                        "quantity": f"{file_name} · ORDER QTY.",
                        "units_per_carton": (
                            f"{file_name} · ASSORTMENT 对应产品数量"
                            if assortment
                            else f"{file_name} · 产品编号 E 后装箱数"
                        ),
                        "unit_price_hkd": f"{file_name} · UNIT PRICE HKD × 0.955",
                        "amount_hkd": "排期计算 · 数量 × 调整后单价",
                        "requested_ship_date": f"{file_name} · DELIVERY DATE",
                        "packaging": f"{file_name} · PO REMARKS 包装要求",
                        "standard": f"{file_name} · PO REMARKS 国家标准",
                    },
                )
            )
        index = max(end, index + 1)
    return result


def _extract_products_legacy_lines(text: str) -> list[dict[str, Any]]:
    """Fallback for PDFs whose extractor emits one table cell per line."""
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
            if next_product and not NOT_PRODUCT_PATTERN.match(candidate) and len(candidate) >= 4:
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
    return [
        product
        for product in normalized
        if product["quantity"] is not None
        and "PCS/CTN" not in product["product_name_en"].upper()
        and "TOTAL" not in product["product_name_en"].upper()
        and not (product["quantity"] <= 9 and not product["product_name_en"])
    ]


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
            "彩星 PDF 没有可读取的文本层；当前映射对应 Playmates 文本型 PDF"
        )
    return text


def parse_caixing_pdf(file_name: str, content: bytes) -> list[CaixingParsedLine]:
    if not file_name.lower().endswith(".pdf"):
        raise CustomerOrderWorkbookError("彩星 PO 只支持 .pdf")
    text = _extract_pdf_text(content)
    metadata = _extract_metadata(text)
    products = _extract_grouped_products(text, metadata, file_name)
    if not products:
        fallback_products = _extract_products_legacy_lines(text)
        for index, product in enumerate(fallback_products, start=1):
            product_no = product["product_no"]
            products.append(
                CaixingParsedLine(
                    source_po_date=metadata["source_po_date"],
                    contract_no=metadata["contract_no"],
                    po_no=metadata["po_no"],
                    customer_name=metadata["customer_name"],
                    product_no=product_no,
                    product_name_en=product["product_name_en"],
                    quantity=product["quantity"],
                    raw_unit_price_hkd=product["raw_unit_price_hkd"],
                    raw_amount_hkd=product["raw_amount_hkd"],
                    units_per_carton=_infer_pack_from_product_code(product_no),
                    parent_product_no=product_no,
                    parent_product_name_en=product["product_name_en"],
                    parent_quantity=product["quantity"],
                    group_id=f"{metadata['po_no'] or file_name}:fallback-{index}",
                    packaging=metadata["packaging"],
                    standard=metadata["standard"],
                    lineage={
                        "received_date": "业务登记 · 客户确认下单邮件日期",
                        "po_no": f"{file_name} · PURCHASE ORDER NO.",
                        "contract_no": f"{file_name} · OUR CONF NO.",
                        "customer_country": f"{file_name} · CUSTOMER",
                        "product_no": f"{file_name} · PRODUCT NO",
                        "product_name_en": f"{file_name} · DESCRIPTION",
                        "quantity": f"{file_name} · ORDER QTY.",
                        "units_per_carton": f"{file_name} · 产品编号 E 后装箱数",
                        "unit_price_hkd": f"{file_name} · UNIT PRICE HKD × 0.955",
                        "amount_hkd": "排期计算 · 数量 × 调整后单价",
                        "requested_ship_date": f"{file_name} · DELIVERY DATE",
                        "packaging": f"{file_name} · PO REMARKS 包装要求",
                        "standard": f"{file_name} · PO REMARKS 国家标准",
                    },
                )
            )
    if not products:
        raise CustomerOrderWorkbookError("未从彩星 Playmates PDF 识别到产品明细")
    return products


class CaixingSchedule(OoxmlSchedule):
    def insert_row_at(
        self,
        sheet_name: str,
        *,
        insert_row: int,
        values: dict[str, dict[str, Any]],
        reference_row_number: int | None = None,
    ) -> int:
        inserted_row = super().insert_row_at(
            sheet_name,
            insert_row=insert_row,
            values=values,
            reference_row_number=reference_row_number,
        )
        self.highlight_row(sheet_name, inserted_row)
        return inserted_row

    def _validate_template(self) -> None:
        missing = REQUIRED_SHEETS - self.sheet_paths.keys()
        if missing:
            raise CustomerOrderWorkbookError(
                "彩星排期结构不匹配，缺少工作表："
                + "、".join(sorted(missing))
            )
        review = self.read_rows(REVIEW_SHEET, limit=2).get(2, {})
        order = self.read_rows(ORDER_SHEET, limit=2).get(2, {})
        item = self.read_rows(ITEM_SHEET, limit=3).get(3, {})
        if (
            "客出单日期" not in review.get("B", "")
            or "S/C NO" not in review.get("D", "")
            or "PO.NO" not in review.get("E", "")
            or "产品" not in review.get("G", "").replace("產", "产").replace("編", "编")
            or "客出单日期" not in order.get("B", "")
            or "PO.NO" not in order.get("E", "")
            or "客出单日期" not in item.get("B", "")
            or "PO.NO" not in item.get("E", "")
        ):
            raise CustomerOrderWorkbookError(
                "彩星排期三张业务表的表头与当前映射版本不一致"
            )
        self.review_insert_row = self._section_insert_row(REVIEW_SHEET, before_total=True)
        self.order_insert_row = self._section_insert_row(ORDER_SHEET)
        self.item_insert_row = self._section_insert_row(ITEM_SHEET)
        self.order_matrix_columns = self._matrix_columns(ORDER_SHEET, 2)
        self.item_matrix_columns = self._matrix_columns(ITEM_SHEET, 1)

    def _section_insert_row(self, sheet_name: str, *, before_total: bool = False) -> int:
        rows = self.read_rows(sheet_name)
        marker_row = next(
            (
                row_number
                for row_number, values in rows.items()
                if CURRENT_ORDER_MARKER in values.get("A", "")
            ),
            None,
        )
        if marker_row is None:
            raise CustomerOrderWorkbookError(
                f"{sheet_name} 未找到“{CURRENT_ORDER_MARKER}”分区边界"
            )
        if before_total:
            prior = rows.get(marker_row - 1, {})
            if "合计" not in prior.get("H", ""):
                raise CustomerOrderWorkbookError(
                    f"{sheet_name} 的2026正单合计行位置异常"
                )
            return marker_row - 1
        return marker_row

    def _matrix_columns(self, sheet_name: str, header_row: int) -> dict[str, str]:
        values = self.read_rows(sheet_name, limit=header_row).get(header_row, {})
        result: dict[str, str] = {}
        for column, value in values.items():
            key = _matrix_product_key(value)
            if key and key.isdigit() and len(key) >= 4:
                result.setdefault(key, column)
        return result

    def build_existing_index(self) -> set[tuple[str, str, str]]:
        existing: set[tuple[str, str, str]] = set()
        for row_number, values in self.read_rows(ORDER_SHEET).items():
            if row_number >= self.order_insert_row:
                break
            po_no = _clean_text(values.get("E"))
            contract_no = _normalize_contract(values.get("D", ""))
            product_no = _normalize_product_code(values.get("G", ""))
            if po_no and product_no:
                existing.add((po_no, contract_no, product_no))
        return existing

    def matrix_columns_for(self, product_no: str) -> tuple[str, str]:
        key = _matrix_product_key(product_no)
        return (
            self.order_matrix_columns.get(key, ""),
            self.item_matrix_columns.get(key, ""),
        )

    def _reference_row(
        self,
        sheet_name: str,
        insert_row: int,
        *,
        parent: bool,
    ) -> int:
        rows = self.read_rows(sheet_name)
        for row_number in range(insert_row - 1, 0, -1):
            values = rows.get(row_number, {})
            if not _clean_text(values.get("G")):
                continue
            is_parent = not _clean_text(values.get("D")) and not _clean_text(values.get("E"))
            if is_parent == parent:
                return row_number
        raise CustomerOrderWorkbookError(
            f"{sheet_name} 找不到可复用的{'套装父行' if parent else '产品明细行'}样式"
        )

    @staticmethod
    def _payload(value: Any, *, inline: bool | None = None) -> dict[str, Any]:
        if inline is None:
            inline = isinstance(value, str)
        return {"value": value, "inline": inline}

    @staticmethod
    def _formula(formula: str, cached: Decimal | int | None = None) -> dict[str, Any]:
        return {"formula": formula, "cached": cached}

    def _write_review(self, groups: OrderedDict[str, list[dict[str, Any]]]) -> None:
        insert_row = self.review_insert_row
        parent_reference = self._reference_row(REVIEW_SHEET, insert_row, parent=True)
        detail_reference = self._reference_row(REVIEW_SHEET, insert_row, parent=False)
        parent_formulas: list[tuple[int, int, int, Decimal]] = []
        for records in groups.values():
            parent = records[0]
            parent_row = insert_row
            self.insert_row_at(
                REVIEW_SHEET,
                insert_row=insert_row,
                reference_row_number=parent_reference,
                values={
                    "G": self._payload(parent["parent_product_no"]),
                    "H": self._payload(parent["parent_product_name_en"]),
                    "J": self._payload(
                        parent["parent_units_per_carton"],
                        inline=False,
                    ),
                },
            )
            insert_row += 1
            child_start = insert_row
            for record in records:
                quantity = record["quantity"]
                pack = record["units_per_carton"]
                raw_price = record["raw_unit_price_hkd"]
                net_price = record["unit_price_hkd"]
                amount = record["amount_hkd"]
                values: dict[str, dict[str, Any]] = {
                    "B": self._payload(record["received_date"]),
                    "D": self._payload(record["contract_no"]),
                    "E": self._payload(record["po_no"]),
                    "F": self._payload(record["customer_name"]),
                    "G": self._payload(record["product_no"]),
                    "H": self._payload(record["product_name_en"]),
                    "I": self._payload(quantity, inline=False),
                    "M": self._formula(f"I{insert_row}-L{insert_row}", quantity),
                    "U": self._payload(record["requested_ship_date"]),
                    "V": self._payload(record["packaging"]),
                    "W": self._payload(record["standard"]),
                }
                if pack is not None:
                    values["J"] = self._payload(pack, inline=False)
                    cached_cartons = (
                        quantity / pack
                        if quantity is not None and pack > 0
                        else None
                    )
                    values["K"] = self._formula(
                        f"I{insert_row}/J{insert_row}",
                        cached_cartons,
                    )
                if raw_price is not None:
                    values["AA"] = self._formula(
                        f"{_decimal_text(raw_price)}*0.955",
                        net_price,
                    )
                    values["AB"] = self._formula(
                        f"I{insert_row}*AA{insert_row}",
                        amount,
                    )
                self.insert_row_at(
                    REVIEW_SHEET,
                    insert_row=insert_row,
                    reference_row_number=detail_reference,
                    values=values,
                )
                insert_row += 1
            child_end = insert_row - 1
            total = sum(
                (record["quantity"] or Decimal("0") for record in records),
                Decimal("0"),
            )
            parent_formulas.append((parent_row, child_start, child_end, total))

        # Set group totals only after every row has been inserted. The generic
        # row inserter intentionally expands a SUM ending directly above the
        # insertion point (needed for worksheet totals); setting a parent SUM
        # earlier would therefore absorb the next parent group and double-count.
        for parent_row, child_start, child_end, total in parent_formulas:
            formula = (
                f"SUM(I{child_start})"
                if child_start == child_end
                else f"SUM(I{child_start}:I{child_end})"
            )
            self.set_cell(
                REVIEW_SHEET,
                parent_row,
                "I",
                formula=formula,
                cached=total,
            )

    def _write_order(self, groups: OrderedDict[str, list[dict[str, Any]]]) -> None:
        insert_row = self.order_insert_row
        parent_reference = self._reference_row(ORDER_SHEET, insert_row, parent=True)
        detail_reference = self._reference_row(ORDER_SHEET, insert_row, parent=False)
        for records in groups.values():
            parent = records[0]
            total = sum(
                (record["quantity"] or Decimal("0") for record in records),
                Decimal("0"),
            )
            self.insert_row_at(
                ORDER_SHEET,
                insert_row=insert_row,
                reference_row_number=parent_reference,
                values={
                    "B": self._payload(parent["received_date"]),
                    "G": self._payload(parent["parent_product_no"]),
                    "H": self._payload(parent["parent_product_name_en"]),
                    "I": self._payload(total, inline=False),
                    "J": self._payload(
                        parent["parent_units_per_carton"],
                        inline=False,
                    ),
                    "M": self._payload(parent["requested_ship_date"]),
                },
            )
            insert_row += 1
            for record in records:
                raw_price = record["raw_unit_price_hkd"]
                values: dict[str, dict[str, Any]] = {
                    "B": self._payload(record["received_date"]),
                    "D": self._payload(record["contract_no"]),
                    "E": self._payload(record["po_no"]),
                    "F": self._payload(record["customer_name"]),
                    "G": self._payload(record["product_no"]),
                    "H": self._payload(record["product_name_en"]),
                    "I": self._payload(record["quantity"], inline=False),
                    "M": self._payload(record["requested_ship_date"]),
                }
                if record["units_per_carton"] is not None:
                    values["J"] = self._payload(
                        record["units_per_carton"],
                        inline=False,
                    )
                if raw_price is not None:
                    values["K"] = self._formula(
                        f"{_decimal_text(raw_price)}*0.955",
                        record["unit_price_hkd"],
                    )
                    values["L"] = self._formula(
                        f"I{insert_row}*K{insert_row}",
                        record["amount_hkd"],
                    )
                matrix_column = record["order_matrix_column"]
                if matrix_column:
                    values[matrix_column] = self._payload(
                        record["quantity"],
                        inline=False,
                    )
                self.insert_row_at(
                    ORDER_SHEET,
                    insert_row=insert_row,
                    reference_row_number=detail_reference,
                    values=values,
                )
                insert_row += 1

    def _write_item(self, groups: OrderedDict[str, list[dict[str, Any]]]) -> None:
        insert_row = self.item_insert_row
        parent_reference = self._reference_row(ITEM_SHEET, insert_row, parent=True)
        detail_reference = self._reference_row(ITEM_SHEET, insert_row, parent=False)
        for records in groups.values():
            parent = records[0]
            total = sum(
                (record["quantity"] or Decimal("0") for record in records),
                Decimal("0"),
            )
            self.insert_row_at(
                ITEM_SHEET,
                insert_row=insert_row,
                reference_row_number=parent_reference,
                values={
                    "B": self._payload(parent["received_date"]),
                    "G": self._payload(parent["parent_product_no"]),
                    "H": self._payload(parent["parent_product_name_en"]),
                    "I": self._payload(total, inline=False),
                    "O": self._payload(parent["requested_ship_date"]),
                },
            )
            insert_row += 1
            for record in records:
                values: dict[str, dict[str, Any]] = {
                    "B": self._payload(record["received_date"]),
                    "D": self._payload(record["contract_no"]),
                    "E": self._payload(record["po_no"]),
                    "F": self._payload(record["customer_name"]),
                    "G": self._payload(record["product_no"]),
                    "H": self._payload(record["product_name_en"]),
                    "I": self._payload(record["quantity"], inline=False),
                    "J": self._payload(record["packaging"]),
                    "O": self._payload(record["requested_ship_date"]),
                }
                matrix_column = record["item_matrix_column"]
                if matrix_column:
                    values[matrix_column] = self._payload(
                        record["quantity"],
                        inline=False,
                    )
                self.insert_row_at(
                    ITEM_SHEET,
                    insert_row=insert_row,
                    reference_row_number=detail_reference,
                    values=values,
                )
                insert_row += 1

    def write_records(self, records: list[dict[str, Any]]) -> None:
        groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for record in records:
            groups.setdefault(record["group_id"], []).append(record)
        self._write_review(groups)
        self._write_order(groups)
        self._write_item(groups)
        self.ensure_business_header_freeze()

    def ensure_business_header_freeze(self) -> None:
        for sheet_name, frozen_rows in (
            (REVIEW_SHEET, 2),
            (ORDER_SHEET, 2),
            (ITEM_SHEET, 3),
        ):
            path = self.sheet_paths[sheet_name]
            root = etree.fromstring(self.parts[path])
            sheet_views = root.find("m:sheetViews", NS)
            if sheet_views is None:
                sheet_views = etree.Element(f"{{{MAIN_NS}}}sheetViews")
                sheet_pr = root.find("m:sheetPr", NS)
                root.insert(1 if sheet_pr is not None else 0, sheet_views)
            sheet_view = sheet_views.find("m:sheetView", NS)
            if sheet_view is None:
                sheet_view = etree.SubElement(
                    sheet_views,
                    f"{{{MAIN_NS}}}sheetView",
                    workbookViewId="0",
                )
            pane = sheet_view.find("m:pane", NS)
            if pane is None:
                pane = etree.Element(f"{{{MAIN_NS}}}pane")
                sheet_view.insert(0, pane)
            pane.set("ySplit", str(frozen_rows))
            pane.set("topLeftCell", pane.get("topLeftCell") or f"A{frozen_rows + 1}")
            pane.set("activePane", "bottomRight" if pane.get("xSplit") else "bottomLeft")
            pane.set("state", "frozen")
            self.parts[path] = etree.tostring(
                root,
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )


def _prepare_caixing_schedule(
    schedule_file_name: str,
    schedule_content: bytes,
) -> PreparedCaixingSchedule:
    plain_schedule, encrypted = _decrypt_schedule(schedule_content)
    legacy_xls = is_legacy_xls_workbook(plain_schedule)
    if legacy_xls:
        if not schedule_file_name.lower().endswith(".xls"):
            raise CustomerOrderWorkbookError(
                "彩星排期内容是旧版 .xls，但文件扩展名不匹配"
            )
        try:
            ooxml_content = convert_legacy_xls_to_xlsx(plain_schedule)
        except LegacyExcelConversionError as exc:
            raise CustomerOrderWorkbookError(str(exc)) from exc
        return PreparedCaixingSchedule(
            ooxml_content=ooxml_content,
            encrypted=encrypted,
            legacy_xls=True,
        )
    if schedule_file_name.lower().endswith(".xls"):
        raise CustomerOrderWorkbookError(
            "彩星排期扩展名是 .xls，但文件内容不是有效的旧版 Excel 工作簿"
        )
    return PreparedCaixingSchedule(
        ooxml_content=plain_schedule,
        encrypted=encrypted,
        legacy_xls=False,
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


def _export_record(
    parsed: CaixingParsedLine,
    received_date: str,
    order_matrix_column: str,
    item_matrix_column: str,
) -> dict[str, Any]:
    return {
        "group_id": parsed.group_id,
        "received_date": received_date.replace("-", "/"),
        "contract_no": parsed.contract_no,
        "po_no": parsed.po_no,
        "customer_name": parsed.customer_name,
        "parent_product_no": parsed.parent_product_no,
        "parent_product_name_en": parsed.parent_product_name_en,
        "parent_units_per_carton": parsed.parent_units_per_carton,
        "product_no": parsed.product_no,
        "product_name_en": parsed.product_name_en,
        "quantity": parsed.quantity,
        "units_per_carton": parsed.units_per_carton,
        "requested_ship_date": parsed.requested_ship_date,
        "packaging": parsed.packaging,
        "standard": parsed.standard,
        "raw_unit_price_hkd": parsed.raw_unit_price_hkd,
        "unit_price_hkd": parsed.unit_price_hkd,
        "amount_hkd": parsed.amount_hkd,
        "order_matrix_column": order_matrix_column,
        "item_matrix_column": item_matrix_column,
    }


def _parent_preview_row(
    parsed: CaixingParsedLine,
    *,
    file_name: str,
    row_index: int,
    received_date: str,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if not parsed.parent_product_no:
        issues.append(
            _make_issue(
                "blocked",
                "missing_parent_product_no",
                "product_no",
                "大货号未能从彩星 PDF 提取",
            )
        )
    if parsed.parent_quantity is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_parent_quantity",
                "quantity",
                "大货号总数量无法由小货号数量汇总",
            )
        )
    if parsed.parent_units_per_carton is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_parent_units_per_carton",
                "units_per_carton",
                "大货号总装箱数未能从 E 后数字或 PCS/CTN 提取",
                can_skip=True,
                skip_label="大货号装箱数留空，稍后由跟客补充",
            )
        )
    if not parsed.requested_ship_date:
        issues.append(
            _make_issue(
                "blocked",
                "missing_required_field",
                "requested_ship_date",
                "大货号 DELIVERY DATE 未能从彩星 PDF 提取",
            )
        )

    status = (
        "blocked"
        if any(issue["severity"] == "blocked" for issue in issues)
        else "warning"
        if issues
        else "valid"
    )
    row_id = f"caixing-parent-{parsed.group_id}-{row_index}"
    for issue in issues:
        if issue["can_skip"]:
            issue["skip_key"] = f"{row_id}|{issue['code']}|{issue['field']}"

    carton_count = (
        parsed.parent_quantity / parsed.parent_units_per_carton
        if parsed.parent_quantity is not None
        and parsed.parent_units_per_carton is not None
        and parsed.parent_units_per_carton > 0
        else None
    )
    lineage = {
        "received_date": "业务登记 · 客户确认下单邮件日期",
        "po_no": f"{file_name} · PURCHASE ORDER NO.",
        "contract_no": f"{file_name} · OUR CONF NO.",
        "customer_country": f"{file_name} · CUSTOMER",
        "product_no": f"{file_name} · 大货号 / MIX 上方 PRODUCT NO",
        "product_name_zh": "彩星排期无中文名称来源 · 留空",
        "product_name_en": f"{file_name} · 大货号 DESCRIPTION",
        "quantity": f"系统汇总 · 大货号下 {parsed.parent_product_no} 的全部小货号数量",
        "units_per_carton": f"{file_name} · 大货号 E 后数字 / PCS/CTN",
        "carton_count": "排期计算 · 大货号总数量 ÷ 大货号装箱数",
        "standard": f"{file_name} · PO REMARKS 的 US/EU STANDARD",
        "unit_price_hkd": "大货号汇总行不填写单价",
        "amount_hkd": "大货号汇总行不填写金额",
        "packaging": f"{file_name} · PO REMARKS 包装要求",
        "line_q": "人工维护字段 · 自动导入留空",
        "customer_q": "人工维护字段 · 自动导入留空",
        "requested_ship_date": f"{file_name} · 大货号下 DELIVERY DATE",
    }
    return {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "有效", "warning": "警告", "blocked": "阻断"}[status],
        "row_role": "parent",
        "parent_product_no": "",
        "received_date": received_date,
        "po_no": parsed.po_no,
        "contract_no": parsed.contract_no,
        "customer_country": parsed.customer_name,
        "customer_name": parsed.customer_name,
        "country": "",
        "product_no": parsed.parent_product_no,
        "product_name_zh": "",
        "product_name_en": parsed.parent_product_name_en,
        "quantity": _decimal_text(parsed.parent_quantity),
        "units_per_carton": _decimal_text(parsed.parent_units_per_carton),
        "carton_count": _decimal_text(carton_count),
        "standard": parsed.standard,
        "unit_price_hkd": "",
        "amount_hkd": "",
        "packaging": parsed.packaging,
        "line_q": "",
        "customer_q": "",
        "requested_ship_date": _iso_date(parsed.requested_ship_date),
        "input_template": INPUT_TEMPLATE,
        "target_template": TARGET_TEMPLATE,
        "item_sheet_name": f"{REVIEW_SHEET} / {ORDER_SHEET} / {ITEM_SHEET}",
        "source_po_file_name": file_name,
        "lineage": lineage,
        "issues": issues,
        "_export_record": None,
    }


def _preview_row(
    parsed: CaixingParsedLine,
    *,
    file_name: str,
    row_index: int,
    received_date: str,
    schedule: CaixingSchedule,
    existing: set[tuple[str, str, str]],
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
        "requested_ship_date": ("客要求走货期", parsed.requested_ship_date),
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
    if parsed.units_per_carton is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_units_per_carton",
                "units_per_carton",
                "装箱数未能从 ASSORTMENT 或产品编号 E 后数字提取",
                can_skip=True,
                skip_label="装箱数及箱数留空，稍后由跟客补充",
            )
        )
    elif (
        parsed.quantity is not None
        and parsed.units_per_carton > 0
        and parsed.quantity / parsed.units_per_carton
        != (parsed.quantity / parsed.units_per_carton).to_integral_value()
    ):
        issues.append(
            _make_issue(
                "blocked",
                "partial_carton",
                "carton_count",
                "数量不能被装箱数整除，箱数会产生小数",
                can_skip=True,
                skip_label="保留小数箱数，稍后由跟客确认",
            )
        )
    if parsed.raw_unit_price_hkd is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_unit_price",
                "unit_price_hkd",
                "PO 未提供单价，无法计算 0.955 调整后单价及金额",
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
                "未从 PO REMARKS 识别到美版、EU 或俄罗斯包装要求",
            )
        )
    if not parsed.standard:
        issues.append(
            _make_issue(
                "warning",
                "missing_standard",
                "standard",
                "未从 PO REMARKS 识别到美国或欧洲国家标准",
            )
        )

    order_matrix_column, item_matrix_column = schedule.matrix_columns_for(
        parsed.product_no
    )
    if not order_matrix_column or not item_matrix_column:
        missing_sheets = "、".join(
            name
            for name, column in (
                (ORDER_SHEET, order_matrix_column),
                (ITEM_SHEET, item_matrix_column),
            )
            if not column
        )
        issues.append(
            _make_issue(
                "warning",
                "missing_product_matrix_column",
                "product_no",
                (
                    f"产品 {parsed.product_no} 在{missing_sheets}右侧产品栏没有对应列；"
                    "本次仍可导出，横向产品栏保持空白"
                ),
            )
        )

    business_key = (
        parsed.po_no,
        _normalize_contract(parsed.contract_no),
        _normalize_product_code(parsed.product_no),
    )
    if business_key in existing:
        issues.append(
            _make_issue(
                "warning",
                "existing_order_line",
                "po_no",
                f"当前排期已存在相同 PO/S-C/产品 {parsed.product_no}；测试阶段允许确认后继续导出",
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

    carton_count = (
        parsed.quantity / parsed.units_per_carton
        if parsed.quantity is not None
        and parsed.units_per_carton is not None
        and parsed.units_per_carton > 0
        else None
    )
    lineage = dict(parsed.lineage or {})
    lineage.update(
        {
            "product_name_zh": "彩星排期无中文名称来源 · 留空",
            "carton_count": "排期计算 · 数量 ÷ 装箱数",
            "line_q": "人工维护字段 · 自动导入留空",
            "customer_q": "人工维护字段 · 自动导入留空",
        }
    )
    return {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "有效", "warning": "警告", "blocked": "阻断"}[status],
        "row_role": "detail",
        "parent_product_no": parsed.parent_product_no,
        "received_date": received_date,
        "po_no": parsed.po_no,
        "contract_no": parsed.contract_no,
        "customer_country": parsed.customer_name,
        "customer_name": parsed.customer_name,
        "country": "",
        "product_no": parsed.product_no,
        "product_name_zh": "",
        "product_name_en": parsed.product_name_en,
        "quantity": _decimal_text(parsed.quantity),
        "units_per_carton": _decimal_text(parsed.units_per_carton),
        "carton_count": _decimal_text(carton_count),
        "standard": parsed.standard,
        "unit_price_hkd": _decimal_text(parsed.unit_price_hkd),
        "amount_hkd": _decimal_text(parsed.amount_hkd),
        "packaging": parsed.packaging,
        "line_q": "",
        "customer_q": "",
        "requested_ship_date": _iso_date(parsed.requested_ship_date),
        "input_template": INPUT_TEMPLATE,
        "target_template": TARGET_TEMPLATE,
        "item_sheet_name": f"{REVIEW_SHEET} / {ORDER_SHEET} / {ITEM_SHEET}",
        "source_po_file_name": file_name,
        "lineage": lineage,
        "issues": issues,
        "_export_record": _export_record(
            parsed,
            received_date,
            order_matrix_column,
            item_matrix_column,
        ),
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

    prepared_schedule = _prepare_caixing_schedule(
        schedule_file_name,
        schedule_content,
    )
    schedule = CaixingSchedule(prepared_schedule.ooxml_content)
    existing = schedule.build_existing_index()
    rows: list[dict[str, Any]] = []
    row_index = 0
    for file_name, content in po_files:
        try:
            parsed_lines = parse_caixing_pdf(file_name, content)
        except CustomerOrderWorkbookError as exc:
            raise CustomerOrderWorkbookError(f"{file_name}：{exc}") from exc
        seen_groups: set[str] = set()
        for parsed in parsed_lines:
            if parsed.group_id not in seen_groups:
                seen_groups.add(parsed.group_id)
                row_index += 1
                rows.append(
                    _parent_preview_row(
                        parsed,
                        file_name=file_name,
                        row_index=row_index,
                        received_date=normalized_received_date,
                    )
                )
            row_index += 1
            rows.append(
                _preview_row(
                    parsed,
                    file_name=file_name,
                    row_index=row_index,
                    received_date=normalized_received_date,
                    schedule=schedule,
                    existing=existing,
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
        "彩星映射按业务步骤同步写入正单评审表、接单表和 ITEM表；不再使用当前活动表固定24列追加逻辑。",
        "来单日期取页面登记的客户确认下单邮件日期；日期码、行Q、客Q、生产车间及上系统状态保留人工维护。",
        "PO 单价按彩星排期口径乘 0.955，金额按数量乘调整后单价；套装按 ASSORTMENT 拆分并填写两张表右侧产品数量栏。",
        (
            "已识别原版 Excel 97-2003 .xls 排期；输出保持原文件名、.xls 格式和工作表结构。"
            if prepared_schedule.legacy_xls
            else "已识别 .xlsx 排期；输出保持原文件名和工作表结构。"
        ),
        (
            "上传排期已加密；输出保留 2026 打开密码。"
            if prepared_schedule.encrypted
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
        "_schedule_encrypted": prepared_schedule.encrypted,
        "_schedule_format": "xls" if prepared_schedule.legacy_xls else "xlsx",
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
    prepared_schedule = _prepare_caixing_schedule(
        schedule_file_name,
        schedule_content,
    )
    workbook = CaixingSchedule(prepared_schedule.ooxml_content)
    workbook.write_records(
        [
            row["_export_record"]
            for row in preview["rows"]
            if row.get("_export_record") is not None
        ]
    )
    workbook.set_recalculation()
    output = workbook.to_bytes()
    if prepared_schedule.legacy_xls:
        try:
            output = convert_xlsx_to_legacy_xls(
                output,
                output_password=(
                    SCHEDULE_PASSWORD
                    if prepared_schedule.encrypted
                    else None
                ),
            )
        except LegacyExcelConversionError as exc:
            raise CustomerOrderWorkbookError(str(exc)) from exc
    elif prepared_schedule.encrypted:
        output = _encrypt_schedule(output)
    return output, schedule_file_name, preview
