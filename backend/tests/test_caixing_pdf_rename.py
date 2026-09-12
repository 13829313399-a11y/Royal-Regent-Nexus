from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.pdf_rename.contracts import (
    PdfRenameSource, RecognizedRegionValue, RecognizedTextBox,
    PdfRenameServiceError, PdfRenameManualOverride,
)
from app.services.pdf_rename.rules.caixing_inspection import CaixingInspectionRule
from app.services.pdf_rename.service import build_pdf_rename_preview, execute_pdf_rename_batch
from app.services.pdf_rename.registry import get_pdf_rename_rule
from app.services.pdf_rename import ocr
from test_buzzbee_pdf_rename import pdf


HEADER = 'Playmates International Company Limited\nSHIPMENT QUALITY INSPECTION REPORT'


def box(text, x, y, width=.09, slope=0, confidence=.99):
    height = .045
    points = ((x, y + slope*x), (x+width, y+slope*(x+width)),
              (x+width, y+slope*(x+width)+height), (x, y+slope*x+height))
    return RecognizedTextBox(text, points, confidence)


def evidence(report='RR6015P', item='57812NMC4', po='1931771', quantity='2800', date='3/04/2026', slope=0):
    entries = [
        ('Item number', .02, .38), (item, .20, .38),
        ('Date Code', .02, .44), ('RR6021-01', .20, .44),
        ('Quantity (Pcs)', .02, .50), (quantity, .20, .50),
        ('Quantity (Ctns)', .02, .56), ('700', .20, .56),
        ('Sample Size (Pcs)', .02, .62), ('125', .20, .62),
        ('P/O no.', .38, .44), (po, .54, .44),
        ('Conf No.', .38, .50), ('1926205', .54, .50),
        ('Batch no.', .73, .62), (report, .86, .62),
        ('DATE:', .73, .18), (date, .83, .18),
    ]
    boxes = tuple(box(text, x, y, slope=slope) for text, x, y in entries)
    raw = HEADER + '\n' + '\n'.join(b.text for b in boxes)
    return RecognizedRegionValue('report_header', '彩星首页', raw, ' '.join(raw.split()), 'LOCAL_OCR', .99, boxes)


def plan(value):
    return CaixingInspectionRule().create_plan(PdfRenameSource('RR9999-#99999-9999999-999-2020.1.1.pdf', pdf()), lambda *_: value)


@pytest.mark.parametrize(('report', 'item', 'po', 'quantity', 'date', 'target'), [
    ('RR6009', '57814NMC4', '1931734', '3000', '2/04/2026', 'RR6009-#57814-1931734-3000-2026.2.4.pdf'),
    ('RR6010', '57814NMC4', '1931773', '2900', '2/04/2026', 'RR6010-#57814-1931773-2900-2026.2.4.pdf'),
    ('RR6011', '57812NMC4', '1931771', '3000', '2/05/2026', 'RR6011-#57812-1931771-3000-2026.2.5.pdf'),
    ('RR6012', '57816NMC4', '1931736', '2904', '3/03/2026', 'RR6012-#57816-1931736-2904-2026.3.3.pdf'),
    ('RR6013', '57811NMC4', '1931770', '5688', '3/03/2026', 'RR6013-#57811-1931770-5688-2026.3.3.pdf'),
    ('RR6014', '57811NMC4', '1931731', '3000', '3/04/2026', 'RR6014-#57811-1931731-3000-2026.3.4.pdf'),
    ('RR6015P', '57812NMC4', '1931771', '2800', '3/04/2026', 'RR6015P-#57812-1931771-2800-2026.3.4.pdf'),
    ('RR6016', '57812NMC4', '1931732', '3000', '2/05/2026', 'RR6016-#57812-1931732-3000-2026.2.5.pdf'),
    ('RR6017', '57810E8-02', '1931852', '312', '4/09/2026', 'RR6017-#57810-1931852-312-2026.4.9.pdf'),
    ('RR0001P', '00123', '0001234', '4,000', '1/08/2026', 'RR0001P-#00123-0001234-4000-2026.1.8.pdf'),
])
def test_body_mapping_not_filename_or_date_code(report, item, po, quantity, date, target):
    result = plan(evidence(report, item, po, quantity, date))
    assert result.target_file_name == target
    assert result.status == 'REVIEW'
    assert len(result.fields) == 6
    assert result.fields[1].raw_text == 'Batch no.\n' + report
    assert result.fields[2].raw_text == 'Item number\n' + item


