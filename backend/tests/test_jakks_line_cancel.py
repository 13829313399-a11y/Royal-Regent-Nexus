from io import BytesIO
from copy import deepcopy
from dataclasses import replace
import openpyxl
from openpyxl.styles import PatternFill
from app.services import customer_order_unified as u
from app.services.customer_order_jakks_unified import cancellation_matches
from app.services.huadeng_order_legacy import jakks_po_parser as p
from test_jakks_supplementary_contract import contract_text, workbook_bytes


def text(two=True, same=False):
    source = contract_text(formal=True)
    start = source.index('416984-PB SONIC')
    end = source.index('CARTON MARKING')
    block = source[start:end]
    second = block.replace('Line#: 1.000', 'Line#: 2.000')
    if not same:
        second = second.replace('424 2.0000 848.00', '200 2.0000 400.00').replace('106 CA', '50 CA')
    return source[:end] + (second if two else '') + source[end:]


def args(schedule=None, files=None):
    return dict(customer_code='jakks', factory_id='huadeng', received_date='2026-11-19',
        po_files=files or [('formal.pdf', b'pdf')], schedule_file_name='schedule.xlsx',
        schedule_content=schedule or workbook_bytes())


def test_line_numbers_not_enumeration_same_quantity_and_retry(monkeypatch):
    monkeypatch.setattr(p, 'extract_text', lambda _: (text(same=True), False))
    v = u.create_unified_customer_preview(**args())
    assert [(r['reference_no'],r['quantity']) for r in v['rows']] == [('5475162-1','424'),('5475162-2','424')]
    out,_,_ = u.export_unified_customer_schedule(**args())
    repeated,_,_ = u.export_unified_customer_schedule(**args(out))
    h = u.read_unified_history(repeated, factory_id='huadeng', customer_code='jakks')
    assert sum(float(r.quantity) for r in h if r.contract_no=='811784') == 848
    monkeypatch.setattr(p, 'extract_text', lambda _: (text(two=False).replace('Line#: 1.000','Line#: 2.000'), False))
    assert u.create_unified_customer_preview(**args(out))['rows'][0]['reference_no']=='5475162-2'


def test_row4_header_styles_and_existing_shipped_rows_survive(monkeypatch):
    b=openpyxl.load_workbook(BytesIO(workbook_bytes()));s=b['ITEM表'];s.insert_rows(3);s['A3']='合同基本信息';s.merge_cells('A3:N3');s.cell(500,16384).fill=PatternFill('solid',fgColor='FF0000')
    stream=BytesIO();b.save(stream)
    monkeypatch.setattr(p, 'extract_text', lambda _: (text(),False))
    out,_,_=u.export_unified_customer_schedule(**args(stream.getvalue()))
    b=openpyxl.load_workbook(BytesIO(out));s=b['ITEM表']
    assert s['A3'].value=='合同基本信息' and s['H4'].value=='产品编号'
    assert s['XFD501'].fill.fgColor.rgb=='00FF0000'
    assert any(c.value=='纸箱' and c.row==4 and c.column<100 for c in s._cells.values())
    assert len(s._cells)<1500
    assert not any(h.product_no=='产品编号' for h in u.read_unified_history(out,factory_id='huadeng',customer_code='jakks'))


