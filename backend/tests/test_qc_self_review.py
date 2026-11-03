"""Real SQLite transitions, photos, CAS, audit and atomic final projection."""
from copy import deepcopy
from io import BytesIO
import base64,json,sqlite3
from uuid import uuid4
import pytest
from PIL import Image
from fastapi import HTTPException
from app.services import qc_workflow as wf,qc_inspection_sheet as sheet,qc_inspection_summary as summary
from test_customer_order_ledger import engine,db
from test_qc_workflow import ACTOR
from test_qc_flow_completion import schedule,push,entries

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):monkeypatch.setattr(wf.settings,'qc_department_data_dir',str(tmp_path/'companies'))
def item(db,n=1):
 push(db,[schedule(n)]);return entries(db)[-1]
def save(row,**extra):return sheet.save('huaxing',row['id'],dict(revision=row['revision'],result='PASS',remark='备注',improvement='措施',inspectionProblem='标签问题',**extra),ACTOR)
def command(row,action='confirm',reason='',key=None):return sheet.review_batch('huaxing',action,dict(entries=[dict(id=row['id'],revision=row['revision'])],reason=reason,requestKey=key or uuid4().hex),ACTOR)
def photo(row,color):
 f=BytesIO();Image.new('RGB',(16,12),color).save(f,'PNG')
 return sheet.add_photo('huaxing',row['id'],dict(revision=row['revision'],name=color+'.png',content=base64.b64encode(f.getvalue()).decode(),requestKey=uuid4().hex),ACTOR)

def test_full_self_review_revoke_reconfirm_photos_and_history(db):
 r=save(item(db));r=photo(photo(r,'red'),'blue');beforephotos=deepcopy(r['photos'])
 r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
 assert r['reviewState']=='pending' and not r['confirmedAt'];assert wf.sources(db,'huaxing')['items'][0]['tasks'][0]['state']=='pending';assert summary.listing('huaxing',{})['total']==0
 r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='FAIL',remark='复核修改\n中文',improvement='整改复测',inspectionProblem=''),ACTOR,review=True)
 assert r['lastLocation']=='审核中心 · 待审核' and r['inspectionProblem']==''
 submit_at=r['submittedAt'];r=command(r)['results'][0]['item'];first_at=r['confirmedAt']
 assert wf.sources(db,'huaxing')['items'][0]['tasks'][0]['state']=='approved'
 one=summary.listing('huaxing',{});assert one['total']==1 and one['items'][0]['status']=='approved'
 detail=summary.detail('huaxing',one['items'][0]['id']);assert detail['photos']==beforephotos and detail['remark']=='复核修改\n中文'
 assert detail['confirmedAt']==first_at and detail['submittedAt']==submit_at and detail['sourceNote']=='原始备注'
 with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='不能修改'),ACTOR,review=True)
 for reason in ['','标签复核后补充']:
  r=command(r,'revoke',reason)['results'][0]['item'];assert r['reviewState']=='pending'
  assert summary.listing('huaxing',{})['total']==0
  r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PENDING',remark=reason,improvement='重审措施'),ACTOR,review=True)
  r=command(r)['results'][0]['item'];assert r['confirmedAt']>=first_at
  assert summary.listing('huaxing',{})['total']==1
 assert r['photos']==beforephotos and r['submittedAt']==submit_at
 history=sheet.audit('huaxing',r['id'])['items'];assert sum(e['action']=='confirm' for e in history)==3
 assert [e['changes']['reason'] for e in history if e['action']=='revoke']==['标签复核后补充','']
 assert all(e['actor']==ACTOR and e['at'] and e['location'] for e in history)
 assert all(e['changes'] for e in history)
 assert len(summary.detail('huaxing',one['items'][0]['id'])['archiveHistory'])>=4
 for p in r['photos']:assert Image.open(BytesIO(sheet.read_photo('huaxing',r['id'],p['id']))).size==(16,12)

def test_noop_reads_redundant_saves_and_cas(db):
 r=save(item(db));before=sheet.audit('huaxing',r['id']);unchanged=save(r)
 assert unchanged==r and sheet.audit('huaxing',r['id'])==before
 for _ in range(3):summary.listing('huaxing',{});sheet.audit('huaxing',r['id'])
 assert sheet.audit('huaxing',r['id'])==before
 with pytest.raises(HTTPException) as error:save(dict(r,revision=r['revision']-1))
 assert error.value.status_code==409 and sheet.audit('huaxing',r['id'])==before