@pytest.mark.parametrize('slope', [-.3, -.05, 0, .03])
def test_skew_and_ocr_output_order_do_not_cross_table_rows(slope):
    value = evidence(slope=slope)
    value = replace(value, text_boxes=tuple(reversed(value.text_boxes)))
    assert plan(value).target_file_name == 'RR6015P-#57812-1931771-2800-2026.3.4.pdf'


@pytest.mark.parametrize(('key', 'bad'), [
    ('report', 'RR6O15P'), ('report', 'RR6015PP'), ('report', 'RR60150'),
    ('item', '5781ONMC4'), ('item', '578123'), ('item', '57812/57811'),
    ('po', '193177I'), ('po', '193177'), ('po', '19317710'), ('po', '1931771+1931732'),
    ('quantity', '2,80'), ('quantity', '-2800'), ('quantity', '0'), ('quantity', '2800.0'),
    ('date', '2/29/2026'), ('date', '13/1/2026'), ('date', '2026/3/4'), ('date', '3/04/26'),
])
def test_invalid_or_ambiguous_values_fail_closed(key, bad):
    result = plan(evidence(**{key: bad}))
    assert result.status == 'ERROR'
    assert not result.target_file_name
    assert result.manual_override_allowed


@pytest.mark.parametrize('missing', ['Batch no.', 'RR6015P', 'Item number', '57812NMC4', '1931771', '2800', '3/04/2026'])
def test_missing_labels_or_cells_never_borrow_neighbour_or_old_name(missing):
    value = evidence()
    result = plan(replace(value, text_boxes=tuple(b for b in value.text_boxes if b.text != missing)))
    assert result.status == 'ERROR'


def test_duplicate_labels_values_low_confidence_and_wrong_header():
    value = evidence()
    for boxes in (value.text_boxes + (value.text_boxes[0],),
                  value.text_boxes + (box('57813NMC4', .29, .38, width=.04),),
                  tuple(replace(b, confidence=.6) if b.text == '1931771' else b for b in value.text_boxes)):
        assert plan(replace(value, text_boxes=boxes)).status == 'ERROR'
    assert plan(replace(value, normalized_text='OTHER INSPECTION REPORT')).status == 'ERROR'
    assert plan(replace(value, text_boxes=())).status == 'ERROR'


def test_inline_values_and_label_only_ocr_variation():
    value = evidence(date='2/29/2024')
    boxes = tuple(replace(b, text='DATE:2/29/2024') if b.text == 'DATE:' else
                  replace(b, text='PIO no.') if b.text == 'P/O no.' else b
                  for b in value.text_boxes if b.text != '2/29/2024')
    assert plan(replace(value, text_boxes=boxes)).target_file_name.endswith('2024.2.29.pdf')


def test_skewed_photograph_neighbour_column_does_not_count_as_quantity():
    value = evidence(slope=-.3)
    extra = box('O/R No.', .32, .50, width=.06, slope=-.3)
    assert plan(replace(value, text_boxes=(*value.text_boxes, extra))).status == 'REVIEW'
    missing = tuple(b for b in value.text_boxes if b.text != '2800')
    assert plan(replace(value, text_boxes=(*missing, extra))).status == 'ERROR'


