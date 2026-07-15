import sys
from decimal import Decimal
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_rri_reconciliation_applies_factor_per_line_before_summing_total():
    from app.services.indonesia_invoice import InvoiceLine, ParsedInvoice, reconcile_rri_invoices

    customer = ParsedInvoice(
        invoice_no="SMC00039",
        po_no="MPO1610115",
        date="2026-06-16",
        declared_total=Decimal("10119.25"),
        lines=[
            InvoiceLine("Y0018400L", "TODDLER FIRE DRAGON WARRIOR 4-5T", 198, Decimal("26.1740"), Decimal("5182.45")),
            InvoiceLine("Y0018400M", "TODDLER FIRE DRAGON WARRIOR 2-3T", 204, Decimal("24.2000"), Decimal("4936.80")),
        ],
    )
    supplier = ParsedInvoice(
        invoice_no="SMC00039",
        po_no="MPO1610115",
        date="2026-06-16",
        declared_total=Decimal("9916.86"),
        lines=[
            InvoiceLine("Y00184", "TODDLER FIRE DRAGON WARRIOR 4-5T", 198, Decimal("25.6505"), Decimal("5078.80")),
            InvoiceLine("Y00184", "TODDLER FIRE DRAGON WARRIOR 2-3T", 204, Decimal("23.7160"), Decimal("4838.06")),
        ],
    )

    response = reconcile_rri_invoices(customer, supplier)

    assert response.customer_profile_code == "faith-jet"
    assert response.customer_name == "施信（Faith Jet）"
    assert response.factor == 0.98
    assert response.summary.status == "matched"
    assert response.summary.matched_line_count == 2
    assert response.summary.expected_supplier_total_hkd == 9916.86
    assert [check.status for check in response.header_checks] == ["matched", "matched", "matched", "matched"]
    assert response.line_checks[0].expected_supplier_unit_price_hkd == 25.6505
    assert response.line_checks[0].expected_supplier_amount_hkd == 5078.80
    assert response.line_checks[0].price_status == "matched"
    assert response.line_checks[0].amount_status == "matched"


def test_rri_reconciliation_flags_price_or_amount_mismatches_without_losing_line_match():
    from app.services.indonesia_invoice import InvoiceLine, ParsedInvoice, reconcile_rri_invoices

    customer = ParsedInvoice(
        invoice_no="SMC00039",
        po_no="MPO1610115",
        date="2026-06-16",
        declared_total=Decimal("5182.45"),
        lines=[InvoiceLine("Y0018400L", "TODDLER FIRE DRAGON WARRIOR 4-5T", 198, Decimal("26.1740"), Decimal("5182.45"))],
    )
    supplier = ParsedInvoice(
        invoice_no="SMC00039",
        po_no="MPO1610115",
        date="2026-06-16",
        declared_total=Decimal("5078.80"),
        lines=[InvoiceLine("Y00184", "TODDLER FIRE DRAGON WARRIOR 4-5T", 198, Decimal("25.6600"), Decimal("5078.80"))],
    )

    response = reconcile_rri_invoices(customer, supplier)

    assert response.summary.status == "review_required"
    assert response.summary.mismatch_line_count == 1
    assert response.line_checks[0].status == "mismatch"
    assert response.line_checks[0].price_status == "mismatch"
    assert response.line_checks[0].amount_status == "matched"
    assert "单价" in response.line_checks[0].note


def test_rri_role_resolution_allows_customer_and_supplier_pdfs_in_either_ab_slot():
    from app.services.indonesia_invoice import InvoiceLine, ParsedInvoice, _resolve_rri_invoice_roles

    customer = ParsedInvoice("SMC00039", "MPO1610115", "2026-06-16", None, [], input_slot="B")
    supplier = ParsedInvoice("SMC00039", "MPO1610115", "2026-06-16", None, [
        InvoiceLine("Y00184", "TODDLER FIRE DRAGON WARRIOR 4-5T", 198, Decimal("25.6505"), Decimal("5078.80")),
    ], input_slot="A")

    resolved_customer, resolved_supplier = _resolve_rri_invoice_roles(("supplier", supplier), ("customer", customer))

    assert resolved_customer.input_slot == "B"
    assert resolved_supplier.input_slot == "A"


def test_rrm_faith_jet_customer_template_uses_ocr_table_fallback():
    from app.services import indonesia_invoice as service

    native_text = """
    FAITH JET LIMITED
    FJ 17732
    PURCHASE ORDER: ZPO1623301
    """
    ocr_text = """
    FAITH JET LIMITED
    30/ Jun/26
    PURCHASE ORDER: ZP01623301
    Yoo504 I SOCK MONKEY 620 SET HK$33. 0260] HK$20476. 12
    Y¥O0306 ENCHANTED UNICORN 562 SET HK$41. 2190] HK$23165. 08
    YO9056 I/T DESERT PRINCESS 1330 SET HK$0.0106 HK$13.30
    """

    parsed = service._parse_rrm_customer_invoice_text(native_text, ocr_text, input_slot="B")

    assert parsed.input_slot == "B"
    assert parsed.invoice_no == "FJ17732"
    assert parsed.po_no == "ZPO1623301"
    assert parsed.date == "2026-06-30"
    assert parsed.declared_total == Decimal("43654.50")
    assert [(line.sku, line.quantity, line.unit_price, line.amount) for line in parsed.lines] == [
        ("Y00504", 620, Decimal("33.0260"), Decimal("20476.12")),
        ("Y00306", 562, Decimal("41.2190"), Decimal("23165.08")),
        ("Y09056", 1330, Decimal("0.0100"), Decimal("13.30")),
    ]


def test_rrm_faith_jet_customer_template_is_classified_as_customer(monkeypatch):
    from app.services import indonesia_invoice as service

    native_text = "FAITH JET LIMITED\nFJ 17732\nPURCHASE ORDER: ZPO1623301"
    ocr_text = "30/Jun/26\nYoo504 I SOCK MONKEY 620 SET HK$33.0260 HK$20476.12"
    monkeypatch.setattr(service, "_read_pdf_text", lambda _pdf_bytes, _label: native_text)
    monkeypatch.setattr(service, "_read_faith_jet_customer_ocr_text", lambda _pdf_bytes, _label: ocr_text)

    role, parsed = service._classify_rri_invoice_pdf(b"%PDF-legacy-rmm", "A")

    assert role == "customer"
    assert parsed.input_slot == "A"
    assert parsed.invoice_no == "FJ17732"
    assert parsed.lines[0].sku == "Y00504"
