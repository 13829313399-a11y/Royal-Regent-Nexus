"""Source-backed help checks; temporary sources and isolated HTTP fixtures only."""
import hashlib
import json
from types import SimpleNamespace
import pytest
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate


def install_registry(tmp_path, monkeypatch):
    from app.services.assistant import help_registry as registry
    source = tmp_path / 'source.vue'
    source.write_bytes(b'field\r\n')
    directory = tmp_path / 'help' / 'modules'
    directory.mkdir(parents=True)
    article = dict(id='test.field', module_id='test', title='合成数量', kind='field', audience='internal',
        route_names=['test-route'], factory_ids=[], anchor_id='test.field', field_keys=['field'],
        summary='通用口径', content='单位为件；合成示例不含业务记录。', steps=[],
        source_refs=[dict(path='source.vue', symbol='field', sha256=hashlib.sha256(b'field\n').hexdigest())],
        knowledge_version='v1', verified_commit='synthetic', status='verified')
    path = directory / 'field.json'
    path.write_text(json.dumps([article], ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    monkeypatch.setattr(registry, 'HELP_DIR', tmp_path / 'help')
    return registry, article, path, source


def test_version_binds_content_steps_and_source_and_normalizes_line_endings(tmp_path, monkeypatch):
    registry, article, path, source = install_registry(tmp_path, monkeypatch)
    first = registry.public(registry.articles()[0], verification=True)
    assert 'verification' not in registry.public(registry.articles()[0])
    assert first['status'] == 'verified'
    assert first['verification']['sources'][0]['matches'] is True
    assert first['verification']['sources'][0]['current_sha256'] == article['source_refs'][0]['sha256']
    article['content'] += '改变口径。'
    path.write_text(json.dumps([article]), encoding='utf-8')
    changed = registry.public(registry.articles()[0], verification=True)
    assert changed['knowledge_version'] == first['knowledge_version']
    assert changed['verification']['fingerprint'] != first['verification']['fingerprint']
    source.write_text('field changed', encoding='utf-8')
    stale = registry.public(registry.articles()[0], verification=True)
    assert stale['status'] == 'needs_review'
    assert stale['verification']['sources'][0]['matches'] is False


@pytest.mark.parametrize('failure', ['missing', 'symbol', 'outside', 'no_sources'])
def test_invalid_source_cannot_establish_verified_help(failure, tmp_path, monkeypatch):
    registry, article, path, source = install_registry(tmp_path, monkeypatch)
    if failure == 'missing':
        source.unlink()
    elif failure == 'symbol':
        article['source_refs'][0]['symbol'] = 'absent'
    elif failure == 'outside':
        article['source_refs'][0]['path'] = '../outside.vue'
    else:
        article['source_refs'] = []
    path.write_text(json.dumps([article]), encoding='utf-8')
    assert registry.articles()[0].status == 'needs_review'


def test_help_http_rechecks_sources_without_business_read_permission(env, tmp_path):
    client, _, calls, monkeypatch = env
    registry, article, _, source = install_registry(tmp_path, monkeypatch)
    params = dict(module_id='test', route_name='test-route')
    first = client.get('/api/assistant/help/context', params=params)
    assert first.status_code == 200
    assert first.headers['cache-control'] == 'private, no-store'
    assert first.json()['items'][0]['status'] == 'verified'
    source.write_text('changed', encoding='utf-8')
    second = client.get('/api/assistant/help/articles/test.field')
    assert second.status_code == 200 and second.json()['status'] == 'needs_review'
    assert second.json()['verification']['sources'][0]['matches'] is False
    assert calls == []
    assert registry.visible(SimpleNamespace(permissions=['carton_supplier:read'])) == []


def help_payload(protocol=2, **values):
    return payload(protocol_version=protocol, intent='explain_element',
        page_context=dict(module_id='test',route_name='test-route',help_id='test.field'), **values) | {'text':'说明合成数量单位'}


def test_stale_help_is_excluded_from_tools_and_chat_but_explicit_explanation_fails_before_admission(env,tmp_path):
    client,dbm,calls,patch=env
    registry,article,_,source=install_registry(tmp_path,patch)
    source.write_text('changed',encoding='utf-8')
    actor=SimpleNamespace(permissions=[])
    assert registry.tool(actor,'help_search',{'query':'合成'}) == []
    with pytest.raises(Exception) as error:
        registry.tool(actor,'help_describe_element',{'help_id':article['id']})
    assert error.value.detail['code'] == 'help_needs_review'
    sid=session(client)
    rejected=client.post(f'/api/assistant/sessions/{sid}/messages',json=help_payload())
    assert rejected.status_code==409 and rejected.json()['detail']['code']=='help_needs_review'
    from app.models.assistant import AssistantRun
    from sqlalchemy import select,func
    with dbm.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AssistantRun))==0
    assert calls==[]
    # Ordinary questions remain available even on a page whose help needs review.
    asked=client.post(f'/api/assistant/sessions/{sid}/messages',json=help_payload() | {'intent':'chat','text':'解释闭包'})
    assert 'run.completed' in asked.text,asked.text
    assert article['content'] not in json.dumps(calls[-1],ensure_ascii=False)


