from io import BytesIO
from zipfile import ZipFile

import pytest
from reportlab.pdfgen.canvas import Canvas

from app.services.pdf_rename import qwen
from app.services.pdf_rename.contracts import PdfRenameSource
from app.services.pdf_rename.registry import list_pdf_rename_rules
from app.services.pdf_rename.service import execute_registered_pdf_rename_batch, preview_registered_pdf_rename_batch
from test_pdf_rename_qwen import cloud, response


def booking_pdf(number, label="EI Booking No."):
    output = BytesIO()
    page = Canvas(output, pagesize=(600, 800))
    page.drawString(18, 750, "EXPEDITORS CARGO MANAGEMENT SYSTEMS")
    page.drawString(18, 710, "Shipper")
    page.drawString(294, 710, label)
    page.drawString(410, 710, "Pickup Location")
    page.drawString(294, 693, number)
    page.drawString(410, 693, "A0099")
    page.drawString(294, 665, "Notes:")
    page.drawString(294, 648, "BY379951")
    page.showPage()
    page.drawString(294, 710, "EI Booking No. S000000001")
    page.save()
    return output.getvalue()


@pytest.mark.parametrize("number", ["S1N3059162", "00001234", "Ab-0027"])
def test_registered_shipping_so_renames_entire_original_pdf(monkeypatch, number):
    monkeypatch.setattr(qwen, "qwen_enabled", lambda: False)
    assert any(rule["label"] == "船务部SO" for rule in list_pdf_rename_rules("huaxing"))
    source = PdfRenameSource("unrelated.pdf", booking_pdf(number))
    preview = preview_registered_pdf_rename_batch("shipping-so", (source,), factory_id="huaxing")
    assert preview.ready_count == 1
    assert preview.items[0].target_file_name == f"SO-{number}.pdf"
    result = execute_registered_pdf_rename_batch(
        "shipping-so", (source,), factory_id="huaxing", expected_preview_token=preview.preview_token,
    )
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.namelist() == [f"SO-{number}.pdf"]
        assert archive.read(archive.namelist()[0]) == source.content


@pytest.mark.parametrize(("label", "number"), [
    ("EI Booking No.", ""), ("Booking Ref.", "S1N3059162"),
    ("EI Booking No.", "S1N3059162 X123"), ("EI Booking No.", "S1N/3059162"),
])
def test_missing_or_ambiguous_booking_number_blocks_automatic_rename(monkeypatch, label, number):
    monkeypatch.setattr(qwen, "qwen_enabled", lambda: False)
    source = PdfRenameSource("SO-S1N3059162.pdf", booking_pdf(number, label))
    preview = preview_registered_pdf_rename_batch("shipping-so", (source,), factory_id="huaxing")
    assert preview.error_count == 1
    assert not preview.items[0].target_file_name


@pytest.mark.parametrize("uncertain", [False, True])
def test_cloud_booking_read_requires_unambiguous_labelled_value(monkeypatch, cloud, uncertain):
    def recognize(_settings, _image, **kwargs):
        assert "EI Booking No." in kwargs["prompt"]
        return response(["EI Booking No.: S1N3059162"], ["ei_booking_no"] if uncertain else [])

    monkeypatch.setattr(qwen.qwen_ocr, "recognize", recognize)
    source = PdfRenameSource("scan.pdf", booking_pdf("S1N3059162"))
    preview = preview_registered_pdf_rename_batch("shipping-so", (source,), factory_id="huaxing")
    assert preview.items[0].target_file_name == ("" if uncertain else "SO-S1N3059162.pdf")
    assert preview.items[0].status == ("ERROR" if uncertain else "READY")
