"""Synthetic Shushupapa PO layouts; private purchase orders stay outside Git."""
from __future__ import annotations

import io

import pytest

from app.services.huaxing_order_legacy import multi_po_parser as parser


PAGE_ONE = """Purchase Order (PO)
PO Number: 2098-0701
Issue Date: Jun 9, 2028
TO (Seller/Vendor):
Example Manufacturer Ltd.
FROM (Buyer/Importer):
SHU SHU PAPA Toy Company LLC
Example address, USA
Item Details
Item # Description Quantity Unit Casepack Total Amount
Price
87654321 18” Example Figure, Orbit 180pcs $3.25 Costco POD USD$585.00
Pilot, Blue Variant 12pcs Per
POD.
Total Order Value: Five Hundred Eighty-five Dollars and Zero Cents.
Terms and Conditions
Costco PO Number: 801-9999-121
"""
PAGE_TWO = """Delivery Date: Seller must ensure goods are ready for loading at Example Port
\uf0b7
on Jul 21st 2028.
Destination & Shipping: Costco Wholesale Japan
Incoterms: FOB Example Port
- Quality & Compliance: Goods must comply with Example Standard X-42
and meet Japan sample safety requirements. Inspection is required before shipment.
- Packaging & Marking: : Final carton markings and label specifications are TBA (To Be
\uf0b7
Advised).
Master Carton Packed with 12 pcs.
- Payment Terms: Net 45 days
Authorized Signature (Buyer):
Example Person
Date: Jun 9 2028
"""


def costco_text():
    return PAGE_ONE + "\f" + PAGE_TWO


def parse(text=None, filename="synthetic-order.pdf"):
    return parser._parse_shushupapa(text if text is not None else costco_text(), filename, 2)


def test_native_costco_source_fields_and_page_evidence():
    order = parse()
    line, = order["lines"]
    assert order["po_number"] == "2098-0701"
    assert order["customer_po"] == "801-9999-121"
    assert order["po_date"] == "2028-06-09"
    assert order["ship_date"] == "2028-07-21"
    assert (order["customer"], order["country"]) == ("Costco", "Japan")
    assert line["description"] == "18” Example Figure, Orbit Pilot, Blue Variant"
    assert (line["item_code"], line["quantity"], line["unit_price"], line["amount"]) == (
        "87654321", 180, 3.25, 585,
    )
    assert (line["outer_pack"], line["cartons"], line["inner_pack"]) == (12, 15, None)
    assert line["source_currency"] == order["source_currency"] == "USD"
    assert line["color_box"] == "Costco POD；12 pcs/POD"
    assert line["casepack"] == "Costco POD 12pcs Per POD."
    assert line["standard"] == (
        "Goods must comply with Example Standard X-42 and meet Japan sample safety "
        "requirements."
    )
    assert line["label"] == line["box_mark"] == "TBA（待客户提供）"
    assert line["shipment_note"] == (
        "Inspection is required before shipment.；"
        "Final carton markings and label specifications are TBA (To Be Advised)."
    )
    assert line["source_lineage"]["standard"]["raw_text"].endswith("Inspection is required before shipment.")
    assert line["remarks"] == line["shipment_note"]
    assert not line.get("date_code") and not line.get("product_name_zh")
    assert not line.get("inspection_date")
    assert "TBA" in order["warnings"][0]
    assert not line.get("amount_words_conflict")
    assert order["confidence"] == "high"
    for field in ("country", "standard", "label", "box_mark", "outer_pack", "ship_date"):
        assert line["source_lineage"][field]["page"] == 2
        assert line["source_lineage"][field]["source_file"] == "synthetic-order.pdf"
    assert line["source_lineage"]["color_box"]["page"] == 1
    assert line["source_lineage"]["outer_pack"]["raw_text"] == "Master Carton Packed with 12 pcs"


def test_item_amount_and_description_lineage_use_the_complete_source_row():
    line, = parse()["lines"]
    for field in ("quantity", "unit_price", "amount", "description"):
        source = line["source_lineage"][field]
        assert source["source"] == "po_pdf"
        assert source["source_file"] == "synthetic-order.pdf"
        assert source["page"] == 1
        assert "87654321 18” Example Figure, Orbit 180pcs $3.25" in source["raw_text"]
        assert "USD$585.00" in source["raw_text"]
        assert "Pilot, Blue Variant" in source["raw_text"]


