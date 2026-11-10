from copy import deepcopy
from io import BytesIO
import openpyxl
import pytest
from app.schemas.customer_order import CustomerOrderIssueOut
from app.services import customer_order_unified as unified
from app.services.customer_order_manual import mark_pending_information, coerce_manual_value
from test_customer_order_unified import _parsed_row, _template_bytes


def arguments(factory='huakang-d',customer='maxx'):
    return dict(factory_id=factory,customer_code=customer,received_date='2026-11-10',
        po_files=[('synthetic.xlsx',b'po')],schedule_file_name='schedule.xlsx',schedule_content=_template_bytes())


def missing(field):
    return dict(severity='blocked',code='missing_'+field,field=field,message=field+'缺失',can_skip=False,skip_key='',skip_label='')


@pytest.mark.parametrize('factory,customer',[('huakang-a','headstart'),('huakang-d','maxx'),('huaxing','disney'),('huadeng','simba')])
def test_all_factories_keep_identified_optional_gaps_without_waiver(monkeypatch,factory,customer):
    row=_parsed_row()
    for field in ('requested_ship_date','line_q','customer_q','units_per_carton','unit_price_hkd','product_name_zh'):
        row[field]=''
        row['issues'].append(missing(field))
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'SYNTHETIC'))
    output,_,preview=unified.export_unified_customer_schedule(**arguments(factory,customer))
    actual=preview['rows'][0]
    assert preview['summary']['blocked']==0
    issues=[i for i in actual['issues'] if i.get('pending_information')]
    assert {'requested_ship_date','units_per_carton','unit_price_hkd'} <= {i['field'] for i in issues}
    assert all(i['severity']=='warning' for i in issues)
    assert CustomerOrderIssueOut.model_validate(issues[0]).pending_information
    book=openpyxl.load_workbook(BytesIO(output),data_only=False)
    try:
        sheet=book['ITEM表'];number=next(r for r in range(4,sheet.max_row+1) if sheet.cell(r,5).value=='SO-1')
        assert sheet.cell(number,11).value==240
        assert all(sheet.cell(number,c).value is None for c in (12,13,25,26))
    finally:book.close()


@pytest.mark.parametrize('field,value',[('quantity',''),('quantity','0'),('quantity','-1'),('quantity','NaN'),('quantity','Infinity'),('product_no',''),('reference_no','')])
def test_core_fields_cannot_be_confirmed_away(monkeypatch,field,value):
    row=_parsed_row();row[field]=value
    if field=='reference_no':row.update(contract_no='',po_no='')
    row['issues']=[missing(field)]
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'SYNTHETIC'))
    preview=unified.create_unified_customer_preview(**arguments())
    assert preview['summary']['blocked']==1
    assert all(not i.get('can_skip') for i in preview['rows'][0]['issues'] if i.get('required_for_intake'))
    keys={i['skip_key'] for i in preview['rows'][0]['issues']}
    with pytest.raises(unified.CustomerOrderUnifiedError,match='数量|订单身份'):
        unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys=keys)


def test_valid_core_manual_correction_is_written(monkeypatch):
    row=_parsed_row();row['quantity']='';row['issues']=[missing('quantity')]
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'SYNTHETIC'))
    preview=unified.create_unified_customer_preview(**arguments());issue=next(i for i in preview['rows'][0]['issues'] if i['field']=='quantity')
    output,_,resolved=unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys={issue['skip_key']},
        manual_overrides=[{'row_id':row['id'],'issue_key':issue['skip_key'],'field':'quantity','value':'120'}])
    assert resolved['rows'][0]['quantity']=='120'
    assert resolved['rows'][0]['status']!='blocked'


def test_fcd_and_inspection_do_not_disappear_when_other_dates_exist():
    row=_parsed_row();row['issues']=[missing('fcd_date'),missing('inspection_date')]
    mark_pending_information(row)
    assert {i['field'] for i in row['issues']}=={'fcd_date','inspection_date'}
    assert all(i['pending_information'] and not i['can_edit'] for i in row['issues'])


@pytest.mark.parametrize('value',[0,-1,'NaN','Infinity'])
def test_invalid_packing_is_not_treated_as_completed(value,monkeypatch):
    row=_parsed_row();row['units_per_carton']=value;row['issues']=[missing('units_per_carton')]
    mark_pending_information(row)
    assert row['issues'][0]['severity']=='blocked' and not row['issues'][0].get('pending_information')
    with pytest.raises(ValueError):coerce_manual_value('units_per_carton',str(value))
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'SYNTHETIC'))
    parsed=unified.create_unified_customer_preview(**arguments());issue=parsed['rows'][0]['issues'][0]
    with pytest.raises(unified.CustomerOrderUnifiedError,match='阻断'):
        unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys={issue['skip_key']})
    _,_,corrected=unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys={issue['skip_key']},
        manual_overrides=[{'row_id':row['id'],'issue_key':issue['skip_key'],'field':'units_per_carton','value':'12'}])
    assert corrected['rows'][0]['units_per_carton']=='12' and corrected['rows'][0]['carton_count']=='20'


def test_zero_price_is_present_and_parent_display_is_unchanged():
    row=_parsed_row();row['unit_price_hkd']=0;row['issues']=[missing('unit_price_hkd')]
    mark_pending_information(row);assert not row['issues']
    parent={**row,'requested_ship_date':'','row_role':'parent','issues':[missing('requested_ship_date')]}
    mark_pending_information(parent)
    assert parent['issues'][0]['severity']=='warning' and not parent['issues'][0]['can_edit']


