"""Owner-bound feedback and metadata-only operational evidence, no paid IO."""
import importlib.util
import json
from pathlib import Path
import time
import asyncio
import threading
from uuid import uuid4
import pytest
from sqlalchemy import select, inspect
from sqlalchemy.exc import OperationalError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_assistant_api import env, session, payload
from test_assistant_durable_runs import durable_env, post, wait_snapshot, frames


def migration():
    path=Path(__file__).parents[1]/'alembic/versions/20261102_0189_assistant_operations.py'
    spec=importlib.util.spec_from_file_location('assistant_operations_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.fixture
def ops_env(durable_env):
    client,dbm,calls,patch=durable_env
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):migration().upgrade()
    yield durable_env


def feedback(**values):
    return dict(client_request_id=uuid4().hex,base_revision=0,categories=['experience'],source_ids=[],comment='FEEDBACK_PRIVATE 中文说明',**values)


def test_feedback_idempotency_conflict_plain_text_owner_and_no_provider_side_effect(ops_env):
    from app.models.assistant import AssistantMessage
    client,dbm,calls,_=ops_env
    sid=session(client)
    rid,_=post(client,sid)
    original=wait_snapshot(client,rid)['items']
    caps=client.get('/api/assistant/capabilities').json()
    assert caps['feedback']['available'] and caps['operational_metrics']['available']
    first=client.get(f'/api/assistant/runs/{rid}/feedback')
    assert first.status_code==200 and first.json()['feedback'] is None and first.json()['sources']==[]
    body=feedback()
    body['comment']='<script>FEEDBACK_PRIVATE 不执行</script>'
    saved=client.put(f'/api/assistant/runs/{rid}/feedback',json=body)
    assert saved.status_code==200 and saved.json()['revision']==1 and saved.json()['comment']==body['comment']
    assert saved.headers['cache-control']=='private, no-store'
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json=body).json()==saved.json()
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json={**body,'comment':'different'}).status_code==409
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json={**body,'client_request_id':uuid4().hex}).status_code==409
    update={**body,'client_request_id':uuid4().hex,'base_revision':1,'categories':['factual','sources']}
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json=update).json()['revision']==2
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json={**update,'source_ids':['foreign-source']}).status_code==422
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json={**update,'categories':['unregistered']}).status_code==422
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']==original and len(calls)==1
    client.cookies.set('rr_session','bob')
    for path in ('feedback','diagnostics'):
        assert client.get(f'/api/assistant/runs/{rid}/{path}').status_code==404
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json=body).status_code==404


def test_metrics_and_receipts_do_not_treat_delivery_as_client_application_and_admin_sees_no_text(ops_env):
    from app.services.assistant import operations
    from app.models.assistant import AssistantRunMetrics,AssistantSubscription
    from test_work_center_api import actor
    client,dbm,_,_=ops_env
    rid,_=post(client,session(client))
    result=wait_snapshot(client,rid)
    diag=client.get(f'/api/assistant/runs/{rid}/diagnostics').json()
    assert diag['measured'] and diag['usage_state']=='actual'
    assert diag['counters']['evidence_measured'] and diag['counters']['source_count']==0
    assert diag['timings']['first_delta_seconds']>=diag['timings']['first_event_seconds']>=0
    assert diag['timings']['first_answer_seconds']>=diag['timings']['first_delta_seconds']
    assert not diag['citation_binding_is_semantic_support']
    key='subscriber-'+uuid4().hex
    delivered=frames(client.get(f'/api/assistant/runs/{rid}/events',params={'after_seq':3,'subscriber_id':key}))
    assert delivered
    with dbm.SessionLocal() as db:
        row=db.get(AssistantSubscription,(rid,key))
        assert row.delivered_seq==result['event_seq'] and row.applied_seq is None and row.closed_at is not None
    admin=actor(factory='group',department='system',permissions=('system:access_manage',))
    before=operations.summary(admin)
    assert before['recovery']['after_seq_attempts']==1 and before['recovery']['client_confirmed_progress']==0 and before['recovery']['missing_client_receipt']==1
    receipt=client.post(f'/api/assistant/runs/{rid}/subscriptions/{key}/receipt',json={'applied_seq':result['event_seq']})
    assert receipt.status_code==200 and receipt.json()['applied_seq']==result['event_seq']
    assert client.post(f'/api/assistant/runs/{rid}/subscriptions/{key}/receipt',json={'applied_seq':result['event_seq']+1}).status_code==422
    assert client.post(f'/api/assistant/runs/{rid}/subscriptions/{key}/receipt',json={'applied_seq':3}).json()['applied_seq']==result['event_seq']
    client.put(f'/api/assistant/runs/{rid}/feedback',json=feedback())
    summary=operations.summary(admin)
    encoded=json.dumps(summary)
    assert summary['recovery']['client_confirmed_progress']==1 and summary['feedback']['categories']['experience']==1
    assert summary['timings']['elapsed_seconds']['samples']==1 and summary['timings']['elapsed_seconds']['p95'] is None
    assert not any(word in encoded for word in (rid,'FEEDBACK_PRIVATE','解释 JavaScript','synthetic-never-sent','provider.example.test','alice','bob'))
    assert client.get('/api/assistant/diagnostics/operations').status_code==403