def test_quality_followup_clauses_stay_in_notes_and_complete_source_evidence():
    text = costco_text().replace(
        "Inspection is required before shipment.",
        "Inspection is required before shipment. Buyer reserves the right to inspect at the factory.",
    )
    line, = parse(text)["lines"]
    assert line["standard"].endswith("Japan sample safety requirements.")
    assert "Inspection" not in line["standard"] and "Buyer" not in line["standard"]
    for field in ("remarks", "shipment_note"):
        assert "Inspection is required before shipment." in line[field]
        assert "Buyer reserves the right to inspect at the factory." in line[field]
        assert "TBA (To Be Advised)" in line[field]
    assert "Buyer reserves the right" in line["source_lineage"]["standard"]["raw_text"]
    assert "Example Standard X-42" in line["source_lineage"]["remarks"]["raw_text"]


def test_quality_without_sentence_terminator_is_preserved_whole():
    text = costco_text().replace(
        "Japan sample safety requirements. Inspection is required before shipment.",
        "Japan sample safety requirements and additional sample requirements",
    )
    line, = parse(text)["lines"]
    assert line["standard"].endswith("Japan sample safety requirements and additional sample requirements")
    assert line["source_lineage"]["standard"]["raw_text"] == line["standard"]


def test_quality_followup_notes_do_not_require_a_tba_label_clause():
    text = costco_text().replace(
        "Final carton markings and label specifications are TBA (To Be\n\uf0b7\nAdvised).",
        "No additional marking instructions.",
    )
    line, = parse(text)["lines"]
    assert line["remarks"] == line["shipment_note"] == "Inspection is required before shipment."
    assert not line.get("label") and not line.get("box_mark")


@pytest.mark.parametrize("delivery,expected", [
    ("onJul21st2028", "2028-07-21"),
    ("on or before July 22nd, 2028", "2028-07-22"),
    ("onorbeforeSept3rd2028", "2028-09-03"),
    ("on September 4 2028", "2028-09-04"),
])
def test_joined_month_dates_and_on_or_before(delivery, expected):
    text = costco_text().replace("Issue Date: Jun 9, 2028", "IssueDate:Jun9th2028")
    text = text.replace("on Jul 21st 2028", delivery)
    result = parse(text)
    assert result["po_date"] == "2028-06-09"
    assert result["ship_date"] == expected


def test_pod_count_does_not_invent_master_carton_quantity():
    line, = parse(costco_text().replace("Master Carton Packed with 12 pcs.", ""))["lines"]
    assert line["color_box"] == "Costco POD；12 pcs/POD"
    assert line["outer_pack"] is None and line["cartons"] is None
    assert "outer_pack" not in line["source_lineage"]


def test_non_integral_carton_count_is_not_rounded_or_truncated():
    text = costco_text().replace("180pcs $3.25", "181pcs $3.25").replace("USD$585.00", "USD$588.25")
    line, = parse(text)["lines"]
    assert line["quantity"] == 181 and line["outer_pack"] == 12
    assert line["cartons"] is None


def test_conflicting_master_carton_statements_reject_document():
    text = costco_text() + "\nMaster Carton Packed with 18 pcs."
    with pytest.raises(ValueError, match="Master Carton.*冲突"):
        parse(text)


def test_multiple_products_reject_before_returning_a_partial_order():
    text = costco_text().replace(
        "Total Order Value:",
        "87654322 Example Extra Figure 12pcs $1.00 Plain Box USD$12.00\nTotal Order Value:",
    )
    with pytest.raises(ValueError, match="多条产品明细.*不能只导入首项"):
        parse(text)


@pytest.mark.parametrize("second_item", ["987654321", "AB-765432", "1234567"])
def test_second_numeric_detail_with_unsupported_item_format_is_not_swallowed(second_item):
    text = costco_text().replace(
        "Total Order Value:",
        f"{second_item} Other Example Figure 12pcs $1.00 Plain Box USD$12.00\nTotal Order Value:",
    )
    with pytest.raises(ValueError, match="未支持的货号格式.*不能只导入首项"):
        parse(text)


def test_supplier_identity_never_comes_from_terminal_po_or_filename():
    text = costco_text().replace("PO Number: 2098-0701\n", "")
    result = parse(text, filename="PO_2098_0701_Costco.pdf")
    assert result["po_number"] == ""
    assert result["customer_po"] == "801-9999-121"
    assert result["lines"][0]["po_number"] == ""


def test_source_absence_does_not_acquire_country_standard_or_label_from_other_words():
    text = PAGE_ONE + "\fDelivery Date: on Jul 21st 2028.\nDestination & Shipping: Costco Wholesale\nIncoterms: FOB Example Port"
    line, = parse(text)["lines"]
    assert line["country"] == ""  # Buyer address says USA, which is not the destination.
    assert line["standard"] == ""
    assert not line.get("color_box", "").startswith("USA")
    assert not line.get("box_mark") and not line.get("label")
    assert not line.get("date_code")


