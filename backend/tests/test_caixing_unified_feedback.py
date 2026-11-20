from decimal import Decimal
from io import BytesIO
import openpyxl
import pytest
from app.services import customer_order_caixing as c, customer_order_unified as u
from app.services.customer_order_ledger import identity_for
from test_customer_order_caixing import PLAYMATES_PO_TEXT
from test_customer_order_unified import _template_bytes


def args():
    return dict(factory_id='huaxing',customer_code='caixing',received_date='2026-11-19',
        po_files=[('order.pdf',b'pdf')],schedule_file_name='schedule.xlsx',schedule_content=_template_bytes())


@pytest.mark.parametrize('month,factor',[(1,'0.915'),(3,'0.915'),(4,'0.955'),(10,'0.955'),(11,'0.915'),(12,'0.915')])
def test_delivery_month_factor_and_zero_price(month,factor):
    p=c.CaixingParsedLine(requested_ship_date=f'2026/{month:02d}/01',raw_unit_price_hkd=Decimal('85.8'))
    assert p.price_factor==Decimal(factor) and p.unit_price_hkd==Decimal('85.8')*Decimal(factor)
    p.raw_unit_price_hkd=Decimal(0);assert p.unit_price_hkd==0


def test_mix_groups_source_identity_prices_and_no_double_count(monkeypatch):
    text=PLAYMATES_PO_TEXT
    a=text.index('58120E8 WINX');b=text.index('TOTAL :');group=text[a:b]
    text=text[:b]+group.replace('58120E8-05','58120E8-06')+text[b:]
    monkeypatch.setattr(c,'_extract_pdf_text',lambda *_:text)
    out,_,v=u.export_unified_customer_schedule(**args())
    parents=[r for r in v['rows'] if r['row_role']=='parent'];details=[r for r in v['rows'] if r['row_role']!='parent']
    assert len(parents)==2 and len(details)==4 and v['summary']['total']==4
    assert len({identity_for(r,'caixing') for r in details})==4
    assert not any(i['code'] in {'existing_quantity_conflict','missing_product_matrix_column'} for r in details for i in r['issues'])
    w=openpyxl.load_workbook(BytesIO(out));item=w['ITEM表'];new=[r for r in range(4,item.max_row+1) if str(item.cell(r,6).value)=='OG-1931815']
    heads=[r for r in new if item.cell(r,2).value=='混装组头'];assert len(heads)==2
    assert sum(item.cell(r,11).value or 0 for r in new)==1200
    assert all(item.cell(r,11).value is None for r in heads)
    for sheet in (w['接单表'],w['正单评审表']):
        rows=[r for r in range(4,sheet.max_row+1) if sheet.cell(r,5).value=='OG-1931815']
        assert len(rows)==6
        assert all(sheet.cell(r,14).value is None for r in rows if sheet.cell(r,2).value=='混装组头')
    prices=[c.value for c in w['接单表']._cells.values() if c.column==14 and c.data_type!='f' and isinstance(c.value,(int,float))]
    assert prices.count(float(Decimal('23.27')*Decimal('0.955')))==4
    assert all(h.product_no not in {'58120E8-05','58120E8-06'} for h in u.read_unified_history(out,factory_id='huaxing',customer_code='caixing'))


def test_packaging_conditions_and_manual_price_override(monkeypatch):
    text=PLAYMATES_PO_TEXT.replace('2026/04/08','2026/12/08')+'\nREMARKS :\nUS PACKAGING MUST INCLUDED FRENCH + GP I/S + GP FRANCE IMPORTER & BARCODE INFO PRINTED OR LABEL ON PACKAGING.\nSHIPPING MARKS: SHIPPING MARK AS PER ATTACHMENT.'
    monkeypatch.setattr(c,'_extract_pdf_text',lambda *_:text)
    v=u.create_unified_customer_preview(**args());row=next(r for r in v['rows'] if r['row_role']=='detail')
    assert row['manual']=='法文＋GP说明书' and row['packaging']=='美版彩盒'
    assert 'GP法国' in row['label'] and '附件' in row['carton_mark']
    out,_,v=u.export_unified_customer_schedule(**args(),manual_overrides=[dict(row_id=row['id'],field='unit_price_hkd',value='12.345',issue_key='')])
    assert next(r for r in v['rows'] if r['id']==row['id'])['unit_price_hkd']=='12.345'


