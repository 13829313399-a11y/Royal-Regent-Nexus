"""Isolated Sales -> QC -> review journeys; never touch persistent user data."""
import base64
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import json
import httpx
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from test_customer_order_ledger import engine, db, ingest, preview
from app.api import qc_department as gateway
from app.db import get_db
from app.services import qc_workflow as wf
from app.services.auth import AuthContext, AuthGrantContext, get_current_user

ACTOR={'id':'qc-1','name':'验货员'}
SUPERVISOR={'id':'supervisor','name':'主管'}


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(wf.settings,'qc_department_data_dir',str(tmp_path/'companies'))


def create(db,method='internal',batch='首验',line=None,key='push-request-001'):
    line=line or ingest(db)
    return wf.create_tasks(db,'huaxing',{'requestKey':key,'items':[{'sourceId':line.id,'sourceRevision':line.revision,
        'method':method,'batch':batch,'plannedDate':'2026-10-26','plannedQuantity':'100'}]},ACTOR)['items'][0]


def fill(task,result='PASS'):
    e=deepcopy(task['execution']);e.update(actualDate='2026-10-26',actualQuantity='100',sampleQuantity='10',inspector='张检验',result=result,remark='原文 <script> & =备注')
    return e


def save(db,t,**changes):
    e=fill(t);e.update(changes)
    return wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':e},ACTOR)


def command(db,t,action,reason=''):
    body={'revision':t['revision']}
    if action in {'approve','return','reopen'}:body['reason']=reason
    return wf.act(db,'huaxing',t['id'],action,body,SUPERVISOR if action in {'approve','return','reopen'} else ACTOR)


def png():
    buf=BytesIO();Image.new('RGB',(2,2),'red').save(buf,format='PNG');return buf.getvalue()


def attach(t,content=None,name='现场照片.png'):
    return wf.add_file('huaxing',t['id'],{'revision':t['revision'],'name':name,
        'content':base64.b64encode(content or png()).decode(),'caption':'划痕位置'},ACTOR)


def test_full_internal_journey_lock_return_approve_and_immutable_evidence(db):
    t=create(db);assert t['state']=='waiting' and t['execution']['result']==''
    t=save(db,t);assert t['state']=='draft';t=attach(t);file_id=t['attachments'][0]['id']
    t=command(db,t,'submit');assert t['state']=='pending' and wf.projections(db,'huaxing')==[]
    submitted=deepcopy(t['history'][-1]['snapshot'])
    for work in [lambda:save(db,t),lambda:attach(t),lambda:wf.remove_file('huaxing',t['id'],file_id,{'revision':t['revision']},ACTOR)]:
        with pytest.raises(HTTPException) as err:work()
        assert err.value.status_code==409
    t=command(db,t,'return','补充问题说明');t=save(db,t,remark='补充后的说明')
    t=wf.remove_file('huaxing',t['id'],file_id,{'revision':t['revision']},ACTOR)
    assert wf.read_file('huaxing',t['id'],file_id)['content']==png()
    t=command(db,t,'submit');t=command(db,t,'approve')
    assert t['state']=='approved' and t['execution']['remark']=='补充后的说明'
    assert next(h['snapshot'] for h in t['history'] if h['action']=='submit')==submitted
    projected=wf.projections(db,'huaxing');assert len(projected)==1 and projected[0]['date']=='2026-10-26'
    t=command(db,t,'reopen','原报告需更正');assert t['state']=='returned' and wf.projections(db,'huaxing')==[]


def test_external_report_keeps_declared_result_with_discrepancy_explanation(db):
    t=create(db,'external');t=save(db,t,measurements=[{'item':'长度','standard':'10','values':'12','result':'FAIL','remark':'报告记载'}])
    t=attach(t,b'%PDF-1.4\noriginal report','原报告.pdf')
    with pytest.raises(HTTPException) as err:command(db,t,'submit')
    assert err.value.status_code==422
    t=save(db,t,resultExplanation='第三方原报告最终结论 PASS，尺寸项附客户确认')
    assert t['execution']['result']=='PASS'
    t=command(db,t,'submit');t=command(db,t,'approve');assert t['execution']['result']=='PASS'
    packet=wf.export_packet(db,'huaxing',{'ids':[t['id']],'formal':True})
    with zipfile.ZipFile(BytesIO(packet)) as z:
        assert any(n.endswith('原报告.pdf') for n in z.namelist())
        assert '客验' in z.read('验货明细.csv').decode('utf-8-sig')
        assert json.loads(z.read(t['id']+'/完整记录及历史.json'))['execution']['result']=='PASS'