def test_words_amount_conflict_warns_without_changing_numeric_source():
    text = costco_text().replace("Five Hundred Eighty-five Dollars", "Six Hundred Eighty-five Dollars")
    result = parse(text)
    line, = result["lines"]
    assert (line["quantity"], line["unit_price"], line["amount"]) == (180, 3.25, 585)
    assert line["amount_words_conflict"] is True
    warning = next(value for value in line["source_warnings"] if "金额大写" in value)
    assert "USD 685.00" in warning and "USD 585.00" in warning
    assert "人工核对原单" in warning
    assert warning in result["warnings"]
    assert result["confidence"] == "low"
    assert line["source_lineage"]["amount_words"]["page"] == 1


@pytest.mark.parametrize("words,expected", [
    ("Sixteen Thousand Two Hundred Thirty-four Dollars and Fifty-six Cents.", 1623456),
    ("Sixty Thousand Two Hundred Thirty-four Dollars and Fifty-six Cents.", 6023456),
    ("One Thousand and Five Dollars", 100500),
    ("Zero Dollars and Five Cents.", 5),
    ("Five hundred twenty twenty Dollars", None),
    ("Five Hundred Dollars and One Hundred Cents.", None),
    ("Amount to be confirmed", None),
    ("Five Hundred Dollars pending review", None),
])
def test_words_currency_parser_is_bounded_and_requires_complete_text(words, expected):
    assert parser._shushupapa_amount_words(words) == expected


def legacy_text(customer, packing):
    return f"""SHUSHUPAPA
PO Number: 2098-0801
Issue Date: June 8, 2028
{customer}
Item # Description Quantity Unit Price Casepack Total Amount
87654329 Example Mixed Figures 40 pcs $2.00 {packing} USD$80.00
Total Order Value: Eighty Dollars.
Terms and Conditions
on or before July 21, 2028
"""


@pytest.mark.parametrize("customer", ["PRICESMART", "Price Smart"])
def test_legacy_pricesmart_mixed_carton_rule_is_preserved(customer):
    text = legacy_text(customer, "4-Vader + 2-Trooper") + "PriceSmart PO Number: TEST-8401\n"
    result = parse(text)
    line, = result["lines"]
    assert result["customer"] == "Price Smart"
    assert result["customer_po"] == "TEST-8401"
    assert result["ship_date"] == "2028-07-21"
    assert (line["inner_pack"], line["outer_pack"], line["cartons"], line["external_quantity"]) == (4, 4, 10, 20)
    assert line["description"] == "Example Mixed Figures"
    assert "外厂：2PCS" in line["shipment_note"]


@pytest.mark.parametrize("customer,packing,outer", [
    ("PRICESMART", "4-Vader + 2-Trooper", 4),
    ("BJS CDU", "4 PCS DARTH + 2 PCS STORM", 6),
])
def test_explicit_master_carton_checks_physical_mix_without_changing_schedule_pack(customer, packing, outer):
    text = legacy_text(customer, packing) + "Master Carton Packed with 6 pcs.\n"
    line, = parse(text)["lines"]
    assert (line["inner_pack"], line["outer_pack"], line["cartons"], line["external_quantity"]) == (4, outer, 10, 20)
    assert line["source_lineage"]["outer_pack"]["raw_text"] == packing
    assert line["source_lineage"]["master_carton"]["raw_text"] == "Master Carton Packed with 6 pcs"


@pytest.mark.parametrize("customer,packing", [
    ("PRICESMART", "4-Vader + 2-Trooper"),
    ("BJS CDU", "4 PCS DARTH + 2 PCS STORM"),
])
def test_explicit_master_carton_rejects_actual_mixed_total_conflict(customer, packing):
    text = legacy_text(customer, packing) + "Master Carton Packed with 7 pcs.\n"
    with pytest.raises(ValueError, match="混装比例与 Master Carton.*冲突"):
        parse(text)


def test_legacy_bjs_mixed_shipments_keep_sort_and_factory_quantity():
    text = legacy_text("BJS CDU", "4 PCS DARTH + 2 PCS STORM") + "20/07/2028 4\n19/07/2028 6\n"
    result = parse(text)
    assert result["customer"] == "BJs"
    assert [line["po_number"] for line in result["lines"]] == ["2098-0801-1", "2098-0801-2"]
    assert [line["ship_date"] for line in result["lines"]] == ["2028-07-19", "2028-07-20"]
    assert [line["quantity"] for line in result["lines"]] == [24, 16]
    assert [line["external_quantity"] for line in result["lines"]] == [12, 8]
    assert [line["cartons"] for line in result["lines"]] == [6, 4]
    assert all(line["inner_pack"] == 4 and line["outer_pack"] == 6 for line in result["lines"])
    assert [line["amount"] for line in result["lines"]] == [48, 32]


