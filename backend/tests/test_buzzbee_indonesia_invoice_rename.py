from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

from app.services.pdf_rename import ocr, qwen
from app.services.pdf_rename.contracts import (
    PdfRenameServiceError, PdfRenameSource, RecognizedRegionValue,
)
from app.services.pdf_rename.registry import list_pdf_rename_rules
from app.services.pdf_rename.rules.buzzbee_indonesia_invoice import BuzzBeeIndonesiaInvoiceRule
from app.services.pdf_rename.service import build_pdf_rename_preview, execute_pdf_rename_batch
from test_buzzbee_pdf_rename import pdf
from test_pdf_rename_qwen import cloud, response


def reading(number="104753", header="BUZZ BEE TOYS (HK)CO. LTD. INVOICE", route="LOCAL_OCR"):
    def recognize(_data, region):
        text = header if region.key == "invoice_header" else number
        return RecognizedRegionValue(region.key, region.label, text, text, route, .8 if route == "LOCAL_OCR" else None)
    return recognize


def invoice_image():
    # A black prefix and a competing black number must not enter transcription.
    image = Image.new("RGB", (1200, 1680), "white")
    draw = ImageDraw.Draw(image)
    draw.text((880, 245), "A 999999", fill="black")
    draw.text((1010, 245), "104753", fill=(255, 60, 80))
    output = BytesIO()
    image.save(output, format="PDF", resolution=144)
    return output.getvalue()


def test_catalog_exposes_invoice_rule_only_in_huaxing():
    rule = next(r for r in list_pdf_rename_rules("huaxing") if r["id"] == "buzzbee-indonesia-invoice")
    assert rule["label"] == "BuzzBee印尼发票" and rule["available"]
    assert not list_pdf_rename_rules("huakang-a")


@pytest.mark.parametrize("number", ["104753", "000123", "1 0 4 7 5 3"])
def test_invoice_name_preserves_digits_and_requires_local_review(number):
    plan = BuzzBeeIndonesiaInvoiceRule().create_plan(PdfRenameSource("客发票--999999.pdf", pdf()), reading(number))
    assert plan.target_file_name == "客发票--" + number.replace(" ", "") + ".pdf"
    assert plan.status == "REVIEW"


@pytest.mark.parametrize("number", ["A104753", "10475", "1047537", "1O4753", "104753\n104754", "", "104/753"])
def test_uncertain_numbers_cannot_be_guessed_from_filename(number):
    plan = BuzzBeeIndonesiaInvoiceRule().create_plan(PdfRenameSource("客发票--104753.pdf", pdf()), reading(number))
    assert plan.status == "ERROR" and not plan.target_file_name


@pytest.mark.parametrize("header", ["BUZZ BEE TOYS INSPECTION REPORT", "OTHER COMPANY INVOICE"])
def test_wrong_document_type_is_blocked(header):
    plan = BuzzBeeIndonesiaInvoiceRule().create_plan(PdfRenameSource("invoice.pdf", pdf()), reading(header=header))
    assert plan.status == "ERROR"


def test_invoice_zip_preserves_original_pdf_and_duplicate_numbers_are_blocked():
    rule = BuzzBeeIndonesiaInvoiceRule()
    sources = (PdfRenameSource("unrelated.pdf", pdf()),)
    preview = build_pdf_rename_preview(rule, sources, recognizer=reading())
    with pytest.raises(PdfRenameServiceError):
        execute_pdf_rename_batch(rule, sources, expected_preview_token=preview.preview_token, recognizer=reading())
    result = execute_pdf_rename_batch(rule, sources, expected_preview_token=preview.preview_token,
                                     recognizer=reading(), ocr_review_confirmed=True)
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.namelist() == ["客发票--104753.pdf"]
        assert archive.read("客发票--104753.pdf") == sources[0].content
    duplicate = build_pdf_rename_preview(rule, sources * 2, recognizer=reading())
    assert duplicate.error_count == 2


def test_red_filter_removes_black_and_blue_ink_and_rejects_missing_red():
    image = Image.new("RGB", (5, 1), "white")
    for x, color in enumerate([(0, 0, 0), (255, 60, 80), (160, 60, 65), (60, 80, 255)]):
        image.putpixel((x, 0), color)
    mask = ocr.isolate_red_text(image)
    assert [mask.getpixel((x + 12, 12)) for x in range(5)] == [255, 0, 0, 255, 255]
    with pytest.raises(PdfRenameServiceError) as error:
        ocr.isolate_red_text(Image.new("RGB", (20, 20), "black"))
    assert error.value.code == "PDF_RENAME_REGION_EMPTY"


def test_local_ocr_uses_only_red_pixels_even_with_hidden_text(monkeypatch):
    import pytesseract

    monkeypatch.setattr(qwen, "qwen_enabled", lambda: False)
    monkeypatch.setattr(ocr, "configure_tesseract", lambda _module: ("test-command", "eng"))
    monkeypatch.setattr(pytesseract, "get_languages", lambda **_kwargs: ["eng"])
    crops = []
    monkeypatch.setattr(pytesseract, "image_to_string", lambda image, **_kwargs: crops.append(image.copy()) or "104753")
    value = ocr.recognize_fixed_region(invoice_image(), BuzzBeeIndonesiaInvoiceRule.definition.regions[1])
    assert value.route == "LOCAL_OCR" and value.normalized_text == "104753"
    assert crops[0].mode == "L"
    assert crops[0].getextrema() == (0, 255)
    # The left part of the crop contained the black prefix/competing number.
    assert crops[0].crop((12, 12, 200, crops[0].height - 12)).getextrema() == (255, 255)


def test_cloud_filters_red_before_transcription_and_reuses_result(cloud, monkeypatch):
    provider = Mock(side_effect=[response(["BUZZ BEETOYS INVOICE"]), response(["104753"])])
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    sources = (PdfRenameSource("unrelated.pdf", invoice_image()),)
    rule = BuzzBeeIndonesiaInvoiceRule()
    preview = build_pdf_rename_preview(rule, sources)
    assert preview.ready_count == 1
    assert preview.items[0].target_file_name == "客发票--104753.pdf"
    execute_pdf_rename_batch(rule, sources, expected_preview_token=preview.preview_token)
    assert provider.call_count == 2
    with Image.open(BytesIO(provider.call_args_list[1].args[1])) as crop:
        assert crop.mode == "L" and crop.getextrema() == (0, 255)
    assert "红色文字" in provider.call_args_list[1].kwargs["prompt"]
    assert "unrelated" not in provider.call_args_list[1].kwargs["prompt"]


def test_no_red_cannot_fall_back_to_cloud_or_black_number(cloud, monkeypatch):
    provider = Mock()
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    with pytest.raises(PdfRenameServiceError) as error:
        ocr.recognize_fixed_region(pdf(), BuzzBeeIndonesiaInvoiceRule.definition.regions[1])
    assert error.value.code == "PDF_RENAME_REGION_EMPTY"
    provider.assert_not_called()
