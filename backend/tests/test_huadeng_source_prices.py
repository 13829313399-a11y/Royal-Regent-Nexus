"""Original PO prices reach unified exports without legacy FX/rounding loss."""
from io import BytesIO
from decimal import Decimal
import openpyxl
import pytest
from app.services import customer_order_unified as service
from app.services.huadeng_order_legacy import casdon_po_parser, spin_po_parser, simba_po_parser
from test_customer_order_goliath import template


def export(monkeypatch, customer, source):
    if customer=='casdon':
        monkeypatch.setattr(casdon_po_parser.CasdonPOParser,'parse',lambda *a:dict(po_number='P-NEW',customer='Test',ship_date='2026-12-01',lines=[source]))
    elif customer=='spin':
        monkeypatch.setattr(spin_po_parser.SpinPOParser,'parse',lambda *a:dict(po_number='P-NEW',customer='Test',ship_date='2026-12-01',lines=[source]))
    else:
        monkeypatch.setattr(simba_po_parser,'parse_po_file',lambda *a,**k:dict(rows=[source],warnings=[]))
    args=dict(factory_id='huadeng',customer_code=customer,received_date='2026-11-19',po_files=[('po.pdf',b'fixture')],schedule_file_name='schedule.xlsx',schedule_content=template())
    output,_,result=service.export_unified_customer_schedule(**args)
    row=result['rows'][0];book=openpyxl.load_workbook(BytesIO(output))
    r=next(c.row for c in book['接单表']._cells.values() if c.column==4 and str(c.value)==row['reference_no'])
    return row,book,r


def casdon(**kw):
    return dict(item_code='67750',description_en='Toy',qty=100,unit_price=1.23456,total_usd=123.46,**kw)


def spin(**kw):
    raw=dict(line_no='1',material_number='12345678',material_group='67750',sales_material='87654321',qty=1000,unit='PCS',price_per=125.6789,price_per_qty=1000,currency='USD',net_value_pdf=125.68,price_identified=True,price_basis_identified=True,unit_price=.125679,total_usd=125.679,ship_date='2026-12-01')
    raw.update(kw);return raw


def simba(**kw):
    return dict(contract_no='SC700123/10',customer_po='PO123/10',item_no='1234567',quantity=100,unit='PCS',po_ship_date='2026-12-01',outer_pack=10,**kw)


def test_casdon_exact_usd_and_formula_links(monkeypatch):
    row,w,r=export(monkeypatch,'casdon',casdon())
    assert row['unit_price_usd']=='1.23456' and Decimal(row['unit_price_hkd'])==Decimal('9.382656')
    assert row['amount_hkd']=='938.27'
    assert w['接单表'].cell(r,16).value==1.23456
    assert f'P{r}*$P$1' in w['接单表'].cell(r,14).value
    assert any(c.value==f'=IF(LEN(\'接单表\'!P{r})=0,"",\'接单表\'!P{r})' for c in w['ITEM表']._cells.values())


def test_casdon_charge_keeps_source_total_without_quantity(monkeypatch):
    raw=casdon(is_charge=True);raw.update(qty=0,unit_price=None,total_usd=12.345,price_identified=False)
    row,w,r=export(monkeypatch,'casdon',raw)
    assert row['quantity']=='' and row['amount_usd']=='12.345'
    assert row['amount_hkd']=='93.82'
    assert w['接单表'].cell(r,17).value==12.345
    assert f'Q{r}*$P$1' in w['接单表'].cell(r,15).value


@pytest.mark.parametrize('currency,price,expected', [('USD',.1256789,'0.95515964'),('HKD',.1256789,'0.01653669736842105263157894737')])
def test_spin_per_thousand_source_precision(monkeypatch,currency,price,expected):
    row,w,r=export(monkeypatch,'spin',spin(currency=currency))
    src='unit_price_'+currency.lower();target='unit_price_hkd' if currency=='USD' else 'unit_price_usd'
    assert Decimal(row[src])==Decimal(str(price))
    assert abs(Decimal(row[target])-Decimal(expected))<Decimal('0.00000001')
    assert w['接单表'].cell(r,16 if currency=='USD' else 14).value==price


@pytest.mark.parametrize('changes,unit,amount', [({'price_per':0,'net_value_pdf':0},'0','0'),({'price_identified':False},'',''),({'price_basis_identified':False},'','125.68')])
def test_spin_zero_missing_and_missing_per_are_distinct(monkeypatch,changes,unit,amount):
    row,w,r=export(monkeypatch,'spin',spin(**changes))
    assert row['unit_price_usd']==unit and row['amount_usd']==amount
    assert w['接单表'].cell(r,16).value==(0 if unit=='0' else None)


