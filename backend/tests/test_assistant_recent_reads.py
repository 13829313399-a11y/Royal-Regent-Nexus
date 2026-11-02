"""Real cache reuse, original clocks and native authority on disposable data."""
from types import SimpleNamespace
import json
import pytest
from sqlalchemy.exc import OperationalError
from test_assistant_native_boundaries import native_boundary
from test_assistant_api import env,session,payload
from assistant_v3_support import ReplayTransport


def native_user(dbm,name='alice'):
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    with dbm.SessionLocal() as db:return build_auth_context(db,db.get(AuthUser,name))


def order(user,rid='recent-run',*,recent=False,**arguments):
    from app.services.assistant import business
    return business.query(user,'list_customer_orders',{'factory_id':'huakang-a',**arguments},rid,
        tool_call_id='call-'+rid,step_id='step-'+rid,reuse_recent=recent)


def watch(native_boundary):
    from app.services import customer_order_queries as reader
    _,dbm,_,patch=native_boundary
    original=reader.progress;queries=[]
    def observed(*args,**kwargs):
        queries.append(1)
        return original(*args,**kwargs)
    patch.setattr(reader,'progress',observed)
    return dbm,patch,queries


def test_lru_deepcopies_does_not_renew_ttl_and_caps_lifetime():
    from app.services.assistant.recent_reads import RecentReads
    tick=[0.0];cache=RecentReads(entries=2,owner_entries=1,clock=lambda:tick[0])
    key=(('db','alice'),'scope','query')
    original={'rows':[{'value':1}]}
    assert cache.put(key,original,ttl=999)
    original['rows'][0]['value']=8
    returned=cache.get(key);assert returned['rows'][0]['value']==1
    returned['rows'][0]['value']=9
    tick[0]=29;assert cache.get(key)['rows'][0]['value']==1
    tick[0]=30;assert cache.get(key) is None
    a=(('db','alice'),'scope','a');b=(('db','alice'),'scope','b')
    c=(('db','bob'),'scope','c');d=(('db','other'),'scope','d')
    assert cache.put(a,1) and cache.put(b,2) and cache.get(a) is None
    assert cache.put(c,3) and cache.put(d,4) and cache.get(b) is None
    assert cache.get(c)==3 and cache.get(d)==4


def test_byte_bounds_and_oversized_refresh_remove_previous_value():
    from app.services.assistant.recent_reads import RecentReads
    cache=RecentReads(bytes_limit=20,owner_bytes=16)
    first=(('db','alice'),'scope','first');second=(('db','alice'),'scope','second')
    assert cache.put(first,{'n':'12345'}) and cache.put(second,{'n':'67890'})
    assert cache.get(first) is None
    other=(('db','bob'),'scope','first')
    assert cache.put(other,{'n':'54321'}) and cache.get(second) is None
    assert not cache.put(other,{'n':'x'*40}) and cache.get(other) is None


@pytest.mark.parametrize('text',['当前订单','现在呢','今天待处理','刷新一下','最新情况','剩余多少','和上次比','之前有变化吗','Compare orders','refresh the view'])
def test_strict_current_comparison_and_refresh_never_use_recent(text):
    from app.services.assistant.recent_reads import allowed_for
    assert not allowed_for(SimpleNamespace(intent='chat',relation=None,context_selection=None,text=text))


def test_server_policy_excludes_prequery_relations_and_frozen_selection():
    from app.services.assistant.recent_reads import allowed_for
    base=dict(intent='chat',relation=None,context_selection=None,text='列出订单')
    assert allowed_for(SimpleNamespace(**base))
    for changes in ({'intent':'my_work'},{'relation':object()},{'context_selection':object()}):
        assert not allowed_for(SimpleNamespace(**{**base,**changes}))


