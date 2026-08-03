from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from typing import Any

from app.services.carton_mark import configure_tesseract
from app.services.customer_order_buzzbee import (
    MAX_BATCH_PO_BYTES,
    MAX_BATCH_PO_FILES,
    MAX_PO_BYTES,
    MAX_SCHEDULE_BYTES,
    CustomerOrderWorkbookError,
    OoxmlSchedule,
    _clean_identifier,
    _clean_text,
    _decimal,
    _decimal_text,
    _decrypt_schedule,
    _encrypt_schedule,
    _excel_serial,
    _format_iso_date,
)


PREVIEW_SCHEMA_VERSION = "customer-order-dickie-preview-v1"
INPUT_TEMPLATE = "DICKIE_SIMBA_RELEASE_ORDER_PDF_V1"
TARGET_TEMPLATE = "DICKIE_PRODUCTION_SCHEDULE_V1"
ITEM_SHEET = "Iteam表"
DINO_ITEM_SHEET = "恐龙蛋口水车Iteam表"
MO_SHEET = "MO订单"
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass
class DickieProductLookup:
    product_name_zh: str = ""
    contact: str = ""
    packaging: str = ""
    order_type: str = "normal"
    existing_rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class DickieParsedOrder:
    reference_no: str = ""
    master_contract: str = ""
    po_no: str = ""
    source_date: str = ""
    ship_date: str = ""
    product_no: str = ""
    product_name_en: str = ""
    quantity: Decimal | None = None
    unit_price_hkd: Decimal | None = None
    packing: str = ""
    customer_name: str = ""
    country: str = ""
    contact: str = ""
    packaging: str = ""
    allocations: list[tuple[str, Decimal]] = field(default_factory=list)
    lineage: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DickieAttachmentAllocation:
    item_no: str
    master_contract: str
    po_no: str
    quantity: Decimal
    unit_price_hkd: Decimal | None


def _normalize_ocr_text(value: str) -> str:
    value = value.replace("\r", "\n")
    value = value.replace("—", "-").replace("–", "-")
    return re.sub(r"[ \t]+", " ", value)


def _normalize_reference(text: str) -> str:
    match = re.search(
        r"\bSC\s*(\d{6,9})\s*[/\-]\s*(\d{2,4})\b",
        text,
        re.IGNORECASE,
    )
    return f"SC{match.group(1)}-{match.group(2)}" if match else ""


def _date_from_match(day: str, month: str, year: str, *, expected_year: int) -> str:
    parsed_year = int(year)
    if parsed_year > expected_year + 2 and str(parsed_year).endswith(str(expected_year)[-1]):
        parsed_year = expected_year
    try:
        return date(parsed_year, MONTHS[month.upper()], int(day)).isoformat()
    except (KeyError, ValueError):
        return ""


def _extract_source_date(text: str, *, expected_year: int) -> str:
    match = re.search(
        r"Date\s+of\s+creation\s*:\s*(\d{1,2})[.\-/ ]"
        r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
        r"[.\-/ ](\d{4})",
        text,
        re.IGNORECASE,
    )
    return (
        _date_from_match(match.group(1), match.group(2), match.group(3), expected_year=expected_year)
        if match
        else ""
    )


def _extract_delivery_dates(text: str, *, expected_year: int) -> list[str]:
    repaired = (
        text.replace("BEG", "DEC")
        .replace("DEG", "DEC")
        .replace("BE¢", "DEC")
        .replace("APF", "APR")
        .replace("JUM", "JUN")
    )
    results: list[str] = []
    for match in re.finditer(
        r"(?<!\d)(\d{1,2})[.\-/ +]*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
        r"[.\-/ +]*(\d{4})(?!\d)",
        repaired,
        re.IGNORECASE,
    ):
        value = _date_from_match(
            match.group(1),
            match.group(2),
            match.group(3),
            expected_year=expected_year,
        )
        if value and value not in results:
            results.append(value)
    return results


