"""P3b isolated acceptance; all stock and prices are synthetic temporary data."""
from dataclasses import replace
from pathlib import Path
import runpy
from concurrent.futures import ThreadPoolExecutor
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from test_cutting_materials import (bridge, client, flow, planned, actor, request_body, send, issue,
    decision, warehouse_post, warehouse_view, ledger)
from test_cutting_ops import BASE, command
from app.services import cutting_usage as usage

URL = BASE+'/orders/line-1/usage'


@pytest.fixture
def custody(bridge):
    p=bridge
    migration=runpy.run_path(str(Path(__file__).parents[1]/'alembic/versions/20261014_0156_cutting_material_usage.py'))
    with p.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration['upgrade']()
    p.cutting_auth['user']=actor('material_request','material_receive','usage_write','usage_review','cost_read','cost_write')
    r=send(p,'request',request_body(p));i=issue(p,r)
    receipt=send(p,'receive',decision(p,i,quantity='4'))
    p.issue_id=i['id'];p.receipt_id=receipt['id']
    return p


def read(p,costs=False):
    response=p.get(URL,params={'factory_id':'huakang-c','with_costs':costs})
    assert response.status_code==200,response.text
    return response.json()


def write(p,action,status=200,**changes):
    body=command(expected_version=read(p)['revision'],day='2026-10-10')|changes
    response=p.post(URL+'/'+action,json=body)
    assert response.status_code==status,response.text
    return response.json(),body


def consume(p,**changes):
    return write(p,'post',issue_id=p.issue_id,consumed_quantity='2',loss_quantity='0.5',counted_remaining='1.5',**changes)


def test_use_counts_signed_balance_once_without_changing_warehouse_stock(custody):
    p=custody;before=warehouse_view(p)['stock']
    posted,body=consume(p)
    assert p.post(URL+'/post',json=body).json()==posted
    result=read(p);row=result['issues'][0]
    assert row['consumed_quantity']=='2' and row['loss_quantity']=='0.5' and row['remaining_quantity']=='1.5'
    assert 'price' not in row and 'cost_at_post' not in result['documents'][0]
    assert 'cost_summary' not in result
    assert warehouse_view(p)['stock']==before
    assert read(p,True)['pending_pricing']==1 and read(p,True)['issues'][0]['normal_cost'] is None


def test_batch_pricing_and_price_revision_are_append_only_and_currency_explicit(custody):
    p=custody;consume(p)
    write(p,'price',issue_id=p.issue_id,unit_cost='3.125',currency='HKD',price_reference='原批次核对发票A')
    result=read(p,True);row=result['issues'][0]
    assert row['normal_cost']=='6.25' and row['loss_cost']=='1.56' and result['amounts']=={'HKD':'7.81'}
    assert result['pending_pricing']==0
    assert result['cost_summary']['tasks'][0]['costs']['HKD']==dict(normal='6.25',loss='1.56',total='7.81')
    write(p,'price',issue_id=p.issue_id,unit_cost='4',currency='HKD',price_reference='同一原批次更正凭据B')
    result=read(p,True)
    assert len(result['price_history'])==2 and result['amounts']=={'HKD':'10.00'}
    assert result['cost_summary']['materials'][0]['costs']['HKD']['total']=='10.00'
    assert result['documents'][0]['cost_at_post'] is None


def test_known_zero_price_requires_explicit_evidence(custody):
    p=custody
    write(p,'price',422,issue_id=p.issue_id,unit_cost='0',currency='CNY',price_reference='')
    write(p,'price',issue_id=p.issue_id,unit_cost='0',currency='CNY',price_reference='客户供料零成本核定')
    consume(p)
    assert read(p,True)['issues'][0]['normal_cost']=='0.00'
    assert read(p,True)['documents'][0]['cost_at_post']['unit_cost']=='0'


