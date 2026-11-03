from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
from uuid import uuid4
import json
import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel, CALENDAR_MAC_1904
from app.services import qc_schedule_candidates as gate
from app.services import qc_inspection_sheet as sheet, qc_inspection_summary as summary, qc_workflow as wf
from test_customer_order_ledger import engine, db
from test_qc_workflow import ACTOR
from test_qc_flow_completion import schedule,push,entries

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(wf.settings,'qc_department_data_dir',str(tmp_path/'companies'))

@pytest.mark.parametrize('today,raw,bucket',[
 ('2026-11-03','2026-11-02','expired'),('2026-11-03','2026-11-03','accepted'),
 ('2026-11-03','2026-11-04','accepted'),('2026-11-30','2026-12-01','accepted'),
 ('2026-12-31','2027-01-01','accepted'),('2027-01-01','2026-12-31','expired'),
 ('2026-11-03','','pending'),('2026-11-03','bad','pending'),('2026-11-03','2026-02-30','pending'),
 ('2026-11-03','11/04','pending'),('2026-11-03','2026年11月4日','accepted'),
 ('2026-11-03','2026/11/04','accepted'),('2026-11-03','2026-11-02T16:01:00Z','accepted'),
 ('2026-11-03','2026-11-02T15:59:00Z','expired'),('2026-11-03',True,'pending'),
 ('2026-11-03',float('nan'),'pending'),
])
def test_fixed_shanghai_boundary(today,raw,bucket):
    row={'id':'source-a','dateFrom':raw,'sourceNote':'原始信息'}
    result=gate.filter_new_candidates([row],today=date.fromisoformat(today))
    assert len(result[bucket])==1
    if not isinstance(raw,float):assert result[bucket][0]['source']==row
    assert result['timezone']=='Asia/Shanghai'


def test_excel_epochs_multiple_stages_and_ambiguous_range():
    for epoch in [gate.CALENDAR_WINDOWS_1900,CALENDAR_MAC_1904]:
        serial=to_excel(datetime(2026,11,4),epoch)
        r=gate.filter_new_candidates([{'dateFrom':serial}],today=date(2026,11,3),epoch=epoch)
        assert r['accepted'][0]['eligibleDates']==['2026-11-04']
    rows=[{'id':'multi','dateFrom':'2026-11-01；2026-11-03；2027-01-01'},
          {'id':'mixed','dateFrom':'2026-11-04;不确定'},
          {'id':'span','dateFrom':'2026-11-02','dateTo':'2026-11-04'},
          {'id':'reverse','dateFrom':'2026-11-05','dateTo':'2026-11-03'}]
    before=deepcopy(rows);r=gate.filter_new_candidates(rows,today=datetime(2026,11,2,16,0,tzinfo=timezone.utc))
    assert rows==before and r['businessDate']=='2026-11-03'
    assert r['accepted'][0]['eligibleDates']==['2026-11-03','2027-01-01']
    assert len(r['pending'])==3


def submitted(db):
    push(db,[schedule(1)])
    r=entries(db)[0]
    r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='保留备注'),ACTOR)
    return sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)


def command(r,action):
    return sheet.review_batch('huaxing',action,dict(entries=[{'id':r['id'],'revision':r['revision']}],requestKey=uuid4().hex,reason=''),ACTOR)['results'][0]['item']