def test_batch_partial_failure_repeat_request_and_factory_boundary(db):
 rows=[schedule(i) for i in range(3)];push(db,rows)
 a,b,c=[sheet.submit('huaxing',r['id'],{'revision':save(r)['revision']},ACTOR) for r in entries(db)]
 key=uuid4().hex;body=dict(entries=[dict(id=a['id'],revision=a['revision']),dict(id=b['id'],revision=b['revision']-1)],requestKey=key)
 out=sheet.review_batch('huaxing','confirm',body,ACTOR);assert (out['succeeded'],out['failed'])==(1,1)
 again=sheet.review_batch('huaxing','confirm',body,ACTOR);assert (again['succeeded'],again['failed'])==(1,1)
 assert sheet.review_batch('huaxing','confirm',body,dict(ACTOR,id='another-user'))['results'][0]['status']==409
 assert len([x for x in sheet.audit('huaxing',a['id'])['items'] if x['action']=='confirm'])==1
 assert summary.listing('huaxing',{})['total']==1
 wrong=sheet.review_batch('huadeng','confirm',body,ACTOR);assert wrong['failed']==2
 bad=deepcopy(body);bad['entries'][0]['revision']+=1
 assert sheet.review_batch('huaxing','confirm',bad,ACTOR)['results'][0]['status']==409
 assert command(b)['succeeded']==1 and summary.listing('huaxing',{})['total']==2
 with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',c['id']))['reviewState']=='pending'

def test_summary_failure_rolls_back_state_time_and_audit(db,monkeypatch):
 r=save(item(db));r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR);before=sheet.audit('huaxing',r['id'])
 def fail(*a,**k):raise sqlite3.OperationalError('simulated full disk')
 monkeypatch.setattr(summary,'upsert',fail)
 with pytest.raises(sqlite3.OperationalError):command(r)
 with sheet.store() as conn:after=sheet.unpack(conn,sheet.get(conn,'huaxing',r['id']))
 assert after==r and sheet.audit('huaxing',r['id'])==before

def test_legacy_completed_additive_migration_preserves_snapshot(db):
 r=save(item(db));legacy=dict(r,submittedAt='2026-11-01T17:05:00+00:00',submittedBy='Historical user',submissionStatus='completed');snapshot=wf.dump(legacy)
 with sheet.store(True) as c:c.execute("UPDATE entry_details SET submitted_at=?,submitted_snapshot=?,flow_version=0 WHERE entry_id=?",(legacy['submittedAt'],snapshot,r['id']))
 a=summary.listing('huaxing',{})['items'][0];assert a['status']=='completed' and a['submittedAt']==legacy['submittedAt'] and not a.get('confirmedAt')
 assert entries(db)[0]['legacyCompleted']
 with sheet.store() as c:
  ext=c.execute('SELECT * FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone();assert ext['submitted_snapshot']==snapshot and ext['confirmed_at']==''
 assert command(entries(db)[0])['failed']==1

def test_beijing_cross_day_from_real_confirmation_timestamp():
 assert summary.business_date('2026-11-01T17:05:00+00:00')=='2026-11-02'
 assert summary.business_date('2026-11-01T00:05:00+00:00')=='2026-11-01'


def test_legacy_approved_without_timestamp_cannot_be_resubmitted(db):
 r=save(item(db))
 with sheet.store(True) as conn:
  base=json.loads(conn.execute('SELECT base FROM entries WHERE id=?',(r['id'],)).fetchone()[0]);base['legacyReviewState']='approved'
  conn.execute('UPDATE entries SET base=? WHERE id=?',(wf.dump(base),r['id']))
  conn.execute('UPDATE entry_details SET flow_version=0 WHERE entry_id=?',(r['id'],))
 before=sheet.audit('huaxing',r['id'])
 with pytest.raises(HTTPException) as error:sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
 assert error.value.status_code==409 and sheet.audit('huaxing',r['id'])==before
