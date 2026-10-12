"""Real API, isolated SQLite, no production data or implicit grants."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import runpy
import pytest
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_cutting_ops import client, user, command, BASE
from test_cutting_orders import flow, amend, receive
from test_cutting_planning import planned, resource, task, save, publish

URL=BASE+'/orders/line-1/reports'


@pytest.fixture
def production(planned):
    flow,_=planned
    migration=runpy.run_path(str(Path(__file__).parents[1]/'alembic/versions/20261010_0155_cutting_production_events.py'))
    with flow.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration['upgrade']()
    a,b=resource(flow),resource(flow,'R02','outsourced')
    response=save(flow,[task(a,target_sets=25,days=[dict(day='2026-10-15',sets=25)]),task(b,task_id='external',target_sets=25,days=[dict(day='2026-10-15',sets=25)])])
    assert response.status_code==200,response.text
    assert publish(flow).status_code==200
    flow.cutting_auth['user']=user('read','report_write','report_review','handover_write','acceptance_write','order_receive','plan_write','plan_publish')
    return flow


def read(p, day=None):
    response=p.get(URL,params={'factory_id':'huakang-c',**({'as_of':day} if day else {})})
    assert response.status_code==200,response.text
    return response.json()


def entry(p, **changes):
    t=read(p)['tasks'][0]
    return dict(task_id=t['task_id'],plan_version=t['plan_version'],day='2026-10-15',mode='sets',kind='daily',sets=10,rejected=0,scrap=0,parts=[],evidence='合成现场核套人及凭据',exception_reason='人工核实生产，领料记录待补')|changes


def send(p, action='post', *, document_id=None, payload=None, expected=None, **changes):
    body=command(expected_version=read(p)['version'] if expected is None else expected,document_id=document_id or uuid4().hex,
                 **({'entry':entry(p,**changes) if payload is None else payload} if action in {'save','post'} else {}))
    return p.post(URL+'/'+action,json=body)


def ok(response):
    assert response.status_code==200,response.text
    return response.json()


def doc(response): return response['documents'][-1]['document_id']


def test_draft_post_zero_correction_review_and_months(production):
    p=production
    draft=ok(send(p,'save'));did=doc(draft)
    assert draft['summary']['completed']==0
    posted=ok(send(p,document_id=did))
    assert posted['summary']['completed']==10 and posted['summary']['remaining']==40
    corrected=ok(send(p,'save',document_id=did,sets=12))
    assert corrected['summary']['completed']==10
    posted=ok(send(p,document_id=did,sets=12))
    assert posted['summary']['completed']==12
    reviewed=ok(send(p,'review',document_id=did))
    assert reviewed['documents'][0]['review']['actor_id']=='test-user'
    assert read(p,'2026-10-14')['summary']['completed']==0
    hand=ok(send(p,kind='handover',sets=8))
    assert hand['summary']['actual_delivery']==8 and hand['summary']['plan_difference']==8-50
    assert hand['summary']['months']['2026-10']==dict(planned=50,completed=12,handed=8)
    zero=ok(send(p,day='2026-10-16',sets=0))
    assert zero['documents'][-1]['posted']['data']['entry']['sets']==0
    assert len(zero['documents'][0]['history'])==5


def test_same_day_duplicate_and_dependent_correction_void(production):
    p=production;posted=ok(send(p));did=doc(posted)
    assert send(p).status_code==422
    hand=ok(send(p,kind='handover',sets=9));hid=doc(hand)
    assert send(p,document_id=did,sets=8).status_code==422
    assert send(p,'void',document_id=did).status_code==422
    ok(send(p,'void',document_id=hid))
    result=ok(send(p,'void',document_id=did))
    assert result['summary']['completed']==0
    assert send(p,document_id=did).status_code==409
    ok(send(p))


def test_parts_matching_carries_loose_and_never_counts_twice(production):
    p=production
    pieces=[dict(code='P01',good=19,rejected=2,scrap=1),dict(code='P02',good=12)]
    daily=ok(send(p,mode='parts',sets=0,parts=pieces));did=doc(daily)
    assert daily['summary']['completed']==0 and daily['tasks'][0]['balance']['matchable']==9
    match=ok(send(p,mode='parts',kind='match',sets=9));mid=doc(match)
    assert match['summary']['completed']==9
    assert match['tasks'][0]['balance']['loose']=={'P01':1,'P02':3}
    assert send(p,mode='parts',kind='match',sets=1).status_code==422
    assert send(p,day='2026-10-16',sets=5).status_code==422
    assert send(p,document_id=did,mode='parts',sets=0,parts=[dict(code='P01',good=10),dict(code='P02',good=12)]).status_code==422
    ok(send(p,'void',document_id=mid))
    assert read(p)['tasks'][0]['balance']['matchable']==9
    ok(send(p,mode='parts',kind='match',sets=9))


def test_outsourced_claim_return_accept_handover_separate(production):
    p=production
    claim=ok(send(p,task_id='external',sets=20))
    assert claim['summary']['completed']==0
    assert send(p,task_id='external',kind='handover',sets=1).status_code==422
    assert send(p,task_id='external',kind='return',sets=21).status_code==422
    received=ok(send(p,task_id='external',kind='return',sets=18));rid=doc(received)
    accepted=ok(send(p,task_id='external',kind='accept',sets=15,rejected=2));aid=doc(accepted)
    assert accepted['summary']['completed']==15 and accepted['summary']['actual_delivery']==0
    assert send(p,task_id='external',kind='accept',sets=2).status_code==422
    hand=ok(send(p,task_id='external',kind='handover',sets=14))
    assert hand['summary']['actual_delivery']==14
    assert send(p,document_id=aid,task_id='external',kind='accept',sets=13,rejected=2).status_code==422
    assert send(p,'void',document_id=rid).status_code==422


def test_concurrent_same_operation_and_recovery_fence(production):
    p=production
    body=command(expected_version=read(p)['version'],document_id=uuid4().hex,entry=entry(p))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:p.post(URL+'/post',json=body),range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert len(read(p)['documents'])==1
    p.cutting_auth['user']=user('read')
    recovery=p.post(BASE+'/orders/line-1/report-operations/recover',json=dict(action='post',command=body))
    assert recovery.status_code==200 and recovery.json()['state']=='committed'
    pending=dict(body,operation_id=uuid4().hex,document_id=uuid4().hex)
    assert p.post(BASE+'/orders/line-1/report-operations/recover',json=dict(action='post',command=pending)).json()['state']=='abandoned'
    p.cutting_auth['user']=user('read','report_write')
    assert p.post(URL+'/post',json=pending).status_code==409
    assert p.post(URL+'/post',json=dict(body,reason='变更原操作内容')).status_code==409


def test_source_change_preserves_facts_and_allows_corrections(production):
    p=production;posted=ok(send(p));did=doc(posted)
    amend(p,True)
    assert send(p,day='2026-10-16').status_code==409
    ok(send(p,document_id=did,sets=8))
    receive(p)
    assert read(p)['summary']['completed']==8
    assert read(p)['summary']['remaining'] is None
    ok(send(p,'void',document_id=did))


@pytest.mark.parametrize('changes',[
    {'sets':-1},{'sets':1.5},{'sets':True},{'day':'2099-01-01'},
    {'kind':'match'},{'kind':'return'},{'mode':'parts','sets':0,'parts':[{'code':'fake','good':1}]},
    {'exception_reason':''},
])
def test_invalid_input_never_writes(production,changes):
    before=read(production)['version']
    assert send(production,**changes).status_code==422
    assert read(production)['version']==before


def test_super_target_negative_remaining_and_separate_permission(production):
    p=production
    result=ok(send(p,sets=60))
    assert result['summary']['remaining']==-10
    p.cutting_auth['user']=user('read','report_write')
    assert send(p,kind='handover',sets=1).status_code==403
    assert send(p,'review',document_id=doc(result)).status_code==403
    p.cutting_auth['user']=user('read','report_write',department='engineering')
    assert send(p,day='2026-10-16').status_code==403


def test_immutable_migration_and_missing_schema_guard(production):
    p=production;ok(send(p))
    with p.engine.begin() as conn:
        for sql in ('UPDATE cutting_ops_production_events SET reason=\'changed\'','DELETE FROM cutting_ops_production_events'):
            with pytest.raises(Exception,match='append-only'):conn.execute(text(sql))
    with p.engine.begin() as conn:conn.execute(text('DROP TABLE cutting_ops_production_events'))
    assert p.get(URL,params={'factory_id':'huakang-c'}).status_code==503


def test_missing_immutable_trigger_refuses_writes(production):
    with production.engine.begin() as conn:conn.execute(text('DROP TRIGGER cutting_production_no_delete'))
    assert production.get(URL,params={'factory_id':'huakang-c'}).status_code==503
    assert send_without_read(production).status_code==503


def send_without_read(p):
    return p.post(URL+'/post',json=command(document_id=uuid4().hex,entry=dict(task_id='task-1',plan_version=1,day='2026-10-10',mode='sets',kind='daily',sets=1,evidence='test')))


def test_no_authorization_via_scope_or_extra_fields(production):
    p=production
    assert p.get(URL,params={'factory_id':'huakang-d'}).status_code==422
    assert p.get(URL+'?factory_id=huakang-c&factory_id=huakang-d').status_code==422
    body=command(expected_version=read(p)['version'],document_id=uuid4().hex,entry=entry(p),completed=999)
    assert p.post(URL+'/post',json=body).status_code==422


def test_discard_correction_keeps_effective_production(production):
    p=production;posted=ok(send(p));did=doc(posted)
    ok(send(p,'save',document_id=did,sets=15))
    result=ok(send(p,'discard',document_id=did))
    assert result['summary']['completed']==10 and result['documents'][0]['draft'] is None
    assert result['documents'][0]['posted']['data']['entry']['sets']==10


def test_saved_handover_can_post_after_same_day_production(production):
    p=production
    draft=ok(send(p,'save',kind='handover',sets=10));did=doc(draft)
    ok(send(p))
    result=ok(send(p,document_id=did,kind='handover',sets=10))
    assert result['summary']['handed']==10


@pytest.mark.parametrize('discarded',[False,True])
def test_unposted_draft_cannot_bypass_cancelled_source(production,discarded):
    p=production;draft=ok(send(p,'save'));did=doc(draft)
    if discarded:ok(send(p,'discard',document_id=did))
    amend(p,True)
    assert send(p,document_id=did).status_code==409
    assert read(p)['summary']['completed']==0


def test_historical_balances_can_flow_after_cancellation(production):
    p=production
    ok(send(p,task_id='external',sets=20))
    ok(send(p,mode='parts',sets=0,parts=[dict(code='P01',good=20),dict(code='P02',good=10)]))
    amend(p,True);receive(p)
    ok(send(p,task_id='external',kind='return',sets=18))
    ok(send(p,task_id='external',kind='accept',sets=15))
    ok(send(p,task_id='external',kind='handover',sets=12))
    ok(send(p,mode='parts',kind='match',sets=10))
    final=ok(send(p,mode='parts',kind='handover',sets=10))
    assert final['summary']['completed']==25 and final['summary']['handed']==22
    assert send(p,day='2026-10-16',mode='parts',sets=0,parts=[dict(code='P01',good=20),dict(code='P02',good=10)]).status_code==409