@pytest.mark.parametrize('reference', ['    ', '\t \n ', '  A  ', '  采购  '])
@pytest.mark.parametrize('unit_cost', ['0', '3.125'])
def test_batch_cost_reference_is_validated_after_trimming(custody, reference, unit_cost):
    p=custody
    before=read(p,True)
    write(p,'price',422,issue_id=p.issue_id,unit_cost=unit_cost,currency='CNY',price_reference=reference)
    after=read(p,True)
    assert after['revision']==before['revision']
    assert after['price_history']==[] and after['issues'][0]['price'] is None


def test_batch_cost_history_retains_trimmed_meaningful_reference(custody):
    p=custody
    write(p,'price',issue_id=p.issue_id,unit_cost='0',currency='CNY',price_reference='  客户供料成本核定  ')
    consume(p)
    result=read(p,True)
    assert result['price_history'][0]['data']['entry']['price_reference']=='客户供料成本核定'
    assert result['documents'][0]['cost_at_post']['price_reference']=='客户供料成本核定'


def test_use_rejects_unbalanced_or_unreceived_quantities_and_duplicate_day(custody):
    p=custody
    write(p,'post',409,issue_id=p.issue_id,consumed_quantity='5',loss_quantity='0',counted_remaining='0')
    write(p,'post',409,issue_id=p.issue_id,consumed_quantity='1',loss_quantity='0',counted_remaining='0')
    consume(p)
    write(p,'post',409,issue_id=p.issue_id,consumed_quantity='1',loss_quantity='0',counted_remaining='0.5')
    assert len(read(p)['documents'])==1


def test_warehouse_cannot_return_consumed_material_or_void_its_receipt(custody):
    p=custody;consume(p)
    warehouse_post(p,'RETURN',409,original_id=p.issue_id,quantity='2',location_id='bin',business_date='2026-10-11')
    send(p,'void',decision(p,{'id':p.receipt_id}),409)
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='1',location_id='bin',business_date='2026-10-11')
    assert read(p)['issues'][0]['remaining_quantity']=='0.5'


def test_void_and_review_keep_original_history_and_recovery_fences_old_commands(custody):
    p=custody;posted,_=consume(p)
    write(p,'review',document_id=posted['document_id'])
    assert read(p)['documents'][0]['reviewed']
    write(p,'void',document_id=posted['document_id'])
    result=read(p)
    assert result['documents'][0]['voided'] and len(result['documents'][0]['history'])==3
    assert result['issues'][0]['remaining_quantity']=='4'
    body=command(expected_version=result['revision'],day='2026-10-11',issue_id=p.issue_id,consumed_quantity='1',loss_quantity='0',counted_remaining='3')
    assert p.post(BASE+'/orders/line-1/usage-operations/recover',json={'action':'post','command':body}).json()['state']=='abandoned'
    assert p.post(URL+'/post',json=body).status_code==409


def test_cost_permissions_do_not_follow_cutting_read_or_production_writes(custody):
    p=custody;consume(p)
    p.cutting_auth['user']=actor('usage_write',department='production')
    assert p.get(URL,params={'factory_id':'huakang-c','with_costs':True}).status_code==403
    body=command(expected_version=read(p)['revision'],day='2026-10-10',issue_id=p.issue_id,unit_cost='4',currency='CNY',price_reference='成本依据核定')
    assert p.post(URL+'/price',json=body).status_code==403
    p.cutting_auth['user']=actor('cost_read','cost_write',department='production')
    assert p.post(URL+'/price',json=body).status_code==403
    p.cutting_auth['user']=actor('cost_read','cost_write',department='pmc-warehouse')
    assert p.post(URL+'/price',json=body).status_code==200
    assert p.get(URL,params={'factory_id':'huaxing'}).status_code==422


def test_immutable_guards_missing_schema_and_source_cancellation(custody):
    from test_cutting_orders import amend
    p=custody;assert usage.schema_ready(p.engine)
    amend(p,cancelled=True)
    consume(p) # Custody facts of the old executor remain accountable after cancellation.
    with p.engine.connect() as connection:
        with pytest.raises(Exception):
            connection.execute(text('DELETE FROM cutting_ops_material_events'))
        connection.rollback()
        connection.execute(text('DROP TRIGGER cutting_material_no_delete'));connection.commit()
    assert p.get(URL,params={'factory_id':'huakang-c'}).status_code==503


