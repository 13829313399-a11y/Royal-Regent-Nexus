"""P3b races on isolated SQLite and an opt-in dedicated PostgreSQL schema.

Set CUTTING_TEST_POSTGRES_URL to a database whose name contains cutting_test.
Never point this fixture at the local business database.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api import cutting_operations as api
from app.services import cutting_ops as c, cutting_usage as usage
from app.services.auth import get_current_user
from test_cutting_ops import user, command, BASE
from test_cutting_usage import custody, bridge, flow, planned, read, consume, write, URL, warehouse_view
from test_cutting_cost_allocation import accounting, allocation_body
from test_cutting_reporting import send as report


@pytest.fixture(params=['sqlite', 'postgresql'])
def race_engine(request, tmp_path):
    if request.param == 'sqlite':
        engine = create_engine('sqlite:///' + (tmp_path / 'races.db').as_posix(),
                               connect_args={'check_same_thread': False, 'timeout': 20})
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        try:
            yield engine
        finally:
            engine.dispose()
        return
    url = os.getenv('CUTTING_TEST_POSTGRES_URL', '')
    if not url:
        pytest.skip('未配置专用 CUTTING_TEST_POSTGRES_URL，不能计作 PostgreSQL 已验收')
    parsed = make_url(url)
    assert parsed.get_backend_name() == 'postgresql' and 'cutting_test' in (parsed.database or '')
    schema = 'cutting_test_' + uuid4().hex
    admin = create_engine(parsed)
    engine = create_engine(parsed, connect_args={'options': f'-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=20000'})
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield engine
    finally:
        engine.dispose()
        assert schema.startswith('cutting_test_') and len(schema) == len('cutting_test_') + 32
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(race_engine, monkeypatch):
    c.TABLES[0].metadata.create_all(race_engine, tables=list(c.TABLES))
    auth = {'user': user('read', 'master_write', 'bom_write', 'bom_publish')}
    def get_db():
        with Session(race_engine, expire_on_commit=False) as db:
            yield db
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = get_db
    app.dependency_overrides[get_current_user] = lambda: auth['user']
    monkeypatch.setattr(api.settings, 'cutting_ops_enabled', True)
    with TestClient(app, raise_server_exceptions=False) as test:
        test.engine, test.cutting_auth = race_engine, auth
        yield test


def race(*calls):
    ready = Barrier(len(calls))
    def run(call):
        ready.wait(timeout=10)
        return call()
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        results = [pool.submit(run, call) for call in calls]
        return [result.result(timeout=30) for result in results]


def test_simultaneous_identical_retry_posts_one_usage(custody):
    p = custody
    body = command(expected_version=0, day='2026-10-10', issue_id=p.issue_id,
                   consumed_quantity='2', loss_quantity='0.5', counted_remaining='1.5')
    responses = race(*[lambda: p.post(URL + '/post', json=body)] * 2)
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    result = read(p)
    assert len(result['documents']) == 1 and result['revision'] == 1
    assert result['issues'][0]['remaining_quantity'] == '1.5'


def test_return_and_use_cannot_both_spend_signed_custody(custody):
    p = custody
    body = command(expected_version=0, day='2026-10-10', issue_id=p.issue_id,
                   consumed_quantity='3', loss_quantity='0', counted_remaining='1')
    returned = dict(factory_id=c.FACTORY, request_id=str(uuid4()), expected_revision=warehouse_view(p)['revision'],
                    kind='RETURN', business_date='2026-10-10', reason='并发退仓凭据', original_id=p.issue_id,
                    quantity='2', location_id='bin')
    responses = race(lambda: p.post(URL + '/post', json=body),
                     lambda: p.post('/api/warehouse-operations/fabric/documents', json=returned))
    assert sorted(r.status_code for r in responses) == [200, 409]
    row = read(p)['issues'][0]
    assert usage.wh.decimal(row['received_quantity']) == sum(usage.wh.decimal(row[k]) for k in
        ('returned_quantity', 'consumed_quantity', 'loss_quantity', 'remaining_quantity'))


def test_simultaneous_price_versions_have_one_winner(custody):
    p = custody
    consume(p)
    revision = read(p)['revision']
    bodies = [command(expected_version=revision, day='2026-10-10', issue_id=p.issue_id,
                      unit_cost=price, currency='CNY', price_reference='核对原批次实际凭据') for price in ('2', '4')]
    responses = race(*[lambda body=body: p.post(URL + '/price', json=body) for body in bodies])
    assert sorted(r.status_code for r in responses) == [200, 409]
    result = read(p, True)
    assert len(result['price_history']) == 1
    assert result['amounts']['CNY'] == result['cost_summary']['tasks'][0]['costs']['CNY']['total']


def test_cost_read_has_one_price_version_while_price_write_waits(custody, monkeypatch):
    p = custody
    consume(p)
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='首次核定成本依据')
    body = command(expected_version=read(p)['revision'], day='2026-10-10', issue_id=p.issue_id,
                   unit_cost='4', currency='CNY', price_reference='再次核定成本依据')
    paused, started = Event(), Event()
    once, used = Lock(), False
    original = usage.events
    def interleave(db):
        nonlocal used
        with once:
            first = not used
            used = True
        if first:
            paused.set()
            assert started.wait(10)
        return original(db)
    monkeypatch.setattr(usage, 'events', interleave)
    def writer():
        started.set()
        return p.post(URL + '/price', json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(lambda: p.get(URL, params={'factory_id': c.FACTORY, 'with_costs': True}))
        assert paused.wait(10)
        pending = pool.submit(writer)
        before, posted = reader.result(timeout=30), pending.result(timeout=30)
    assert before.status_code == posted.status_code == 200
    assert before.json()['amounts'] == {'CNY': '5.00'}
    assert before.json()['cost_summary']['tasks'][0]['costs']['CNY']['total'] == '5.00'
    assert read(p, True)['amounts'] == {'CNY': '10.00'}


def test_failed_post_rolls_back_event_receipt_and_releases_lock(custody, monkeypatch):
    p = custody
    original = usage.execute
    failing = uuid4().hex
    def execute(db, actor, line_id, body, action):
        result = original(db, actor, line_id, body, action)
        if body.operation_id == failing:
            raise RuntimeError('synthetic failure after flush')
        return result
    monkeypatch.setattr(usage, 'execute', execute)
    body = command(expected_version=0, day='2026-10-10', issue_id=p.issue_id,
                   consumed_quantity='2', loss_quantity='0', counted_remaining='2')
    failed = p.post(URL + '/post', json=body | {'operation_id': failing})
    assert failed.status_code == 500
    assert read(p)['revision'] == 0 and read(p)['documents'] == []
    responses = race(lambda: p.post(URL + '/post', json=body | {'operation_id': failing}),
                     lambda: p.post(URL + '/post', json=body))
    # The valid writer can win first; the failed writer then sees a stale version.
    assert responses[1].status_code == 200
    assert responses[0].status_code in (409, 500)
    result = read(p)
    assert result['revision'] == 1 and len(result['documents']) == 1


def test_two_supervisors_cannot_silently_replace_each_others_confirmation(accounting):
    p = accounting
    body = allocation_body(p)
    other = body | dict(operation_id=uuid4().hex, allocations=[dict(issue_id=p.issue_id, completed_quantity='1')])
    responses = race(lambda: p.post(URL + '/allocate', json=body), lambda: p.post(URL + '/allocate', json=other))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(read(p, True)['cost_allocation']['history']) == 1


def test_report_correction_and_allocation_never_leave_old_unit_cost_current(accounting):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='并发核对批次成本')
    body = allocation_body(p)
    responses = race(lambda: p.post(URL + '/allocate', json=body),
                     lambda: report(p, document_id=p.report_id, sets=8))
    assert responses[1].status_code == 200, responses[1].text
    assert responses[0].status_code in (200, 409)
    group = read(p, True)['cost_allocation']['groups'][0]
    assert group['completed_sets'] == 8
    assert group['status'] in {'stale', 'unconfirmed'} and group['costs']['CNY']['unit_cost'] is None


def test_monthly_preview_keeps_one_cost_version_during_price_write(accounting, monkeypatch):
    p = accounting
    write(p, 'price', issue_id=p.issue_id, unit_cost='2', currency='CNY', price_reference='月核对原成本依据')
    body = command(expected_version=read(p)['revision'], day='2026-10-10', issue_id=p.issue_id,
                   unit_cost='4', currency='CNY', price_reference='月核对新成本依据')
    paused, started = Event(), Event()
    original, first = usage.events, True
    def interleave(db):
        nonlocal first
        if first:
            first = False
            paused.set()
            assert started.wait(10)
        return original(db)
    monkeypatch.setattr(usage, 'events', interleave)
    def writer():
        started.set()
        return p.post(URL + '/price', json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(lambda: p.get(BASE + '/orders/line-1/closing-preview', params=dict(factory_id=c.FACTORY, month='2026-10', with_costs=True)))
        assert paused.wait(10)
        pending = pool.submit(writer)
        before, posted = reader.result(timeout=30), pending.result(timeout=30)
    assert before.status_code == posted.status_code == 200
    assert before.json()['costs'] == {'CNY': {'normal': '4.00', 'loss': '1.00'}}
    assert before.json()['materials'][0]['price']['data']['entry']['unit_cost'] == '2'
    assert read(p, True)['amounts'] == {'CNY': '10.00'}
