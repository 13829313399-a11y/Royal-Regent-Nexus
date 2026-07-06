import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_carton_mark_auto_check_extracts_template_fields_and_requests_photo_review():
    from app.services.carton_mark import build_carton_mark_auto_check

    response = build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"NUMERO DE PEDIDO 203302017\n"
            b"ITEM 700142617\n"
            b"G.W. 4.3 KGS\n"
            b"N.W. 3.1 KGS\n"
            b"BARCODE 197919619\n"
        ),
        front_image_bytes=b"not-an-image",
        side_image_bytes=b"not-an-image",
        customer_name="Dicky",
        po="203302017",
        item="700142617",
    )

    template_fields = {field.key: field.value for field in response.template_fields}
    front_template_fields = {field.key: field.value for field in response.front_template_fields}
    side_template_fields = {field.key: field.value for field in response.side_template_fields}
    assert template_fields["customer_name"] == "Dicky"
    assert template_fields["po"] == "203302017"
    assert template_fields["item"] == "700142617"
    assert template_fields["barcode"] == "197919619"
    assert front_template_fields["po"] == "203302017"
    assert side_template_fields["item"] == "700142617"

    assert response.summary.overall_status == "需复核"
    assert response.summary.review_count > 0
    assert any(item.side == "front" and item.field_key == "po" and item.status == "review" for item in response.comparisons)
    assert any(status.source == "front_photo" and not status.ok for status in response.extraction)


def test_carton_mark_field_extraction_handles_noisy_photo_ocr_rows():
    from app.services.carton_mark import extract_fields

    fields = {
        field.key: field.value
        for field in extract_fields(
            (
                "P.0 N0 | 2033 | ITEM N0 | 2017\n"
                "QTY/CTN 24 PCS\n"
                "G W 4.3 KGS\n"
                "N W 3.1 KGS\n"
                "C/NO 1-10\n"
            ),
            source="front_photo",
        )
    }

    assert fields["po"] == "2033"
    assert fields["item"] == "2017"
    assert fields["quantity"] == "24"
    assert fields["gw"] == "4.3 KGS"
    assert fields["nw"] == "3.1 KGS"
    assert fields["carton_no"] == "1-10"


def test_carton_mark_auto_check_matches_photo_raw_values_when_labels_are_noisy(monkeypatch):
    from app.schemas.carton_mark import CartonMarkExtractionStatus
    from app.services import carton_mark

    def fake_extract_image_text(image_bytes: bytes, *, source: str):
        return "photo text only 2033 2017 197919619", CartonMarkExtractionStatus(
            source=source,
            ok=True,
            engine="test",
            message="",
            raw_text="photo text only 2033 2017 197919619",
        )

    monkeypatch.setattr(carton_mark, "extract_image_text", fake_extract_image_text)

    response = carton_mark.build_carton_mark_auto_check(
        pdf_bytes=(
            b"SHIPPING IDENTIFICATION MARK\n"
            b"PO 2033\n"
            b"ITEM 2017\n"
            b"BARCODE 197919619\n"
        ),
        front_image_bytes=b"front-photo",
        side_image_bytes=b"side-photo",
        customer_name="Dicky",
        po="2033",
        item="2017",
    )

    front_statuses = {
        item.field_key: item.status
        for item in response.comparisons
        if item.side == "front"
    }
    assert front_statuses["po"] == "pass"
    assert front_statuses["item"] == "pass"
    assert front_statuses["barcode"] == "pass"
