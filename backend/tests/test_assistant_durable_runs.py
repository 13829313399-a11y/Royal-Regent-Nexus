"""V3 worker integration: disposable SQLite, native auth and replay providers."""
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import threading
import time
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate


def migration():
    path = Path(__file__).parents[1] / 'alembic/versions/20261026_0176_assistant_durable_runs.py'
    spec = importlib.util.spec_from_file_location('durable_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def durable_env(env):
    client, dbm, calls, patch = env
    migrate(dbm)
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration().upgrade()
    from app.services.assistant import durable
    from app.core.config import settings
    patch.setattr(settings, 'assistant_durable_runs_enabled', True)
    client.portal.call(durable.worker.start)
    try:
        yield env
    finally:
        client.portal.call(durable.worker.stop)


def wait_snapshot(client, rid, terminal=True):
    until = time.monotonic() + 12
    while time.monotonic() < until:
        result = client.get('/api/assistant/runs/' + rid)
        assert result.status_code == 200, result.text
        value = result.json()
        if not terminal or value['state'] in ('completed', 'cancelled', 'interrupted', 'failed'):
            return value
        time.sleep(.03)
    pytest.fail('bounded synthetic worker did not reach a terminal state')


def post(client, sid, **values):
    body = payload(protocol_version=3, **values)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    assert response.status_code == 202, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    return response.json()['run_id'], body


def frames(response):
    assert response.status_code == 200, response.text
    result = []
    for block in response.text.strip().split('\n\n'):
        if block.startswith('event: '):
            kind, data = block.split('\ndata: ', 1)
            result.append(dict(event=kind[7:], data=json.loads(data)))
    return result


def test_worker_finishes_without_subscriber_and_ordered_replay_is_read_only(durable_env):
    from app.models.assistant import AssistantExecution, AssistantProviderStep, AssistantRunEvent
    client, dbm, calls, _ = durable_env
    caps = client.get('/api/assistant/capabilities').json()
    assert caps['run_protocols'] == [1, 2, 3] and caps['durable_runs']['available']
    sid = session(client)
    rid, body = post(client, sid)
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] == 'completed', snapshot
    assert snapshot['protocol_version'] == 3 and len(calls) == 1
    assert '自由回答' in json.dumps(snapshot['items'], ensure_ascii=False)
    one = frames(client.get(f'/api/assistant/runs/{rid}/events'))
    two = frames(client.get(f'/api/assistant/runs/{rid}/events', params={'after_seq': 3}))
    assert [v['data']['seq'] for v in one] == list(range(1, snapshot['event_seq'] + 1))
    assert two == one[3:] and len(calls) == 1
    assert one[0]['event'] == 'run.started' and one[-1]['event'] == 'run.completed'
    assert client.post(f'/api/assistant/sessions/{sid}/messages', json=body).json()['reused']
    assert client.post(f'/api/assistant/sessions/{sid}/messages', json={**body, 'text': 'another question'}).status_code == 409
    assert len(calls) == 1
    assert client.get(f'/api/assistant/runs/{rid}/events', params={'after_seq': snapshot['event_seq'] + 1}).status_code == 409
    with dbm.SessionLocal() as db:
        execution = db.get(AssistantExecution, rid)
        assert execution.status == 'terminal' and execution.auth_session_id == 'alice' and execution.fence == 1
        steps = db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id == rid)).all()
        assert [(s.step_id, s.status, s.request_id) for s in steps] == [('chat-0', 'completed', 'synthetic')]
        assert steps[0].usage['total_tokens'] == 12
        assert len(db.scalars(select(AssistantRunEvent).where(AssistantRunEvent.run_id == rid)).all()) == snapshot['event_seq']
    client.cookies.set('rr_session', 'bob')
    assert client.get(f'/api/assistant/runs/{rid}/events').status_code == 404