def test_two_writers_cannot_spend_the_same_remaining_material(custody):
    p=custody
    body=command(expected_version=read(p)['revision'],day='2026-10-10',issue_id=p.issue_id,consumed_quantity='3',loss_quantity='0',counted_remaining='1')
    other=body|{'operation_id':'other-concurrent-use'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda b:p.post(URL+'/post',json=b).status_code,[body,other]))
    assert sorted(results)==[200,409]
    assert read(p)['issues'][0]['remaining_quantity']=='1'


def test_dependency_removing_void_day_limits_later_returns_and_receipt_voids(custody):
    p=custody;posted,_=consume(p)
    write(p,'void',document_id=posted['document_id'],day='2026-10-12')
    warehouse_post(p,'RETURN',409,original_id=p.issue_id,quantity='2',location_id='bin',business_date='2026-10-11')
    send(p,'void',decision(p,{'id':p.receipt_id})|{'business_date':'2026-10-11'},409)
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='2',location_id='bin',business_date='2026-10-12')


def test_usage_read_serializes_warehouse_and_usage_snapshots(custody,monkeypatch):
    from threading import Event, Lock
    p=custody
    body=command(expected_version=0,day='2026-10-10',issue_id=p.issue_id,consumed_quantity='2',loss_quantity='0.5',counted_remaining='1.5')
    paused,writer_started=Event(),Event()
    once=Lock();used=False
    original=usage.events
    def interleave(db):
        nonlocal used
        with once:
            first=not used;used=True
        if first:
            paused.set();assert writer_started.wait(5)
        return original(db)
    monkeypatch.setattr(usage,'events',interleave)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader=pool.submit(lambda:p.get(URL,params={'factory_id':'huakang-c'}))
        assert paused.wait(5)
        def writer():
            writer_started.set()
            return p.post(URL+'/post',json=body)
        write_result=pool.submit(writer)
        response=reader.result(timeout=15);posted=write_result.result(timeout=15)
    assert response.status_code==200,response.text
    assert response.json()['revision']==0
    assert posted.status_code==200,posted.text
    assert read(p)['issues'][0]['remaining_quantity']=='1.5'


def test_one_original_batch_price_is_shared_but_currencies_are_not_combined(custody):
    p=custody;consume(p)
    write(p,'price',issue_id=p.issue_id,unit_cost='3.125',currency='HKD',price_reference='批次一实际成本凭据')
    request=ledger(p)['requests'][0]
    second_issue=warehouse_post(p,'ISSUE',original_id=request['id'],batch_id=p.stock_id,quantity='1',counterparty='R01')
    send(p,'receive',decision(p,second_issue,quantity='1'))
    write(p,'post',issue_id=second_issue['id'],consumed_quantity='1',loss_quantity='0',counted_remaining='0')
    result=read(p,True)
    assert result['issues'][0]['price']['version']==result['issues'][1]['price']['version']
    assert result['amounts']=={'HKD':'10.94'}
    stock=warehouse_post(p,'RECEIPT',quantity='5',source_no='other-batch',source_line='1',item_code='FAB-01',item_name='蓝布',unit='米',location_id='bin',lot='LOT-2',counterparty='测试供方')
    other=warehouse_post(p,'ISSUE',original_id=request['id'],batch_id=stock['id'],quantity='1',counterparty='R01')
    send(p,'receive',decision(p,other,quantity='1'))
    write(p,'post',issue_id=other['id'],consumed_quantity='1',loss_quantity='0',counted_remaining='0')
    write(p,'price',issue_id=other['id'],unit_cost='5',currency='CNY',price_reference='批次二实际成本凭据')
    assert read(p,True)['amounts']=={'HKD':'10.94','CNY':'5.00'}


