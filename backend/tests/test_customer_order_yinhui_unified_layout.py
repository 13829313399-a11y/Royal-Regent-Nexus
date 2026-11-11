from copy import copy
from datetime import date
from io import BytesIO

import openpyxl
import pytest
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.services import customer_order_huaxing_unified as huaxing
from app.services import customer_order_unified as unified
from app.services import customer_order_yinhui_unified as yinhui


def serialize(book):
    result = BytesIO()
    book.save(result)
    return result.getvalue()


def template(variant=True, room=1):
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name in unified.SHEETS:
        sheet = book.create_sheet(name)
        headers = list(unified.ITEM_HEADERS if name == 'ITEM表' else unified.ORDER_HEADERS)
        if variant and name == 'ITEM表':
            headers[25:25] = ['放版日期', '抽版日期']
        if variant and name == '接单表':
            headers.remove('订单类型')
        for col, value in enumerate(headers, 1):
            sheet.cell(3, col, value)
            sheet.cell(4, col).font = Font(name='Arial', size=12, color='000000')
            sheet.cell(4, col).fill = PatternFill('solid', fgColor='FFFFEE')
            sheet.cell(4, col).alignment = Alignment(wrap_text=True)
        cols = yinhui.columns(sheet)
        for field, value in {'reference_no': 'OLD-SO', 'po_no': 'OLD-PO', 'product_no': 'OLD-ITEM',
                             'quantity': 100, 'units_per_carton': 10,
                             'requested_ship_date': date(2026, 12, 20)}.items():
            sheet.cell(4, cols[field], value)
        sheet.row_dimensions[4].height = 33
        end = 5 + room
        qty = openpyxl.utils.get_column_letter(cols['quantity'])
        sheet.cell(end, cols['quantity'] - 1, '合计')
        sheet.cell(end, cols['quantity'], f'=SUM({qty}4:{qty}4)')
        sheet.cell(end + 1, 1, '已走货')  # No cancel marker is required.
        sheet.cell(end + 2, cols['product_no'], 'SHIPPED-ITEM')
        sheet.cell(end + 2, cols['reference_no'], 'SHIPPED-SO')
        sheet.cell(end + 2, cols['quantity'], 200)
        sheet.cell(end + 2, cols['requested_ship_date'], date(2026, 9, 1))
        sheet.print_area = f'A1:{openpyxl.utils.get_column_letter(len(headers))}{end + 2}'
    book['ITEM表']['Z4'], book['ITEM表']['AA4'] = ('人工放版', '人工抽版') if variant else ('旧走货', '旧验货')
    book['接单表']['XFD2'].fill = PatternFill('solid', fgColor='ABCDEF')
    book.create_sheet('原件附页')['A1'] = '人工数据，必须保留'
    book['原件附页']['B1'] = "='ITEM表'!H8"
    return book


def row(index=1):
    return dict(id=str(index), _huaxing_customer='yinhui', item_sheet_name='ITEM表',
                received_date='2026-11-05', order_type='正式PO', reference_no=f'NEW-SO-{index}',
                contract_no='', po_no=f'NEW-PO-{index}', product_no=f'00123-{index}',
                customer_name='CUSTOMER', product_name_en='Toy', quantity='120',
                units_per_carton='12', unit_price_usd='2.91', unit_price_hkd='22.5525',
                requested_ship_date='2027-03-15', customer_q='2027-03-10', remarks='note', issues=[])


def test_variant_header_validation_is_yinhui_only_and_history_reads_shifted_date():
    content = serialize(template())
    unified.ensure_unified_schedule('silverlit.xlsx', content, factory_id='huaxing', customer_code='yinhui')
    for factory, customer in [('huaxing', 'maxx'), ('huakang-a', '360'), ('huakang-b', 'yinhui')]:
        with pytest.raises(unified.CustomerOrderUnifiedError):
            unified.ensure_unified_schedule('silverlit.xlsx', content, factory_id=factory, customer_code=customer)
    history = unified.read_unified_history(content, factory_id='huaxing', customer_code='yinhui')
    assert [(h.reference_no, h.requested_ship_date) for h in history] == [
        ('OLD-SO', '2026-12-20T00:00:00'), ('SHIPPED-SO', '2026-09-01T00:00:00')]