def test_native_source_revocation_hides_saved_feedback_and_own_diagnostics(ops_env):
    from app.models.auth import AuthRole,AuthRolePermission,AuthUserRole,AuthPermission
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.core.config import settings
    from decimal import Decimal
    client,dbm,calls,patch=ops_env
    patch.setattr(settings,'authz_mode','enforce')
    with dbm.SessionLocal() as db:
        permission=db.scalar(select(AuthPermission).where(AuthPermission.code=='customer_order:read'))
        db.add(AuthRole(id='ops-order',code='ops-order',name='synthetic'))
        db.flush()
        db.add(AuthRolePermission(id='ops-order-read',role_id='ops-order',permission_id=permission.id))
        db.add(AuthUserRole(id='ops-order-assignment',user_id='alice',role_id='ops-order',factory_id='huakang-a',department='sales-business'))
        db.add(OrderLedgerLine(id='OPS-PRIVATE',factory_id='huakang-a',customer_code='synthetic',customer_name='来源私有名称',identity_key='OPS-PRIVATE',reference_no='OPS-PRIVATE',product_no='SYN',quantity=Decimal('1000'),shipped_quantity=Decimal('600'),status='active',data={},created_at='2026-10-26 00:00:00',updated_at='2026-10-26 00:00:00'))
        db.commit()
    rid,_=post(client,session(client),intent='my_work',page_context=dict(module_id='customer-orders',route_name='customer-order-center',factory_id='huakang-a'))
    wait_snapshot(client,rid)
    sources=client.get(f'/api/assistant/runs/{rid}/feedback').json()['sources']
    chosen=next(s['source_id'] for s in sources if s['kind']=='business')
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json={**feedback(),'source_ids':[chosen]}).status_code==200
    with dbm.SessionLocal() as db:
        db.delete(db.get(AuthRolePermission,'ops-order-read'));db.commit()
    for path in ('feedback','diagnostics'):
        denied=client.get(f'/api/assistant/runs/{rid}/{path}')
        assert denied.status_code==410 and 'FEEDBACK_PRIVATE' not in denied.text and '来源私有名称' not in denied.text
    assert client.put(f'/api/assistant/runs/{rid}/feedback',json=feedback()).status_code==410
    assert len(calls)==1


def test_optional_metrics_failure_does_not_rollback_saved_answer_or_log_private_sql_parameters(ops_env,caplog):
    from app.services.assistant import operations
    from app.models.assistant import AssistantRunMetrics
    client,dbm,_,patch=ops_env
    def failure(*args):
        raise OperationalError('UPDATE private_metrics',{'private':'DO-NOT-LOG-THIS'},Exception('DO-NOT-LOG-THIS'))
    patch.setattr(operations,'finished',failure)
    sid=session(client)
    rid,_=post(client,sid)
    result=wait_snapshot(client,rid)
    assert result['state']=='completed' and '自由回答' in json.dumps(result,ensure_ascii=False)
    assert 'DO-NOT-LOG-THIS' not in caplog.text
    with dbm.SessionLocal() as db:
        row=db.get(AssistantRunMetrics,rid)
        assert row is not None and row.terminal_state is None
    assert client.get(f'/api/assistant/runs/{rid}/export').status_code==200


