from copy import deepcopy
from io import BytesIO
import base64,json
from uuid import uuid4
import pytest
from PIL import Image
from fastapi import HTTPException
from app.services import qc_workflow as wf,qc_inspection_sheet as sheet,qc_inspection_summary as summary
from test_customer_order_ledger import engine,db
from test_qc_workflow import ACTOR
@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):monkeypatch.setattr(wf.settings,'qc_department_data_dir',str(tmp_path/'companies'))
def schedule(n,factory='huaxing'):
 return wf.create_schedule(factory,{'requestKey':'manual-test-'+str(n),'row':dict(dateFrom='2026-11-03',dateTo='',customer='ZURU',poNo='TEST-PO',country='UK',productNo='ITEM-'+str(n),productName='产品',quantity='100',unitsPerCarton='10',cartonCount='10',production='生产一部',agency='行验',customerPo='CP-001',remark='原始备注')},ACTOR)
def push(db,rows,key=None):
 return wf.create_tasks(db,'huaxing',{'requestKey':key or uuid4().hex,'items':[dict(sourceId=r['id'],sourceRevision=1,method='internal',batch='首验',plannedDate=r['dateFrom'],plannedQuantity=r['quantity']) for r in rows]},ACTOR)
def entries(db):return sheet.sync('huaxing',sheet.candidates('huaxing',[],wf.list_tasks(db,'huaxing')['items'],wf.sources(db,'huaxing')['items']))['items']
def test_manual_5_plus_3_retry_factory_and_history(db):
 rows=[schedule(i) for i in range(8)];other=schedule(99,'huadeng')
 assert schedule(0)['id']==rows[0]['id']
 push(db,rows[:5],'lost-response-key');before=entries(db);assert len(before)==5
 first=before[0];saved=sheet.save('huaxing',first['id'],dict(revision=first['revision'],result='PASS',remark='保留',improvement='措施'),ACTOR)
 before=entries(db);push(db,rows[5:]);assert len(entries(db))==8
 push(db,rows[:5],'lost-response-key');push(db,rows);assert len(entries(db))==8
 after={r['id']:r for r in entries(db)}
 for r in before:assert after[r['id']]==r
 with pytest.raises(HTTPException):push(db,[other])
 assert len(wf.sources(db,'huadeng')['items'])==1
 assert len(wf.sources(db,'huaxing')['items'])==8

def test_submit_full_snapshot_photos_time_lock_and_read_recovery(db):
 row=schedule(1);push(db,[row]);item=entries(db)[0]
 item=sheet.save('huaxing',item['id'],dict(revision=item['revision'],result='PENDING',remark='备注\n长文本',improvement='改善包装\n复核标签'),ACTOR)
 for color in ['red','blue']:
  f=BytesIO();Image.new('RGB',(12,12),color).save(f,'PNG')
  item=sheet.add_photo('huaxing',item['id'],dict(revision=item['revision'],name=color+'.png',content=base64.b64encode(f.getvalue()).decode(),requestKey=uuid4().hex),ACTOR)
 saved=sheet.submit('huaxing',item['id'],{'revision':item['revision']},ACTOR)
 assert saved['submittedAt'] and saved['improvement']=='改善包装\n复核标签'
 assert sheet.submit('huaxing',item['id'],{'revision':item['revision']},ACTOR)['submittedAt']==saved['submittedAt']
 refreshed=entries(db)[0];assert refreshed['revision']==saved['revision'] and refreshed['completion']=='待审核'
 assert summary.listing('huaxing',{})['total']==0
 saved=sheet.review_batch('huaxing','confirm',dict(entries=[dict(id=saved['id'],revision=saved['revision'])],requestKey=uuid4().hex),ACTOR)['results'][0]['item']
 result=summary.listing('huaxing',{});assert result['total']==1
 detail=summary.detail('huaxing',result['items'][0]['id']);assert detail['status']=='approved' and detail['submittedAt']==saved['submittedAt']
 assert detail['sourceNote']=='原始备注' and detail['customerPo']=='CP-001' and detail['country']=='UK'
 assert len(detail['photos'])==2 and detail['remark']=='备注\n长文本' and detail['improvement']=='改善包装\n复核标签'
 for p in detail['photos']:assert Image.open(BytesIO(sheet.read_photo('huaxing',item['id'],p['id']))).size==(12,12)
 assert summary.listing('huaxing',{})['items']==result['items']
 assert summary.listing('huadeng',{})['total']==0
 with pytest.raises(HTTPException):sheet.save('huaxing',item['id'],dict(revision=saved['revision'],result='FAIL',remark='覆盖'),ACTOR)
 with pytest.raises(HTTPException):sheet.remove_photo('huaxing',item['id'],dict(revision=saved['revision'],photoId=detail['photos'][0]['id']),ACTOR)

def test_invalid_schedule_does_not_insert():
 r=schedule(1)['input'];r['dateFrom']='2026-02-30'
 with pytest.raises(HTTPException):wf.create_schedule('huaxing',{'requestKey':uuid4().hex,'row':r},ACTOR)
 with wf.store() as c:assert c.execute('select count(*) from manual_schedules').fetchone()[0]==1