def test_external_report_missing_requires_explanation_and_empty_result_never_submits(db):
    t=create(db,'external')
    with pytest.raises(HTTPException):command(db,t,'submit')
    t=save(db,t)
    with pytest.raises(HTTPException):command(db,t,'submit')
    t=save(db,t,reportMissingReason='机构系统暂不可下载，主管核对编号')
    assert command(db,t,'submit')['state']=='pending'


def test_retries_unique_batches_and_two_inspection_methods(db):
    line=ingest(db);first=create(db,line=line);again=create(db,line=line)
    assert first['id']==again['id']
    assert create(db,line=line,key='other-request-key')['id']==first['id']
    second=create(db,'external',line=line,key='external-request');third=create(db,batch='返工重验1',line=line,key='recheck-request')
    assert len({first['id'],second['id'],third['id']})==3
    rows=wf.sources(db,'huaxing')['items'];assert len(rows)==1 and len(rows[0]['tasks'])==3
    assert 'unit_price_hkd' not in str(rows)


def test_source_dates_never_use_ship_dates_and_cross_factory_sources_hidden(db):
    line=ingest(db);payload=wf.sources(db,'huaxing');assert payload['items'][0]['dateFrom']==''
    assert payload['items'][0]['shipDate']=='2026-10-01'
    assert wf.sources(db,'huadeng')['items']==[]
    assert payload['items'][0]['productNo']=='000045'
    with pytest.raises(HTTPException):wf.create_tasks(db,'huadeng',{'requestKey':'another-factory','items':[{'sourceId':line.id,'sourceRevision':1,'method':'internal','batch':'a','plannedDate':'2026-10-26','plannedQuantity':'10'}]},ACTOR)


def test_atomic_batch_and_invalid_source_or_quantity(db):
    line=ingest(db)
    item={'sourceId':line.id,'sourceRevision':line.revision,'method':'internal','batch':'one','plannedDate':'2026-10-26','plannedQuantity':'100'}
    with pytest.raises(HTTPException):wf.create_tasks(db,'huaxing',{'requestKey':'atomic-failure','items':[item,{**item,'sourceId':'example-row','batch':'two'}]},ACTOR)
    assert wf.list_tasks(db,'huaxing')['items']==[]
    for bad in ['NaN','Infinity','-1','10000000000000']:
        with pytest.raises(HTTPException):wf.create_tasks(db,'huaxing',{'requestKey':'bad-quantity','items':[{**item,'plannedQuantity':bad}]},ACTOR)


def test_conflicts_and_source_changes_preserve_draft(db):
    line=ingest(db);t=create(db,line=line);old=deepcopy(t);t=save(db,t)
    with pytest.raises(HTTPException) as err:save(db,old)
    assert err.value.status_code==409
    line.revision+=1;line.quantity=900;db.commit()
    assert wf.detail(db,'huaxing',t['id'])['sourceChanged']
    with pytest.raises(HTTPException):command(db,t,'submit')
    t=wf.act(db,'huaxing',t['id'],'ack-source',{'revision':t['revision'],'sourceRevision':line.revision,'reason':'已核对订单减量，本次100件不变'},ACTOR)
    assert t['execution']['remark'].startswith('原文')
    t=command(db,t,'submit');line.revision+=1;db.commit()
    with pytest.raises(HTTPException):command(db,t,'approve')


