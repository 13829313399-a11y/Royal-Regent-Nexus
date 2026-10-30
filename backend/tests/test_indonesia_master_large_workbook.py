"""Large photo workbooks retain bounded, sparse and preview-only intake."""
from io import BytesIO
from zipfile import ZipFile, ZIP_STORED
from xml.etree import ElementTree as ET

import pytest
from fastapi import HTTPException

from app.services.indonesia_master_import import parse_material_book
from test_indonesia_master_import import workbook, source
from test_indonesia_master_template import rewrite, template_book, S
from test_indonesia_materials import client, workspace
from test_indonesia_master_import import catalog, preview


@pytest.mark.parametrize('dimension', ['A1:CC1048474', 'A1', None])
def test_ignores_formatting_dimensions_but_keeps_sparse_real_rows(dimension):
    def change(parts):
        root = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        bounds = root.find(S+'dimension')
        if dimension is None:
            root.remove(bounds)
        else:
            bounds.set('ref', dimension)
        rows = root.find(S+'sheetData')
        row = rows[-1]
        row.set('r', '800000')
        for cell in row:
            cell.set('r', cell.get('r')[:-1] + '800000')
        ET.SubElement(rows, S+'row', r='1048474', s='0', customFormat='1')
        parts['xl/worksheets/sheet1.xml'] = ET.tostring(root)
    parsed = parse_material_book(rewrite(workbook([source(name='第一款'), source(name='第二款')]), change), '稀疏.xlsx')
    assert [(r['source_row'], r['source']['name']) for r in parsed['rows']] == [(2, '第一款'), (800000, '第二款')]


def test_accepts_photo_archive_above_previous_25_mib_limit():
    output = BytesIO(workbook([source()]))
    with ZipFile(output, 'a', ZIP_STORED) as archive:
        archive.writestr('xl/media/unrelated.bin', b'0' * (26 * 1024 * 1024))
    assert len(parse_material_book(output.getvalue(), '较大文件.xlsx')['rows']) == 1


def test_unselected_product_photos_do_not_consume_selected_image_budget(monkeypatch):
    from app.services import indonesia_master_workbook as photos
    monkeypatch.setattr(photos, 'IMAGE_TOTAL_LIMIT', 200)
    # Four rows have individual images. Only the requested product uses the budget.
    def change(parts):
        root = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        for cell in root.findall('.//'+S+'c'):
            if cell.get('r') in {'D4', 'D5', 'D6'}:
                cell.find('.//'+S+'t').text = 'OTHER'
        parts['xl/worksheets/sheet1.xml'] = ET.tostring(root)
    parsed = parse_material_book(rewrite(template_book(), change), '图片.xlsx', product_codes=['40149'])
    rows = {r['source_row']: r for r in parsed['rows']}
    assert 'image_data' in rows[7]['source']
    assert all('image_data' not in rows[n]['source'] for n in (4, 5, 6))


def test_real_material_row_limit_is_not_relaxed():
    with pytest.raises(HTTPException, match='2000'):
        parse_material_book(workbook([source() for _ in range(2001)]), '过多.xlsx')


@pytest.mark.parametrize('limit', ['bytes', 'expanded', 'entries', 'xml'])
def test_resource_limits_remain_bounded(monkeypatch, limit):
    from app.services import indonesia_master_archive as archive_rules, indonesia_master_import as importer
    content = workbook([source()])
    if limit == 'bytes':
        monkeypatch.setattr(importer, 'MAX_FILE_BYTES', len(content)-1)
    elif limit == 'expanded':
        monkeypatch.setattr(archive_rules, 'MAX_EXPANDED_BYTES', 1)
    elif limit == 'entries':
        monkeypatch.setattr(archive_rules, 'MAX_ENTRIES', 1)
    else:
        # Check the XML cap without allocating an 80 MiB fixture.
        with ZipFile(BytesIO(content)) as archive:
            archive.getinfo('xl/worksheets/sheet1.xml').file_size = 80 * 1024 * 1024 + 1
            with pytest.raises(HTTPException, match='单项内容过大'):
                archive_rules.validate_archive(archive)
        return
    with pytest.raises(HTTPException) as raised:
        parse_material_book(content, '受限.xlsx')
    assert raised.value.status_code == (413 if limit == 'bytes' else 422)


