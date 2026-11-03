"""Real isolated SQLite: receipts, supplements and return/resubmit lifecycle."""
from copy import deepcopy
import json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.services import qc_workflow as wf,qc_inspection_sheet as sheet,qc_inspection_summary as summary
from test_customer_order_ledger import engine,db
from test_qc_workflow import ACTOR
from test_qc_self_review import item,save,photo,command
from test_qc_flow_completion import entries

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):monkeypatch.setattr(wf.settings,'qc_department_data_dir',str(tmp_path/'companies'))
def submitted(db):
 r=photo(save(item(db)),'red');return sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
def read(r):
 with sheet.store() as c:return sheet.unpack(c,sheet.get(c,'huaxing',r['id']))

def test_notifications_user_factory_once_and_new_events(db):
 r=submitted(db);r=command(r)['results'][0]['item'];r=command(r,'revoke','检查标识')['results'][0]['item']
 data=sheet.reversal_notifications('huaxing',ACTOR)['items'];assert len(data)==1
 e=data[0];assert e['reason']=='检查标识' and e['customer']==r['customer'] and e['entryId']==r['id']
 assert sheet.reversal_notifications('huakang-a',ACTOR)['items']==[]
 other=dict(ACTOR,id='other');assert sheet.reversal_notifications('huaxing',other)['items']==data
 sheet.reversal_notifications('huaxing',ACTOR,{'eventIds':[e['eventId']]})
 assert not sheet.reversal_notifications('huaxing',ACTOR)['items'];assert sheet.reversal_notifications('huaxing',other)['items']==data
 assert read(r)['lastReversal']['eventId']==e['eventId'];assert len([x for x in sheet.audit('huaxing',r['id'])['items'] if x['action']=='revoke'])==1
 r=command(r)['results'][0]['item'];r=command(r,'revoke')['results'][0]['item'];assert len(sheet.reversal_notifications('huaxing',ACTOR)['items'])==1

def test_return_resubmit_complete_evidence_no_duplicates(db):
 r=submitted(db);initial=deepcopy(r)
 with sheet.store() as c:old_submission=c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]
 patch=dict(revision=r['revision'],result=r['result'],remark=r['remark'],firstResponsible='甲',secondResponsible='乙',customerRequirements='包装与标签完整\n保留照片',shipDate='2026-12-23')
 r=sheet.save('huaxing',r['id'],patch,ACTOR,review=True)
 assert read(r)['shipDate']=='2026-12-23' and read(r)['customerRequirements']==patch['customerRequirements']
 body={'revision':r['revision'],'requestKey':uuid4().hex};out=sheet.return_to_inspection('huaxing',r['id'],body,ACTOR);r=out['item']
 assert r['reviewState']=='returned_to_inspection' and sheet.workbench_items([r])==[r]
 assert r['photos']==initial['photos'] and r['sourceKey']==initial['sourceKey'] and r['submittedAt']==initial['submittedAt']
 with sheet.store() as c:assert c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]==old_submission
 again=sheet.return_to_inspection('huaxing',r['id'],body,ACTOR);assert again['replayed'] and again['eventId']==out['eventId']
 assert wf.sources(db,'huaxing')['items'][0]['tasks'][0]['state']=='returned'
 with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='wrong page'),ACTOR,review=True)
 r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='FAIL',remark='重新验货备注',improvement='重检'),ACTOR);r=photo(r,'blue')
 r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR);assert r['reviewState']=='pending' and not sheet.workbench_items([r])
 r=command(r)['results'][0]['item'];report=summary.detail('huaxing',summary.listing('huaxing',{})['items'][0]['id'])
 assert len(report['photos'])==2 and report['firstResponsible']=='甲' and report['shipDate']=='2026-12-23' and report['result']=='FAIL'
 events=sheet.audit('huaxing',r['id'])['items'];assert next(e for e in events if e['action']=='submit')['changes']['previousSubmissionSnapshot']==json.loads(old_submission);assert len([e for e in events if e['action']=='return-to-inspection'])==1 and len([e for e in events if e['action']=='submit'])==2
 with sheet.store() as c:
  assert c.execute('SELECT count(*) FROM entries').fetchone()[0]==1
  snapshots=[json.loads(e[0]) for e in c.execute("SELECT snapshot FROM changes WHERE entry_id=? AND action='submit' ORDER BY id",(r['id'],))]
  assert snapshots[0]['remark']==initial['remark'] and len(snapshots[0]['photos'])==1 and snapshots[1]['remark']=='重新验货备注'
 assert not sheet.reversal_notifications('huaxing',ACTOR)['items']

def test_invalid_stale_cancelled_cross_factory_and_locked_edits(db):
 r=submitted(db);body={'revision':r['revision'],'requestKey':uuid4().hex}
 for factory,payload,sources in [('huakang-a',body,None),('huaxing',{**body,'revision':-1},None),('huaxing',body,[{'id':r['sourceId'],'sourceStatus':'cancelled'}])]:
  with pytest.raises(HTTPException):sheet.return_to_inspection(factory,r['id'],payload,ACTOR,sources)
 assert read(r)['reviewState']=='pending'
 for value in ['2026-02-30','11/03/2026']:
  with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='',shipDate=value),ACTOR,review=True)
 r=command(r)['results'][0]['item']
 with pytest.raises(HTTPException):sheet.return_to_inspection('huaxing',r['id'],{'revision':r['revision'],'requestKey':uuid4().hex},ACTOR)
 with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='',customerRequirements='blocked'),ACTOR,review=True)