def test_native_cache_hit_preserves_origin_and_rebinds_current_run_sources(native_boundary):
    from app.services.assistant import orders
    dbm,patch,queries=watch(native_boundary);user=native_user(dbm)
    first,source,actions=order(user,'origin')
    patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:10+00:00')
    hit,new_source,new_actions=order(user,'later',recent=True)
    assert len(queries)==1 and hit['freshness']['cache_hit']
    assert hit['freshness']['cache_created_at']==first['retrieved_at']
    assert all(hit[k]==first[k] for k in ('as_of','observed_at','business_date','metrics','rows','scope','total_count'))
    assert hit['requested_at']==hit['retrieved_at']=='2026-10-23T09:00:10+08:00'
    assert hit['run_id']=='later' and hit['tool_call_id']=='call-later' and hit['step_id']=='step-later'
    assert new_source['run_id']=='later' and new_source['source_id']!=source['source_id']
    assert hit['source_refs']==[new_source['source_id']] and new_source['as_of']==source['as_of']
    assert new_actions==actions and hit['allowed_actions']!=first['allowed_actions']
    hit['metrics']['remaining_quantity']['value']='666'
    again,_,_=order(user,'third',recent=True)
    assert again['metrics']['remaining_quantity']['value']=='900' and first['metrics']['remaining_quantity']['value']=='900'
    assert again['freshness']['cache_created_at']==first['retrieved_at'] and len(queries)==1


def test_native_filter_cursor_user_epoch_and_permission_cannot_share_cache(native_boundary):
    from app.models.auth import AuthUserRole,EmployeeProfile,AuthRolePermission
    from app.services.assistant.errors import AssistantError
    dbm,_,queries=watch(native_boundary);alice=native_user(dbm)
    order(alice,'all')
    filtered,_,_=order(alice,'filtered',recent=True,customer_code='FILTER-A',limit=1)
    assert not filtered['freshness']['cache_hit'] and filtered['total_count']==2
    page2,_,_=order(alice,'page2',recent=True,customer_code='FILTER-A',limit=1,cursor=filtered['next_cursor'])
    assert not page2['freshness']['cache_hit'] and page2['rows'][0]['id']=='SYN-O-A003'
    page2_again,_,_=order(alice,'page2-again',recent=True,customer_code='FILTER-A',limit=1,cursor=filtered['next_cursor'])
    assert page2_again['freshness']['cache_hit'] and len(queries)==3
    with dbm.SessionLocal() as db:
        db.add(AuthUserRole(id='closure-bob-read',user_id='bob',role_id='closure-order',factory_id='huakang-a',department='sales-business'))
        db.commit()
    bob_result,_,_=order(native_user(dbm,'bob'),'bob',recent=True)
    assert not bob_result['freshness']['cache_hit'] and len(queries)==4
    with dbm.SessionLocal() as db:
        db.get(EmployeeProfile,'alice').employment_epoch=2;db.commit()
    new_epoch,_,_=order(native_user(dbm),'new-epoch',recent=True)
    assert not new_epoch['freshness']['cache_hit'] and len(queries)==5
    with dbm.SessionLocal() as db:
        db.get(EmployeeProfile,'alice').employment_epoch=1;db.commit()
    restored,_,_=order(native_user(dbm),'restored-epoch',recent=True)
    assert not restored['freshness']['cache_hit'] and len(queries)==6
    with pytest.raises(AssistantError) as failure:order(native_user(dbm),'foreign',recent=True,factory_id='huakang-b')
    assert failure.value.status_code==403
    with dbm.SessionLocal() as db:
        db.delete(db.get(AuthRolePermission,'closure-order-read'));db.commit()
    with pytest.raises(AssistantError) as failure:order(native_user(dbm),'revoked',recent=True)
    assert failure.value.status_code==403 and len(queries)==6


def test_deleted_source_forces_native_refresh_instead_of_cached_totals(native_boundary):
    from app.models.customer_order_ledger import OrderLedgerLine
    dbm,_,queries=watch(native_boundary);user=native_user(dbm)
    original,_,_=order(user)
    with dbm.SessionLocal() as db:
        db.delete(db.get(OrderLedgerLine,'SYN-O-A001'));db.commit()
    fresh,_,_=order(user,'after-delete',recent=True)
    assert not fresh['freshness']['cache_hit'] and len(queries)==2
    assert fresh['total_count']==2 and fresh['metrics']['remaining_quantity']['value']=='500'
    assert original['total_count']==3 and original['metrics']['remaining_quantity']['value']=='900'