def test_cancel_saves_every_persisted_delta_rejects_late_completion_and_no_subscriber_dependency(durable_env):
    from app.services.assistant import provider, service
    from app.models.assistant import AssistantRun, AssistantProviderStep
    from app.services.assistant.errors import AssistantError
    client, dbm, _, patch = durable_env
    started, closed = threading.Event(), threading.Event()
    calls = []
    async def slow(*args):
        calls.append(1)
        try:
            for text in ('第一段', '第二段', '第三段'):
                yield dict(kind='delta', channel='answer', text=text)
            started.set()
            await asyncio.sleep(60)
            yield dict(kind='done', finish_reason='stop')
        finally:
            closed.set()
    patch.setattr(provider, 'stream', slow)
    sid = session(client)
    rid, _ = post(client, sid)
    assert started.wait(8)
    before = wait_snapshot(client, rid, False)
    assert '第一段第二段第三段' in json.dumps(before['items'], ensure_ascii=False)
    with dbm.SessionLocal() as db:
        lease = db.get(AssistantRun, rid).lease_owner
    cancelled = client.post(f'/api/assistant/runs/{rid}/cancel')
    assert cancelled.json()['state'] == 'cancelled'
    assert closed.wait(4)
    for values in (dict(parts=[dict(type='text', text='晚到的秘密')]), dict(terminal='completed')):
        with pytest.raises(AssistantError, match='409'):
            service.control(rid, lease, **values)
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] == 'cancelled' and len(calls) == 1
    assert '第一段第二段第三段' in json.dumps(snapshot, ensure_ascii=False) and '晚到' not in json.dumps(snapshot, ensure_ascii=False)
    events = frames(client.get(f'/api/assistant/runs/{rid}/events'))
    assert [e['event'] for e in events if e['event'] in ('run.completed', 'run.cancelled', 'run.interrupted', 'run.failed')] == ['run.cancelled']
    assert client.post(f'/api/assistant/runs/{rid}/cancel').json()['state'] == 'cancelled'
    with dbm.SessionLocal() as db:
        assert db.get(AssistantProviderStep, (rid, 'chat-0')).status == 'unknown'


def test_length_notice_is_persisted_without_rewriting_provider_text_and_exported(durable_env):
    from app.services.assistant import provider
    client, _, _, patch = durable_env
    async def limited(*args):
        yield dict(kind='delta', channel='answer', text='原文保留[ref_')
        yield dict(kind='usage', usage={'completion_tokens': 10, 'total_tokens': 20})
        yield dict(kind='done', finish_reason='length')
    patch.setattr(provider, 'stream', limited)
    sid = session(client)
    rid, _ = post(client, sid)
    snapshot = wait_snapshot(client, rid)
    answer = snapshot['items'][-1]
    assert snapshot['state'] == 'completed' and snapshot['context_window']['finish_reason'] == 'length'
    assert ''.join(p['text'] for p in answer['content_parts'] if p['type'] == 'text') == '原文保留[ref_'
    assert next(p for p in answer['content_parts'] if p['type'] == 'run_notice')['code'] == 'output_limit'
    for url in (f'/api/assistant/sessions/{sid}/export', f'/api/assistant/runs/{rid}/export'):
        response = client.get(url)
        assert response.status_code == 200 and '模型输出上限' in response.text
    assert frames(client.get(f'/api/assistant/runs/{rid}/events'))[-1]['data']['finish_reason'] == 'length'


def hold_queue(client, patch):
    from app.services.assistant import durable
    original = durable.claim
    patch.setattr(durable, 'claim', lambda worker_id: None)
    return original


def test_queued_restart_auth_binding_and_no_credential_persistence(durable_env):
    from app.services.assistant import durable
    from app.models.auth import AuthSession, AuthUser
    from app.models.assistant import AssistantExecution
    client, dbm, calls, patch = durable_env
    original = hold_queue(client, patch)
    sid = session(client)
    rid, _ = post(client, sid)
    client.portal.call(durable.worker.stop)
    with dbm.SessionLocal() as db:
        row = db.get(AssistantExecution, rid)
        assert row.status == 'queued' and row.fence == 0
        stored = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        assert stored['auth_session_id'] == 'alice'
        assert not {'cookie', 'token', 'token_hash', 'api_key'} & stored.keys()
    patch.setattr(durable, 'claim', original)
    client.portal.call(durable.worker.start)
    assert wait_snapshot(client, rid)['state'] == 'completed' and len(calls) == 1
    # A queued job cannot start using a revoked or forced-change login.
    for field in ('status', 'force_password_change'):
        original = hold_queue(client, patch)
        sid = session(client)
        stopped, _ = post(client, sid)
        client.portal.call(durable.worker.stop)
        with dbm.SessionLocal() as db:
            target = db.get(AuthSession, 'alice') if field == 'status' else db.get(AuthUser, 'alice')
            setattr(target, field, 'revoked' if field == 'status' else 1)
            db.commit()
        patch.setattr(durable, 'claim', original)
        client.portal.call(durable.worker.start)
        until = time.monotonic() + 8
        while time.monotonic() < until:
            from app.models.assistant import AssistantRun
            with dbm.SessionLocal() as db:
                state = db.get(AssistantRun, stopped).state
            if state == 'interrupted':
                break
            time.sleep(.03)
        assert state == 'interrupted' and len(calls) == 1
        with dbm.SessionLocal() as db:
            target = db.get(AuthSession, 'alice') if field == 'status' else db.get(AuthUser, 'alice')
            setattr(target, field, 'active' if field == 'status' else 0)
            db.commit()


