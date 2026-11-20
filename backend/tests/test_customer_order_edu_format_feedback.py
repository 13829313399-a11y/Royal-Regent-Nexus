"""Distinct source variants, shared display references and consistent EDU output."""
from copy import copy
from datetime import date
from io import BytesIO
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from app.services import customer_order_unified as service
from app.services.huaxing_order_legacy import edu_grouped_export as writer, edu_schedule
from test_customer_order_edu_grouped_export import template, reserve, order, PRODUCT, contents, find_row
from test_edu_order_identity import preview_args, po_bytes
from test_customer_order_edu_controls import stock_book


def test_full_colour_variants_share_group_but_never_order_identity():
    wb=stock_book()
    args=preview_args(po_bytes(['SAME','SAME'],products=[PRODUCT+'0017',PRODUCT+'0023'],pos=['P1','P1'],quantities=[3000,3000]),wb)
    preview=service.create_unified_customer_preview(**args)
    assert [r['product_no'] for r in preview['rows']]==[PRODUCT+'0017',PRODUCT+'0023']
    assert len({r['reference_no'] for r in preview['rows']})==2
    output,_,_=service.export_unified_customer_schedule(**args)
    after=openpyxl.load_workbook(BytesIO(output))
    stock=next(r for r in writer.reservation_candidates(after,PRODUCT) if r['po']=='P1')
    assert stock['quantity']=='=0-3000-3000'
    assert after['PO订单'].max_row==3
    for sheet in writer.SHEETS:
        productcol=writer._columns(after[sheet])[1]
        assert sum(after[sheet].cell(r,productcol).value in [PRODUCT+'0017',PRODUCT+'0023'] for r in range(4,after[sheet].max_row+1))==2
    retried,_,_=service.export_unified_customer_schedule(**{**args,'schedule_content':output})
    assert contents(after)==contents(openpyxl.load_workbook(BytesIO(retried)))


def test_shared_manual_number_exports_both_customer_orders_and_retries_once():
    args=preview_args(po_bytes(['C1','C2'],products=[PRODUCT+'0000']*2,pos=['P1','P1']),stock_book())
    preview=service.create_unified_customer_preview(**args)
    overrides=[]
    for row in preview['rows']:
        issue=next(i for i in row['issues'] if i.get('edit_field')=='reference_no')
        overrides.append(dict(row_id=row['id'],issue_key=issue['skip_key'],field='reference_no',value='EDUHX00666'))
    output,_,resolved=service.export_unified_customer_schedule(**args,manual_overrides=overrides)
    assert all(r['reference_no']=='EDUHX00666' for r in resolved['rows'])
    assert not any(i['code']=='edited_identity_overlap' for r in resolved['rows'] for i in r['issues'])
    book=openpyxl.load_workbook(BytesIO(output))
    assert sum(c.value=='EDUHX00666' for c in book['ITEM表']['E'])==2
    retry,_,_=service.export_unified_customer_schedule(**{**args,'schedule_content':output})
    assert contents(book)==contents(openpyxl.load_workbook(BytesIO(retry)))


def test_summary_batch_is_contiguous_in_input_order_and_blue_without_history_restyle():
    wb=template();reserve(wb,6)
    second='F12-YY902-C902';reserve(wb,9,product=second+'0000',reference='EDUHX00011')
    for name in writer.SHEETS[1:]:
        wb[name]['D7']='OLD-SECOND';wb[name]['G7']=second+'0000';wb[name]['J7']=100
        wb[name]['N7'].fill=PatternFill('solid',fgColor='FFFFFF00')
    oldstyles=[(c,copy(c._style),c.value) for s in wb for c in s._cells.values() if c.data_type!='f']
    rows=[order(reference_no='N1',edu_reservation_row='6'),order(reference_no='N2',product_no=second,source_product_no=second+'0001',contract_no='C2',edu_reservation_row='9'),order(reference_no='N3',contract_no='C3',edu_reservation_row='6')]
    writer.export_rows(wb,rows)
    for name in writer.SHEETS[1:]:
        assert [wb[name].cell(r,4).value for r in (8,9,10)]==['N1','N2','N3']
        for r in (8,9,10):
            assert all(c.font.color.type=='rgb' and c.font.color.rgb[-6:]=='0000FF' for c in wb[name][r])
            assert wb[name].cell(r,7).alignment.wrapText
            assert "'ITEM表'!K" in wb[name].cell(r,10).value
    for cell,style,value in oldstyles:
        assert cell._style==style or (not cell.has_style and not style)
        if cell.column!=11:assert cell.value==value


