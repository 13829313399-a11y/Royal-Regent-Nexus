"""Synthetic isolated benchmark. Refuses an existing database; never reads .env data."""
import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--measure-only', action='store_true')
    p.add_argument('--http', action='store_true', help='Also measure authenticated ASGI request including serialization (no network)')
    args = p.parse_args()
    if args.database.exists() and not args.measure_only: p.error('Database must not exist; use --measure-only only for this script synthetic fixture')
    args.database.parent.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite:///' + args.database.as_posix()
    os.environ['SEED_ADMIN_PASSWORD'] = 'SyntheticOnly123!'
    os.environ['SPRAY_OPS_ENABLED'] = 'false'; os.environ['UV_OPS_ENABLED'] = 'false'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db import init_db, engine, SessionLocal
    init_db()
    from app.models.auth import AuthRegistrationRequest, AuthUser
    from app.models.work_center import WorkCenterEntry, WorkCenterEvent
    from app.services.work_center.registry import current_query
    from app.services.work_center.projection import materialize
    from app.services.work_center.service import snapshot, now
    from app.services.auth import build_auth_context
    from sqlalchemy import select, event
    with SessionLocal() as db:
        if not args.measure_only:
            db.execute(AuthRegistrationRequest.__table__.insert(), [dict(id=f'bench-{i:05}', user_id='user-admin', username=f'synthetic-{i}',
                factory_id='huakang-a', department='engineering', status='pending', submitted_at='2025-01-01 08:00:00') for i in range(10000)])
            db.commit()
            source = current_query(db, None)
            # Bounded projection batches; no browser or API receives the full source set.
            for start in range(0, 10000, 200):
                rows = db.execute(select(source).where(source.c.entity_id >= f'bench-{start:05}', source.c.entity_id < f'bench-{start+200:05}')).mappings().all()
                materialize(db, rows, legacy=True)
            db.commit()
            for start in range(0, 90000, 1000):
                db.execute(WorkCenterEvent.__table__.insert(), [dict(id=f'benchmark-event-{i:06}', entry_id=f'account_requests:bench-{i % 10000:05}:registration:1',
                    source_event_key=f'synthetic-{i}', occurred_at=now(), event_kind='synthetic', safe_summary='合成历史事件') for i in range(start, start+1000)])
            db.commit()
        from sqlalchemy import func
        assert db.scalar(select(func.count()).select_from(AuthRegistrationRequest).where(~AuthRegistrationRequest.id.like('bench-%'))) == 0
        assert db.scalar(select(func.count()).select_from(WorkCenterEvent)) == 100000
        user = build_auth_context(db, db.get(AuthUser, 'user-admin'))
        plans, statements = [], []
        def capture(conn, cursor, statement, params, context, many):
            if statement.lstrip().upper().startswith(('SELECT', 'WITH')):
                statements.append((statement, params))
        event.listen(engine, 'before_cursor_execute', capture)
        start = time.perf_counter(); first = snapshot(db, user); cold = (time.perf_counter() - start) * 1000
        event.remove(engine, 'before_cursor_execute', capture)
        for statement, params in statements:
            plans.extend(row[3] for row in db.connection().exec_driver_sql('EXPLAIN QUERY PLAN ' + statement, params))
        timings = []
        for _ in range(20):
            start = time.perf_counter(); result = snapshot(db, user); timings.append((time.perf_counter() - start) * 1000)
            assert result['summary']['actionable_total'] == 10000 and len(result['items']) == 30
        report = dict(platform=platform.platform(), python=platform.python_version(), cpu=platform.processor(), concurrency=1,
            database='SQLite local synthetic', active_entries=10000, historical_events=100000, page_size=30, samples=len(timings),
            scope='service snapshot including SQL and DTO; excludes HTTP, authentication, network and browser',
            cold_ms=round(cold, 2), p50_ms=round(statistics.median(timings), 2), p95_ms=round(sorted(timings)[18], 2),
            select_count=len(statements), query_plan=plans, target_p95_ms=350)
    if args.http:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.work_center import router
        from app.services.auth import create_session, SESSION_COOKIE_NAME
        app = FastAPI(); app.include_router(router)
        with SessionLocal() as db:
            token = create_session(db, db.get(AuthUser, 'user-admin')); db.commit()
        with TestClient(app) as client:
            client.cookies.set(SESSION_COOKIE_NAME, token)
            samples = []
            for _ in range(21):
                start = time.perf_counter(); response = client.get('/api/work-center/snapshot')
                samples.append((time.perf_counter() - start) * 1000)
                assert response.status_code == 200, response.text
                assert response.json()['summary']['actionable_total'] == 10000
            report['authenticated_asgi'] = dict(scope='HTTP routing, current authentication, snapshot and JSON serialization; excludes TCP, reverse proxy and browser',
                cold_ms=round(samples[0], 2), samples=20, p50_ms=round(statistics.median(samples[1:]), 2), p95_ms=round(sorted(samples[1:])[18], 2))
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'query_plan'}, ensure_ascii=False))

if __name__ == '__main__': main()