def test_review_fields_full_persistence_cas_audit_snapshot_and_readonly(db):
    r=submitted(db);before=deepcopy(r)
    values={'responsible':'UAT 负责人','firstResponsible':'第一人','secondResponsible':'第二人','otherRemark':'独立其他备注\n第二行','inspectionFactory':'华兴补录'}
    body=dict(revision=r['revision'],result=r['result'],remark=r['remark'],**values)
    r=sheet.save('huaxing',r['id'],body,ACTOR,review=True)
    with sheet.store() as c:
        reread=sheet.unpack(c,sheet.get(c,'huaxing',r['id']))
        source=json.loads(c.execute('SELECT base FROM entries WHERE id=?',(r['id'],)).fetchone()[0])
    assert all(reread[k]==v for k,v in values.items())
    assert source['sourceRecord']==before['sourceRecord'] and r['photos']==before['photos']
    event=sheet.audit('huaxing',r['id'])['items'][0]
    assert set(event['changes'])==set(values) and event['location']=='审核中心 · 待审核'
    with pytest.raises(HTTPException) as conflict:sheet.save('huaxing',r['id'],body,ACTOR,review=True)
    assert conflict.value.status_code==409
    r=command(r,'confirm');s=summary.listing('huaxing',{})['items'][0]
    assert all(s[k]==v for k,v in values.items())
    with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(body,revision=r['revision']),ACTOR,review=True)
    r=command(r,'revoke')
    r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result=r['result'],remark=r['remark'],responsible=''),ACTOR,review=True)
    assert r['firstResponsible']=='第一人' and r['otherRemark']==values['otherRemark']
    r=command(r,'confirm');assert summary.listing('huaxing',{})['items'][0]['responsible']==''
    assert r['submittedAt']==before['submittedAt']
    for name in ['responsible','firstResponsible','inspectionFactory']:
        r=command(r,'revoke')
        with pytest.raises(HTTPException) as e:sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='',**{name:'x\ny'}),ACTOR,review=True)
        assert e.value.status_code==422
        r=command(r,'confirm')
    with pytest.raises(HTTPException):sheet.save('huadeng',r['id'],dict(revision=r['revision'],result='PASS',remark='',responsible='跨厂'),ACTOR,review=True)


def test_summary_schedule_date_is_read_only_filter_sort_detail_and_export(db):
    r=command(submitted(db),'confirm')
    assert not r.get('actualDate')
    before=summary.listing('huaxing',{})['items'][0]
    result=summary.listing('huaxing',{'dateBasis':'schedule','year':r['dateFrom'][:4]})
    assert result['total']==1 and result['items'][0]['scheduleDate']==r['dateFrom']
    assert result['items'][0]['inspectionDate']==''
    assert summary.detail('huaxing',before['id'])['scheduleDate']==r['dateFrom']
    assert summary.listing('huaxing',{'dateBasis':'schedule','year':'2040'})['total']==0
    assert summary.listing('huadeng',{'dateBasis':'schedule'})['total']==0
    assert summary.listing('huaxing',{})['items'][0]==before
    unlinked={'id':'old','inspectionDate':'2026-11-01','submittedAt':'2026-11-03','confirmedAt':'2026-11-04'}
    assert summary.with_schedule_dates('huaxing',[unlinked])[0]['scheduleDate']==''
    content=summary.export_excel('huaxing',{'dateBasis':'schedule','year':r['dateFrom'][:4]})
    book=load_workbook(BytesIO(content[0] if isinstance(content,tuple) else content))
    assert book.active.cell(1,1).value=='实际验货日期'
    assert book.active.cell(2,1).value is None
    book.close()

def test_automatic_intake_keeps_historical_schedule_and_existing_task(db):
    from test_customer_order_ledger import ingest
    line=ingest(db)
    line.data={**line.data,'planned_inspection_date':'2026-11-02','inspection_agency':'客验'}
    db.flush()
    before=deepcopy(wf.sources(db,'huaxing'))
    report=wf.automatic_schedule_candidates(db,'huaxing',today=date(2026,11,3))
    assert len(report['expired'])==1 and not report['accepted']
    assert wf.sources(db,'huaxing')==before
    line.data={**line.data,'planned_inspection_date':'2026-11-03'};db.flush()
    assert len(wf.automatic_schedule_candidates(db,'huaxing',today=date(2026,11,3))['accepted'])==1
    wf.create_tasks(db,'huaxing',{'requestKey':'round5-push-001','items':[{'sourceId':line.id,'sourceRevision':line.revision,'method':'external','batch':'首验','plannedDate':'2026-11-03','plannedQuantity':'100'}]},ACTOR)
    before=deepcopy(wf.sources(db,'huaxing'))
    assert not wf.automatic_schedule_candidates(db,'huaxing',today=date(2026,11,4))['expired']
    assert wf.sources(db,'huaxing')==before and len(before['items'][0]['tasks'])==1
    assert not wf.automatic_schedule_candidates(db,'huadeng',today=date(2026,11,3))['accepted']


