import json
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.pdf_rename.contracts import PdfRenameManualOverride, PdfRenameServiceError, PdfRenameSource
from app.services.pdf_rename.rules.buzzbee_inspection import BuzzBeeInspectionRule
from app.services.pdf_rename.service import build_pdf_rename_preview, execute_pdf_rename_batch, parse_manual_overrides
from test_buzzbee_pdf_rename import HEADER, mock_tesseract, pdf, recognizer

BROKEN_OCR = "Item No./Description:\n11O11/PRODUCT\nS/C:-52136+52137"


def preview(overrides, *, content=None, read=None):
    return build_pdf_rename_preview(BuzzBeeInspectionRule(), (PdfRenameSource('scan.pdf', content or pdf()),),
        recognizer=read or recognizer(BROKEN_OCR), manual_overrides=overrides)


def test_manual_release_preserves_evidence_and_bytes_and_requires_final_review():
    source = PdfRenameSource('random.pdf', pdf())
    overrides = (PdfRenameManualOverride(0, '#11011-52136+52137', True),)
    read = recognizer(BROKEN_OCR)
    plan = build_pdf_rename_preview(BuzzBeeInspectionRule(), (source,), recognizer=read, manual_overrides=overrides)
    row = plan.items[0]
    assert row.status == 'REVIEW' and row.manual_override
    assert row.target_file_name == '#11011-52136+52137.pdf'
    assert any('11O11' in field.raw_text for field in row.fields)
    assert any(issue.code == 'PDF_RENAME_INTERVAL_INVALID' for issue in row.issues)
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(BuzzBeeInspectionRule(), (source,), recognizer=read,
            manual_overrides=overrides, expected_preview_token=plan.preview_token)
    assert error.value.code == 'PDF_RENAME_OCR_REVIEW_REQUIRED'
    result = execute_pdf_rename_batch(BuzzBeeInspectionRule(), (source,), recognizer=read,
        manual_overrides=overrides, expected_preview_token=plan.preview_token, ocr_review_confirmed=True)
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.namelist() == ['#11011-52136+52137.pdf']
        assert archive.read(archive.namelist()[0]) == source.content


@pytest.mark.parametrize('name', ['', '.pdf', '../a.pdf', 'a/b.pdf', 'a\\b.pdf', 'C:a.pdf', 'a?.pdf',
    'CON.pdf', 'con.other.pdf', 'LPT1.pdf', 'a .pdf', 'a..pdf', 'a.txt', 'a\x00.pdf', 'a\u202e.pdf',
    'a' * 161 + '.pdf', '汉' * 100 + '.pdf'])
def test_invalid_manual_targets_remain_blocked(name):
    result = preview((PdfRenameManualOverride(0, name, True),))
    assert result.error_count == 1
    assert not result.items[0].manual_override
    assert result.items[0].issues[-1].code == 'PDF_RENAME_MANUAL_TARGET_INVALID'


def test_confirmation_and_unique_in_range_indexes_are_required():
    with pytest.raises(PdfRenameServiceError) as error:
        preview((PdfRenameManualOverride(0, 'correct.pdf', False),))
    assert error.value.code == 'PDF_RENAME_MANUAL_CONFIRMATION_REQUIRED'
    for rows in [(PdfRenameManualOverride(-1, 'correct.pdf', True),),
                 (PdfRenameManualOverride(1, 'correct.pdf', True),),
                 (PdfRenameManualOverride(True, 'correct.pdf', True),),
                 (PdfRenameManualOverride(0, 'a.pdf', True), PdfRenameManualOverride(0, 'b.pdf', True))]:
        with pytest.raises(PdfRenameServiceError) as error:
            preview(rows)
        assert error.value.code == 'PDF_RENAME_MANUAL_INVALID'


def test_manual_name_cannot_bypass_invalid_pdf_or_hard_errors():
    result = preview((PdfRenameManualOverride(0, 'correct.pdf', True),), content=b'%PDF-broken')
    assert result.error_count == 1
    assert result.items[0].issues[-1].code == 'PDF_RENAME_PDF_INVALID'
    assert not result.items[0].manual_override_allowed
    def encrypted(_content, _region):
        raise PdfRenameServiceError('PDF_RENAME_PDF_ENCRYPTED', 'encrypted', action='unlock')
    result = preview((PdfRenameManualOverride(0, 'correct.pdf', True),), read=encrypted)
    assert result.error_count == 1 and not result.items[0].manual_override


