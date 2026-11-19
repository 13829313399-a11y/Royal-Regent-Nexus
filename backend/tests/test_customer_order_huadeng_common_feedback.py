"""Huadeng source-price preservation and manual-date consistency regressions."""
from io import BytesIO
import openpyxl
import pytest
from app.services import customer_order_unified as service, customer_order_regional as regional
from app.services.huadeng_order_legacy import casdon_po_parser, casdon_schedule, simba_po_parser
from test_customer_order_goliath import european_po, template
from test_jakks_supplementary_contract import contract_text, workbook_bytes, parser


def args(customer, content=b'fixture'):
    return dict(factory_id='huadeng', customer_code=customer, received_date='2026-11-19',
                po_files=[('order.pdf', content)], schedule_file_name='schedule.xlsx', schedule_content=template())


def test_goliath_shipping_correction_recomputes_exported_date_code():
    data=args('goliath', european_po())
    preview=service.create_unified_customer_preview(**data)
    row=preview['rows'][0]
    issue=next(i for i in row['issues'] if i['code']=='goliath_delivery_date_conflict')
    output,_,resolved=service.export_unified_customer_schedule(**data,manual_overrides=[dict(
        row_id=row['id'],issue_key=issue['skip_key'],field='requested_ship_date',value='2026-01-26')])
    assert resolved['rows'][0]['date_code']=='RR0166'
    item=openpyxl.load_workbook(BytesIO(output))[service.ITEM_SHEET]
    assert item['U5'].value=='RR0166'
    assert item['Z5'].value.date().isoformat()=='2026-01-26'


def test_casdon_missing_shipping_correction_populates_derived_dates(monkeypatch):
    monkeypatch.setattr(casdon_po_parser.CasdonPOParser,'parse',lambda *a,**k:dict(
        po_number='15286',customer='Casdon UK',ship_date='',version='AW26',
        lines=[dict(item_code='67750',description_en='Toy',qty=100,unit_price=1.5,total_usd=150)]))
    data=args('casdon');preview=service.create_unified_customer_preview(**data);row=preview['rows'][0]
    issue=next(i for i in row['issues'] if i.get('edit_field')=='requested_ship_date')
    output,_,resolved=service.export_unified_customer_schedule(**data,manual_overrides=[dict(
        row_id=row['id'],issue_key=issue['skip_key'],field='requested_ship_date',value='2026-12-19')])
    current=resolved['rows'][0]
    assert current['line_q']==current['customer_q']=='2026-12-11'
    assert current['date_code']==casdon_schedule._date_code(current['product_no'],casdon_schedule.parse_date('2026-12-11'))
    item=openpyxl.load_workbook(BytesIO(output))[service.ITEM_SHEET]
    assert item['Y5'].value.date().isoformat()=='2026-12-11'
    assert item['U5'].value==current['date_code']


@pytest.mark.parametrize('customer',['casdon','goliath'])
def test_explicit_manual_dates_and_codes_take_priority(customer):
    row=dict(_regional_customer=customer,product_no='67750',requested_ship_date='2026-12-19',
             line_q='2026-12-08',customer_q='',date_code='MANUAL',issues=[])
    regional.recalculate_dates(row,{'requested_ship_date','line_q','date_code'})
    assert row['line_q']=='2026-12-08' and row['date_code']=='MANUAL'


@pytest.mark.parametrize('difference', ['unit_price_hkd','outer_pack','customer_label'])
def test_simba_preserves_same_revision_business_differences_and_skips_exact_copy(monkeypatch,difference):
    def parse(content,filename=None):
        row=dict(contract_no='SC700123/10',customer_po='PO123/10',item_no='1234567',
                 quantity=5,unit='PCS',po_ship_date='2026-12-01',outer_pack=10,
                 unit_price_hkd=2.5,total_hkd=12.5,customer_label='label A')
        if content!=b'first':
            row[difference]={'unit_price_hkd':25,'outer_pack':20,'customer_label':'label B'}[difference]
            if difference=='unit_price_hkd':row['total_hkd']=125
        return dict(rows=[row],warnings=[])
    monkeypatch.setattr(simba_po_parser,'parse_po_file',parse)
    data=args('simba');data['po_files']=[('one.pdf',b'first'),('two.pdf',b'second'),('copy.pdf',b'copy')]
    output,_,preview=service.export_unified_customer_schedule(**data)
    assert len(preview['rows'])==2 and preview['summary']['blocked']==0
    assert any('同修订明细有差异' in w for w in preview['warnings'])
    item=openpyxl.load_workbook(BytesIO(output))[service.ITEM_SHEET]
    assert sum(c.value=='1234567' for c in item['H'])==2


def test_jakks_explicit_zero_price_never_inherits_historical_99(monkeypatch):
    monkeypatch.setattr(parser,'extract_text',lambda p:(contract_text(formal=True).replace('2.0000 848.00 USD','0.0000 0.00 USD'),False))
    data=args('jakks');data['schedule_content']=workbook_bytes()
    output,_,preview=service.export_unified_customer_schedule(**data)
    row=preview['rows'][0]
    assert float(row['unit_price_usd'])==float(row['amount_usd'])==0
    assert row['unit_price_hkd']==row['amount_hkd']==''  # No rate in this synthetic template.
    book=openpyxl.load_workbook(BytesIO(output))
    assert book[service.ORDER_SHEET]['N4'].value==99
