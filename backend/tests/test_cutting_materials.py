"""P3a cross-domain acceptance. Temporary SQLite only; no real inventory writes."""
import json
from dataclasses import replace
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from test_cutting_ops import client, user, command, BASE
from test_cutting_orders import flow, read as order_read, amend
from test_cutting_planning import planned, resource, task, save, publish
from app.api import warehouse_operations as warehouse_api
from app.models.fabric_master import FabricMasterRecord
from app.models.warehouse_operations import WarehouseOperation
from app.services import warehouse_operations as wh
from app.services.auth import AuthGrantContext

URL=BASE+'/orders/line-1/materials'

def actor(*cutting, warehouse=True, department='*'):
    u=user('read',*cutting,department=department)
    codes=u.permissions | (frozenset(['fabric_operations:read','fabric_operations:operate','fabric_operations:correct']) if warehouse else frozenset())
    return replace(u,permissions=codes,active_permission_codes=codes,grants=(AuthGrantContext(role_id='test',role_name='Test',factory_id='huakang-c',department=department,permissions=codes),))

@pytest.fixture
def bridge(planned):
    p,_=planned
    r=resource(p)
    assert save(p,[task(r)]).status_code==200
    assert publish(p).status_code==200
    p.app.include_router(warehouse_api.router)
    # Import authoritative warehouse models, then create isolated fixture tables only.
    tables=[t for t in WarehouseOperation.metadata.sorted_tables if t.name.startswith('fabric_') or t.name=='warehouse_operations_documents']
    WarehouseOperation.metadata.create_all(p.engine,tables=tables)
    with Session(p.engine) as db:
        for key,kind,code,name,data in [('fabric-mat','MATERIAL','FAB-01','蓝布',dict(category='FABRIC',unit='米',spec='规格A',color='蓝')),('bin','LOCATION','A01','A01',dict(warehouse='布料一仓'))]:
            db.add(FabricMasterRecord(id=key,factory_id='huakang-c',kind=kind,code=code,name=name,status='ACTIVE',revision=1,data_json=json.dumps(data),updated_at='2026-10-10'))
        db.commit()
    p.cutting_auth['user']=actor('material_request','material_receive')
    stock=warehouse_post(p,'RECEIPT',quantity='20',source_no='test-stock',source_line='1',item_code='FAB-01',item_name='蓝布',unit='米',location_id='bin',lot='LOT-1',counterparty='测试供方')
    p.stock_id=stock['id']
    return p

def ledger(p):
    result=p.get(URL,params={'factory_id':'huakang-c'});assert result.status_code==200,result.text
    return result.json()

def request_body(p,**changes):
    o=order_read(p)
    return command(expected_version=o['current']['version'],task_id='task-1',plan_version=o['current']['data']['planning']['published']['version'],row=0,material_id='fabric-mat',material_revision=1,quantity='6.5',business_date='2026-10-10',mapping_basis='核对规格颜色与单位一致',**changes)

def send(p,action,body,status=200):
    r=p.post(URL+'/'+action,json=body);assert r.status_code==status,r.text
    return r.json()

def warehouse_view(p):
    r=p.get('/api/warehouse-operations/fabric',params={'factory_id':'huakang-c'});assert r.status_code==200,r.text
    return r.json()

def warehouse_post(p,kind,status=200,**changes):
    body=dict(factory_id='huakang-c',request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'],kind=kind,business_date='2026-10-10',reason='现场凭据核对') | changes
    r=p.post('/api/warehouse-operations/fabric/documents',json=body);assert r.status_code==status,r.text
    return r.json()

def issue(p,request,quantity='4',status=200):
    return warehouse_post(p,'ISSUE',status=status,original_id=request['id'],batch_id=p.stock_id,quantity=quantity,counterparty='R01')

def decision(p,original,**kw):
    return command(expected_version=ledger(p)['revision'],original_id=original['id'],business_date='2026-10-10',**kw)

def test_request_partial_issue_receipt_return_close_single_inventory(bridge):
    p=bridge; body=request_body(p); r=send(p,'request',body)
    assert send(p,'request',body)==r
    assert warehouse_view(p)['stock'][0]['quantity']=='20'
    issued=issue(p,r)
    assert warehouse_view(p)['stock'][0]['quantity']=='16'
    receipt=send(p,'receive',decision(p,issued,quantity='2.5'))
    assert ledger(p)['requests'][0]['issues'][0]['received_quantity']=='2.5'
    assert warehouse_view(p)['stock'][0]['quantity']=='16'
    send(p,'receive',decision(p,issued,quantity='2'),409)
    warehouse_post(p,'RETURN',status=409,original_id=issued['id'],quantity='3',location_id='bin')
    warehouse_post(p,'RETURN',original_id=issued['id'],quantity='1',location_id='bin')
    send(p,'void',decision(p,receipt),409)
    send(p,'close',decision(p,r))
    issue(p,r,quantity='1',status=409)
    assert ledger(p)['requests'][0]['closed']
    assert sum(wh.decimal(b['quantity']) for b in warehouse_view(p)['stock'])==17


def test_receipt_reversal_and_issue_correction_preserve_history(bridge):
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r)
    a=send(p,'receive',decision(p,i,quantity='1'))
    warehouse_post(p,'CORRECTION',status=409,original_id=i['id'])
    send(p,'void',decision(p,a))
    warehouse_post(p,'CORRECTION',original_id=i['id'])
    result=ledger(p)['requests'][0]
    assert result['receipts'][0]['reversed'] and result['issues'][0]['reversed']
    assert result['issued_quantity']=='0' and warehouse_view(p)['stock'][0]['quantity']=='20'
    send(p,'receive',decision(p,i,quantity='1'),409)


