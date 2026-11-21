from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException
from openpyxl import load_workbook
from PIL import Image
import pytest

from app.services import qc_inspection_intake as intake
from app.services import qc_inspection_schedule_excel as excel
from app.services import qc_inspection_sheet as journal


ACTOR = {'id': 'tester', 'name': '验货员'}


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setattr(journal.settings, 'qc_department_data_dir', str(tmp_path))


def manual_entry():
    fields = dict.fromkeys(intake.MANUAL_FIELDS, '')
    fields.update(dateFrom='2026-11-10', customer='原客户', productNo='0001', quantity='20', agency='客验')
    return {'requestKey': str(uuid4()), 'row': fields}


def exported_rows(color='blue'):
    photo = BytesIO()
    Image.new('RGB', (14, 12), color).save(photo, format='JPEG')
    return excel.schedule_workbook([
        {'dateFrom': '2026-11-16', 'dateTo': '2026-11-19', 'customer': '客户甲', 'poNo': '00012',
         'productNo': '00002', 'customerPo': '00091', 'quantity': '20', 'unitsPerCarton': '4',
         'cartonCount': '5', 'agency': '客验', 'result': 'PASS', 'inspectionProblem': '需核对箱唛',
         'remark': '=原样保留\n第二行', 'inspectionExecution': {'sampleQuantity': '0', 'inspector': '张三'},
         'photos': [photo.getvalue()]},
        {'dateFrom': '2026-11-20', 'customer': '客户甲', 'poNo': '00012', 'productNo': '00002', 'quantity': '0'},
    ])


def repack(content, comment=b'same rows, different file bytes'):
    stream = BytesIO(content)
    with ZipFile(stream, 'a') as book:
        book.comment = comment
    return stream.getvalue()


def confirm(content, factory='huaxing'):
    preview = intake.workbook(factory, ACTOR, content)
    return intake.workbook(factory, ACTOR, content, preview['digest'])


def test_preview_and_append_export_same_rows_without_overwriting():
    entry = manual_entry()
    assert intake.manual('huaxing', ACTOR, entry) == {'count': 1, 'existing': 0}
    assert intake.manual('huaxing', ACTOR, entry) == {'count': 0, 'existing': 1}
    original, = journal.sync('huaxing', [])['items']
    assert original['sourceRecord']['agency'] == '客验'
    content = exported_rows()
    preview = intake.workbook('huaxing', ACTOR, content)
    assert len(preview['rows']) == 2
    assert journal.sync('huaxing', [])['items'] == [original]
    row = preview['rows'][0]
    assert (row['dateFrom'], row['dateTo'], row['poNo'], row['productNo'], row['customerPo']) == (
        '2026-11-16', '2026-11-19', '00012', '00002', '00091')
    assert (row['cartonCount'], row['sampleQuantity'], row['photos']) == ('5', '0', 1)
    assert preview['rows'][1]['quantity'] == '0'
    with pytest.raises(HTTPException) as error:
        intake.workbook('huaxing', ACTOR, content, 'changed')
    assert error.value.status_code == 409
    assert intake.workbook('huaxing', ACTOR, content, preview['digest']) == {'count': 2, 'existing': 0}
    assert intake.workbook('huaxing', {'id': 'other', 'name': '同事'}, content, preview['digest']) == {'count': 0, 'existing': 2}
    current = journal.workbench_items(journal.sync('huaxing', [])['items'])
    assert len(current) == 3 and original in current
    saved = next(item for item in current if item['dateTo'] == '2026-11-19')
    assert saved['result'] == 'PASS' and saved['reviewState'] == ''
    assert saved['remark'] == '=原样保留\n第二行' and saved['inspectionProblem'] == '需核对箱唛'
    assert saved['inspectionExecution'] == {'sampleQuantity': '0', 'inspector': '张三'}
    assert journal.read_photo('huaxing', saved['id'], saved['photos'][0]['id'])[0]
    assert journal.sync('huakang-a', [])['items'] == []


