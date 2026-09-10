from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock, MagicMock
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.services.pdf_rename.contracts import PdfRenameSource, RecognizedRegionValue, PdfRenameServiceError
from app.services.pdf_rename.registry import get_pdf_rename_rule, list_pdf_rename_rules
from app.services.pdf_rename.rules.buzzbee_inspection import BuzzBeeInspectionRule
from app.services.pdf_rename.service import build_pdf_rename_preview, execute_pdf_rename_batch
from app.services.pdf_rename import ocr

HEADER = "BUZZ BEE TOYS (HK) CO., LIMITED\nINSPECTION REPORT"
WRAPPED_ITEM_SCAN = """Se OE a ae

a

Se aad

Inspected By / Date:

Lena/050226

Item No. /Description:

~11011/AF T-REX SQUIRTER

ubmission:- 1

Factory:- WH

late Code:- 100086B

5/C:-52136+52137

Lot Size/Total Order:

3800/475+1896/237-5696/712"""


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def recognizer(body, header=HEADER):
    def recognize(_pdf, region):
        raw = header if region.key == "report_header" else body
        return RecognizedRegionValue(region.key, region.label, raw, " ".join(raw.split()), "LOCAL_OCR", .8)
    return recognize


def plan(body, header=HEADER):
    # The old name deliberately disagrees: business identifiers come only from the report.
    return BuzzBeeInspectionRule().create_plan(PdfRenameSource("#99999-99999.pdf", pdf()), recognizer(body, header))


@pytest.mark.parametrize(("item", "pos"), [
    ("10330", "53102"),
    ("93229", "52604+52713+52640+52703+52651+52617+52631+52608"),
    ("10400", "52341+52342+52343+52340+52344"),
    ("11009", "52045+51989+52018+52019+52046+52012"),
    ("11001", "52129+52138+52139"), ("11001", "52140+52141"),
    ("11009", "52013+51991+52039+52016+51999+52014+51971"),
    ("11009", "52015+51992+52036+52023+52020+52009+52028+52035"),
    ("00123", "00001+00009+00001"),
])
def test_filename_contract_preserves_all_po_order_zeroes_and_repetitions(item, pos):
    result = plan(f"Item No. /Description:- {item}/PRODUCT\nDate Code:-100086B\nS/C:-{pos}\nLot Size/Total Order:1000/125")
    assert result.target_file_name == f"#{item}-{pos}.pdf"
    assert result.status == "REVIEW"
    fields = {field.key: field for field in result.fields}
    assert fields["item_no"].normalized_text == item
    assert fields["po_numbers"].normalized_text == pos
    assert fields["po_numbers"].raw_text == f"S/C:-{pos}"


@pytest.mark.parametrize("label", ["S/C:-", "5/C:~", "/C:-", "IS/C:-", "S / C : —"])
def test_scan_label_noise_is_allowed_but_digits_are_not_repaired(label):
    result = plan(f"[tem No. /Description:—11001/PRODUCT\n{label}52140 + 52141")
    assert result.target_file_name == "#11001-52140+52141.pdf"


def test_explicit_plus_wrapping_and_fullwidth_punctuation():
    result = plan("Item No./Description：＃11001/PRODUCT\nS/C：５２１４０＋\n５２１４１")
    assert result.status == "ERROR"  # Unsupported item prefix is not silently discarded.
    result = plan("Item No./Description：－１１００１/PRODUCT\nS/C：５２１４０＋\n５２１４１\n+52142")
    assert result.target_file_name == "#11001-52140+52141+52142.pdf"


def test_reported_split_item_label_keeps_raw_evidence_and_requires_review():
    result = plan(WRAPPED_ITEM_SCAN)
    assert result.target_file_name == "#11011-52136+52137.pdf"
    assert result.status == "REVIEW"
    fields = {field.key: field for field in result.fields}
    assert fields["item_no"].normalized_text == "11011"
    assert fields["item_no"].raw_text == "Item No. /Description:\n~11011/AF T-REX SQUIRTER"
    assert fields["po_numbers"].normalized_text == "52136+52137"


@pytest.mark.parametrize("label", ["Item No./Description:", "Item No./Description:-", "[tem No. /Description：—"])
@pytest.mark.parametrize("separator", ["\n", "\r\n", "\n\n  \n"])
def test_item_label_and_value_may_be_on_adjacent_nonempty_lines(label, separator):
    result = plan(f"{label}{separator}~00123/PRODUCT\nS/C:-00001+00009")
    assert result.target_file_name == "#00123-00001+00009.pdf"


