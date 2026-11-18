"""Synthetic EDU PDF contracts; private originals remain outside the repository."""
from io import BytesIO

import openpyxl
import pytest
from reportlab.pdfgen import canvas

from app.services.huaxing_order_legacy import edu_pdf, edu_po_parser
from app.services import customer_order_unified as service
from app.services.customer_order_huaxing import HUAXING_CUSTOMER_MAPPINGS
from test_customer_order_huaxing_unified import template, data


def page(*, po='990001234', qty='1,200', delivery='1200', amount='3,000.00', currency='HKD', item='F12-ZZ901-C9010000'):
    return f'''EDU-SCIENCE (H.K.) LIMITED
PURCHASE ORDER
P.O.: {po}
Date 2026-11-18
Currency {currency}
Item Description Unit price Qty Amount
{item} Synthetic toy/TEST CUSTOMER{{Test series, 2.5000/SET {qty} {amount}
00010001, none, 00010001 }}
Warehouse: A13
Delivery 2026-12-28 Qty {delivery}
Total: {amount} {currency}
Ship to FOB YAN-TIAN
SO99000123
'''


def pdf_bytes(text):
    out = BytesIO()
    document = canvas.Canvas(out)
    for i, line in enumerate(text.splitlines()):
        document.drawString(35, 800 - i * 18, line)
    document.save()
    return out.getvalue()


def parsed(text=None, *, ocr=False):
    return edu_pdf.parse_pages([text or page()], 'synthetic.pdf', ocr)


def args_for(monkeypatch, text=None, wb=None):
    monkeypatch.setattr(edu_pdf, 'read_pdf_pages', lambda *a, **k: ([text or page()], False))
    return dict(customer_code='edu', factory_id='huaxing', received_date='2026-11-18',
        po_files=[('synthetic.pdf', b'%PDF-synthetic mocked extraction')],
        schedule_file_name='EDU.xlsx', schedule_content=data(wb or template('edu')))


def test_native_pdf_is_supported_without_changing_caixing_dispatch(monkeypatch):
    result = edu_po_parser.parse_edu_po_file(pdf_bytes(page()), 'native.pdf')
    row, = result['rows']
    assert result['meta']['used_ocr'] is False
    assert row['customer_po'] == '990001234' and row['item_no'] == 'F12-ZZ901-C901'
    assert row['source_item_no'] == 'F12-ZZ901-C9010000'
    assert row['quantity'] == 1200 and row['unit_price'] == 2.5 and row['amount'] == 3000
    assert row['ship_date'] == '2026-12-28' and row['inspection_date'] == '2026-12-21'
    assert row['customer'] == 'TEST CUSTOMER'
    assert row['so_no'] == 'SO99000123' and not row['contract_no']
    assert row['case_pack'] is None and not row['country']
    assert '.pdf' in HUAXING_CUSTOMER_MAPPINGS['edu'].po_extensions
    monkeypatch.setattr(edu_po_parser, 'parse_caixing_pdf', lambda *a: 'CAIXING_UNCHANGED')
    assert edu_po_parser.parse_po_file(b'pdf', 'caixing.pdf') == 'CAIXING_UNCHANGED'


def test_scanned_quantity_uses_delivery_and_arithmetic_not_decimal_replacement():
    text = page(qty='1.200') + '\n' + page()
    result = parsed(text, ocr=True)
    row, = result['rows']
    assert row['quantity'] == 1200
    assert row['source_quantity'] == '1.200' and row['source_delivery_quantity'] == '1200'
    assert any('结合单价与金额' in s for s in result['warnings'])
    assert row['source_page'] == 1


def test_multi_product_multi_page_retains_order_and_never_swallows_bad_line():
    first = page().replace('Total: 3,000.00 HKD',
        'F12-YY902-C9020000 Another toy/TEST CUSTOMER{Series} 2.5/SET 1000 2500.00\n'
        'Delivery 2026-12-30 Qty 1000\nTotal: 5500.00 HKD')
    rows = edu_pdf.parse_pages([first, page(po='990001235')], 'multi.pdf')['rows']
    assert len(rows) == 3 and [r['source_page'] for r in rows] == [1, 1, 2]
    assert [r['quantity'] for r in rows] == [1200, 1000, 1200]
    broken = page().replace('Total:', 'F12-YY902-C9020000 unreadable numeric columns\nTotal:')
    with pytest.raises(ValueError, match='未只导出部分商品'):
        parsed(broken)
    with pytest.raises(ValueError, match='不是已支持'):
        edu_pdf.parse_pages([page(), 'unrecognized second page'], 'multi.pdf')


