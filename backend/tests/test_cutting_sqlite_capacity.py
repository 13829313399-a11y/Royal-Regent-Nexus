"""Bounded synthetic SQLite multi-order API baseline, not a production SLA.

Independent request sessions use a pytest-owned database. No business DB URL,
original rows, real accounts, network service or live application is used.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from math import ceil
from time import perf_counter, process_time
import json
import sqlite3
import statistics

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_cutting_ops import client, command, BASE
from test_cutting_orders import flow, Line, Dispatch, ledger, DispatchIn, CuttingOrder, CuttingOrderRevision
from test_cutting_p5c import evidence, logical_digest


def metrics(samples, elapsed, cpu):
    times = sorted(row['seconds'] for row in samples)
    failures = sum(row['status'] != 200 for row in samples)
    return dict(requests=len(samples), failures=failures, failure_rate=failures / len(samples),
                median_seconds=statistics.median(times), p95_seconds=times[ceil(.95 * len(times))-1],
                max_seconds=max(times), wall_seconds=elapsed, process_cpu_seconds=cpu,
                requests_per_second=len(samples)/elapsed,
                max_response_bytes=max(row['bytes'] for row in samples), samples=samples)


def measure(calls, workers):
    def call(fn):
        start = perf_counter()
        response = fn()
        return response, dict(seconds=perf_counter()-start, status=response.status_code,
                              bytes=len(response.content))
    start, cpu = perf_counter(), process_time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(call, calls))
    return [r for r, _ in results], metrics([s for _, s in results], perf_counter()-start, process_time()-cpu)


@pytest.mark.parametrize('count,workers', [(100, 4), (500, 8)])
def test_multi_order_read_write_and_restore_baseline(flow, tmp_path, count, workers):
    p = flow
    # Source ledger fixtures use its real dispatch service; receipt writes below
    # go through real APIs. No invented revision clones or frozen balances.
    with Session(p.engine) as db:
        for i in range(1, count):
            line = Line(id=f'capacity-{i}', factory_id='huakang-c', customer_code='synthetic',
                        customer_name='合成容量样本', identity_key=f'capacity-{i}',
                        reference_no=f'CAP-{i:06}', product_no='00012', quantity=Decimal('100'),
                        shipped_quantity=0, status='active', version=1, revision=1,
                        data={'quantity':'100', 'requested_ship_date':'2026-10-30'},
                        created_at='2026-10-09', updated_at='2026-10-09')
            db.add(line)
            db.flush()
            ledger.dispatch(db, line, DispatchIn(expected_revision=1, recipients=['cutting']), 'synthetic')
        db.commit()
        dispatched = list(db.scalars(select(Dispatch).where(Dispatch.recipient == 'cutting')))
        targets = [(d.line_id, command(dispatch_id=d.id)) for d in dispatched[:32]]
    assert len(dispatched) == count
    before = logical_digest(p.engine.url.database)
    pages = list(range(1, ceil(count/50)+1)) * 4
    responses, reads = measure([
        lambda page=page: p.get(BASE+'/orders', params={'factory_id':'huakang-c', 'page':page})
        for page in pages], workers)
    assert reads['failures'] == 0
    assert all(r.json()['total'] == count for r in responses)
    first_pass = responses[:ceil(count/50)]
    assert len({row['line_id'] for r in first_pass for row in r.json()['data']}) == count
    assert logical_digest(p.engine.url.database) == before

    # Mix independent writes and retried operation IDs with reads. Application
    # locking must queue writers and preserve exactly one receipt per order.
    calls = [lambda line=line, body=body: p.post(f'{BASE}/orders/{line}/receive', json=body)
             for line, body in targets for _ in range(2)]
    calls = [fn for call in calls for fn in (call, lambda: p.get(BASE+'/orders', params={'factory_id':'huakang-c'}))]
    responses, mixed = measure(calls, workers)
    assert mixed['failures'] == 0, [(r.status_code, r.text[:400]) for r in responses if r.status_code != 200]
    with Session(p.engine) as db:
        assert db.scalar(select(func.count()).select_from(CuttingOrder)) == len(targets)
        assert db.scalar(select(func.count()).select_from(CuttingOrderRevision)) == len(targets)
        assert set(db.scalars(select(CuttingOrder.version))) == {1}
    # Scheduling filters currently scan the factory's matching orders rather
    # than only one page. Measure this heavier path separately from basic lists.
    before_filter = logical_digest(p.engine.url.database)
    filtered_responses, filtered = measure([
        lambda: p.get(BASE+'/orders', params={'factory_id':'huakang-c', 'plan_status':'unplanned'})
        for _ in range(20)], workers)
    assert filtered['failures'] == 0
    assert all(r.json()['total'] == count and len(r.json()['data']) == 50 for r in filtered_responses)
    assert logical_digest(p.engine.url.database) == before_filter
    restored = tmp_path/'capacity-restored.db'
    start = perf_counter()
    with sqlite3.connect(p.engine.url.database) as source, sqlite3.connect(restored) as target:
        source.backup(target)
    restore_seconds = perf_counter()-start
    assert logical_digest(restored) == logical_digest(p.engine.url.database)
    with sqlite3.connect(restored) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        journal_mode = db.execute('PRAGMA journal_mode').fetchone()[0]
    (evidence(tmp_path)/f'capacity-sqlite-{count}-{workers}.json').write_text(json.dumps(dict(
        engine='SQLite', sqlite_version=sqlite3.sqlite_version, orders=count, workers=workers,
        journal_mode=journal_mode, reads=reads, mixed=mixed, filtered=filtered,
        restored_bytes=restored.stat().st_size,
        backup_seconds=restore_seconds, restore_equal=True, read_only_phase_unchanged=True,
        distinct_receipts=len(targets), duplicate_receipts=0,
        scope='in-process API; dispatched orders and receipt workload; excludes full-history cost scans, network and real users',
        production_capacity_accepted=False), ensure_ascii=False, indent=2), encoding='utf-8')


def test_percentile_and_failure_metrics_do_not_hide_errors():
    samples = [dict(seconds=i, status=500 if i == 20 else 200, bytes=i) for i in range(1, 21)]
    result = metrics(samples, 10, 2)
    assert result['p95_seconds'] == 19 and result['max_seconds'] == 20
    assert result['failures'] == 1 and result['failure_rate'] == .05
