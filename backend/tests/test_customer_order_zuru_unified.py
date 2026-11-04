"""Synthetic ZURU input; never check private order files into the repository."""
from io import BytesIO
from importlib import import_module

import openpyxl
import pytest
from fastapi import HTTPException

from app.services import customer_order_zuru as zuru
from app.services import customer_order_unified as unified
from app.schemas.customer_order import CustomerOrderImportPreviewOut
from test_customer_order_huaxing_unified import template as huaxing_template


def data(workbook):
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def template(customer='zuru'):
    w = huaxing_template(customer)
    for c, value in {6: '7816-14', 7: 'GT', 8: 'BBJDTR-1850', 9: '翻斗车',
                     10: 'Dump Truck', 11: 2500, 12: 6, 20: '彩盒'}.items():
        w['ITEM表'].cell(4, c, value)
    for name in ('接单表', '正单评审表'):
        w[name]['G4'], w[name]['N4'], w[name]['O4'] = 'OLD', 11, '=J4*N4'
    return data(w)


def po_book():
    w = openpyxl.Workbook()
    s = w.active
    for addr, value in {'A1': 'ZURU PURCHASE ORDER', 'A5': 'Date:', 'E5': '2026-10-01',
                        'A6': 'ZURU Inc PO#', 'E6': '4500999001', 'A7': 'Customer Name:',
                        'E7': 'Example Retail', 'U5': 'Shipment Date:', 'X5': '2026-12-01',
                        'U10': 'Destination Country:', 'X10': 'United Kingdom'}.items():
        s[addr] = value
    headers = {'A': 'Line', 'B': 'SKU', 'C': 'SKU-SPEC', 'G': 'Name', 'J': 'Inner',
               'N': 'Outer', 'S': 'Individual\nBarcode', 'U': 'Delivery\nDate',
               'W': 'Price\nUSD', 'X': 'QTY\nPCS', 'Z': 'Total\nUSD', 'AA': 'Total\nCTNS', 'AE': 'Customer PO'}
    for col, value in headers.items():
        s[f'{col}13'] = value
    for n, line, qty, spec, terminal in [(15, 10, 100, '9560-S001', '000100'), (16, 20, 200, '9560-S004-MB', '000200')]:
        for col, value in {'A': str(line), 'B': '9560', 'C': spec, 'G': 'Example toy',
                           'J': 0, 'N': 4, 'S': '0012345678901', 'U': '2026/12/1',
                           'W': '2.5000', 'X': qty, 'Z': qty * 2.5, 'AA': qty // 4, 'AE': terminal}.items():
            s[f'{col}{n}'] = value
    for col, value in {'A': 'Totals', 'X': 300, 'Z': 750, 'AA': 75}.items():
        s[f'{col}17'] = value
    return w


def args(book=None, schedule=None, name='PO.xlsx'):
    return dict(customer_code='zuru', factory_id='huaxing', received_date='2026-10-29',
                po_files=[(name, data(book or po_book()))], schedule_file_name='统一排期.xlsx',
                schedule_content=schedule or template('zuru'))


@pytest.fixture(autouse=True)
def reload_modules():
    global unified, zuru
    unified = import_module('app.services.customer_order_unified')
    zuru = import_module('app.services.customer_order_zuru')


def test_preview_contract_distinct_references_and_full_variants():
    preview = unified.create_unified_customer_preview(**args())
    assert preview['summary'] == dict(total=2, valid=2, warning=0, blocked=0)
    assert [r['reference_no'] for r in preview['rows']] == ['4500999001-10', '4500999001-20']
    assert [r['product_no'] for r in preview['rows']] == ['9560-S001', '9560-S004-MB']
    assert [r['po_no'] for r in preview['rows']] == ['000100', '000200']
    for r in preview['rows']:
        assert r['order_type'] == '正单' and r['contract_no'] == '4500999001'
        assert r['unit_price_hkd'] == r['production_no'] == r['line_q'] == ''
        assert r['requested_ship_date'] == '2026-12-01'
        assert r['unit_price_usd'] == '2.5'
    CustomerOrderImportPreviewOut.model_validate(dict(preview, preview_fingerprint='synthetic'))


def test_export_independent_rows_links_manual_columns_and_preserves_history():
    params = args()
    old = openpyxl.load_workbook(BytesIO(params['schedule_content']))
    output, _, preview = unified.export_unified_customer_schedule(**params)
    w = openpyxl.load_workbook(BytesIO(output))
    assert w.sheetnames == old.sheetnames
    for name in w.sheetnames:
        headers = [c.value for c in w[name][3]]
        assert headers.count('纸箱') == headers.count('拆单来源') == 1
        assert '出货货号' not in headers
        assert w[name]['G4'].value == old[name]['G4'].value
        refcol = 5 if name == 'ITEM表' else 4
        for reference in ['4500999001-10', '4500999001-20']:
            n, = [c.row for c in w[name]._cells.values() if c.column == refcol and c.value == reference]
            assert n < unified._marker_row(w[name])
            if name != 'ITEM表':
                item_n, = [c.row for c in w['ITEM表']._cells.values() if c.column == 5 and c.value == reference]
                assert w[name].cell(n, 10).value == f'=IF(LEN(\'ITEM表\'!K{item_n})=0,"",\'ITEM表\'!K{item_n})'
                assert w[name].cell(n, 16).value == 2.5
                assert w[name].cell(n, 17).value == (250 if reference.endswith('-10') else 500)
    assert unified.create_unified_customer_preview(**dict(params, schedule_content=output))['summary']['blocked'] == 0
    assert len(preview['rows']) == 2
    assert preview['factory_id'] == 'huaxing'
    assert preview['target_template'] == 'HEYUAN_BUSINESS_UNIFIED_HUAXING_V2'


def test_cross_page_fragment_attaches_to_next_line_not_previous_customer_po():
    w = po_book()
    s = w.active
    s.insert_rows(16)
    s['G16'], s['S16'], s['AE16'] = 'Prefix', '0012345678902', '000200'
    s['G17'], s['S17'], s['AE17'] = 'Suffix', None, None
    parsed = zuru.parse_po('PO.xlsx', data(w))
    assert [r['customer_po'] for r in parsed['lines']] == ['000100', '000200']
    assert parsed['lines'][1]['name'] == 'Prefix\nSuffix'
    assert parsed['lines'][1]['source_rows'] == [16, 17]
    s['AE17'] = 'DIFFERENT'
    with pytest.raises(ValueError, match='冲突'):
        zuru.parse_po('PO.xlsx', data(w))


def test_bare_po_fragment_cannot_be_assigned_by_proximity():
    w = po_book()
    s = w.active
    s['AE15'] = None
    s.insert_rows(16)
    s['AE16'], s['AE17'] = '000100', None
    with pytest.raises(ValueError, match='归属不明确'):
        zuru.parse_po('PO.xlsx', data(w))


@pytest.mark.parametrize('address,value', [('S15', None), ('S15', '002'), ('S17', '003'), ('AE15', None)])
def test_fragment_requires_unambiguous_adjacent_barcode_evidence(address, value):
    w = po_book()
    s = w.active
    s.insert_rows(16)
    s['G16'], s['S16'], s['AE16'] = 'Prefix', '002', '000200'
    s['S17'], s['AE17'] = None, None
    s[address] = value
    with pytest.raises(ValueError, match='归属不明确'):
        zuru.parse_po('PO.xlsx', data(w))


def test_partial_detail_after_total_is_not_ignored():
    w = po_book()
    w.active['C18'], w.active['X18'] = '9560-S009', 100
    with pytest.raises(ValueError, match='总计后仍有订单明细'):
        zuru.parse_po('PO.xlsx', data(w))


def test_new_summary_cannot_inherit_implicit_hkd_conversion():
    w = openpyxl.load_workbook(BytesIO(template('zuru')))
    for name in ('接单表', '正单评审表'):
        w[name]['N4'], w[name]['O4'] = '=P4*7.8', '=J4*N4'
    output, _, _ = unified.export_unified_customer_schedule(**args(schedule=data(w)))
    out = openpyxl.load_workbook(BytesIO(output))
    for name in ('接单表', '正单评审表'):
        assert out[name]['N4'].value == '=P4*7.8'
        for n in (5, 6):
            assert out[name].cell(n, 14).value is None
            assert out[name].cell(n, 15).value is None
            assert out[name].cell(n, 16).value == 2.5


def test_post_line_continuation_and_shifted_name_anchor():
    w = po_book()
    s = w.active
    s.insert_rows(16)
    s['B16'], s['C16'], s['F16'] = '9560', '9560-S001', 'name continuation'
    s['B15'], s['C15'] = None, None
    result = zuru.parse_po('PO.xlsx', data(w))
    assert result['lines'][0]['spec'] == '9560-S001'
    assert result['lines'][0]['name'] == 'Example toy\nname continuation'
    assert result['lines'][0]['source_rows'] == [15, 16]


@pytest.mark.parametrize('address,value,message', [
    ('X15', -1, '数量'), ('X17', 301, '总计'), ('Z17', 751, '总计'), ('AA17', 74, '总计'),
    ('N15', 6, '混装'), ('A16', 10, '重复'), ('A15', None, 'Line'),
    ('C15', '', 'SKU'), ('C15', 'OTHER-S001', 'SKU'), ('E6', '', 'PO 号'),
    ('U15', 'bad', '日期'), ('W15', 50, '金额'), ('X15', '=1+1', '公式'),
    ('AE15', '#REF!', '错误'), ('AE13', 'QTY PCS', '表头重复'),
])
def test_bad_source_is_rejected_without_partial_output(address, value, message):
    w = po_book()
    w.active[address] = value
    with pytest.raises(ValueError, match=message):
        zuru.parse_po('PO.xlsx', data(w))


@pytest.mark.parametrize('name', ['PO Cancel.xlsx', 'MPO.xlsx', 'mixed.xlsx', 'PO.pdf', 'PO.xlsm'])
def test_unsupported_inputs_not_treated_as_formal(name):
    with pytest.raises(ValueError):
        zuru.parse_po(name, data(po_book()))


def test_rounding_is_bounded_and_original_amount_preserved():
    w = po_book()
    w.active['W15'], w.active['X15'], w.active['Z15'], w.active['AA15'] = '3.0668', 50000, 153342, 12500
    w.active['X17'], w.active['Z17'], w.active['AA17'] = 50200, 153842, 12550
    preview = unified.create_unified_customer_preview(**args(w))
    r = preview['rows'][0]
    assert r['amount_usd'] == '153342.0' and r['issues'][0]['severity'] == 'warning'
    CustomerOrderImportPreviewOut.model_validate(dict(preview, preview_fingerprint='rounding'))
    r['quantity'] = '100'
    unified._recalculate_preview_row(r)
    assert r['amount_usd'] == '306.68'
    w.active['Z15'], w.active['Z17'] = 153344, 153844
    with pytest.raises(ValueError, match='金额'):
        zuru.parse_po('PO.xlsx', data(w))


def test_missing_outer_derived_only_from_exact_qty_cartons():
    w = po_book()
    w.active['N13'] = 'Unknown'
    row = zuru.parse_po('PO.xlsx', data(w))['lines'][0]
    assert row['outer'] == 4 and row['warnings']


@pytest.mark.parametrize('factory', ['huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng'])
def test_factory_scope_rejected(factory):
    api = import_module('app.api.customer_order')
    with pytest.raises(HTTPException):
        api._ensure_customer_factory('zuru', factory)
    with pytest.raises(unified.CustomerOrderUnifiedError, match='不属于当前厂区'):
        unified.create_unified_customer_preview(**dict(args(), factory_id=factory))
    api._ensure_customer_factory('zuru', 'huaxing')
    assert api._get_mapped_customer_spec('zuru', 'huaxing').po_extensions == ('.pdf', '.xlsx')


def test_usd_not_replaced_by_history_and_text_not_executed():
    schedule = openpyxl.load_workbook(BytesIO(template('zuru')))
    schedule['ITEM表']['H4'] = '9560-S001'
    schedule['ITEM表']['G4'] = 'Example Retail'
    schedule['接单表']['G4'], schedule['接单表']['N4'] = '9560-S001', 99
    book = po_book()
    book.active['G15'] = '=BAD()'
    book.active['G15'].data_type = 's'
    params = args(book, data(schedule))
    result = unified.create_unified_customer_preview(**params)
    assert result['rows'][0]['unit_price_hkd'] == ''
    output, _, _ = unified.export_unified_customer_schedule(**params)
    s = openpyxl.load_workbook(BytesIO(output))['ITEM表']
    cell, = [c for c in s._cells.values() if c.column == 10 and c.value == '=BAD()']
    assert cell.data_type == 's'


def test_full_product_punctuation_cannot_inherit_other_variant_packaging():
    w = openpyxl.load_workbook(BytesIO(template('zuru')))
    w['ITEM表']['H4'] = '9560-S001'
    w['ITEM表']['G4'] = 'Example Retail'
    w['ITEM表']['T4'] = 'Other variant packaging'
    book = po_book()
    book.active['C15'] = '9560-S.001'
    preview = unified.create_unified_customer_preview(**args(book, data(w)))
    assert preview['rows'][0]['product_no'] == '9560-S.001'
    assert preview['rows'][0]['packaging'] == ''


def test_quantity_conflicts_stay_blocked_but_exact_duplicate_is_warning():
    params = args()
    existing, _, _ = unified.export_unified_customer_schedule(**params)
    params['schedule_content'] = existing
    result = unified.create_unified_customer_preview(**params)
    assert result['summary']['blocked'] == 0
    assert result['rows'][0]['status'] == 'warning'
    book = po_book()
    book.active['X15'], book.active['Z15'], book.active['AA15'] = 104, 260, 26
    book.active['X17'], book.active['Z17'], book.active['AA17'] = 304, 760, 76
    params['po_files'] = [('changed.xlsx', data(book))]
    assert unified.create_unified_customer_preview(**params)['summary']['blocked'] > 0
    with pytest.raises(unified.CustomerOrderUnifiedError):
        unified.export_unified_customer_schedule(**params)


def test_full_product_punctuation_does_not_create_false_history_conflict():
    w = openpyxl.load_workbook(BytesIO(template()))
    item = w['ITEM表']
    item['E4'], item['H4'], item['K4'] = '4500999001-10', '9560-S001', 999
    book = po_book()
    book.active['C15'] = '9560-S.001'
    preview = unified.create_unified_customer_preview(**args(book, data(w)))
    assert not any(i['code'] in {'existing_quantity_conflict', 'duplicate_existing_order'}
                   for i in preview['rows'][0]['issues'])


def test_zuru_history_packaging_needs_same_terminal_customer():
    w = openpyxl.load_workbook(BytesIO(template()))
    item = w['ITEM表']
    item['H4'], item['G4'], item['L4'], item['T4'] = '9560-S001', 'Different retailer', 99, 'Other packaging'
    book = po_book()
    for address in ('N15', 'AA15', 'AA17'):
        book.active[address] = None
    preview = unified.create_unified_customer_preview(**args(book, data(w)))
    row = preview['rows'][0]
    assert row['units_per_carton'] == row['packaging'] == ''


def test_zuru_manual_usd_price_recalculates_only_new_usd_amounts():
    params = args()
    preview = unified.create_unified_customer_preview(**params)
    output, _, changed = unified.export_unified_customer_schedule(**params,
        manual_overrides=[dict(row_id=preview['rows'][0]['id'], field='unit_price_usd', value='3.5', reason='核对原件更正')])
    assert changed['rows'][0]['amount_usd'] == '350'
    wb = openpyxl.load_workbook(BytesIO(output))
    for name in ('接单表', '正单评审表'):
        sheet = wb[name]
        n, = [c.row for c in sheet._cells.values() if c.column == 4 and c.value == '4500999001-10']
        assert (sheet.cell(n, 14).value, sheet.cell(n, 15).value) == (None, None)
        assert (sheet.cell(n, 16).value, sheet.cell(n, 17).value) == (3.5, 350)
        assert sheet['N4'].value == 11


def test_zuru_edited_product_keeps_exact_history_and_terminal_boundaries():
    from app.services import customer_order_huaxing_unified as mapping
    history = [
        unified.UnifiedHistoryRow(row=4, product_no='9560-S001', customer_name='Example Retail', packaging='Wrong punctuation', units_per_carton='99'),
        unified.UnifiedHistoryRow(row=5, product_no='9560-S.001', customer_name='Other retailer', packaging='Wrong retailer', units_per_carton='88'),
    ]
    row = dict(id='1', product_no='9560-S.001', reference_no='R', contract_no='R', po_no='',
        customer_name='Example Retail', units_per_carton='4', packaging='Old historical value',
        lineage={'units_per_carton': '唯一历史值', 'packaging': '唯一历史值'}, _zuru_customer=True, _huaxing_customer='zuru')
    mapping.validate_edited_identities({'rows': [row]}, {'1': ('OLD', 'R', 'R', '')}, history, ['ITEM表'])
    assert row['units_per_carton'] == row['packaging'] == ''
