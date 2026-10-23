"""Explicit isolated production-chain expansion and mixed HTTP soak.

Normal regression is a short harness check. The dedicated runner supplies the
100/10-chain and 500/50-chain ten-minute profiles; no production URL is accepted.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import Barrier, Event, Thread, Lock
from time import perf_counter, process_time
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import sys
from datetime import datetime, UTC

import httpx
import pytest
from sqlalchemy import event, select, func, text
from sqlalchemy.orm import Session

from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order, BASE
from test_cutting_http_capacity import (isolated_http, add_dispatched_orders, login_http,
                                       projection, validate_workbook, endpoint_metrics)
from test_cutting_p5c import evidence
from test_cutting_ops import command
from app.models.cutting_ops import CuttingProductionEvent
from cutting_capacity_fixture import expand_chains


request_stats = ContextVar('capacity_request_stats', default=None)
REQUIRED_ENDPOINTS = {'planning', 'tasks', 'inventory', 'costs', 'period', 'settlement',
                      'payments', 'export_preview', 'export_download', 'write_basis', 'write', 'write_retry'}


def verify_endpoint_coverage(samples):
    missing = REQUIRED_ENDPOINTS - {sample['endpoint'] for sample in samples}
    assert not missing, f'Missing workload endpoints: {sorted(missing)}'


def test_long_soak_requires_every_endpoint():
    samples = [{'endpoint': name} for name in sorted(REQUIRED_ENDPOINTS)]
    verify_endpoint_coverage(samples)
    with pytest.raises(AssertionError, match='Missing workload endpoints'):
        verify_endpoint_coverage(samples[:-1])


@contextmanager
def awake_system():
    """Thread-scoped sleep inhibition, restored on exit; no power-plan change."""
    if sys.platform != 'win32':
        yield
        return
    import ctypes
    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    previous = set_state(0x80000001)  # continuous + system required (not display)
    if not previous:
        raise RuntimeError('Cannot prevent system idle sleep during soak')
    try:
        yield
    finally:
        set_state(previous)


def configuration():
    values = {key: int(os.environ.get('CUTTING_SOAK_'+key.upper(), default)) for key, default in
              [('orders', '3'), ('chains', '3'), ('workers', '3'), ('seconds', '3')]}
    assert 3 <= values['chains'] <= min(values['orders'], 50)
    assert values['orders'] <= 500 and 3 <= values['workers'] <= 10
    assert 3 <= values['seconds'] <= 1800
    values['workload'] = os.environ.get('CUTTING_SOAK_WORKLOAD', 'paced')
    assert values['workload'] in ('paced', 'burst')
    return values


class Diagnostics:
    def __init__(self, p):
        self.rows, self.gaps, self.lock_spans = [], [], []
        self.lock, self.stop = Lock(), Event()
        self.engine = p.engine
        self.origin = perf_counter()
        self.patches = ExitStack()
        from app.services import cutting_ops, cutting_payments, cutting_exports, cutting_workspace
        for module, names in [(cutting_ops, ['command', 'payment_command']),
                (cutting_payments, ['basis', 'preview', 'read', 'execute', 'balances']),
                (cutting_exports, ['capture', 'source_revision', 'package_isolated']),
                (cutting_workspace, ['task_board', 'inventory', 'cost_overview', 'scheduling'])]:
            for name in names:
                self.patches.enter_context(patch.object(module, name, self.tracked(getattr(module, name), module.__name__.rsplit('.', 1)[-1]+'.'+name)))
        @p.app.middleware('http')
        async def measure(request, call_next):
            stats = dict(sql_count=0, sql_seconds=0., lock_seconds=0., failed_sql=0,
                         request_id=request.headers.get('X-Test-Request-ID', ''), phase='request', phases=[])
            token = request_stats.set(stats)
            began = perf_counter()
            try:
                response = await call_next(request)
                response.headers['X-Test-Request-ID'] = request.headers.get('X-Test-Request-ID', '')
                return response
            finally:
                with self.lock:
                    self.rows.append(dict(stats, request_id=request.headers.get('X-Test-Request-ID', ''),
                        path=request.url.path, started_seconds=began-self.origin,
                        header_ready_seconds=perf_counter()-began))
                request_stats.reset(token)
        event.listen(self.engine, 'before_cursor_execute', self.before)
        event.listen(self.engine, 'after_cursor_execute', self.after)
        event.listen(self.engine, 'handle_error', self.sql_error)
        event.listen(self.engine, 'checkin', self.released)
        self.thread = Thread(target=self.heartbeat, daemon=True)

    def tracked(self, function, name):
        @wraps(function)
        def wrapped(*args, **kwargs):
            stats = request_stats.get()
            if stats is None:
                return function(*args, **kwargs)
            previous, began = stats['phase'], perf_counter()
            stats['phase'] = name
            try:
                return function(*args, **kwargs)
            finally:
                stats['phases'].append(dict(name=name, start=began-self.origin, end=perf_counter()-self.origin))
                stats['phase'] = previous
        return wrapped

    def before(self, conn, cursor, statement, parameters, context, many):
        context.capacity_began = perf_counter()

    def after(self, conn, cursor, statement, parameters, context, many):
        self.record_sql(statement, context, False)
        if statement.lstrip().upper().startswith('BEGIN IMMEDIATE'):
            stats = request_stats.get()
            conn.info['cutting_test_lock_span'] = dict(request_id=stats.get('request_id', '') if stats else '',
                phase=stats.get('phase', 'request') if stats else 'outside-request',
                waiting=context.capacity_began-self.origin, acquired=perf_counter()-self.origin)

    def released(self, connection, record):
        span = record.info.pop('cutting_test_lock_span', None)
        if span:
            span['released'] = perf_counter()-self.origin
            span['wait_seconds'] = span['acquired']-span['waiting']
            span['hold_seconds'] = span['released']-span['acquired']
            span['release_boundary'] = 'connection-return-after-transaction'
            with self.lock:
                self.lock_spans.append(span)

    def sql_error(self, error):
        if error.execution_context is not None:
            self.record_sql(error.statement or '', error.execution_context, True)

    def record_sql(self, statement, context, failed):
        stats = request_stats.get()
        if stats is not None and hasattr(context, 'capacity_began'):
            seconds = perf_counter()-context.capacity_began
            stats['sql_count'] += 1
            stats['failed_sql'] += int(failed)
            stats['sql_seconds'] += seconds
            if statement.lstrip().upper().startswith('BEGIN IMMEDIATE'):
                stats['lock_seconds'] += seconds

    def heartbeat(self):
        previous = perf_counter()
        while not self.stop.wait(.5):
            now = perf_counter()
            if now-previous > 5:
                self.gaps.append(dict(elapsed=now-previous, at=datetime.now(UTC).isoformat()))
            previous = now

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(2)
        event.remove(self.engine, 'before_cursor_execute', self.before)
        event.remove(self.engine, 'after_cursor_execute', self.after)
        event.remove(self.engine, 'handle_error', self.sql_error)
        event.remove(self.engine, 'checkin', self.released)
        self.patches.close()


def test_failed_lock_wait_is_measured():
    diagnostic = Diagnostics.__new__(Diagnostics)
    stats = dict(sql_count=0, sql_seconds=0., lock_seconds=0., failed_sql=0)
    token = request_stats.set(stats)
    try:
        diagnostic.sql_error(SimpleNamespace(statement='BEGIN IMMEDIATE',
            execution_context=SimpleNamespace(capacity_began=perf_counter()-.1)))
        assert stats['failed_sql'] == stats['sql_count'] == 1
        assert stats['lock_seconds'] >= .1
    finally:
        request_stats.reset(token)


def test_failed_acceptance_keeps_report(tmp_path, monkeypatch):
    monkeypatch.delenv('CUTTING_P5C_EVIDENCE', raising=False)
    def failed(p, root, report):
        report['samples'] = [{'status':200}]
        raise AssertionError('synthetic final reconciliation failure')
    monkeypatch.setattr(sys.modules[__name__], 'run_mixed_http', failed)
    with pytest.raises(AssertionError):
        test_expanded_production_chain_mixed_http(None, tmp_path)
    saved = json.loads((evidence(tmp_path)/'http-soak.json').read_text(encoding='utf-8'))
    assert saved['automated_status'] == 'failed' and saved['samples'] == [{'status':200}]


def test_expanded_production_chain_mixed_http(role_flow, tmp_path):
    report = dict(config=configuration(), automated_status='failed', release_ready=False,
                  production_capacity_accepted=False)
    try:
        run_mixed_http(role_flow, tmp_path, report)
        report['automated_status'] = 'passed'
    except Exception as error:
        report['error'] = dict(type=type(error).__name__, detail=str(error)[:1000])
        raise
    finally:
        (evidence(tmp_path)/'http-soak.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def run_mixed_http(role_flow, tmp_path, report):
    config = report['config']
    p = role_flow
    prepare_closed_order(p)
    add_dispatched_orders(p, config['orders'])
    expand_chains(p, config['chains'])
    # The fixture TestClient has already built the middleware stack. Add the
    # diagnostic wrapper only to this isolated application, then rebuild it.
    p.app.middleware_stack = None
    diagnostics = Diagnostics(p)
    report.update(server_requests=diagnostics.rows, heartbeat_gaps=diagnostics.gaps, lock_spans=diagnostics.lock_spans)
    endpoints = [
        ('planning', '/workspace/planning', {}),
        ('tasks', '/workspace/tasks', {'day': '2026-10-15'}),
        ('inventory', '/workspace/inventory', {}),
        ('costs', '/workspace/costs', {}),
        ('period', '/periods/2026-10', {}),
        ('settlement', '/settlements/2026-10', {'document_id': p.one}),
        ('payments', '/payments/2026-11', {}),
    ]
    failures, samples, writes, runs = [], [], [], []
    report.update(samples=samples, failures=failures, write_records=writes, worker_runs=runs)
    workers = config['workers']
    try:
        with awake_system(), isolated_http(p, tmp_path) as url, ExitStack() as stack:
            sessions = [stack.enter_context(httpx.Client(base_url=url, timeout=30, trust_env=False))
                        for _ in range(workers)]
            for i, session in enumerate(sessions):
                login_http(session, 'clerk' if i < 2 else 'reviewer')
            expected = {}
            for name, path, params in endpoints:
                response = sessions[-1].get(BASE+path, params={'factory_id': 'huakang-c', **params})
                assert response.status_code == 200, (name, response.text)
                expected[name] = projection(name, response.json())
            assert expected['planning'][0] == config['orders']
            assert expected['tasks'][1] == config['chains']*2
            assert expected['tasks'][2]['completed'] == config['chains']*25
            assert expected['inventory'][0] == config['chains']*2
            frozen = sessions[-1].get(BASE+'/periods/2026-10', params={'factory_id':'huakang-c'}).json()['data']['snapshot']
            export_body = dict(factory_id='huakang-c', kind='period', month='2026-10', event_id=expected['period'][1])
            barrier = Barrier(workers, timeout=30)
            abort = Event()
            def worker(index):
                session = sessions[index]
                local, errors, posted = [], [], []
                active_name = ''
                def request(name, method, path, **kwargs):
                    nonlocal active_name
                    active_name = name
                    started = perf_counter()
                    status, size = 0, 0
                    identifier = uuid4().hex
                    try:
                        result = session.request(method, BASE+path, headers={'X-Test-Request-ID':identifier}, **kwargs)
                        status, size = result.status_code, len(result.content)
                        assert status == 200, f'{name}: {status}: {result.text[:300]}'
                        return result
                    finally:
                        local.append(dict(endpoint=name, seconds=perf_counter()-started, status=status,
                                          bytes=size, request_id=identifier))
                barrier.wait()
                began = perf_counter()
                last_progress = began
                deadline = began + config['seconds']
                cycles = 0
                paced = config['workload'] == 'paced'
                next_export = began + (index-2)*7 if index >= 2 else deadline
                while cycles == 0 or perf_counter() < deadline:
                    if abort.is_set():
                        break
                    try:
                        if index < 2:
                            path = f'/orders/http-capacity-{index+1}/reports'
                            current = request('write_basis', 'GET', path, params={'factory_id':'huakang-c', 'history_page':1}).json()
                            task = next(t for t in current['tasks'] if t['task_id'] == 'task-1')
                            body = command(expected_version=current['version'], document_id=f'soak-handover-{index:04d}', entry=dict(
                                task_id='task-1', plan_version=task['plan_version'], day='2026-12-14', mode='sets',
                                kind='handover', sets=1+cycles%2, rejected=0, scrap=0, parts=[],
                                evidence=f'合成写入轮次{cycles}', exception_reason=''))
                            a = request('write', 'POST', path+'/post', json=body).json()
                            b = request('write_retry', 'POST', path+'/post', json=body).json()
                            assert a == b
                            posted.append(dict(line_id=f'http-capacity-{index+1}', document_id=f'soak-handover-{index:04d}', sets=1+cycles%2, operation_id=body['operation_id']))
                        else:
                            selected_endpoints = [endpoints[(cycles+index-2) % len(endpoints)]] if paced else endpoints
                            for name, path, params in selected_endpoints:
                                response = request(name, 'GET', path, params={'factory_id':'huakang-c', **params})
                                assert projection(name, response.json()) == expected[name], name
                            if not paced or perf_counter() >= next_export:
                                response = request('export_preview', 'POST', '/exports/preview', json=export_body)
                                download = request('export_download', 'POST', '/exports/download',
                                                   json={**export_body, 'token':response.json()['token']})
                                validate_workbook(download, multiplier=config['chains'])
                                next_export = perf_counter()+60
                        cycles += 1
                        if index == 0 and perf_counter()-last_progress >= 60:
                            print(f'soak elapsed {perf_counter()-began:.0f}s; writer cycles {cycles}', flush=True)
                            last_progress = perf_counter()
                        diagnostics.stop.wait(2 if paced else (1 if index < 2 else .2))
                    except Exception as error:
                        errors.append(dict(worker=index, endpoint=active_name, type=type(error).__name__, detail=str(error)[:500]))
                        abort.set()
                        break
                return local, errors, posted, dict(seconds=perf_counter()-began, cycles=cycles, writer=index<2)
            diagnostics.start()
            began, cpu = perf_counter(), process_time()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(worker, range(workers)))
            elapsed, cpu = perf_counter()-began, process_time()-cpu
            report.update(elapsed_seconds=elapsed, process_cpu_seconds=cpu)
            for rows, errors, posted, run in results:
                samples.extend(rows); failures.extend(errors); writes.extend(posted); runs.append(run)
            report['frozen_snapshot_unchanged'] = sessions[-1].get(BASE+'/periods/2026-10', params={'factory_id':'huakang-c'}).json()['data']['snapshot'] == frozen
            assert report['frozen_snapshot_unchanged']
            for index in range(2):
                selected = [w for w in writes if w['line_id'] == f'http-capacity-{index+1}']
                if selected:
                    current = sessions[-1].get(BASE+f'/orders/http-capacity-{index+1}/reports', params={'factory_id':'huakang-c'}).json()
                    assert current['summary']['completed'] == 25
                    assert current['summary']['actual_delivery'] == 22 + selected[-1]['sets']
                    document = next(d for d in current['documents'] if d['document_id'] == selected[-1]['document_id'])
                    assert len(document['history']) == len(selected)
                    assert document['posted']['data']['entry']['sets'] == selected[-1]['sets']
            with Session(p.engine) as db:
                persisted = db.scalar(select(func.count()).select_from(CuttingProductionEvent).where(
                    CuttingProductionEvent.document_id.in_(['soak-handover-0000','soak-handover-0001']), CuttingProductionEvent.action=='post'))
                integrity = db.execute(text('PRAGMA integrity_check')).scalar()
                foreign_keys = db.execute(text('PRAGMA foreign_key_check')).all()
            report.update(config=config, elapsed_seconds=elapsed, process_cpu_seconds=cpu, worker_runs=runs,
                requests=len(samples), failures=failures, writes=len(writes), persisted_posts=persisted,
                integrity=integrity, foreign_key_errors=len(foreign_keys), frozen_snapshot_unchanged=True,
                samples=samples, server_requests=diagnostics.rows, heartbeat_gaps=diagnostics.gaps,
                scope='synthetic API-created production chains, two clerk writer sessions; remaining reviewer sessions',
                release_ready=False, production_capacity_accepted=False)
            report['per_endpoint'] = {name: endpoint_metrics(
                [s for s in samples if s['endpoint'] == name], elapsed, [e for e in failures if e['endpoint'] == name])
                for name in sorted({s['endpoint'] for s in samples})}
            assert not failures, failures
            if config['seconds'] >= 60:
                verify_endpoint_coverage(samples)
            assert not diagnostics.gaps, 'Run interrupted: inspect heartbeat gaps; do not accept performance evidence'
            assert persisted == len(writes) >= 2
            assert integrity == 'ok' and not foreign_keys
            assert all(r['seconds'] >= config['seconds'] and r['cycles'] for r in runs)
    finally:
        diagnostics.close()