def test_invalid_excel_row_prevents_entire_batch():
    book = load_workbook(BytesIO(exported_rows()))
    book.active['C8'] = '=A7'
    corrupt = BytesIO()
    book.save(corrupt)
    book.close()
    with pytest.raises(HTTPException, match='第 8 行'):
        intake.workbook('huaxing', ACTOR, corrupt.getvalue())
    assert not journal.database_path().exists()


def test_legacy_date_bands_and_subtotals_are_not_records(monkeypatch):
    row = ['11月16日-19日', '客户甲', '00012', 'UK', '00021', '玩具', 20, 4, 5, '组装', '客验', '00096', '旧完成状态', '备注']
    band = [date(2026, 11, 20), *([''] * 13)]
    total = ['', '', '', '', '', '总数量', 20, '', '', '', '', '', '', '']
    ratio = ['', '', '', '', '', 12.5, 20, '', 5, '', 3, '', '', '']
    rows = [['标题'], [date(2026, 11, 16)], intake.LEGACY_HEADERS, row, total, ratio, band, intake.LEGACY_HEADERS,
            [date(2026, 11, 20), *row[1:]]]
    monkeypatch.setattr(intake, 'read_xls', lambda _: (rows, {}))
    name, parsed = intake.parse(bytes.fromhex('d0cf11e0a1b11ae1'))
    assert name == intake.LEGACY_SHEET
    assert [item['line'] for item in parsed] == [4, 9]
    assert parsed[0]['fields']['dateTo'] == '2026-11-19'
    assert parsed[1]['fields']['dateFrom'] == '2026-11-20'
    assert parsed[0]['fields']['completion'] == '旧完成状态' and 'result' not in parsed[0]['fields']


def test_preview_marks_existing_and_same_workbook_rows_without_initializing_store():
    row = manual_entry()['row']
    raw = excel.schedule_workbook([row, dict(row)])
    preview = intake.workbook('huaxing', ACTOR, raw)
    assert not journal.database_path().exists()
    assert (preview['count'], preview['existing']) == (1, 1)
    assert [r['duplicate'] for r in preview['rows']] == [False, True]
    intake.manual('huaxing', ACTOR, manual_entry())
    old, = journal.sync('huaxing', [])['items']
    assert intake.workbook('huaxing', ACTOR, raw, preview['digest']) == {'count': 0, 'existing': 2}
    assert journal.sync('huaxing', [])['items'] == [old]
    assert confirm(raw, 'huakang-a') == {'count': 1, 'existing': 1}


def test_different_file_same_fields_and_workbench_photo_reexport():
    raw = exported_rows()
    assert confirm(raw) == {'count': 2, 'existing': 0}
    original = journal.sync('huaxing', [])['items']
    edited_container = repack(raw)
    p = intake.workbook('huaxing', ACTOR, edited_container)
    assert (p['count'], p['existing']) == (0, 2)
    assert all(r['duplicate'] for r in p['rows'])
    assert edited_container != raw
    assert confirm(edited_container) == {'count': 0, 'existing': 2}
    reexport = excel.export('huaxing', {'entries': [{'id': r['id'], 'revision': r['revision']} for r in original]})
    assert intake.parse(reexport)[1][0]['photos'][0][0] != intake.parse(raw)[1][0]['photos'][0][0]
    assert confirm(reexport) == {'count': 0, 'existing': 2}
    assert journal.sync('huaxing', [])['items'] == original

    changed_photo = exported_rows('green')
    assert confirm(changed_photo) == {'count': 1, 'existing': 1}
    assert all(row in journal.sync('huaxing', [])['items'] for row in original)