def test_new_rule_zip_review_collision_staleness_and_manual_release():
    rule = CaixingInspectionRule()
    source = PdfRenameSource('scan.pdf', pdf())
    read = lambda *_: evidence()
    preview = build_pdf_rename_preview(rule, (source,), recognizer=read)
    with pytest.raises(PdfRenameServiceError) as exc:
        execute_pdf_rename_batch(rule, (source,), expected_preview_token=preview.preview_token, recognizer=read)
    assert exc.value.code == 'PDF_RENAME_OCR_REVIEW_REQUIRED'
    with pytest.raises(PdfRenameServiceError) as exc:
        execute_pdf_rename_batch(rule, (source,), expected_preview_token='stale', recognizer=read, ocr_review_confirmed=True)
    assert exc.value.code == 'PDF_RENAME_PREVIEW_STALE'
    assert build_pdf_rename_preview(rule, (source, replace(source, source_file_name='scan2.pdf')), recognizer=read).error_count == 2
    bad_read = lambda *_: evidence(item='5781ONMC4')
    manual = (PdfRenameManualOverride(0, 'RR6015P-#57812-1931771-2800-2026.3.4.pdf', True),)
    preview = build_pdf_rename_preview(rule, (source,), recognizer=bad_read, manual_overrides=manual)
    assert preview.items[0].manual_override and preview.review_count == 1
    result = execute_pdf_rename_batch(rule, (source,), expected_preview_token=preview.preview_token,
        recognizer=bad_read, manual_overrides=manual, ocr_review_confirmed=True)
    with ZipFile(BytesIO(result.content)) as archive:
        assert archive.read(manual[0].target_file_name) == source.content


def test_local_spatial_ocr_opt_in_ignores_native_text_and_preserves_boxes(monkeypatch):
    import app.services.carton_mark as carton
    value = evidence()
    # Simulated pixel coordinates must round-trip to normalized polygons.
    result = SimpleNamespace(txts=[b.text for b in value.text_boxes], scores=[b.confidence for b in value.text_boxes],
        boxes=[[(x*100, y*100) for x,y in b.polygon] for b in value.text_boxes])
    engine = Mock(return_value=result)
    monkeypatch.setattr(carton, 'get_rapidocr_engine', lambda: engine)
    native = Mock(side_effect=AssertionError('Must not consult embedded OCR'))
    monkeypatch.setattr(ocr.pdfplumber, 'open', native)
    result = ocr.recognize_fixed_region(pdf(), CaixingInspectionRule.definition.regions[0])
    assert result.route == 'LOCAL_OCR' and len(result.text_boxes) == len(value.text_boxes)
    assert result.text_boxes[0].text == 'Item number'
    assert 'text_boxes' not in result.as_dict()  # Spatial data is internal; raw evidence is public.
    native.assert_not_called()
    monkeypatch.setattr(carton, 'get_rapidocr_engine', lambda: None)
    with pytest.raises(PdfRenameServiceError) as exc:
        ocr.recognize_fixed_region(pdf(), CaixingInspectionRule.definition.regions[0])
    assert exc.value.code == 'PDF_RENAME_OCR_UNAVAILABLE'


@pytest.mark.parametrize('factory', ['huaxing', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d'])
def test_catalog_and_api_enforce_huaxing_only(factory, monkeypatch):
    from app.api import pdf_rename as routes
    from app.core.config import settings
    from app.services.auth import get_current_user
    monkeypatch.setattr(settings, 'document_tools_enabled', True)
    monkeypatch.setattr(ocr, '_recognize_spatial_region', lambda *_: evidence())
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as client:
        catalog = client.get('/api/tools/pdf-rename/rules', params={'factory_id':factory})
        assert catalog.status_code == 200
        assert any(r['id']=='caixing-inspection' for r in catalog.json()['rules']) == (factory == 'huaxing')
        data = {'rule_id':'caixing-inspection', 'factory_id':factory}
        files = {'pdf_files':('scan.pdf', pdf(), 'application/pdf')}
        preview = client.post('/api/tools/pdf-rename/preview', data=data, files=files)
        if factory != 'huaxing':
            assert preview.status_code == 403
            with pytest.raises(PdfRenameServiceError):
                get_pdf_rename_rule('caixing-inspection', factory)
        else:
            assert preview.status_code == 200, preview.text
            assert preview.json()['summary']['review'] == 1
        data.update(preview_token=preview.json().get('preview_token', 'foreign'), ocr_review_confirmed='true')
        result = client.post('/api/tools/pdf-rename/execute', data=data, files=files)
        assert result.status_code == (200 if factory=='huaxing' else 403), result.text if result.status_code != 200 else ''
        if factory == 'huaxing':
            with ZipFile(BytesIO(result.content)) as archive:
                assert archive.read('RR6015P-#57812-1931771-2800-2026.3.4.pdf') == files['pdf_files'][1]
