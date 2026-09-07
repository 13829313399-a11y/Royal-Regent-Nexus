from copy import copy
from io import BytesIO

import openpyxl
import pytest
from openpyxl.worksheet.formula import ArrayFormula

from app.services import customer_order_unified as service
from app.services.huakang_a_order_legacy import unified_schedule as mapping


def template(customer):
    w = openpyxl.Workbook()
    w.remove(w.active)
    for name, marker in ((service.ITEM_SHEET, 8), (service.ORDER_SHEET, 6), (service.REVIEW_SHEET, 7)):
        s = w.create_sheet(name)
        headers = service.ITEM_HEADERS[:29] + mapping.ITEM_TAILS[customer] if name == service.ITEM_SHEET else service.ORDER_HEADERS
        for c, value in enumerate(headers, 1):
            s.cell(3, c, value)
        s.cell(marker, 1, '取消单')
        s.cell(marker + 2, 1, '已走货订单')
        s.cell(marker + 3, 1, '保留历史')
        s.cell(marker + 3, 2, f'=A{marker + 3}')
        s.merge_cells(start_row=marker, start_column=1, end_row=marker, end_column=3)
        if name == service.ITEM_SHEET:
            for c, value in {6: '7816-14', 7: 'GT', 8: 'BBJDTR-1850', 9: '翻斗车', 10: 'Dump Truck', 11: 2500, 12: 6, 20: '彩盒'}.items():
                s.cell(4, c, value)
            s.cell(4, 13, '=CEILING(K4/L4,1)')
        else:
            s.cell(4, 7, 'OLD')
            s.cell(4, 8, ArrayFormula(ref='H4', text='=IF(D4="","",ITEM表!I4)'))
            s.cell(4, 14, 11)
            s.cell(4, 15, '=J4*N4')
    buffer = BytesIO()
    w.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize('customer', mapping.ITEM_TAILS)
def test_common_headers_accept_different_customer_extensions(customer):
    content = template(customer)
    service.ensure_unified_schedule('new.xlsx', content, factory_id='huakang-a', customer_code=customer)
    service.ensure_unified_schedule('new.xlsx', content, factory_id='huaxing', customer_code='360')
    other = next(c for c in mapping.ITEM_TAILS if c != customer)
    service.ensure_unified_schedule('new.xlsx', content, factory_id='huakang-a', customer_code=other)


def test_custom_columns_optional_but_common_keys_required():
    w = openpyxl.load_workbook(BytesIO(template('360')))
    item = w[service.ITEM_SHEET]
    item.delete_cols(29, 30)
    for name in (service.ORDER_SHEET, service.REVIEW_SHEET):
        w[name]['T3'] = '跟客自定义备注'
    b = BytesIO()
    w.save(b)
    service.ensure_unified_schedule('new.xlsx', b.getvalue())
    item['H3'] = '错误公共字段'
    b = BytesIO()
    w.save(b)
    with pytest.raises(service.CustomerOrderUnifiedError, match='公共字段.*产品编号'):
        service.ensure_unified_schedule('new.xlsx', b.getvalue())


def test_reordered_extensions_write_by_header_and_preserve_unknown_cells():
    w = openpyxl.load_workbook(BytesIO(template('360')))
    s = w[service.ITEM_SHEET]
    for c in range(29, 39):
        s.cell(3, c).value = None
    for c, value in {29:'跟客负责人', 30:'备注', 31:'Port of Discharge', 34:'条码', 36:'Consolidated ID', 38:'MS Container Type (FCL/LCL)'}.items():
        s.cell(3, c).value = value
    s['AC5'], s['AD5'] = '人工跟客', '人工备注'
    mapping.write_extras(s, 5, {'barcode':'00123','port':'China','container_type':'LCL','consolidated_id':'FCL'}, '360')
    assert [s.cell(5,c).value for c in (31,34,36,38)] == ['China','00123','FCL','LCL']
    assert (s['AC5'].value,s['AD5'].value) == ('人工跟客','人工备注')
    # Missing or duplicate labels are not a reason to reject the common template.
    s['AI3'] = '条码'
    s['AH5'], s['AI5'] = '保留1', '保留2'
    mapping.write_extras(s, 5, {'barcode':'999'}, '360')
    assert (s['AH5'].value,s['AI5'].value) == ('保留1','保留2')


@pytest.mark.parametrize('customer', ['green-toys','headstart'])
def test_price_formulas_follow_reordered_headers(customer):
    w = openpyxl.load_workbook(BytesIO(template(customer)))
    s = w[service.ITEM_SHEET]
    s.insert_cols(30, 2)
    columns = mapping.extra_columns(s, customer)
    row = {'quantity':'25','unit_price_usd':'1.89','unit_price_hkd':'14.742','transportation_mode':"40'YT"}
    mapping.write_extras(s, 5, row, customer)
    assert s['AJ5'].value == 1.89
    assert 'AJ5*7.8' in s['AL5'].value
    assert 'K5*AJ5' in s['AK5'].value
    assert 'K5*AL5' in s['AM5'].value
    if customer == 'green-toys':
        assert columns['transportation_mode'] == 35
        assert s['AI5'].value == "40'YT"
        assert s['AR5'].value is None  # actual shipping mode


def test_actual_shipping_mode_not_written_when_planned_mode_removed():
    w = openpyxl.load_workbook(BytesIO(template('green-toys')))
    s = w[service.ITEM_SHEET]
    s['AG3'] = '人工备注'
    s['AP5'] = '实际运输方式'
    assert 'transportation_mode' not in mapping.extra_columns(s, 'green-toys')
    mapping.write_extras(s, 5, {'transportation_mode': "40'YT"}, 'green-toys')
    assert s['AP5'].value == '实际运输方式'