@pytest.mark.parametrize('clock',['2026-10-23T01:00:31+00:00','2026-10-23T00:59:59+00:00'])
def test_expired_or_future_snapshot_is_not_relabelled_fresh(native_boundary,clock):
    from app.services.assistant import orders
    dbm,patch,queries=watch(native_boundary);user=native_user(dbm)
    original,_,_=order(user)
    patch.setattr(orders,'now_iso',lambda:clock)
    fresh,_,_=order(user,'new-clock',recent=True)
    assert not fresh['freshness']['cache_hit'] and fresh['as_of']!=original['as_of'] and len(queries)==2


def test_strict_read_replaces_recent_snapshot_and_failed_refresh_cannot_leave_old_hit(native_boundary):
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.services import customer_order_queries as reader
    from app.services.assistant import orders
    dbm,patch,queries=watch(native_boundary);user=native_user(dbm)
    old,_,_=order(user)
    with dbm.SessionLocal() as db:
        db.get(OrderLedgerLine,'SYN-O-A001').shipped_quantity=700;db.commit()
    patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:10+00:00')
    recent,_,_=order(user,'recent',recent=True)
    assert recent['freshness']['cache_hit'] and recent['metrics']['remaining_quantity']['value']=='900'
    strict,_,_=order(user,'strict')
    assert not strict['freshness']['cache_hit'] and strict['metrics']['remaining_quantity']['value']=='800'
    newer,_,_=order(user,'newer',recent=True)
    assert newer['freshness']['cache_hit'] and newer['metrics']==strict['metrics'] and old['metrics']['remaining_quantity']['value']=='900'
    observed=reader.progress
    def failed(*args,**kwargs):raise OperationalError('PRIVATE-SQL',{},Exception('PRIVATE-ERROR'))
    patch.setattr(reader,'progress',failed)
    with pytest.raises(OperationalError):order(user,'failed-refresh')
    patch.setattr(reader,'progress',observed)
    after_error,_,_=order(user,'after-error',recent=True)
    assert not after_error['freshness']['cache_hit'] and len(queries)==3


def sse(values):
    return ''.join('data: '+json.dumps(value,ensure_ascii=False)+'\n\n' for value in values)+'data: [DONE]\n\n'


def test_runtime_tool_reuses_recent_then_current_words_query_native_again(native_boundary):
    from app.services.assistant import provider,orders
    from app.core.config import settings
    from app.models.customer_order_ledger import OrderLedgerLine
    dbm,patch,queries=watch(native_boundary);client=native_boundary[0]
    patch.setattr(settings,'assistant_max_tool_rounds',1)
    tools=sse([dict(choices=[dict(delta={'tool_calls':[dict(index=0,id='native-order-call',type='function',
        function={'name':'list_customer_orders','arguments':json.dumps({'factory_id':'huakang-a'})})]},finish_reason='tool_calls')])])
    answer=sse([dict(choices=[dict(delta={'content':'按业务快照核对。'},finish_reason='stop')]),dict(choices=[],usage={'total_tokens':12})])
    replay=ReplayTransport([tools,answer]*3)
    patch.setattr(provider,'open_stream',replay.open)
    snapshots=[]
    for index,text in enumerate(('列出订单','列出订单','现在还有多少订单？')):
        if index==1:patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:10+00:00')
        if index==2:
            with dbm.SessionLocal() as db:
                db.get(OrderLedgerLine,'SYN-O-A001').shipped_quantity=700;db.commit()
            patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:20+00:00')
        sid=session(client)
        response=client.post(f'/api/assistant/sessions/{sid}/messages',json={**payload(protocol_version=2,web_search='off'),'text':text})
        assert 'event: run.completed' in response.text,response.text[-2000:]
        messages=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
        result=next(p['result'] for p in messages[-1]['content_parts'] if p['type']=='tool_result' and p['name']=='list_customer_orders')
        snapshots.append(result)
    assert [r['freshness']['cache_hit'] for r in snapshots]==[False,True,False]
    assert snapshots[1]['as_of']==snapshots[0]['as_of'] and snapshots[1]['retrieved_at']!=snapshots[0]['retrieved_at']
    assert snapshots[0]['metrics']['remaining_quantity']['value']==snapshots[1]['metrics']['remaining_quantity']['value']=='900'
    assert snapshots[2]['metrics']['remaining_quantity']['value']=='800'
    assert len(queries)==2 and len(replay.calls)==6 and not replay.frames
    assert len({r['source_refs'][0] for r in snapshots})==3
    replay.assert_private_absent(['PRIVATE-B-TITLE-CANARY','SYN-O-B001','PRIVATE-EXTENSION-CANARY'])