def test_failed_usage_handler_rolls_back_evidence_and_command_atomically(custody,monkeypatch):
    from fastapi import HTTPException
    p=custody;execute=usage.execute
    def fail_after_flush(*args,**kwargs):
        execute(*args,**kwargs)
        raise HTTPException(409,'模拟提交前故障')
    monkeypatch.setattr(usage,'execute',fail_after_flush)
    body=command(expected_version=0,day='2026-10-10',issue_id=p.issue_id,consumed_quantity='2',loss_quantity='0.5',counted_remaining='1.5')
    assert p.post(URL+'/post',json=body).status_code==409
    assert read(p)['revision']==0 and read(p)['documents']==[]


def test_same_day_return_preserves_original_count_and_still_blocks_overreturn(custody):
    p=custody;posted,_=consume(p)
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='1',location_id='bin')
    result=read(p)
    assert result['issues'][0]['remaining_quantity']=='0.5'
    assert result['documents'][0]['entry']['counted_remaining']=='1.5'
    warehouse_post(p,'RETURN',409,original_id=p.issue_id,quantity='1',location_id='bin')
    assert read(p)['issues'][0]['remaining_quantity']=='0.5'


def test_same_day_later_signature_is_after_the_count_snapshot(custody):
    p=custody
    send(p,'void',decision(p,{'id':p.receipt_id}))
    send(p,'receive',decision(p,{'id':p.issue_id},quantity='3'))
    write(p,'post',issue_id=p.issue_id,consumed_quantity='2',loss_quantity='0',counted_remaining='1')
    send(p,'receive',decision(p,{'id':p.issue_id},quantity='1'))
    assert read(p)['issues'][0]['remaining_quantity']=='2'
    assert read(p)['documents'][0]['entry']['counted_remaining']=='1'


def test_legacy_usage_timestamp_keeps_same_day_later_return_operable(custody):
    from app.models.cutting_material_usage import CuttingMaterialEvent
    from sqlalchemy.orm import Session
    p=custody
    # Insert an original-format event, without altering immutable posted evidence.
    with Session(p.engine) as db:
        _,entries=usage.wh.projection(db,'fabric')
        db.add(CuttingMaterialEvent(id='legacy',factory_id='huakang-c',line_id='line-1',version=1,document_id='legacy',action='post',
            data={'entry':{'issue_id':p.issue_id,'day':'2026-10-10','consumed_quantity':'2','loss_quantity':'0.5','counted_remaining':'1.5'},
                  'context':usage.issue_context(entries,p.issue_id)},actor_id='legacy',actor_name='旧文员',created_at=usage.datetime.now(usage.UTC).isoformat(),reason='旧格式凭据'))
        db.commit()
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='1',location_id='bin')
    assert read(p)['issues'][0]['remaining_quantity']=='0.5'


def test_balance_preview_uses_selected_day_and_never_exposes_costs(custody):
    p=custody;consume(p)
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='1',location_id='bin',business_date='2026-10-11')
    response=p.get(BASE+'/orders/line-1/usage-balance',params={'factory_id':'huakang-c','issue_id':p.issue_id,'day':'2026-10-10'})
    assert response.status_code==200,response.text
    hint=response.json()
    assert hint['received_quantity']=='4' and hint['returned_quantity']=='0' and hint['available_quantity']=='1.5'
    assert 'price' not in str(hint) and hint['same_day_document_ids']
    assert read(p)['issues'][0]['remaining_quantity']=='0.5'
    assert p.get(BASE+'/orders/line-1/usage-balance',params={'factory_id':'huaxing','issue_id':p.issue_id,'day':'2026-10-10'}).status_code==422