def test_manual_names_are_checked_for_collisions_after_override():
    sources = (PdfRenameSource('same.pdf', pdf()), PdfRenameSource('same.pdf', pdf()))
    overrides = (PdfRenameManualOverride(0, 'same.pdf', True), PdfRenameManualOverride(1, 'SAME.pdf', True))
    read = recognizer(BROKEN_OCR)
    result = build_pdf_rename_preview(BuzzBeeInspectionRule(), sources, recognizer=read, manual_overrides=overrides)
    assert result.error_count == 2
    assert all(item.issues[-1].code == 'PDF_RENAME_TARGET_COLLISION' for item in result.items)
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(BuzzBeeInspectionRule(), sources, recognizer=read, manual_overrides=overrides,
            expected_preview_token=result.preview_token, ocr_review_confirmed=True)
    assert error.value.code == 'PDF_RENAME_PREVIEW_HAS_ERRORS'


def test_execute_binds_manual_source_index_name_mode_and_content_to_preview():
    sources = (PdfRenameSource('A.pdf', pdf()), PdfRenameSource('B.pdf', pdf()))
    read = recognizer('Item No./Description:-11011/PRODUCT\nS/C:-52136')
    rule = BuzzBeeInspectionRule()
    overrides = (PdfRenameManualOverride(0, 'A.pdf', True), PdfRenameManualOverride(1, 'B.pdf', True))
    result = build_pdf_rename_preview(rule, sources, recognizer=read, manual_overrides=overrides)
    changed = (replace(overrides[0], target_file_name='changed.pdf'), overrides[1])
    swapped = (replace(overrides[0], source_index=1), replace(overrides[1], source_index=0))
    for modifications in (changed, swapped, ()):
        with pytest.raises(PdfRenameServiceError) as error:
            execute_pdf_rename_batch(rule, sources, recognizer=read, manual_overrides=modifications,
                expected_preview_token=result.preview_token, ocr_review_confirmed=True)
        assert error.value.code == 'PDF_RENAME_PREVIEW_STALE'
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(rule, tuple(reversed(sources)), recognizer=read, manual_overrides=overrides,
            expected_preview_token=result.preview_token, ocr_review_confirmed=True)
    assert error.value.code == 'PDF_RENAME_PREVIEW_STALE'
    changed_sources = (replace(sources[0], content=sources[0].content + b'\n% updated source'), sources[1])
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(rule, changed_sources, recognizer=read, manual_overrides=overrides,
            expected_preview_token=result.preview_token, ocr_review_confirmed=True)
    assert error.value.code == 'PDF_RENAME_PREVIEW_STALE'
    # Even an unchanged target must not silently lose its manual provenance.
    one = (sources[0],)
    override = (PdfRenameManualOverride(0, '#11011-52136.pdf', True),)
    result = build_pdf_rename_preview(rule, one, recognizer=read, manual_overrides=override)
    with pytest.raises(PdfRenameServiceError) as error:
        execute_pdf_rename_batch(rule, one, recognizer=read, expected_preview_token=result.preview_token, ocr_review_confirmed=True)
    assert error.value.code == 'PDF_RENAME_PREVIEW_STALE'


@pytest.mark.parametrize('value', ['bad', '{}', 'null', '[{}]', '[1]',
    '[{"source_index":true,"target_file_name":"a.pdf","confirmed":true}]',
    '[{"source_index":0,"target_file_name":"a.pdf","confirmed":"true"}]',
    '[{"source_index":0,"target_file_name":12,"confirmed":true}]', ' ' * 32001])
def test_manual_payload_is_strict(value):
    with pytest.raises(PdfRenameServiceError) as error:
        parse_manual_overrides(value)
    assert error.value.code == 'PDF_RENAME_MANUAL_INVALID'


def test_api_manual_preview_release_and_factory_guard(monkeypatch):
    from app.api import tools as routes
    from app.core.config import settings
    from app.services.auth import get_current_user
    monkeypatch.setattr(settings, 'document_tools_enabled', True)
    mock_tesseract(monkeypatch, [HEADER, BROKEN_OCR] * 6)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    files = {'pdf_files': ('unknown.pdf', pdf(), 'application/pdf')}
    overrides = [{'source_index': 0, 'target_file_name': '#11011-52136+52137.pdf', 'confirmed': True}]
    data = {'factory_id': 'huaxing', 'rule_id': 'buzzbee-inspection', 'manual_overrides': json.dumps(overrides)}
    with TestClient(app) as client:
        response = client.post('/api/tools/pdf-rename/preview', data=data, files=files)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['items'][0]['manual_override'] is True
        assert result['summary']['error'] == 0
        data.update(preview_token=result['preview_token'], ocr_review_confirmed='true')
        response = client.post('/api/tools/pdf-rename/execute', data=data, files=files)
        assert response.status_code == 200, response.text
        with ZipFile(BytesIO(response.content)) as archive:
            assert archive.read('#11011-52136+52137.pdf') == files['pdf_files'][1]
        for endpoint in ('preview', 'execute'):
            response = client.post(f'/api/tools/pdf-rename/{endpoint}', data={**data, 'factory_id': 'huadeng'}, files=files)
            assert response.status_code == 403
