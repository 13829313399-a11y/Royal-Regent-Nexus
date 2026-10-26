"""Native UV commands and HTTP readers over disposable synthetic databases."""
from dataclasses import replace
import json

import pytest
from sqlalchemy import event
from test_assistant_api import env, session, payload


def setup(env):
    from app.models import uv_operations as m
    from app.services import auth
    from app.core.config import settings
    from test_uv_ops import user_with
    from app.services.permission_codes import UV_OPS_PERMISSION_CODES
    client, dbm, calls, patch = env
    patch.setattr(settings, 'uv_ops_enabled', True)
    patch.setattr(settings, 'authz_mode', 'enforce')
    m.Base.metadata.create_all(dbm.engine, tables=[t for t in m.Base.metadata.sorted_tables if t.name.startswith('uv_ops_')])
    with dbm.SessionLocal() as db:
        if db.get(m.UvOpsSettings, m.FACTORY) is None:
            db.add(m.UvOpsSettings(id=m.FACTORY, data_mode='synthetic'))
        db.commit()
    user = user_with(*(code.split(':')[1] for code in UV_OPS_PERMISSION_CODES))
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    return client, dbm, calls, user


def query(user, **args):
    from app.services.assistant.uv import query as read
    return read(user, dict(factory_id='huakang-a', **args), 'synthetic-uv-read')


def native(client, path):
    response = client.get('/api/uv-operations/' + path, params={'factory_id': 'huakang-a'})
    assert response.status_code == 200, response.text
    return response.json()


