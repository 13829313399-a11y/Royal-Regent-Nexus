import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from pydantic import SecretStr
from PIL import Image

from app.services.document_tools.document_ir import ToolError
from app.services.pdf_rename import ocr, qwen
from app.services.pdf_rename.contracts import PdfRenameServiceError, PdfRenameSource
from app.services.pdf_rename.rules.buzzbee_inspection import BuzzBeeInspectionRule
from app.services.pdf_rename.rules.caixing_inspection import CaixingInspectionRule
from app.services.pdf_rename.service import build_pdf_rename_preview, execute_pdf_rename_batch
from test_buzzbee_pdf_rename import HEADER, LONG_POS, pdf


@pytest.fixture
def cloud(monkeypatch):
    settings = SimpleNamespace(document_tools_ai_mode="auto",
        document_tools_qwen_api_key=SecretStr("test-placeholder"),
        document_tools_qwen_base_url="https://example.invalid/api/v1",
        document_tools_qwen_protocol="dashscope", document_tools_qwen_layout_model="qwen3-vl-plus")
    monkeypatch.setattr(qwen, "settings", settings)
    qwen._cache.clear()
    yield settings
    qwen._cache.clear()


def response(lines, uncertain=None):
    return {"text": json.dumps({"lines": lines, "uncertain_fields": uncertain or []})}


def test_buzzbee_cloud_uses_crops_and_reuses_reading_for_lossless_download(cloud, monkeypatch):
    provider = Mock(side_effect=[response(HEADER.splitlines()), response([
        "Item No./Description:93219/ AF TOXIC CATCH.", "S/C:-" + LONG_POS])])
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    local = Mock(side_effect=AssertionError("Cloud mode must not silently use local OCR"))
    monkeypatch.setattr(ocr, "configure_tesseract", local)
    rule = BuzzBeeInspectionRule()
    sources = (PdfRenameSource("private-upload-name.pdf", pdf()),)
    preview = build_pdf_rename_preview(rule, sources)
    assert preview.ready_count == 1 and preview.review_count == 0
    assert all(field.route == "QWEN" for field in preview.items[0].fields)
    assert len(preview.items[0].fields[-1].normalized_text.split("+")) == 13
    result = execute_pdf_rename_batch(rule, sources, expected_preview_token=preview.preview_token)
    assert provider.call_count == 2  # header + identifiers, no further execute call
    assert local.call_count == 0
    for call in provider.call_args_list:
        with Image.open(BytesIO(call.args[1])) as crop:
            assert crop.height < 842  # only the upper report region, not the full page
        assert call.kwargs["layout"] is True
        assert "private-upload-name" not in call.kwargs["prompt"]
        assert "不补号" in call.kwargs["prompt"]
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.read(f"#93219-{LONG_POS}.pdf") == sources[0].content


def test_caixing_cloud_validates_labelled_values_without_fabricating_boxes(cloud, monkeypatch):
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", Mock(return_value=response([
        "Playmates International Company Limited", "SHIPMENT QUALITY INSPECTION REPORT",
        "Batch no.: RR6015P", "Item number: 57812NMC4", "Date Code: RR6021-01",
        "P/O no.: 1931771", "Quantity (Pcs): 2,800", "Quantity (Ctns): 700", "DATE: 3/04/2026"])))
    preview = build_pdf_rename_preview(CaixingInspectionRule(), (PdfRenameSource("old.pdf", pdf()),))
    assert preview.ready_count == 1 and preview.review_count == 0
    assert preview.items[0].target_file_name == "RR6015P-#57812-1931771-2800-2026.3.4.pdf"
    assert all(field.route == "QWEN" and field.confidence is None for field in preview.items[0].fields)
    assert all(not field.text_boxes for field in preview.items[0].fields)


@pytest.mark.parametrize("lines", [
    ["S/C:-52963+52973", "S/C:-52989"],
    ["S/C:-52963+529 14452923"],
    ["S/C:-52963+5297"],
    ["S/C:-52963+5297O"],
    ["S/C:52963", "+529I3"],
    ["S/C:-5296352973"],
    ["Date Code:-52963"],
])
def test_cloud_does_not_relax_identifier_validation(cloud, monkeypatch, lines):
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", Mock(side_effect=[response(HEADER.splitlines()),
        response(["Item No./Description:93219/PRODUCT", *lines])]))
    preview = build_pdf_rename_preview(BuzzBeeInspectionRule(), (PdfRenameSource("scan.pdf", pdf()),))
    assert preview.error_count == 1 and not preview.items[0].target_file_name


