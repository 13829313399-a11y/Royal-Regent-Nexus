from io import BytesIO
from zipfile import ZipFile
import pytest
from assistant_office_fixtures import docx_fixture, xlsx_fixture, rewrite


def extract(raw, extension, pages=100, characters=100000):
    from app.services.assistant.document_parser import extract as parse
    return parse(raw, extension, pages, characters)


def error(raw, extension, code, **limits):
    from app.services.assistant.document_parser import DocumentParseError
    with pytest.raises(DocumentParseError) as caught:
        extract(raw, extension, **limits)
    assert caught.value.code == code


def test_docx_real_paragraph_heading_table_and_empty_paragraph_positions():
    parts = extract(docx_fixture(), '.docx')
    clause = next(p for p in parts if p['locator']['paragraph'] == 8)
    assert clause['text'] == '合成条款：交付前核对数量与单位。'
    assert clause['metadata']['heading'] == '验收条件'
    assert not any(p['locator'].get('page') for p in parts)
    assert not any(p['locator']['paragraph'] == 3 for p in parts)
    assert parts[-1]['locator']['paragraph'] == 9 and parts[-1]['metadata']['in_table']
    assert '不推算页码' in clause['metadata']['coverage']


def test_xlsx_keeps_actual_caches_unknown_zero_dates_merged_header_and_hidden_data():
    parts = extract(xlsx_fixture(), '.xlsx')
    cells = {p['locator']['cells']: p for p in parts if p['locator']['sheet'] == '采购'}
    assert cells['C7']['text'] == '400'
    assert cells['C7']['metadata']['formula'] == '=A7-B7'
    assert cells['C7']['metadata']['cache_status'] == 'available'
    assert cells['D7']['text'] == '未知（公式未保存可用缓存）'
    assert cells['D7']['metadata']['formula'] == '=EXTERNAL_REF'
    assert cells['D7']['metadata']['raw_value'] is None
    assert cells['D7']['metadata']['cache_status'] == 'missing'
    assert cells['E7']['text'] == '0' and cells['E7']['metadata']['cache_status'] == 'available'
    assert cells['A1']['metadata']['merged_range'] == 'A1:D1'
    assert cells['A1']['metadata']['merged_anchor'] == 'A1'
    assert cells['A2']['text'] == '00017'
    assert cells['A3']['text'] == '2026-10-23T00:00:00'
    assert cells['C7']['metadata']['hidden_row']
    assert parts[-1]['metadata']['sheet_state'] == 'hidden'


@pytest.mark.parametrize('extension', ['.docx', '.xlsx'])
def test_rejects_disguised_plain_text(extension):
    error(b'not an Office package', extension, 'office_signature')


@pytest.mark.parametrize('name,content,code', [
    ('../outside.xml', b'<x/>', 'office_package_path'),
    ('xl/vbaProject.bin', b'never execute', 'office_active_content'),
    ('xl/embeddings/object.bin', b'never execute', 'office_active_content'),
    ('xl/large.txt', b'0' * 1000000, 'office_expansion_limit'),
    ('xl/sharedStrings.xml', b'<!DOCTYPE s [<!ENTITY x SYSTEM "file:///private">]><s>&x;</s>', 'office_active_content'),
], ids=['path-traversal', 'macro', 'embedding', 'expansion-bomb', 'external-entity'])
def test_rejects_unsafe_packages_without_extracting_or_following_entities(name, content, code):
    error(rewrite(xlsx_fixture(), {name: content}), '.xlsx', code)


def test_refuses_macro_content_type_even_with_normal_filename():
    raw = xlsx_fixture()
    with ZipFile(BytesIO(raw)) as source:
        types = source.read('[Content_Types].xml').replace(
            b'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
            b'application/vnd.ms-excel.sheet.macroEnabled.main+xml')
    error(rewrite(raw, {'[Content_Types].xml': types}), '.xlsx', 'office_active_content')


def test_budgets_apply_to_metadata_sheets_cells_and_paragraphs(monkeypatch):
    from app.services.assistant import office_parser
    error(xlsx_fixture(), '.xlsx', 'file_text_limit', characters=100)
    error(xlsx_fixture(), '.xlsx', 'office_sheet_limit', pages=1)
    monkeypatch.setattr(office_parser, 'MAX_CELLS', 2)
    error(xlsx_fixture(), '.xlsx', 'office_cell_limit')
    error(docx_fixture(), '.docx', 'office_paragraph_limit', pages=0)


def test_shared_formulas_use_saved_cache_and_preserve_translated_expression():
    raw = xlsx_fixture()
    with ZipFile(BytesIO(raw)) as source:
        sheet = source.read('xl/worksheets/sheet1.xml')
    sheet = sheet.replace(b'<f>A7-B7</f>', b'<f t="shared" si="0" ref="C7:D7">A7-B7</f>')
    sheet = sheet.replace(b'<f>EXTERNAL_REF</f>', b'<f t="shared" si="0"/>')
    parts = extract(rewrite(raw, {'xl/worksheets/sheet1.xml': sheet}), '.xlsx')
    right = next(p for p in parts if p['locator']['cells'] == 'D7')
    assert right['metadata']['formula'] == '=B7-C7'
    assert right['metadata']['cache_status'] == 'missing'


def test_archive_closes_when_signature_validation_fails(monkeypatch):
    from app.services.assistant import office_parser
    archives = []
    original = office_parser.ZipFile
    def capture(*args, **kwargs):
        archive = original(*args, **kwargs); archives.append(archive); return archive
    monkeypatch.setattr(office_parser, 'ZipFile', capture)
    error(xlsx_fixture(), '.docx', 'office_signature')
    assert archives and all(z.fp is None for z in archives)
