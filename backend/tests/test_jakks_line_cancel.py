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
    b=openpyxl.load_workbook(BytesIO(out));assert b['ITEM表']['B5'].value=='已走货';assert b['ITEM表']['B7'].value is None
    v=u.create_unified_customer_preview(**args());row=v['rows'][0]
    old=u.UnifiedHistoryRow(row=5,contract_no=row['contract_no'],reference_no=row['confirmation_no'],po_no=row['po_no'],product_no=row['product_no'],quantity=row['quantity'],requested_ship_date=row['requested_ship_date'])
    assert cancellation_matches(row,[old])==[old]
    assert cancellation_matches(row,[old, replace(old,row=6)])==[]


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
    assert [r.order_type for r in h if r.contract_no=='811784']==['正单']
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False).replace('Line#: 1.000',''),False))
    first,_,_=u.export_unified_customer_schedule(**args(files=[('CXL.pdf',b'cancel')]))
    again,_,_=u.export_unified_customer_schedule(**args(first,[('CXL.pdf',b'cancel')]))
    assert len([r for r in u.read_unified_history(again,factory_id='huadeng',customer_code='jakks') if r.contract_no=='811784'])==0


def test_formal_precedes_sup_and_upgrade_keeps_amount_formula(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda path: (contract_text(formal='formal' in path.name),False))
    for files in ([('order-SUP.pdf',b'sup'),('formal.pdf',b'formal')],[('formal.pdf',b'formal'),('order-SUP.pdf',b'sup')]):
        v=u.create_unified_customer_preview(**args(files=files));assert v['rows'][0]['unit_price_usd']=='2'
    source,_,_=u.export_unified_customer_schedule(**args(files=[('order-SUP.pdf',b'sup')]))
    w=openpyxl.load_workbook(BytesIO(source));w['接单表']['Q5']='=J5*P5';buf=BytesIO();w.save(buf)
    out,_,_=u.export_unified_customer_schedule(**args(buf.getvalue(),[('formal.pdf',b'formal')]))
    w=openpyxl.load_workbook(BytesIO(out));assert w['接单表']['Q5'].value=='=J5*P5';assert w['接单表']['P5'].value==2


def test_cancel_bare_so_keeps_all_original_fields_and_formulas(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,_=u.export_unified_customer_schedule(**args())
    w=openpyxl.load_workbook(BytesIO(source))
    w['ITEM表']['E5']='5475162'
    w['ITEM表']['R5']='原手工资料'
    for name in ('接单表','正单评审表'): w[name]['D5']='5475162'
    before={(s.title,c.coordinate):deepcopy(c.value) for s in w for c in s._cells.values()}
    stream=BytesIO();w.save(stream)
    out,_,_=u.export_unified_customer_schedule(**args(stream.getvalue(),[('CXL.pdf',b'cancel')]))
    book=openpyxl.load_workbook(BytesIO(out))
    assert book['ITEM表']['B5'].value=='取消单'
    for (name,coord),value in before.items():
        if name=='ITEM表' and coord=='B5': continue
        assert book[name][coord].value==value,(name,coord)
    repeated,_,_=u.export_unified_customer_schedule(**args(out))
    h=u.read_unified_history(repeated,factory_id='huadeng',customer_code='jakks')
    assert len([r for r in h if r.contract_no=='811784'])==1
    assert [r.order_type for r in h if r.contract_no=='811784']==['取消单']


def test_distinct_cancel_lines_cannot_both_claim_one_bare_so(monkeypatch):
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,_=u.export_unified_customer_schedule(**args())
    w=openpyxl.load_workbook(BytesIO(source));w['ITEM表']['E5']='5475162'
    for name in ('接单表','正单评审表'): w[name]['D5']='5475162'
    stream=BytesIO();w.save(stream)
    monkeypatch.setattr(p,'extract_text',lambda _: (text(same=True),False))
    out,_,v=u.export_unified_customer_schedule(**args(stream.getvalue(),[('CXL.pdf',b'cancel')]))
    assert openpyxl.load_workbook(BytesIO(out))['ITEM表']['B5'].value=='正单'
    assert any('批次或三表' in msg for msg in v['warnings'])


def test_prior_generated_notice_is_cleared_only_when_three_sheet_signature_matches(monkeypatch):
    from copy import copy
    from openpyxl.formula.translate import Translator
    monkeypatch.setattr(p,'extract_text',lambda _: (text(two=False),False))
    source,_,initial=u.export_unified_customer_schedule(**args())
    for with_manual in (False, "notes", "packaging", "price", "customer", "summary_note", "cartons", "date_code"):
        w=openpyxl.load_workbook(BytesIO(source))
        for name in ('ITEM表','接单表','正单评审表'):
            s=w[name]
            for c in list(s[5]):
                value=c.value
                if c.data_type=='f':value=Translator(value,origin=c.coordinate).translate_formula(s.cell(7,c.column).coordinate)
                s.cell(7,c.column).value=value
                s.cell(7,c.column)._style=copy(c._style)
            s.cell(7,2).value='取消单'
        for name in ('接单表','正单评审表'):
            for col,field in ((14,'unit_price_hkd'),(15,'amount_hkd'),(16,'unit_price_usd'),(17,'amount_usd')):
                value=initial['rows'][0].get(field)
                w[name].cell(7,col).value=float(value) if value else None
        w['ITEM表']['E5']='5475162'
        for name in ('接单表','正单评审表'):w[name]['D5']='5475162'
        if with_manual == 'notes':w['ITEM表']['R7']='业务独立记录，必须保留'
        if with_manual == 'packaging':w['ITEM表']['T7']='人工改过包装'
        if with_manual == 'price':w['接单表']['P7']=99
        if with_manual == 'customer':w['接单表']['F7']='人工客名'
        if with_manual == 'summary_note':w['接单表']['T7']='人工备注'
        if with_manual == 'cartons':w['ITEM表']['M7']=999
        if with_manual == 'date_code':w['ITEM表']['AC7']='人工日期码'
        stream=BytesIO();w.save(stream)
        out,_,v=u.export_unified_customer_schedule(**args(stream.getvalue(),[('CXL.pdf',b'cancel')]))
        b=openpyxl.load_workbook(BytesIO(out))
        assert b['ITEM表']['B5'].value==('正单' if with_manual else '取消单')
        assert b['ITEM表']['E5'].value=='5475162'
        if with_manual:
            if with_manual == 'notes':assert b['ITEM表']['R7'].value=='业务独立记录，必须保留'
            if with_manual == 'packaging':assert b['ITEM表']['T7'].value=='人工改过包装'
            if with_manual == 'price':assert b['接单表']['P7'].value==99
            assert b['ITEM表']['E7'].value=='5475162-1'
        else:
            assert all(c.value is None for c in b['ITEM表'][7])
            assert all(c.value is None for c in b['接单表'][7])
            assert all(c.value is None for c in b['正单评审表'][7])


def test_legitimate_cancelled_sibling_does_not_cancel_another_bare_so():
    row=dict(contract_no='C',po_no='P',product_no='ITEM',reference_no='SO-1',
        confirmation_no='SO',source_line_no='1',quantity='10',requested_ship_date='2026-12-01')
    old=u.UnifiedHistoryRow(row=5,contract_no='C',po_no='P',product_no='ITEM',reference_no='SO',
        quantity='10',requested_ship_date='2026-12-01',order_type='正单')
    assert cancellation_matches(row,[old,replace(old,row=6,reference_no='SO-1',order_type='取消单')])==[]