def test_atomic_correction_links_both_documents_and_keeps_original_cutoff(custody):
    p=custody;original,_=consume(p)
    warehouse_post(p,'RETURN',original_id=p.issue_id,quantity='1',location_id='bin')
    corrected,body=write(p,'correct',document_id=original['document_id'],issue_id=p.issue_id,consumed_quantity='2.25',loss_quantity='0.5',counted_remaining='1.25')
    assert p.post(URL+'/correct',json=body).json()==corrected
    result=read(p);old,new=result['documents']
    assert old['voided'] and old['replaced_by_document_id']==new['id']
    assert new['replaces_document_id']==old['id'] and new['warehouse_cutoff']==old['warehouse_cutoff']
    assert result['issues'][0]['remaining_quantity']=='0.25'
    hint=p.get(BASE+'/orders/line-1/usage-balance',params={'factory_id':'huakang-c','issue_id':p.issue_id,'day':'2026-10-10','document_id':new['id']}).json()
    assert hint['available_quantity']=='4' and hint['returned_quantity']=='0'


def test_correction_failure_keeps_original_and_points_to_later_dependency(custody):
    p=custody;original,_=consume(p)
    later,_=write(p,'post',day='2026-10-11',issue_id=p.issue_id,consumed_quantity='1',loss_quantity='0',counted_remaining='0.5')
    version=read(p)['revision']
    body=command(expected_version=version,day='2026-10-10',document_id=original['document_id'],issue_id=p.issue_id,consumed_quantity='2.25',loss_quantity='0.5',counted_remaining='1.25')
    response=p.post(URL+'/correct',json=body)
    assert response.status_code==409 and later['document_id'] in response.json()['detail']
    result=read(p)
    assert result['revision']==version and len(result['documents'])==2 and not result['documents'][0]['voided']
    assert p.post(URL+'/correct',json=body|{'day':'2026-10-09'}).status_code==422


def test_correction_permission_recovery_and_stale_original(custody):
    p=custody;original,_=consume(p)
    body=command(expected_version=read(p)['revision'],day='2026-10-10',document_id=original['document_id'],issue_id=p.issue_id,consumed_quantity='1',loss_quantity='0',counted_remaining='3')
    p.cutting_auth['user']=actor('usage_review',department='production')
    assert p.post(URL+'/correct',json=body).status_code==403
    p.cutting_auth['user']=actor('usage_write',department='production')
    recovered=p.post(BASE+'/orders/line-1/usage-operations/recover',json={'action':'correct','command':body})
    assert recovered.status_code==200 and recovered.json()['state']=='abandoned'
    assert p.post(URL+'/correct',json=body).status_code==409


def test_later_receipts_cannot_replace_evidence_before_the_original_count(custody):
    p=custody
    send(p,'void',decision(p,{'id':p.receipt_id}))
    first=send(p,'receive',decision(p,{'id':p.issue_id},quantity='3'))
    write(p,'post',issue_id=p.issue_id,consumed_quantity='2',loss_quantity='0',counted_remaining='1')
    send(p,'receive',decision(p,{'id':p.issue_id},quantity='1'))
    send(p,'void',decision(p,first),409)
    assert read(p)['issues'][0]['remaining_quantity']=='2'


def test_same_day_return_and_correction_compete_for_one_remaining_balance(custody):
    p=custody;original,_=consume(p)
    correction=command(expected_version=read(p)['revision'],day='2026-10-10',document_id=original['document_id'],issue_id=p.issue_id,consumed_quantity='3.5',loss_quantity='0',counted_remaining='0.5')
    returned=dict(factory_id='huakang-c',request_id='c0b113fd-a80c-4d84-a11f-57129cd4b4e9',expected_revision=warehouse_view(p)['revision'],kind='RETURN',business_date='2026-10-10',reason='并发退料依据',original_id=p.issue_id,quantity='1',location_id='bin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(lambda:p.post(URL+'/correct',json=correction))
        second=pool.submit(lambda:p.post('/api/warehouse-operations/fabric/documents',json=returned))
        assert sorted([first.result().status_code,second.result().status_code])==[200,409]
    assert usage.wh.decimal(read(p)['issues'][0]['remaining_quantity'])>=0