def test_source_change_blocks_issue_but_preserves_historical_settlement(bridge):
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r)
    amend(p,cancelled=True)
    issue(p,r,quantity='1',status=409)
    send(p,'receive',decision(p,i,quantity='1'))
    send(p,'close',decision(p,r))
    warehouse_post(p,'RETURN',original_id=i['id'],quantity='1',location_id='bin')


@pytest.mark.parametrize('changes,status',[({'quantity':'0'},422),({'quantity':'0.0000001'},422),({'quantity':'NaN'},422),({'material_revision':2},409),({'expected_version':0},409),({'plan_version':1},409),({'row':99},422),({'factory_id':'huaxing'},422),({'mapping_basis':''},422)])
def test_invalid_request_is_atomic(bridge,changes,status):
    p=bridge;body=request_body(p);before=warehouse_view(p)['revision'];send(p,'request',body|changes,status)
    assert warehouse_view(p)['revision']==before and ledger(p)['requests']==[]


def test_spoof_and_permissions_are_rejected(bridge):
    p=bridge
    warehouse_post(p,'REQUEST',status=422,source_system='CUTTING_P3A',source_no='fake',source_line='1',item_code='FAB-01',item_name='蓝布',unit='米',quantity='1',counterparty='R01')
    warehouse_post(p,'CUTTING_RECEIPT',status=422,original_id='fake',quantity='1')
    body=request_body(p);p.cutting_auth['user']=actor(warehouse=True)
    send(p,'request',body,403)
    p.cutting_auth['user']=actor('material_request',department='engineering')
    send(p,'request',body,403)
    p.cutting_auth['user']=actor('material_request',warehouse=False,department='production')
    r=send(p,'request',body)
    assert p.get('/api/warehouse-operations/fabric',params={'factory_id':'huakang-c'}).status_code==403
    send(p,'receive',command(expected_version=ledger(p)['revision'],original_id=r['id'],quantity='1',business_date='2026-10-10'),403)


def test_retry_fencing_and_stale_acknowledgement(bridge):
    p=bridge;body=request_body(p);r=send(p,'request',body)
    send(p,'request',body|{'quantity':'7'},409)
    i=issue(p,r);receipt=decision(p,i,quantity='1');send(p,'receive',receipt)
    send(p,'receive',receipt|{'operation_id':uuid4().hex},409)
    pending=request_body(p)
    response=p.post(BASE+'/orders/line-1/material-operations/recover',json={'action':'request','command':pending})
    assert response.status_code==200 and response.json()['state']=='abandoned'
    send(p,'request',pending,409)


def test_catalog_is_whitelisted_and_unit_or_material_changes_block(bridge):
    p=bridge;response=p.get(BASE+'/warehouse-materials',params={'factory_id':'huakang-c'})
    assert response.status_code==200 and set(response.json()['items'][0])=={'id','code','name','revision','unit','category','spec','color'}
    r=send(p,'request',request_body(p))
    with Session(p.engine) as db:
        m=db.get(FabricMasterRecord,'fabric-mat');m.revision+=1;db.commit()
    issue(p,r,status=409)
    with Session(p.engine) as db:
        m=db.get(FabricMasterRecord,'fabric-mat');data=json.loads(m.data_json);data['unit']='码';m.data_json=json.dumps(data);db.commit()
    send(p,'request',request_body(p)|{'material_revision':2},422)
    frozen=ledger(p)['requests'][0]['context']['warehouse_material']
    assert frozen['unit']=='米' and frozen['spec']=='规格A' and frozen['color']=='蓝' and frozen['revision']==1


