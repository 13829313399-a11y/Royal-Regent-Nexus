"""Same-authority native HTTP comparisons, no model/network acceptance claims."""
import json

import pytest
from sqlalchemy import event
from test_assistant_api import env, session, payload
from test_work_center_api import actor


def seed(env):
    from app.models.auth import SystemNotification
    from app.models.work_center import WorkCenterUserState
    from app.services import auth
    from app.services.work_center import service as work
    from app.services.assistant import runtime
    client, dbm, _, patch = env
    user = actor('alice')
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    patch.setattr(runtime, 'authenticate', lambda request: user)
    with dbm.SessionLocal() as db:
        for index in range(42):
            db.add(SystemNotification(id=f'SYN-V3-WORK-{index:03}', type='identity_changed', target_user_id='alice',
                title='Synthetic work acceptance', created_at='2026-10-23 08:00:00'))
        db.add(SystemNotification(id='SYN-FOREIGN', type='identity_changed', target_user_id='bob', created_at='2026-10-23 08:00:00'))
        db.commit()
        all_items = work.snapshot(db, user, view='info', limit=50)['items']
        assert len(all_items)==42
        for item in all_items[:16]:
            db.add(WorkCenterUserState(user_id='alice', employment_epoch=1, entry_id=item['id'], read_version=item['content_version']))
        db.commit()
    return client, dbm, user, patch


def query(user, **arguments):
    from app.services.assistant import business
    return business.query(user, 'get_my_work', {'factory_id': 'authorized', **arguments}, 'synthetic-work-run')


def test_full_filter_count_cursor_native_detail_and_no_personal_writes(env):
    client, dbm, user, _ = seed(env)
    statements=[]
    def capture(conn,cursor,statement,*args): statements.append(statement)
    event.listen(dbm.engine,'before_cursor_execute',capture)
    try:
        result, source, actions = query(user, view='info', unread_only=True)
        native = client.get('/api/work-center/snapshot', params=dict(view='info', unread_only=True, limit=20)).json()
        whole = client.get('/api/work-center/snapshot', params=dict(view='info', limit=20)).json()
    finally:
        event.remove(dbm.engine,'before_cursor_execute',capture)
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE')) for s in statements)
    assert whole['query']['filtered_total']==42
    assert native['query']['filtered_total']==result['total_count']==result['metrics']['filtered_count']['value']==26
    assert result['returned_count']==20 and result['truncated'] and result['next_cursor']
    assert [x['id'] for x in result['rows']]==[x['id'] for x in native['items']]
    assert 'SYN-FOREIGN' not in json.dumps(result) and not any('actions' in row for row in result['rows'])
    rest, _, _=query(user,view='info',unread_only=True,cursor=result['next_cursor'])
    assert rest['returned_count']==6 and rest['total_count']==26 and not rest['next_cursor']
    assert not set(x['id'] for x in result['rows']) & set(x['id'] for x in rest['rows'])
    assert actions[0]['query']==dict(factory='authorized',view='info',unread='1')
    selected, _, _=query(user,resource_id=result['rows'][0]['id'])
    assert selected['total_count']==1 and selected['scope']['coverage']=='selected_resources'
    assert set(selected['metrics'])=={'filtered_count'}
    assert result['as_of']==source['as_of'] and result['as_of'].endswith('+08:00')
    assert client.get('/api/work-center/snapshot',params=dict(view='info',unread_only=True)).json()['query']['filtered_total']==26


def test_strict_scope_cursor_and_source_health_unknown(env):
    from app.services.assistant.errors import AssistantError
    from app.services.work_center import service as work
    client, _, user, patch=seed(env)
    result, _, _=query(user,view='info',unread_only=True)
    for args in ({'limit':True},{'view':'anything'},{'unread_only':'true'},{'sql':'SELECT *'},{'resource_id':result['rows'][0]['id'],'view':'info'}):
        with pytest.raises(AssistantError): query(user,**args)
    with pytest.raises(Exception): query(user,view='info',q='changed',cursor=result['next_cursor'])
    with pytest.raises(AssistantError): query(user,factory_id='huakang-a',resource_id=result['rows'][0]['id'])
    original=work.snapshot
    def partial(*args,**kwargs):
        value=original(*args,**kwargs)
        value['health'].update(status='partial',unavailable_sources=['synthetic_unavailable_source'])
        return value
    patch.setattr(work,'snapshot',partial)
    unknown, _, _=query(user,view='info',q='absent')
    assert unknown['status']=='partial' and unknown['total_count'] is None
    assert unknown['metrics']['filtered_count']['value'] is None and unknown['freshness']['state']=='unknown'


def test_runtime_stores_work_snapshot_and_resolves_filtered_list(env):
    from app.core.config import settings
    from app.services.assistant import runtime
    client, _, user, _=seed(env)
    settings.assistant_context_character_budget=24000
    sid=session(client)
    body=payload(protocol_version=2,intent='my_work',web_search='off',page_context=dict(module_id='work-center',route_name='notification-center'))
    body['text']='我的未读事项一共多少？请按当前筛选核对完整总数与本页返回数，说明是否还有下一页，并提供打开当前原列表的入口。'
    body['context_selection']=dict(selection_id='work-filter',resources=[],filters=dict(factory_id='authorized',view='info',unread_only=True))
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=body)
    assert 'event: run.completed' in response.text, response.text[-1200:]
    message=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    snapshot=next(p['result'] for p in message['content_parts'] if p['type']=='business_snapshot')
    assert snapshot['total_count']==26 and snapshot['returned_count']==20 and snapshot['tool_call_id']=='prequery-0'
    call=env[2][0]
    supplied=next(m['content'] for m in call['messages'] if isinstance(m['content'],str) and m['content'].startswith('已受权业务快照'))
    assert json.loads(supplied.split('：',1)[1]) == snapshot
    assert runtime.context_size(call['messages']) <= 22000
    citation_text=next(m['content'] for m in call['messages'] if isinstance(m['content'],str) and m['content'].startswith('本轮可用来源'))
    assert 'authorization_fingerprint' not in citation_text
    stored_source=next(p for p in message['content_parts'] if p['type']=='evidence')['sources'][-1]
    assert len(stored_source['resources'])==20 and stored_source['authorization_fingerprint']
    actions=next(p['items'] for p in message['content_parts'] if p['type']=='actions')
    index=next(i for i,a in enumerate(actions) if a['label']=='打开当前事项列表')
    resolved=client.post('/api/assistant/actions/resolve',json=dict(run_id=message['run_id'],index=index))
    assert resolved.status_code==200 and resolved.json()['query']['unread']=='1'
    entry_index=next(i for i,a in enumerate(actions) if a.get('query',{}).get('entry'))
    entry_action=dict(run_id=message['run_id'],index=entry_index)
    assert client.post('/api/assistant/actions/resolve',json=entry_action).status_code==200
    # Historical answers and their record links lose visibility with the source.
    from app.models.auth import SystemNotification
    _, dbm, _, _=env
    with dbm.SessionLocal() as db:
        row=db.get(SystemNotification, snapshot['rows'][0]['id'].split(':')[1])
        row.target_user_id='bob';db.commit()
    assert client.post('/api/assistant/actions/resolve',json=entry_action).status_code==410
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']