def test_real_group_admin_can_trace_metadata_without_employee_chat_or_feedback_comment(ops_env):
    from app.models.auth import AuthRole,AuthRolePermission,AuthUserRole,AuthPermission
    from app.models.assistant import AssistantRun,AssistantProviderStep
    from app.core.config import settings
    from sqlalchemy import event
    client,dbm,_,patch=ops_env
    patch.setattr(settings,'authz_mode','enforce')
    rid,_=post(client,session(client))
    wait_snapshot(client,rid)
    client.put(f'/api/assistant/runs/{rid}/feedback',json=feedback())
    with dbm.SessionLocal() as db:
        permission=db.scalar(select(AuthPermission).where(AuthPermission.code=='system:access_manage'))
        db.add(AuthRole(id='ops-admin',code='ops-admin',name='synthetic'))
        db.flush()
        db.add(AuthRolePermission(id='ops-admin-read',role_id='ops-admin',permission_id=permission.id))
        db.add(AuthUserRole(id='ops-admin-assignment',user_id='bob',role_id='ops-admin',factory_id='group',department='system'))
        run=db.get(AssistantRun,rid);run.usage={**run.usage,'private_extra':'DO-NOT-RETURN-EXTRA'}
        step=db.get(AssistantProviderStep,(rid,'chat-0'));step.usage={**step.usage,'private_extra':'DO-NOT-RETURN-EXTRA'}
        db.commit()
    client.cookies.set('rr_session','bob')
    # Observe the diagnostic request, not the supervisor's independent lease scan.
    # Its terminal run and step evidence is already persisted above.
    from app.services.assistant import durable
    client.portal.call(durable.worker.stop)
    assert not durable.worker.running
    statements=[]
    def capture(conn,cursor,statement,*args):statements.append(statement.lower())
    event.listen(dbm.engine,'before_cursor_execute',capture)
    try:
        traced=client.get('/api/assistant/diagnostics/runs/'+rid)
        aggregate=client.get('/api/assistant/diagnostics/operations')
    finally:event.remove(dbm.engine,'before_cursor_execute',capture)
    assert traced.status_code==aggregate.status_code==200,(traced.text,aggregate.text)
    result=traced.json()
    assert result['metadata_only'] and result['run']['id']==rid and result['run']['usage']=={'total_tokens':12}
    assert result['steps'][0]['provider_request_id']=='synthetic'
    assert not any(token in traced.text+aggregate.text for token in ('FEEDBACK_PRIVATE','DO-NOT-RETURN-EXTRA','解释 JavaScript','自由回答','合成测试'))
    assert not any('nexus_assistant_messages' in sql or 'request_input' in sql or 'nexus_assistant_feedback.comment' in sql for sql in statements)
    assert client.get(f'/api/assistant/runs/{rid}/feedback').status_code==404
    client.cookies.set('rr_session','alice')
    assert client.get('/api/assistant/diagnostics/runs/'+rid).status_code==403


def test_counters_keep_unknowns_permission_failures_and_binding_separate_from_semantic_support():
    from app.services.assistant.operations import counters
    sources=[dict(source_id='a',kind='business',run_id='r'),dict(source_id='b',kind='business',run_id='r',origin={'run_id':'past'}),dict(source_id='c',kind='file',citation_eligible=False)]
    evidence=dict(type='evidence',sources=sources,citations=[dict(resolution='resolved'),dict(resolution='unresolved')],
        activities=[dict(kind='query_business'),dict(kind='query_business')])
    current=dict(contract_version=3,run_id='r',tool_call_id='a',step_id='one',status='partial',data_mode='snapshot',freshness={'state':'unknown'})
    failed=dict(contract_version=3,run_id='r',tool_call_id='b',step_id='two',status='forbidden',data_mode='unavailable',diagnostic_code='business_forbidden')
    output=counters([evidence,dict(type='business_snapshot',result=current),dict(type='tool_result',result=current),dict(type='business_failure',result=failed)],'r')
    assert output['source_count']==3 and output['eligible_sources']==2
    assert output['citations']==2 and output['resolved_citations']==1
    assert output['business_attempts']==2 and output['business_completed']==1 and output['business_permission_errors']==1
    assert output['current_business_sources']==1 and output['historical_business_sources']==1 and output['freshness_unknown']==1
    assert counters([dict(type='text',text='old legacy answer')],'old')=={'evidence_measured':False}