def test_issue_retry_survives_unreleased_source_change(bridge):
    from test_cutting_orders import Line
    p=bridge;r=send(p,'request',request_body(p))
    body=dict(factory_id='huakang-c',request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'],kind='ISSUE',business_date='2026-10-10',original_id=r['id'],batch_id=p.stock_id,quantity='1',counterparty='R01')
    url='/api/warehouse-operations/fabric/documents'
    first=p.post(url,json=body);assert first.status_code==200,first.text
    with Session(p.engine) as db:
        line=db.get(Line,'line-1');line.version+=1;db.commit()
    assert p.post(url,json=body).json()==first.json()
    assert p.post(url,json=body|{'request_id':str(uuid4()),'expected_revision':warehouse_view(p)['revision']}).status_code==409


def test_returns_require_received_quantity_as_of_return_date(bridge):
    p=bridge
    stock=warehouse_post(p,'RECEIPT',business_date='2026-10-01',quantity='10',source_no='earlier-stock',source_line='1',item_code='FAB-01',item_name='蓝布',unit='米',location_id='bin',lot='EARLY',counterparty='供方')
    r=send(p,'request',request_body(p)|{'business_date':'2026-10-01'})
    i=warehouse_post(p,'ISSUE',business_date='2026-10-02',original_id=r['id'],batch_id=stock['id'],quantity='4',counterparty='R01')
    send(p,'receive',decision(p,i,quantity='1')|{'business_date':'2026-10-03'})
    send(p,'receive',decision(p,i,quantity='2')|{'business_date':'2026-10-10'})
    warehouse_post(p,'RETURN',status=409,business_date='2026-10-09',original_id=i['id'],quantity='2',location_id='bin')
    warehouse_post(p,'RETURN',business_date='2026-10-09',original_id=i['id'],quantity='1',location_id='bin')
    warehouse_post(p,'RETURN',business_date='2026-10-10',original_id=i['id'],quantity='2',location_id='bin')
    assert ledger(p)['requests'][0]['issues'][0]['returned_quantity']=='3'


def test_concurrent_receipt_retries_and_revision_conflicts(bridge):
    from concurrent.futures import ThreadPoolExecutor
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r);body=decision(p,i,quantity='1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda b:p.post(URL+'/receive',json=b),[body,body]))
    assert [r.status_code for r in replies]==[200,200]
    assert len(ledger(p)['requests'][0]['receipts'])==1
    body=decision(p,i,quantity='1')
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda b:p.post(URL+'/receive',json=b),[body,body|{'operation_id':uuid4().hex}]))
    assert sorted(r.status_code for r in replies)==[200,409]
    assert ledger(p)['requests'][0]['issues'][0]['received_quantity']=='2'


def test_bridge_failure_rolls_back_both_domains(bridge,monkeypatch):
    from fastapi import HTTPException
    from app.models.cutting_ops import CuttingCommand
    p=bridge;before=warehouse_view(p)['revision'];body=request_body(p);original=wh.post
    def failing(*args,**kwargs):
        original(*args,**kwargs)
        raise HTTPException(409,'模拟提交失败')
    monkeypatch.setattr(wh,'post',failing)
    send(p,'request',body,409)
    assert warehouse_view(p)['revision']==before
    with Session(p.engine) as db:
        assert db.get(CuttingCommand,body['operation_id']) is None


def test_missing_warehouse_schema_fails_closed(bridge):
    p=bridge
    WarehouseOperation.__table__.drop(p.engine)
    assert p.get(URL,params={'factory_id':'huakang-c'}).status_code==503


def early_issue(p):
    stock=warehouse_post(p,'RECEIPT',business_date='2026-10-01',quantity='10',source_no='early-audit',source_line='1',item_code='FAB-01',item_name='蓝布',unit='米',location_id='bin',lot='EARLY',counterparty='供方')
    r=send(p,'request',request_body(p)|{'business_date':'2026-10-01','due_date':'2026-10-05'})
    i=warehouse_post(p,'ISSUE',business_date='2026-10-02',original_id=r['id'],batch_id=stock['id'],quantity='5',counterparty='R01')
    return r,i