@pytest.mark.parametrize('protocol',[1,2])
def test_frozen_help_invalidates_history_actions_exports_and_all_artifact_versions(env,tmp_path,protocol):
    client,dbm,calls,patch=env;migrate(dbm)
    registry,article,path,_=install_registry(tmp_path,patch)
    sid=session(client);request=help_payload(protocol)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request)
    assert 'run.completed' in response.text,response.text
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    run=answer['run_id'];frozen=answer['help_citations'][0]
    assert frozen['source_fingerprint']==registry.fingerprint(registry.articles()[0])
    assert article['content'] in json.dumps(calls[0],ensure_ascii=False)
    action=client.post('/api/assistant/actions/resolve',json=dict(run_id=run,index=0))
    assert action.status_code==200,action.text
    assert action.json()['source_fingerprint']==frozen['source_fingerprint']
    saved=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=run,title='合成帮助成果',kind='research',content='合成结果'))
    assert saved.status_code==200,saved.text
    aid=saved.json()['id']
    assert saved.json()['source_refs'][0]['source_fingerprint']==frozen['source_fingerprint']
    assert client.post(f'/api/assistant/artifacts/{aid}/versions',json=dict(base_revision=1,content='合成修订')).status_code==200
    article['content']='新的合成单位口径，版本标签仍相同。'
    path.write_text(json.dumps([article]),encoding='utf-8')
    assert registry.articles()[0].status=='verified'
    assert registry.articles()[0].knowledge_version==frozen['version']
    messages=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
    assert all(m['unavailable'] and not m['help_citations'] for m in messages)
    assert client.get(f'/api/assistant/runs/{run}/export').status_code==410
    assert '自由回答' not in client.get(f'/api/assistant/sessions/{sid}/export').text
    assert client.post('/api/assistant/actions/resolve',json=dict(run_id=run,index=0)).status_code==410
    for revision in (1,2):
        assert client.get(f'/api/assistant/artifacts/{aid}?revision={revision}').status_code==410
        assert client.get(f'/api/assistant/artifacts/{aid}/export?revision={revision}').status_code==410
    assert client.post(f'/api/assistant/sessions/{sid}/messages',json=request).json()['reused'] is True
    assert len(calls)==1


def test_legacy_version_only_history_remains_readable_without_becoming_new_evidence(env,tmp_path):
    client,dbm,calls,patch=env;migrate(dbm)
    registry,_,_,_=install_registry(tmp_path,patch)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=help_payload(1))
    assert 'run.completed' in response.text,response.text
    from app.models.assistant import AssistantMessage
    from sqlalchemy import select
    with dbm.SessionLocal() as db:
        for message in db.scalars(select(AssistantMessage)):
            message.help_citations=[{k:v for k,v in c.items() if k!='source_fingerprint'} for c in message.help_citations]
            if message.role=='assistant':
                message.content_parts=[dict(type='text',text='LEGACY_GUIDE_RULE'),dict(type='actions',items=[dict(type='highlight',help_id='test.field',label='旧引导')])]
                run=message.run_id
        db.commit()
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    assert answer['help_verification']=='legacy_version_only'
    assert answer['content_parts'][0]['text']=='LEGACY_GUIDE_RULE'
    assert client.post('/api/assistant/actions/resolve',json=dict(run_id=run,index=0)).json()['detail']['code']=='help_legacy'
    saved=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=run,title='旧资料',kind='research',content='LEGACY_GUIDE_RULE'))
    assert saved.status_code==200,saved.text
    assert saved.json()['source_refs'][0]['source_fingerprint'] is None
    assert '旧记录未保存' in client.get(f"/api/assistant/artifacts/{saved.json()['id']}/export").text
    follow=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload())
    assert 'run.completed' in follow.text,follow.text
    assert 'LEGACY_GUIDE_RULE' not in json.dumps(calls[-1],ensure_ascii=False)
    assert '未保存来源指纹' in json.dumps(calls[-1],ensure_ascii=False)


@pytest.mark.parametrize('when',['before_provider','during_provider'])
def test_changed_help_stops_generation_without_paid_retry(env,tmp_path,when):
    client,_,calls,patch=env
    _,article,path,_=install_registry(tmp_path,patch)
    from app.services.assistant import runtime,provider
    def change():
        path.write_text(json.dumps([{**article,'content':'changed source rule'}]),encoding='utf-8')
    if when=='before_provider':
        original=runtime.history
        def history(*args,**kwargs):
            result=original(*args,**kwargs);change();return result
        patch.setattr(runtime,'history',history)
    else:
        from contextlib import asynccontextmanager
        original=provider.open_stream
        @asynccontextmanager
        async def upstream(body):
            async with original(body) as chunks:
                async def drift():
                    changed=False
                    async for chunk in chunks:
                        if not changed:
                            change();changed=True
                        yield chunk
                yield drift()
        patch.setattr(provider,'open_stream',upstream)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=help_payload(1))
    assert 'run.completed' not in response.text,response.text
    assert 'help_changed' in response.text,response.text
    assert len(calls)==(0 if when=='before_provider' else 1)