def test_biz007_full_scope_totals_match_native_http_and_page_details_without_writes(env):
    from test_uv_ops import setup_task, confirm, user_with
    client, dbm, calls, _ = setup(env)
    ids = []
    for qty, good in ((100, 40), (80, 0), (60, 0), (50, 50), (20, 20)):
        data = setup_task(client, quantity=qty)
        ids.append(data['task']['id'])
        if good:
            confirm(client, data, good=good, rework=0)
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, 'before_cursor_execute', capture)
    try:
        reader = user_with('read')
        result, source, actions = query(reader, limit=2)
        assert {key: value['value'] for key, value in result['metrics'].items()} == dict(
            tasks=5, original_tasks=5, rework_tasks=0, cancelled_tasks=0,
            planned=310, completed=110, remaining=200, scrap=0, incomplete_tasks=3,
            overdue_tasks=None, material_shortage=None)
        assert result['truncated'] and result['total_count'] == 5
        assert result['status'] == 'partial' and result['observed_at'] is None
        assert result['scope']['filters']['source_data_mode'] == 'synthetic'
        assert len(actions) == len(result['rows']) == len(result['allowed_actions'])
        assert all(a['route_name'] == 'uv-planning' and a['query'] == dict(factory='huakang-a', uv_task=r['id'])
                   and a['resource']['resource_id'] == r['id'] for a, r in zip(actions, result['rows']))
        items = list(result['rows'])
        page = result
        while page['next_cursor']:
            page, _, _ = query(reader, limit=2, cursor=page['next_cursor'])
            assert page['metrics'] == result['metrics']
            items.extend(page['rows'])
        assert {item['id'] for item in items} == set(ids)
        assert sum(item['quantity'] for item in items) == 310
        assert sum(batch['good'] for item in items for batch in item['batches']) == 110
        from app.services.assistant import uv
        for item in items:
            original = native(client, 'tasks/' + item['id'])['data']
            selected, selected_source, _ = query(reader, resource_id=item['id'])
            assert selected['rows'] == [item]
            assert selected['scope']['resource_refs'] == [f"uv-operations:task:{item['id']}"]
            assert {key: item[key] for key in uv.TASK_FIELDS} == {key: original[key] for key in uv.TASK_FIELDS}
            assert item['batches'] == [{key: batch[key] for key in uv.BATCH_FIELDS}
                                       for batch in sorted(original['batches'], key=lambda b: b['id'])]
            with dbm.SessionLocal() as db: assert uv.visible(db, reader, selected_source)
        encoded = json.dumps([result, source], ensure_ascii=False)
        for private in ('cost_price_snapshot', 'payroll_policy_snapshot', 'process_snapshot', 'created_by', 'first_article_evidence'):
            assert private not in encoded
        assert not any(s.lstrip().split(None, 1)[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'} for s in statements)
    finally:
        event.remove(dbm.engine, 'before_cursor_execute', capture)
    assert not calls


def test_multiple_passes_rework_and_scrap_never_duplicate_physical_quantity(env):
    from test_uv_ops import setup_task, confirm, post, user_with
    client, _, calls, _ = setup(env)
    data = setup_task(client, quantity=101, passes=2)
    first = confirm(client, data, good=101, rework=0)
    reader = user_with('read')
    result, _, _ = query(reader)
    assert result['metrics']['completed']['value'] == 0
    assert result['metrics']['remaining']['value'] == 101
    data['batch'] = post(client, 'batches/' + data['batch']['id'] + '/advance-pass', expected_version=first['batch']['version'])
    second = confirm(client, data, good=95, rework=5, scrap=1)
    data['batch'] = second['batch']
    rework = post(client, 'rework-tasks', batch_id=data['batch']['id'], expected_version=data['batch']['version'], code='SYN-RW', quantity=5)
    result, _, _ = query(reader)
    assert result['metrics']['tasks']['value'] == 2
    assert result['metrics']['planned']['value'] == 101
    assert result['metrics']['completed']['value'] == 95
    assert result['metrics']['remaining']['value'] == 5
    assert result['metrics']['scrap']['value'] == 1
    selected, _, _ = query(reader, resource_id=rework['id'])
    assert selected['rows'][0]['batch_scope'] == 'bound_original_batches'
    assert selected['metrics']['completed']['value'] is None
    assert selected['metrics']['incomplete_tasks']['value'] is None
    data['task'] = rework
    confirm(client, data, good=5, rework=0, source_bucket='rework')
    result, _, _ = query(reader)
    assert result['metrics']['completed']['value'] == 100
    assert result['metrics']['remaining']['value'] == 0
    assert result['metrics']['incomplete_tasks']['value'] == 0
    assert result['metrics']['scrap']['value'] == 1
    assert not calls


@pytest.mark.parametrize('mode', ['legacy', 'shadow', 'enforce'])
def test_native_authority_and_feature_gate_in_every_platform_mode(env, mode):
    from app.core.config import settings
    from app.services.assistant.errors import AssistantError
    from test_uv_ops import user_with
    _, _, calls, _ = setup(env)
    env[3].setattr(settings, 'authz_mode', mode)
    for user in (user_with(), user_with('read', factory='huakang-b')):
        with pytest.raises(AssistantError) as error: query(user)
        assert error.value.status_code == 403
    for factory in ('group', '', 'huakang-b', 'huaxing'):
        with pytest.raises(AssistantError) as error:
            from app.services.assistant.uv import query as read
            read(user_with('read'), dict(factory_id=factory), 'invalid-factory')
        assert error.value.status_code == 422
    env[3].setattr(settings, 'uv_ops_enabled', False)
    with pytest.raises(AssistantError) as error: query(user_with('read'))
    assert error.value.status_code == 503 and error.value.detail['code'] == 'module_disabled'
    assert not calls


def test_empty_missing_arguments_schema_and_explicit_registered_dispatch(env):
    from app.models import uv_operations as m
    from app.services.assistant import uv, registry
    from app.services.assistant.errors import AssistantError
    from test_uv_ops import user_with
    _, dbm, calls, _ = setup(env)
    reader = user_with('read')
    result, _, _ = query(reader)
    assert result['status'] == 'empty' and result['total_count'] == 0
    assert result['metrics']['planned']['value'] == 0
    assert result['metrics']['overdue_tasks']['value'] is None
    for args in ({'resource_id': 'missing'}, {'resource_id': ' x'}, {'limit': True},
                 {'limit': 51}, {'status': 'completed'}, {'cursor': 'bad'},
                 {'resource_id': 'x', 'cursor': 'bad'}):
        with pytest.raises(AssistantError) as error: query(reader, **args)
        assert error.value.status_code in (404, 422)
    assert registry.BY_MODULE[uv.MODULE].callable
    assert registry.BY_MODULE[uv.MODULE].coverage_state == 'implemented_unverified'
    with dbm.SessionLocal() as db:
        db.delete(db.get(m.UvOpsSettings, m.FACTORY)); db.commit()
    with pytest.raises(AssistantError) as error: query(reader)
    assert error.value.detail['code'] == 'schema_not_ready'
    assert not calls


def test_cursor_revision_identity_and_evidence_visibility(env):
    from app.services.assistant import uv
    from app.services.assistant.errors import AssistantError
    from test_uv_ops import setup_task, post, user_with
    client, dbm, calls, _ = setup(env)
    setup_task(client, quantity=3)
    setup_task(client, quantity=4)
    reader = user_with('read')
    result, source, _ = query(reader, limit=1)
    with pytest.raises(AssistantError) as error:
        query(replace(reader, authorization_version=reader.authorization_version + 1), cursor=result['next_cursor'])
    assert error.value.detail['code'] == 'cursor_invalid'
    with dbm.SessionLocal() as db:
        assert uv.visible(db, reader, source)
        assert not uv.visible(db, replace(reader, authorization_version=reader.authorization_version + 1), source)
        assert not uv.visible(db, reader, {**source, 'resources': [dict(module_id='internal-quote', resource_type='task', resource_id=result['rows'][0]['id'])]})
        assert not uv.visible(db, reader, {**source, 'resources': [dict(module_id=uv.MODULE, resource_type='task', resource_id='missing')]})
        with pytest.raises(AssistantError): uv.visible(db, user_with(), source)
    post(client, 'machines', code='SYN-REVISION', name='合成版本更新')
    with pytest.raises(AssistantError) as error: query(reader, cursor=result['next_cursor'])
    assert error.value.detail['code'] == 'cursor_invalid'
    assert not calls


def test_cancelled_tasks_and_incomplete_batch_denominator_are_explicit(env):
    from app.models import uv_operations as m
    from test_uv_ops import setup_task, post, user_with
    client, dbm, calls, _ = setup(env)
    cancelled = setup_task(client, quantity=20)
    active = setup_task(client, quantity=30)
    post(client, 'tasks/' + cancelled['task']['id'] + '/cancel', expected_version=cancelled['task']['version'], reason='合成取消验证')
    reader = user_with('read')
    result, _, _ = query(reader)
    assert result['metrics']['tasks']['value'] == 2
    assert result['metrics']['cancelled_tasks']['value'] == 1
    assert result['metrics']['planned']['value'] == result['metrics']['remaining']['value'] == 30
    # Disposable corruption fixture models an incomplete imported/legacy family.
    # No production reader may invent a full zero from a missing active batch.
    with dbm.SessionLocal() as db:
        batch = db.get(m.UvOpsBatch, active['batch']['id'])
        batch.active = False
        db.commit()
    result, _, _ = query(reader, resource_id=active['task']['id'])
    assert result['metrics']['planned']['value'] == 30
    for key in ('completed', 'remaining', 'scrap', 'incomplete_tasks'):
        assert result['metrics'][key]['value'] is None
    assert any(value['field'] == 'physical_progress' for value in result['unknown_fields'])
    assert not calls


def runtime_setup(env):
    from app.models.auth import AuthUser
    from app.services.assistant import runtime
    from test_assistant_v2 import migrate
    client, dbm, calls, user = setup(env)
    with dbm.SessionLocal() as db:
        db.add(AuthUser(id=user.id, username='synthetic-uv-reader', display_name='合成UV读取',
            password_salt='unused', password_hash='unused', status='active'))
        db.commit()
    migrate(dbm)
    env[3].setattr(runtime, 'authenticate', lambda request: user)
    return client, dbm, calls, user


def test_runtime_native_selection_snapshot_history_and_typed_action_resolver(env):
    from copy import deepcopy
    from app.models.assistant import AssistantMessage
    from app.services import auth
    from app.services.assistant import runtime
    from test_uv_ops import setup_task, confirm, user_with
    client, dbm, calls, user = runtime_setup(env)
    data = setup_task(client, quantity=100)
    confirm(client, data, good=40, rework=0)
    sid = session(client)
    page = dict(module_id='uv-operations', route_name='uv-planning', factory_id='huakang-a')
    selected = dict(selection_id='uv-native-task', resources=[dict(module_id='uv-operations', resource_type='task', resource_id=data['task']['id'])],
        filters=dict(factory_id='huakang-a', view='tasks'))
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2,
        intent='my_work', web_search='off', page_context=page, context_selection=selected))
    assert 'event: run.completed' in response.text, response.text[-2500:]
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in answer['content_parts'] if p['type']=='business_snapshot')
    assert result['metrics']['completed']['value']==40 and result['total_count']==1
    assert result['scope']['resource_refs']==['uv-operations:task:'+data['task']['id']]
    actions = next(p['items'] for p in answer['content_parts'] if p['type']=='actions')
    index = next(i for i, action in enumerate(actions) if action['type']=='open_record')
    response = client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index))
    assert response.status_code==200, response.text
    assert response.json()['query']==dict(factory='huakang-a',uv_task=data['task']['id'])
    assert response.json()['route_name']=='uv-planning' and response.json()['params']=={}
    history, _ = runtime.history(user, sid, 'future-run', [])
    assert any(m['role']=='system' and '历史业务快照' in m['content'] for m in history)
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code==200
    assert len(calls)==1  # deterministic provider replay, never a paid request
    assert 'cost_price_snapshot' not in json.dumps(calls,ensure_ascii=False)
    artifact = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(
        source_run_id=answer['run_id'], title='UV来源验收', kind='markdown', content='合成UV生产事实'))
    assert artifact.status_code == 200, artifact.text
    artifact_id = artifact.json()['id']
    original = deepcopy(answer['content_parts'])
    for patch, expected in [
        (dict(query=dict(factory='huakang-a', uv_task=data['task']['id'], task=data['task']['id'])), 422),
        (dict(params=dict(taskId=data['task']['id'])), 422),
        (dict(resource=dict(module_id='uv-operations', resource_type='task', resource_id='different')), 410),
        (dict(query=dict(factory='huakang-a', uv_task='missing'),
              resource=dict(module_id='uv-operations', resource_type='task', resource_id='missing')), 410),
        (dict(query=dict(factory='huakang-b', uv_task=data['task']['id'])), 422),
    ]:
        with dbm.SessionLocal() as db:
            parts = deepcopy(original)
            next(p['items'] for p in parts if p['type']=='actions')[index].update(patch)
            db.get(AssistantMessage, answer['id']).content_parts = parts
            db.commit()
        resolved = client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index))
        assert resolved.status_code == expected, resolved.text
    with dbm.SessionLocal() as db:
        db.get(AssistantMessage, answer['id']).content_parts = original
        db.commit()
    revoked = user_with()
    client.app.dependency_overrides[auth.get_current_user] = lambda: revoked
    env[3].setattr(runtime, 'authenticate', lambda request: revoked)
    hidden = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    assert hidden['unavailable'] and data['task']['id'] not in json.dumps(hidden['content_parts'])
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code == 410
    assert client.get(f'/api/assistant/artifacts/{artifact_id}/export').status_code == 410
    assert client.post('/api/assistant/actions/resolve', json=dict(run_id=answer['run_id'], index=index)).status_code == 410
    assert len(calls) == 1


def test_uv_unbound_page_and_failed_selection_stop_before_query_or_provider(env):
    from app.services.assistant import business
    client, _, calls, _ = runtime_setup(env)
    def prohibited(*args, **kwargs): pytest.fail('Unverified native scope must not query a business tool')
    env[3].setattr(business, 'query', prohibited)
    for route, filters in [('uv-live', {}), ('uv-planning', dict(view='tasks',scope_error='任务读取失败'))]:
        sid = session(client)
        response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2,
            intent='my_work', web_search='off', page_context=dict(module_id='uv-operations', route_name=route, factory_id='huakang-a'),
            context_selection=dict(selection_id='invalid',resources=[],filters=dict(factory_id='huakang-a',**filters))))
        assert 'event: run.failed' in response.text and 'context_unavailable' in response.text, response.text[-2500:]
    assert not calls