def test_mixed_batch_first_row_skipped_and_retry_preserves_existing():
    raw = exported_rows()
    confirm(raw)
    original = journal.sync('huaxing', [])['items']
    book = load_workbook(BytesIO(raw))
    book.active['P8'] = '只改第二条备注'
    output = BytesIO()
    book.save(output)
    book.close()
    changed = output.getvalue()
    preview = intake.workbook('huaxing', ACTOR, changed)
    assert [r['duplicate'] for r in preview['rows']] == [True, False]
    assert confirm(changed) == {'count': 1, 'existing': 1}
    current = journal.sync('huaxing', [])['items']
    assert len(current) == 3 and all(row in current for row in original)
    added, = [row for row in current if row['remark'] == '只改第二条备注']
    journal.save('huaxing', added['id'], {'revision': added['revision'], 'result': '', 'remark': '后来编辑'}, ACTOR)
    after_edit = journal.sync('huaxing', [])['items']
    assert confirm(changed) == {'count': 0, 'existing': 2}
    assert journal.sync('huaxing', [])['items'] == after_edit


def test_effective_saved_fields_and_literal_identifiers_are_compared():
    body = manual_entry()
    body['row'].update(poNo='00019', unitsPerCarton='4', quantity='20.00', cartonCount='5')
    intake.manual('huaxing', ACTOR, body)
    existing, = journal.sync('huaxing', [])['items']
    journal.save('huaxing', existing['id'], {'revision': existing['revision'], 'result': 'FAIL',
                 'remark': '第一行\r\n第二行', 'inspectionProblem': '问题',
                 'inspectionExecution': {'sampleQuantity': '0', 'inspector': '现有验货员'}}, ACTOR)
    row = {**body['row'], 'quantity': '20', 'remark': '第一行\n第二行', 'result': 'FAIL',
           'sampleQuantity': '0', 'inspectionProblem': '问题', 'inspector': '现有验货员'}
    assert confirm(excel.schedule_workbook([row])) == {'count': 0, 'existing': 1}
    for change in ({'poNo': '19'}, {'sampleQuantity': ''}, {'result': 'PASS'}, {'inspectionProblem': ''},
                   {'inspector': '另一位验货员'}, {'dateTo': '2026-11-11'}):
        assert confirm(excel.schedule_workbook([{**row, **change}])) == {'count': 1, 'existing': 0}


def test_legacy_completion_is_original_data_not_derived_status(monkeypatch):
    def legacy_file(value):
        return bytes.fromhex('d0cf11e0a1b11ae1') + value.encode()

    def read(raw):
        completion = '待复检' if raw.endswith(b'changed') else '已完成'
        row = [date(2026, 11, 20), '客户', '00012', '', '00021', '', 20, 4, 5, '', '客验', '', completion, '备注']
        return ([['标题'], [date(2026, 11, 20)], intake.LEGACY_HEADERS, row], {})

    monkeypatch.setattr(intake, 'read_xls', read)
    assert confirm(legacy_file('first')) == {'count': 1, 'existing': 0}
    old, = journal.sync('huaxing', [])['items']
    assert old['completion'] == '未完成' and old['sourceRecord']['completion'] == '已完成'
    assert confirm(legacy_file('repacked')) == {'count': 0, 'existing': 1}
    assert confirm(legacy_file('changed')) == {'count': 1, 'existing': 0}
    assert old in journal.sync('huaxing', [])['items']


def test_concurrent_confirmations_of_different_files_check_in_the_write_transaction():
    raw = excel.schedule_workbook([manual_entry()['row']])
    other = repack(raw)
    content = [raw, other]
    previews = [intake.workbook('huaxing', ACTOR, candidate) for candidate in content]
    assert [p['count'] for p in previews] == [1, 1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        commits = [pool.submit(intake.workbook, 'huaxing', ACTOR, data, p['digest'])
                   for data, p in zip(content, previews)]
        assert sorted((f.result()['count'], f.result()['existing']) for f in commits) == [(0, 1), (1, 0)]
    assert len(journal.sync('huaxing', [])['items']) == 1