@pytest.mark.parametrize('source,source_col,expected', [({'unit_price_usd':1.23456,'total_usd':123.46},16,1.23456),({'unit_price_hkd':9.54321,'total_hkd':954.32,'currency':'HKD'},14,9.54321)])
def test_simba_original_currency(monkeypatch,source,source_col,expected):
    row,w,r=export(monkeypatch,'simba',simba(**source))
    assert w['接单表'].cell(r,source_col).value==expected
    assert w['正单评审表'].cell(r,source_col).data_type=='f'


def test_simba_both_explicit_prices_remain_independent(monkeypatch):
    row,w,r=export(monkeypatch,'simba',simba(unit_price_hkd=9.1,unit_price_usd=1.2,total_hkd=910,total_usd=120))
    assert row['unit_price_hkd']=='9.1' and row['unit_price_usd']=='1.2'
    assert w['接单表'].cell(r,14).value==9.1 and w['接单表'].cell(r,16).value==1.2
    assert any(i['code']=='dual_source_prices' for i in row['issues'])


def test_unknown_currency_never_becomes_hkd(monkeypatch):
    row,w,r=export(monkeypatch,'simba',simba(unit_price_hkd=9.1,total_hkd=910,currency='EUR'))
    assert row['unit_price_hkd']==row['unit_price_usd']==''
    assert any('EUR' in i['message'] for i in row['issues'])
    assert all(w['接单表'].cell(r,c).value is None for c in range(14,18))


def test_spin_parser_records_explicit_zero_and_basis_presence():
    parser=spin_po_parser.SpinPOParser()
    block=['1 1000 PC 12345678','Sales Material: 87654321 0 USD Per 01/12/2026 0','Material Group: 67750 1000 PC']
    line=parser._parse_product_block(block).to_dict()
    assert line['price_identified'] and line['price_basis_identified'] and line['price_per']==0
    assert not parser._parse_product_block(block[:2]).price_basis_identified
    assert not parser._parse_product_block(block[:1]).price_identified


@pytest.mark.parametrize('price,total,expected', [(0,0,(True,True)),(None,None,(False,False)),(None,10,(False,True)),(2,0,(True,True))])
def test_casdon_excel_zero_missing_and_net_zero(price,total,expected):
    w=openpyxl.Workbook();s=w.active
    s.append(['Line','Item Code','Description','Commodity Code','Quantity','Unit','Unit Price','Net'])
    s.append([1,'67750','Toy','95030000',10,'PCS',price,total])
    lines=casdon_po_parser.CasdonPOParser()._parse_excel_lines(s)
    assert len(lines)==1
    row=lines[0]
    assert (row.price_identified,row.amount_identified)==expected
    assert row.total_usd==(total or 0) and row.unit_price==(price or 0)


@pytest.mark.parametrize('price,total',[(0,125),(125,0)])
def test_explicit_zero_conflict_keeps_amount_and_warns(monkeypatch,price,total):
    row,w,r=export(monkeypatch,'spin',spin(price_per=price,net_value_pdf=total))
    assert Decimal(row['amount_usd'])==Decimal(total)
    assert any(i['code']=='source_price_amount_conflict_usd' for i in row['issues'])
    assert w['接单表'].cell(r,17).value==total
    assert f'Q{r}*$P$1' in w['接单表'].cell(r,15).value


def test_simba_hkd_conflict_survives_common_enrichment(monkeypatch):
    row,w,r=export(monkeypatch,'simba',simba(unit_price_hkd=2,total_hkd=0,currency='HKD'))
    assert Decimal(row['amount_hkd'])==0
    assert w['接单表'].cell(r,15).value==0
    assert any(i['code']=='source_price_amount_conflict_hkd' for i in row['issues'])


def test_fx_uses_unrounded_quantity_price_not_rounded_usd_total(monkeypatch):
    raw=casdon();raw.update(qty=1998,unit_price=.826,total_usd=1650.35)
    row,w,r=export(monkeypatch,'casdon',raw)
    assert row['amount_usd']=='1650.35' and row['amount_hkd']=='12542.64'
    assert f'ROUND(J{r}*N{r},2)' in w['接单表'].cell(r,15).value


@pytest.mark.parametrize('rate',['7.6',True])
def test_text_or_boolean_rate_matches_excel_isnumber(rate):
    from app.services.customer_order_huadeng_usd import apply_preview
    w=openpyxl.load_workbook(BytesIO(template()));w['接单表']['P1']=rate
    row=dict(_huadeng_source_currency='USD',unit_price_usd='1.25',quantity='100',amount_usd='125',issues=[])
    apply_preview(w,[row])
    assert row['unit_price_hkd']==row['amount_hkd']==''
    assert any(i['field']=='exchange_rate' for i in row['issues'])
