"""P2a scheduling invariants in isolated SQLite, never the business database."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from sqlalchemy.orm import Session
import pytest
from app.services.cutting_planning import first_supply
from app.services.cutting_schemas import WorkCalendar
from test_cutting_ops import client, user, command, create, state, BASE
from test_cutting_orders import flow, submitted, read, post, receive, amend, batch


def calendar(**changes):
    return dict(weekdays=[1,2,3,4,5,6], exceptions=[], basis='主管确认本厂工作日') | changes


@pytest.fixture
def planned(flow, monkeypatch):
    monkeypatch.setattr('app.services.cutting_planning.business_today', lambda: date(2026,10,31))
    row, _ = submitted(flow)
    flow.cutting_auth['user'] = user('read','master_write','bom_write','bom_publish','order_receive','requisition_submit','eta_write','requisition_reconcile','plan_write','plan_publish')
    reply=post(flow,'eta',expected_version=row['current']['version'],requisition_version=row['current']['data']['requisition']['version'],batches=[dict(batch(quantity='7'),expected_date='2026-10-12')])
    assert reply.status_code==200,reply.text
    return flow, reply.json()


def resource(flow, code='R01', execution='internal', cal=True):
    return create(flow, command(kind='resource', code=code, data=dict(name=code, execution=execution, source_reference='测试确认资源', calendar=calendar() if cal else None)))


def task(ref, **changes):
    return dict(task_id='task-1', name='合成裁剪任务', resource_id=ref['id'], resource_version=ref['version'], target_sets=50,
        materials=[dict(row=0, expected_date='2026-10-12')], readiness_basis='本批次用料数量与预计交期经主管核对',
        actual_issue_date=None, actual_issue_reference='', prerequisite_date=None, prerequisite_basis='', days=[dict(day='2026-10-15', sets=50)]) | changes


def save(flow, tasks, **changes):
    return post(flow, 'plan', expected_version=read(flow)['current']['version'], tasks=tasks, **changes)


def publish(flow, **changes):
    row=read(flow)
    return post(flow, 'plan-publish', expected_version=row['current']['version'], draft_version=row['current']['data']['planning']['draft']['version'], **changes)


def test_split_publish_partial_and_preserve_baseline(planned):
    flow, row=planned
    a,b=resource(flow),resource(flow,'R02','outsourced')
    tasks=[task(a,target_sets=30,days=[dict(day='2026-10-15',sets=20)]),task(b,task_id='task-2',target_sets=20,days=[dict(day='2026-10-15',sets=20)])]
    response=save(flow,tasks); assert response.status_code==200,response.text
    draft=response.json()['current']['data']['planning']['draft']
    assert draft['allocated_sets']==50 and draft['unallocated_sets']==0
    assert draft['tasks'][0]['completion_date'] is None and draft['tasks'][0]['unplanned_sets']==10
    assert draft['tasks'][1]['completion_date']=='2026-10-15'
    assert draft['tasks'][0]['earliest_supply_date']=='2026-10-15'
    first=publish(flow); assert first.status_code==200,first.text
    baseline=first.json()['current']['data']['planning']['baseline']
    tasks[0]['days'].append(dict(day='2026-10-16',sets=10))
    assert save(flow,tasks).status_code==200
    assert read(flow)['current']['data']['planning']['published']==baseline
    second=publish(flow).json()['current']['data']['planning']
    assert second['baseline']==baseline and second['published']['version']>baseline['version']
    assert second['published']['tasks'][0]['completion_date']=='2026-10-16'


@pytest.mark.parametrize('ready,exceptions,expected', [
    ('2026-10-12', [], '2026-10-15'),
    ('2026-10-16', [], '2026-10-20'),
    ('2026-10-17', [], '2026-10-21'),
    ('2026-10-12',[dict(day='2026-10-13',working=False,reason='节假日')],'2026-10-16'),
    ('2026-10-16',[dict(day='2026-10-18',working=True,reason='调休加班')],'2026-10-19'),
    ('2026-12-31', [], '2027-01-04'),
])
def test_three_working_days_excludes_ready_day(ready,exceptions,expected):
    assert first_supply(date.fromisoformat(ready),WorkCalendar(**calendar(exceptions=exceptions))).isoformat()==expected


def test_fallback_uses_actual_issue_date_and_never_claims_actual_stock(planned):
    flow,_=planned
    r=resource(flow,cal=False)
    t=task(r, date_basis='actual', materials=[], actual_issue_date='2026-10-16', actual_issue_reference='ISSUE-001 核对实领', days=[dict(day='2026-10-20',sets=50)])
    response=save(flow,[t]); assert response.status_code==200,response.text
    saved=response.json()['current']['data']['planning']['draft']['tasks'][0]
    assert saved['earliest_supply_date']=='2026-10-20' and saved['readiness_kind']=='actual_review'
    t['actual_issue_date']=None
    assert save(flow,[t]).status_code==422


@pytest.mark.parametrize('changes', [
    dict(target_sets=51), dict(target_sets=0), dict(target_sets=True),
    dict(days=[dict(day='2026-10-15',sets=51)]),
    dict(days=[dict(day='2026-10-15',sets=1),dict(day='2026-10-15',sets=1)]),
    dict(days=[dict(day='2026-10-14',sets=50)]), dict(days=[dict(day='2026-10-18',sets=50)]),
    dict(materials=[dict(row=1,expected_date='2026-10-12')]),
    dict(materials=[dict(row=299,expected_date='2026-10-12')]),
    dict(materials=[dict(row=0,expected_date=None)]), dict(readiness_basis=''),
    dict(prerequisite_date='2026-10-14',prerequisite_basis='贴合尚待完成'),
])
def test_invalid_allocations_dates_and_missing_required_materials_rejected(planned,changes):
    flow,_=planned
    t=task(resource(flow),**changes)
    before=read(flow)['current']['version']
    assert save(flow,[t]).status_code==422
    assert read(flow)['current']['version']==before


def test_unplanned_tasks_can_be_saved_but_not_published(planned):
    flow,_=planned
    response=save(flow,[task(resource(flow),target_sets=20,materials=[],days=[])])
    assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['draft']['unallocated_sets']==30
    assert publish(flow).status_code==422


def test_resource_changes_mark_publication_stale_and_block_old_draft(planned):
    flow,_=planned
    r=resource(flow); t=task(r)
    assert save(flow,[t]).status_code==200
    assert publish(flow).status_code==200
    assert save(flow,[t]).status_code==200
    assert state(flow,r,'inactive').status_code==200
    row=read(flow)
    assert row['planning_summary']['published_stale'] and row['planning_summary']['draft_stale']
    assert publish(flow).status_code==409


def test_eta_or_source_changes_retain_but_invalidate_plans(planned):
    flow,_=planned
    assert save(flow,[task(resource(flow))]).status_code==200
    publication=publish(flow).json()['current']['data']['planning']['published']
    row=read(flow)
    assert post(flow,'eta',expected_version=row['current']['version'],requisition_version=row['current']['data']['requisition']['version'],batches=[batch()]).status_code==200
    assert read(flow)['planning_summary']['published_stale']
    amend(flow)
    assert read(flow)['planning_summary']['published_stale']
    row=receive(flow)
    assert row['current']['data']['planning']['published']==publication
    assert row['planning_summary']['published_stale']
    assert save(flow,[task(resource(flow,'R02'))]).status_code==409


@pytest.mark.parametrize('department,actions', [('engineering',['read','plan_write']),('pmc-warehouse',['read','plan_publish']),('production',['read']),('production',['plan_write'])])
def test_separate_production_permissions(planned,department,actions):
    flow,_=planned
    t=task(resource(flow))
    flow.cutting_auth['user']=user(*actions,department=department)
    assert post(flow,'plan',expected_version=3,tasks=[t]).status_code==403


def test_concurrent_plan_commands_and_lost_response_recovery(planned):
    flow,row=planned
    t=task(resource(flow))
    body=command(expected_version=row['current']['version'],tasks=[t])
    url=BASE+'/orders/line-1/plan'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:flow.post(url,json=body),range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert responses[0].json()==responses[1].json()
    recovery=flow.post(BASE+'/orders/line-1/operations/recover',json=dict(action='plan',command=body))
    assert recovery.status_code==200 and recovery.json()['state']=='committed'
    stale_body=command(expected_version=row['current']['version'],tasks=[t])
    assert flow.post(url,json=stale_body).status_code==409
    fence=flow.post(BASE+'/orders/line-1/operations/recover',json=dict(action='plan',command=stale_body))
    assert fence.json()['state']=='abandoned'
    assert flow.post(url,json=stale_body).status_code==409


def test_calendar_revision_changes_are_detected_without_rewriting_history(planned):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r)]).status_code==200
    published=publish(flow).json()['current']['data']['planning']['published']
    body=command(kind='resource',code=r['code'],expected_version=r['version'],data=dict(r['data'],calendar=calendar(weekdays=[1,2,3,4,5])))
    updated=flow.put(BASE+'/masters/'+r['id'],json=body); assert updated.status_code==200,updated.text
    row=read(flow)
    assert row['planning_summary']['published_stale']
    assert row['current']['data']['planning']['published']==published
    t=task(updated.json(),materials=[dict(row=0,expected_date='2026-10-16')],days=[dict(day='2026-10-21',sets=50)])
    saved=save(flow,[t]); assert saved.status_code==200,saved.text
    assert saved.json()['current']['data']['planning']['draft']['tasks'][0]['earliest_supply_date']=='2026-10-21'


def test_disabled_material_marks_stale_and_blocks_new_plan(planned):
    flow,_=planned
    r=resource(flow); assert save(flow,[task(r)]).status_code==200
    assert publish(flow).status_code==200
    material=flow.get(BASE+'/masters?factory_id=huakang-c&kind=material').json()['data'][0]
    assert state(flow,material,'inactive').status_code==200
    assert read(flow)['planning_summary']['published_stale']
    assert save(flow,[task(r)]).status_code==409


def test_two_independent_saves_cannot_overwrite_same_version(planned):
    flow,row=planned
    t=task(resource(flow))
    bodies=[command(expected_version=row['current']['version'],tasks=[t]) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda b:flow.post(BASE+'/orders/line-1/plan',json=b),bodies))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_cancelled_order_keeps_plan_history_but_blocks_scheduling(planned):
    flow,_=planned
    r=resource(flow); assert save(flow,[task(r)]).status_code==200
    publication=publish(flow).json()['current']['data']['planning']['published']
    amend(flow,cancelled=True); receive(flow)
    assert read(flow)['current']['data']['planning']['published']==publication
    assert read(flow)['planning_summary']['published_stale']
    assert save(flow,[task(r)]).status_code==409


@pytest.mark.parametrize('cal', [calendar(weekdays=[]),calendar(weekdays=[1,1]),calendar(exceptions=[dict(day='2026-10-18',working=False,reason='a'),dict(day='2026-10-18',working=True,reason='b')])])
def test_invalid_calendar_does_not_create_resource(planned,cal):
    flow,_=planned
    response=flow.post(BASE+'/masters',json=command(kind='resource',code='BAD',data=dict(name='bad',execution='internal',source_reference='test',calendar=cal)))
    assert response.status_code==422


@pytest.mark.parametrize('configured',[True,False])
def test_later_accessories_do_not_delay_current_cutting_stage(planned,configured):
    flow,_=planned
    t=task(resource(flow,cal=configured),materials=[dict(row=0,expected_date='2026-10-12'),dict(row=1,expected_date='2026-11-01')],actual_issue_date='2026-10-12', actual_issue_reference='ISSUE-002 核对实领')
    response=save(flow,[t]); assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['draft']['tasks'][0]['earliest_supply_date']=='2026-10-15'


@pytest.mark.parametrize('changes', [dict(actual_issue_date='2026-11-01',actual_issue_reference='未来日期不是真实领料'), dict(actual_issue_date='2026-10-12',actual_issue_reference=''), dict(actual_issue_date=None,actual_issue_reference='缺实领日期')])
def test_actual_issue_requires_past_or_today_date_and_reference(planned,changes):
    flow,_=planned
    response=save(flow,[task(resource(flow,cal=False),materials=[],days=[],**changes)])
    assert response.status_code==422,response.text


def test_estimated_issue_input_is_never_accepted_as_actual(planned):
    flow,_=planned
    t=task(resource(flow,cal=False),days=[])
    t.pop('actual_issue_date'); t.pop('actual_issue_reference')
    t['expected_issue_date']='2026-10-12'
    assert save(flow,[t]).status_code==422


def test_legacy_plan_requires_review_and_retains_estimated_evidence(planned):
    from app.models.cutting_ops import CuttingOrderRevision
    flow,_=planned
    r=resource(flow,cal=False)
    t=task(r,actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-001')
    assert save(flow,[t]).status_code==200
    row=read(flow)
    with Session(flow.engine) as db:
        revision=db.get(CuttingOrderRevision,('line-1',row['current']['version']))
        data=deepcopy(revision.data)
        draft=data['planning']['draft']; draft['basis'].pop('issue_date_rule')
        old=draft['tasks'][0]; old['expected_issue_date']=old.pop('actual_issue_date'); old.pop('actual_issue_reference')
        revision.data=data; db.commit()
    row=read(flow)
    assert row['planning_summary']['draft_stale']
    assert row['current']['data']['planning']['draft']['tasks'][0]['expected_issue_date']=='2026-10-12'
    assert publish(flow).status_code==409


def test_old_publish_receipt_replay_returns_current_stale_status(planned):
    from app.models.cutting_ops import CuttingOrderRevision, CuttingCommand
    flow,_=planned
    r=resource(flow,cal=False)
    assert save(flow,[task(r,actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-001')]).status_code==200
    row=read(flow)
    body=command(expected_version=row['current']['version'],draft_version=row['current']['data']['planning']['draft']['version'])
    url=BASE+'/orders/line-1/plan-publish'
    published=flow.post(url,json=body); assert published.status_code==200
    with Session(flow.engine) as db:
        revision=db.get(CuttingOrderRevision,('line-1',published.json()['current']['version']))
        data=deepcopy(revision.data)
        for key in ('published','baseline'):
            data['planning'][key]['basis'].pop('issue_date_rule')
            t=data['planning'][key]['tasks'][0]; t['expected_issue_date']=t.pop('actual_issue_date'); t.pop('actual_issue_reference')
        revision.data=data
        receipt=db.get(CuttingCommand,body['operation_id'])
        old_result=deepcopy(receipt.result); old_result['current']['data']=deepcopy(data)
        old_result['planning_summary']['published_stale']=False
        receipt.result=old_result; db.commit()
    replay=flow.post(url,json=body); assert replay.status_code==200,replay.text
    assert replay.json()['planning_summary']['published_stale'] is True
    with Session(flow.engine) as db:
        assert db.get(CuttingCommand,body['operation_id']).result==old_result


@pytest.mark.parametrize('configured',[False,True])
def test_advance_plan_can_publish_before_actual_issue(planned,configured):
    flow,_=planned
    r=resource(flow,cal=configured)
    response=save(flow,[task(r)])
    assert response.status_code==200,response.text
    t=response.json()['current']['data']['planning']['draft']['tasks'][0]
    assert t['actual_issue_date'] is None and t['estimated_supply_date']=='2026-10-15'
    assert t['actual_supply_date'] is None and t['actual_review_pending']
    publication=publish(flow); assert publication.status_code==200,publication.text


def test_actual_issue_delayed_requires_adjustment_and_preserves_original_baseline(planned):
    flow,_=planned
    r=resource(flow,cal=False)
    assert save(flow,[task(r)]).status_code==200
    original=publish(flow).json()['current']['data']['planning']['published']
    t=task(r,date_basis='actual',actual_issue_date='2026-10-16',actual_issue_reference='领料单ISSUE-016')
    assert save(flow,[t]).status_code==422  # Old 15th cannot remain after delayed actual readiness.
    assert read(flow)['current']['data']['planning']['published']==original
    t['days']=[dict(day='2026-10-20',sets=50)]
    response=save(flow,[t]); assert response.status_code==200,response.text
    actual=response.json()['current']['data']['planning']['draft']['tasks'][0]
    assert actual['estimated_supply_date']=='2026-10-15' and actual['actual_supply_date']=='2026-10-20'
    assert actual['earliest_supply_date']=='2026-10-20' and not actual['actual_review_pending']
    pub=publish(flow); assert pub.status_code==200,pub.text
    assert pub.json()['current']['data']['planning']['baseline']==original


def test_actual_review_does_not_use_estimated_material_or_prerequisite_dates(planned):
    flow,_=planned
    r=resource(flow)
    t=task(r,date_basis='actual',materials=[dict(row=0,expected_date='2026-10-26')],actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-012',
           prerequisite_date='2026-10-25',prerequisite_basis='旧预计贴合',actual_prerequisite_date='2026-10-14',actual_prerequisite_reference='贴合完成单-014',days=[dict(day='2026-10-17',sets=50)])
    response=save(flow,[t]); assert response.status_code==200,response.text
    record=response.json()['current']['data']['planning']['draft']['tasks'][0]
    assert record['actual_supply_date']=='2026-10-17' and record['estimated_supply_date']=='2026-10-29'
    t['actual_prerequisite_date']=None;t['actual_prerequisite_reference']=''
    assert save(flow,[t]).status_code==422


@pytest.mark.parametrize('action',[dict(actual_issue_date=None,actual_issue_reference=''),dict(actual_prerequisite_date='2026-11-01',actual_prerequisite_reference='未来非实际')])
def test_actual_review_missing_or_future_facts_cannot_be_replaced_by_estimates(planned,action):
    flow,_=planned
    t=task(resource(flow),date_basis='actual',actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-012')
    t.update(action)
    assert save(flow,[t]).status_code==422


def test_advance_plans_require_procurement_reply_for_current_required_purchase_material(planned):
    flow,_=planned
    row=read(flow)
    assert post(flow,'eta',expected_version=row['current']['version'],requisition_version=row['current']['data']['requisition']['version'],batches=[]).status_code==200
    assert save(flow,[task(resource(flow))]).status_code==422


def test_advance_plan_date_cannot_precede_procurement_first_reply(planned):
    flow,_=planned
    t=task(resource(flow),materials=[dict(row=0,expected_date='2026-10-10')])
    assert save(flow,[t]).status_code==422



def test_clearing_stale_prerequisite_date_cannot_remove_requirement(planned):
    flow,_=planned
    r=resource(flow)
    t=task(r,prerequisite_date='2026-10-12',prerequisite_basis='贴合待完成')
    assert save(flow,[t]).status_code==200
    assert publish(flow).status_code==200
    t.update(date_basis='actual',prerequisite_date=None,prerequisite_basis='',actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-012')
    assert save(flow,[t]).status_code==422  # Clearing the expected date cannot cancel the saved requirement.
    t.update(prerequisite_required=True)
    assert save(flow,[t]).status_code==422  # Actual prerequisite evidence still missing.
    t.update(actual_prerequisite_date='2026-10-12',actual_prerequisite_reference='贴合完成012')
    assert save(flow,[t]).status_code==200
    t.update(prerequisite_required=False,actual_prerequisite_date=None,actual_prerequisite_reference='',prerequisite_change_reason='工程核实本批不需要贴合')
    assert save(flow,[t]).status_code==200


def test_actual_draft_without_facts_remains_pending_review(planned):
    flow,_=planned
    response=save(flow,[task(resource(flow),date_basis='actual',materials=[],days=[])])
    assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['draft']['tasks'][0]['actual_review_pending']



def test_no_purchase_required_material_can_preplan_with_manual_estimate(planned):
    flow,_=planned
    row=read(flow); old=row['current']['data']['requisition']['version']
    assert post(flow,'withdraw',expected_version=row['current']['version'],requisition_version=old).status_code==200
    row=read(flow)
    response=post(flow,'reconcile',expected_version=row['current']['version'],requisition_version=old,disposition='cancelled_or_reallocated',evidence='原需求已全部核对转用',all_handled=True)
    assert response.status_code==200,response.text
    row=read(flow)
    response=post(flow,'requisition',expected_version=row['current']['version'],lines=[dict(row=0,quantity='0',purchase_mode='no_purchase',no_purchase_reason='已有材料无需本次采购'),dict(row=1,quantity='8')])
    assert response.status_code==200,response.text
    assert save(flow,[task(resource(flow,cal=False))]).status_code==200
    assert publish(flow).status_code==200


@pytest.mark.parametrize('ready,days,exceptions,expected', [
    ('2026-10-12', 0, [], '2026-10-12'),
    ('2026-10-18', 0, [], '2026-10-19'),
    ('2026-10-12', 1, [], '2026-10-13'),
    ('2026-10-16', 2, [], '2026-10-19'),
    ('2026-10-16', 5, [], '2026-10-22'),
    ('2026-10-12', 1, [dict(day='2026-10-13', working=False, reason='休息')], '2026-10-14'),
    ('2026-10-18', 0, [dict(day='2026-10-18', working=True, reason='加班')], '2026-10-18'),
])
def test_adjustable_working_day_interval(ready, days, exceptions, expected):
    assert first_supply(date.fromisoformat(ready), WorkCalendar(**calendar(exceptions=exceptions)), days).isoformat()==expected


@pytest.mark.parametrize('mode', ['estimated', 'actual'])
@pytest.mark.parametrize('days,supply', [(0,'2026-10-12'),(1,'2026-10-13'),(5,'2026-10-17')])
def test_adjusted_preparation_can_publish_in_both_modes(planned, mode, days, supply):
    flow,_=planned
    t=task(resource(flow,cal=False), date_basis=mode, preparation_workdays=days,
           actual_issue_date='2026-10-12' if mode=='actual' else None, actual_issue_reference='ISSUE-012' if mode=='actual' else '',
           days=[dict(day=supply,sets=50)])
    response=save(flow,[t]); assert response.status_code==200,response.text
    record=response.json()['current']['data']['planning']['draft']['tasks'][0]
    assert record['preparation_workdays']==days and record['earliest_supply_date']==supply
    assert publish(flow).status_code==200


@pytest.mark.parametrize('changes', [
    dict(preparation_workdays=-1), dict(preparation_workdays=366), dict(preparation_workdays=True),
    dict(preparation_workdays=1.5), dict(preparation_workdays='1'),
    dict(preparation_workdays=5),
])
def test_invalid_interval_or_unadjusted_early_daily_plan_is_rejected(planned, changes):
    flow,_=planned
    before=read(flow)['current']['version']
    assert save(flow,[task(resource(flow),**changes)]).status_code==422
    assert read(flow)['current']['version']==before


def test_preparation_revision_requires_reason_after_publication_and_retains_first_baseline(planned):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r)],reason='').status_code==200
    original=publish(flow,reason='').json()['current']['data']['planning']['baseline']
    shorter=task(r,preparation_workdays=1,days=[dict(day='2026-10-13',sets=50)])
    assert save(flow,[shorter],reason='').status_code==422
    assert save(flow,[shorter],reason='已备料缩短准备周期').status_code==200
    second=publish(flow,reason='').json()['current']['data']['planning']
    assert second['baseline']==original and second['published']['tasks'][0]['preparation_workdays']==1
    assert second['published']['adjustment_reason']=='已备料缩短准备周期'
    assert second['published']['reason']=='已备料缩短准备周期'
    assert save(flow,[task(r)],reason='').status_code==422
    assert save(flow,[task(r)],reason='恢复常规准备周期').status_code==200
    assert publish(flow,reason='').json()['current']['data']['planning']['baseline']==original


@pytest.mark.parametrize('reason', [None, '', '   '])
def test_saved_publication_cannot_be_adjusted_without_entered_reason(planned, reason):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r)],reason='').status_code==200
    assert publish(flow,reason='').status_code==200
    before=read(flow)
    body=command(expected_version=before['current']['version'],tasks=[task(r,days=[dict(day='2026-10-16',sets=50)])])
    if reason is None: body.pop('reason')
    else: body['reason']=reason
    rejected=flow.post(BASE+'/orders/line-1/plan',json=body)
    assert rejected.status_code==422 and '调整原因' in rejected.text
    assert read(flow)['current']==before['current']


def test_legacy_adjustment_draft_requires_reason_at_publication(planned):
    from app.models.cutting_ops import CuttingOrderRevision
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r)]).status_code==200
    assert publish(flow).status_code==200
    assert save(flow,[task(r)],reason='原调整内容').status_code==200
    row=read(flow)
    with Session(flow.engine) as db:
        revision=db.get(CuttingOrderRevision,('line-1',row['current']['version']))
        data=deepcopy(revision.data);data['planning']['draft'].pop('adjustment_reason')
        revision.data=data;db.commit()
    assert publish(flow,reason='').status_code==422
    published=publish(flow,reason='核对历史草稿调整原因')
    assert published.status_code==200,published.text
    assert published.json()['current']['data']['planning']['published']['adjustment_reason']=='核对历史草稿调整原因'


def test_blank_command_revalidation_does_not_invent_a_user_reason():
    from app.services.cutting_planning_schemas import PublishPlan
    body=PublishPlan.model_validate(command(draft_version=1,reason=''))
    assert not body._reason_entered
    assert not PublishPlan.model_validate(body)._reason_entered


def test_successful_blank_initial_plan_replay_and_recovery_remain_valid_after_publication(planned):
    flow,_=planned
    body=command(expected_version=read(flow)['current']['version'],tasks=[task(resource(flow))],reason='')
    saved=flow.post(BASE+'/orders/line-1/plan',json=body);assert saved.status_code==200
    original=publish(flow,reason='').json()['current']['data']['planning']['published']
    replay=flow.post(BASE+'/orders/line-1/plan',json=body);assert replay.status_code==200,replay.text
    assert replay.json()['current']['data']['planning']['published']==original
    recovered=flow.post(BASE+'/orders/line-1/operations/recover',json=dict(action='plan',command=body))
    assert recovered.status_code==200 and recovered.json()['state']=='committed'


def test_long_preparation_with_one_weekly_workday_is_supported():
    ready=date(2026,10,12)
    assert first_supply(ready,WorkCalendar(**calendar(weekdays=[1])),365)==ready+timedelta(weeks=365)


def test_blank_plan_reason_is_normalized_and_recovery_matches_original_payload(planned):
    flow,_=planned
    body=command(expected_version=read(flow)['current']['version'],tasks=[task(resource(flow),preparation_workdays=0,days=[dict(day='2026-10-12',sets=50)])],reason='')
    response=flow.post(BASE+'/orders/line-1/plan',json=body);assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['draft']['reason']=='保存生产计划'
    recovered=flow.post(BASE+'/orders/line-1/operations/recover',json=dict(action='plan',command=body))
    assert recovered.status_code==200,recovered.text
    row=read(flow)
    publish_body=command(expected_version=row['current']['version'],draft_version=row['current']['data']['planning']['draft']['version'],reason='  ')
    published=flow.post(BASE+'/orders/line-1/plan-publish',json=publish_body);assert published.status_code==200,published.text
    assert published.json()['current']['data']['planning']['published']['reason']=='发布生产计划'
    recovered=flow.post(BASE+'/orders/line-1/operations/recover',json=dict(action='plan-publish',command=publish_body))
    assert recovered.status_code==200,recovered.text


def test_replacing_executor_keeps_task_identity_and_prerequisites(planned):
    flow,_=planned
    a,b=resource(flow),resource(flow,'OUT','outsourced')
    t=task(a,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='必须贴合后裁剪')
    assert save(flow,[t]).status_code==200
    baseline=publish(flow).json()['current']['data']['planning']['baseline']
    new=task(b,prerequisite_required=True,date_basis='actual',actual_issue_date='2026-10-12',actual_issue_reference='OUT-012')
    assert save(flow,[new]).status_code==422  # Same identity cannot drop actual prerequisite readiness.
    new.update(actual_prerequisite_date='2026-10-12',actual_prerequisite_reference='贴合完成012')
    assert save(flow,[new]).status_code==422  # Changed executor requires explicit actual-evidence review.
    new['resource_change_basis']='核对外发厂领料及贴合移交凭据'
    response=save(flow,[new]);assert response.status_code==200,response.text
    result=publish(flow).json()['current']['data']['planning']
    assert result['baseline']==baseline and result['published']['tasks'][0]['task_id']==t['task_id']


def test_new_task_id_cannot_silently_drop_saved_prerequisite_requirement(planned):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='必须贴合')]).status_code==200
    t=task(r,task_id='replacement',date_basis='actual',actual_issue_date='2026-10-12',actual_issue_reference='ISSUE-012')
    assert save(flow,[t]).status_code==422
    response=save(flow,[t],removed_task_reasons={'task-1':'工程确认原任务取消前置要求'})
    assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['draft']['removed_task_reasons']['task-1']=='工程确认原任务取消前置要求'
    assert publish(flow).status_code==200


def test_removal_evidence_is_preserved_through_multiple_draft_saves(planned):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='原批需贴合')]).status_code==200
    t=task(r,task_id='new')
    assert save(flow,[t],removed_task_reasons={'unknown':'不能伪造取消依据'}).status_code==422
    assert save(flow,[t],removed_task_reasons={'task-1':'取消原批重新核对工序'}).status_code==200
    assert save(flow,[t]).status_code==200
    response=publish(flow);assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['published']['removed_task_reasons']=={'task-1':'取消原批重新核对工序'}


def test_resource_default_preparation_and_multi_field_master_search(planned):
    flow,_=planned
    body=command(kind='resource',code='PREP',data=dict(name='本厂准备组',execution='internal',source_reference='主管默认',preparation_workdays=1))
    r=create(flow,body);assert r['data']['preparation_workdays']==1
    assert flow.get(BASE+'/masters',params=dict(factory_id='huakang-c',kind='resource',q='本厂准备')).json()['total']==1
    bom=read(flow)['current']['data']['bom']
    for term in ('00012','款式A','测试套装','蓝'):
        response=flow.get(BASE+'/masters',params=dict(factory_id='huakang-c',kind='bom',q=term))
        assert response.status_code==200 and bom['id'] in [row['id'] for row in response.json()['data']]
    assert flow.get(BASE+'/masters',params=dict(factory_id='huakang-c',kind='bom',q='%')).json()['total']==0
    body['operation_id']='invalid-default';body['data']['preparation_workdays']=True
    assert flow.post(BASE+'/masters',json=body).status_code==422


def test_plan_status_filters_use_current_resource_state_and_preserve_partial_baseline(planned):
    flow,_=planned
    params=dict(factory_id='huakang-c',plan_status='unplanned')
    assert flow.get(BASE+'/orders',params=params).json()['total']==1
    r=resource(flow)
    assert save(flow,[task(r,days=[dict(day='2026-10-15',sets=20)])]).status_code==200
    params['plan_status']='partial';assert flow.get(BASE+'/orders',params=params).json()['total']==1
    assert publish(flow).status_code==200
    for status in ('published','pending_actual'):
        params['plan_status']=status;assert flow.get(BASE+'/orders',params=params).json()['total']==1
    assert state(flow,r,'inactive').status_code==200
    params['plan_status']='review';assert flow.get(BASE+'/orders',params=params).json()['total']==1
    params['plan_status']='published';assert flow.get(BASE+'/orders',params=params).json()['total']==0
    params['plan_status']='bad';assert flow.get(BASE+'/orders',params=params).status_code==422


def test_empty_removal_extension_keeps_original_plan_receipt_fingerprint():
    from app.services.cutting_planning_schemas import SavePlan
    from app.services.cutting_ops import command_fingerprint, payload_fingerprint
    body=SavePlan.model_validate(command(tasks=[task(dict(id='r',version=1))]))
    old=body.model_dump(mode='json');old.pop('removed_task_reasons')
    for t in old['tasks']: t.pop('resource_change_basis')
    assert command_fingerprint(body,'plan_write:line-1')==payload_fingerprint(old,'plan_write:line-1')


def test_legacy_draft_removed_required_published_task_cannot_publish_without_cancellation_basis(planned):
    from app.models.cutting_ops import CuttingOrderRevision
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='必须贴合')]).status_code==200
    original=publish(flow).json()['current']['data']['planning']['published']
    assert save(flow,[task(r,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='必须贴合')]).status_code==200
    row=read(flow)
    with Session(flow.engine) as db:
        revision=db.get(CuttingOrderRevision,('line-1',row['current']['version']))
        data=deepcopy(revision.data)
        data['planning']['draft']['tasks'][0].update(task_id='new-id',prerequisite_required=False,prerequisite_date=None,prerequisite_basis='')
        data['planning']['draft'].pop('removed_task_reasons',None)
        revision.data=data;db.commit()
    assert publish(flow).status_code==422
    t=task(r,task_id='new-id')
    assert save(flow,[t]).status_code==422
    assert save(flow,[t],removed_task_reasons={'task-1':'工程确认取消原批前置任务'}).status_code==200
    result=publish(flow);assert result.status_code==200,result.text
    assert result.json()['current']['data']['planning']['baseline']==original


def test_executor_change_cannot_reuse_actual_evidence_without_review_basis(planned):
    flow,_=planned
    a,b=resource(flow),resource(flow,'OUT','outsourced')
    assert save(flow,[task(a,date_basis='actual',actual_issue_date='2026-10-12',actual_issue_reference='原厂领料')]).status_code==200
    assert publish(flow).status_code==200
    new=task(b,date_basis='actual',actual_issue_date='2026-10-12',actual_issue_reference='原厂领料')
    assert save(flow,[new]).status_code==422
    new['resource_change_basis']='核对实际领料已随任务移交外发'
    assert save(flow,[new]).status_code==200


def test_cancelling_prerequisite_then_removing_task_preserves_cancel_basis_at_publish(planned):
    flow,_=planned
    r=resource(flow)
    assert save(flow,[task(r,prerequisite_required=True,prerequisite_date='2026-10-12',prerequisite_basis='必须贴合')]).status_code==200
    assert publish(flow).status_code==200
    assert save(flow,[task(r,prerequisite_required=False,prerequisite_change_reason='原批工序已取消核对')]).status_code==200
    assert save(flow,[task(r,task_id='new-id')]).status_code==200
    response=publish(flow);assert response.status_code==200,response.text
    assert response.json()['current']['data']['planning']['published']['removed_task_reasons']['task-1']=='原批工序已取消核对'