def test_return_transaction_failure_rolls_back_event_and_state(db,monkeypatch):
 r=submitted(db);before=read(r);history=sheet.audit('huaxing',r['id']);original=sheet.changed
 def failure(*args,**kwargs):
  original(*args,**kwargs);raise RuntimeError('simulated database write failure')
 monkeypatch.setattr(sheet,'changed',failure)
 with pytest.raises(RuntimeError):sheet.return_to_inspection('huaxing',r['id'],{'revision':r['revision'],'requestKey':uuid4().hex},ACTOR)
 assert read(r)==before and sheet.audit('huaxing',r['id'])==history

def test_concurrent_duplicate_return_creates_one_event(db):
 from concurrent.futures import ThreadPoolExecutor
 r=submitted(db);body={'revision':r['revision'],'requestKey':uuid4().hex}
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(sheet.return_to_inspection,'huaxing',r['id'],body,ACTOR) for _ in range(2)]
  results=[f.result() for f in futures]
 assert results[0]['eventId']==results[1]['eventId']
 assert sum(x['replayed'] for x in results)==1
 assert len([x for x in sheet.audit('huaxing',r['id'])['items'] if x['action']=='return-to-inspection'])==1
 with pytest.raises(HTTPException):sheet.return_to_inspection('huaxing',r['id'],body,dict(ACTOR,id='someone-else'))

def test_multiple_unseen_reversals_are_all_included(db):
 rows=[]
 for n in [1,2,3]:
  item(db,n);r=save(next(r for r in entries(db) if r['productNo']=='ITEM-'+str(n)));r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR);r=command(r)['results'][0]['item'];r=command(r,'revoke','理由'+str(n))['results'][0]['item'];rows.append(r)
 events=sheet.reversal_notifications('huaxing',ACTOR)['items'];assert {e['entryId'] for e in events}=={r['id'] for r in rows};assert len(events)==3
 sheet.reversal_notifications('huakang-a',ACTOR,{'eventIds':[e['eventId'] for e in events]})
 assert len(sheet.reversal_notifications('huaxing',ACTOR)['items'])==3
 sheet.reversal_notifications('huaxing',ACTOR,{'eventIds':[e['eventId'] for e in events]});assert not sheet.reversal_notifications('huaxing',ACTOR)['items']

def test_review_order_supplements_persist_without_rewriting_source(db):
 r=submitted(db)
 # Old entry with a captured upstream order and no review supplement.
 with sheet.store(True) as c:
  base=json.loads(sheet.get(c,'huaxing',r['id'])['base'])
  base['sourceRecord'].update(contractNo='SRC-001',customerCode='0007',shippedQuantity=0)
  c.execute('UPDATE entries SET base=? WHERE id=?',(wf.dump(base),r['id']))
  original_base=wf.dump(base)
 r=read(r);original_source=deepcopy(r['sourceRecord'])
 assert (r['contractNo'],r['customerCode'],r['shippedQuantity'])==('SRC-001','0007','0')
 with sheet.store() as c:original_snapshot=c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]
 def patch(row,**values):return dict(revision=row['revision'],result=row['result'],remark=row['remark'],**values)
 values=dict(contractNo='001-TEST',customerCode='00042',shippedQuantity='12.5000')
 r=sheet.save('huaxing',r['id'],patch(r,**values),ACTOR,review=True)
 persisted=read(r)
 for k,v in values.items():assert persisted[k]==v
 assert persisted['sourceRecord']==original_source
 audit=sheet.audit('huaxing',r['id'])['items'][0]
 assert audit['changes']['customerCode']=={'before':'0007','after':'00042'}
 with sheet.store() as c:
  assert sheet.get(c,'huaxing',r['id'])['base']==original_base
  assert c.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0]==original_snapshot
 for factory,review,payload in [('huakang-a',True,patch(r,**values)),('huaxing',False,patch(r,**values)),('huaxing',True,{**patch(r,**values),'revision':-1})]:
  with pytest.raises(HTTPException):sheet.save(factory,r['id'],payload,ACTOR,review=review)
 for bad in ['-1','NaN','Infinity','1000000000001','1.00001','abc']:
  with pytest.raises(HTTPException) as error:sheet.save('huaxing',r['id'],patch(r,shippedQuantity=bad),ACTOR,review=True)
  assert error.value.status_code==422
 for key in ('contractNo','customerCode'):
  for bad in ['x'*201,'line1\nline2',123]:
   with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],patch(r,**{key:bad}),ACTOR,review=True)
 assert read(r)==persisted
 r=sheet.save('huaxing',r['id'],patch(r,contractNo='',shippedQuantity='0'),ACTOR,review=True)
 assert read(r)['contractNo']=='' and read(r)['shippedQuantity']=='0'
 r=command(r)['results'][0]['item']
 report=summary.detail('huaxing',summary.listing('huaxing',{})['items'][0]['id'])
 assert (report['contractNo'],report['customerCode'],report['shippedQuantity'])==('','00042','0')
 assert report['sourceRecord']==original_source
 with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],patch(r,contractNo='blocked'),ACTOR,review=True)
 r=command(r,'revoke')['results'][0]['item'];r=sheet.save('huaxing',r['id'],patch(r,shippedQuantity=''),ACTOR,review=True)
 assert read(r)['shippedQuantity']==''
 r=command(r)['results'][0]['item'];report=summary.detail('huaxing',summary.listing('huaxing',{})['items'][0]['id'])
 assert report['shippedQuantity']=='' and report['sourceRecord']==original_source
