from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from app.schemas.indonesia_invoice import (
    RriInvoiceDocument,
    RriInvoiceHeaderCheck,
    RriInvoiceLineCheck,
    RriInvoiceReconciliationResponse,
    RriInvoiceReconciliationSummary,
)
from app.services.carton_mark import configure_tesseract, missing_tesseract_message

FAITH_JET_FACTOR = Decimal("0.98")
PRICE_QUANTUM = Decimal("0.0001")
AMOUNT_QUANTUM = Decimal("0.01")
FAITH_JET_PROFILE_CODE = "faith-jet"
FAITH_JET_CUSTOMER_NAME = "施信（Faith Jet）"


class RriInvoiceParseError(ValueError):
    """Raised when a PDF does not follow the supported Faith Jet text-based invoice layout."""


@dataclass(frozen=True)
class InvoiceLine:
    sku: str
    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class ParsedInvoice:
    invoice_no: str
    po_no: str
    date: str
    declared_total: Decimal | None
    lines: list[InvoiceLine]
    input_slot: str = ""


CUSTOMER_LINE_PATTERN = re.compile(
    r"^(?P<sku>[A-Z0-9]+)\([^)]*\)\s+(?P<description>.+?)\s+(?P<quantity>\d+)\s+"
    r"(?P<unit_price>\d+\.\d{4})\s+(?P<amount>[\d,]+\.\d{2})\s*$",
)
SUPPLIER_LINE_PATTERN = re.compile(
    r"^(?P<sku>[A-Z0-9]+)\s+(?P<description>.+?)\s+(?P<quantity>\d+)\s+PCS\s+HKD\s+"
    r"(?P<unit_price>\d+\.\d{4})\s+HKD\s+(?P<amount>[\d,]+\.\d{2})\s*$",
)
RRM_CUSTOMER_LINE_PATTERN = re.compile(
    r"^\W*(?P<sku>(?:Y|¥)\S{3,8})\s+(?P<description>.+?)\s+(?P<quantity>\d+)\s+S(?:E|F)T\s+"
    r"\D*?(?P<unit_price>[\dOG]+\.\s*\d{4})\D+?(?P<amount>[\d,]+\.\s*\d{2})\s*$",
    re.IGNORECASE,
)


def _money(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _as_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "").strip())