def test_feedback_epoch_isolation_delete_cascade_and_nonempty_downgrade(ops_env):
    from app.models.auth import EmployeeProfile
    from app.models.assistant import AssistantFeedback,AssistantRunMetrics,AssistantSubscription
    client,dbm,_,_=ops_env
    sid=session(client);rid,_=post(client,sid);wait_snapshot(client,rid)
    client.put(f'/api/assistant/runs/{rid}/feedback',json=feedback())
    key='subscriber-'+uuid4().hex
    client.get(f'/api/assistant/runs/{rid}/events',params={'after_seq':3,'subscriber_id':key})
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError,match='preserved'):migration().downgrade()
    with dbm.SessionLocal() as db:
        db.add(EmployeeProfile(user_id='alice',employment_epoch=2,employment_status='active',identity_mode='legacy'));db.commit()
    assert client.get(f'/api/assistant/runs/{rid}/feedback').status_code==404
    with dbm.SessionLocal() as db:
        db.get(EmployeeProfile,'alice').employment_epoch=1;db.commit()
    assert client.delete(f'/api/assistant/sessions/{sid}').status_code==200
    with dbm.SessionLocal() as db:
        assert db.get(AssistantFeedback,rid) is None and db.get(AssistantRunMetrics,rid) is None and db.get(AssistantSubscription,(rid,key)) is None


def test_distribution_thresholds_and_unknown_old_metadata_use_explicit_samples(ops_env):
    from app.services.assistant import operations
    from app.models.assistant import AssistantRun,AssistantRunMetrics
    from test_work_center_api import actor
    client,dbm,_,_=ops_env
    sid=session(client);rid,_=post(client,sid);wait_snapshot(client,rid)
    with dbm.SessionLocal() as db:
        original=db.get(AssistantRun,rid)
        columns={c.name:getattr(original,c.name) for c in AssistantRun.__table__.columns}
        row=db.get(AssistantRunMetrics,rid);row.elapsed_seconds=0
        metric={c.name:getattr(row,c.name) for c in AssistantRunMetrics.__table__.columns}
        for i in range(1,99):
            ident=uuid4().hex
            db.add(AssistantRun(**{**columns,'id':ident,'client_request_id':uuid4().hex}))
            db.add(AssistantRunMetrics(**{**metric,'run_id':ident,'elapsed_seconds':float(i)}))
        db.commit()
    admin=actor(factory='group',department='system',permissions=('system:access_manage',))
    first=operations.summary(admin)
    assert first['timings']['elapsed_seconds']['samples']==99
    assert first['timings']['elapsed_seconds']['p50']==49 and first['timings']['elapsed_seconds']['p95'] is None
    with dbm.SessionLocal() as db:
        ident=uuid4().hex
        db.add(AssistantRun(**{**columns,'id':ident,'client_request_id':uuid4().hex}))
        db.add(AssistantRunMetrics(**{**metric,'run_id':ident,'elapsed_seconds':99.0}))
        db.commit()
    second=operations.summary(admin)
    assert second['timings']['elapsed_seconds']['p50']==49.5
    assert second['timings']['elapsed_seconds']['p95']==pytest.approx(94.05)
    assert operations.duration(10,9) is None and operations.duration(None,0) is None
    with dbm.SessionLocal() as db:
        rows=list(db.scalars(select(AssistantRunMetrics)).all())
        for row in rows:row.counters={'evidence_measured':False}
        rows[0].counters={'evidence_measured':True,'eligible_sources':0,'source_count':0}
        rows[1].counters={'evidence_measured':True,'eligible_sources':1,'source_count':1}
        rows[2].counters={'evidence_measured':True,'eligible_sources':0,'source_count':0}
        rows[2].terminal_state=None
        db.commit()
    sources=operations.summary(admin)
    assert sources['no_source_ratio']==dict(numerator=1,denominator=2,value=.5)
    assert '普通聊天' in sources['definitions']['no_source']