@pytest.mark.parametrize("payload", [
    {"lines": ["S/C:53135"], "uncertain_fields": ["S/C"]},
    {"lines": ["S/C:[无法辨认]"], "uncertain_fields": []},
    {"lines": [], "uncertain_fields": []},
    {"lines": "S/C:53135", "uncertain_fields": []},
    {"lines": ["S/C:53135"]},
    {"lines": [123], "uncertain_fields": []},
    {"lines": ["a" * 20001], "uncertain_fields": []},
])
def test_ambiguous_or_malformed_provider_result_is_blocked(cloud, monkeypatch, payload):
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", Mock(return_value={"text": json.dumps(payload)}))
    with pytest.raises(PdfRenameServiceError):
        ocr.recognize_fixed_region(pdf(), BuzzBeeInspectionRule.definition.regions[1])
    assert not qwen._cache


def test_provider_error_is_visible_and_never_silently_falls_back(cloud, monkeypatch):
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", Mock(side_effect=ToolError("QWEN_AUTH", "千问鉴权失败")))
    with pytest.raises(PdfRenameServiceError) as error:
        ocr.recognize_fixed_region(pdf(), BuzzBeeInspectionRule.definition.regions[1])
    assert error.value.code == "PDF_RENAME_QWEN_AUTH"
    assert error.value.status_code == 503
    assert not qwen._cache


@pytest.mark.parametrize("missing", ["off", "key", "endpoint"])
def test_unconfigured_or_disabled_cloud_remains_local(cloud, monkeypatch, missing):
    if missing == "off":
        cloud.document_tools_ai_mode = "off"
    elif missing == "key":
        cloud.document_tools_qwen_api_key = SecretStr("")
    else:
        cloud.document_tools_qwen_base_url = ""
    assert qwen.recognition_status()["mode"] == "local"
    provider = Mock(side_effect=AssertionError("Cloud is disabled"))
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    from test_buzzbee_pdf_rename import mock_tesseract
    mock_tesseract(monkeypatch, "S/C:53135")
    value = ocr.recognize_fixed_region(pdf(), BuzzBeeInspectionRule.definition.regions[1])
    assert value.route == "LOCAL_OCR"
    assert provider.call_count == 0


def test_cache_is_bounded_expires_and_changes_with_config_or_content(cloud, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(qwen.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(qwen, "_CACHE_LIMIT", 2)
    provider = Mock(return_value=response(["S/C:53135"]))
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    source = pdf()
    region = BuzzBeeInspectionRule.definition.regions[1]
    ocr.recognize_fixed_region(source, region)
    ocr.recognize_fixed_region(source, region)
    assert provider.call_count == 1
    cloud.document_tools_qwen_layout_model = "another-model"
    ocr.recognize_fixed_region(source, region)
    ocr.recognize_fixed_region(source + b"\n", region)
    assert provider.call_count == 3 and len(qwen._cache) == 2
    clock[0] += qwen._CACHE_TTL_SECONDS + 1
    ocr.recognize_fixed_region(source, region)
    assert provider.call_count == 4 and len(qwen._cache) == 1


def test_explicit_new_preview_refreshes_cloud_readings(cloud, monkeypatch):
    from app.services.pdf_rename.service import preview_registered_pdf_rename_batch
    provider = Mock(side_effect=[response(HEADER.splitlines()), response([
        "Item No./Description:93219/PRODUCT", "S/C:52963"])] * 2)
    monkeypatch.setattr(qwen.qwen_ocr, "recognize", provider)
    source = PdfRenameSource("scan.pdf", pdf())
    for _ in range(2):
        preview = preview_registered_pdf_rename_batch("buzzbee-inspection", (source,), factory_id="huaxing")
        assert preview.ready_count == 1
    assert provider.call_count == 4
