from datetime import date
from hashlib import sha256

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
import pytest

from app.services import qc_inspection_print as printing
from app.services import qc_inspection_sheet as journal


def template_workbook(path):
    book = Workbook()
    book.remove(book.active)
    for index, name in enumerate(printing.TEMPLATES):
        sheet = book.create_sheet(name)
        sheet.merge_cells('A1:N1')
        sheet['A1'] = '历史日期标题'
        sheet.merge_cells('A2:N2')
        sheet['A2'] = date(2026, 11, 9)
        for column, header in enumerate(printing.HEADERS, 1):
            sheet.cell(3, column, header)
        sheet['A5'] = date(2026, 11, 9)
        sheet['B5'] = '历史客户'
        sheet['I5'] = '=G5/H5'
        sheet['F6'] = '总数量'
        sheet['G6'] = 99999
        sheet['F8'] = '=G8/I8*K8'
        sheet['I8'] = 240
        sheet['K8'] = 58
        sheet.column_dimensions['N'].width = 13 + index
        sheet.row_dimensions[5].height = 23
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    book.create_sheet('历史资料')['A1'] = '不能出现在打印里'
    book.save(path)
    book.close()


@pytest.mark.parametrize('template', printing.TEMPLATES)
def test_print_fills_confirmed_template_without_carrying_historical_records(tmp_path, template):
    template_file = tmp_path / 'origin.xlsx'
    output = tmp_path / 'print.xlsx'
    template_workbook(template_file)
    before = sha256(template_file.read_bytes()).digest()
    printing.fill_template(template_file, output, template, [
        {'customer': '客户', 'poNo': '000812', 'contractNo': 'C-real',
         'actualDate': '2026-11-16', 'quantity': 40, 'unitsPerCarton': 4, 'cartonCount': 10,
         'result': 'PASS', 'remark': '=NOT_A_FORMULA\n' + '中文内容' * 6},
        {'customer': '客户', 'dateFrom': '2026-11-17', 'poNo': '000813', 'quantity': 0, 'cartonCount': 0},
    ])
    assert sha256(template_file.read_bytes()).digest() == before
    book = load_workbook(output)
    try:
        assert book.sheetnames == [template]
        sheet = book.active
        assert sheet.page_setup.orientation == 'landscape'
        assert sheet.page_setup.paperSize == int(sheet.PAPERSIZE_A4)
        assert sheet.column_dimensions['N'].width == (13 if template == printing.TEMPLATES[0] else 14)
        assert sheet.print_title_rows == '$3:$3'
        assert 'A1:N1' in sheet.merged_cells and 'A2:N2' in sheet.merged_cells
        assert sheet['A2'].value.date() == date(2026, 11, 16)
        assert sheet['C5'].value == '000812'
        assert sheet['I5'].value == '=G5/H5'
        assert sheet['M5'].value == 'PASS'
        assert sheet['N5'].value.startswith('=NOT_A_FORMULA')
        assert sheet['N5'].data_type == 's'
        assert sheet.row_dimensions[5].height > 23
        assert sheet['F8'].data_type == 'f'
        second = next(row for row in sheet.iter_rows() if row[2].value == '000813')
        assert second[0].value is None and second[6].value == 0 and second[8].value == 0
        values = {cell.value for row in sheet for cell in row}
        assert values.isdisjoint({'历史客户', '不能出现在打印里', 'C-real', 99999})
    finally:
        book.close()


def test_print_reads_saved_current_factory_revisions_without_writing(monkeypatch, tmp_path):
    monkeypatch.setattr(journal.settings, 'qc_department_data_dir', str(tmp_path))
    with journal.store(write=True) as connection:
        connection.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,0,0,?)',
                           ('a' * 32, 'huaxing', 'legacy:6', '{"poNo":"0001"}', 'PASS', '', ''))
        connection.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,1,0,?)',
                           ('b' * 32, 'huaxing', 'legacy:7', '{"poNo":"0002"}', '', '', ''))
        connection.execute('INSERT INTO entry_details(entry_id, review_state) VALUES(?,?)',
                           ('b' * 32, 'pending'))
    before = sha256(journal.database_path().read_bytes()).digest()
    identity = {'id': 'a' * 32, 'revision': 0}
    assert printing.saved_records('huaxing', [identity])[0]['poNo'] == '0001'
    for factory, entries, expected in [
        ('huakang-a', [identity], 404),
        ('huaxing', [{**identity, 'revision': 1}], 409),
        ('huaxing', [{'id': 'b' * 32, 'revision': 1}], 409),
        ('huaxing', [], 422),
        ('huaxing', [identity, identity], 422),
    ]:
        with pytest.raises(HTTPException) as error:
            printing.saved_records(factory, entries)
        assert error.value.status_code == expected
    assert sha256(journal.database_path().read_bytes()).digest() == before