def test_packaging_text_and_retired_sources_cannot_reappear(db):
 from test_customer_order_ledger import ingest
 row=schedule(1)['input'];row['unitsPerCarton']='6P/12'
 assert wf.create_schedule('huaxing',{'requestKey':'packing-text','row':row},ACTOR)['unitsPerCarton']=='6P/12'
 line=ingest(db);original=deepcopy(line.data)
 with wf.store(True) as c:c.execute('INSERT INTO retired_test_sources VALUES(?,?,?,?)',('huaxing',line.id,wf.now(),'authorized test cleanup'))
 assert line.id not in [r['id'] for r in wf.sources(db,'huaxing')['items']]
 with pytest.raises(HTTPException):wf.create_tasks(db,'huaxing',{'requestKey':uuid4().hex,'items':[dict(sourceId=line.id,sourceRevision=line.revision,method='internal',batch='首验',plannedDate='2026-11-03',plannedQuantity='1')]},ACTOR)
 assert line.data==original

def test_http_manual_submit_actor_permissions_and_factory(db,monkeypatch):
 from dataclasses import replace
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 import httpx
 from app.api import qc_department as gateway
 from app.db import get_db
 from app.services import auth
 from app.services.auth import get_current_user
 from test_qc_workflow import qc_user
 monkeypatch.setattr(auth,'add_auth_audit',lambda *a,**k:None)
 async def upstream(*args):return httpx.Response(200,json={'records':[]})
 monkeypatch.setattr(gateway,'upstream',upstream)
 app=FastAPI();app.include_router(gateway.router);current=[qc_user()]
 app.dependency_overrides[get_current_user]=lambda:current[0];app.dependency_overrides[get_db]=lambda:db
 with TestClient(app) as client:
  base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']+'api/'
  assert client.get(base+'../qc-inspection-audit.js').status_code==200
  asset=client.get(base+'../qc-photo-paste.js');assert asset.status_code==200
  assert 'QcPhotoPaste' in asset.text
  assert client.get(base+'../qc-photo-paste.test.js').status_code==404
  body={'requestKey':'http-manual-one','row':schedule(88)['input']}
  r=client.post(base+'workflow/schedules',json=body);assert r.status_code==200,r.text
  row=r.json();assert client.post(base+'workflow/schedules',json=body).json()['id']==row['id']
  assert client.post(base+'workflow/schedules',json=body,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
  pushbody={'requestKey':'http-push-one','items':[dict(sourceId=row['id'],sourceRevision=1,method='internal',batch='首验',plannedDate=row['dateFrom'],plannedQuantity=row['quantity'])]}
  assert client.post(base+'workflow/tasks',json=pushbody).status_code==200
  item=client.get(base+'inspection-sheet/entries').json()['items'][0]
  url=base+'inspection-sheet/entries/'+item['id']
  r=client.post(url+'/save',json=dict(revision=item['revision'],result='FAIL',remark='HTTP备注',improvement='HTTP改进'));assert r.status_code==200,r.text
  r=client.post(url+'/submit',json={'revision':r.json()['revision']});assert r.status_code==200 and r.json()['submittedAt']
  assert client.get(base+'inspection-sheet/entries').json()['items']==[]
  assert client.get(base+'inspection-summary/records').json()['total']==0
  pending=client.get(base+'inspection-sheet/review/entries').json()['items'][0]
  confirmation=client.post(base+'inspection-sheet/review/confirm',json={'entries':[dict(id=pending['id'],revision=pending['revision'])],'requestKey':uuid4().hex})
  assert confirmation.status_code==200 and confirmation.json()['succeeded']==1
  assert 'qc_inspection:review' not in current[0].permissions
  audit=client.get(base+'inspection-sheet/entries/'+pending['id']+'/audit').json()['items']
  assert audit[0]['actor']['id']==current[0].id and audit[0]['location']=='审核中心 · 待审核'
  approved=confirmation.json()['results'][0]['item']
  assert client.get(base+'inspection-sheet/entries').json()['items']==[]
  listing=client.get(base+'inspection-summary/records').json();assert listing['total']==1 and listing['items'][0]['status']=='approved'
  with summary.store() as c:changes=c.execute('select count(*) from changes').fetchone()[0]
  client.get(base+'inspection-summary/records');client.get(base+'inspection-summary/records')
  with summary.store() as c:assert c.execute('select count(*) from changes').fetchone()[0]==changes
  assert client.post(url.replace('/huaxing/','/huadeng/')+'/submit',json={'revision':r.json()['revision']}).status_code==403
  current[0]=replace(current[0],permissions=frozenset({'qc_inspection:read'}),grants=())
  assert client.post(base+'workflow/schedules',json=body).status_code==403
  assert client.post(url+'/submit',json={'revision':r.json()['revision']}).status_code==403
  assert client.post(base+'inspection-sheet/review/revoke',json={'entries':[dict(id=pending['id'],revision=approved['revision'])],'requestKey':uuid4().hex}).status_code==403
