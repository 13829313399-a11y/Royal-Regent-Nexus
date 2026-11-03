"""Explicit reasks retain source restrictions even outside the history window."""
import hashlib
import json
from sqlalchemy import select
import pytest
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate


def test_optional_relation_preserves_both_historical_canonical_hashes():
    from app.schemas.assistant import SendMessage, canonical_request
    for version in (1, 2):
        body = payload(protocol_version=version)
        request = SendMessage(**body)
        expected = request.model_dump(mode='json', exclude={'relation'})
        if version == 1:
            for key in ('protocol_version', 'document_ids', 'context_selection'):
                expected.pop(key)
        assert canonical_request(request) == expected
        assert hashlib.sha256(json.dumps(canonical_request(request), sort_keys=True).encode()).digest() == hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).digest()
    with pytest.raises(ValueError):
        SendMessage(**payload(relation=dict(parent_run_id='old', kind='revise')))


def test_zero_tool_rounds_is_a_valid_single_synthesis_limit(env,tmp_path):
    from app.core.config import Settings
    from test_assistant_api import verified_profile
    from app.services.assistant import capabilities
    assert Settings(_env_file=None,assistant_max_tool_rounds=0).assistant_max_tool_rounds==0
    for value in (-1,17):
        with pytest.raises(ValueError): Settings(_env_file=None,assistant_max_tool_rounds=value)
    client,dbm,calls,patch=env
    migrate(dbm)
    settings=verified_profile(tmp_path)
    settings.assistant_max_tool_rounds=0
    settings.assistant_context_character_budget=24000
    settings.assistant_max_output_tokens=1024
    settings.assistant_daily_token_budget=450000
    assert capabilities.capabilities()['profiles'][0]['function_calling']
    sid=session(client)
    result=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2))
    assert 'run.completed' in result.text,result.text[-1000:]
    assert len(calls)==1 and 'tools' not in calls[0]
    message=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    saved=client.get('/api/assistant/runs/'+message['run_id']).json()
    assert saved['context_window']['reserved_tokens']==97024 and saved['usage']['total_tokens']==12


def test_question_scope_relations_immutability_and_rejection_before_provider(env):
    client, dbm, calls, patch = env
    migrate(dbm)
    sid = session(client)
    original = payload(protocol_version=2, thinking='auto', web_search='off')
    assert 'run.completed' in client.post(f'/api/assistant/sessions/{sid}/messages', json=original).text
    before = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
    parent = before[-1]['run_id']
    read = client.get(f'/api/assistant/runs/{parent}/question')
    assert read.status_code == 200 and read.headers['cache-control'] == 'private, no-store'
    assert read.json()['payload']['text'] == original['text']
    assert 'client_request_id' not in read.json()['payload']
    for kind in ('revise', 'regenerate', 'excerpt', 'retry'):
        body = payload(protocol_version=2, relation=dict(parent_run_id=parent, kind=kind))
        result = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
        assert 'run.completed' in result.text, result.text[-1000:]
        assert client.post(f'/api/assistant/sessions/{sid}/messages', json=body).json()['reused']
        current = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
        assert current[:2] == before
        assert dict(type='run_relation', parent_run_id=parent, kind=kind) in current[-2]['content_parts']
    assert len(calls) == 5
    assert '提问关系：' in client.get(f'/api/assistant/sessions/{sid}/export').text
    other = session(client)
    bad = client.post(f'/api/assistant/sessions/{other}/messages', json=payload(protocol_version=2, relation=dict(parent_run_id=parent, kind='revise')))
    assert bad.status_code == 404 and len(calls) == 5
    client.cookies.set('rr_session', 'bob')
    assert client.get(f'/api/assistant/runs/{parent}/question').status_code == 404
    assert len(calls) == 5