def test_new_summaries_precede_annual_total_and_include_new_amounts():
    wb=template()
    for name in writer.SHEETS[1:]:
        wb[name]['J8']='2026年接单合计';wb[name]['O8']='=SUM(O4:O4)'
    writer.export_rows(wb,[order()])
    for name in writer.SHEETS[1:]:
        assert wb[name]['D5'].value=='EDUHX00104'
        assert wb[name]['J9'].value=='2026年接单合计'
        assert wb[name]['O9'].value=='=SUM(O4:O5)'


def test_selective_summary_sum_is_not_broadened_to_new_orders():
    wb=template()
    for name in writer.SHEETS[1:]:
        wb[name]['D7']='OLD-SECOND';wb[name]['G7']=PRODUCT+'0001'
        wb[name]['J10']='2026年接单合计'
        wb[name]['O10']='=SUM(O4:O4)';wb[name]['Q10']='=SUM(Q4:Q7)'
    writer.export_rows(wb,[order()])
    for name in writer.SHEETS[1:]:
        assert wb[name]['O11'].value=='=SUM(O4:O4)'
        assert wb[name]['Q11'].value=='=SUM(Q4:Q8)'


def test_source_and_manual_weekend_dates_roll_back_to_friday_not_blank_today():
    row=dict(customer_type='EDU',item_no=PRODUCT+'0017',ship_date='2026-12-19')
    edu_schedule.add_derived_fields(row)
    assert row['ship_date']=='2026-12-18' and row['source_ship_date']=='2026-12-19'
    assert row['inspection_date']=='2026-12-11'
    empty=dict(customer_type='EDU',item_no=PRODUCT);edu_schedule.add_derived_fields(empty)
    assert not empty['ship_date'] and not empty['inspection_date']
    from app.services.customer_order_edu import validate_controls
    record=dict(id='r',product_no=PRODUCT+'0017',quantity='100',units_per_carton='10',requested_ship_date='2026-12-20',customer_q='2026-12-10',issues=[])
    validate_controls(template(),[record],[dict(row_id='r',field='requested_ship_date')])
    assert record['requested_ship_date']=='2026-12-18' and record['customer_q']=='2026-12-11'
    wb=template();writer.export_rows(wb,[order(**record)])
    r=find_row(wb['ITEM表'],'EDUHX00104')
    assert wb['ITEM表'].cell(r,25).value==date(2026,12,11)
    assert wb['ITEM表'].cell(r,26).value==date(2026,12,18)


def test_precise_full_history_duplicate_wins_over_ambiguous_short_row():
    wb=stock_book();s=wb['ITEM表']
    for r,product in [(7,PRODUCT),(8,PRODUCT+'0017')]:
        for col,value in {4:'C1',5:'EDUHX00050',6:'P1',8:product,11:3000}.items():s.cell(r,col,value)
    args=preview_args(po_bytes(['C1'],products=[PRODUCT+'0017'],pos=['P1'],quantities=[3000]),wb)
    output,_,preview=service.export_unified_customer_schedule(**args)
    assert preview['rows'][0]['_edu_existing_order']
    assert 'ITEM待补资料' not in openpyxl.load_workbook(BytesIO(output)).sheetnames