def test_provider_steps_are_distinct_and_cannot_be_attempted_twice(durable_env, tmp_path):
    from app.services.assistant import provider, durable
    from app.models.assistant import AssistantProviderStep, AssistantRun
    from app.services.assistant.errors import AssistantError
    from test_assistant_api import verified_profile
    client, dbm, _, patch = durable_env
    settings = verified_profile(tmp_path)
    settings.assistant_max_tool_rounds = 1
    calls = []
    async def tool_roundtrip(*args):
        calls.append(1)
        yield dict(kind='request_id', value=f'provider-step-{len(calls)}')
        if len(calls) == 1:
            yield dict(kind='calls', calls=[dict(id='help-call', type='function', function=dict(name='help_search', arguments='{"query":"no synthetic matching help"}'))])
        else:
            yield dict(kind='delta', channel='answer', text='第二个独立步骤')
        yield dict(kind='usage', usage={'total_tokens': 11})
        yield dict(kind='done', finish_reason='tool_calls' if len(calls) == 1 else 'stop')
    patch.setattr(provider, 'stream', tool_roundtrip)
    sid = session(client)
    rid, _ = post(client, sid)
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] == 'completed' and len(calls) == 2, snapshot
    with dbm.SessionLocal() as db:
        steps = db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id == rid).order_by(AssistantProviderStep.step_id)).all()
        assert [(s.step_id, s.status, s.request_id) for s in steps] == [('chat-0', 'completed', 'provider-step-1'), ('chat-1', 'completed', 'provider-step-2')]
        lease = db.get(AssistantRun, rid).lease_owner
    with pytest.raises(AssistantError):
        durable.begin_step(rid, lease, 'chat-0', 'synthetic')
    assert frames(client.get(f'/api/assistant/runs/{rid}/events', params={'after_seq': 3}))
    assert len(calls) == 2 and snapshot['usage']['total_tokens'] == 22


