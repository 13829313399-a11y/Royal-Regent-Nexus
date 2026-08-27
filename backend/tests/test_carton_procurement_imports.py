from decimal import Decimal
from io import BytesIO

import pillow_heif
from PIL import Image

from app.services.carton_procurement_imports import (
    DeliveryOcrWord,
    _delivery_rows_from_ocr_words,
    _register_heic_opener,
)


def _word(text: str, x: int, y: int, width: int = 120, height: int = 24) -> DeliveryOcrWord:
    return DeliveryOcrWord(
        text=text,
        left=x - width // 2,
        top=y - height // 2,
        right=x + width // 2,
        bottom=y + height // 2,
        confidence=0.99,
    )


def test_delivery_note_table_maps_four_columns_and_keeps_dn_out_of_order_rows() -> None:
    words = [
        _word("DN26061301", 2200, 40),
        _word("26/06/13", 2100, 70),
        _word("订单编号", 400, 100),
        _word("PONO", 400, 125),
        _word("DESCRIPTION", 850, 125),
        _word("SPECIFICATION", 1350, 125),
        _word("数", 1680, 100, 30),
        _word("量", 1810, 100, 30),
        _word("单价", 2000, 100, 80),
        _word("So700145011/3500-20330203", 390, 185, 420),
        _word("8", 390, 215, 20),
        _word("普通箱", 780, 200, 100),
        _word("A33+B", 930, 200, 90),
        _word("31.5 x 11.125 x 11.25", 1330, 200, 320),
        _word("inch", 1590, 200, 60),
        _word("6", 1745, 200, 30),
        _word("合计", 2000, 350, 80),
    ]

    parsed = _delivery_rows_from_ocr_words(words)

    assert parsed is not None
    assert parsed["delivery_note_no"] == "DN26061301"
    assert parsed["delivery_date"] == "2026-06-13"
    assert len(parsed["rows"]) == 1
    row = parsed["rows"][0]
    assert row["order_reference"] == "SC700145011/3500-203302038"
    assert row["contract_no"] == "SC700145011/3500"
    assert row["item_no"] == "203302038"
    assert row["packaging_type"] == "普通箱"
    assert row["paper_quality"] == "A33+B"
    assert row["specification"] == "31.5 × 11.125 × 11.25 in"
    assert Decimal(str(row["delivered_quantity"])) == Decimal("6")
    assert row["contract_no"] != "DN26061301"


def test_delivery_note_table_keeps_unreadable_order_as_review_row() -> None:
    words = [
        _word("订单编号", 400, 100),
        _word("DESCRIPTION", 850, 125),
        _word("SPECIFICATION", 1350, 125),
        _word("数", 1680, 100, 30),
        _word("量", 1810, 100, 30),
        _word("单价", 2000, 100, 80),
        _word("普通箱", 780, 200, 100),
        _word("B3B", 930, 200, 70),
        _word("15.5 x 10.625 x 5.25", 1330, 200, 300),
        _word("24", 1745, 200, 40),
        _word("TOTAL", 2000, 350, 80),
    ]

    parsed = _delivery_rows_from_ocr_words(words)

    assert parsed is not None
    assert len(parsed["rows"]) == 1
    row = parsed["rows"][0]
    assert row["contract_no"] == ""
    assert row["item_no"] == ""
    assert row["paper_quality"] == "B3B"
    assert Decimal(str(row["delivered_quantity"])) == Decimal("24")


def test_heic_opener_decodes_an_uploaded_phone_photo() -> None:
    encoded = BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (8, 6), color=(82, 151, 146))).save(encoded)

    _register_heic_opener()

    with Image.open(BytesIO(encoded.getvalue())) as decoded:
        assert decoded.format == "HEIF"
        assert decoded.size == (8, 6)