def test_attachments_permissions_types_limits_and_factory_boundary(db):
    t=create(db)
    for name,content in [('bad.html',b'<script>'),('../secret.pdf',b'%PDF-x'),('fake.png',b'%PDF-x'),('huge.pdf',b'%PDF-'+b'x'*wf.MAX_FILE)]:
        with pytest.raises(HTTPException):attach(t,content,name)
    t=attach(t);f=t['attachments'][0]['id']
    with pytest.raises(HTTPException) as err:wf.read_file('huadeng',t['id'],f)
    assert err.value.status_code==404
    assert wf.detail(db,'huaxing',t['id'])['revision']==t['revision']


def test_work_exports_dont_claim_formal_and_csv_formula_text_is_safe(db):
    t=create(db);t=save(db,t,remark='=HYPERLINK("bad")')
    with pytest.raises(HTTPException):wf.export_packet(db,'huaxing',{'ids':[t['id']],'formal':True})
    with zipfile.ZipFile(BytesIO(wf.export_packet(db,'huaxing',{'ids':[t['id']],'formal':False}))) as z:
        assert "'=HYPERLINK" in z.read('验货明细.csv').decode('utf-8-sig')
        assert '非正式统计' in z.read('汇总口径.txt').decode()


def qc_user(review=False,factory='huaxing'):
    codes=frozenset('qc_inspection:'+p for p in ['read','schedule_write','order_write','result_write','report_export']+(['review'] if review else []))
    return AuthContext(id='supervisor' if review else 'inspector',username='test',display_name='主管' if review else '验货员',roles=('test',),role_codes=('test',),permissions=codes,factory_scopes=(factory,),department_scopes=('qc',),
        grants=(AuthGrantContext(role_id='test',role_name='test',factory_id=factory,department='qc',permissions=codes),))


