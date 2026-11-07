"""Synthetic regressions for the Silverlit November PDF feedback."""
from datetime import date

import pytest

from app.services.huaxing_order_legacy import yinhui_po_parser as parser
from app.services.huaxing_order_legacy.yinhui_schedule import add_derived_fields


HEADER = """Page: 1 of 1
PURCHASE ORDER: TEST-900001
Date (YMD): 2026.11.01
ITEM# PART# DESCRIPTION DELI.(YMD) QTY UNIT PRICE AMOUNT
"""


def parse(monkeypatch, body, *, ocr=True, remarks=""):
    text = HEADER + body + ("\nRemarks:\n" + remarks if remarks else "")
    monkeypatch.setattr(parser, "_pdf_text", lambda source: (text, 1, ocr))
    return parser.parse_pdf(b"synthetic", "test.pdf")


def three_lines():
    return """00010 ALPHA-11 TOY EDITION 2027.01.20 24 PCS 5.0000 120.00
Packaging: WINDOW BOX PR:3000000001
Color/Style: BLUE S0O:2300000001 -10
Packing (Inner/Outer): 0/8
Name:TEST CUSTOMER
00020 BETA-22 54PCS DISPLAY W/TRY- 2027.01.20 2 POP 9.0000 18.00
ME PR:3000000002
Packaging: POP s50:2300000001 -20
Packing (Inner/Outer): 0/1
00030 GAMMA-33 TOY STUDIO EDITION —2027.01.20 12 PCS 3.0000 36.00
Packaging: WINDOW BOX PR:3000000003
Color/Style: RED $S0O:2300000001 -30
Packing (Inner/Outer): 0/4
Total: 174.00
**SAY: USD ONE HUNDRED SEVENTY-FOUR DOLLARS AND ZERO CENTS ONLY**
"""


def test_ocr_pop_and_rule_before_date_keep_all_details_and_their_own_pack(monkeypatch):
    result = parse(monkeypatch, three_lines())
    rows = result["rows"]
    assert [row["item_no"] for row in rows] == ["ALPHA-11", "BETA-22", "GAMMA-33"]
    assert [row["quantity"] for row in rows] == [24, 2, 12]
    assert [row["quantity_unit"] for row in rows] == ["PCS", "POP", "PCS"]
    assert [row["case_pack"] for row in rows] == [8, 1, 4]
    assert [row["cartons"] for row in rows] == [3, 2, 3]
    assert [row["total_usd"] for row in rows] == [120, 18, 36]
    assert all(row["so_no"] == "2300000001" for row in rows)
    assert all(row["inspection_date"] == "2027-01-15" for row in rows)
    assert rows[2]["product_name"] == "TOY STUDIO EDITION"
    assert any("2 POP" in warning for warning in result["warnings"])
    assert not any("金额校验不符" in warning for warning in result["warnings"])


@pytest.mark.parametrize("change", [
    ("2 POP", "2 KGM"),
    ("—2027.01.20", "2027.0I.20"),
    ("9.0000 18.00", "?.???? 18.00"),
])
def test_unparsed_numbered_detail_blocks_partial_order(monkeypatch, change):
    with pytest.raises(ValueError, match="有明细行未完整识别.*不能只导出已识别行"):
        parse(monkeypatch, three_lines().replace(*change))


def test_native_text_does_not_silently_rewrite_dash_before_date(monkeypatch):
    with pytest.raises(ValueError, match="00030 / GAMMA-33"):
        parse(monkeypatch, three_lines(), ocr=False)


def test_native_pop_is_supported_without_quantity_conversion(monkeypatch):
    result = parse(monkeypatch, three_lines().replace("—2027", "2027"), ocr=False)
    assert result["rows"][1]["quantity"] == 2
    assert result["rows"][1]["quantity_unit"] == "POP"
    assert all(not row.get("source_review_flags") for row in result["rows"])


@pytest.mark.parametrize("ocr", [True, False])
def test_explicit_single_item_remark_pack_conflict_is_retained_for_preview(monkeypatch, ocr):
    result = parse(monkeypatch, """00010 ALPHA-11 TOY 2027.01.20 24 PCS 5.0000 120.00
SO:2300000001 -10
Packing (Inner/Outer): 0/12
Name:TEST CUSTOMER
Total: 120.00
""", ocr=ocr, remarks="R02) 产品要求跟工程签板；6pcs/ctn\nTerms and Conditions:")
    row = result["rows"][0]
    assert row["case_pack"] == 12  # No automatic choice of the conflicting 6.
    flags = row["source_review_flags"]
    conflict = next(flag for flag in flags if flag["code"] == "case_pack_source_conflict")
    assert conflict["severity"] == "blocked"
    assert conflict["field"] == "units_per_carton"
    assert "12" in conflict["text"] and "6 PCS/CTN" in conflict["text"]
    add_derived_fields(row, today=date(2026, 11, 1))
    assert row["source_review_flags"] == flags
    assert (any(flag["code"] == "ocr_case_pack_review" for flag in flags)) == ocr