def test_api_exact_size_boundary_and_rejection_leave_records_unchanged(client, monkeypatch):
    from app.services import indonesia_master_archive as limits
    _, p, _, _ = catalog(client)
    content = workbook([source()])
    monkeypatch.setattr(limits, 'MAX_FILE_BYTES', len(content))
    staged = preview(client, content, p)
    assert staged['data']['matched_rows'] == 1
    before = workspace(client)
    monkeypatch.setattr(limits, 'MAX_FILE_BYTES', len(content)-1)
    preview(client, content, p, status=413)
    preview(client, b'', p, status=413)
    assert workspace(client) == before


def test_api_admission_precedes_file_read_and_releases_after_error(client, monkeypatch):
    from starlette.datastructures import UploadFile
    from app.api import indonesia_materials as api
    from app.services.indonesia_master_archive import upload_slot
    _, p, _, _ = catalog(client)
    read = UploadFile.read
    reads = []
    async def record_read(self, size=-1):
        reads.append(size)
        return await read(self, size)
    monkeypatch.setattr(UploadFile, 'read', record_read)
    content = workbook([source()])
    with upload_slot():
        preview(client, content, p, status=429)
    assert reads == []
    original = api.run_order_job
    async def failed(*args, **kwargs):
        raise HTTPException(504, '测试读取超时')
    monkeypatch.setattr(api, 'run_order_job', failed)
    before = workspace(client)
    preview(client, content, p, status=504)
    assert workspace(client) == before
    monkeypatch.setattr(api, 'run_order_job', original)
    assert preview(client, content, p)['data']['matched_rows'] == 1


def test_parser_revision_refreshes_preview_without_invalidating_older_drafts(client, monkeypatch):
    from app.services import indonesia_master_import as importer
    _, p, _, _ = catalog(client)
    content = workbook([source()])
    before = preview(client, content, p)
    monkeypatch.setattr(importer, 'PARSER_REVISION', 'next-reader')
    after = preview(client, content, p)
    assert before['id'] != after['id']
    assert before['data']['format_rule'] == after['data']['format_rule']
    assert before['id'] in {r['id'] for r in workspace(client)['records']}


@pytest.mark.parametrize('mode', ['valid', 'external', 'duplicate', 'duplicate_relationship', 'oversized', 'unsupported_formula'])
def test_wps_cell_images_are_static_unique_bounded_and_never_drop_materials(mode):
    def change(parts):
        root = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        for drawing in root.findall(S+'drawing'):
            root.remove(drawing)
        row = next(row for row in root.findall('.//'+S+'row') if row.get('r') == '4')
        cell = ET.SubElement(row, S+'c', r='T4')
        ET.SubElement(cell, S+'f').text = '_xlfn.DISPIMG("ID_PHOTO",1)' if mode != 'unsupported_formula' else 'WEBSERVICE("https://example.invalid/")'
        parts['xl/worksheets/sheet1.xml'] = ET.tostring(root)
        picture = '''<xdr:pic xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:nvPicPr><xdr:cNvPr id="1" name="ID_PHOTO"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rIdPhoto"/></xdr:blipFill></xdr:pic>'''
        parts['xl/cellimages.xml'] = ('<cellImages>' + picture * (2 if mode == 'duplicate' else 1) + '</cellImages>').encode()
        target = 'https://example.invalid/photo.png' if mode == 'external' else 'media/image1.png'
        external = 'TargetMode="External"' if mode == 'external' else ''
        parts['xl/_rels/cellimages.xml.rels'] = f'<Relationships><Relationship Id="rIdPhoto" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}" {external}/></Relationships>'.encode()
        if mode == 'duplicate_relationship':
            parts['xl/_rels/cellimages.xml.rels'] = parts['xl/_rels/cellimages.xml.rels'].replace(b'</Relationships>', b'<Relationship Id="rIdPhoto" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/></Relationships>')
        if mode == 'oversized':
            parts['xl/media/image1.png'] = b'x' * 1500001
    parsed = parse_material_book(rewrite(template_book(), change), 'WPS.xlsx', product_codes=['40149'])
    row = next(r for r in parsed['rows'] if r['source_row'] == 4)
    assert row['source']['name'] == '子弹筒'
    assert len(parsed['rows']) == 6
    if mode == 'valid':
        assert row['source']['image_data'].startswith('data:image/png;base64,')
    else:
        assert 'image_data' not in row['source']
        assert any('图片' in warning for warning in row['warnings'])