def test_missing_date_and_money_conflicts_are_reminders():
    text = page().replace('Delivery 2026-12-28 Qty 1200\n', '')
    row, = parsed(text)['rows']
    assert row['quantity'] == 1200 and row['ship_date'] is None
    result = parsed(page(amount='2,999.00'))
    assert result['rows'][0]['quantity'] == 1200 and result['rows'][0]['amount'] == 2999
    assert any('金额不一致' in s for s in result['warnings'])
    result = parsed(page(qty='1000', delivery='1100', amount='2999'))
    assert result['rows'][0]['quantity'] is None
    assert any('数量留空' in s for s in result['warnings'])


def test_wrong_customer_and_multiple_delivery_layout_fail_clearly():
    with pytest.raises(ValueError, match='不是已支持'):
        parsed(page().replace('EDU-SCIENCE', 'UNRELATED CUSTOMER'))
    with pytest.raises(ValueError, match='多个 Delivery'):
        parsed(page().replace('Total:', 'Delivery 2026-12-30 Qty 100\nTotal:'))


def test_mixed_native_scanned_pages_trigger_bounded_ocr(monkeypatch):
    from app.services import customer_order_ocr
    monkeypatch.setattr(edu_pdf, 'read_pdf_pages', lambda *a, **k: ([page(), ''], False))
    calls = []
    def ocr(content, count):
        calls.append((content, count))
        return [page(), page(po='990001235')]
    monkeypatch.setattr(customer_order_ocr, 'read_scanned_order_pdf', ocr)
    result = edu_pdf.parse_pdf(BytesIO(b'original bytes'), 'mixed.pdf')
    assert calls == [(b'original bytes', 2)]
    assert len(result['rows']) == 2 and result['meta']['used_ocr']


def test_unified_export_missing_pack_and_contract_are_not_gates(monkeypatch):
    args = args_for(monkeypatch)
    output, _, preview = service.export_unified_customer_schedule(**args)
    assert preview['summary']['blocked'] == 0
    row, = preview['rows']
    assert not row['contract_no'] and row['quantity'] == '1200'
    assert '第 1 页' in row['lineage']['source']
    book = openpyxl.load_workbook(BytesIO(output))
    sheet = book['ITEM表']
    new = next(r for r in range(4, sheet.max_row + 1) if sheet.cell(r, 6).value == '990001234')
    assert sheet.cell(new, 8).value == 'F12-ZZ901-C901'
    assert sheet.cell(new, 11).value == 1200 and sheet.cell(new, 12).value is None
    assert row['unit_price_hkd'] == '2.5' and sheet.cell(new, 4).value is None
    for name in ('接单表', '正单评审表'):
        assert any(book[name].cell(r, 5).value == '990001234' for r in range(4, book[name].max_row + 1))
    order_row = next(r for r in range(4,book['接单表'].max_row+1) if book['接单表'].cell(r,5).value=='990001234')
    review_row = next(r for r in range(4,book['正单评审表'].max_row+1) if book['正单评审表'].cell(r,5).value=='990001234')
    assert book['接单表'].cell(order_row,14).value==2.5
    assert f"'接单表'!N{order_row}" in book['正单评审表'].cell(review_row,14).value
    assert book['PO订单'].max_row == 2
    retry = service.create_unified_customer_preview(**{**args, 'schedule_content': output})
    assert any(i['code'] == 'duplicate_existing_order' for i in retry['rows'][0]['issues'])


def test_pdf_reconciles_only_unique_historical_contract(monkeypatch):
    wb = template('edu');ws = wb['ITEM表']
    for col, value in {4:'CONTRACT/ONE', 5:'EDUHX00123', 6:'990001234', 7:'TEST CUSTOMER',
                       8:'F12-ZZ901-C901', 11:1200, 12:12}.items():
        ws.cell(4, col, value)
    args = args_for(monkeypatch, wb=wb)
    preview = service.create_unified_customer_preview(**args)
    row, = preview['rows']
    assert row['contract_no'] == 'CONTRACT/ONE' and row['reference_no'] == 'EDUHX00123'
    assert any(i['code'] == 'duplicate_existing_order' for i in row['issues'])
    for col, value in {4:'CONTRACT/TWO', 5:'EDUHX00124', 6:'990001234', 7:'TEST CUSTOMER',
                       8:'F12-ZZ901-C901', 11:1200, 12:12}.items(): ws.cell(5,col,value)
    output, _, preview = service.export_unified_customer_schedule(**{**args,'schedule_content':data(wb)})
    assert preview['summary']['blocked'] == 0
    assert any(i['code']=='ambiguous_edu_history' for i in preview['rows'][0]['issues'])
    assert 'ITEM待补资料' in openpyxl.load_workbook(BytesIO(output)).sheetnames


