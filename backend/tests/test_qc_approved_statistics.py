"""Statistics against real isolated workflow confirmations, not mocked approval rows."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
import pytest
from app.services import qc_workflow as wf, qc_inspection_sheet as sheet, qc_inspection_summary as summary
from app.services import qc_approved_statistics as stats, qc_daily_report as daily
from test_customer_order_ledger import engine, db
from test_qc_workflow import ACTOR


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(wf.settings, 'qc_department_data_dir', str(tmp_path / 'companies'))


def approval(db, n, result='PASS', factory='huaxing', customer='合成客户', code='', actual='', planned='2026-11-03', flag=None):
    row = wf.create_schedule(factory, {'requestKey':uuid4().hex, 'row':dict(dateFrom=planned,
        dateTo='', customer=customer, poNo='SYNTHETIC-PO', country='UK', productNo='ITEM-'+str(n),
        productName='合成验收产品', quantity='100', unitsPerCarton='10', cartonCount='10',
        production='合成生产部', agency='行验', customerPo='SYNTHETIC-CP', remark='合成验收数据')}, ACTOR)
    wf.create_tasks(db, factory, {'requestKey':uuid4().hex, 'items':[dict(sourceId=row['id'], sourceRevision=1,
        method='internal', batch='首验', plannedDate=planned, plannedQuantity='100')]}, ACTOR)
    entries = sheet.sync(factory, sheet.candidates(factory, [], wf.list_tasks(db,factory)['items'], wf.sources(db,factory)['items']))['items']
    entry = next(x for x in entries if x['sourceId']==row['id'])
    # Synthetic source-identity/flag fixtures; never touches any real stored source.
    with sheet.store(True) as conn:
        base = json.loads(sheet.get(conn,factory,entry['id'])['base'])
        base['sourceRecord']['customerCode'] = code
        if flag: base[flag] = True
        conn.execute('UPDATE entries SET base=? WHERE id=?',(wf.dump(base),entry['id']))
    entry = sheet.save(factory,entry['id'],dict(revision=entry['revision'],result=result,remark='合成备注',inspectionExecution={'actualDate':actual}),ACTOR)
    entry = sheet.submit(factory,entry['id'],dict(revision=entry['revision']),ACTOR)
    return transition(entry, factory=factory)


def transition(entry, action='confirm', factory='huaxing'):
    response = sheet.review_batch(factory, action, dict(entries=[dict(id=entry['id'],revision=entry['revision'])],requestKey=uuid4().hex),ACTOR)
    assert response['succeeded']==1, response
    return response['results'][0]['item']


def hashes():
    return {str(p):sha256(p.read_bytes()).hexdigest() for p in Path(wf.settings.qc_department_data_dir).rglob('*') if p.is_file()}


@pytest.mark.parametrize('results,expected', [(['PASS']*2,100),(['FAIL']*2,0),(['PASS','FAIL'],50),
    (['PASS','PENDING'],100),(['PASS','LG'],100),(['PENDING','LG'],None)])
def test_confirmed_formula_matches_summary_without_writing(db,monkeypatch,results,expected):
    for n,result in enumerate(results): approval(db,n,result)
    assert summary.listing('huaxing',{})['total']==len(results)
    before=hashes()
    def forbidden(*a,**k): raise AssertionError('read tried to use a write-capable store or resolver')
    for module,name in [(summary,'store'),(summary,'reconcile'),(summary,'resolve_inspection_date'),(sheet,'store')]:
        monkeypatch.setattr(module,name,forbidden)
    data=stats.query('huaxing',{})
    assert data['totals']['total']==len(results) and data['totals']['passRate']==expected
    assert data['totals']['decided']==sum(x in {'PASS','FAIL'} for x in results)
    assert data['excluded']=={} and hashes()==before


def test_reconfirm_revoke_return_and_same_po_never_count_history(db):
    first=approval(db,1); second=approval(db,2,'FAIL') # Same PO, distinct stable tasks.
    assert stats.query('huaxing',{})['totals']['total']==2
    first=transition(first,'revoke'); assert stats.query('huaxing',{})['totals']['total']==1
    first=transition(first); first=transition(first,'revoke'); first=transition(first)
    assert stats.query('huaxing',{})['totals']['total']==2
    second=transition(second,'revoke')
    sheet.return_to_inspection('huaxing',second['id'],dict(revision=second['revision'],requestKey=uuid4().hex),ACTOR)
    assert stats.query('huaxing',{})['totals']['total']==1
    with sheet.store() as conn: assert conn.execute("SELECT count(*) FROM changes WHERE action='confirm'").fetchone()[0]==4


def test_factory_customer_and_frozen_date_scope(db):
    approval(db,1,code='A',actual='2026-10-30'); approval(db,2,'FAIL',code='B')
    approval(db,3,'LG',factory='huadeng',code='C')
    data=stats.query('huaxing',{}); assert data['totals']['total']==2 and len(data['customers'])==2
    a=next(x['key'] for x in data['customers'] if x['code']=='A')
    assert stats.query('huaxing',{'customer':a})['totals']['PASS']==1
    assert stats.query('huaxing',{'from':'2026-11-01'})['totals']['FAIL']==1
    assert stats.query('huaxing',{'to':'2026-10-30'})['totals']['PASS']==1
    assert stats.query('huaxing',{'from':'2026-10-30','to':'2026-10-30'})['totals']['total']==1
    assert stats.query('huaxing',{'customer':'f'*64})['customerUnavailable'] is True
    assert stats.query('huadeng',{})['totals']['LG']==1


def test_test_reference_included_but_stale_and_tampered_projection_excluded(db):
    approval(db,1,flag='testData'); approval(db,2,flag='referenceData'); bad=approval(db,3)
    old=approval(db,4); transition(old,'revoke')
    with summary.store(True) as conn:
        conn.execute('UPDATE records SET active=1 WHERE source_key=?',('entry:'+old['id'],))
        conn.execute("UPDATE records SET result='FAIL' WHERE source_key=?",('entry:'+bad['id'],))
    data=stats.query('huaxing',{})
    assert data['totals']['total']==2 and data['totals']['passRate']==100
    assert data['excluded']==dict(notCurrentInlineApproval=1,invalidLineage=1)


def rewrite_fixture(entry, **updates):
    with sheet.store(True,review=True) as conn:
        row=conn.execute('SELECT approved_snapshot FROM entry_details WHERE entry_id=?',(entry['id'],)).fetchone()
        snapshot=json.loads(row[0]); snapshot.update(updates)
        if 'inspectionDateSource' in updates and updates['inspectionDateSource']=='REMOVE':
            snapshot.pop('inspectionDateSource'); snapshot.pop('inspectionDate',None)
            # Seed a pre-marker projection in the isolated fixture. The real
            # upsert correctly refuses downgrading a previously frozen record.
            conn.execute('DELETE FROM qsum.records WHERE factory=? AND source_key=?',
                         ('huaxing', 'entry:'+entry['id']))
        conn.execute('UPDATE entry_details SET approved_snapshot=? WHERE entry_id=?',(wf.dump(snapshot),entry['id']))
        conn.execute('UPDATE entries SET result=? WHERE id=?',(snapshot['result'],entry['id']))
        summary.upsert(conn,'huaxing','entry:'+entry['id'],summary.review_item(snapshot),schema='qsum.')


def test_legacy_other_states_and_historical_blank_dates_not_inferred(db):
    for n,result in enumerate(['REJ','COND','HOLD']):
        row=approval(db,n); rewrite_fixture(row,result=result,inspectionDateSource='REMOVE',actualDate='')
    data=stats.query('huaxing',{})
    assert data['totals']['other']==dict(REJ=1,COND=1,HOLD=1)
    assert data['totals']['decided']==0 and data['totals']['passRate'] is None and data['missingDate']==3
    assert data['months']==[] and stats.query('huaxing',{'from':'2026-01-01'})['totals']['total']==0


def test_report_groups_legacy_approvals_by_captured_plan_when_final_date_is_blank(db):
    planned = approval(db, 1, 'FAIL', planned='2026-11-04')
    rewrite_fixture(planned, inspectionDateSource='REMOVE')
    actual = approval(db, 2, 'PASS', actual='2026-10-30')
    rewrite_fixture(actual, inspectionDateSource='REMOVE')
    before = hashes()

    report = stats.report('huaxing', {'result':'ALL'})
    assert report['options']['years'] == ['2026']
    assert [(m['month'], m['total']) for m in report['months']] == [('2026-10', 1), ('2026-11', 1)]
    assert report['totals']['total'] == 2 and report['scheduleDateCount'] == 1 and report['missingDate'] == 0
    assert [(r['date'], r['usesScheduleDate']) for r in report['details']['items']] == [
        ('2026-11-04', True), ('2026-10-30', False)]
    filtered = stats.report('huaxing', {'year':'2026','month':'11','day':'4'})
    assert filtered['options']['days'] == ['4'] and filtered['details']['total'] == 1
    daily_plan = daily.report('huaxing', '2026-11-04')
    assert daily_plan['total'] == filtered['totals']['total'] == 1
    assert daily_plan['rows'][0]['values'][8] == 'FAIL' and daily_plan['scheduleCount'] == 1
    daily_actual = daily.report('huaxing', '2026-10-30')
    assert daily_actual['passed'] == 1 and daily_actual['scheduleCount'] == 0
    assert daily.report('huaxing', '2026-11-03')['total'] == 0
    assert stats.query('huaxing', {'from':'2026-11-01'})['totals']['total'] == 0
    assert hashes() == before

    summary_rows = summary.listing('huaxing', {'dateBasis':'report'})
    assert summary_rows['years'] == ['2026'] and summary_rows['unknownDates'] == 0
    assert [(row['entryId'], row['reportDate'], row['inspectionDate']) for row in summary_rows['items']] == [
        (actual['id'], '2026-10-30', '2026-10-30'), (planned['id'], '2026-11-04', '')]
    query = {'dateBasis':'report', 'year':'2026', 'month':'11', 'day':'4'}
    matched = summary.listing('huaxing', query)
    assert matched['total'] == filtered['totals']['total'] == 1
    assert summary.detail('huaxing', matched['items'][0]['id'])['reportDate'] == '2026-11-04'
    assert summary.listing('huaxing', {**query, 'dateBasis':'actual'})['total'] == 0


def test_malformed_frozen_marker_rejected_without_repair(db):
    row=approval(db,1); rewrite_fixture(row,inspectionDateSource='qc_manual')
    before=hashes(); data=stats.query('huaxing',{})
    assert data['excluded']=={'invalidLineage':1} and hashes()==before


def test_missing_projection_reported_and_snapshot_capacity_never_truncates(db,monkeypatch):
    row=approval(db,1)
    with summary.store(True) as conn:
        conn.execute('UPDATE records SET active=0 WHERE source_key=?',('entry:'+row['id'],))
    before=hashes();data=stats.query('huaxing',{})
    assert data['excluded']=={'missingProjection':1} and hashes()==before
    approval(db,2)
    monkeypatch.setattr(stats,'MAX_SNAPSHOT_BYTES',1)
    before=hashes()
    with pytest.raises(HTTPException) as error:stats.query('huaxing',{})
    assert error.value.status_code==503 and hashes()==before


def test_explicit_manual_test_declarations_do_not_hide_summary_records(db):
    first=approval(db,1);rewrite_fixture(first,remark='手动测试｜本条为模拟排期')
    second=approval(db,2);rewrite_fixture(second,sourceNote='【QC隔离验收测试】图片上传验收')
    approval(db,3,customer='测试仪器制造客户',code='UAT-REAL-CUSTOMER')
    before=hashes();data=stats.query('huaxing',{})
    assert data['totals']['total']==3 and data['excluded']=={}
    assert any(c['code']=='UAT-REAL-CUSTOMER' for c in data['customers']) and hashes()==before


@pytest.mark.parametrize('params',[{'from':'2026-02-30'},{'from':'2026-11-02','to':'2026-11-01'},
    {'customer':'x'},{'factory':'huadeng'},{'from':'20261101'}])
def test_invalid_filter_does_not_initialize_database(params):
    with pytest.raises(HTTPException) as error: stats.query('huaxing',params)
    assert error.value.status_code==422 and not Path(wf.settings.qc_department_data_dir).exists()


def test_missing_stores_no_creation_and_capacity_no_partial_results(db,monkeypatch):
    assert stats.query('huaxing',{})['ready'] is False
    assert not Path(wf.settings.qc_department_data_dir).exists()
    approval(db,1); approval(db,2)
    monkeypatch.setattr(stats,'MAX_ROWS',1)
    before=hashes()
    with pytest.raises(HTTPException) as error: stats.query('huaxing',{})
    assert error.value.status_code==503 and hashes()==before


def test_real_gateway_statistics_and_self_review_permissions(monkeypatch,tmp_path):
    # Real seeded role definitions, authentication cookies and factory scopes.
    from test_molding_sample_api import make_client,login_as
    from test_qc_department_gateway import install_upstream
    import test_molding_sample_api, importlib
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'qc'))
    with make_client(monkeypatch) as client:
        from app.api import qc_department
        install_upstream(monkeypatch)
        monkeypatch.setattr(qc_department, 'schedule_example', lambda factory: {'items': []})
        assert client.get('/api/qc-department/huaxing/api/approved-statistics').status_code==401
        login_as(client,'qc_inspector')
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        assert client.get(base+'api/approved-statistics').status_code==200
        assert client.post(base+'api/approved-statistics',json={}).status_code==404
        assert client.get(base+'api/approved-statistics?company=hy-huadeng').status_code==403
        assert client.get(base+'api/approved-statistics?from=2026-01-01&from=2026-02-01').status_code==422
        assert client.get('/api/qc-department/huakang-a/api/approved-statistics').status_code==403
        assert client.get(base+'qc-approved-statistics.js').status_code==200
        for username in ('qc_inspector','qc_supervisor'):
            login_as(client,username)
            base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
            def post(path,body):
                response=client.post(base+'api/'+path,json=body)
                assert response.status_code==200,response.text
                return response.json()
            source=post('workflow/schedules',{'requestKey':uuid4().hex,'row':dict(dateFrom='2026-11-03',dateTo='',
                customer='角色验收',poNo=username,country='UK',productNo='ROLE',productName='合成',quantity='100',
                unitsPerCarton='10',cartonCount='10',production='合成',agency='行验',customerPo='',remark='')})
            task=post('workflow/tasks',{'requestKey':uuid4().hex,'items':[dict(sourceId=source['id'],sourceRevision=1,
                method='internal',batch='首验',plannedDate='2026-11-03',plannedQuantity='100')]})['items'][0]
            entry=next(x for x in client.get(base+'api/inspection-sheet/entries').json()['items'] if x['sourceId']==source['id'])
            entry=post('inspection-sheet/entries/'+entry['id']+'/save',dict(revision=entry['revision'],result='PASS',remark='本人填写确认'))
            entry=post('inspection-sheet/entries/'+entry['id']+'/submit',dict(revision=entry['revision']))
            body=dict(entries=[dict(id=entry['id'],revision=entry['revision'])],requestKey=uuid4().hex)
            result=post('inspection-sheet/review/confirm',body); assert result['succeeded']==1
            approved=result['results'][0]['item']; assert approved['lastActor']['name']==approved['submittedBy']
            audit=client.get(base+'api/inspection-sheet/entries/'+entry['id']+'/audit').json()['items']
            assert next(e for e in audit if e['action']=='submit')['actor']['id']==approved['lastActor']['id']
            stale=post('inspection-sheet/review/revoke',{**body,'requestKey':uuid4().hex})
            assert stale['failed']==1 and stale['results'][0]['status']==409
            assert client.post(base+'api/inspection-sheet/review/entries/'+entry['id']+'/save',json=dict(revision=approved['revision'],result='FAIL',remark='锁定')).status_code==409
            # Legacy approval cannot confirm this inline task or bypass its state.
            legacy=client.post(base+'api/workflow/tasks/'+task['id']+'/approve',json=dict(revision=task['revision'],reason=''))
            assert legacy.status_code==(403 if username=='qc_inspector' else 409)
            assert client.post('/api/qc-department/huakang-a/'+base.split('/huaxing/')[1]+'api/inspection-sheet/review/confirm',json=body).status_code==403
            revoked=post('inspection-sheet/review/revoke',dict(entries=[dict(id=entry['id'],revision=approved['revision'])],requestKey=uuid4().hex))
            assert revoked['succeeded']==1
        assert client.get(base+'api/approved-statistics').json()['totals']['total']==0
        client.post('/api/auth/logout')
        assert client.post(base+'api/inspection-sheet/review/confirm',json=body).status_code==401
        login_as(client,'engineer')
        assert client.get(base+'api/approved-statistics').status_code==403


def test_all_seven_summary_records_including_pending_lg_and_labels(db):
    for n,result in enumerate(['PASS','PASS','FAIL','PENDING','LG']):
        approval(db,n,result)
    approval(db,5,flag='testData'); approval(db,6,flag='referenceData')
    summary_total=summary.listing('huaxing',{})['total']
    before=hashes(); data=stats.query('huaxing',{})
    assert data['totals']==dict(total=7,PASS=4,FAIL=1,PENDING=1,LG=1,decided=5,other={},passRate=80)
    assert data['totals']['total']==summary_total==data['months'][0]['total']
    assert data['excluded']=={} and hashes()==before


def test_report_facets_details_and_denominator_share_readonly_snapshot(db):
    for n,result in enumerate(['PASS','PASS','FAIL','PENDING','LG','PASS','FAIL']):
        approval(db,n,result,code='A',actual='2026-11-03')
    approval(db,10,'PASS',customer='另一客户',code='B',actual='2026-10-04')
    approval(db,11,'FAIL',customer='旧年客户',code='C',actual='2025-08-20')
    approval(db,12,'LG',factory='huadeng',customer='另一厂',actual='2026-09-01')
    before=hashes();data=stats.report('huaxing',{'result':'ALL'})
    assert data['options']['years']==['2026','2025']
    assert data['options']['months']==['10','11'] and data['options']['days']==[]
    assert data['filters']['year']=='2026' and data['totals']['total']==8
    assert data['totals']['passRate']==66.6667
    assert data['details']['total']==8 and len(data['details']['items'])==5
    page2=stats.report('huaxing',{'year':'2026','result':'ALL','page':'2'})
    assert page2['totals']==data['totals'] and len(page2['details']['items'])==3
    assert not ({r['id'] for r in data['details']['items']} & {r['id'] for r in page2['details']['items']})
    selected=stats.report('huaxing',{'year':'2026','month':'11','day':'3','result':'PENDING'})
    assert selected['options']['days']==['3'] and [c['code'] for c in selected['options']['customers']]==['A']
    assert selected['totals']['total']==7 and selected['details']['total']==1
    assert selected['details']['items'][0]['date']=='2026-11-03'
    assert selected['details']['items'][0]['result']=='PENDING'
    assert selected['details']['items'][0]['poNo']=='SYNTHETIC-PO'
    assert 'approved_snapshot' not in selected['details']['items'][0]
    assert hashes()==before


def test_report_empty_undecided_missing_dates_and_removed_selections(db):
    empty=stats.report('huaxing',{})
    assert empty['options']==dict(years=[],months=[],days=[],customers=[])
    assert empty['totals']['passRate'] is None and empty['details']['items']==[]
    approval(db,1,'PENDING',actual='2026-02-03',code='A')
    approval(db,2,'LG',actual='2026-02-03',code='A')
    data=stats.report('huaxing',{'year':'2026','month':'2','day':'3'})
    assert data['totals']['total']==2 and data['totals']['passRate'] is None
    assert data['months'][0]['passRate'] is None
    stale=stats.report('huaxing',{'year':'2026','month':'1','customer':'f'*64})
    assert stale['filters']['customer']=='' and stale['filters']['month']=='' and len(stale['notices'])==2
    row=approval(db,3);rewrite_fixture(row,result='HOLD',inspectionDateSource='REMOVE',actualDate='',dateFrom='')
    data=stats.report('huaxing',{})
    assert data['missingDate']==1 and data['totals']['total']==2


@pytest.mark.parametrize('params',[{'year':'0'},{'year':'2026','month':'13'},
    {'year':'2026','month':'2','day':'30'},{'month':'11'},{'year':'2026','day':'1'},
    {'year':'2026','result':'hack'},{'page':'0'},{'page':'10000000'},{'customer':'x'},{'factory':'huadeng'}])
def test_report_invalid_filters_do_not_create_stores(params):
    with pytest.raises(HTTPException) as error:stats.report('huaxing',params)
    assert error.value.status_code==422 and not Path(wf.settings.qc_department_data_dir).exists()


def test_period_reports_share_daily_snapshot_source_and_include_exact_boundaries(db):
    days = ['2026-10-31', '2026-11-01', '2026-11-02', '2026-11-08',
            '2026-11-09', '2026-11-30', '2026-12-01']
    for n, day in enumerate(days):
        approval(db, n, actual=day)
    week = daily.report('huaxing', '2026-11-06', 'weekly')
    month = daily.report('huaxing', '2026-11-06', 'monthly')
    assert (week['dateFrom'], week['dateTo'], week['total']) == ('2026-11-02', '2026-11-08', 2)
    assert (month['dateFrom'], month['dateTo'], month['total']) == ('2026-11-01', '2026-11-30', 5)
    assert {r['values'][3] for r in week['rows']} == {'ITEM-2', 'ITEM-3'}
    assert month['passed'] == 5 and month['rate'] == 100
    assert daily.period_bounds('2024-02-20', 'monthly') == ('2024-02-01', '2024-02-29')
    assert daily.period_bounds('2026-01-01', 'weekly') == ('2025-12-29', '2026-01-04')
    assert daily.report('huaxing', '2026-11-06')['total'] == 0
    with pytest.raises(HTTPException):
        daily.report('huaxing', '2026-11-06', 'yearly')
