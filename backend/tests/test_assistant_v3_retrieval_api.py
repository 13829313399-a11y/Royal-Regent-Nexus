"""Actual private upload/search/history endpoints; model transport is offline replay."""
import hashlib
import json
from types import SimpleNamespace
import pytest
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate
from test_assistant_v3_office_api import ready


def upload(client,sid,text='SYN-R0913 紫色内衬必须提供耐湿检验记录。',name='synthetic.txt'):
    response=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':(name,text.encode(),'text/plain')})
    assert response.status_code==200,response.text
    ident=response.json()['id']; value=ready(client,ident)
    assert value['parse_status']=='ready',value
    return value


def search(client,sid,ident,query):
    return client.post(f'/api/assistant/sessions/{sid}/files/search',json=dict(document_ids=[ident],query=query))


def ask(client,sid,ident,query):
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,
        document_ids=[ident] if ident else [],intent='analyze_files')|{'text':query})
    assert 'event: run.completed' in response.text,response.text
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    return answer,next(p for p in answer['content_parts'] if p['type']=='evidence')


def test_long_file_uses_same_selected_snapshot_for_inspection_model_and_citations(env):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client)
    lines=[f'SYN-R{i:04d} 合成常规条款，包装数量以签字单为准。'*4 for i in range(1000)]
    lines[913]='SYN-R0913 紫色内衬必须提供耐湿检验记录。'
    info=upload(client,sid,'\n'.join(lines)); ident=info['id']
    query='SYN-R0913 的验收条件是什么？'
    inspection=search(client,sid,ident,query)
    assert inspection.status_code==200,inspection.text
    assert inspection.headers['cache-control']=='private, no-store'
    assert not calls
    selected=inspection.json()
    assert selected['report']['total_chunks']>100
    assert selected['report']['selected_characters']<=8000
    assert selected['report']['selected_chunks']<selected['report']['total_chunks']
    answer,evidence=ask(client,sid,ident,query)
    body=calls[-1]['messages']
    replay=next(row['content'] for row in body if isinstance(row.get('content'),str) and row['content'].startswith('本轮选用的文件检索。'))
    material=json.loads(replay.split('\n',1)[1])
    assert material['report']==selected['report']
    assert [(m['text'],m['locator'],m['document_version']) for m in material['materials']]==[
        (m['text'],m['locator'],m['document_version']) for m in selected['materials']]
    refs=[s for s in evidence['sources'] if s.get('citation_eligible',True)]
    assert {m['source_id'] for m in material['materials']}=={s['source_id'] for s in refs}
    assert all(s['document_version']==info['document_version'] for s in refs)
    assert 'SYN-R0000' not in json.dumps(body,ensure_ascii=False)
    for m in material['materials']:
        source=next(s for s in refs if s['source_id']==m['source_id'])
        assert source['chunk_hash']==hashlib.sha256(m['text'].encode()).hexdigest()
    _,followup=ask(client,sid,None,'SYN-R0012 的条款是什么？')
    followup_record=next(row['content'] for row in calls[-1]['messages'] if isinstance(row.get('content'),str) and row['content'].startswith('本轮沿用同会话'))
    assert 'SYN-R0012' in followup_record and 'SYN-R0913' not in followup_record
    assert any(s.get('origin') for s in followup['sources']), 'historical evidence retains its original turn'


def test_no_match_has_no_text_citation_but_still_invalidates_all_artifact_versions(env):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); info=upload(client,sid)
    inspection=search(client,sid,info['id'],'SYN-R09130').json()
    assert not inspection['materials'] and inspection['report']['coverage']=='no_match'
    assert len(inspection['sources'])==1 and inspection['sources'][0]['citation_eligible'] is False
    answer,evidence=ask(client,sid,info['id'],'SYN-R09130 是否有记录？')
    assert len(evidence['sources'])==1 and not evidence['sources'][0].get('citation_aliases')
    assert all(not s.get('citation_eligible',True) for s in evidence['sources'])
    saved=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=answer['run_id'],title='未命中检查',kind='markdown',content='当前未召回目标编号。'))
    assert saved.status_code==200,saved.text
    aid=saved.json()['id']
    assert client.post(f'/api/assistant/artifacts/{aid}/versions',json=dict(base_revision=1,content='仍需核对原文件。')).status_code==200
    assert client.delete(f"/api/assistant/files/{info['id']}").status_code==204
    assert search(client,sid,info['id'],'SYN-R0913').status_code==410
    assert client.get(f"/api/assistant/sessions/{sid}/messages").json()['items'][-1]['unavailable']
    for revision in (1,2):
        assert client.get(f'/api/assistant/artifacts/{aid}?revision={revision}').status_code==410
        assert client.get(f'/api/assistant/artifacts/{aid}/export?revision={revision}').status_code==410