def test_print_preserves_individual_template_rows_and_hides_unused_slots(tmp_path):
    from openpyxl.styles import Font, PatternFill
    source, output = tmp_path / 'source.xlsx', tmp_path / 'filled.xlsx'
    template_workbook(source)
    book = load_workbook(source)
    sheet = book[printing.TEMPLATES[0]]
    sheet.insert_rows(6, 2)
    sheet['B6'] = '历史第二行'
    sheet['B7'] = '历史第三行'
    sheet['C7'] = 'PRIVATE-OLD-PO'
    sheet.row_dimensions[6].height = 47
    sheet['B6'].font = Font(name='Arial', size=14, bold=True)
    sheet['B6'].fill = PatternFill('solid', fgColor='FFFF00')
    book.save(source); book.close()
    records = [dict(customer='新客户',poNo='0001',actualDate='2026-11-16',quantity=0),
               dict(customer='新客户',poNo='0002',actualDate='2026-11-16',quantity=2)]
    printing.fill_template(source,output,printing.TEMPLATES[0],records)
    book=load_workbook(output); sheet=book.active
    assert sheet['B6'].font.bold and sheet['B6'].font.sz == 14
    assert sheet['B6'].fill.fgColor.rgb == '00FFFF00'
    assert sheet.row_dimensions[6].height == 47
    assert sheet.row_dimensions[7].hidden
    assert sheet['C7'].value is None
    assert sheet['C5'].value == '0001' and sheet['C6'].value == '0002'
    assert sheet['G8'].value == '=IF(COUNT(G5:G6)=2,SUM(G5:G6),"")'
    assert 'A1:N1' in sheet.merged_cells and 'A2:N2' in sheet.merged_cells
    book.close()


def test_print_expands_bands_and_customer_groups_without_losing_records(tmp_path):
    source, output = tmp_path / 'source.xlsx', tmp_path / 'filled.xlsx'
    template_workbook(source)
    records = [dict(customer='客户'+str(i%3),poNo=str(i).zfill(4),actualDate=f'2026-11-{16+i//7:02}',quantity=i)
               for i in range(50)]
    printing.fill_template(source,output,printing.TEMPLATES[1],records)
    book=load_workbook(output); sheet=book.active
    emitted=[row[2].value for row in sheet if row[2].value not in (None,'PO#')]
    assert sorted(emitted)==sorted(row['poNo'] for row in records)
    assert all(not sheet.row_dimensions[row[0].row].hidden for row in sheet if row[2].value in emitted)
    assert len(sheet.merged_cells.ranges)==9  # original title and eight date bands
    book.close()


def test_fractional_quantities_do_not_round_to_a_different_printed_number(tmp_path):
    source, output = tmp_path / 'source.xlsx', tmp_path / 'filled.xlsx'
    template_workbook(source)
    book=load_workbook(source)
    book[printing.TEMPLATES[0]]['I5'].number_format='0'
    book.save(source); book.close()
    printing.fill_template(source,output,printing.TEMPLATES[0],[dict(customer='A',quantity=3,unitsPerCarton=2,cartonCount=1.5)])
    book=load_workbook(output)
    assert book.active['I5'].value=='=G5/H5'
    assert book.active['I5'].number_format=='0.########'
    book.close()


def test_workbench_excel_uses_desk_fields_dates_and_embedded_photos():
    from io import BytesIO
    from PIL import Image
    from app.services.qc_inspection_schedule_excel import schedule_workbook

    photo = BytesIO()
    Image.new('RGB', (60, 90), 'red').save(photo, 'JPEG')
    record = dict(dateFrom='2026-11-19', poNo='00007', customerPo='00008', country='英国',
                  quantity=20, unitsPerCarton=4, cartonCount=5, result='', cumulativeResult='REJ',
                  inspectionProblem='包装破损', remark='=原文', inspector='旧名',
                  inspectionExecution={'sampleQuantity': 0, 'inspector': '陈工'},
                  photos=[photo.getvalue(), photo.getvalue()])
    sheet = load_workbook(BytesIO(schedule_workbook([record, dict(dateFrom='2026-11-20',
        dateTo='2026-11-21', inspector='林工', sampleQuantity=12)]))).active
    assert [c.value for c in sheet[6]] == (
        '验货日期 客户 PO# 出口国 货号 产品名称 数量 装箱 箱数 生产 机构 客PO# 验货结果 抽查数量 验货问题 备注 照片 检验人员'.split())
    assert [c.value for c in sheet[7]][2:] == [
        '00007', '英国', None, None, 20, 4, '=G7/H7', None, None, '00008',
        None, 0, '包装破损', '=原文', None, '陈工']
    assert sheet['P7'].data_type == 's' and sheet['A7'].value.date() == date(2026, 11, 19)
    assert (sheet['A8'].value, sheet['N8'].value, sheet['R8'].value) == ('11月20日-21日', 12, '林工')
    assert sheet.auto_filter.ref == 'A6:R8' and sheet.freeze_panes == 'A7'
    assert [c.colId for c in sheet.auto_filter.filterColumn if c.hiddenButton] == list(range(1, 18))
    assert len(sheet._images) == 2
    assert all((im.anchor._from.col, im.anchor._from.row, im.anchor.to.row) == (16, 6, 6)
               for im in sheet._images)