def test_review_execution_supplements_roundtrip_audit_approval_and_clear(db):
    r=submitted(db);original=deepcopy(r)
    with sheet.store() as c:
        submission=c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]
    patch={'actualDate':'2026-11-03','actualQuantity':'120','sampleQuantity':'8','inspector':'测试检验员','institution':'测试机构','reportNo':'TEST-REPORT-01','reportMissingReason':'等待签章\n测试说明','resultExplanation':'补录结论','defects':[{'desc':'包装压痕','qty':'0','level':'MIN 2.5','remark':'测试'}],'measurements':[{'item':'长度','standard':'100±1 mm','values':'100.2 mm','result':'PASS','remark':'测试'}]}
    body=dict(revision=r['revision'],result=r['result'],remark=r['remark'],inspectionExecution=patch,reportStatus='已收到')
    r=sheet.save('huaxing',r['id'],body,ACTOR,review=True)
    assert all(r['inspectionExecution'][k]==v for k,v in patch.items())
    assert r['actualDate']=='2026-11-03' and r['actualQuantity']=='120' and r['inspector']=='测试检验员'
    assert r['sourceRecord']==original['sourceRecord'] and r['photos']==original['photos']
    with sheet.store() as c:
        assert sheet.unpack(c,sheet.get(c,'huaxing',r['id']))==r
        assert c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]==submission
    event=sheet.audit('huaxing',r['id'])['items'][0]
    assert event['changes']['inspectionExecution.defects']['after']==patch['defects']
    assert event['changes']['inspectionExecution.actualDate']['after']=='2026-11-03'
    unchanged=sheet.save('huaxing',r['id'],dict(body,revision=r['revision']),ACTOR,review=True)
    assert unchanged['revision']==r['revision']
    with pytest.raises(HTTPException) as conflict:sheet.save('huaxing',r['id'],body,ACTOR,review=True)
    assert conflict.value.status_code==409
    with pytest.raises(HTTPException):sheet.save('huadeng',r['id'],dict(body,revision=r['revision']),ACTOR,review=True)
    r=command(r,'confirm');saved=summary.listing('huaxing',{})['items'][0]
    assert saved['inspectionExecution']==r['inspectionExecution'] and saved['inspectionDate']=='2026-11-03'
    assert saved['reportStatus']=='已收到'
    with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(body,revision=r['revision']),ACTOR,review=True)
    r=command(r,'revoke');r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result=r['result'],remark=r['remark'],inspectionExecution={'actualQuantity':'0','sampleQuantity':'','defects':[],'reportNo':''}),ACTOR,review=True)
    assert r['actualQuantity']=='0' and r['inspectionExecution']['sampleQuantity'] is None
    assert r['inspectionExecution']['defects']==[] and r['inspectionExecution']['reportNo']==''
    assert r['inspectionExecution']['measurements']==patch['measurements']
    assert r['submittedAt']==original['submittedAt']


@pytest.mark.parametrize('patch',[
 {'actualDate':'2026-02-30'}, {'actualQuantity':'-1'}, {'sampleQuantity':True},
 {'sampleQuantity':'NaN'},{'sampleQuantity':'1.00001'},{'result':'PASS'}, {'sourceRecord':{}},
 {'defects':[{'desc':'x','qty':'-1','level':'CR','remark':''}]},
 {'defects':[{'desc':'x','qty':'1','level':'wrong','remark':''}]},
 {'measurements':[{'item':'x','standard':'','values':'','result':'bad','remark':''}]},
 {'measurements':[{'item':'','standard':'','values':'','result':'PASS','remark':''}]},
 {'defects':{}}, {'reportNo':'x'*256},
])
def test_review_execution_validation_rejects_without_changing_record(db,patch):
    r=submitted(db)
    with pytest.raises(HTTPException) as e:sheet.save('huaxing',r['id'],dict(revision=r['revision'],result=r['result'],remark=r['remark'],inspectionExecution=patch),ACTOR,review=True)
    assert e.value.status_code==422
    with sheet.store() as c:assert sheet.unpack(c,sheet.get(c,'huaxing',r['id']))==r


def test_workbench_cannot_write_review_execution(db):
    push(db,[schedule(1)]);r=entries(db)[0]
    with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='',inspectionExecution={'reportNo':'not-allowed'}),ACTOR)
