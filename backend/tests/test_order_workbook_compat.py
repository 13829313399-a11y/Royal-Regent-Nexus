from io import BytesIO
from zipfile import ZipFile

from lxml import etree as ET
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table, TableColumn, TableFormula
from openpyxl.worksheet.filters import AutoFilter, SortState, SortCondition
import pytest

from app.services.order_workbook_compat import normalize_table_ranges, MAIN
from app.services import customer_order_unified as unified
from test_customer_order_casdon_workbook import fixture, content
from test_casdon_original_sku import casdon_po

NS = {'m': MAIN}


def rewrite(blob, replacements):
    output = BytesIO()
    with ZipFile(BytesIO(blob)) as source, ZipFile(output, 'w') as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            target.writestr(info, replacements[info.filename](raw) if info.filename in replacements else raw)
    return output.getvalue()


@pytest.fixture(scope='module')
def wide_table():
    book = fixture()
    sheet = book['ITEM表']
    names = [f'字段{i}' for i in range(1, 48)] + [f'列{i}' for i in range(1, 16338)]
    for column, label in enumerate(names, 1):
        sheet.cell(13, column, label)
    sheet['AD14'].comment = Comment('历史出货备注', '业务')
    sheet['AD14'].font = Font(color='123456')
    table = Table(displayName='ArchiveTable', ref='A13:XFD20',
                  tableColumns=[TableColumn(id=i, name=n) for i, n in enumerate(names, 1)],
                  autoFilter=AutoFilter(ref='A13:XFD20'))
    sheet.add_table(table)
    valid = content(book)
    malformed = rewrite(valid, {'xl/tables/table1.xml': lambda raw: raw.replace(b'ref="A13:XFD20"', b'ref="13:20"', 1)})
    return valid, malformed


def test_valid_tables_are_byte_identical(wide_table):
    valid, _ = wide_table
    assert normalize_table_ranges(valid) == (valid, [])


def test_wps_whole_rows_preserve_business_cells_and_native_parts(wide_table):
    valid, malformed = wide_table
    with pytest.raises(ValueError):
        openpyxl.load_workbook(BytesIO(malformed))
    repaired, notes = normalize_table_ranges(malformed)
    assert notes and normalize_table_ranges(repaired) == (repaired, [])
    with ZipFile(BytesIO(malformed)) as before, ZipFile(BytesIO(repaired)) as after:
        assert after.testzip() is None
        assert before.namelist() == after.namelist()
        assert {n for n in before.namelist() if before.read(n) != after.read(n)} == {
            'xl/tables/table1.xml', 'xl/worksheets/sheet1.xml'}
    before = openpyxl.load_workbook(BytesIO(valid))
    after = openpyxl.load_workbook(BytesIO(repaired))
    sheet = after['ITEM表']
    assert sheet.tables['ArchiveTable'].ref == 'A13:AU20'
    assert sheet.tables['ArchiveTable'].autoFilter.ref == 'A13:AU20'
    assert len(sheet.tables['ArchiveTable'].tableColumns) == 47
    assert sheet.max_column == 47
    for name in before.sheetnames:
        for (r, c), cell in before[name]._cells.items():
            if name == 'ITEM表' and r == 13 and c > 47:
                continue
            other = after[name].cell(r, c)
            assert (other.value, other.data_type, other._style) == (cell.value, cell.data_type, cell._style)
            assert (other.comment.text if other.comment else None) == (cell.comment.text if cell.comment else None)
            assert other.hyperlink == cell.hyperlink


@pytest.mark.parametrize('extra', ['value', 'formula', 'comment', 'hyperlink', 'structured',
                                 'whole_table', 'table_headers', 'lowercase', 'whole_column',
                                 'whole_column_end', 'whole_row', 'indirect', 'offset',
                                 'native_formula', 'native_total', 'filter'])
