"""Synthetic SEASONS text preserves source layouts without customer order data."""
import pytest

from app.services.huaxing_order_legacy import shixin_schedule as parser


@pytest.mark.parametrize('formal,item,quantity,pack,date_code', [
    (False, 'W90001', 864, 288, '012301JAN31'),
    (True, 'W90001', 864, 288, '012301JAN31'),
    (False, 'W90002', 120, 2, ''),
    (True, 'W90002', 120, 2, ''),
])
def test_synthetic_qf_and_formal_product_evidence(monkeypatch, formal, item, quantity, pack, date_code):
    small_item = item == 'W90001'
    qf = 'QF90000001' if small_item else 'QF90000002'
    po = 'ZPO9000001' if small_item else 'ZPO9000002'
    oc = 'ZE900001' if small_item else 'ZE900002'
    price, amount = ('1.2500', '1080.00') if small_item else ('7.5000', '900.00')
    header = 'PURCHASE ORDER' if formal else 'SEASONS ORDER QUICK FORM'
    line = (
        f'{item} OC #.: {oc} SHIPDATE: 2030/12/18 {quantity} {price} 0.00% {amount}'
        if formal else f'{item} SHIPDATE: 2030/12/18 {quantity}'
    )
    description = 'SAMPLE SMALL TOY' if small_item else 'SAMPLE LARGE TOY'
    remarks = (
        'SAMPLE SMALL TOY 3.12/288装，12个装一内箱\n'
        '4.日期码： 012301JAN31\n-12 PCS PER INNER;'
        if small_item else 'SAMPLE PART IS KD PACKAGE 3.1/2装，一套装个胶袋，需热封口'
    )
    unit = 'P' if small_item and not formal else 'PCS'
    text = f'''{header}
Customer Name: SAMPLE CUSTOMER LTD Order Date: 2030/9/7
OQF No.: {qf}
PO No.: {po}
{line}
{description}
{remarks}
Packing : Inner Type: CTN Inner : {12 if small_item else 1}PCS Outer Type: CARTON Outer : {pack}{unit}
ITEM NO.: {item}TEST5FIX-1
客人设计的OEM的产品和客吊牌产品用客人的DATE CODE, 其它是用SEASONS 的DATE CODE.
装箱为0/1的号码，外箱都要贴UPC贴纸。
'''
    monkeypatch.setattr(parser, '_pdf_text', lambda data: (text, 1))
    result = parser.parse_order_documents(b'PDF text fixture', f'{po if formal else qf}.pdf')
    assert result['status'] == 'success'
    row, = result['records']
    assert row['item_no'] == item and row['quantity'] == quantity
    assert row['pack_qty'] == pack and row['cartons'] == quantity // pack
    assert row['ship_date'] == '2030-12-18'
    assert row['date_code'] == date_code


@pytest.mark.parametrize('text,expected', [
    ('4.日期码： 012301JAN31', '012301JAN31'),
    ('日期碼: 001234', '001234'),
    ('DATE CODE: 012301JAN31', '012301JAN31'),
    ('Date Code: 04-26/09\nDATE CODE: 04-26/09', '04-26/09'),
    ('使用客人的DATE CODE, 其它用SEASONS的DATE CODE.', ''),
    ('DATE CODE: SEE CUSTOMER PO\nSHIPDATE: 2030/12/18', ''),
    ('日期码：\n5.需符合美国标准', ''),
    ('Packing: Outer: 288PCS\n其他号码 DATE CODE: 123456', ''),
])
def test_date_code_requires_explicit_product_value(text, expected):
    assert parser._date_code_from_block(text) == expected


def test_conflicting_date_codes_are_not_silently_selected():
    with pytest.raises(ValueError, match='日期码存在冲突'):
        parser._date_code_from_block('日期码：012301JAN31\nDATE CODE: 022301JAN31')


@pytest.mark.parametrize('qf_quantity,expected_remaining,blocked', [(None, None, False), (288, -576, True), (0, -864, True), (864, 0, False)])
def test_qf_overdraw_requires_an_observed_reservation(qf_quantity, expected_remaining, blocked):
    formal = dict(document_type='正式PO', oqf_no='QF90000001', po_no='ZPO9000001',
                  oc_no='ZE900001', item_no='W90001', quantity=864, customer='SAMPLE CUSTOMER LTD')
    records = [formal]
    if qf_quantity is not None:
        records.append(dict(document_type='QF预备单', oqf_no='QF90000001', po_no='',
                            item_no='W90001', quantity=qf_quantity, customer='SAMPLE CUSTOMER LTD'))
    result = parser.reconcile_documents([dict(filename='fixture.pdf', records=records, warnings=[])], [])
    row = next(item for item in result['records'] if item.get('po_no'))
    assert row['qf_quantity'] == qf_quantity
    assert row['remaining_qf'] == expected_remaining
    assert (row.get('risk_text') == 'QF数量不足，正式PO累计超扣') is blocked
    if qf_quantity is None:
        assert any('剩余数量未知' in warning for warning in result['warnings'])
