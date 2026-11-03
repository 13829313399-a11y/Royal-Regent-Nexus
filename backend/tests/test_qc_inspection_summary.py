"""Actual SQLite/workflow/OOXML tests; no production data or mocked persistence."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from uuid import uuid4
import base64
import json
import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from app.services import qc_inspection_summary as s, qc_cumulative as c, qc_inspection_sheet as sheet, qc_workflow as wf
from test_customer_order_ledger import engine, db, ingest
from test_qc_workflow import create, save, command, ACTOR, qc_user
from test_qc_cumulative import request

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(s.settings,'qc_department_data_dir',str(tmp_path/'companies'))


def entry(db,t):
    return sheet.sync('huaxing',sheet.candidates('huaxing',[],[t],wf.sources(db,'huaxing')['items']))['items'][0]


def merged(db,approve=True):
    t=save(db,create(db),remark='Inspection passed.')
    t=command(db,t,'submit')
    if approve:t=command(db,t,'approve')
    row=entry(db,t)
    c.operate('huaxing','operator',request([row]),[row])
    return t,row


def history(year=2024,count=3,duplicate=False):
    wb=Workbook();ws=wb.active;ws.title='ZURU行验货'
    ws.append([datetime(year,2,29 if year%4==0 else 28)])
    ws.append(c.writer.HEAD1)
    for n in range(count):
        ws.append(['ZURU','000001' if duplicate else f'000{n:03}','USA','00042','Test',12,6,2,['PASS','FAIL','PENDING'][n%3] if not duplicate else 'PASS','=Literal remark'])
        ws.cell(ws.max_row,10).data_type='s'
    buf=BytesIO();wb.save(buf);return buf.getvalue()


def preview(content=None):
    return s.preview('huaxing','operator',{'filename':'历史测试副本.xlsx','content':base64.b64encode(content or history()).decode(),'mime':''})


def test_approval_and_durable_merge_required_recovery_idempotency(db):
    t,row=merged(db,False)
    first=s.listing('huaxing',{});assert first['total']==1 and first['items'][0]['status']=='unverified'
    assert first['items'][0]['archivedAt']==''
    t=command(db,t,'approve')
    archived=s.listing('huaxing',{});item=archived['items'][0]
    assert item['status']=='archived' and item['inspectionDate']=='2026-10-26'
    assert item['inspectionType']=='行验' and item['stockNo']=='' and item['approvalEventId']
    assert s.listing('huaxing',{})['items']==archived['items']
    assert s.detail('huaxing',item['id'])['approvalSnapshot']['state']=='approved'
    assert s.listing('huadeng',{})['total']==0
    with pytest.raises(HTTPException):s.detail('huadeng',item['id'])


def test_approved_before_merge_and_failed_merge_cannot_archive(db,monkeypatch):
    t=command(db,command(db,save(db,create(db)),'submit'),'approve');row=entry(db,t)
    assert s.listing('huaxing',{})['total']==0
    original=c.writer.build
    def fail(*args):raise RuntimeError('disk failure')
    monkeypatch.setattr(c.writer,'build',fail)
    with pytest.raises(HTTPException):c.operate('huaxing','operator',request([row]),[row])
    assert s.listing('huaxing',{})['total']==0
    assert len(c.pending_items('huaxing',[row]))==1
    monkeypatch.setattr(c.writer,'build',original)
    c.operate('huaxing','operator',request([row]),[row])
    assert s.listing('huaxing',{})['items'][0]['status']=='archived'


def test_changed_result_reopen_and_undo_remove_formal_qualification(db):
    t,row=merged(db);a=s.listing('huaxing',{})['items'][0]
    assert a['status']=='archived'
    with pytest.raises(HTTPException) as locked:
        sheet.save('huaxing',row['id'],{'revision':row['revision'],'result':'FAIL','remark':'Changed'},ACTOR)
    assert locked.value.status_code==409
    assert s.listing('huaxing',{})['items'][0]['status']=='archived'
    command(db,t,'reopen','核对报告')
    assert s.listing('huaxing',{})['items'][0]['status']=='unverified'
    assert s.listing('huaxing',{})['items'][0]['id']==a['id']


def test_history_preview_commit_repeated_file_retains_real_duplicates_rollback():
    p=preview(history(2024,2,True));assert p['total']==2 and p['new']==2
    assert s.listing('huaxing',{})['total']==0
    assert s.commit_history('huaxing','operator',p['id'])['count']==2
    records=s.listing('huaxing',{})['items'];assert len({r['id'] for r in records})==2
    assert all(r['status']=='unverified' and r['inspectionType']=='待确认' and not r['archivedAt'] for r in records)
    again=preview(history(2024,2,True));assert again['duplicate']==2 and again['new']==0
    assert s.commit_history('huaxing','operator',again['id'])['count']==0
    assert s.commit_history('huaxing','operator',p['id'])['status']=='unchanged'
    assert s.rollback_history('huaxing',p['id'])['count']==2
    assert s.listing('huaxing',{})['total']==0
    with s.store() as conn:assert bytes(conn.execute('SELECT original FROM batches WHERE id=?',(p['id'],)).fetchone()[0])
    new=preview(history(2024,2,True));s.commit_history('huaxing','operator',new['id'])
    assert {r['id'] for r in s.listing('huaxing',{})['items']}=={r['id'] for r in records}


def test_cross_document_ambiguity_is_held_not_silently_merged():
    a=preview(history(2024,2));s.commit_history('huaxing','operator',a['id'])
    b=preview(history(2024,3));assert b['conflict']==2 and b['new']==1
    result=s.commit_history('huaxing','operator',b['id']);assert result['count']==1 and result['conflict']==2
    assert s.listing('huaxing',{})['total']==3


def test_year_month_day_leap_unknown_date_stable_pagination_and_full_export():
    for year,count in [(2024,65),(2025,2),(2026,2)]:
        p=preview(history(year,count));s.commit_history('huaxing','operator',p['id'])
    all_data=s.listing('huaxing',{});assert all_data['total']==69 and all_data['years']==['2024','2025','2026']
    assert len(all_data['items'])==30
    f={'year':'2024','month':'2','day':'29','search':'00042','pageSize':'10'}
    assert s.listing('huaxing',f)['total']==65
    ids=[r['id'] for r in s.listing('huaxing',{},all_rows=True)['items']]
    assert ids==[r['id'] for r in s.listing('huaxing',{},all_rows=True)['items']]
    raw,name=s.export_excel('huaxing',f);wb=load_workbook(BytesIO(raw))
    assert wb['验货汇总明细'].max_row==66 and '2024-02-29' in name
    assert wb['验货汇总明细']['D2'].value=='00042' and wb['验货汇总明细']['I2'].data_type=='s'
    assert wb['验货汇总明细']['I2'].value=='=Literal remark'
    assert s.listing('huaxing',{'year':'2025','month':'3'})['total']==0
    assert s.listing('huaxing',{'search':"%' OR 1=1 --"})['total']==0
    for invalid in ({'year':'2025','month':'2','day':'29'},{'month':'2'},{'day':'1'},{'year':'2024 OR 1=1'}):
        with pytest.raises(HTTPException):s.listing('huaxing',invalid)
    with pytest.raises(HTTPException):s.export_excel('huaxing',{'year':'2020'})
    assert s.business_date('2023-12-31T18:00:00Z')=='2024-01-01'


def test_preview_actor_scope_corrupt_file_and_no_source_mutation():
    before=c.template('huaxing');p=preview()
    with pytest.raises(HTTPException):s.commit_history('huaxing','another',p['id'])
    with pytest.raises(HTTPException):s.batch_detail('huadeng',p['id'])
    with pytest.raises(HTTPException):preview(b'broken workbook')
    assert c.template('huaxing')==before and s.listing('huaxing',{})['total']==0


def test_http_read_export_import_permissions_factory_and_actor(db,monkeypatch):
    from dataclasses import replace
    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import qc_department as gateway
    from app.db import get_db
    from app.services import auth
    from app.services.auth import get_current_user
    monkeypatch.setattr(auth,'add_auth_audit',lambda *a,**k:None)
    async def healthy(*args):return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(gateway,'upstream',healthy)
    app=FastAPI();app.include_router(gateway.router);current=[qc_user()]
    app.dependency_overrides[get_current_user]=lambda:current[0]
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        assert client.get(base+'api/inspection-summary/records').status_code==200
        assert client.post(base+'api/inspection-summary/history/preview',json={}).status_code==403
        assert client.get('/api/qc-department/huadeng/api/inspection-summary/records').status_code==403
        user=current[0];codes=user.permissions|{'qc_inspection:customer_manage'}
        current[0]=replace(user,permissions=codes,grants=tuple(replace(g,permissions=codes) for g in user.grants))
        payload={'filename':'test.xlsx','mime':'','content':base64.b64encode(history()).decode()}
        assert client.post(base+'api/inspection-summary/history/preview',json=payload,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
        response=client.post(base+'api/inspection-summary/history/preview',json=payload);assert response.status_code==200,response.text
        batch=response.json()['id'];assert client.post(base+'api/inspection-summary/history/'+batch+'/commit',json={}).status_code==200
        head=client.head(base+'api/inspection-summary/export');assert head.status_code==200 and int(head.headers['content-length'])>0 and not head.content
        output=client.get(base+'api/inspection-summary/export');assert output.status_code==200 and load_workbook(BytesIO(output.content)).active.max_row==4
        codes=current[0].permissions-{'qc_inspection:report_export'}
        current[0]=replace(current[0],permissions=codes,grants=tuple(replace(g,permissions=codes) for g in current[0].grants))
        assert client.get(base+'api/inspection-summary/export').status_code==403
        assert client.get(base+'api/inspection-summary/records').status_code==200


def test_same_source_multiple_actual_inspections_keep_distinct_identity(db):
    line=ingest(db);tasks=[]
    for batch in ['首验','二次验货']:
        task=create(db,line=line,batch=batch,key=uuid4().hex)
        tasks.append(command(db,command(db,save(db,task),'submit'),'approve'))
    rows=sheet.sync('huaxing',sheet.candidates('huaxing',[],tasks,wf.sources(db,'huaxing')['items']))['items']
    c.operate('huaxing','operator',request(rows),rows)
    items=s.listing('huaxing',{})['items'];assert len(items)==2 and all(i['status']=='archived' for i in items)
    assert items[0]['inspectionDate']==items[1]['inspectionDate'] and items[0]['productNo']==items[1]['productNo']
    assert items[0]['id']!=items[1]['id']



def test_changed_cross_file_record_is_held_instead_of_duplicate_history():
    a=preview(history(2024,1));s.commit_history('huaxing','operator',a['id'])
    wb=load_workbook(BytesIO(history(2024,1)));wb.active['I3']='FAIL';buf=BytesIO();wb.save(buf)
    b=preview(buf.getvalue());assert b['new']==0 and b['conflict']==1
    assert s.commit_history('huaxing','operator',b['id'])['count']==0
    assert s.listing('huaxing',{})['total']==1



def test_vertical_merges_preserve_customer_order_result_and_notes_without_guessing():
    wb=load_workbook(BytesIO(history(2024,2)));ws=wb.active;ws['I3']='FAIL';ws['D4']='00043'
    for column in ['A','B','I','J']:ws.merge_cells(f'{column}3:{column}4')
    stream=BytesIO();wb.save(stream);p=preview(stream.getvalue())
    assert p['total']==2
    s.commit_history('huaxing','operator',p['id'])
    items=s.listing('huaxing',{})['items']
    assert all(r['customer']=='ZURU' and r['poNo']=='000000' and r['result']=='FAIL' and r['remark']=='=Literal remark' for r in items)
    assert all(r['sharedSourceCells']['1']['anchor']=='A3' for r in items)
    assert any(r['originalCells'].get('1','')=='' for r in items)


def test_cleared_workbook_projection_stays_hidden_without_changing_sources(db):
    task, row = merged(db)
    item = s.listing('huaxing', {})['items'][0]
    with c.store() as conn:
        before = [tuple(r) for r in conn.execute('SELECT * FROM versions')]
    with s.store(True) as conn:
        conn.execute('UPDATE records SET active=0 WHERE factory=? AND id=?', ('huaxing', item['id']))
    assert s.listing('huaxing', {})['total'] == 0
    assert s.listing('huaxing', {})['total'] == 0
    with s.store() as conn:
        saved = conn.execute('SELECT payload,active FROM records WHERE id=?', (item['id'],)).fetchone()
        assert not saved['active'] and json.loads(saved['payload'])['entryId'] == row['id']
    with c.store() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM versions')] == before
    assert wf.sources(db, 'huaxing')['items'][0]['tasks'][0]['id'] == task['id']