def test_unknown_upstream_process_crash_preserves_atomic_partial_and_never_reissues(durable_env, tmp_path):
    from app.services.assistant import durable, service
    from app.models.assistant import AssistantRun, AssistantProviderStep
    client, dbm, calls, patch = durable_env
    original = hold_queue(client, patch)
    sid = session(client)
    rid, _ = post(client, sid)
    client.portal.call(durable.worker.stop)
    patch.setattr(durable, 'claim', original)
    marker = tmp_path / 'child-provider-attempt.txt'
    script = tmp_path / 'crash_worker.py'
    script.write_text('''import asyncio, os
from pathlib import Path
from app.services.assistant import durable, runtime, provider, service
from app.schemas.assistant import SendMessage
service.LEASE_SECONDS = 1
async def broken(*args):
    Path(os.environ['CRASH_MARKER']).write_text('one provider attempt', encoding='utf-8')
    for text in ('崩溃前第一段', '第二段', '第三段'):
        yield dict(kind='delta', channel='answer', text=text)
    os._exit(37)
provider.stream = broken
async def main():
    work = durable.claim('synthetic-crash-process')
    assert work and work['admitted']['run_id'] == os.environ['CRASH_RUN']
    user = runtime.authenticate(work['request'])
    async for _ in runtime.events(work['request'], user, SendMessage.model_validate(work['frozen']), work['admitted']):
        pass
asyncio.run(main())
''', encoding='utf-8')
    child_env = {**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1]), 'DATABASE_URL': str(dbm.engine.url),
        'ASSISTANT_ENABLED': 'true', 'ASSISTANT_DURABLE_RUNS_ENABLED': 'true', 'ASSISTANT_QWEN_API_KEY': 'synthetic-never-sent',
        'ASSISTANT_QWEN_BASE_URL': 'https://provider.example.test/v1', 'ASSISTANT_MODEL': 'synthetic-model',
        'ASSISTANT_MODEL_CAPABILITIES_FILE': '', 'ASSISTANT_DAILY_TOKEN_BUDGET': '',
        'ASSISTANT_CONTEXT_CHARACTER_BUDGET': '100000', 'ASSISTANT_MAX_OUTPUT_TOKENS': '',
        'CRASH_MARKER': str(marker), 'CRASH_RUN': rid}
    child = subprocess.run([sys.executable, str(script)], env=child_env, capture_output=True, text=True, timeout=20)
    assert child.returncode == 37, child.stderr[-3000:]
    assert marker.read_text(encoding='utf-8') == 'one provider attempt'
    with dbm.SessionLocal() as db:
        run = db.get(AssistantRun, rid)
        old_lease = run.lease_owner
        assert run.state in service.ACTIVE
    time.sleep(1.1)
    client.portal.call(durable.worker.start)
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] == 'interrupted' and snapshot['error_code'] == 'lease_expired'
    assert '崩溃前第一段第二段第三段' in json.dumps(snapshot['items'], ensure_ascii=False)
    with dbm.SessionLocal() as db:
        assert db.get(AssistantProviderStep, (rid, 'chat-0')).status == 'unknown'
    from app.services.assistant.errors import AssistantError
    with pytest.raises(AssistantError):
        service.control(rid, old_lease, parts=[dict(type='text', text='late overwrite')], terminal='completed')
    assert len(calls) == 0 and frames(client.get(f'/api/assistant/runs/{rid}/events'))[-1]['event'] == 'run.interrupted'
    retry, body = post(client, sid, relation={'parent_run_id': rid, 'kind': 'retry'})
    assert wait_snapshot(client, retry)['state'] == 'completed' and retry != rid and len(calls) == 1
    assert '崩溃前第一段第二段第三段' in json.dumps(wait_snapshot(client, rid)['items'], ensure_ascii=False)


def test_native_permission_revocation_blocks_event_union_and_snapshot_consistently(durable_env):
    from app.models.auth import AuthRole, AuthRolePermission, AuthUserRole, AuthPermission
    from app.models.assistant import AssistantRun, AssistantMessage, AssistantExecution
    from app.services.assistant import provider, service
    from app.core.config import settings
    from app.models.customer_order_ledger import OrderLedgerLine
    from decimal import Decimal
    client, dbm, _, patch = durable_env
    patch.setattr(settings, 'authz_mode', 'enforce')
    with dbm.SessionLocal() as db:
        permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'customer_order:read'))
        assert permission
        db.add(AuthRole(id='durable-orders', code='durable-orders', name='synthetic'))
        db.flush()
        db.add(AuthRolePermission(id='durable-permission', role_id='durable-orders', permission_id=permission.id))
        db.add(AuthUserRole(id='durable-assignment', user_id='alice', role_id='durable-orders', factory_id='huakang-a', department='sales-business'))
        db.add(OrderLedgerLine(id='DURABLE-PRIVATE', factory_id='huakang-a', customer_code='synthetic', customer_name='私有来源标题',
            identity_key='DURABLE-PRIVATE', reference_no='DURABLE-PRIVATE', product_no='PRIVATE-PRODUCT',
            quantity=Decimal('1000'), shipped_quantity=Decimal('600'), status='active', data={}, created_at='2026-10-26 00:00:00', updated_at='2026-10-26 00:00:00'))
        db.commit()
    waiting = threading.Event()
    async def paused(*args):
        yield dict(kind='delta', channel='answer', text='私有订单剩余400，PRIVATE-PRODUCT')
        waiting.set()
        await asyncio.sleep(60)
    patch.setattr(provider, 'stream', paused)
    sid = session(client)
    rid, _ = post(client, sid, intent='my_work', page_context=dict(module_id='customer-orders', route_name='customer-order-center', factory_id='huakang-a'))
    assert waiting.wait(10), wait_snapshot(client, rid, False)
    with dbm.SessionLocal() as db:
        run = db.get(AssistantRun, rid)
        lease = run.lease_owner
        execution = db.get(AssistantExecution, rid)
        assert any(s['kind'] == 'business' for s in execution.source_refs)
    # A subsequent snapshot legitimately omitting an earlier event source must
    # still depend on that source for every private export, history and replay.
    service.control(rid, lease, parts=[dict(type='text', text='PRIVATE-PRODUCT 400')])
    with dbm.SessionLocal() as db:
        db.delete(db.get(AuthRolePermission, 'durable-permission'))
        db.commit()
    snapshot = wait_snapshot(client, rid, False)
    assert all(m.get('unavailable') for m in snapshot['items'])
    assert 'PRIVATE-PRODUCT' not in json.dumps(snapshot) and '400' not in json.dumps(snapshot['items'])
    denied = client.get(f'/api/assistant/runs/{rid}/events', params={'after_seq': 0})
    assert denied.status_code == 410 and 'PRIVATE-PRODUCT' not in denied.text and '私有来源标题' not in denied.text
    assert client.get(f'/api/assistant/runs/{rid}/export').status_code == 410
    client.post(f'/api/assistant/runs/{rid}/cancel')


