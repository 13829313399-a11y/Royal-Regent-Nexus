from datetime import date
from io import BytesIO
from uuid import uuid4

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


def exported_rows():
    photo = BytesIO()
    Image.new('RGB', (14, 12), 'blue').save(photo, format='JPEG')
    return excel.schedule_workbook([
        {'dateFrom': '2026-11-16', 'dateTo': '2026-11-19', 'customer': '客户甲', 'poNo': '00012',
         'productNo': '00002', 'customerPo': '00091', 'quantity': '20', 'unitsPerCarton': '4',
         'cartonCount': '5', 'agency': '客验', 'result': 'PASS', 'inspectionProblem': '需核对箱唛',
         'remark': '=原样保留\n第二行', 'inspectionExecution': {'sampleQuantity': '0', 'inspector': '张三'},
         'photos': [photo.getvalue()]},
        {'dateFrom': '2026-11-20', 'customer': '客户甲', 'poNo': '00012', 'productNo': '00002', 'quantity': '0'},
    ])


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