@pytest.mark.parametrize('variant', [False, True])
def test_three_sheets_bind_by_headers_preserve_manual_dates_styles_and_prices(variant):
    book = template(variant)
    before_cells = len(book['接单表']._cells)
    source_style = copy(book['ITEM表']['H4']._style)
    huaxing.export_rows(book, [row()])
    item = book['ITEM表']
    cols = yinhui.columns(item)
    assert item.cell(5, cols['requested_ship_date']).value == date(2027, 3, 15)
    assert item['H5'].value == '00123-1' and item['H5'].data_type == 's'
    assert item['M5'].value == '=K5/L5'
    assert item['H5']._style == source_style
    if variant:
        assert item['Z4'].value == '人工放版' and item['AA4'].value == '人工抽版'
        assert item['Z5'].value is None and item['AA5'].value is None
    for name in ('接单表', '正单评审表'):
        sheet = book[name]
        mapping = yinhui.columns(sheet)
        assert sheet.cell(5, mapping['product_no']).value == '00123-1'
        assert sheet.cell(5, mapping['unit_price_usd']).value == 2.91
        assert sheet.cell(5, mapping['unit_price_hkd']).value == 22.5525
        assert sheet.cell(5, mapping['quantity']).value == '=IF(LEN(\'ITEM表\'!K5)=0,"",\'ITEM表\'!K5)'
        assert sheet.cell(5, mapping['requested_ship_date']).value.endswith(f"'ITEM表'!{'AB' if variant else 'Z'}5)")
        qty = openpyxl.utils.get_column_letter(mapping['quantity'])
        assert sheet.cell(6, mapping['quantity']).value == f'=SUM({qty}4:{qty}5)'
        assert sheet.cell(8, mapping['product_no']).value == 'SHIPPED-ITEM'
    assert book['接单表']['XFD2'].fill.fgColor.rgb == '00ABCDEF'
    assert len(book['接单表']._cells) < before_cells + 100
    assert book['原件附页']['A1'].value == '人工数据，必须保留'


def test_insert_shortfall_moves_shipped_and_formula_references_without_overwriting_manual_rows():
    book = template(room=1)
    item = book['ITEM表']
    item['AF5'] = '保留此空白行上的手填内容'
    item.merge_cells('A7:C7')
    validation = DataValidation(type='list', formula1='"A,B"')
    validation.add('G4')
    item.add_data_validation(validation)
    huaxing.export_rows(book, [row(1), row(2)])
    assert item['AF5'].value == '保留此空白行上的手填内容'
    assert [item[f'H{r}'].value for r in (6, 7, 10)] == ['00123-1', '00123-2', 'SHIPPED-ITEM']
    assert item['K8'].value == '=SUM(K4:K7)'
    assert 'A9:C9' in item.merged_cells
    assert 'G6' in validation.cells and 'G7' in validation.cells
    assert book['原件附页']['B1'].value == "='ITEM表'!H10"
    assert str(item.print_area).endswith('$AF$10')
    # The two summaries have an extra available row and insert just one row.
    assert book['接单表']['F9'].value == 'SHIPPED-ITEM'
    assert book['接单表']['I5'].value.endswith("'ITEM表'!K6)")
    assert book['接单表']['I6'].value.endswith("'ITEM表'!K7)")


@pytest.mark.parametrize('header', ['SO#/Reference', '客要求走货期', '單价USD'])
def test_ambiguous_or_missing_required_headers_reject_before_writing(header):
    book = template()
    book['接单表']['T3'] = header
    if header == '單价USD':
        book['接单表']['O3'] = header
    with pytest.raises(unified.CustomerOrderUnifiedError, match='缺失或重复'):
        yinhui.validate(book)