def test_step_deadline_unknown_usage_and_flag_rollback_preserve_private_rows(durable_env):
    from app.services.assistant import provider, durable
    from app.models.assistant import AssistantExecution, AssistantProviderStep, AssistantSession
    from app.core.config import settings
    from test_assistant_api import verified_profile
    client, dbm, _, patch = durable_env
    patch.setattr(settings, 'assistant_step_timeout_seconds', 1)
    attempts = []
    async def slow(*args):
        attempts.append(1)
        yield dict(kind='delta', channel='answer', text='部分内容')
        await asyncio.sleep(60)
    patch.setattr(provider, 'stream', slow)
    sid = session(client)
    rid, _ = post(client, sid)
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] == 'failed' and snapshot['error_code'] == 'step_timeout' and len(attempts) == 1
    assert snapshot['usage'] is None
    with dbm.SessionLocal() as db:
        assert db.get(AssistantProviderStep, (rid, 'chat-0')).status == 'unknown'
        assert db.get(AssistantSession, sid).budget_unknown
    patch.setattr(settings, 'assistant_durable_runs_enabled', False)
    caps = client.get('/api/assistant/capabilities').json()
    assert caps['run_protocols'] == [1, 2] and not caps['durable_runs']['available']
    assert frames(client.get(f'/api/assistant/runs/{rid}/events'))
    assert client.post(f'/api/assistant/sessions/{session(client)}/messages', json=payload(protocol_version=3)).status_code == 503
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError, match='preserved'):
                migration().downgrade()
        assert conn.exec_driver_sql('SELECT COUNT(*) FROM nexus_assistant_executions').scalar() == 1
    client.portal.call(durable.worker.stop)


def test_admission_is_atomic_double_click_and_terminal_race_settles_exactly_once(durable_env):
    from app.services.assistant import durable, service
    from app.models.assistant import AssistantRun, AssistantMessage, AssistantExecution, AssistantSession
    from app.services.assistant.errors import AssistantError
    client, dbm, calls, patch = durable_env
    original = hold_queue(client, patch)
    sid = session(client)
    body = payload(protocol_version=3)
    enqueue = durable.enqueue
    def reject_after_enqueue(*args):
        enqueue(*args)
        raise AssistantError('synthetic_queue_failure', 'isolated rollback test', 503)
    patch.setattr(durable, 'enqueue', reject_after_enqueue)
    assert client.post(f'/api/assistant/sessions/{sid}/messages', json=body).status_code == 503
    with dbm.SessionLocal() as db:
        assert not db.scalars(select(AssistantRun).where(AssistantRun.session_id == sid)).all()
        assert not db.scalars(select(AssistantMessage).where(AssistantMessage.session_id == sid)).all()
        assert not db.scalars(select(AssistantExecution)).all()
        assert db.get(AssistantSession, sid).title == '新对话'
    patch.setattr(durable, 'enqueue', enqueue)
    barrier = threading.Barrier(2)
    def send_twice():
        barrier.wait()
        return client.post(f'/api/assistant/sessions/{sid}/messages', json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send_twice(), range(2)))
    assert sorted(r.status_code for r in results) == [200, 202]
    rid = results[0].json()['run_id']
    assert all(r.json()['run_id'] == rid for r in results) and not calls
    work = original('manual-isolated-worker')
    assert work['admitted']['run_id'] == rid
    lease = work['admitted']['lease']
    durable.begin_step(rid, lease, 'chat-0', 'synthetic')
    with pytest.raises(AssistantError) as repeated:
        durable.begin_step(rid, lease, 'chat-0', 'synthetic')
    assert repeated.value.detail['code'] == 'step_already_attempted'
    durable.finish_step(rid, lease, 'chat-0', 'synthetic-id', {'total_tokens': 7})
    service.control(rid, lease, parts=[dict(type='text', text='已显示的最后一段')], usage={'total_tokens': 7})
    with dbm.SessionLocal() as db:
        user = work['request'].authenticate(db)
    barrier = threading.Barrier(2)
    def complete():
        barrier.wait()
        try:
            return service.control(rid, lease, terminal='completed', usage={'total_tokens': 7})
        except AssistantError as exc:
            return exc.detail['code']
    def cancel():
        barrier.wait()
        return service.cancel(user, rid)['state']
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(complete), pool.submit(cancel)
        assert a.result() in ('completed', 'cancelled', 'lease_lost')
        assert b.result() in ('completed', 'cancelled')
    snapshot = wait_snapshot(client, rid)
    assert snapshot['state'] in ('completed', 'cancelled')
    assert '已显示的最后一段' in json.dumps(snapshot, ensure_ascii=False)
    terminal_events = [f for f in frames(client.get(f'/api/assistant/runs/{rid}/events')) if f['event'] in ('run.completed','run.cancelled')]
    assert len(terminal_events) == 1 and terminal_events[0]['event'] == 'run.' + snapshot['state']
    with dbm.SessionLocal() as db:
        assert db.get(AssistantSession, sid).budget_tokens == 7
        assert len(db.scalars(select(AssistantMessage).where(AssistantMessage.run_id == rid)).all()) == 2