def test_real_http_gateway_enforces_role_factory_actor_and_submission_lock(db,monkeypatch):
    from app.services import auth
    monkeypatch.setattr(auth,'add_auth_audit',lambda *a,**k:None)
    async def healthy(*args): return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(gateway,'upstream',healthy)
    line=ingest(db);app=FastAPI();app.include_router(gateway.router)
    current=[qc_user()];app.dependency_overrides[get_current_user]=lambda:current[0];app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        source=client.get(base+'api/schedule-source');assert source.status_code==200 and source.json()['status']=='ready'
        t=client.post(base+'api/workflow/tasks',json={'requestKey':'http-create-001','items':[{'sourceId':line.id,'sourceRevision':1,'method':'internal','batch':'首验','plannedDate':'2026-10-26','plannedQuantity':'100'}]}).json()['items'][0]
        path=base+'api/workflow/tasks/'+t['id']
        t=client.post(path+'/save',json={'revision':t['revision'],'execution':fill(t)}).json()
        t=client.post(path+'/submit',json={'revision':t['revision']}).json();assert t['state']=='pending'
        assert client.post(path+'/save',json={'revision':t['revision'],'execution':fill(t)}).status_code==409
        assert client.post(path+'/approve',json={'revision':t['revision'],'reason':''}).status_code==403
        assert client.post(path+'/return',json={'revision':t['revision'],'reason':'退回'}).status_code==403
        assert client.post(path+'/save',json={},headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
        assert client.get('/api/qc-department/huadeng/api/health').status_code==403
        current[0]=qc_user(True)
        assert client.get(path).status_code==409
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url'];path=base+'api/workflow/tasks/'+t['id']
        assert client.get(path).json()['execution']==t['execution']
        t=client.post(path+'/return',json={'revision':t['revision'],'reason':'补充照片'}).json();assert t['state']=='returned'
        t=client.post(path+'/save',json={'revision':t['revision'],'execution':fill(t)}).json()
        t=client.post(path+'/submit',json={'revision':t['revision']}).json()
        assert client.post(path+'/approve',json={'revision':t['revision'],'reason':''}).json()['state']=='approved'


def test_builtin_supervisor_has_review_but_inspector_does_not():
    from app.services.system_positions import QC_INSPECTION_OPERATOR_PERMISSION_CODES,QC_INSPECTION_SUPERVISOR_PERMISSION_CODES
    assert 'qc_inspection:review' not in QC_INSPECTION_OPERATOR_PERMISSION_CODES
    assert 'qc_inspection:review' in QC_INSPECTION_SUPERVISOR_PERMISSION_CODES


def test_http_export_ticket_is_owner_scoped_expiring_and_preserves_zip(db, monkeypatch):
    t=save(db,create(db));t=command(db,t,'submit');t=command(db,t,'approve')
    ticket=wf.prepare_export(db,'huaxing',{'ids':[t['id']],'formal':True},ACTOR['id'])
    token=ticket['url'].split('/')[-1]
    raw=wf.download_export('huaxing',ACTOR['id'],token)
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        assert '验货明细.csv' in archive.namelist()
    for factory,actor in [('huadeng',ACTOR['id']),('huaxing','another-user')]:
        with pytest.raises(HTTPException) as error:wf.download_export(factory,actor,token)
        assert error.value.status_code==404
    clock=wf.time.time()+601
    monkeypatch.setattr(wf.time,'time',lambda:clock)
    with pytest.raises(HTTPException) as error:wf.download_export('huaxing',ACTOR['id'],token)
    assert error.value.status_code==410


def test_manual_record_draft_keeps_full_fields_and_saved_report_result(db):
    e=fill(create(db));e['record']={'supplier':'名发','client':'ZURU','productNo':'00123','deliveryNo':'0005501','orderNo':'00042','type':'半成品','date':'日期待核对','fail':8,'pass':72,'defectRate':'10.00%','measurements':[{'item':'长宽高','measureType':'lwh','lValues':['10'],'wValues':['20'],'hValues':['30'],'result':'FAIL'}]}
    body={'requestKey':'manual-001-request','method':'internal','execution':e}
    t=wf.create_entry('huaxing',body,ACTOR);assert t['state']=='draft'
    assert wf.create_entry('huaxing',body,ACTOR)['id']==t['id']
    changed=deepcopy(body);changed['execution']['remark']='different'
    with pytest.raises(HTTPException):wf.create_entry('huaxing',changed,ACTOR)
    t=command(db,t,'submit');t=command(db,t,'approve')
    r=next(r for r in wf.projections(db,'huaxing') if r['workflowId']==t['id'])
    assert r['deliveryNo']=='0005501' and r['result']=='PASS'
    assert r['measurements']==e['record']['measurements'] and r['date']=='日期待核对'


def test_returned_legacy_keeps_original_snapshot_and_new_revision_attachments(db):
    record={'id':22,'status':'rejected','result':'REJ','supplier':'名发','productNo':'00123','qty':600,'sampleQty':80,'fail':8,'pass':72,'defectRate':'10.00%','date':'未知日期','inspDate':'2026-10-26','qc':'QC','remark':'历史备注','defects':[],'measurements':[],'rejectReason':'补照片','updatedAt':'old'}
    original=deepcopy(record)
    t=wf.create_entry('huaxing',{'recordId':22},ACTOR,record,True)
    assert record==original and t['legacyOriginal']==original and t['reference']
    assert wf.legacy_links('huaxing')=={22:t['id']} and wf.legacy_links('huadeng')=={}
    e=deepcopy(t['execution']);e['remark']='补充备注';e['record']['remark']='补充备注'
    t=wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':e,'method':'internal'},ACTOR)
    t=attach(t);t=command(db,t,'submit');t=command(db,t,'approve')
    assert t['legacyOriginal']==original and t['execution']['record']['date']=='未知日期'
    assert t['attachments'] and t['execution']['remark']=='补充备注'
    with pytest.raises(HTTPException):wf.create_entry('huaxing',{'recordId':23},ACTOR,{**record,'id':23,'status':'approved'})


def test_schedule_feedback_keeps_sales_notes_separate_from_inspection_issues(db):
    line=ingest(db)
    row=wf.sources(db,'huaxing')['items'][0]
    assert row['completion']=='未推送' and row['remark']=='' and row['tasks']==[]
    line.data={**line.data,'note':'客户要求：出货前确认包装\n保留换行 <script>'};db.commit()
    first=create(db,line=line)
    first=save(db,first,remark='现场划痕 <script>',defects=[{'desc':'外观划痕','qty':'1','level':'','remark':'左侧'}])
    first=command(db,first,'submit')
    first=command(db,first,'return','补拍照片')
    second=create(db,line=line,batch='第二批',key='second-batch-request')
    before=deepcopy(wf.list_tasks(db,'huaxing'))
    row=wf.sources(db,'huaxing')['items'][0]
    assert '首验：已退回' in row['completion'] and '第二批：待验货' in row['completion']
    tasks={t['id']:t for t in row['tasks']}
    assert tasks[first['id']]['result']=='PASS' and tasks[second['id']]['result']==''
    assert row['remark']=='客户要求：出货前确认包装\n保留换行 <script>'
    assert '现场划痕' not in row['remark'] and '外观划痕' not in row['remark']
    line.data={**line.data,'note':''};db.commit()
    assert wf.sources(db,'huaxing')['items'][0]['remark']==''
    assert wf.list_tasks(db,'huaxing')==before
    assert wf.sources(db,'huadeng')['items']==[]


def test_example_source_notes_survive_saved_feedback():
    from app.services.qc_schedule_example_feedback import read_feedback, save_feedback
    payload={'factory_id':'huaxing','source':{'sha256':'example-source'},
             'items':[{'id':'example-1','completion':'','remark':'原排期备注\n保留原文'}]}
    save_feedback(deepcopy(payload),{'id':'example-1','sourceSha256':'example-source',
        'completion':'已完成','remark':'验货备注','revision':0},'test')
    row=read_feedback(deepcopy(payload))['items'][0]
    assert row['sourceRemark']=='原排期备注\n保留原文'
    assert row['remark']=='验货备注' and row['feedbackRevision']==1


def test_inspector_is_bound_to_authenticated_writer_and_review_preserves_it(db):
    t=create(db)
    assert t['execution']['inspector']==''  # scheduling is not inspection
    e=fill(t);e['record']={'qc':'冒名者'}
    t=wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':e},ACTOR)
    assert t['execution']['inspector']==ACTOR['name']
    assert t['execution']['record']['qc']==ACTOR['name']
    assert t['inspectorAccount']==ACTOR
    t=command(db,t,'submit');submitted=deepcopy(t['execution'])
    t=command(db,t,'approve')
    assert t['execution']==submitted and t['inspectorAccount']==ACTOR
    t=command(db,t,'reopen','重新核对')
    other={'id':'qc-2','name':'另一位检验员'}
    t=wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':e},other)
    assert t['inspectorAccount']==other and t['execution']['inspector']==other['name']
    assert any(h['action']=='submit' and h['snapshot']['execution']['inspector']==ACTOR['name'] for h in t['history'])


def test_manual_inspector_cannot_be_spoofed_and_legacy_original_is_preserved(db):
    e=fill(create(db));e['record']={'qc':'冒名者'}
    t=wf.create_entry('huaxing',{'requestKey':'inspector-manual-test','method':'internal','execution':e},ACTOR)
    assert t['inspectorAccount']==ACTOR and t['execution']['record']['qc']==ACTOR['name']
    record={'id':99,'status':'rejected','qc':'历史检验员','qty':10,'result':'PASS'}
    t=wf.create_entry('huaxing',{'recordId':99},ACTOR,record)
    assert t['execution']['inspector']=='历史检验员'
    t=wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':t['execution']},ACTOR)
    assert t['execution']['inspector']==ACTOR['name']
    assert t['legacyOriginal']['qc']=='历史检验员' and record['qc']=='历史检验员'


@pytest.mark.parametrize('endpoint',['api/records','api/records/replace'])
def test_legacy_sync_cannot_change_inspector(db,monkeypatch,endpoint):
    from app.services import auth
    monkeypatch.setattr(auth,'add_auth_audit',lambda *a,**k:None)
    user=qc_user(True)
    codes=user.permissions|{'qc_inspection:customer_manage'}
    user=replace(user,permissions=codes,grants=(replace(user.grants[0],permissions=codes),))
    calls=[]
    async def upstream(method,path,params,body):
        if method=='POST': calls.append(json.loads(body))
        return httpx.Response(200,json={'ok':True,'records':[{'id':1,'status':'rejected','qc':'原检验员'}]})
    monkeypatch.setattr(gateway,'upstream',upstream)
    app=FastAPI();app.include_router(gateway.router)
    app.dependency_overrides[get_current_user]=lambda:user
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        base=client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        assert client.post(base+endpoint,json={'records':[{'id':1,'status':'rejected','qc':'伪造'}]}).status_code==409
        assert calls==[]
        for bad_id in ['1', True, 1.0, 0, -1]:
            assert client.post(base+endpoint,json={'records':[{'id':bad_id,'qc':'伪造'}]}).status_code==400
        assert calls==[]
        assert client.post(base+endpoint,json={'records':[{'id':1,'status':'rejected','qc':'原检验员'},{'id':2,'qc':'伪造'}]}).status_code==200
        assert calls[-1]['records'][0]['qc']=='原检验员'
        assert calls[-1]['records'][1]['qc']==user.display_name
    assert gateway.ui_context(replace(user,display_name=''),'huaxing')['inspector']=={'id':user.id,'name':user.username}


def test_only_exact_local_test_snapshot_can_open_without_supervisor_return(db):
    from pathlib import Path
    from hashlib import sha256
    r={'id':31,'status':None,'qc':'','result':'','qty':100,'client':'Test','remark':'【客排期测试数据】'}
    with pytest.raises(HTTPException):wf.create_entry('huaxing',{'recordId':31},ACTOR,r)
    allow=Path(wf.settings.qc_department_data_dir)/'_workflow'/'test-entry-allowlist.json'
    allow.parent.mkdir(parents=True,exist_ok=True)
    allow.write_text(json.dumps({'huaxing':{'31':sha256(wf.dump(r).encode()).hexdigest()}}))
    assert wf.test_entry_allowed('huaxing',r)
    assert not wf.test_entry_allowed('huadeng',r)
    for changed in [{**r,'qty':101},{**r,'status':'approved'},{**r,'id':32},{**r,'qc':'someone'}]:
        assert not wf.test_entry_allowed('huaxing',changed)
        with pytest.raises(HTTPException):wf.create_entry('huaxing',{'recordId':changed['id']},ACTOR,changed)
    t=wf.create_entry('huaxing',{'recordId':31},ACTOR,r)
    assert t['state']=='draft' and t['testEntry'] and t['reference']
    assert t['legacyOriginal']==r and t['execution']['inspector']==ACTOR['name']
    assert wf.create_entry('huaxing',{'recordId':31},ACTOR,r)['id']==t['id']
    t=wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':fill(t),'method':'internal'},ACTOR)
    t=command(db,t,'submit')
    with pytest.raises(HTTPException):wf.act(db,'huaxing',t['id'],'save',{'revision':t['revision'],'execution':fill(t)},ACTOR)


def test_explicit_sales_schedule_range_and_agency_survive_push(db):
    from app.services import qc_inspection_sheet as sheet
    line=ingest(db)
    line.data={**line.data,'planned_inspection_date':'2026-10-27','planned_inspection_date_to':'2026-10-29','inspection_agency':'行验','note':'10%抽板'}
    db.commit()
    source=wf.sources(db,'huaxing')['items'][0]
    assert (source['dateFrom'],source['dateTo'],source['agency'])==('2026-10-27','2026-10-29','行验')
    task=create(db,line=line)
    rows=sheet.sync('huaxing',sheet.candidates('huaxing',[],[task],[source]))['items']
    assert len(rows)==1 and rows[0]['dateTo']=='2026-10-29' and rows[0]['agency']=='行验' and rows[0]['result']==''
    line.data={**line.data,'planned_inspection_date':'','planned_inspection_date_to':'','inspection_agency':''};db.commit()
    source=wf.sources(db,'huaxing')['items'][0]
    assert source['dateFrom']==source['dateTo']==source['agency']==''