def test_no_boundary_is_actionable_and_duplicate_export_stays_red_and_sparse():
    book = template()
    data = row()
    data['issues'] = [{'code': 'existing_order_line'}]
    huaxing.export_rows(book, [data])
    assert book['接单表']['F5'].font.color.rgb == 'FFFF0000'
    assert len(book['接单表']._cells) < 200
    book = template()
    book['ITEM表']['J6'] = None
    book['ITEM表']['A7'] = None
    with pytest.raises(unified.CustomerOrderUnifiedError, match='边界'):
        huaxing.export_rows(book, [row()])


def test_source_usd_price_is_carried_to_unified_row_without_historical_fallback():
    result = {}
    huaxing.map_record(result, {'so_no': 'SO123', 'contract_no': 'PO456', 'unit_price_usd': 2.91}, 'yinhui')
    assert result['unit_price_usd'] == '2.91'


def test_preview_blocks_conflicting_pack_until_explicit_confirmation_and_exports_manual_value(monkeypatch):
    from app.services.huaxing_order_legacy import yinhui_po_parser
    from app.services.customer_order_manual import decorate_manual_resolution_policy
    record = dict(item_no='SOURCE-ITEM', so_no='NEW-SO', contract_no='NEW-PO',
                  quantity=120, case_pack=12, customer='CUSTOMER', product_name='TOY',
                  po_ship_date='2099-03-15', unit_price_usd=2.91, total_usd=349.2,
                  source_review_flags=[dict(severity='blocked', code='case_pack_source_conflict',
                                           field='units_per_carton', text='表格12与备注6冲突，请核对')])
    monkeypatch.setattr(yinhui_po_parser, 'parse_po', lambda *args: {'rows': [dict(record)], 'warnings': []})
    args = dict(customer_code='yinhui', factory_id='huaxing', received_date='2026-11-05',
                po_files=[('test.pdf', b'test')], schedule_file_name='test.xlsx', schedule_content=serialize(template()))
    preview = decorate_manual_resolution_policy(unified.create_unified_customer_preview(**args))
    assert preview['preview_schema_version'].endswith('-yinhui-layout-v1')
    assert preview['rows'][0]['units_per_carton'] == '12'
    assert preview['rows'][0]['unit_price_usd'] == '2.91'
    issue = next(i for i in preview['rows'][0]['issues'] if i['code'] == 'case_pack_source_conflict')
    assert issue['can_edit'] and issue['edit_field'] == 'units_per_carton'
    with pytest.raises(unified.CustomerOrderUnifiedError, match='仍有阻断项'):
        unified.export_unified_customer_schedule(**args)
    keys = {i['skip_key'] for r in preview['rows'] for i in r['issues'] if i.get('can_skip')}
    content, _, _ = unified.export_unified_customer_schedule(
        **args, skipped_issue_keys=keys,
        manual_overrides=[dict(row_id=preview['rows'][0]['id'], field='units_per_carton', value='6')])
    book = openpyxl.load_workbook(BytesIO(content))
    assert book['ITEM表']['L5'].value == 6
    assert book['接单表']['O5'].value == 2.91
    assert book['接单表']['M5'].value == 22.5525
    assert book['ITEM表']['AB5'].value.date() == date(2099, 3, 15)
    assert '纸箱' in [c.value for c in book['接单表']._cells.values() if c.row == 3]


def test_unreadable_pdf_cannot_silently_disappear_from_batch(monkeypatch):
    from app.services.huaxing_order_legacy import yinhui_po_parser
    monkeypatch.setattr(yinhui_po_parser, 'parse_po', lambda *args: {'rows': [], 'warnings': ['未识别']})
    with pytest.raises(unified.CustomerOrderUnifiedError, match='test.pdf.*本批不会仅导出其他文件'):
        unified.create_unified_customer_preview(
            customer_code='yinhui', factory_id='huaxing', received_date='2026-11-05',
            po_files=[('test.pdf', b'test'), ('other.pdf', b'other')],
            schedule_file_name='test.xlsx', schedule_content=serialize(template()))