def _extract_product_no(text: str) -> str:
    match = re.search(
        r"Mat\.?\s*No\.?\s*:\s*[|¦Il\[\](){}]*\s*([A-Z0-9]{6,16})",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _extract_product_name(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not re.search(r"Mat\.?\s*No\.?", line, re.IGNORECASE):
            continue
        for candidate in lines[index + 1:index + 6]:
            if (
                re.fullmatch(r"[\d\s|]+", candidate)
                or "EAN" in candidate.upper()
                or candidate.lower().startswith(("packing:", "quantity "))
            ):
                continue
            if re.search(r"[A-Za-z]{3}", candidate):
                return candidate[:120]
    return ""


def _extract_packing(text: str) -> str:
    match = re.search(
        r"Packing\s*:\s*([0O]?\s*PC|\d+\s*PC)\s*/\s*(\d+)\s*PC",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    inner = re.sub(r"\D", "", match.group(1).replace("O", "0").replace("o", "0")) or "0"
    return f"{int(inner)}/{int(match.group(2))}"


def _extract_packaging(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if not re.search(r"\bPacking\s*:", line, re.IGNORECASE):
            continue
        for candidate in lines[index + 1:index + 5]:
            if not candidate:
                continue
            if re.search(r"Quantity|Master\s+Contract|PO\s+Contract", candidate, re.IGNORECASE):
                break
            if re.search(r"[A-Za-z]{3}", candidate):
                return candidate[:120]
    return ""


def _extract_contact(text: str) -> str:
    match = re.search(
        r"Pers\.?\s*respons\.?\s*:?\s*([A-Za-z][A-Za-z .'-]{2,35}?)"
        r"\s*(?:-\s*Tel|Tel:|\+\d|$)",
        text,
        re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _extract_customer(text: str) -> tuple[str, str]:
    match = re.search(
        r"This\s+order\s+is\s+for\s+([A-Za-z][A-Za-z &.'()\-]{2,60}?)\s*[.\n]",
        text,
        re.IGNORECASE,
    )
    if match:
        customer = re.sub(r"\s+", " ", match.group(1)).strip()
        country = "德国" if "GERMANY" in customer.upper() else ""
        return customer, country
    upper = text.upper()
    if "CALENDAR HOLDINGS" in upper or "HOUSTON" in upper:
        return "Calendar", "美国"
    port_match = re.search(
        r"Port\s+of\s+discharge\s*:\s*[^A-Z0-9\n]{0,8}([A-Z][A-Z \-]{2,30})",
        text,
        re.IGNORECASE,
    )
    if port_match:
        port = re.sub(r"\s+", " ", port_match.group(1)).strip()
        port_country = {
            "HAMBURG": "德国",
            "HOUSTON": "美国",
            "MONTREAL": "加拿大",
        }
        return port.title(), port_country.get(port.upper(), "")
    return "", ""


ATTACHMENT_DETAIL_ROW_PATTERN = re.compile(
    r"^\s*(?P<item>\d[A-Z0-9]{5,20})[.,]?"
    r"(?:\s*\([^()\n]{1,24}\))*\s+"
    r"(?P<quantity>[\d,]+)\s*PCS?\s+"
    r"(?P<remainder>.+)$",
    re.IGNORECASE,
)
ATTACHMENT_CONTRACT_PATTERN = re.compile(
    r"(?<!\d)(?P<number>[35]\d{8})\s*/\s*(?P<suffix>\d{1,2})(?!\d)",
    re.IGNORECASE,
)
ATTACHMENT_REFERENCE_PATTERN = re.compile(
    r"(?<!\d)(?P<number>7(?:\s*\d){8})\s*/\s*(?P<suffix>\d{1,4})(?!\d)",
    re.IGNORECASE,
)


def _extract_single_attachment_price(text: str) -> Decimal | None:
    before_hkd, separator, _ = text.upper().partition("HKD")
    if not separator:
        return None
    candidates = re.findall(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)(?!\d)", before_hkd)
    if len(candidates) != 1:
        # Handwritten revisions are commonly placed beside a struck-through
        # printed price. Never guess which of multiple OCR numbers is active.
        return None
    return Decimal(candidates[0].replace(",", "."))


def _parse_attachment_detail_row(line: str) -> DickieAttachmentAllocation | None:
    row_match = ATTACHMENT_DETAIL_ROW_PATTERN.match(line)
    if not row_match:
        return None
    item_no = row_match.group("item").upper()
    if item_no.startswith("990"):
        # Simba Dickie uses 990... rows for handling charges. Their shipment
        # quantity repeats the full order and must not be counted as product.
        return None

    remainder = row_match.group("remainder")
    reference_match = ATTACHMENT_REFERENCE_PATTERN.search(remainder)
    if not reference_match:
        return None
    contracts = [
        f"{match.group('number')}/{match.group('suffix')}"
        for match in ATTACHMENT_CONTRACT_PATTERN.finditer(
            remainder[:reference_match.start()]
        )
    ]
    if not contracts:
        return None
    return DickieAttachmentAllocation(
        item_no=item_no,
        master_contract=contracts[0],
        po_no=contracts[1] if len(contracts) > 1 else "",
        quantity=Decimal(row_match.group("quantity").replace(",", "")),
        unit_price_hkd=_extract_single_attachment_price(
            remainder[reference_match.end():]
        ),
    )


def _extract_attachment_allocations(
    text: str,
) -> list[DickieAttachmentAllocation]:
    return [
        allocation
        for line in text.splitlines()
        if (allocation := _parse_attachment_detail_row(line)) is not None
    ]


def _extract_release_quantity(text: str) -> Decimal | None:
    flattened = re.sub(r"\s+", " ", text)
    header = re.search(
        r"\bQuantity\b.{0,180}?\bDelivery\s+Date\b",
        flattened,
        re.IGNORECASE,
    )
    if header:
        quantity_match = re.search(
            r"(?<!\d)([\d,]+)\s*PCS?\b",
            flattened[header.end():header.end() + 100],
            re.IGNORECASE,
        )
        if quantity_match:
            return Decimal(quantity_match.group(1).replace(",", ""))

    candidates = [
        Decimal(match.group(1).replace(",", ""))
        for line in text.splitlines()
        if "PACKING" not in line.upper()
        for match in re.finditer(r"(?<!\d)([\d,]+)\s*PCS?\b", line, re.IGNORECASE)
    ]
    return max(candidates) if candidates else None


def _extract_main_order_numbers(
    text: str,
) -> tuple[str, str, Decimal | None, Decimal | None]:
    flattened = re.sub(r"\s+", " ", text)
    match = re.search(
        r"(?P<quantity>[\d,]+)\s*PC\s+[^0-9]{0,8}"
        r"(?P<master>5\d{8})\s*/\s*(?P<master_suffix>\d{1,2})\s+"
        r"(?P<po>3\d{8})\s*/\s*(?P<po_suffix>\d{1,2})\s+"
        r"(?P<price>\d+(?:\.\d+)?)\s*HKD",
        flattened,
        re.IGNORECASE,
    )
    if not match:
        return (
            "",
            "",
            _extract_release_quantity(text),
            None,
        )
    return (
        f"{match.group('master')}/{match.group('master_suffix')}",
        f"{match.group('po')}/{match.group('po_suffix')}",
        Decimal(match.group("quantity").replace(",", "")),
        Decimal(match.group("price")),
    )


def _extract_pdf_ocr_pages(content: bytes) -> list[str]:
    try:
        import pypdfium2 as pdfium  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:
        raise CustomerOrderWorkbookError(
            "Dickie PDF 本地识别引擎未配置，请安装 pypdfium2、Pillow 和 pytesseract"
        ) from exc
    tesseract_cmd, language = configure_tesseract(pytesseract)
    if not tesseract_cmd:
        raise CustomerOrderWorkbookError("未找到 Tesseract，无法识别 Dickie 扫描版 PDF")
    try:
        document = pdfium.PdfDocument(content)
    except Exception as exc:
        raise CustomerOrderWorkbookError("Dickie PO 不是有效的 PDF 文件") from exc
    if len(document) == 0 or len(document) > 20:
        raise CustomerOrderWorkbookError("Dickie PO 页数必须在 1 至 20 页之间")
    pages: list[str] = []
    for page in document:
        image = page.render(scale=2.2).to_pil().convert("RGB")
        try:
            text = pytesseract.image_to_string(
                image,
                lang=language,
                config="--oem 3 --psm 6",
                timeout=60,
            )
        except Exception as exc:
            raise CustomerOrderWorkbookError(f"Dickie PDF OCR 失败：{exc}") from exc
        pages.append(_normalize_ocr_text(text))
    return pages


def _parse_dickie_ocr_pages(
    pages: list[str],
    *,
    fallback_received_date: str,
) -> DickieParsedOrder:
    if not pages:
        raise CustomerOrderWorkbookError("Dickie PO 没有可识别页面")
    try:
        expected_year = date.fromisoformat(fallback_received_date).year
    except ValueError as exc:
        raise CustomerOrderWorkbookError("来单日期必须是 YYYY-MM-DD") from exc
    first_page = pages[0]
    all_text = "\n".join(pages)
    reference_no = _normalize_reference(all_text)
    source_date = _extract_source_date(first_page, expected_year=expected_year) or fallback_received_date
    product_no = _extract_product_no(first_page)
    product_name_en = _extract_product_name(first_page)
    packing = _extract_packing(first_page)
    contact = _extract_contact(first_page)
    customer_name, country = _extract_customer(all_text)
    packaging = _extract_packaging(first_page)
    master_contract, po_no, quantity, unit_price = _extract_main_order_numbers(first_page)

    attachment_text = "\n".join(
        page
        for page in pages
        if re.search(r"Release\s+order\s+Attachment", page, re.IGNORECASE)
    )
    attachment_allocations = _extract_attachment_allocations(attachment_text)
    allocations: list[tuple[str, Decimal]] = []
    if attachment_allocations:
        attachment_quantity = sum(
            (item.quantity for item in attachment_allocations),
            Decimal("0"),
        )
        attachment_is_complete = quantity is None or attachment_quantity == quantity
        master_contract = "\n".join(
            item.master_contract for item in attachment_allocations
        )
        po_no = "\n".join(
            item.po_no for item in attachment_allocations if item.po_no
        )
        if attachment_is_complete:
            quantity = attachment_quantity
        attachment_prices = [
            item.unit_price_hkd for item in attachment_allocations
        ]
        if (
            attachment_is_complete
            and quantity
            and all(price is not None for price in attachment_prices)
        ):
            total_amount = sum(
                (
                    item.quantity * item.unit_price_hkd
                    for item in attachment_allocations
                    if item.unit_price_hkd is not None
                ),
                Decimal("0"),
            )
            unit_price = total_amount / quantity
        elif unit_price is None:
            unit_price = None
        allocations = [
            (item.master_contract, item.quantity)
            for item in attachment_allocations
            if item.master_contract
        ]
    elif master_contract and quantity is not None:
        allocations = [(master_contract, quantity)]

    delivery_dates = _extract_delivery_dates(first_page, expected_year=expected_year)
    if not delivery_dates and attachment_text:
        delivery_dates = _extract_delivery_dates(attachment_text, expected_year=expected_year)
    ship_date = delivery_dates[-1] if delivery_dates else ""

    return DickieParsedOrder(
        reference_no=reference_no,
        master_contract=master_contract,
        po_no=po_no,
        source_date=source_date,
        ship_date=ship_date,
        product_no=product_no,
        product_name_en=product_name_en,
        quantity=quantity,
        unit_price_hkd=unit_price,
        packing=packing,
        customer_name=customer_name,
        country=country,
        contact=contact,
        packaging=packaging,
        allocations=allocations,
        lineage={
            "received_date": "PDF首页 · Date of creation",
            "po_no": "PDF首页/Attachment · Purchase Contract No.",
            "contract_no": "PDF首页/Attachment · Master Contract No.",
            "customer_country": "PDF唛头/备注 · This order is for / Port of discharge",
            "product_no": "PDF首页 · Mat. No.",
            "product_name_en": "PDF首页 · Mat. No. 下方 Short Description",
            "quantity": "PDF首页/Attachment · Quantity",
            "units_per_carton": "PDF首页 · Packing（外箱装箱数）",
            "carton_count": "系统计算 · 数量 ÷ 外箱装箱数",
            "standard": "模板规则 · 按目的市场映射",
            "unit_price_hkd": "PDF首页/Attachment · Unit Price HKD",
            "amount_hkd": "系统计算 · 数量 × 单价HK",
            "packaging": "PDF首页 · Packing 下方包装方式",
            "line_q": "PDF · Delivery Date",
            "customer_q": "旧插件规则 · Delivery Date 减 7 天",
            "requested_ship_date": "PDF · Delivery Date",
        },
    )


def _split_dickie_order_page_groups(pages: list[str]) -> list[list[str]]:
    """Split one uploaded PDF into its individual Release Orders.

    Dickie frequently sends a combined PDF where every order starts with a
    scanned ``Release Order Page 1`` and is followed by its mark/attachment
    pages.  Keeping those pages together preserves customer and mixed-contract
    context while preventing the next order from overwriting the first one.
    """
    order_starts = [
        index
        for index, page in enumerate(pages)
        if re.search(
            r"\bRelease\s+Order\s+Page\s*:?\s*1\b",
            page,
            re.IGNORECASE,
        )
    ]
    if len(order_starts) <= 1:
        return [pages]

    groups: list[list[str]] = []
    for position, start in enumerate(order_starts):
        end = order_starts[position + 1] if position + 1 < len(order_starts) else len(pages)
        group = pages[start:end]
        if group:
            groups.append(group)
    return groups or [pages]


def parse_dickie_pdf_orders(
    file_name: str,
    content: bytes,
    *,
    fallback_received_date: str,
) -> list[DickieParsedOrder]:
    if not file_name.lower().endswith(".pdf"):
        raise CustomerOrderWorkbookError("Dickie 原始 PO 只支持 .pdf")
    if not content.startswith(b"%PDF"):
        raise CustomerOrderWorkbookError("Dickie PO 文件扩展名为 PDF，但内容不是有效 PDF")
    pages = _extract_pdf_ocr_pages(content)
    return [
        _parse_dickie_ocr_pages(
            group,
            fallback_received_date=fallback_received_date,
        )
        for group in _split_dickie_order_page_groups(pages)
    ]


def parse_dickie_pdf(
    file_name: str,
    content: bytes,
    *,
    fallback_received_date: str,
) -> DickieParsedOrder:
    return parse_dickie_pdf_orders(
        file_name,
        content,
        fallback_received_date=fallback_received_date,
    )[0]


def format_dickie_product_no(raw: str) -> str:
    compact = re.sub(r"\s+", "", raw or "")
    match = re.fullmatch(r"(\d{2})(\d{3})(\d{4,5})([A-Za-z0-9]*)", compact)
    if not match:
        return raw
    return f"{match.group(1)} {match.group(2)} {match.group(3)}{match.group(4)}".strip()


def _product_key(value: Any) -> str:
    return re.sub(r"\s+", "", _clean_identifier(value)).upper()


def _packing_units(packing: str) -> Decimal | None:
    values = [Decimal(value) for value in re.findall(r"\d+", packing)]
    if not values:
        return None
    return values[-1]


def _country_standard(customer_name: str, country: str) -> str:
    combined = f"{customer_name} {country}".upper()
    if "GERMANY" in combined or "德国" in combined:
        return "德国标准"
    if "USA" in combined or "美国" in combined or "CALENDAR" in combined:
        return "美国标准"
    if "CANADA" in combined or "加拿大" in combined or "MONTREAL" in combined:
        return "加拿大标准"
    return ""


class DickieSchedule(OoxmlSchedule):
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
        required = {"接单表", "正单评审表", ITEM_SHEET, DINO_ITEM_SHEET, MO_SHEET}
        missing = required - self.sheet_paths.keys()
        if missing:
            raise CustomerOrderWorkbookError(
                "排期结构不匹配 DICKIE_PRODUCTION_SCHEDULE_V1，"
                f"缺少工作表：{', '.join(sorted(missing))}"
            )
        order_headers = self.read_rows("接单表", limit=3).get(3, {})
        item_headers = self.read_rows(ITEM_SHEET, limit=3).get(3, {})
        dino_headers = self.read_rows(DINO_ITEM_SHEET, limit=1).get(1, {})
        if (
            order_headers.get("D") != "Reference"
            or item_headers.get("C") != "Reference"
            or dino_headers.get("C") != "Reference"
        ):
            raise CustomerOrderWorkbookError("Dickie 排期表头与当前模板版本不一致")

    def build_product_index(self) -> dict[str, DickieProductLookup]:
        index: dict[str, DickieProductLookup] = {}
        for sheet_name, order_type, contact_column, packaging_column in (
            (ITEM_SHEET, "normal", "K", "L"),
            (DINO_ITEM_SHEET, "dino", "L", "M"),
        ):
            for row_number, values in self.read_rows(sheet_name).items():
                product_no = _product_key(values.get("F"))
                if not product_no:
                    continue
                record = index.setdefault(product_no, DickieProductLookup())
                record.order_type = order_type
                if values.get("H"):
                    record.product_name_zh = _clean_text(values.get("H"))
                if values.get(contact_column):
                    record.contact = _clean_text(values.get(contact_column))
                if values.get(packaging_column):
                    record.packaging = _clean_text(values.get(packaging_column))
                record.existing_rows.append(
                    {
                        "sheet_name": sheet_name,
                        "row": str(row_number),
                        "reference_no": _clean_text(values.get("C")),
                        "master_contract": _clean_text(values.get("B")),
                    }
                )
        return index

    @staticmethod
    def _is_schedule_record(values: dict[str, str]) -> bool:
        return bool(
            _clean_text(values.get("B"))
            and _clean_text(values.get("C"))
            and _clean_text(values.get("D")).upper().startswith("SC")
        )

    @classmethod
    def _is_reserved_row(cls, values: dict[str, str]) -> bool:
        return (
            not _clean_text(values.get("B"))
            and not _clean_text(values.get("C"))
            and not cls._is_schedule_record(values)
        )

    def _find_append_position(
        self,
        sheet_name: str,
        *,
        boundary_row: int,
    ) -> tuple[int, int]:
        rows = self.read_rows(sheet_name)
        record_rows = [
            row_number
            for row_number, values in rows.items()
            if row_number < boundary_row and self._is_schedule_record(values)
        ]
        if not record_rows:
            raise CustomerOrderWorkbookError(f"{sheet_name} 未找到可复用样式的数据行")

        # Current Dickie schedules keep formula-backed blank rows before the
        # subtotal/footer. Insert into the first such reserved row instead of
        # immediately before the marker. This also bypasses records written to
        # the footer by older versions of the importer.
        transition_rows = [
            row_number
            for row_number in record_rows
            if row_number + 1 < boundary_row
            and self._is_reserved_row(rows.get(row_number + 1, {}))
        ]
        reference_row = max(transition_rows or record_rows)
        insert_row = reference_row + 1
        if insert_row > boundary_row:
            raise CustomerOrderWorkbookError(f"{sheet_name} 没有可用的接单写入位置")
        return insert_row, reference_row

    def find_order_append_position(self) -> tuple[int, int]:
        boundary_rows = [
            row_number
            for row_number, values in self.read_rows("接单表").items()
            if "年接单" in _clean_text(values.get("H"))
            and "合计" in _clean_text(values.get("K"))
        ]
        if not boundary_rows:
            raise CustomerOrderWorkbookError("接单表未找到年度接单合计边界")
        return self._find_append_position(
            "接单表",
            boundary_row=max(boundary_rows),
        )

    def find_review_append_position(self) -> tuple[int, int]:
        boundary_rows = [
            row_number
            for row_number, values in self.read_rows("正单评审表").items()
            if "负责人：罗成灿" in _clean_text(values.get("F"))
        ]
        if not boundary_rows:
            raise CustomerOrderWorkbookError("正单评审表未找到负责人边界")
        return self._find_append_position(
            "正单评审表",
            boundary_row=max(boundary_rows),
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


def _preview_row(
    parsed: DickieParsedOrder,
    lookup: DickieProductLookup | None,
    *,
    file_name: str,
    row_index: int,
) -> dict[str, Any]:
    product_no = _clean_identifier(parsed.product_no)
    formatted_product_no = format_dickie_product_no(product_no)
    quantity = parsed.quantity
    packing_units = _packing_units(parsed.packing)
    carton_count = (
        quantity / packing_units
        if quantity is not None and packing_units is not None and packing_units > 0
        else None
    )
    unit_price = parsed.unit_price_hkd
    amount = quantity * unit_price if quantity is not None and unit_price is not None else None
    inspection_date = (
        (date.fromisoformat(parsed.ship_date) - timedelta(days=7)).isoformat()
        if parsed.ship_date
        else ""
    )
    issues: list[dict[str, Any]] = []
    required = {
        "reference_no": ("SC Reference", parsed.reference_no),
        "contract_no": ("Master Contract No.", parsed.master_contract),
        "po_no": ("Purchase Contract No.", parsed.po_no),
        "product_no": ("产品编号", product_no),
        "quantity": ("数量", _decimal_text(quantity) if quantity is not None else ""),
        "unit_price_hkd": ("单价HK", _decimal_text(unit_price) if unit_price is not None else ""),
        "requested_ship_date": ("客要求走货期", parsed.ship_date),
    }
    for field_name, (label, value) in required.items():
        if not value:
            issues.append(
                _make_issue(
                    "blocked",
                    "missing_required_field",
                    field_name,
                    f"{label} 未能从 Dickie PDF 提取",
                )
            )
    if packing_units is None:
        issues.append(
            _make_issue(
                "blocked",
                "missing_required_field",
                "units_per_carton",
                "装箱数未能从 Dickie PDF Packing 提取",
            )
        )
    duplicate_rows = [
        existing
        for existing in (lookup.existing_rows if lookup else [])
        if existing["reference_no"] == parsed.reference_no
    ]
    if duplicate_rows:
        duplicate = duplicate_rows[0]
        issues.append(
            _make_issue(
                "blocked",
                "duplicate_reference",
                "reference_no",
                (
                    f"Reference {parsed.reference_no} 已存在于当前排期"
                    f"{duplicate['sheet_name']}第 {duplicate['row']} 行，不能重复导入"
                ),
            )
        )
    if lookup is None:
        issues.append(
            _make_issue(
                "warning",
                "product_not_in_schedule",
                "product_no",
                f"产品 {formatted_product_no or product_no} 未在当前 Dickie Item 表出现，将追加到活动区末尾",
            )
        )
    if not parsed.customer_name:
        issues.append(
            _make_issue(
                "blocked",
                "missing_customer",
                "customer_country",
                "客名/国家未能从 Dickie PDF 提取",
                can_skip=True,
                skip_label="客名/国家留空，稍后由跟客补充",
            )
        )
    product_name_zh = lookup.product_name_zh if lookup else parsed.product_name_en
    contact = parsed.contact or (lookup.contact if lookup else "")
    packaging = parsed.packaging or (lookup.packaging if lookup else "")
    if not contact:
        issues.append(
            _make_issue(
                "warning",
                "missing_contact",
                "contact",
                "联系人未能从 PDF 或当前排期匹配，将留空",
            )
        )
    if not packaging:
        issues.append(
            _make_issue(
                "warning",
                "missing_packaging",
                "packaging",
                "包装方式未能从 PDF 或当前排期匹配，将留空",
            )
        )
    status = (
        "blocked"
        if any(issue["severity"] == "blocked" for issue in issues)
        else "warning"
        if issues
        else "valid"
    )
    row_id = f"dickie-{parsed.reference_no or row_index}-{product_no or row_index}-{row_index}"
    for issue in issues:
        issue["skip_key"] = (
            f"{row_id}|{issue['code']}|{issue['field']}"
            if issue["can_skip"]
            else ""
        )
    customer_country = " / ".join(
        value for value in (parsed.customer_name, parsed.country) if value
    )
    lineage = dict(parsed.lineage)
    lineage["product_name_zh"] = (
        f"当前 Dickie 排期 · 货号 {formatted_product_no}"
        if lookup and lookup.product_name_zh
        else "PDF产品英文名回退"
    )
    return {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "有效", "warning": "警告", "blocked": "阻断"}[status],
        "received_date": parsed.source_date,
        "po_no": parsed.po_no,
        "contract_no": parsed.master_contract,
        "reference_no": parsed.reference_no,
        "customer_country": customer_country,
        "customer_name": parsed.customer_name,
        "country": parsed.country,
        "product_no": formatted_product_no,
        "product_name_zh": product_name_zh,
        "product_name_en": parsed.product_name_en,
        "quantity": _decimal_text(quantity),
        "units_per_carton": _decimal_text(packing_units),
        "packing": parsed.packing,
        "carton_count": _decimal_text(carton_count),
        "standard": _country_standard(parsed.customer_name, parsed.country),
        "unit_price_hkd": _decimal_text(unit_price),
        "amount_hkd": _decimal_text(amount),
        "packaging": packaging,
        "contact": contact,
        "line_q": parsed.ship_date,
        "customer_q": inspection_date,
        "requested_ship_date": parsed.ship_date,
        "input_template": INPUT_TEMPLATE,
        "target_template": TARGET_TEMPLATE,
        "item_sheet_name": (
            DINO_ITEM_SHEET if lookup and lookup.order_type == "dino" else ITEM_SHEET
        ),
        "source_po_file_name": file_name,
        "lineage": lineage,
        "issues": issues,
        "_allocations": parsed.allocations,
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


def create_dickie_batch_preview(
    *,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> dict[str, Any]:
    if factory_id != "huaxing":
        raise CustomerOrderWorkbookError("Dickie 只属于华兴厂区，不能导入其他厂区")
    if not po_files:
        raise CustomerOrderWorkbookError("请至少上传一份 Dickie PDF")
    if len(po_files) > MAX_BATCH_PO_FILES:
        raise CustomerOrderWorkbookError(f"单批最多上传 {MAX_BATCH_PO_FILES} 份 Dickie PDF")
    if sum(len(content) for _, content in po_files) > MAX_BATCH_PO_BYTES:
        raise CustomerOrderWorkbookError("本批 Dickie PDF 合计超过 80MB 限制")
    if any(len(content) > MAX_PO_BYTES for _, content in po_files):
        raise CustomerOrderWorkbookError("单份 Dickie PDF 不能超过 12MB")
    if len(schedule_content) > MAX_SCHEDULE_BYTES:
        raise CustomerOrderWorkbookError("Dickie 客户排期超过 35MB 限制")
    try:
        normalized_received_date = date.fromisoformat(received_date).isoformat()
    except ValueError as exc:
        raise CustomerOrderWorkbookError("来单日期必须是 YYYY-MM-DD") from exc

    plain_schedule, encrypted = _decrypt_schedule(schedule_content)
    schedule = DickieSchedule(plain_schedule)
    product_index = schedule.build_product_index()
    rows: list[dict[str, Any]] = []
    row_index = 0
    for file_name, content in po_files:
        try:
            parsed_orders = parse_dickie_pdf_orders(
                file_name,
                content,
                fallback_received_date=normalized_received_date,
            )
        except CustomerOrderWorkbookError as exc:
            raise CustomerOrderWorkbookError(f"{file_name}：{exc}") from exc
        for parsed in parsed_orders:
            row_index += 1
            lookup = product_index.get(_product_key(parsed.product_no))
            rows.append(
                _preview_row(
                    parsed,
                    lookup,
                    file_name=file_name,
                    row_index=row_index,
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
        "Dickie 原始 PO 为扫描版 PDF，预览保留字段级来源；确认前需人工核对 OCR 识别结果。",
        "输出更新接单表、正单评审表及 Iteam 表；同货号、同主合同的“已入系统”行按各子合同数量分别扣减。",
        "下载文件保持原排期文件名和 2026 打开密码。"
        if encrypted
        else "上传文件未加密；下载文件将使用 2026 打开密码。",
    ]
    return {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "customer_code": "dickie",
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
    }


def _formula_payload(formula: str, cached: Decimal | None = None) -> dict[str, Any]:
    return {"formula": formula, **({"cached": cached} if cached is not None else {})}


def _item_sheet_for_row(row: dict[str, Any]) -> str:
    return row["item_sheet_name"]


def _item_date_column(row: dict[str, Any]) -> str:
    return "P" if _item_sheet_for_row(row) == DINO_ITEM_SHEET else "O"


def _item_inspection_column(row: dict[str, Any]) -> str:
    return "R" if _item_sheet_for_row(row) == DINO_ITEM_SHEET else "Q"


def _item_template_row(
    workbook: DickieSchedule,
    sheet_name: str,
    product_no: str,
) -> tuple[int, int]:
    rows = workbook.read_rows(sheet_name)
    matches = [
        row_number
        for row_number, values in rows.items()
        if _product_key(values.get("F")) == _product_key(product_no)
    ]
    if matches:
        return matches[0], matches[0]
    fallback = next(
        (
            row_number
            for row_number, values in sorted(rows.items())
            if _product_key(values.get("F"))
            and row_number > (1 if sheet_name == DINO_ITEM_SHEET else 3)
        ),
        None,
    )
    if fallback is None:
        raise CustomerOrderWorkbookError(f"{sheet_name} 没有可复用的订单行样式")
    return max(rows, default=fallback) + 1, fallback


def _find_item_insert_row(
    workbook: DickieSchedule,
    row: dict[str, Any],
) -> tuple[int, int]:
    sheet_name = _item_sheet_for_row(row)
    rows = workbook.read_rows(sheet_name)
    product_no = _product_key(row["product_no"])
    date_column = _item_date_column(row)
    new_ship_date = row["requested_ship_date"]
    matches = [
        row_number
        for row_number, values in sorted(rows.items())
        if _product_key(values.get("F")) == product_no
    ]
    if not matches:
        return _item_template_row(workbook, sheet_name, product_no)
    active_rows = [
        row_number for row_number in matches if _clean_text(rows[row_number].get("C")) != "已入系统"
    ]
    system_rows = [
        row_number for row_number in matches if _clean_text(rows[row_number].get("C")) == "已入系统"
    ]
    for row_number in active_rows:
        existing_date = _format_iso_date(
            _decimal(rows[row_number].get(date_column)) or rows[row_number].get(date_column)
        )
        if existing_date and new_ship_date and new_ship_date < existing_date:
            return row_number, row_number
    if system_rows:
        return system_rows[0], active_rows[-1] if active_rows else system_rows[0]
    return matches[-1] + 1, matches[-1]


def _item_values(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sheet_name = _item_sheet_for_row(row)
    values: dict[str, dict[str, Any]] = {
        "A": {"value": _excel_serial(row["received_date"])},
        "B": {"value": row["contract_no"], "inline": True},
        "C": {"value": row["reference_no"], "inline": True},
        "D": {"value": row["po_no"], "inline": True},
        "E": {"value": row["customer_name"], "inline": True},
        "F": {"value": row["product_no"], "inline": True},
        "G": {"value": row["product_no"], "inline": True},
        "H": {"value": row["product_name_zh"], "inline": True},
        "I": {"value": Decimal(row["quantity"])},
        "J": {"value": row["packing"], "inline": True},
        _item_date_column(row): {"value": _excel_serial(row["requested_ship_date"])},
        _item_inspection_column(row): {"value": _excel_serial(row["customer_q"])},
    }
    if sheet_name == DINO_ITEM_SHEET:
        values["L"] = {"value": row["contact"], "inline": True}
        values["M"] = {"value": row["packaging"], "inline": True}
    else:
        values["K"] = {"value": row["contact"], "inline": True}
        values["L"] = {"value": row["packaging"], "inline": True}
    return values


def _contract_base(value: str) -> str:
    first_line = _clean_text(value).splitlines()[0] if value else ""
    return re.sub(r"/\d+$", "", first_line).strip()


def _deduct_allocations(
    workbook: DickieSchedule,
    row: dict[str, Any],
) -> None:
    sheet_name = _item_sheet_for_row(row)
    product_no = _product_key(row["product_no"])
    rows = workbook.read_rows(sheet_name)
    allocations = row.get("_allocations") or [
        (row["contract_no"].splitlines()[0], Decimal(row["quantity"]))
    ]
    for master_contract, allocation_quantity in allocations:
        master_base = _contract_base(master_contract)
        target_row = next(
            (
                row_number
                for row_number, values in rows.items()
                if _clean_text(values.get("C")) == "已入系统"
                and _product_key(values.get("F")) == product_no
                and _contract_base(values.get("B", "")) == master_base
            ),
            None,
        )
        if target_row is None:
            continue
        formula = workbook.read_cell_formula(sheet_name, target_row, "I").strip()
        current_quantity = _decimal(rows[target_row].get("I"))
        formula_base = formula or _decimal_text(current_quantity)
        if not formula_base:
            raise CustomerOrderWorkbookError(
                f"{sheet_name} 第 {target_row} 行已入系统数量为空，无法扣减"
            )
        workbook.set_cell(
            sheet_name,
            target_row,
            "I",
            formula=f"{formula_base}-{_decimal_text(allocation_quantity)}",
            cached=(
                current_quantity - allocation_quantity
                if current_quantity is not None
                else None
            ),
        )


def _write_item_row(workbook: DickieSchedule, row: dict[str, Any]) -> None:
    sheet_name = _item_sheet_for_row(row)
    insert_row, template_row = _find_item_insert_row(workbook, row)
    workbook.insert_row_at(
        sheet_name,
        insert_row=insert_row,
        values=_item_values(row),
        reference_row_number=template_row,
    )
    _deduct_allocations(workbook, row)


def _order_values(row: dict[str, Any], insert_row: int) -> dict[str, dict[str, Any]]:
    item_sheet = _item_sheet_for_row(row)
    return {
        "B": {"value": _excel_serial(row["received_date"])},
        "C": {"value": row["contract_no"], "inline": True},
        "D": {"value": row["reference_no"], "inline": True},
        "E": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:D,2,0)"),
        "F": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:E,3,0)"),
        "G": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:F,4,0)"),
        "H": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:H,6,0)"),
        "I": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:I,7,0)"),
        "J": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:J,8,0)"),
        "K": _formula_payload(f"VLOOKUP(D{insert_row},'正单评审表'!D:S,16,0)"),
        "L": _formula_payload(f"I{insert_row}*K{insert_row}"),
        "O": _formula_payload(f"VLOOKUP(D{insert_row},'正单评审表'!D:R,14,0)"),
    }


def _review_values(row: dict[str, Any], insert_row: int) -> dict[str, dict[str, Any]]:
    item_sheet = _item_sheet_for_row(row)
    is_dino = item_sheet == DINO_ITEM_SHEET
    ship_range_end = "P" if is_dino else "Q"
    ship_index = 14 if is_dino else 15
    requested_range_end = "R" if is_dino else "O"
    requested_index = 16 if is_dino else 13
    return {
        "B": {"value": _excel_serial(row["received_date"])},
        "C": {"value": row["contract_no"], "inline": True},
        "D": {"value": row["reference_no"], "inline": True},
        "E": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:D,2,0)"),
        "F": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:E,3,0)"),
        "G": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:F,4,0)"),
        "H": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:H,6,0)"),
        "I": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:I,7,0)"),
        "J": _formula_payload(f"VLOOKUP(D{insert_row},'{item_sheet}'!C:J,8,0)"),
        "K": _formula_payload(f"I{insert_row}/J{insert_row}"),
        "Q": _formula_payload(
            f"VLOOKUP(D{insert_row},'{item_sheet}'!C:{ship_range_end},{ship_index},0)"
        ),
        "R": _formula_payload(
            f"VLOOKUP(D{insert_row},'{item_sheet}'!C:{requested_range_end},{requested_index},0)"
        ),
        "S": {"value": Decimal(row["unit_price_hkd"])},
        "T": _formula_payload(f"I{insert_row}*S{insert_row}"),
    }