def test_cancel_timing_measures_upstream_close_and_not_just_terminal_commit(ops_env):
    from app.services.assistant import provider
    from app.models.assistant import AssistantRunMetrics
    client,dbm,_,patch=ops_env
    entered,closed=threading.Event(),threading.Event()
    async def paused(*args):
        try:
            yield dict(kind='delta',channel='answer',text='已收到的部分')
            entered.set();await asyncio.sleep(60)
        finally:closed.set()
    patch.setattr(provider,'stream',paused)
    rid,_=post(client,session(client));assert entered.wait(8)
    assert client.post(f'/api/assistant/runs/{rid}/cancel').json()['state']=='cancelled'
    assert closed.wait(4)
    until=time.monotonic()+4
    while time.monotonic()<until:
        with dbm.SessionLocal() as db:
            metric=db.get(AssistantRunMetrics,rid)
            requested,stopped=metric.cancel_requested_at,metric.upstream_closed_at
        if stopped is not None:break
        time.sleep(.02)
    assert requested is not None and stopped is not None and stopped>=requested
    value=client.get(f'/api/assistant/runs/{rid}/diagnostics').json()
    assert value['state']=='cancelled' and value['timings']['upstream_close_after_cancel_seconds']>=0
    assert value['usage_state']=='unknown'


def test_statistics_deadline_releases_connection_and_never_returns_partial_zero_counts(ops_env):
    from app.services.assistant import operations
    from app.core.config import settings
    from app.services.assistant.errors import AssistantError
    from sqlalchemy import text
    client,dbm,_,patch=ops_env
    patch.setattr(settings,'assistant_operations_query_timeout_ms',100)
    with pytest.raises(AssistantError) as failure:
        with operations.metadata_read() as db:
            db.execute(text('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n'))
    assert failure.value.detail['code']=='operations_query_timeout'
    with dbm.SessionLocal() as db:assert db.execute(text('SELECT 1')).scalar()==1


def test_statistics_snapshot_remains_readable_while_a_writer_waits_to_commit(ops_env):
    from app.services.assistant import operations,durable
    from app.models.assistant import AssistantRunMetrics
    from test_work_center_api import actor
    from sqlalchemy import event,update
    client,dbm,_,_=ops_env
    rid,_=post(client,session(client));wait_snapshot(client,rid)
    client.portal.call(durable.worker.stop)
    with dbm.SessionLocal() as db:
        db.get(AssistantRunMetrics,rid).elapsed_seconds=1.0;db.commit()
    committing,done=threading.Event(),threading.Event()
    failures=[]
    def pending_commit(conn):
        if threading.current_thread() is writer:committing.set()
    def write():
        try:
            with dbm.engine.begin() as conn:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
                conn.execute(update(AssistantRunMetrics).where(AssistantRunMetrics.run_id==rid).values(elapsed_seconds=777.0))
        except Exception as exc:failures.append(type(exc).__name__)
        finally:done.set()
    writer=threading.Thread(target=write,name='statistics-pending-writer',daemon=True)
    def begin_write(conn,cursor,statement,*args):
        # The summary now owns its real read snapshot. A pending writer must
        # not prevent the rest of that snapshot from reading other tables.
        if threading.current_thread() is threading.main_thread() and not writer.ident and statement.startswith('SELECT count(') and 'nexus_assistant_run_metrics' in statement:
            writer.start()
            assert committing.wait(2)
    event.listen(dbm.engine,'commit',pending_commit)
    event.listen(dbm.engine,'after_cursor_execute',begin_write)
    try:
        result=operations.summary(actor(factory='group',department='system',permissions=('system:access_manage',)))
    finally:
        event.remove(dbm.engine,'after_cursor_execute',begin_write)
        event.remove(dbm.engine,'commit',pending_commit)
        if writer.ident:writer.join(6)
    assert done.is_set() and not failures
    assert result['timings']['elapsed_seconds']['min']==1.0
    with dbm.SessionLocal() as db:assert db.get(AssistantRunMetrics,rid).elapsed_seconds==777.0