def test_native_employment_epoch_change_stops_queued_job_and_hides_old_owner_exports(durable_env):
    from app.services.assistant import durable
    from app.models.auth import EmployeeProfile
    from app.models.assistant import AssistantRun
    client, dbm, calls, patch = durable_env
    original = hold_queue(client, patch)
    sid = session(client)
    rid, _ = post(client, sid)
    client.portal.call(durable.worker.stop)
    with dbm.SessionLocal() as db:
        db.add(EmployeeProfile(user_id='alice', employment_epoch=2, employment_status='active', identity_mode='legacy'))
        db.commit()
    patch.setattr(durable, 'claim', original)
    client.portal.call(durable.worker.start)
    until = time.monotonic() + 8
    while time.monotonic() < until:
        with dbm.SessionLocal() as db:
            run = db.get(AssistantRun, rid)
            state, code = run.state, run.error_code
        if state == 'interrupted': break
        time.sleep(.03)
    assert state == 'interrupted' and code == 'identity_changed' and len(calls) == 0
    for url in (f'/api/assistant/runs/{rid}', f'/api/assistant/runs/{rid}/events', f'/api/assistant/sessions/{sid}/messages', f'/api/assistant/sessions/{sid}/export'):
        assert client.get(url).status_code == 404


def test_additive_sqlite_migration_keeps_legacy_hashes_content_and_artifact_and_pg_sql_is_only_compilation(env):
    from app.models.assistant import AssistantRun
    from app.core.config import settings
    from app.schemas.assistant import SendMessage, canonical_request
    client, dbm, calls, patch = env
    migrate(dbm)
    sid = session(client)
    originals = []
    for version in (1,2):
        body = payload(protocol_version=version)
        assert 'run.completed' in client.post(f'/api/assistant/sessions/{sid}/messages', json=body).text
    before = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
    rid = before[-1]['run_id']
    artifact = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(source_run_id=rid,title='旧成果保留',content='旧版原文')).json()
    with dbm.SessionLocal() as db:
        originals = [(r.id, r.request_hash, r.request_input) for r in db.scalars(select(AssistantRun).where(AssistantRun.session_id == sid))]
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration().upgrade()
            migration().downgrade()  # Empty-only rollback is allowed.
            migration().upgrade()
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'] == before
    assert client.get('/api/assistant/artifacts/' + artifact['id']).json()['content'] == '旧版原文'
    with dbm.SessionLocal() as db:
        assert [(r.id, r.request_hash, r.request_input) for r in db.scalars(select(AssistantRun).where(AssistantRun.session_id == sid))] == originals
    fixed = dict(client_request_id='0123456789abcdef',text='legacy')
    legacy = dict(**fixed,attachment_ids=[],intent='chat',profile_id='default',thinking='auto',web_search='off',page_context=None)
    value = canonical_request(SendMessage(**fixed))
    assert value == legacy
    assert hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() == hashlib.sha256(json.dumps(legacy,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    sql = StringIO()
    with Operations.context(MigrationContext.configure(dialect_name='postgresql', opts={'as_sql':True,'output_buffer':sql})):
        migration().upgrade()
    assert 'CREATE TABLE nexus_assistant_run_events' in sql.getvalue() and 'PRIMARY KEY (run_id, seq)' in sql.getvalue()
    assert len(calls) == 2


def test_replay_source_validation_releases_write_lock_and_source_growth_rechecks_before_release(durable_env):
    from app.services.assistant import durable, service, visibility
    from app.models.assistant import AssistantExecution
    client, dbm, _, patch = durable_env
    sid = session(client)
    rid, _ = post(client, sid)
    wait_snapshot(client, rid)
    with dbm.SessionLocal() as db:
        from app.models.auth import AuthSession
        from app.services.auth import authenticated_session_user
        user = authenticated_session_user(db, db.get(AuthSession,'alice'), method='GET',path='/api/assistant/runs/events')
    checking, release = threading.Event(), threading.Event()
    original = visibility.allowed
    def slow(*args, **kwargs):
        checking.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    patch.setattr(visibility, 'allowed', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(durable.replay, user, rid)
        try:
            assert checking.wait(3)
            assert pool.submit(service.create, user, uuid4().hex).result(timeout=1)['id']
            with service.transaction() as db:
                row=db.get(AssistantExecution,rid)
                row.source_refs=[dict(source_id='new-web-reference',kind='web',title='new dependency')]
        finally:
            release.set()
        first=reader.result(timeout=5)
    assert first['events']==[]
    assert durable.replay(user,rid)['events']


def test_unknown_second_step_cannot_reuse_previous_known_usage_and_keeps_failed_step_request_id(durable_env, tmp_path):
    from app.services.assistant import provider
    from app.models.assistant import AssistantRun, AssistantSession, AssistantProviderStep
    from app.services.assistant.errors import AssistantError
    from test_assistant_api import verified_profile
    client, dbm, _, patch = durable_env
    settings=verified_profile(tmp_path)
    settings.assistant_max_tool_rounds=1
    settings.assistant_context_character_budget=10000
    settings.assistant_max_output_tokens=32
    settings.assistant_daily_token_budget=1000000
    attempts=[]
    async def mixed(*args):
        attempts.append(1)
        if len(attempts)==1:
            yield dict(kind='request_id',value='first-known-step')
            yield dict(kind='calls',calls=[dict(id='help',type='function',function=dict(name='help_search',arguments='{"query":"no matching synthetic help"}'))])
            yield dict(kind='usage',usage={'total_tokens':11})
            yield dict(kind='done',finish_reason='tool_calls')
        else:
            with dbm.SessionLocal() as db:
                running=db.scalar(select(AssistantRun).where(AssistantRun.state.in_(('connecting','thinking','answering','tool_running'))))
                assert running.usage is None, 'new dispatch must clear the prior known total atomically'
            yield dict(kind='request_id',value='second-unknown-step')
            yield dict(kind='delta',channel='answer',text='第二步已收到的部分')
            raise AssistantError('provider_incomplete','合成流中断',502,True)
    patch.setattr(provider,'stream',mixed)
    sid=session(client)
    rid,_=post(client,sid)
    snapshot=wait_snapshot(client,rid)
    assert snapshot['state']=='interrupted' and snapshot['usage'] is None and len(attempts)==2
    with dbm.SessionLocal() as db:
        assert db.get(AssistantSession,sid).budget_tokens==80064
        step=db.get(AssistantProviderStep,(rid,'chat-1'))
        assert step.status=='unknown' and step.request_id=='second-unknown-step' and step.usage is None


def test_search_and_synthesis_continue_after_subscription_close_and_two_replays_do_not_execute_steps(durable_env):
    from starlette.requests import Request
    from app.services.assistant import durable, native_search, search_capabilities
    from app.models.assistant import AssistantProviderStep
    client, dbm, synthesis_calls, patch=durable_env
    # A bounded offline transport fixture, not provider-capability acceptance.
    patch.setattr(search_capabilities,'validate',lambda p:None)
    entered, release=threading.Event(),threading.Event()
    search_calls=[]
    async def search(*args):
        search_calls.append(1)
        yield dict(kind='request_id',value='synthetic-search-request')
        yield dict(kind='delta',channel='answer',text='只作为研究草稿')
        entered.set()
        while not release.is_set(): await asyncio.sleep(.02)
        yield dict(kind='sources',items=[dict(index=1,title='synthetic source',url='https://sources.example.test/a')])
        yield dict(kind='usage',usage={'total_tokens':7},search_count=1)
        yield dict(kind='done',finish_reason='stop')
    patch.setattr(native_search,'stream',search)
    sid=session(client)
    rid,_=post(client,sid,web_search='on')
    assert entered.wait(8)
    async def close_reader():
        async def receive():
            await asyncio.sleep(0)
            return {'type':'http.request','body':b'','more_body':False}
        request=Request(dict(type='http',method='GET',path=f'/api/assistant/runs/{rid}/events',
            scheme='http',server=('testserver',80),client=('127.0.0.1',1234),query_string=b'',
            headers=[(b'cookie',b'rr_session=alice')]),receive=receive)
        stream=durable.subscription(request,rid,0)
        received=[]
        try:
            for _ in range(3):received.append(await anext(stream))
        finally:
            await stream.aclose()
        return received
    first=client.portal.call(close_reader)
    assert len(first)==3 and json.loads(first[-1].split('data: ',1)[1])['seq']==3
    assert wait_snapshot(client,rid,False)['state'] in ('connecting','thinking','answering','tool_running')
    assert len(search_calls)==1 and not synthesis_calls
    release.set()
    result=wait_snapshot(client,rid)
    assert result['state']=='completed' and result['usage']['total_tokens']==19
    a=frames(client.get(f'/api/assistant/runs/{rid}/events',params={'after_seq':3}))
    b=frames(client.get(f'/api/assistant/runs/{rid}/events',params={'after_seq':3}))
    assert a==b and [e['data']['seq'] for e in a]==list(range(4,result['event_seq']+1))
    assert len(search_calls)==1 and len(synthesis_calls)==1
    with dbm.SessionLocal() as db:
        steps=db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id==rid).order_by(AssistantProviderStep.step_id)).all()
        assert [(s.step_id,s.status) for s in steps]==[('search-0','completed'),('synthesis-0','completed')]


def test_error_categories_request_ids_tool_limit_and_unrelated_search_config_do_not_trigger_paid_retries(durable_env,tmp_path):
    from app.services.assistant import provider
    from app.services.assistant.errors import AssistantError
    from app.core.config import settings
    from test_assistant_api import verified_profile
    client,_,_,patch=durable_env
    patch.setattr(settings,'assistant_search_endpoint','invalid-unrelated-search-url')
    patch.setattr(settings,'assistant_search_capabilities_file',str(tmp_path/'missing-search-profile.json'))
    assert wait_snapshot(client,post(client,session(client))[0])['state']=='completed'
    attempts=[]
    for code,status in [('provider_auth',502),('provider_rate_limit',429)]:
        async def denied(*args):
            attempts.append(code)
            raise AssistantError(code,'合成错误分类',status,False)
            yield
        patch.setattr(provider,'stream',denied)
        rid,_=post(client,session(client))
        result=wait_snapshot(client,rid)
        terminal=frames(client.get(f'/api/assistant/runs/{rid}/events'))[-1]
        assert result['state']=='failed' and result['error_code']==code
        assert terminal['data']['request_id']==rid and terminal['data']['code']==code
        assert terminal['data']['retryable'] is False
        assert client.get('/api/auth/me').status_code==200
    assert attempts==['provider_auth','provider_rate_limit']
    verified_profile(tmp_path)
    settings.assistant_max_tool_rounds=1
    loops=[]
    async def endless(*args):
        loops.append(1)
        yield dict(kind='calls',calls=[dict(id=f'help-{len(loops)}',type='function',function=dict(name='help_search',arguments='{"query":"synthetic no matching help"}'))])
        yield dict(kind='usage',usage={'total_tokens':5})
        yield dict(kind='done',finish_reason='tool_calls')
    patch.setattr(provider,'stream',endless)
    rid,_=post(client,session(client))
    result=wait_snapshot(client,rid)
    assert result['state']=='failed' and result['error_code']=='tool_limit' and len(loops)==2
    assert frames(client.get(f'/api/assistant/runs/{rid}/events'))[-1]['data']['request_id']==rid