def _normalize_text(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _read_pdf_text(pdf_bytes: bytes, label: str) -> str:
    if not pdf_bytes.startswith(b"%PDF"):
        raise RriInvoiceParseError(f"{label}不是有效的 PDF 文件。")

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # pragma: no cover - third-party PDF parse failures vary by runtime
        raise RriInvoiceParseError(f"{label}无法读取：{exc}") from exc

    if not text.strip():
        raise RriInvoiceParseError(f"{label}没有可读取的文字；目前施信客户核对仅支持文字型 PDF。")

    return text


def _find_first(pattern: str, text: str, *, flags: int = re.IGNORECASE) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _normalize_date(value: str) -> str:
    value = re.sub(r"\s+", "", value.strip())
    for pattern in ("%Y/%m/%d", "%d-%b-%y", "%d-%b-%Y", "%d/%b/%y", "%d/%b/%Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return value


def _parse_lines(text: str, pattern: re.Pattern[str]) -> list[InvoiceLine]:
    lines: list[InvoiceLine] = []
    for raw_line in text.splitlines():
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        groups = match.groupdict()
        lines.append(InvoiceLine(
            sku=groups["sku"],
            description=groups["description"].strip(),
            quantity=int(groups["quantity"]),
            unit_price=_as_decimal(groups["unit_price"]),
            amount=_as_decimal(groups["amount"]),
        ))
    return lines


def _normalize_rrm_customer_sku(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "", value.upper())
    if not normalized.startswith("Y"):
        normalized = f"Y{normalized}"
    return f"Y{normalized[1:].translate(str.maketrans({'O': '0', 'Q': '0'}))}"


def _normalize_ocr_decimal(value: str) -> Decimal:
    normalized = re.sub(r"\s+", "", value.upper()).translate(str.maketrans({"O": "0", "G": "0"}))
    return _as_decimal(normalized)


def _resolve_rrm_customer_unit_price(*, ocr_price: Decimal, amount: Decimal, quantity: int) -> Decimal:
    """Repair an OCR decimal only when it contradicts the printed line amount."""
    if _money(ocr_price * quantity, AMOUNT_QUANTUM) == amount:
        return ocr_price

    derived_price = _money(amount / quantity, PRICE_QUANTUM)
    if _money(derived_price * quantity, AMOUNT_QUANTUM) == amount:
        return derived_price
    return ocr_price


def _parse_rrm_customer_lines(ocr_text: str) -> list[InvoiceLine]:
    lines: list[InvoiceLine] = []
    for raw_line in ocr_text.splitlines():
        cleaned_line = re.sub(r"([OG])\.\s*(?=\d{4}\b)", "0.", raw_line.upper())
        match = RRM_CUSTOMER_LINE_PATTERN.match(cleaned_line.strip())
        if not match:
            continue
        groups = match.groupdict()
        amount = _normalize_ocr_decimal(groups["amount"])
        unit_price = _resolve_rrm_customer_unit_price(
            ocr_price=_normalize_ocr_decimal(groups["unit_price"]),
            amount=amount,
            quantity=int(groups["quantity"]),
        )
        lines.append(InvoiceLine(
            sku=_normalize_rrm_customer_sku(groups["sku"]),
            description=groups["description"].strip(),
            quantity=int(groups["quantity"]),
            unit_price=unit_price,
            amount=amount,
        ))
    return lines


def _first_fj_invoice_number(*texts: str) -> str:
    for text in texts:
        match = re.search(r"\bFJ\s*(\d{5})\b", text, re.IGNORECASE)
        if match:
            return f"FJ{match.group(1)}"
    return ""


def _first_fj_purchase_order(*texts: str) -> str:
    for text in texts:
        match = re.search(r"\bZP[O0]\s*(\d{6,})\b", text, re.IGNORECASE)
        if match:
            return f"ZPO{match.group(1)}"
    return ""


def _first_fj_date(*texts: str) -> str:
    for text in texts:
        match = re.search(r"\b(\d{1,2}\s*[/\-]\s*[A-Za-z]{3}\s*[/\-]\s*\d{2,4})\b", text)
        if match:
            return _normalize_date(match.group(1))
    return ""


def _read_faith_jet_customer_ocr_text(pdf_bytes: bytes, label: str) -> str:
    """Render the legacy RRM Faith Jet customer invoice and read its table with local OCR."""
    try:
        import pypdfium2 as pdfium  # type: ignore
        import pytesseract  # type: ignore
    except Exception as exc:  # pragma: no cover - optional runtime packages vary by deployment
        raise RriInvoiceParseError(
            f"{label}已识别为施信 RRM 客票版式，但本机缺少 OCR 依赖（pypdfium2、Pillow 或 pytesseract）。",
        ) from exc

    tesseract_cmd, language = configure_tesseract(pytesseract)
    if not tesseract_cmd:
        raise RriInvoiceParseError(
            f"{label}已识别为施信 RRM 客票版式，但本机 OCR 引擎不可用。{missing_tesseract_message()}",
        )

    try:
        document = pdfium.PdfDocument(pdf_bytes)
        image = document[0].render(scale=4).to_pil().convert("RGB")
        return pytesseract.image_to_string(
            image,
            lang=language,
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
            timeout=35,
        )
    except Exception as exc:  # pragma: no cover - third-party OCR failures vary by host
        raise RriInvoiceParseError(f"{label}的施信 RRM 客票 OCR 识别失败：{exc}") from exc
    finally:
        if "document" in locals():
            document.close()


def _parse_rrm_customer_invoice_text(native_text: str, ocr_text: str, *, input_slot: str = "") -> ParsedInvoice:
    lines = _parse_rrm_customer_lines(ocr_text)
    if not lines:
        raise RriInvoiceParseError("未识别到施信 RRM 客户票明细行。")

    return ParsedInvoice(
        invoice_no=_first_fj_invoice_number(native_text, ocr_text),
        po_no=_first_fj_purchase_order(native_text, ocr_text),
        date=_first_fj_date(ocr_text, native_text),
        # Legacy Faith Jet customer invoices place the declared total in a scanned/encoded footer.
        # The parsed line amounts are the reliable display value; supplier total remains independently checked.
        declared_total=_money(sum((line.amount for line in lines), Decimal("0")), AMOUNT_QUANTUM),
        lines=lines,
        input_slot=input_slot,
    )


def _parse_rri_customer_invoice_text(text: str, *, input_slot: str = "") -> ParsedInvoice:
    lines = _parse_lines(text, CUSTOMER_LINE_PATTERN)
    if not lines:
        raise RriInvoiceParseError("未识别到施信客户票明细行。")

    return ParsedInvoice(
        invoice_no=_find_first(r"\b(SMC\d+)\b", text),
        po_no=_find_first(r"PO\s*NO\s*:\s*([A-Z0-9-]+)", text),
        date=_normalize_date(_find_first(r"DATE.{0,5}\s*(\d{4}/\d{1,2}/\d{1,2})", text)),
        declared_total=_as_decimal(_find_first(r"Total:\s*([\d,]+\.\d{2})", text)) if re.search(r"Total:\s*[\d,]+\.\d{2}", text, re.IGNORECASE) else None,
        lines=lines,
        input_slot=input_slot,
    )


def _parse_rri_supplier_invoice_text(text: str, *, input_slot: str = "") -> ParsedInvoice:
    lines = _parse_lines(text, SUPPLIER_LINE_PATTERN)
    if not lines:
        raise RriInvoiceParseError("未识别到施信供应商票明细行。")

    date_match = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{2})", text)
    total_match = re.search(r"TOTAL\s+HKD\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
    invoice_no = _find_first(r"\b(SMC\d+)\b", text)
    po_no = _find_first(r"\b(MPO\d+)\b", text)
    return ParsedInvoice(
        invoice_no=invoice_no or _first_fj_invoice_number(text),
        po_no=po_no or _first_fj_purchase_order(text),
        date=_normalize_date(date_match.group(1)) if date_match else "",
        declared_total=_as_decimal(total_match.group(1)) if total_match else None,
        lines=lines,
        input_slot=input_slot,
    )


def parse_rri_customer_invoice(pdf_bytes: bytes) -> ParsedInvoice:
    return _parse_rri_customer_invoice_text(_read_pdf_text(pdf_bytes, "客户票"))


def parse_rri_supplier_invoice(pdf_bytes: bytes) -> ParsedInvoice:
    return _parse_rri_supplier_invoice_text(_read_pdf_text(pdf_bytes, "供应商票"))


def _classify_rri_invoice_pdf(pdf_bytes: bytes, input_slot: str) -> tuple[str, ParsedInvoice]:
    text = _read_pdf_text(pdf_bytes, f"PDF {input_slot}")
    customer_lines = _parse_lines(text, CUSTOMER_LINE_PATTERN)
    supplier_lines = _parse_lines(text, SUPPLIER_LINE_PATTERN)

    if customer_lines and not supplier_lines:
        return "customer", _parse_rri_customer_invoice_text(text, input_slot=input_slot)
    if supplier_lines and not customer_lines:
        return "supplier", _parse_rri_supplier_invoice_text(text, input_slot=input_slot)

    if customer_lines and supplier_lines:
        raise RriInvoiceParseError(f"PDF {input_slot} 同时匹配施信客户票和供应商票版式，无法自动判断票据角色。")

    if re.search(r"FJ\s*\d{5}", text, re.IGNORECASE) or re.search(r"F[AR]ITH\s+JET", text, re.IGNORECASE):
        ocr_text = _read_faith_jet_customer_ocr_text(pdf_bytes, f"PDF {input_slot}")
        return "customer", _parse_rrm_customer_invoice_text(text, ocr_text, input_slot=input_slot)

    raise RriInvoiceParseError(
        f"PDF {input_slot} 未识别为已支持的施信客户票或供应商票；请上传文字型 PDF。",
    )


def _resolve_rri_invoice_roles(
    first: tuple[str, ParsedInvoice],
    second: tuple[str, ParsedInvoice],
) -> tuple[ParsedInvoice, ParsedInvoice]:
    first_role, first_invoice = first
    second_role, second_invoice = second
    if first_role == second_role:
        role_label = "客户票" if first_role == "customer" else "供应商票"
        raise RriInvoiceParseError(
            f"PDF {first_invoice.input_slot} 和 PDF {second_invoice.input_slot} 均识别为施信 {role_label}；请各导入一份客户票和供应商票。",
        )

    if first_role == "customer":
        return first_invoice, second_invoice
    return second_invoice, first_invoice


def _line_match_key(line: InvoiceLine) -> tuple[str, int]:
    description = _normalize_text(line.description)
    # Legacy Faith Jet customer invoices are OCR-read. The printed I/T prefix can
    # be recognized as 1/T without changing meaningful product-number digits.
    if description.startswith("1T"):
        description = f"IT{description[2:]}"
    return description, line.quantity


def _header_check(field: str, customer_value: str, supplier_value: str, note: str = "") -> RriInvoiceHeaderCheck:
    return RriInvoiceHeaderCheck(
        field=field,
        customer_value=customer_value,
        supplier_value=supplier_value,
        status="matched" if customer_value and customer_value == supplier_value else "mismatch",
        note=note,
    )


def reconcile_rri_invoices(customer: ParsedInvoice, supplier: ParsedInvoice) -> RriInvoiceReconciliationResponse:
    supplier_buckets: dict[tuple[str, int], list[InvoiceLine]] = defaultdict(list)
    for line in supplier.lines:
        supplier_buckets[_line_match_key(line)].append(line)

    checks: list[RriInvoiceLineCheck] = []
    matched_count = 0
    mismatch_count = 0
    missing_count = 0
    expected_supplier_total = Decimal("0")

    for customer_line in customer.lines:
        expected_price = _money(customer_line.unit_price * FAITH_JET_FACTOR, PRICE_QUANTUM)
        expected_amount = _money(expected_price * customer_line.quantity, AMOUNT_QUANTUM)
        expected_supplier_total += expected_amount
        candidates = supplier_buckets[_line_match_key(customer_line)]
        supplier_line = candidates.pop(0) if candidates else None

        if supplier_line is None:
            missing_count += 1
            checks.append(RriInvoiceLineCheck(
                customer_sku=customer_line.sku,
                description=customer_line.description,
                quantity=customer_line.quantity,
                customer_unit_price_hkd=float(customer_line.unit_price),
                expected_supplier_unit_price_hkd=float(expected_price),
                customer_amount_hkd=float(customer_line.amount),
                expected_supplier_amount_hkd=float(expected_amount),
                price_status="not_available",
                amount_status="not_available",
                status="missing_supplier_line",
                note="未找到描述和数量均一致的供应商票明细行。",
            ))
            continue

        price_matches = supplier_line.unit_price == expected_price
        amount_matches = supplier_line.amount == expected_amount
        status = "matched" if price_matches and amount_matches else "mismatch"
        if status == "matched":
            matched_count += 1
        else:
            mismatch_count += 1

        notes: list[str] = []
        if not price_matches:
            notes.append("供应商单价未等于客户单价 × 0.98（四舍五入至 4 位）。")
        if not amount_matches:
            notes.append("供应商行金额未等于换算后供应商单价 × 数量（四舍五入至 2 位）。")

        checks.append(RriInvoiceLineCheck(
            customer_sku=customer_line.sku,
            supplier_sku=supplier_line.sku,
            description=customer_line.description,
            quantity=customer_line.quantity,
            customer_unit_price_hkd=float(customer_line.unit_price),
            expected_supplier_unit_price_hkd=float(expected_price),
            supplier_unit_price_hkd=float(supplier_line.unit_price),
            customer_amount_hkd=float(customer_line.amount),
            expected_supplier_amount_hkd=float(expected_amount),
            supplier_amount_hkd=float(supplier_line.amount),
            price_status="matched" if price_matches else "mismatch",
            amount_status="matched" if amount_matches else "mismatch",
            status=status,
            note=" ".join(notes),
        ))

    unexpected_count = sum(len(lines) for lines in supplier_buckets.values())
    expected_supplier_total = _money(expected_supplier_total, AMOUNT_QUANTUM)
    supplier_total_difference = (
        _money(supplier.declared_total - expected_supplier_total, AMOUNT_QUANTUM)
        if supplier.declared_total is not None
        else None
    )
    header_checks = [
        _header_check("发票号码", customer.invoice_no, supplier.invoice_no),
        _header_check("PO / S/N", customer.po_no, supplier.po_no, "客户票 PO 应与供应商票 S/N 一致。"),
        _header_check("日期", customer.date, supplier.date),
        RriInvoiceHeaderCheck(
            field="供应商票总额",
            customer_value=f"逐行换算 {expected_supplier_total}",
            supplier_value=str(supplier.declared_total) if supplier.declared_total is not None else "未识别",
            status="matched" if supplier_total_difference == Decimal("0.00") else "mismatch",
            note="总额按每一行换算后供应商单价 × 数量并四舍五入至 2 位后求和，不直接以客户总额 × 0.98 比较。",
        ),
    ]
    has_issue = mismatch_count or missing_count or unexpected_count or any(check.status != "matched" for check in header_checks)

    return RriInvoiceReconciliationResponse(
        customer_profile_code=FAITH_JET_PROFILE_CODE,
        customer_name=FAITH_JET_CUSTOMER_NAME,
        factor=float(FAITH_JET_FACTOR),
        rounding_rule="逐行：客户单价 × 0.98 四舍五入至 4 位；换算后单价 × 数量四舍五入至 2 位；总额为换算后行金额之和。",
        customer_invoice=RriInvoiceDocument(
            input_slot=customer.input_slot,
            invoice_no=customer.invoice_no,
            po_no=customer.po_no,
            date=customer.date,
            line_count=len(customer.lines),
            declared_total_hkd=float(customer.declared_total) if customer.declared_total is not None else None,
        ),
        supplier_invoice=RriInvoiceDocument(
            input_slot=supplier.input_slot,
            invoice_no=supplier.invoice_no,
            po_no=supplier.po_no,
            date=supplier.date,
            line_count=len(supplier.lines),
            declared_total_hkd=float(supplier.declared_total) if supplier.declared_total is not None else None,
        ),
        header_checks=header_checks,
        line_checks=checks,
        summary=RriInvoiceReconciliationSummary(
            customer_line_count=len(customer.lines),
            supplier_line_count=len(supplier.lines),
            matched_line_count=matched_count,
            mismatch_line_count=mismatch_count,
            missing_supplier_line_count=missing_count,
            unexpected_supplier_line_count=unexpected_count,
            expected_supplier_total_hkd=float(expected_supplier_total),
            supplier_declared_total_hkd=float(supplier.declared_total) if supplier.declared_total is not None else None,
            supplier_total_difference_hkd=float(supplier_total_difference) if supplier_total_difference is not None else None,
            status="matched" if not has_issue else "review_required",
        ),
    )


def reconcile_rri_invoice_pdfs(pdf_a_bytes: bytes, pdf_b_bytes: bytes) -> RriInvoiceReconciliationResponse:
    customer, supplier = _resolve_rri_invoice_roles(
        _classify_rri_invoice_pdf(pdf_a_bytes, "A"),
        _classify_rri_invoice_pdf(pdf_b_bytes, "B"),
    )
    return reconcile_rri_invoices(customer, supplier)