@pytest.mark.parametrize("body", [
    "Item No./Description:\nDate Code:-11011/PRODUCT\nS/C:-52136",
    "Item No./Description:\nFactory:-WH\n11011/PRODUCT\nS/C:-52136",
    "Item No./Description:\n11O11/PRODUCT\nS/C:-52136",
    "Item No./Description:\n1101/PRODUCT\nS/C:-52136",
    "Item No./Description:\n110111/PRODUCT\nS/C:-52136",
    "Item No./Description:\n11011 PRODUCT\nS/C:-52136",
    "Item No./Description:\n110\n11/PRODUCT\nS/C:-52136",
    "Item No./Description:\nS/C:-52136\n11011/PRODUCT",
    "Item No./Description:\n11011/PRODUCT\nItem No./Description:-11009/OTHER\nS/C:-52136",
    "Item No./Description:-11011/PRODUCT\nItem No./Description:\nUNKNOWN\nS/C:-52136",
    "Item No./Description:\n11011/PRODUCT\nItem No./Description:\n11011/PRODUCT\nS/C:-52136",
])
def test_split_item_does_not_guess_skip_fields_or_accept_ambiguous_labels(body):
    result = plan(body)
    assert result.status == "ERROR"
    assert not result.target_file_name


@pytest.mark.parametrize("body", [
    "Date Code:-10400 100196A\nS/C:-52341",  # No fallback to date code or upload name.
    "Item No./Description:-11001/PRODUCT",  # Missing PO.
    "Item No./Description:-11001/PRODUCT\nItem No./Description:-11009/OTHER\nS/C:-52140",
    "Item No./Description:-11001/PRODUCT\nS/C:-52140\nS/C:-52141",
    *[f"Item No./Description:-11001/PRODUCT\nS/C:-{pos}" for pos in (
        "52140+", "5214052141", "52140++52141", "52140 52141", "52140/52141",
        "52140+52O41", "52140+5214", "52140+521410", "52140+52141 ???", "52140\n52141", "",
    )],
    "Item No./Description:-1100I/PRODUCT\nS/C:-52140",
    "Item No./Description:-11001/PRODUCT\nS/C:-" + "+".join(["52140"] * 30),
])
def test_ambiguous_missing_or_overlength_identifiers_fail_closed(body):
    result = plan(body)
    assert result.status == "ERROR"
    assert not result.target_file_name


def test_other_reports_are_not_accepted():
    result = plan("Item No./Description:-11001/PRODUCT\nS/C:-52140", header="OTHER COMPANY INSPECTION REPORT")
    assert result.status == "ERROR"


def test_catalog_enables_a_separate_versioned_ocr_rule():
    rule = get_pdf_rename_rule("buzzbee-inspection", "huaxing")
    assert rule.definition.version == "1.0.1"
    assert all(region.ocr_only and region.page_number == 1 for region in rule.definition.regions)
    assert rule.definition.factory_ids == ("huaxing",)
    assert next(row for row in list_pdf_rename_rules("huaxing") if row["id"] == "buzzbee-inspection")["available"]


def test_collision_review_staleness_and_lossless_zip():
    rule = BuzzBeeInspectionRule()
    source = PdfRenameSource("old.pdf", pdf())
    read = recognizer("Item No./Description:-11001/PRODUCT\nS/C:-52140+52141")
    preview = build_pdf_rename_preview(rule, (source,), recognizer=read)
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(rule, (source,), expected_preview_token=preview.preview_token, recognizer=read)
    assert error.value.code == "PDF_RENAME_OCR_REVIEW_REQUIRED"
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(rule, (source,), expected_preview_token="stale", ocr_review_confirmed=True, recognizer=read)
    assert error.value.code == "PDF_RENAME_PREVIEW_STALE"
    collision = build_pdf_rename_preview(rule, (source, replace(source, source_file_name="other.pdf")), recognizer=read)
    assert collision.error_count == 2
    archive = execute_pdf_rename_batch(rule, (source,), expected_preview_token=preview.preview_token,
                                     ocr_review_confirmed=True, recognizer=read)
    with ZipFile(BytesIO(archive.content)) as z:
        assert z.namelist() == ["#11001-52140+52141.pdf"]
        assert z.read(z.namelist()[0]) == source.content


def mock_tesseract(monkeypatch, text):
    pytesseract = pytest.importorskip("pytesseract")
    monkeypatch.setattr(ocr, "configure_tesseract", lambda _module: ("test-tesseract", "eng"))
    monkeypatch.setattr(pytesseract, "get_languages", lambda **_kwargs: ["eng"])
    recognize = Mock(side_effect=text) if isinstance(text, list) else Mock(return_value=text)
    monkeypatch.setattr(pytesseract, "image_to_string", recognize)
    return recognize


def test_rule_ignores_incorrect_embedded_text_and_uses_sparse_region_ocr(monkeypatch):
    text_layer = Mock(side_effect=AssertionError("Embedded OCR must not be used"))
    monkeypatch.setattr(ocr.pdfplumber, "open", text_layer)
    recognize = mock_tesseract(monkeypatch, "S/C:-52036+52023")
    result = ocr.recognize_fixed_region(pdf(), BuzzBeeInspectionRule.definition.regions[1])
    assert text_layer.call_count == 0
    assert result.normalized_text == "S/C:-52036+52023"
    assert result.route == "LOCAL_OCR"
    assert "--psm 11" in recognize.call_args.kwargs["config"]


