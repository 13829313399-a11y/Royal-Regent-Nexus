"""Synthetic Barter contract text preserves the observed OCR error shapes."""
from PIL import Image
import pytest

from app.services.huaxing_order_legacy import multi_po_parser as parser


@pytest.mark.parametrize("source,expected", [
    ("PLEASE APPLY DATE CODE WM88111RR-1026 TO BOTH ON PRODUCT", "WM88111RR-1026"),
    ("PLEASE APPLY DATE CODE WM8B111 RR–1O26TO BOTH ON PRODUCT", "WM88111RR-1026"),
    ("DATE CODE: RR-1 O 2 6 TO BOTH ON PRODUCT", "WM88111RR-1026"),
    ("DATE C0DE RR-1026", "WM88111RR-1026"),
    ("PLEASE APPLY DATE CODE WM88111RR-!?26TO BOTH ON PRODUCT", ""),
    ("PLEASE APPLY DATE CODE WM88111RR-/o 26 TO BOTH ON PRODUCT", ""),
    ("PLEASE APPLY DATE CODE WM88111RR-;0 2.4 TO BOTH ON PRODUCT", ""),
    ("DATE CODE WM88111RR-026 TO BOTH ON PRODUCT", ""),
    ("DATE CODE WM88111RR-10260 TO BOTH ON PRODUCT", ""),
    ("DATE CODE WM87111RR-1026 TO BOTH ON PRODUCT", ""),
    ("DATE CODE WM88111RR-1026\nDATE CODE WM88111RR-1126", ""),
])
def test_date_code_uses_only_unique_explicit_digits(source, expected):
    assert parser._barter_date_code(source, "88111") == expected


@pytest.mark.parametrize("product_line,cartons,quantity,amount", [
    ("88111 - SAMPLE TOY 100 PCS _12.3450/PCS - 1,234.50 一", 20, 100, 1234.5),
    ("88111 7 SAMPLE TOY 150 PCS 12.3450/PCS - 1,851.75", 30, 150, 1851.75),
    ("88111 SAMPLE TOY 200 PCS (12.3450/PCS, 2,469.00", 40, 200, 2469.0),
    ("88111 - SAMPLE TOY 250 PCS 12.3450/PCS _ 3,086.25", 50, 250, 3086.25),
])
def test_printed_financial_fields_survive_scan_markings(product_line, cartons, quantity, amount):
    line, warnings = parser._parse_barter_page(
        f"""PURCHASE CONTRACT CONTRACT #: TNT/F90701
DELIVERY :OCT 12, 2026
CUSTOMER :WAL-MART USA (0100000001)
{product_line}
({cartons} CTN)
5 PC PER MASTER
PLEASE APPLY DATE CODE WM88111RR-!?26TO BOTH ON PRODUCT & PACKAGING.
""",
        page_number=1, expected_contract=None, ocr_used=True,
    )
    assert line["quantity"] == quantity
    assert line["unit_price"] == 12.345
    assert line["amount"] == amount
    assert line["date_code"] == ""
    assert not warnings


HEADER = """PURCHASE CONTRACT CONTRACT #: TNT/F90701
DELIVERY :OCT 12, 2026
CUSTOMER :WAL-MART USA (0100000001)
"""


@pytest.mark.parametrize("dense,expected_calls", [
    (HEADER, 1),
    (HEADER.replace("90701", "9O701"), 2),
    (HEADER.replace("0100000001", "O100000001"), 2),
    (HEADER.replace("0100000001", "0980000009"), 2),
    (HEADER.replace("OCT 12, 2026", "OCF 12, 2026"), 2),
    (HEADER + "CUSTOMER :WAL-MART USA (0100000002)", 2),
    ("MAXX PURCHASE ORDER 90701", 2),
])
def test_complete_barter_header_avoids_redundant_ocr_only_when_unambiguous(dense, expected_calls):
    calls = []

    class Engine:
        @staticmethod
        def image_to_string(image, **kwargs):
            calls.append(kwargs)
            return dense if len(calls) == 1 else "sparse fallback"

    with Image.new("RGB", (100, 100), "white") as image:
        result = parser._ocr_contract_page(Engine, image, "eng")
    assert len(calls) == expected_calls
    expected = dense if expected_calls == 1 else dense + "\nsparse fallback"
    assert result == expected
    assert calls[0]["timeout"] == 30
    if expected_calls == 2:
        assert calls[1]["timeout"] == 15
