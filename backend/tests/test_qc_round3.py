"""Round 3 uses real SQLite, attached summary transactions and native workbook XML."""
from copy import deepcopy
from io import BytesIO
import json,sqlite3
from uuid import uuid4
import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from app.services import qc_inspection_sheet as sheet,qc_inspection_summary as summary,qc_workflow as wf
from app.services.qc_inspection_results import RESULTS, ALLOWED_INSPECTION_RESULTS
from test_customer_order_ledger import engine,db
from test_qc_self_review import isolated,item,photo,command
from test_qc_workflow import ACTOR

@pytest.mark.parametrize('result',ALLOWED_INSPECTION_RESULTS)
def test_every_legal_result_review_photo_and_summary(db,result):
 r=item(db);r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result=result,remark='原样结论 '+result),ACTOR)
 r=photo(r,'red');original=deepcopy(r['photos']);r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
 r=command(r)['results'][0]['item'];assert r['reviewState']=='approved' and r['result']==result
 detail=summary.detail('huaxing',summary.listing('huaxing',{})['items'][0]['id'])
 assert detail['photos']==original and detail['result']==result
 for p in detail['photos']:assert sheet.read_photo('huaxing',r['id'],p['id'])

@pytest.mark.parametrize('result',['','UNKNOWN','lg','Pending',None])
def test_invalid_or_empty_cannot_confirm(db,result):
 r=item(db)
 if result!='':
  with pytest.raises(HTTPException):sheet.save('huaxing',r['id'],dict(revision=r['revision'],result=result,remark=''),ACTOR)
 with pytest.raises(HTTPException):sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
 # Independently protect a corrupt/old pending row without a result.
 with sheet.store(True) as c:c.execute("UPDATE entry_details SET review_state='pending',flow_version=2 WHERE entry_id=?",(r['id'],))
 assert command(r)['failed']==1 and summary.listing('huaxing',{})['total']==0

def test_legacy_explicit_revoke_preserves_original_then_reconfirms(db):
 r=item(db);r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='原始备注'),ACTOR);r=photo(r,'blue')
 legacy=dict(r,submittedAt='2026-11-01T17:05:00+00:00',submittedBy='历史操作人');snapshot=wf.dump(legacy)
 with sheet.store(True) as c:c.execute("UPDATE entry_details SET submitted_at=?,submitted_snapshot=?,flow_version=0 WHERE entry_id=?",(legacy['submittedAt'],snapshot,r['id']))
 before=summary.listing('huaxing',{})['items'][0];assert before['status']=='completed'
 key=uuid4().hex;out=command(r,'revoke','第一行\n第二行',key);assert out['succeeded']==1
 updated=out['results'][0]['item'];assert updated['flowVersion']==2 and updated['reviewState']=='pending' and not updated['legacyCompleted']
 assert command(r,'revoke','第一行\n第二行',key)['succeeded']==1 and summary.listing('huaxing',{})['total']==0
 with sheet.store() as c:
  saved=c.execute('SELECT * FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()
  assert saved['submitted_snapshot']==snapshot and saved['submitted_at']==legacy['submittedAt'] and saved['approved_snapshot'] and saved['confirmed_at']==''
 updated=sheet.save('huaxing',r['id'],dict(revision=updated['revision'],result='LG',remark='再确认'),ACTOR,review=True)
 assert command(updated)['succeeded']==1
 detail=summary.detail('huaxing',before['id']);assert detail['result']=='LG' and detail['photos']==r['photos'] and detail['submittedAt']==legacy['submittedAt']
 assert any(x['record']['result']=='PASS' for x in detail['archiveHistory'])
 events=sheet.audit('huaxing',r['id'])['items'];revokes=[e for e in events if e['action']=='revoke'];assert len(revokes)==1 and revokes[0]['changes']['reason']=='第一行\n第二行'

def test_photo_fallback_is_stable_entry_scoped_and_factory_protected(db):
 r=item(db);r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='LG',remark=''),ACTOR);r=photo(r,'blue')
 r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR);r=command(r)['results'][0]['item']
 identity=summary.listing('huaxing',{})['items'][0]['id']
 with summary.store(True) as c:
  payload=json.loads(c.execute('SELECT payload FROM records WHERE id=?',(identity,)).fetchone()[0]);payload['photos']=[]
  c.execute('UPDATE records SET payload=? WHERE id=?',(wf.dump(payload),identity))
 assert summary.detail('huaxing',identity)['photos']==r['photos']
 with pytest.raises(HTTPException):summary.detail('huadeng',identity)
 with pytest.raises(HTTPException):sheet.read_photo('huadeng',r['id'],r['photos'][0]['id'])
 with pytest.raises(HTTPException):sheet.read_photo('huaxing','another-entry',r['photos'][0]['id'])

def test_result_check_migration_keeps_all_rows_children_and_audit(db):
 r=item(db);r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='保留'),ACTOR);r=photo(r,'red');r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
 path=sheet.settings.qc_department_data_dir+'/_inspection_sheet/inspections.sqlite3';c=sqlite3.connect(path)
 tables=['entries','entry_details','photos','changes'];before={t:c.execute('SELECT * FROM '+t).fetchall() for t in tables}
 c.execute('PRAGMA foreign_keys=OFF');c.execute('BEGIN')
 ddl=sheet.SCHEMA.split(';')[0].replace('IF NOT EXISTS entries','entries_previous').replace(",'REJ','COND','HOLD','LG'",'')
 c.execute(ddl);c.execute('INSERT INTO entries_previous SELECT * FROM entries');c.execute('DROP TABLE entries');c.execute('ALTER TABLE entries_previous RENAME TO entries');c.execute('CREATE INDEX preserved_entry_factory ON entries(factory)');c.commit();c.close()
 with sheet.store() as c:
  assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
  assert c.execute("SELECT 1 FROM sqlite_master WHERE name='preserved_entry_factory'").fetchone()
  assert {t:[tuple(x) for x in c.execute('SELECT * FROM '+t)] for t in tables}==before
  assert all("'"+value+"'" in c.execute("SELECT sql FROM sqlite_master WHERE name='entries'").fetchone()[0] for value in RESULTS)

def test_legacy_without_extension_row_revoke_is_persistent(db):
 r=item(db)
 with sheet.store(True) as c:
  base=json.loads(c.execute('SELECT base FROM entries WHERE id=?',(r['id'],)).fetchone()[0]);base['legacyReviewState']='approved'
  c.execute('UPDATE entries SET base=? WHERE id=?',(wf.dump(base),r['id']))
  c.execute('DELETE FROM entry_details WHERE entry_id=?',(r['id'],))
 out=command(r,'revoke');assert out['succeeded']==1
 with sheet.store() as c:
  restored=sheet.unpack(c,sheet.get(c,'huaxing',r['id']))
  assert restored['reviewState']=='pending' and restored['flowVersion']==2
  assert restored['submittedAt']=='' and restored['confirmedAt']==''