def test_meaningful_tail_is_never_removed(wide_table, extra):
    valid, _ = wide_table
    book = openpyxl.load_workbook(BytesIO(valid))
    sheet = book['ITEM表']
    if extra == 'value':
        sheet['AV14'] = '业务手填'
    elif extra == 'formula':
        sheet['AV14'] = '=1+2'
    elif extra == 'comment':
        sheet['AV13'].comment = Comment('保留', '业务')
    elif extra == 'hyperlink':
        sheet['AV13'].hyperlink = 'https://example.com'
    elif extra == 'structured':
        book['接单表']['H4'] = '=COUNTA(ArchiveTable[列1])'
    elif extra == 'whole_column':
        book['接单表']['H4'] = "=COUNTA('ITEM表'!AV:AV)"
    elif extra == 'lowercase':
        book['接单表']['H4'] = "=COUNTA('ITEM表'!av:av)"
    elif extra == 'whole_table':
        book['接单表']['H4'] = '=COLUMNS(ArchiveTable)'
    elif extra == 'table_headers':
        book['接单表']['H4'] = '=COUNTA(ArchiveTable[#Headers])'
    elif extra == 'native_formula':
        sheet.tables['ArchiveTable'].tableColumns[0].calculatedColumnFormula = TableFormula(attr_text='COLUMNS(ArchiveTable)')
    elif extra == 'native_total':
        sheet.tables['ArchiveTable'].tableColumns[0].totalsRowFormula = TableFormula(attr_text='COUNTA(ArchiveTable[列1])')
    elif extra == 'whole_row':
        book['接单表']['H4'] = "=COUNTA('ITEM表'!$13:$13)"
    elif extra == 'whole_column_end':
        book['接单表']['H4'] = "=COUNTA('ITEM表'!$a:$av)"
    elif extra == 'indirect':
        book['接单表']['H4'] = '=COUNTA(INDIRECT("AV"&13))'
    elif extra == 'offset':
        book['接单表']['H4'] = '=COUNTA(OFFSET(A13,0,47))'
    else:
        sheet.tables['ArchiveTable'].autoFilter.add_filter_column(47, ['保留'])
    malformed = rewrite(content(book), {'xl/tables/table1.xml': lambda raw: raw.replace(b'ref="A13:XFD20"', b'ref="13:20"', 1)})
    repaired, notes = normalize_table_ranges(malformed)
    with ZipFile(BytesIO(malformed)) as before, ZipFile(BytesIO(repaired)) as after:
        assert {n for n in before.namelist() if before.read(n) != after.read(n)} == {'xl/tables/table1.xml'}
    assert openpyxl.load_workbook(BytesIO(repaired))['ITEM表'].tables['ArchiveTable'].ref == 'A13:XFD20'


def test_inconsistent_metadata_is_not_guessed(wide_table):
    _, malformed = wide_table
    wrong = rewrite(malformed, {'xl/tables/table1.xml': lambda raw: raw.replace(b'count="16384"', b'count="47"')})
    with pytest.raises(ValueError, match='不一致'):
        normalize_table_ranges(wrong)


def test_casdon_preview_and_export_with_wps_archive_table(wide_table):
    _, malformed = wide_table
    args = dict(factory_id='huadeng', customer_code='casdon', received_date='2026-11-26',
        po_files=[('new.pdf', casdon_po())], schedule_file_name='casdon.xlsx', schedule_content=malformed)
    preview = unified.create_unified_customer_preview(**args)
    assert [r['product_no'] for r in preview['rows']] == ['30050', '30050.TAR001']
    blob, _, _ = unified.export_unified_customer_schedule(**args)
    book = openpyxl.load_workbook(BytesIO(blob))
    sheet = book['ITEM表']
    native = sheet.tables['ArchiveTable']
    assert native.ref == native.autoFilter.ref == 'A15:AU22'
    assert sheet['AD16'].comment.text == '历史出货备注'
    assert sheet['AD16'].font.color.rgb == '00123456'
    assert sheet['AD4'].value == '原始备注'
    assert sheet['K7'].value == '=SUM(K4:K6)'
    assert sum(c.value == '0000099991' for c in sheet._cells.values() if c.column == 5) == 2
    assert sheet.max_column < 100


def test_table_sort_and_filter_follow_inserted_rows():
    from app.services.huakang_a_order_legacy.unified_schedule import _insert_rows
    book = openpyxl.Workbook()
    sheet = book.active
    table = Table(displayName='History', ref='A10:C20', autoFilter=AutoFilter(ref='A10:C20',
        sortState=SortState(ref='A11:C20', sortCondition=[SortCondition(ref='B11:B20') ])),
        sortState=SortState(ref='A11:C20', sortCondition=[SortCondition(ref='C11:C20')]))
    sheet.add_table(table)
    _insert_rows(book, sheet, 5, 2)
    assert table.ref == table.autoFilter.ref == 'A12:C22'
    assert table.sortState.ref == table.autoFilter.sortState.ref == 'A13:C22'
    assert table.sortState.sortCondition[0].ref == 'C13:C22'
    assert table.autoFilter.sortState.sortCondition[0].ref == 'B13:B22'


def test_empty_sort_metadata_does_not_break_insertion():
    from app.services.huakang_a_order_legacy.unified_schedule import _insert_rows
    book = openpyxl.Workbook()
    table = Table(displayName='EmptySort', ref='A10:C20',
        autoFilter=AutoFilter(ref='A10:C20', sortState=SortState()),
        sortState=SortState(sortCondition=[SortCondition()]))
    book.active.add_table(table)
    _insert_rows(book, book.active, 5, 1)
    assert table.ref == table.autoFilter.ref == 'A11:C21'
    assert table.sortState.ref is None
    assert table.sortState.sortCondition[0].ref is None