def test_source_correction_and_edu_identity_remain_blocked():
    row=_parsed_row();row.update(_huaxing_customer='edu',contract_no='',po_no='',reference_no='EDUHX999')
    row['issues']=[{**missing('contract_no'),'requires_source_correction':True},
                   dict(severity='blocked',code='edu_missing_business_identity',field='contract_no',message='缺客户身份')]
    unified._enrich_row(row,[],'EDU')
    assert row['status']=='blocked'
    assert any(i.get('requires_source_correction') for i in row['issues'])
    assert not any(i.get('pending_information') for i in row['issues'] if i['field']=='contract_no')


def test_uncertain_ocr_product_requires_matching_manual_correction(monkeypatch):
    row=_parsed_row();row['issues']=[dict(severity='blocked',code='ocr_product_uncertain',
        field='product_no',message='货号OCR疑点须补录',requires_manual_correction=True)]
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(row)],[],'SYNTHETIC'))
    parsed=unified.create_unified_customer_preview(**arguments());issue=parsed['rows'][0]['issues'][0]
    assert not issue['can_skip'] and issue['can_edit']
    for keys in (set(),{issue['skip_key']}):
        with pytest.raises(unified.CustomerOrderUnifiedError,match='阻断'):
            unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys=keys)
    _,_,resolved=unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys={issue['skip_key']},
        manual_overrides=[{'row_id':row['id'],'issue_key':issue['skip_key'],'field':'product_no','value':'CONFIRMED-123'}])
    assert resolved['rows'][0]['product_no']=='CONFIRMED-123'
    assert resolved['rows'][0]['status']!='blocked'


def test_source_identity_cannot_clear_during_unrelated_recalculation():
    row=_parsed_row();row['issues']=[dict(missing('contract_no'),required_for_intake=True,requires_source_correction=True)]
    unified._recalculate_preview_row(row)
    assert row['issues'][0]['severity']=='blocked'
    with pytest.raises(unified.CustomerOrderUnifiedError,match='阻断'):
        unified._validate_resolutions({'rows':[row]},set())


def test_parent_optional_display_does_not_block_but_unresolved_total_does(monkeypatch):
    child=_parsed_row()
    parent={**deepcopy(child),'id':'summary-parent','row_role':'parent','reference_no':'','contract_no':'','po_no':'',
            'requested_ship_date':'','units_per_carton':'',
            'issues':[missing('requested_ship_date'),{**missing('units_per_carton'),'code':'missing_parent_units_per_carton'}]}
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(parent),deepcopy(child)],[],'SYNTHETIC'))
    _,_,parsed=unified.export_unified_customer_schedule(**arguments())
    assert len(parsed['rows'])==1 and parsed['rows'][0]['row_role']=='detail'
    parent['issues'].append(dict(severity='blocked',code='quantity_conflict',field='quantity',message='父汇总数量矛盾'))
    with pytest.raises(unified.CustomerOrderUnifiedError,match='父汇总数量矛盾'):
        unified.export_unified_customer_schedule(**arguments())


def test_dickie_specialized_missing_prices_editor_survives_pending_policy():
    row=_parsed_row();row['unit_price_hkd']='';row['issues']=[dict(missing('unit_price_hkd'),
        code='missing_po_unit_prices',can_edit=True,edit_field='po_unit_prices',edit_input_type='textarea',edit_label='各PO单价')]
    mark_pending_information(row)
    issue=row['issues'][0]
    assert issue['pending_information'] and issue['edit_field']=='po_unit_prices' and issue['edit_input_type']=='textarea'


@pytest.mark.parametrize('existing_in',['batch','history'])
@pytest.mark.parametrize('other_quantity',['100','240'])
def test_core_correction_cannot_create_new_order_collision(monkeypatch,existing_in,other_quantity):
    row=_parsed_row();row['product_no']='';row['issues']=[missing('product_no')]
    other=_parsed_row(2);other.update(reference_no=row['reference_no'],quantity=other_quantity)
    rows=[row,other] if existing_in=='batch' else [row]
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *_:([deepcopy(r) for r in rows],[],'SYNTHETIC'))
    if existing_in=='history':
        history=[unified.UnifiedHistoryRow(row=4,reference_no=other['reference_no'],product_no=other['product_no'],quantity=other_quantity)]
        monkeypatch.setattr(unified,'read_unified_history',lambda *_,**__:history)
    parsed=unified.create_unified_customer_preview(**arguments());issue=parsed['rows'][0]['issues'][0]
    with pytest.raises(unified.CustomerOrderUnifiedError,match='补录后'):
        unified.export_unified_customer_schedule(**arguments(),skipped_issue_keys={issue['skip_key']},
            manual_overrides=[{'row_id':row['id'],'issue_key':issue['skip_key'],'field':'product_no','value':other['product_no']}])


@pytest.mark.parametrize('wrong_field',['factory_id','customer_code','reference_no','product_no'])
def test_quantity_reconciliation_is_scoped_to_selected_existing_identity(wrong_field):
    row=_parsed_row();row['issues']=[dict(severity='blocked',code='existing_quantity_conflict',field='quantity',
        message='历史数量不同',requires_source_correction=True,can_skip=False)]
    preview={'factory_id':'huaxing','customer_code':'disney','rows':[row]}
    target=dict(factory_id='huaxing',customer_code='disney',reference_no=row['reference_no'],product_no=row['product_no'])
    unified._validate_resolutions(preview,set(),target)
    target[wrong_field]='wrong'
    with pytest.raises(unified.CustomerOrderUnifiedError,match='阻断'):
        unified._validate_resolutions(preview,set(),target)
    with pytest.raises(unified.CustomerOrderUnifiedError,match='阻断'):
        unified._validate_resolutions(preview,set())