def _validate_skips(preview: dict[str, Any], requested_skips: set[str]) -> None:
    available = {
        issue["skip_key"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["can_skip"]
    }
    if requested_skips - available:
        raise CustomerOrderWorkbookError("所选跳过项已失效或不允许跳过，请重新解析后再确认")
    remaining = [
        issue["message"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["severity"] == "blocked"
        and issue["skip_key"] not in requested_skips
    ]
    if remaining:
        raise CustomerOrderWorkbookError("仍有阻断项：" + "；".join(remaining))


def export_dickie_batch_schedule(
    *,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
    skipped_issue_keys: set[str] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    preview = create_dickie_batch_preview(
        factory_id=factory_id,
        received_date=received_date,
        po_files=po_files,
        schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
    )
    _validate_skips(preview, skipped_issue_keys or set())
    plain_schedule, _ = _decrypt_schedule(schedule_content)
    workbook = DickieSchedule(plain_schedule)

    for row in reversed(preview["rows"]):
        _write_item_row(workbook, row)

    for row in preview["rows"]:
        order_insert_row, order_reference_row = workbook.find_order_append_position()
        workbook.insert_row_at(
            "接单表",
            insert_row=order_insert_row,
            values=_order_values(row, order_insert_row),
            reference_row_number=order_reference_row,
        )
        review_insert_row, review_reference_row = workbook.find_review_append_position()
        workbook.insert_row_at(
            "正单评审表",
            insert_row=review_insert_row,
            values=_review_values(row, review_insert_row),
            reference_row_number=review_reference_row,
        )

    workbook.set_recalculation()
    output = _encrypt_schedule(workbook.to_bytes())
    return output, schedule_file_name, preview