def test_owner_session_and_epoch_are_checked_before_retrieval(env):
    client,dbm,calls,patch=env; migrate(dbm); sid=session(client); info=upload(client,sid)
    from app.services.assistant import document_retrieval, files
    from app.services.assistant.errors import AssistantError
    reached=[]
    original=document_retrieval.retrieve
    def tracked(*args,**kwargs):
        reached.append(True); return original(*args,**kwargs)
    patch.setattr(document_retrieval,'retrieve',tracked)
    client.cookies.set('rr_session','bob'); other=session(client)
    assert search(client,other,info['id'],'SYN-R0913').status_code==404
    client.cookies.set('rr_session','alice'); other=session(client)
    assert search(client,other,info['id'],'SYN-R0913').status_code==404
    with dbm.SessionLocal() as db,pytest.raises(AssistantError) as exc:
        files.search_documents(db,SimpleNamespace(id='alice',identity={'employment_epoch':2}),sid,[info['id']],'SYN-R0913','test')
    assert exc.value.status_code==404 and not reached and not calls


@pytest.mark.parametrize('mutation',['original','index','malformed'])
def test_version_drift_is_rejected_by_search_preview_history_and_export(env,mutation):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); info=upload(client,sid)
    answer,_=ask(client,sid,info['id'],'SYN-R0913')
    from app.services.assistant import files
    with dbm.SessionLocal() as db:
        row=db.get(files.Document,info['id']); original=files.path_for(row.storage_key); index=files.path_for(row.storage_key,True)
    if mutation=='original':
        original.write_bytes(original.read_bytes().replace(b'0913',b'9999'))
    elif mutation=='index':
        segments=json.loads(index.read_text(encoding='utf-8')); segments[0]['text']='stale substituted text'
        index.write_text(json.dumps(segments),encoding='utf-8')
    else: index.write_text('[null]',encoding='utf-8')
    assert search(client,sid,info['id'],'SYN-R0913').status_code==409
    assert client.get(f"/api/assistant/files/{info['id']}/content?extracted=true&version={info['document_version']}").status_code==409
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code==410


def test_legacy_unstamped_index_is_versioned_and_source_ranges_are_rechecked(env):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); info=upload(client,sid)
    from app.services.assistant import files, visibility
    with dbm.SessionLocal() as db:
        row=db.get(files.Document,info['id']); index=files.path_for(row.storage_key,True)
    parts=json.loads(index.read_text(encoding='utf-8'))
    for part in parts:
        part.pop('document_version'); part.pop('original_hash')
    index.write_text(json.dumps(parts,ensure_ascii=False),encoding='utf-8')
    result=search(client,sid,info['id'],'SYN-R0913')
    assert result.status_code==200,result.text
    assert result.json()['report']['versions'][info['id']]==info['document_version']
    actor=SimpleNamespace(id='alice',identity={'employment_epoch':1})
    refs=result.json()['sources']; assert visibility.allowed(actor,refs)
    refs[0]['excerpt_range']['end']+=1
    assert not visibility.allowed(actor,refs)
    assert not calls


def test_search_contract_rejects_empty_duplicate_overcomplex_and_tiny_budget(env):
    client,dbm,calls,patch=env; migrate(dbm); sid=session(client); info=upload(client,sid)
    path=f'/api/assistant/sessions/{sid}/files/search'
    assert client.post(path,json=dict(document_ids=[],query='q')).status_code==422
    assert client.post(path,json=dict(document_ids=[info['id']]*2,query='q')).status_code==422
    assert search(client,sid,info['id'],' '.join(f'UNIQUE-{i}' for i in range(33))).status_code==422
    from app.services.assistant import files
    patch.setattr(files.settings,'assistant_context_character_budget',60)
    response=search(client,sid,info['id'],'SYN-R0913')
    assert response.status_code==422 and response.json()['detail']['code']=='file_context_limit'
    assert not calls