def test_cancel_is_separate_from_order_and_repeat_is_idempotent(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,_=u.export_unified_customer_schedule(**args())
    cancel=args(source,[('customer-CXL(1).pdf',b'cancel')])
    v=u.create_unified_customer_preview(**cancel)
    assert v['rows'][0]['order_type']=='取消单'
    out,_,_=u.export_unified_customer_schedule(**cancel)
    rows=u.read_unified_history(out,factory_id='huadeng',customer_code='jakks')
    found=[r for r in rows if r.contract_no=='811784'];assert len(found)==1 and found[0].order_type=='取消单'
    assert u._marker_row(openpyxl.load_workbook(BytesIO(out))['ITEM表'])==6
    second,_,_=u.export_unified_customer_schedule(**args(out,[('copy-CXL.pdf',b'cancel')]))
    assert len([r for r in u.read_unified_history(second,factory_id='huadeng',customer_code='jakks') if r.contract_no=='811784'])==1
    batch=u.create_unified_customer_preview(**args(files=[('formal.pdf',b'normal'),('copy-CXL.pdf',b'cancel')]))
    assert len(batch['rows'])==2


def test_cancel_unmatched_shipped_and_unnumbered_never_rewrites(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,_=u.export_unified_customer_schedule(**args())
    b=openpyxl.load_workbook(BytesIO(source));b['ITEM表']['B5']='已走货';buf=BytesIO();b.save(buf)
    out,_,_=u.export_unified_customer_schedule(**args(buf.getvalue(),[('CXL.pdf',b'cancel')]))
    b=openpyxl.load_workbook(BytesIO(out));assert b['ITEM表']['B5'].value=='已走货';assert b['ITEM表']['B7'].value=='取消单'
    v=u.create_unified_customer_preview(**args());row=v['rows'][0]
    old=u.UnifiedHistoryRow(row=5,contract_no=row['contract_no'],reference_no=row['confirmation_no'],po_no=row['po_no'],product_no=row['product_no'],quantity=row['quantity'],requested_ship_date=row['requested_ship_date'])
    assert cancellation_matches(row,[old])==[]


def test_filename_and_explicit_cancel_body_do_not_confuse_terms(monkeypatch,tmp_path):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False)+'\n6/17/2025 - CANCEL ORDER\n',False))
    assert p.parse_po(tmp_path/'plain.pdf',allow_cancellation=True)['document_kind']=='cancellation'
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False)+'\nLIABILITY FOR ANY ORDER CANCELLATION OVER 90 DAYS\n',False))
    assert p.parse_po(tmp_path/'plain.pdf',allow_cancellation=True)['document_kind']=='contract'


def test_cancel_prechecks_all_three_sheets_and_unnumbered_notice_retries(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,_=u.export_unified_customer_schedule(**args())
    w=openpyxl.load_workbook(BytesIO(source));s=w['接单表']
    for col in range(1,20): s.cell(10,col).value=s.cell(5,col).value
    data=BytesIO();w.save(data)
    out,_,_=u.export_unified_customer_schedule(**args(data.getvalue(),[('CXL.pdf',b'cancel')]))
    h=u.read_unified_history(out,factory_id='huadeng',customer_code='jakks')
    assert [r.order_type for r in h if r.contract_no=='811784']==['正单','取消单']
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False).replace('Line#: 1.000',''),False))
    first,_,_=u.export_unified_customer_schedule(**args(files=[('CXL.pdf',b'cancel')]))
    again,_,_=u.export_unified_customer_schedule(**args(first,[('CXL.pdf',b'cancel')]))
    assert len([r for r in u.read_unified_history(again,factory_id='huadeng',customer_code='jakks') if r.contract_no=='811784'])==1


def test_formal_precedes_sup_and_upgrade_keeps_amount_formula(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda path: (contract_text(formal='formal' in path.name),False))
    for files in ([('order-SUP.pdf',b'sup'),('formal.pdf',b'formal')],[('formal.pdf',b'formal'),('order-SUP.pdf',b'sup')]):
        v=u.create_unified_customer_preview(**args(files=files));assert v['rows'][0]['unit_price_usd']=='2'
    source,_,_=u.export_unified_customer_schedule(**args(files=[('order-SUP.pdf',b'sup')]))
    w=openpyxl.load_workbook(BytesIO(source));w['接单表']['Q5']='=J5*P5';buf=BytesIO();w.save(buf)
    out,_,_=u.export_unified_customer_schedule(**args(buf.getvalue(),[('formal.pdf',b'formal')]))
    w=openpyxl.load_workbook(BytesIO(out));assert w['接单表']['Q5'].value=='=J5*P5';assert w['接单表']['P5'].value==2
