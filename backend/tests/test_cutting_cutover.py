"""Cutover preview uses isolated evidence; never populates business opening rows."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import text
from test_cutting_periods import (month_client, accounting, custody, bridge, client, flow, planned, actor,
                                 lock, act, write, get as period_get)
from test_cutting_payments import (paid_setup, fees, production, user, ok, save, decision, reviewer)
from test_cutting_ops import BASE
from app.services import warehouse_operations as wh
import pytest


def preview(p, scope='internal', month='2026-11', status=200, **kwargs):
    response=p.post(BASE+'/cutover/preview',json=dict(factory_id='huakang-c',scope=scope,month=month,**kwargs))
    assert response.status_code==status,response.text
    if status==200: assert response.headers['cache-control']=='no-store'
    return response.json()


def find(result, prefix):
    return next(r for r in result['rows'] if r['key'].startswith(prefix+':'))


def test_internal_unknown_wip_exact_comparison_and_no_write(month_client):
    p=month_client
    with p.engine.connect() as db:
        before=db.execute(text('select count(*) from cutting_ops_period_events')).scalar()
    value=preview(p)
    assert value['cutoff']=='2026-10-31' and not value['can_post']
    assert find(value,'wip')['value'] is None
    material=find(value,'custody')
    comparison=dict(key=material['key'],value=material['value'],unit=material['unit'],evidence='盘点表行1')
    checked=preview(p,token=value['token'],comparisons=[comparison])
    assert find(checked,'custody')['status']=='一致'
    changed=preview(p,token=value['token'],comparisons=[comparison|dict(value='0')])
    assert find(changed,'custody')['declared']=='0'
    assert find(changed,'wip')['status']=='待确认系统值'
    assert preview(p,token=value['token'],external=[dict(description='旧外发余料未建档',evidence='旧盘点表')])['external']
    with p.engine.connect() as db:
        assert db.execute(text('select count(*) from cutting_ops_period_events')).scalar()==before
    preview(p,comparisons=[comparison],status=422)
    preview(p,token=value['token'],comparisons=[comparison,comparison],status=422)
    preview(p,token=value['token'],comparisons=[comparison|dict(unit='千克')],status=422)
    preview(p,token=value['token'],comparisons=[comparison|dict(key='foreign-id')],status=422)


def test_locked_wip_is_exact_and_reopen_invalidates_preview(month_client):
    p=month_client;event=lock(p)
    value=preview(p)
    assert find(value,'wip')['value']=='0.8'
    assert find(value,'wip_cost')['value']=='2.50'
    assert event['id'] in find(value,'wip')['sources']
    act(p,'reopen')
    preview(p,token=value['token'],status=409)
    fresh=preview(p)
    assert find(fresh,'wip')['value'] is None
    # Still available as immutable history, not silently selected as current opening.
    assert period_get(p,event_id=event['id'])['data']['snapshot']['costs']['HKD']['ending_wip']=='2.50'


def test_dates_permissions_and_scope(month_client):
    p=month_client
    preview(p,month='2099-01',status=422)
    preview(p,month='2000-01',status=422)
    preview(p,month='2026-10')
    original=p.cutting_auth['user']
    p.cutting_auth['user']=actor('read')
    preview(p,status=403)
    p.cutting_auth['user']=user('read','cost_read',factory='huaxing')
    preview(p,status=403)
    p.cutting_auth['user']=original
    assert p.post(BASE+'/cutover/preview',json=dict(factory_id='huaxing',month='2026-11',scope='internal')).status_code==422


@pytest.mark.parametrize('month_client', [False], indirect=True)
def test_missing_price_is_unknown_but_explicit_zero_cost_is_known(month_client):
    p=month_client
    value=preview(p)
    assert find(value,'custody_cost')['value'] is None
    write(p,'price',issue_id=p.issue_id,unit_cost='0',currency='HKD',price_reference='明确免费批次凭据')
    preview(p,token=value['token'],status=409)
    zero=preview(p)
    assert find(zero,'custody_cost')['value']=='0.00'
    assert find(zero,'custody_cost')['unit']=='HKD'
    assert find(zero,'wip_cost')['value'] is None


def test_invalid_comparisons_do_not_become_zero(month_client):
    p=month_client;value=preview(p);material=find(value,'custody')
    row=dict(key=material['key'],value='1',unit=material['unit'],evidence='盘点依据')
    for patch in ({'value':''},{'value':'NaN'},{'value':'-1'},{'value':'0.0000001'},{'evidence':'   '}):
        preview(p,token=value['token'],comparisons=[row|patch],status=422)


def test_prior_cutoff_does_not_include_later_receipts(month_client):
    value=preview(month_client,month='2026-10')
    assert not [r for r in value['rows'] if r['category']=='现场余料']


def test_finance_respects_cutoff_and_does_not_treat_pending_as_paid(paid_setup,monkeypatch):
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    old=preview(p,'finance')
    assert sum(float(r['value']) for r in old['rows'] if r['category']=='切入前未付')==40
    did=save(p);ok(decision(p,did,'submit'))
    pending=preview(p,'finance')
    assert sum(float(r['value']) for r in pending['rows'] if r['category']=='切入前未付')==40
    assert any('尚未确认' in n['message'] for n in pending['notices'])
    reviewer(p);ok(decision(p,did,'confirm'))
    preview(p,'finance',token=old['token'],status=409)
    now=preview(p,'finance')
    assert sum(float(r['value']) for r in now['rows'] if r['category']=='切入前未付')==35
    assert not [r for r in preview(p,'finance',month='2026-10')['rows'] if r['category']=='切入前未付']
    p.cutting_auth['user']=user('read','settlement_read',department='accounting')
    preview(p,'finance',status=403)


def test_later_payment_does_not_reduce_opening_and_reversal_recalculates(paid_setup,monkeypatch):
    from datetime import date
    from app.services import cutting_planning as planning
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(planning,'business_today',lambda:date(2026,12,15))
    did=save(p,day='2026-11-01');ok(decision(p,did,'submit'));reviewer(p);ok(decision(p,did,'confirm'))
    before=preview(p,'finance')
    assert sum(Decimal(r['value']) for r in before['rows'] if r['category']=='切入前未付')==Decimal('40')
    assert any('切入后已付 5.00' in r['note'] for r in before['rows'])
    after=preview(p,'finance',month='2026-12')
    assert sum(Decimal(r['value']) for r in after['rows'] if r['category']=='切入前未付')==Decimal('35')
    ok(decision(p,did,'reverse'))
    preview(p,'finance',month='2026-12',token=after['token'],status=409)
    revised=preview(p,'finance',month='2026-12')
    assert sum(Decimal(r['value']) for r in revised['rows'] if r['category']=='切入前未付')==Decimal('40')


def test_unrelated_future_draft_does_not_invalidate_opening(paid_setup, monkeypatch):
    from datetime import date
    from app.services import cutting_planning as planning
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(planning,'business_today',lambda:date(2026,12,15))
    before=preview(p,'finance')
    save(p,day='2026-12-01')
    after=preview(p,'finance',token=before['token'])
    assert before['rows']==after['rows'] and before['history']==after['history']
    assert before['token']==after['token']


def test_payment_reversal_retains_original_and_current_trace(paid_setup, monkeypatch):
    from test_cutting_payments import read
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    did=save(p);ok(decision(p,did,'submit'));reviewer(p);ok(decision(p,did,'confirm'))
    confirmed=read(p,did)['event_id'];before=preview(p,'finance')
    ok(decision(p,did,'reverse'));reversed_id=read(p,did)['event_id']
    preview(p,'finance',token=before['token'],status=409)
    after=preview(p,'finance')
    chain=next(t for t in after['history'] if t['document_id']==did)
    assert not chain['effective'] and chain['state']=='冲销登记'
    assert {confirmed,reversed_id}<={e['id'] for e in chain['history']}
    assert chain['history'][-1]['target']['event_id']==reversed_id
    assert all(e['actor_id'] and e['date'] and e['reason'] for e in chain['history'])
    assert sum(Decimal(r['value']) for r in after['rows'] if r['category']=='切入前未付')==40


def test_finance_batches_cover_every_row_and_history_once(paid_setup, monkeypatch):
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    full=preview(p,'finance')
    first=preview(p,'finance',batch_size=1)
    keys=[]
    for number in range(1,first['batch']['pages']+1):
        part=preview(p,'finance',batch_size=1,batch=number)
        keys.extend('row:'+r['key'] for r in part['rows'])
        keys.extend('trace:'+r['key'] for r in part['history'])
    assert len(keys)==len(set(keys))==first['batch']['total']
    assert set(keys)=={'row:'+r['key'] for r in full['rows']}|{'trace:'+t['key'] for t in full['history']}
    preview(p,'finance',batch_size=1,batch=first['batch']['pages']+1,status=422)
    preview(p,'finance',batch_size=201,status=422)


def test_internal_scope_excludes_later_orders_and_targets_original_issue(month_client):
    p=month_client
    before=preview(p,month='2026-10')
    assert before['batch']['total']==0
    value=preview(p,batch_size=1)
    target=find(value,'custody')['target']
    assert target['id']==p.issue_id and target['workspace']=='materials' and target['month']=='2026-10'
    filtered=preview(p,query='does-not-match-any-order')
    assert filtered['rows']==[] and filtered['batch']['total']==0


def test_current_allocation_does_not_invalidate_historical_opening(month_client):
    from test_cutting_cost_allocation import allocate
    p=month_client
    before=preview(p)
    old_user=p.cutting_auth['user']
    p.cutting_auth['user']=actor('allocation_confirm','cost_read')
    allocate(p)
    p.cutting_auth['user']=old_user
    after=preview(p,token=before['token'])
    assert after['token']==before['token']
    assert find(after,'wip')['value'] is None


def test_reopened_settlement_remains_traceable(paid_setup,monkeypatch):
    from test_cutting_settlement import decision as fee_decision
    p=paid_setup
    monkeypatch.setattr(wh,'business_now',lambda:datetime(2026,12,15,tzinfo=ZoneInfo('Asia/Shanghai')))
    before=preview(p,'finance')
    ok(fee_decision(p,p.two,'reopen'))
    preview(p,'finance',token=before['token'],status=409)
    after=preview(p,'finance')
    assert sum(Decimal(r['value']) for r in after['rows'] if r['category']=='切入前未付')==20
    trace=next(t for t in after['history'] if t['document_id']==p.two)
    assert trace['state']=='反结' and not trace['effective']
    assert trace['history'][-1]['action']=='反结'
    assert any(e['action']=='确认' for e in trace['history'])


def test_batch_selection_covers_more_than_two_hundred_candidates():
    from app.services.cutting_cutover import Selection, batch_items
    candidates=[f'order-{i:04d}' for i in range(401)]
    covered=[]
    for number in range(1,10):
        selected,meta=batch_items(candidates,Selection(factory_id='huakang-c',month='2026-11',scope='internal',batch=number), '订单')
        covered.extend(selected)
        assert len(selected)<=50 and meta['total']==401 and meta['pages']==9
    assert covered==candidates