def test_backfilled_return_checks_all_dates_and_ignores_reversed_returns(bridge):
    p=bridge;r,i=early_issue(p)
    send(p,'receive',decision(p,i,quantity='2')|{'business_date':'2026-10-03'})
    send(p,'receive',decision(p,i,quantity='3')|{'business_date':'2026-10-09'})
    future=warehouse_post(p,'RETURN',business_date='2026-10-10',original_id=i['id'],quantity='3',location_id='bin')
    warehouse_post(p,'RETURN',business_date='2026-10-04',original_id=i['id'],quantity='2',location_id='bin')
    warehouse_post(p,'RETURN',status=409,business_date='2026-10-04',original_id=i['id'],quantity='0.1',location_id='bin')
    warehouse_post(p,'CORRECTION',original_id=future['id'])
    warehouse_post(p,'RETURN',business_date='2026-10-09',original_id=i['id'],quantity='3',location_id='bin')
    row=ledger(p)['requests'][0]
    assert row['issues'][0]['returned_quantity']=='5'
    assert row['due_date']=='2026-10-05'
    assert {e['kind'] for e in row['history']} >= {'RETURN','CORRECTION','CUTTING_RECEIPT','REQUEST','ISSUE'}
    assert next(e for e in row['history'] if e['id']==future['id'])['reversed']
    assert all(e['actor'] and e['occurred_at'] for e in row['history'])


def test_return_correction_releases_dependencies_but_dates_remain_ordered(bridge):
    p=bridge;r,i=early_issue(p)
    sig=send(p,'receive',decision(p,i,quantity='5')|{'business_date':'2026-10-03'})
    ret=warehouse_post(p,'RETURN',business_date='2026-10-04',original_id=i['id'],quantity='3',location_id='bin')
    correction=warehouse_post(p,'CORRECTION',business_date='2026-10-08',original_id=ret['id'])
    warehouse_post(p,'CORRECTION',original_id=ret['id'],status=409)
    send(p,'void',decision(p,sig)|{'business_date':'2026-10-07'},409)
    void=send(p,'void',decision(p,sig)|{'business_date':'2026-10-09'})
    warehouse_post(p,'CORRECTION',business_date='2026-10-08',original_id=i['id'],status=409)
    warehouse_post(p,'CORRECTION',business_date='2026-10-09',original_id=i['id'])
    row=ledger(p)['requests'][0]
    assert row['issued_quantity']=='0' and row['issues'][0]['returned_quantity']=='0'
    assert {correction['id'],void['id']} <= {e['id'] for e in row['history']}
    assert sum(wh.decimal(b['quantity']) for b in warehouse_view(p)['stock'])==30


def test_used_return_batch_cannot_be_reversed(bridge):
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r)
    send(p,'receive',decision(p,i,quantity='4'))
    ret=warehouse_post(p,'RETURN',original_id=i['id'],quantity='3',location_id='bin')
    warehouse_post(p,'ISSUE',batch_id=ret['id'],quantity='1',counterparty='另一个车间')
    warehouse_post(p,'CORRECTION',original_id=ret['id'],status=409)
    assert ledger(p)['requests'][0]['issues'][0]['returned_quantity']=='3'