@pytest.mark.parametrize('currency', ['USD', 'XXX', ''])
def test_non_hkd_never_inherits_historical_hkd_prices(monkeypatch, currency):
    wb=template('edu');ws=wb['ITEM表']
    for col, value in {4:'OTHER',5:'EDUHX00001',6:'OTHER',7:'TEST CUSTOMER',8:'F12-ZZ901-C901',11:100,16:999}.items(): ws.cell(4,col,value)
    args=args_for(monkeypatch,page(currency=currency),wb)
    row,=service.create_unified_customer_preview(**args)['rows']
    assert not row['unit_price_hkd'] and not row['amount_hkd']


def test_same_batch_excel_contract_is_not_inferred_from_so():
    pdf=parsed()
    excel={'filename':'EDU.xlsx','rows':[dict(pdf['rows'][0],source_pdf=False,contract_no='ACTUAL-CONTRACT')]}
    rows,_=edu_po_parser.merge_edu_po_results([excel,pdf])
    assert {r['contract_no'] for r in rows}=={'ACTUAL-CONTRACT'}
    assert all(r['contract_no']!='SO99000123' for r in rows)


@pytest.mark.parametrize('peers', [[('C1', 'TEST CUSTOMER'), ('C2', 'TEST CUSTOMER')], [('C1', 'OTHER CUSTOMER')]])
def test_ambiguous_batch_pdf_is_staged_without_extra_stock_debit(monkeypatch, peers):
    from copy import deepcopy
    from test_customer_order_edu_grouped_export import template as stock_template, reserve, find_row
    wb = stock_template(); reserve(wb, 6, quantity=10000)
    pdf = parsed()
    excel = dict(filename='source.xlsx', customer_type='EDU', rows=[dict(pdf['rows'][0],
        source_pdf=False, contract_no=contract, customer=customer) for contract, customer in peers])
    monkeypatch.setattr(edu_po_parser, 'parse_edu_po_file', lambda content, filename: deepcopy(pdf if filename.endswith('.pdf') else excel))
    args = args_for(monkeypatch, wb=wb)
    args['po_files'].append(('source.xlsx', b'synthetic excel'))
    output, _, preview = service.export_unified_customer_schedule(**args)
    assert preview['summary']['blocked'] == 0
    pending = next(r for r in preview['rows'] if any(i['code']=='ambiguous_edu_batch' for i in r['issues']))
    assert not pending['contract_no']
    book = openpyxl.load_workbook(BytesIO(output))
    sheet = book['ITEM待补资料']
    assert sum(sheet.cell(r,6).value=='990001234' for r in range(4,sheet.max_row+1)) == 1
    assert book['ITEM表'].cell(find_row(book['ITEM表'],'EDUHX00010'),11).value == '=10000' + '-1200'*len(peers)
    assert book['PO订单'].max_row == 1 + len(peers)


def test_ambiguous_pdf_does_not_stage_duplicate_or_prevent_normal_new_order(monkeypatch):
    from test_customer_order_edu_grouped_export import template as stock_template, reserve, find_row
    wb = stock_template(); ws = wb['ITEM表']; reserve(wb, 8, quantity=10000)
    for r, contract, po in [(4,'C1','990001234'), (5,'C2','990001234'), (6,'C3','990001235')]:
        for col, value in {4:contract,5:f'EDUHX00{r:03}',6:po,7:'TEST CUSTOMER',8:'F12-ZZ901-C901',11:1200,12:12}.items():
            ws.cell(r,col,value)
    monkeypatch.setattr(edu_po_parser, 'parse_edu_po_file', lambda content, filename:
        edu_pdf.parse_pages([page(po=filename[:-4])],filename))
    args = args_for(monkeypatch,wb=wb)
    args['po_files'] = [(po+'.pdf',b'synthetic') for po in ('990001234','990001235','990001236')]
    output,_,preview = service.export_unified_customer_schedule(**args)
    assert preview['summary']['blocked'] == 0
    book = openpyxl.load_workbook(BytesIO(output))
    staged = book['ITEM待补资料']
    assert [staged.cell(r,6).value for r in range(4,staged.max_row+1) if staged.cell(r,6).value] == ['990001234']
    item = book['ITEM表']
    assert sum(item.cell(r,6).value=='990001235' for r in range(4,item.max_row+1)) == 1
    assert sum(item.cell(r,6).value=='990001236' for r in range(4,item.max_row+1)) == 1
    assert item.cell(find_row(item,'EDUHX00010'),11).value == '=10000-1200'
    assert book['PO订单'].max_row == 2