def test_cached_answer_artifact_and_export_revalidate_native_sources(native_boundary):
    from io import StringIO
    import csv
    from app.models.auth import AuthRolePermission
    from app.services.assistant import provider,orders
    from app.core.config import settings
    from test_assistant_v2 import migrate
    dbm,patch,queries=watch(native_boundary);client=native_boundary[0]
    migrate(dbm)
    original,_,_=order(native_user(dbm),'prime')
    patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:10+00:00')
    patch.setattr(settings,'assistant_max_tool_rounds',1)
    tools=sse([dict(choices=[dict(delta={'tool_calls':[dict(index=0,id='cached-export',type='function',
        function={'name':'list_customer_orders','arguments':json.dumps({'factory_id':'huakang-a'})})]},finish_reason='tool_calls')])])
    answer=sse([dict(choices=[dict(delta={'content':'缓存快照可核对。'},finish_reason='stop')]),dict(choices=[],usage={'total_tokens':12})])
    replay=ReplayTransport([tools,answer]);patch.setattr(provider,'open_stream',replay.open)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,web_search='off'))
    assert 'event: run.completed' in response.text,response.text[-1500:]
    message=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    cached=next(p['result'] for p in message['content_parts'] if p['type']=='tool_result')
    assert cached['freshness']['cache_hit'] and len(queries)==1
    saved=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=message['run_id'],kind='table',
        title='近期订单核对',content='CACHED_EXPORT_NOTE_CANARY：人工说明不改原数量。'))
    assert saved.status_code==200,saved.text
    artifact=saved.json();datasets=artifact['datasets']
    assert len(datasets)==1,'A cached business tool result must retain its real dataset in the saved artifact'
    dataset=datasets[0]
    assert dataset['as_of']==original['as_of']==cached['as_of']
    assert dataset['retrieved_at']==cached['retrieved_at'] and dataset['source_ids']==cached['source_refs']
    assert dataset['total_count']==3 and next(m['value'] for m in dataset['metrics'] if m['key']=='remaining_quantity')=='900'
    exported=client.get('/api/assistant/artifacts/'+artifact['id']+'/export',params={'format':'csv'})
    assert exported.status_code==200
    rows=list(csv.reader(StringIO(exported.content.decode('utf-8-sig'))))
    cells=[cell for row in rows for cell in row]
    assert '900' in cells and 'SYN-O-A001' in cells
    with dbm.SessionLocal() as db:
        db.delete(db.get(AuthRolePermission,'closure-order-read'));db.commit()
    snapshot=client.get('/api/assistant/runs/'+message['run_id'])
    assert snapshot.status_code==200 and all(m.get('unavailable') for m in snapshot.json()['items'])
    assert client.get('/api/assistant/artifacts/'+artifact['id']).status_code==410
    for format_name in ('md','csv','pdf','xlsx'):
        denied=client.get('/api/assistant/artifacts/'+artifact['id']+'/export',params={'format':format_name})
        assert denied.status_code==410 and 'CACHED_EXPORT_NOTE_CANARY' not in denied.text
    assert len(replay.calls)==2 and not replay.frames