@pytest.mark.parametrize("first_count,second_count", [("1,000", "1,000"), ("1000", "1,000")])
def test_bjs_thousands_separators_preserve_all_shipments_and_their_dates(first_count, second_count):
    text = legacy_text("BJS CDU", "4 PCS DARTH + 2 PCS STORM")
    text = text.replace("40 pcs", "8000 pcs").replace("USD$80.00", "USD$16000.00")
    text = text.replace("Eighty Dollars.", "Sixteen Thousand Dollars.")
    text += f"20/07/2028 {first_count}\n19/07/2028 {second_count}\n"
    result = parse(text)
    assert [line["po_number"] for line in result["lines"]] == ["2098-0801-1", "2098-0801-2"]
    assert [line["ship_date"] for line in result["lines"]] == ["2028-07-19", "2028-07-20"]
    assert [line["quantity"] for line in result["lines"]] == [4000, 4000]
    assert [line["cartons"] for line in result["lines"]] == [1000, 1000]
    assert [line["external_quantity"] for line in result["lines"]] == [2000, 2000]
    assert [line["amount"] for line in result["lines"]] == [8000, 8000]


@pytest.mark.parametrize("customer,packing,outer", [
    ("BJS CDU", "4 PCS DARTH + 2 PCS STORM", 6),
    ("PRICESMART", "4-Vader + 2-Trooper", 4),
])
def test_existing_excel_mixed_packing_stays_unchanged(customer, packing, outer):
    rows = [
        ["Item #", "Description", "Quantity", "Unit Price", "Casepack", "Total Amount"],
        ["87654329", "Example Mixed Figures", 40, 2, packing, 80],
    ]
    result = parser._parse_shushupapa_excel(rows, legacy_text(customer, packing), "example.xlsx")
    line, = result["lines"]
    assert line["outer_pack"] == outer
    assert line["quantity"] == 40 and line["cartons"] == 10 and line["external_quantity"] == 20


def test_native_pdf_reread_is_shushupapa_only_and_preserves_page_evidence(monkeypatch):
    calls = []

    def read(source, **kwargs):
        assert source == b"synthetic-pdf"
        calls.append(kwargs)
        if kwargs:
            return [PAGE_ONE, PAGE_TWO], False
        return ["SHUSHUPAPA\nMerged native text", "Native terms"], False

    monkeypatch.setattr(parser, "read_pdf_pages", read)
    result = parser.parse_po(io.BytesIO(b"synthetic-pdf"), "example.pdf")
    assert calls == [{}, {"x_tolerance": 1, "y_tolerance": 1}]
    assert result["lines"][0]["source_lineage"]["outer_pack"]["page"] == 2
    assert result["customer_po"] == "801-9999-121"


def test_other_native_customer_keeps_existing_text_tolerance(monkeypatch):
    calls = []

    def read(source, **kwargs):
        calls.append(kwargs)
        return ["MAXX MARKETING example PO"], False

    monkeypatch.setattr(parser, "read_pdf_pages", read)
    monkeypatch.setattr(parser, "_parse_maxx", lambda text, name, pages: {"po_number": "EXAMPLE", "lines": [], "warnings": []})
    parser.parse_po(b"synthetic-pdf", "example.pdf")
    assert calls == [{}]


def test_scanned_shushupapa_uses_existing_bounded_ocr_result_without_native_reread(monkeypatch):
    calls = []

    def read(source, **kwargs):
        calls.append(kwargs)
        return [PAGE_ONE, PAGE_TWO], True

    monkeypatch.setattr(parser, "read_pdf_pages", read)
    result = parser.parse_po(b"synthetic-scan", "example.pdf")
    assert calls == [{}]
    assert result["lines"][0]["outer_pack"] == 12


def test_pdf_reader_optional_tolerances_leave_defaults_and_limits_unchanged(monkeypatch):
    calls = []

    class Page:
        def extract_text(self, **kwargs):
            calls.append(kwargs)
            return PAGE_ONE

    class PDF:
        pages = [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(parser.pdfplumber, "open", lambda _: PDF())
    parser.read_pdf_pages(b"synthetic")
    parser.read_pdf_pages(b"synthetic", x_tolerance=1, y_tolerance=1)
    assert calls == [{"x_tolerance": 2, "y_tolerance": 3}, {"x_tolerance": 1, "y_tolerance": 1}]
    with pytest.raises(ValueError, match="最多支持"):
        parser.read_pdf_pages(b"synthetic", max_pages=0, x_tolerance=1, y_tolerance=1)
    assert len(calls) == 2