def test_multi_item_remarks_need_exact_item_scope_and_ignore_auxiliary_rows(monkeypatch):
    result = parse(monkeypatch, three_lines(), remarks="""Generic 6pcs/ctn
For ALPHA-11 8pcs/ctn
For BETA-22 3pcs/ctn
For GAMMA-333 9pcs/ctn
For ALPHA-11-2 9pcs/ctn
00010 NOT-ORDER barcode row should not become a PO detail
Terms and Conditions:
""")
    conflicts = [row["item_no"] for row in result["rows"]
                 if any(flag["code"] == "case_pack_source_conflict" for flag in row["source_review_flags"])]
    assert conflicts == ["BETA-22"]
    assert len(result["rows"]) == 3


@pytest.mark.parametrize("ocr", [True, False])
def test_continuation_details_after_page_local_remarks_are_not_truncated(monkeypatch, ocr):
    page_break = "<<OCR_PAGE_BREAK>>" if ocr else ""
    result = parse(monkeypatch, f"""00010 ALPHA-11 TOY 2027.01.20 24 PCS 5.0000 120.00
SO:2300000001 -10
Packing (Inner/Outer): 0/12
Name:TEST CUSTOMER
Remarks:
00010 NOT-ORDER barcode row in a remark
Terms and Conditions:
{page_break}
Page: 2 of 2
ITEM# PART# DESCRIPTION DELI.(YMD) QTY UNIT PRICE AMOUNT
00020 BETA-22 TOY 2027.01.20 12 PCS 3.0000 36.00
SO:2300000002 -20
Packing (Inner/Outer): 0/4
Total: 156.00
Remarks:
00020 NOT-ORDER barcode row in second remark
""", ocr=ocr)
    assert [row["item_no"] for row in result["rows"]] == ["ALPHA-11", "BETA-22"]
    assert [row["so_no"] for row in result["rows"]] == ["2300000001", "2300000002"]
    assert [row["case_pack"] for row in result["rows"]] == [12, 4]


def test_amount_mismatches_are_still_reported(monkeypatch):
    result = parse(monkeypatch, three_lines().replace("3.0000 36.00", "3.0000 35.00"))
    assert any("数量×单价" in warning for warning in result["warnings"])
    assert any("大写金额校验不符" in warning for warning in result["warnings"])


def test_postal_address_before_table_is_not_an_unread_order(monkeypatch):
    text = HEADER.replace("ITEM#", "12345 BERLIN GERMANY\nITEM#") + three_lines()
    monkeypatch.setattr(parser, "_pdf_text", lambda source: (text, 1, True))
    assert len(parser.parse_pdf(b"synthetic", "test.pdf")["rows"]) == 3


@pytest.mark.parametrize("ocr", [True, False])
def test_missing_table_header_still_reads_financial_detail(monkeypatch, ocr):
    text = HEADER.split("ITEM#")[0] + "01234 BERLIN GERMANY\n" + three_lines().replace("—2027", "2027")
    monkeypatch.setattr(parser, "_pdf_text", lambda source: (text, 1, ocr))
    assert len(parser.parse_pdf(b"synthetic", "test.pdf")["rows"]) == 3


@pytest.mark.parametrize("ocr", [True, False])
def test_second_page_with_damaged_header_cannot_be_silently_ignored(monkeypatch, ocr):
    page = "<<OCR_PAGE_BREAK>>" if ocr else "Page: 2 of 2"
    text = HEADER + three_lines().replace("—2027", "2027") + f"""Remarks:
Auxiliary barcode 12345
{page}
damaged table heading
00040 DELTA-44 TOY 2027.01.20 12 PCS 3.0000 36.00
SO:2300000002 -40
Packing (Inner/Outer): 0/4
Total: 36.00
"""
    monkeypatch.setattr(parser, "_pdf_text", lambda source: (text, 2, ocr))
    rows = parser.parse_pdf(b"synthetic", "test.pdf")["rows"]
    assert [row["item_no"] for row in rows] == ["ALPHA-11", "BETA-22", "GAMMA-33", "DELTA-44"]


def test_financial_detail_after_remarks_without_page_evidence_blocks_partial_export(monkeypatch):
    with pytest.raises(ValueError, match="无法确认明细分区"):
        parse(monkeypatch, three_lines(), remarks="00040 DELTA-44 TOY 2027.01.20 12 PCS 3.0000 36.00")


@pytest.mark.parametrize("text", ["", "PURCHASE ORDER: TEST-900001\nUnreadable table"])
def test_no_rows_is_an_error_so_batch_cannot_skip_unread_source(monkeypatch, text):
    monkeypatch.setattr(parser, "_pdf_text", lambda source: (text, 1, True))
    with pytest.raises(ValueError, match="本批不能忽略此文件继续导出"):
        parser.parse_pdf(b"synthetic", "test.pdf")


def test_so_label_tolerance_does_not_match_embedded_item_text():
    assert parser._so_no("Packaging: POP s50:2300000001 -20") == "2300000001"
    assert parser._so_no("AS50:2300000001") is None
