from copy import copy
from io import BytesIO
import openpyxl
import pytest
from openpyxl.comments import Comment
from app.services import customer_order_huadeng_headers as headers, customer_order_unified as service
from test_customer_order_unified import _template_bytes, _parsed_row


@pytest.mark.parametrize('customer', headers.CUSTOMERS)
@pytest.mark.parametrize('header', (3, 4))
def test_extensions_preserve_existing_cells_and_meanings_and_are_idempotent(customer, header):
    book = openpyxl.load_workbook(BytesIO(_template_bytes()))
    sheet = book['ITEM表']
    if header == 4:
        sheet.insert_rows(3)
    existing = ['交仓日期', '柜型/车型', 'COO证书', '品牌', '验货报告编码', '柜号/车']
    for column, label in enumerate(existing, 31):
        sheet.cell(header, column, label)
        sheet.cell(header+1, column, '保留原值')
    sheet.cell(header+2, 37, '=1+2').comment = Comment('original comment', 'User')
    sheet.column_dimensions['AK'].width = 23
    before = {pos: (c.value, copy(c._style), c.comment.text if c.comment else None) for pos, c in sheet._cells.items()}
    first = headers.ensure_headers(book, 'huadeng', customer)
    assert headers.ensure_headers(book, 'huadeng', customer) == first
    for pos, value in before.items():
        c = sheet.cell(*pos)
        assert (c.value, c._style, c.comment.text if c.comment else None) == value
    assert sheet.column_dimensions['AK'].width == 23
    assert first['柜号'] == ['AJ']
    assert first['出货日期'] != ['AE']
    assert first['国家'] != ['N']
    assert first['打发票价格'] != first['单价HK']
    assert first['CO证书'] == ['AG']
    assert first['品牌名'] == ['AH']
    assert first['报告编号'] == ['AI']
    assert all(sheet[f'{cols[0]}{header}'].value for cols in first.values())


def test_other_factory_unchanged():
    book = openpyxl.load_workbook(BytesIO(_template_bytes()))
    before = {(s.title, c.coordinate): c.value for s in book for c in s._cells.values()}
    assert headers.ensure_headers(book, 'huakang-a', 'zuru') == {}
    assert {(s.title, c.coordinate): c.value for s in book for c in s._cells.values()} == before


def test_casdon_price_aliases_remain_single_existing_columns():
    from app.services.customer_order_casdon import prepare_money, money_columns
    book = openpyxl.load_workbook(BytesIO(_template_bytes()))
    item = book['ITEM表']
    for c, label in enumerate(('港币单价', '港币金额', '美元单价', '美元金额'), 31):
        item.cell(3, c, label)
        item.cell(4, c, 123)
    ensure = headers.ensure_headers(book, 'huadeng', 'casdon')
    prepare_money(book)
    assert money_columns(book) == [31,32,33,34]
    assert headers.ensure_headers(book, 'huadeng', 'casdon') == ensure
    assert [item.cell(4,c).value for c in range(31,35)] == [123]*4


def test_unmatched_jakks_cancellation_never_creates_order_or_copies_manual_fields(monkeypatch):
    from test_jakks_line_cancel import args, text, p
    monkeypatch.setattr(p, 'extract_text', lambda _: (text(two=False), False))
    params = args(files=[('CXL.pdf', b'cancel')])
    book = openpyxl.load_workbook(BytesIO(params['schedule_content']))
    book['ITEM表']['AE3'] = '发票号'
    book['ITEM表']['AE4'] = '="OLD-INVOICE"'
    stream=BytesIO(); book.save(stream); params['schedule_content']=stream.getvalue()
    output, _, preview = service.export_unified_customer_schedule(**params)
    book = openpyxl.load_workbook(BytesIO(output))
    assert not any(c.value == '取消单' for c in book['ITEM表']['B'])
    assert book['ITEM表']['AE4'].value == '="OLD-INVOICE"'
    assert any('取消未应用' in w for w in preview['warnings'])


@pytest.mark.parametrize('customer', headers.CUSTOMERS)
def test_actual_export_completes_headers_and_only_links_new_prices(customer, monkeypatch):
    row = _parsed_row()
    row.update(_regional_customer=customer, _huadeng_source_currency='USD', unit_price_usd='1.2345', amount_usd='296.28')
    monkeypatch.setattr(service, '_create_customer_rows', lambda *args: ([row], [], 'TEST'))
    original = openpyxl.load_workbook(BytesIO(_template_bytes()))
    for c, label in enumerate(('发票号', '出货日期', '报告编号'), 31):
        original['ITEM表'].cell(3, c, label)
        for r in range(4,7):
            original['ITEM表'].cell(r, c, '="OLD-MANUAL"')
    stream = BytesIO(); original.save(stream); source = stream.getvalue()
    output, _, preview = service.export_unified_customer_schedule(factory_id='huadeng', customer_code=customer,
        received_date='2026-11-19', po_files=[('test.pdf', b'test')], schedule_file_name='schedule.xlsx', schedule_content=source)
    book = openpyxl.load_workbook(BytesIO(output))
    columns = headers.ensure_headers(book, 'huadeng', customer)
    assert len(columns) == len(headers.FIELDS)
    item = book['ITEM表']
    r = next(c.row for c in item['E'] if c.value == 'SO-1')
    for label in ('发票号', '出货日期', '报告编号', '打发票价格'):
        assert item[f'{columns[label][0]}{r}'].value is None
    for label in ('发票号', '出货日期', '报告编号'):
        assert item[f'{columns[label][0]}4'].value == '="OLD-MANUAL"'
    assert "'接单表'!P" in item[f'{columns["单价USD"][0]}{r}'].value
    assert preview['summary']['blocked'] == 0