def test_default_rules_keep_the_native_text_path(monkeypatch):
    document = MagicMock()
    page = document.__enter__.return_value.pages.__getitem__.return_value
    page.width, page.height = 595, 842
    page.crop.return_value.extract_text.return_value = "native text"
    monkeypatch.setattr(ocr.pdfplumber, "open", Mock(return_value=document))
    region = replace(BuzzBeeInspectionRule.definition.regions[1], ocr_only=False)
    assert ocr.recognize_fixed_region(pdf(), region).route == "NATIVE_TEXT"


@pytest.mark.parametrize(("body", "expected_name"), [
    ("Item No./Description:-11001/PRODUCT\nS/C:-52140+52141", "#11001-52140+52141.pdf"),
    (WRAPPED_ITEM_SCAN, "#11011-52136+52137.pdf"),
])
def test_authenticated_api_catalog_preview_review_gate_and_zip(monkeypatch, body, expected_name):
    from app.api import pdf_rename as routes
    from app.core.config import settings
    from app.services.auth import get_current_user
    monkeypatch.setattr(settings, "document_tools_enabled", True)
    mock_tesseract(monkeypatch, [HEADER, body] * 4)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        assert client.get("/api/tools/pdf-rename/rules").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: object()
        catalog = client.get("/api/tools/pdf-rename/rules", params={"factory_id": "huaxing"})
        assert catalog.status_code == 200
        data = {"rule_id": "buzzbee-inspection", "factory_id": "huaxing"}
        files = {"pdf_files": ("random.pdf", pdf(), "application/pdf")}
        response = client.post("/api/tools/pdf-rename/preview", data=data, files=files)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["summary"] == {"total": 1, "ready": 0, "review": 1, "error": 0}
        data["preview_token"] = preview["preview_token"]
        assert client.post("/api/tools/pdf-rename/execute", data=data, files=files).status_code == 409
        data["ocr_review_confirmed"] = "true"
        response = client.post("/api/tools/pdf-rename/execute", data=data, files=files)
        assert response.status_code == 200, response.text
        with ZipFile(BytesIO(response.content)) as archive:
            assert archive.read(expected_name) == files["pdf_files"][1]


@pytest.mark.parametrize("factory_id", ["huadeng", "huakang-a", "huakang-b", "huakang-c", "huakang-d"])
def test_buzzbee_is_hidden_and_rejected_outside_huaxing(factory_id, monkeypatch):
    from app.api import pdf_rename as routes
    from app.core.config import settings
    from app.services.auth import get_current_user
    monkeypatch.setattr(settings, "document_tools_enabled", True)
    read = Mock(side_effect=AssertionError("Wrong-factory files must not be read"))
    monkeypatch.setattr(routes, "_read_pdf_rename_batch", read)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as client:
        catalog = client.get("/api/tools/pdf-rename/rules", params={"factory_id": factory_id})
        assert catalog.status_code == 200
        assert all(row["id"] != "buzzbee-inspection" for row in catalog.json()["rules"])
        assert catalog.json()["rules"] == []
        for endpoint in ("preview", "execute"):
            response = client.post(f"/api/tools/pdf-rename/{endpoint}",
                data={"factory_id": factory_id, "rule_id": "buzzbee-inspection",
                      "preview_token": "huaxing-preview", "ocr_review_confirmed": "true"},
                files={"pdf_files": ("scan.pdf", pdf(), "application/pdf")})
            assert response.status_code == 403, response.text
            assert response.json()["detail"]["code"] == "PDF_RENAME_RULE_FACTORY_MISMATCH"
        assert read.call_count == 0

    # The registered service entry points enforce the same boundary without the API.
    from app.services.pdf_rename.service import preview_registered_pdf_rename_batch, execute_registered_pdf_rename_batch
    with pytest.raises(PdfRenameServiceError) as error:
        preview_registered_pdf_rename_batch("buzzbee-inspection", (), factory_id=factory_id)
    assert error.value.code == "PDF_RENAME_RULE_FACTORY_MISMATCH"
    with pytest.raises(PdfRenameServiceError) as error:
        execute_registered_pdf_rename_batch("buzzbee-inspection", (), factory_id=factory_id,
                                           expected_preview_token="huaxing-preview", ocr_review_confirmed=True)
    assert error.value.code == "PDF_RENAME_RULE_FACTORY_MISMATCH"


@pytest.mark.parametrize("factory_id", [None, "", "group", "unknown"])
def test_factory_context_is_explicit_and_validated(factory_id, monkeypatch):
    from app.api import pdf_rename as routes
    from app.core.config import settings
    from app.services.auth import get_current_user
    monkeypatch.setattr(settings, "document_tools_enabled", True)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    factory = {} if factory_id is None else {"factory_id": factory_id}
    with TestClient(app) as client:
        assert client.get("/api/tools/pdf-rename/rules", params=factory).status_code in {400, 422}
        for endpoint in ("preview", "execute"):
            response = client.post(f"/api/tools/pdf-rename/{endpoint}",
                data={**factory, "rule_id": "buzzbee-inspection", "preview_token": "old"},
                files={"pdf_files": ("scan.pdf", pdf(), "application/pdf")})
            assert response.status_code in {400, 422}, response.text