def replace(client,old,new,**overrides):
    return client.post(f"/api/assistant/files/{old['id']}/replace",json=dict(replacement_id=new['id'],
        expected_version=old['document_version'],replacement_version=new.get('document_version','0'*64))|overrides)


def test_replacement_reindexes_new_bytes_and_retires_old_answers_and_artifacts(env):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); old=upload(client,sid)
    answer,_=ask(client,sid,old['id'],'SYN-R0913')
    saved=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=answer['run_id'],title='旧版',kind='markdown',content='旧版合成验收内容'))
    aid=saved.json()['id']
    client.post(f'/api/assistant/artifacts/{aid}/versions',json=dict(base_revision=1,content='旧版第二次整理'))
    new=upload(client,sid,'SYN-R0913 新版改为蓝色内衬。','replacement.txt')
    response=replace(client,old,new)
    assert response.status_code==200,response.text
    assert response.json()['file']['document_version']==new['document_version']!=old['document_version']
    metadata=client.get(f"/api/assistant/files/{old['id']}").json()
    assert metadata['parse_status']=='superseded' and metadata['parse_index']==[]
    assert search(client,sid,old['id'],'SYN-R0913').status_code==410
    assert client.get(f"/api/assistant/files/{old['id']}/content").status_code==410
    selected=search(client,sid,new['id'],'SYN-R0913').json()
    assert '蓝色' in selected['materials'][0]['text'] and '紫色' not in json.dumps(selected,ensure_ascii=False)
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']
    for revision in (1,2): assert client.get(f'/api/assistant/artifacts/{aid}/export?revision={revision}').status_code==410
    from app.services.assistant import files
    with dbm.SessionLocal() as db: key=db.get(files.Document,old['id']).storage_key
    assert not files.path_for(key).exists() and not files.path_for(key,True).exists()
    _,evidence=ask(client,sid,new['id'],'SYN-R0913')
    assert all(s['file_ref']['id']==new['id'] for s in evidence['sources'] if s['kind']=='file')
    assert '紫色' not in json.dumps(calls[-1],ensure_ascii=False)


def test_failed_stale_cross_session_and_foreign_replacements_preserve_original(env):
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); old=upload(client,sid)
    bad=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('bad.pdf',b'not a PDF')}).json()
    assert ready(client,bad['id'])['parse_status']=='failed'
    assert replace(client,old,bad).status_code==409
    new=upload(client,sid,'SYN-R0913 新版')
    assert replace(client,old,new,expected_version='0'*64).status_code==409
    assert replace(client,old,new,replacement_version='0'*64).status_code==409
    other=upload(client,session(client),'SYN-R0913 其他会话')
    assert replace(client,old,other).status_code==404
    client.cookies.set('rr_session','bob'); foreign=upload(client,session(client),'SYN-R0913 其他账号')
    client.cookies.set('rr_session','alice')
    assert replace(client,old,foreign).status_code==404
    assert replace(client,old,old).status_code==422
    assert search(client,sid,old['id'],'SYN-R0913').status_code==200 and not calls


def test_competing_replacements_have_only_one_winner(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client,dbm,calls,_=env; migrate(dbm); sid=session(client); old=upload(client,sid)
    first=upload(client,sid,'SYN-R0913 first');second=upload(client,sid,'SYN-R0913 second')
    from app.services.assistant import files
    from app.services.assistant.errors import AssistantError
    gate=Barrier(2); actor=SimpleNamespace(id='alice',identity={'employment_epoch':1})
    def compete(candidate):
        gate.wait()
        try: files.replace(actor,old['id'],candidate['id'],old['document_version'],candidate['document_version']); return 200
        except AssistantError as exc: return exc.status_code
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(compete,[first,second]))
    assert sorted(results)==[200,410] and not calls
    assert all(search(client,sid,d['id'],'SYN-R0913').status_code==200 for d in (first,second))