def test_green_history_identity_uses_base_po_and_item_even_below_cancel():
    content = template('green-toys')
    w = openpyxl.load_workbook(BytesIO(content))
    s = w[service.ITEM_SHEET]
    s['F15'], s['H15'], s['K15'] = '7816-2', 'BOOK-1', 50
    b = BytesIO()
    w.save(b)
    history = service.read_unified_history(b.getvalue(), factory_id='huakang-a', customer_code='green-toys')
    assert {h.reference_no for h in history} == {'7816-14', '7816-2'}
    record = {'contract_no': '7816', 'customer_po': '7816-1', 'item_no': 'BBJDTR-1850'}
    assigned = {}
    mapping.reconcile_green_po(record, history, assigned)
    assert record['customer_po'] == '7816-14'
    new = {'contract_no': '7816', 'item_no': 'NEW'}
    mapping.reconcile_green_po(new, history, assigned)
    assert new['customer_po'] == '7816-15'
    assert mapping.identity('headstart', '2022116AAA', '25833−0206') == mapping.identity('headstart', '2022116AA', '25833-0206')


@pytest.mark.parametrize('customer', mapping.ITEM_TAILS)
def test_independent_append_preserves_history_and_fills_reserved_array_formulas(customer):
    w = openpyxl.load_workbook(BytesIO(template(customer)))
    before = {s.title: service._marker_row(s) for s in w}
    slots = mapping.output_slots(w, 6)
    assert all(len(rows) == 6 for rows in slots.values())
    for s in w:
        marker = service._marker_row(s)
        delta = marker - before[s.title]
        assert s.cell(before[s.title] + 3 + delta, 1).value == '保留历史'
        assert s.cell(before[s.title] + 3 + delta, 2).value == f'=A{before[s.title] + 3 + delta}'
        assert f'A{marker}:C{marker}' in {str(r) for r in s.merged_cells.ranges}
        assert max(slots[s.title]) < marker
        if s.title != service.ITEM_SHEET:
            assert s['N4'].value == 11
            for r in slots[s.title]:
                assert isinstance(s.cell(r, 8).value, ArrayFormula)
                assert s.cell(r, 8).value.ref == f'H{r}'
                assert f'D{r}' in s.cell(r, 8).value.text
                assert s.cell(r, 14).value is None
    b = BytesIO()
    w.save(b)
    loaded = openpyxl.load_workbook(BytesIO(b.getvalue()))
    assert isinstance(loaded[service.ORDER_SHEET]['H5'].value, ArrayFormula)


@pytest.mark.parametrize('customer', mapping.ITEM_TAILS)
def test_preview_and_export_customer_fields(monkeypatch, customer):
    # API regression fixtures reload service modules between tests.
    from app.services.huakang_a_order_legacy import schedule_parser, green_toys_headstart
    record = {
        'contract_no': 'RL-450783-19' if customer == '360' else '2022802AB',
        'customer_release': 'RL232670318', 'customer_po': '2326703',
        'item_no': 'NEW', 'description': 'New toy', 'quantity': 2500,
        'master_carton_qty': 6, 'barcode': '001234567890', 'container_type': 'LCL',
        'consolidated_id': 'FCL', 'port': 'China', 'unit_price_usd': 1.89,
        'country': '美国', 'product_packaging': 'Window Box', 'customer_name': 'Target',
        'planned_inspection_date': '2026-09-20', 'factory_commit_date': '2026-09-21',
        'parse_ok': True, 'parse_warnings': [],
    }
    if customer == '360':
        monkeypatch.setattr(schedule_parser, 'parse_po_file', lambda *_: copy(record))
    else:
        fn = 'parse_green_toys_image' if customer == 'green-toys' else 'parse_headstart_pdf'
        monkeypatch.setattr(green_toys_headstart, fn, lambda *_: [copy(record)])
    output, _, preview = service.export_unified_customer_schedule(
        customer_code=customer, factory_id='huakang-a', received_date='2026-09-07',
        po_files=[('po.pdf' if customer != 'green-toys' else 'po.png', b'po')],
        schedule_file_name='new.xlsx', schedule_content=template(customer),
    )
    row = preview['rows'][0]
    assert row['standard'] == ''
    assert row['packaging'] == 'Window Box'
    assert row['carton_count'] == '417'
    w = openpyxl.load_workbook(BytesIO(output))
    s = w[service.ITEM_SHEET]
    assert s['M5'].value == '=CEILING(K5/L5,1)'
    assert s['N5'].value is None
    if customer == '360':
        assert s['D5'].value == 'RL232670318'
        assert s['E5'].value == s['F5'].value == 'RL-450783-19'
        assert [s.cell(5, c).value for c in range(30, 34)] == ['001234567890', 'LCL', 'FCL', 'China']
    else:
        assert s['AH5'].value == 1.89
        assert '7.8' in s['AJ5'].value
        assert 'ROUND' not in s['AI5'].value
        assert s['AL5'].value is None
    for name in (service.ORDER_SHEET, service.REVIEW_SHEET):
        assert [w[name].cell(5, c).value for c in range(3, 8)] == [s.cell(5, c).value for c in range(4, 9)]


def test_reserved_summary_formulas_take_priority_over_legacy_contract_formulas():
    w = openpyxl.load_workbook(BytesIO(template('360')))
    s = w[service.REVIEW_SHEET]
    # The latest 360 file has a complete SO-based formula row after a blank gap.
    for c in (1, 2, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18):
        s.cell(6, c, '=IF(D6="","",ITEM表!E6)')
    slots = mapping.output_slots(w, 4)
    assert slots[service.REVIEW_SHEET][0] == 5
    assert s['H5'].value.startswith('=IF(D5=')
    assert s['H6'].value == '=IF(D6="","",ITEM表!E6)'
    assert s['N5'].value is None