def test_summary_mix_columns_fx_formula_and_historical_po_isolation(monkeypatch):
    monkeypatch.setattr(c,'_extract_pdf_text',lambda *_:PLAYMATES_PO_TEXT)
    a=args();book=openpyxl.load_workbook(BytesIO(a['schedule_content']));book['接单表']['P1']=7.6;buf=BytesIO();book.save(buf);a['schedule_content']=buf.getvalue()
    out,_,_=u.export_unified_customer_schedule(**a)
    w=openpyxl.load_workbook(BytesIO(out))
    for name in ('接单表','正单评审表'):
        s=w[name];col=next(x.column for x in s[3] if x.value=='MIX编号')
        added=[r for r in range(4,s.max_row+1) if s.cell(r,5).value=='OG-1931815']
        assert all(s.cell(r,col).value=='58120E8-05' for r in added)
        for r in added:
            if s.cell(r,2).value=='混装组头': continue
            assert s.cell(r,16).data_type=='f' and s.cell(r,17).data_type=='f'
            if name=='接单表': assert '$P$1' in s.cell(r,16).value
    # Same SO/product/MIX with another customer PO is not a duplicate.
    for cell in w['ITEM表']._cells.values():
        if cell.column==6 and cell.row>3 and cell.value=='OG-1931815': cell.value='DIFFERENT-PO'
    buf=BytesIO();w.save(buf);a['schedule_content']=buf.getvalue()
    v=u.create_unified_customer_preview(**a)
    assert not any(i['code']=='duplicate_existing_order' for row in v['rows'] for i in row['issues'])


def test_labels_and_eu_exceptions_are_product_specific():
    from app.services.customer_order_caixing_unified import prepare
    p=c.CaixingParsedLine(requested_ship_date='2026/11/01',source_remarks='''REMARKS: USE US STANDARD PACKAGING EXCEPT 68771, 68791 AND 68963.
FOR 68771, 68791 AND 68963, EU MULTI-LINGUAL PACKAGING.
CUSTOMER'S BUTTON CELL WARNING LABELS AND QR CODE WARNING LABEL. MMPR ITEM: 68695
LABELS ARE CONSIGNED BY CUSTOMER. DISTRIBUTOR LABEL IS NOT REQUIRED.
RFID LABEL REQUIRED FOR WALMART U.S. STORES.''')
    def row(product): return dict(product_no=product,packaging='美版彩盒',lineage={},issues=[],source_po_file_name='test.pdf')
    one=prepare(row('68695E3'),p);assert 'QR码' in one['label'] and 'RFID' in one['label'] and '不需分销商' in one['label']
    other=prepare(row('68771'),p);assert other['packaging']=='EU多语言包装' and 'QR码' not in other['label']


def test_legacy_formula_uses_delivery_factor_and_manual_price_once(monkeypatch):
    from test_customer_order_caixing import build_caixing_schedule
    monkeypatch.setattr(c,'_extract_pdf_text',lambda *_:PLAYMATES_PO_TEXT.replace('2026/04/08','2026/12/08'))
    a=dict(factory_id='huaxing',received_date='2026-11-19',po_files=[('PO.pdf',b'pdf')],schedule_file_name='legacy.xlsx',schedule_content=build_caixing_schedule())
    output,_,v=c.export_caixing_batch_schedule(**a)
    w=openpyxl.load_workbook(BytesIO(output))
    formulas=[str(x.value) for s in w for x in s._cells.values() if x.data_type=='f']
    assert any('23.27*0.915' in f for f in formulas) and not any('23.27*0.955' in f for f in formulas)