def test_warehouse_recovery_fences_late_requests_and_is_actor_bound(bridge):
    p=bridge;r=send(p,'request',request_body(p))
    body=dict(factory_id='huakang-c',request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'],kind='ISSUE',business_date='2026-10-10',original_id=r['id'],batch_id=p.stock_id,quantity='1',counterparty='R01')
    url='/api/warehouse-operations/fabric/documents'
    result=p.post(url+'/recover',json=body);assert result.status_code==200,result.text
    assert result.json()['state']=='abandoned'
    assert p.post(url,json=body).status_code==409
    assert p.post(url+'/recover',json=body|{'quantity':'2'}).status_code==409
    assert warehouse_view(p)['stock'][0]['quantity']=='20'
    body.update(request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'])
    assert p.post(url,json=body).status_code==200
    assert p.post(url+'/recover',json=body).json()['state']=='committed'
    assert p.post(url,json=body).status_code==200
    assert warehouse_view(p)['stock'][0]['quantity']=='19'
    assert not any(e['kind']=='COMMAND_ABANDONED' for e in warehouse_view(p)['documents'])
    p.cutting_auth['user']=actor('material_request',warehouse=False)
    assert p.post(url+'/recover',json=body).status_code==403


def replan(p, **changes):
    from app.services.cutting_planning_schemas import PlanTask
    current=order_read(p)['current']['data']['planning']['published']['tasks'][0]
    updated={k:v for k,v in current.items() if k in PlanTask.model_fields}|changes
    p.cutting_auth['user']=actor('material_request','material_receive','plan_write','plan_publish')
    response=save(p,[updated],reason='核对实际领料后调整排期');assert response.status_code==200,response.text
    response=publish(p,reason='核对实际领料后调整排期');assert response.status_code==200,response.text
    return order_read(p)['current']['data']['planning']['published']['version']


def test_date_only_plan_reuse_explicit_audited_and_repeatable(bridge):
    p=bridge;r=send(p,'request',request_body(p));original=ledger(p)['requests'][0]['context']['plan_version']
    issue(p,r,quantity='1')
    version=replan(p,days=[dict(day='2026-10-16',sets=50)])
    issue(p,r,quantity='1',status=409)
    body=decision(p,r)|{'plan_version':version}
    p.cutting_auth['user']=actor('material_receive')
    send(p,'reuse',body,403)
    p.cutting_auth['user']=actor('material_request','material_receive')
    reuse=send(p,'reuse',body)
    assert send(p,'reuse',body)==reuse
    issue(p,r,quantity='1')
    row=ledger(p)['requests'][0]
    assert row['context']['plan_version']==original and row['accepted_plan_version']==version
    assert row['history'][-2]['kind']=='CUTTING_REQUEST_REUSE'
    version=replan(p,days=[dict(day='2026-10-17',sets=50)])
    issue(p,r,quantity='1',status=409)
    send(p,'reuse',decision(p,r)|{'plan_version':version})
    issue(p,r,quantity='1')
    send(p,'close',decision(p,r))
    send(p,'reuse',decision(p,r)|{'plan_version':version},409)


def test_plan_reuse_rejects_target_quantity_changes(bridge):
    p=bridge;r=send(p,'request',request_body(p))
    version=replan(p,target_sets=40,days=[dict(day='2026-10-16',sets=40)])
    send(p,'reuse',decision(p,r)|{'plan_version':version},409)
    issue(p,r,quantity='1',status=409)


def test_old_accepted_backdated_correction_remains_readable(bridge,monkeypatch):
    p=bridge;r,i=early_issue(p)
    receipt=send(p,'receive',decision(p,i,quantity='1')|{'business_date':'2026-10-09'})
    send(p,'void',decision(p,receipt))
    # Simulate a document accepted by the previous version, in isolated test data.
    with monkeypatch.context() as old_version:
        old_version.setattr(wh,'validate_correction_date',lambda *_:None)
        warehouse_post(p,'CORRECTION',business_date='2026-10-03',original_id=i['id'])
    assert ledger(p)['requests'][0]['issues'][0]['reversed']
    assert sum(wh.decimal(b['quantity']) for b in warehouse_view(p)['stock'])==30


def readonly_warehouse(p):
    u=actor('material_request','material_receive')
    codes=u.permissions-{'fabric_operations:operate','fabric_operations:correct'}
    p.cutting_auth['user']=replace(u,permissions=codes,active_permission_codes=codes,grants=(AuthGrantContext(role_id='test',role_name='Test',factory_id='huakang-c',department='*',permissions=codes),))


@pytest.mark.parametrize('committed',[False,True])
def test_recovery_after_write_revoked_still_requires_original_actor(bridge,committed):
    p=bridge;r=send(p,'request',request_body(p))
    body=dict(factory_id='huakang-c',request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'],kind='ISSUE',business_date='2026-10-10',original_id=r['id'],batch_id=p.stock_id,quantity='1',counterparty='R01')
    url='/api/warehouse-operations/fabric/documents'
    if committed: assert p.post(url,json=body).status_code==200
    readonly_warehouse(p)
    assert p.post(url,json=body).status_code==403
    response=p.post(url+'/recover',json=body)
    assert response.status_code==200,response.text
    assert response.json()['state']==('committed' if committed else 'abandoned')
    p.cutting_auth['user']=replace(p.cutting_auth['user'],id='another-user')
    assert p.post(url+'/recover',json=body).status_code==409


def test_recovery_races_with_original_issue_without_duplicate_stock(bridge):
    from concurrent.futures import ThreadPoolExecutor
    p=bridge;r=send(p,'request',request_body(p))
    body=dict(factory_id='huakang-c',request_id=str(uuid4()),expected_revision=warehouse_view(p)['revision'],kind='ISSUE',business_date='2026-10-10',original_id=r['id'],batch_id=p.stock_id,quantity='1',counterparty='R01')
    url='/api/warehouse-operations/fabric/documents'
    with ThreadPoolExecutor(max_workers=2) as pool:
        original=pool.submit(p.post,url,json=body)
        recovery=pool.submit(p.post,url+'/recover',json=body)
        first,second=original.result(),recovery.result()
    assert second.status_code==200,second.text
    if second.json()['state']=='committed':
        assert first.status_code==200 and warehouse_view(p)['stock'][0]['quantity']=='19'
    else:
        assert first.status_code==409 and warehouse_view(p)['stock'][0]['quantity']=='20'


def test_reuse_rejects_new_material_identity_and_source_cancellation(bridge):
    p=bridge;r=send(p,'request',request_body(p))
    version=replan(p,days=[dict(day='2026-10-16',sets=50)])
    body=decision(p,r)|{'plan_version':version}
    send(p,'reuse',body|{'plan_version':version-1},409)
    with Session(p.engine) as db:
        m=db.get(FabricMasterRecord,'fabric-mat');m.revision+=1;db.commit()
    send(p,'reuse',body,409)
    amend(p,cancelled=True)
    send(p,'reuse',body,409)


def test_current_order_refresh_is_read_only_and_factory_scoped(bridge):
    p=bridge
    response=p.get(BASE+'/orders/line-1',params={'factory_id':'huakang-c'})
    assert response.status_code==200 and response.json()['current']['version']==order_read(p)['current']['version']
    assert p.get(BASE+'/orders/line-1',params={'factory_id':'huaxing'}).status_code==422
    assert p.get(BASE+'/orders/missing',params={'factory_id':'huakang-c'}).status_code==404


def test_receipt_links_mark_published_plan_stale_after_void_without_changing_baseline(bridge):
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r)
    receipt=send(p,'receive',decision(p,i,quantity='2'))
    original_baseline=order_read(p)['current']['data']['planning']['baseline']
    replan(p,date_basis='actual',actual_issue_date='2026-10-10',actual_issue_reference='裁床收妥核对',material_receipt_ids=[receipt['id']])
    current=order_read(p)
    assert not current['planning_summary']['receipt_review_required']
    assert current['current']['data']['planning']['published']['tasks'][0]['material_receipts'][0]['id']==receipt['id']
    send(p,'void',decision(p,receipt))
    current=order_read(p)
    assert current['planning_summary']['receipt_review_required'] and current['planning_summary']['published_stale']
    assert current['current']['data']['planning']['baseline']==original_baseline


def test_receipt_link_rejects_wrong_task_date_and_post_draft_return_changes(bridge):
    from app.services.cutting_planning_schemas import PlanTask
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r)
    receipt=send(p,'receive',decision(p,i,quantity='2'))
    current=order_read(p)['current']['data']['planning']['published']['tasks'][0]
    updated={k:v for k,v in current.items() if k in PlanTask.model_fields}|dict(date_basis='actual',actual_issue_date='2026-10-10',actual_issue_reference='签收核对凭据',material_receipt_ids=[receipt['id']])
    p.cutting_auth['user']=actor('material_request','material_receive','plan_write','plan_publish')
    assert save(p,[updated|{'actual_issue_date':'2026-10-09'}],reason='核对实际领料').status_code==422
    assert save(p,[updated|{'task_id':'other'}],reason='核对实际领料').status_code==409
    assert save(p,[updated],reason='核对实际领料').status_code==200
    warehouse_post(p,'RETURN',original_id=i['id'],quantity='1',location_id='bin')
    assert publish(p,reason='核对实际领料').status_code==409
    assert save(p,[updated],reason='退仓后复核可支持数量').status_code==200
    assert publish(p,reason='退仓后复核可支持数量').status_code==200


def test_material_totals_keep_closed_remainders_returns_and_reversals_distinct(bridge):
    p=bridge;r=send(p,'request',request_body(p));i=issue(p,r,quantity='4')
    send(p,'receive',decision(p,i,quantity='3'))
    warehouse_post(p,'RETURN',original_id=i['id'],quantity='1',location_id='bin')
    send(p,'close',decision(p,r))
    send(p,'request',request_body(p)|{'quantity':'40'})
    total=ledger(p)['totals'][0]
    assert total['requested_quantity']=='46.5' and total['effective_requested_quantity']=='44'
    assert total['issued_quantity']=='4' and total['outstanding_quantity']=='40'
    assert total['received_quantity']=='3' and total['returned_quantity']=='1' and total['net_received_quantity']=='2'
    assert total['exceeds_theoretical']