def test_trimmed_parent_sources_restrict_excerpt_answer_search_favorite_and_artifact(env):
    from test_assistant_v3_orders import setup
    from test_work_center_api import actor
    from app.services.assistant import runtime
    from app.services import auth
    from app.models.assistant import AssistantMessage, AssistantRun
    from app.core.config import settings
    client, dbm, calls, patch, user = setup(env)
    migrate(dbm)
    patch.setattr(runtime, 'authenticate', lambda request: user)
    sid = session(client)
    body = payload(protocol_version=2, intent='my_work', page_context=dict(module_id='customer-orders',route_name='customer-order-center',factory_id='huakang-a'))
    assert 'run.completed' in client.post(f'/api/assistant/sessions/{sid}/messages', json=body).text
    parent = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['run_id']
    # Keep the persisted original facts but force the original turn out of this
    # test's context window. The new user turn must carry its own dependencies.
    with dbm.SessionLocal() as db:
        answer = db.scalar(select(AssistantMessage).where(AssistantMessage.run_id==parent, AssistantMessage.role=='assistant'))
        answer.content_parts = answer.content_parts + [dict(type='text',text='原授权订单证据'*10000)]
        db.commit()
    settings.assistant_context_character_budget = 18000
    follow = payload(protocol_version=2, relation=dict(parent_run_id=parent,kind='excerpt'))
    follow['text'] = '仅针对刚才合成订单摘录继续解释，保留原时点，不刷新数据。'
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=follow)
    assert 'run.completed' in response.text, response.text[-2000:]
    items = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
    child = items[-1]['run_id']
    assert not items[-1].get('unavailable')
    evidence = next(p for p in items[-1]['content_parts'] if p['type']=='evidence')
    assert any(s['kind']=='business' and s['origin']['run_id']==parent for s in evidence['sources'])
    with dbm.SessionLocal() as db:
        assert db.get(AssistantRun,child).context_window['omitted_turns'] >= 1
    aid = client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=child,title='摘录成果',content='合成订单私有摘录')).json()['id']
    assert client.patch(f'/api/assistant/sessions/{sid}/favorite',json=dict(favorite=True)).status_code==200
    denied = actor('alice', department='sales-business', permissions=())
    client.app.dependency_overrides[auth.get_current_user] = lambda: denied
    patch.setattr(runtime, 'authenticate', lambda request: denied)
    assert all(m.get('unavailable') for m in client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'])
    assert client.get(f'/api/assistant/runs/{child}/question').status_code==410
    assert client.get(f'/api/assistant/artifacts/{aid}').status_code==410
    assert not client.get('/api/assistant/sessions',params=dict(q='合成订单',favorites=True)).json()['items']
    count=len(calls)
    rejected=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,relation=dict(parent_run_id=child,kind='excerpt')))
    assert rejected.status_code==410 and len(calls)==count


def test_post_query_packing_keeps_current_facts_and_parent_dependency_without_old_text():
    from app.services.assistant.runtime import fit_context, context_size
    from app.services.assistant.evidence import RunContent
    original = dict(kind='business',source_id='parent-source',run_id='child',title='原查询',scope={'factory_id':'huakang-a'})
    omitted = dict(kind='business',source_id='unused-old-source',run_id='child',title='更早资料')
    fresh = dict(kind='business',source_id='fresh',run_id='child',title='新查询')
    content = RunContent('child','off')
    for source in (original,omitted,fresh): content.add_source(source)
    packing = dict(prefix=[dict(role='system',content='应用指令')],groups=[
        (1,[dict(role='user',content='旧问题'),dict(role='assistant',content='旧长回答'*500)],[original,omitted]),
        (3,[dict(role='user',content='本轮修订问题')],[original])])
    facts=dict(role='system',content='本轮完整范围：共3条，剩余900；未知不为零；厂区华康A；新时点。'*35)
    window=dict(character_budget=3500,first_seq=1,omitted_turns=0)
    packed=fit_context(packing,[facts],content,window)
    assert context_size(packed)<=3500 and facts in packed
    assert not any('旧长回答' in str(record['content']) for record in packed)
    assert window['first_seq']==3 and window['omitted_turns']==1
    assert {s['source_id'] for s in content.evidence['sources']}=={'parent-source','fresh'}


def test_proven_pre_provider_failure_uses_zero_but_unknown_attempt_still_reserves(env):
    from app.services.assistant import runtime
    from app.services.assistant.errors import AssistantError
    from app.models.assistant import AssistantRun, AssistantSession
    client, dbm, calls, patch = env
    migrate(dbm)
    sid=session(client)
    def too_large(*args,**kwargs):
        raise AssistantError('context_too_large','合成上下文超限')
    patch.setattr(runtime,'history',too_large)
    result=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2))
    assert 'run.failed' in result.text and not calls
    with dbm.SessionLocal() as db:
        run=db.scalar(select(AssistantRun).where(AssistantRun.session_id==sid))
        row=db.get(AssistantSession,sid)
        assert run.context_window['provider_attempt_state']=='not_started'
        assert run.usage is None and row.budget_tokens==0 and not row.budget_unknown
        # Historical missing markers remain conservative. Never infer zero from
        # a null usage or retrospectively erase accounting for an unknown call.
        from app.services.assistant.service import account_usage
        run.context_window={'reserved_tokens':1234}
        account_usage(db,run)
        assert row.budget_tokens==1234
