"""Round-four contracts using temporary SQLite stores, never the daily DB."""
from copy import deepcopy
from uuid import uuid4
import pytest
from fastapi import HTTPException
from test_qc_inspection_sheet import isolated, seed, save, photo, ACTOR
from app.services import qc_inspection_sheet as sheet
from app.services import qc_workflow as workflow


def test_workbench_is_unsubmitted_not_workbook_pending():
    rows=[{'id':'draft'}, {'id':'legacy-draft','flowVersion':0},
          {'id':'legacy-done','legacyCompleted':True},
          {'id':'sent','submittedAt':'2026-11-02T00:00:00Z'},
          {'id':'old-pending','reviewState':'pending'}, {'id':'approved','reviewState':'approved'}]
    before=deepcopy(rows)
    assert [r['id'] for r in sheet.workbench_items(rows)]==['draft','legacy-draft']
    assert rows==before


def test_submit_failure_keeps_row_success_and_retry_preserve_photos():
    a,b,c=seed()
    with pytest.raises(HTTPException):sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)
    with sheet.store() as conn:assert sheet.workbench_items([sheet.unpack(conn,sheet.get(conn,'huaxing',a['id']))])
    a=save(a,'PASS');a,_=photo(a);submitted=sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)
    assert submitted['reviewState']=='pending' and not sheet.workbench_items([submitted])
    assert sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)==submitted
    with sheet.store() as conn:
        assert conn.execute("SELECT count(*) FROM changes WHERE entry_id=? AND action='submit'",(a['id'],)).fetchone()[0]==1
        assert sheet.unpack(conn,sheet.get(conn,'huaxing',a['id']))['photos']==a['photos']


@pytest.mark.parametrize('result',['PASS','FAIL','PENDING','LG'])
def test_four_results_save_submit_and_confirm(result):
    a,*_=seed();a=save(a,result)
    a=sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)
    out=sheet.review_batch('huaxing','confirm',{'requestKey':uuid4().hex,'entries':[{'id':a['id'],'revision':a['revision']}]},ACTOR)
    assert out['succeeded']==1 and out['results'][0]['item']['result']==result


@pytest.mark.parametrize('result',['REJ','COND','HOLD','UNKNOWN'])
def test_new_values_rejected_historical_values_not_rewritten(result):
    a,*_=seed()
    with pytest.raises(HTTPException):save(a,result)
    if result=='UNKNOWN':return
    with sheet.store(True) as conn:
        conn.execute('UPDATE entries SET result=? WHERE id=?',(result,a['id']))
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',a['id']))['result']==result
    with pytest.raises(HTTPException):sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)
    with sheet.store(True) as conn:
        conn.execute("INSERT INTO entry_details(entry_id,flow_version,review_state) VALUES(?,2,'pending') ON CONFLICT(entry_id) DO UPDATE SET flow_version=2,review_state='pending'",(a['id'],))
    out=sheet.review_batch('huaxing','confirm',{'requestKey':uuid4().hex,'entries':[{'id':a['id'],'revision':a['revision']}]},ACTOR)
    assert out['failed']==1
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',a['id']))['result']==result


def review(row,action,reason='',key=None):
    return sheet.review_batch('huaxing',action,{'requestKey':key or uuid4().hex,'entries':[{'id':row['id'],'revision':row['revision']}],'reason':reason},ACTOR)


def test_reversal_receipt_persists_and_retry_keeps_original_event():
    a,*_=seed();a=save(a,'PASS');a=sheet.submit('huaxing',a['id'],{'revision':a['revision']},ACTOR)
    a=review(a,'confirm')['results'][0]['item'];original=a;key=uuid4().hex
    out=review(a,'revoke',key=key);first=out['results'][0]['reversal'];a=out['results'][0]['item']
    assert first==a['lastReversal'] and first['reason']=='' and first['actor']==ACTOR
    assert first['customer']==a['customer'] and first['poNo']==a['poNo'] and first['location']=='审核中心 · 已审核'
    assert first['at']==sheet.audit('huaxing',a['id'])['items'][0]['at']
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',a['id']))['lastReversal']==first
    a=review(a,'confirm')['results'][0]['item'];assert a['lastReversal']==first
    a=review(a,'revoke','检查标签\n再次核对')['results'][0]['item'];assert a['lastReversal']['reason']=='检查标签\n再次核对'
    retry=review(original,'revoke',key=key)['results'][0]
    assert retry['reversal']==first and retry['item']['lastReversal']==a['lastReversal']
    assert len([e for e in sheet.audit('huaxing',a['id'])['items'] if e['action']=='revoke'])==2


def test_partial_reversal_never_invents_receipt_for_failure():
    a,b,*_=seed();rows=[]
    for row in (a,b):
        row=save(row,'LG');row=sheet.submit('huaxing',row['id'],{'revision':row['revision']},ACTOR)
        rows.append(review(row,'confirm')['results'][0]['item'])
    out=sheet.review_batch('huaxing','revoke',{'requestKey':uuid4().hex,'reason':'检查照片','entries':[{'id':r['id'],'revision':r['revision']-i} for i,r in enumerate(rows)]},ACTOR)
    assert (out['succeeded'],out['failed'])==(1,1)
    assert out['results'][0]['reversal']['reason']=='检查照片' and 'reversal' not in out['results'][1]
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',b['id']))['reviewState']=='approved'


def test_legacy_result_cannot_bypass_workflow_submit_or_approval():
    record={'id':901,'status':'rejected','result':'REJ','client':'ZURU','productNo':'x','qty':10,'sampleQty':1,'inspDate':'2026-11-02','qc':'QC'}
    task=workflow.create_entry('huaxing',{'recordId':901},ACTOR,record,True)
    assert task['execution']['result']=='REJ' and task['legacyOriginal']['result']=='REJ'
    with workflow.store(True) as conn:
        import json
        payload=json.loads(conn.execute('SELECT payload FROM tasks WHERE id=?',(task['id'],)).fetchone()[0]);payload['methodConfirmed']=True
        conn.execute("UPDATE tasks SET state='draft',payload=? WHERE id=?",(workflow.dump(payload),task['id']))
    with pytest.raises(HTTPException):workflow.act(None,'huaxing',task['id'],'submit',{'revision':task['revision']},ACTOR)
    with workflow.store(True) as conn:conn.execute("UPDATE tasks SET state='pending' WHERE id=?",(task['id'],))
    with pytest.raises(HTTPException):workflow.act(None,'huaxing',task['id'],'approve',{'revision':task['revision'],'reason':''},ACTOR)
