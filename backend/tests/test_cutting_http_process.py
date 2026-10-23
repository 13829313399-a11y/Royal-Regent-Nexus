"""Safety and phase attribution for the independent synthetic API probe."""
import json
import importlib.util
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cutting_http_process import validate_copy
from test_cutting_http_soak import Diagnostics
from app.services.transaction_lock import lock_transaction

spec = importlib.util.spec_from_file_location('lock_phase_runner', Path(__file__).parents[1]/'scripts/verify_cutting_lock_phases.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('damage', ['gap', 'failed_sql', 'missing_retry', 'retry_lock', 'retry_admission'])
def test_diagnostic_failures_cannot_be_reported_as_passed(damage):
    sample = dict(endpoint='payment_save_retry', request_id='retry')
    diagnostic = dict(heartbeat_gaps=[], lock_spans=[], requests=[dict(request_id='retry', failed_sql=0, lock_seconds=0)])
    assert runner.diagnostics_summary(diagnostic, [sample])['payment_retries'] == 1
    if damage == 'gap': diagnostic['heartbeat_gaps'] = [{'elapsed':10}]
    if damage == 'failed_sql': diagnostic['requests'][0]['failed_sql'] = 1
    if damage == 'missing_retry': diagnostic['requests'] = []
    if damage == 'retry_lock': diagnostic['requests'][0]['lock_seconds'] = .01
    if damage == 'retry_admission': diagnostic['requests'][0]['admission_seconds'] = .01
    with pytest.raises(AssertionError):
        runner.diagnostics_summary(diagnostic, [sample])


def test_seed_requires_passed_exact_profile_before_copying(tmp_path):
    path = tmp_path/'.tmp/cutting-http-soak/run/databases/case/cutting.db'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not opened by provenance validation')
    run = path.parents[2]
    (run/'evidence').mkdir()
    (run/'report.json').write_text(json.dumps({'automated_status':'passed'}))
    inner = dict(automated_status='passed', config=dict(orders=500,chains=100,finance_chains=20,workers=10))
    evidence = run/'evidence/financial-soak.json'
    evidence.write_text(json.dumps(inner))
    assert runner.seed_file(path, root=tmp_path) == path.resolve()
    inner['automated_status'] = 'failed'
    evidence.write_text(json.dumps(inner))
    with pytest.raises(ValueError): runner.seed_file(path, root=tmp_path)
    inner.update(automated_status='passed', config=dict(inner['config'],chains=50))
    evidence.write_text(json.dumps(inner))
    with pytest.raises(ValueError): runner.seed_file(path, root=tmp_path)


def test_copy_guard_rejects_nonfixture_databases_without_writing(tmp_path):
    path = tmp_path/'.tmp/probe/cutting.db'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE auth_users (username TEXT)')
        db.executemany('INSERT INTO auth_users VALUES (?)', [(f'p5b-{i}',) for i in range(8)])
    before = path.read_bytes()
    with pytest.raises(ValueError):
        validate_copy(path, root=tmp_path)
    (path.parent/'fixture.json').write_text(json.dumps({'kind':'cutting-synthetic-copy'}))
    assert validate_copy(path, root=tmp_path) == path.resolve()
    with pytest.raises(ValueError):
        validate_copy(path, root=tmp_path/'other')
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        db.execute("UPDATE auth_users SET username='real-employee' WHERE username='p5b-0'")
    with pytest.raises(ValueError):
        validate_copy(path, root=tmp_path)


def test_lock_telemetry_pairs_owner_phase_and_connection_return(tmp_path):
    engine = create_engine('sqlite:///'+(tmp_path/'phases.db').as_posix(), connect_args={'check_same_thread':False})
    app = FastAPI()
    def capture():
        with Session(engine) as db:
            lock_transaction(db, 'cutting-master', 'huakang-c')
            db.rollback()
        return {'captured':True}
    diagnostic = Diagnostics(SimpleNamespace(app=app, engine=engine))
    app.get('/probe')(diagnostic.tracked(capture, 'probe.capture'))
    try:
        with TestClient(app) as client:
            for identifier in ['first-owner', 'second-owner']:
                assert client.get('/probe', headers={'X-Test-Request-ID':identifier}).json() == {'captured':True}
        assert len(diagnostic.lock_spans) == 2
        assert [s['request_id'] for s in diagnostic.lock_spans] == ['first-owner', 'second-owner']
        assert all(s['phase']=='probe.capture' and s['waiting'] <= s['acquired'] <= s['released']
                   and s['release_boundary']=='connection-return-after-transaction' for s in diagnostic.lock_spans)
        assert all(row['phases'][-1]['name']=='probe.capture' for row in diagnostic.rows)
        assert all(sum(p['name']=='cutting_sqlite_queue.reserve' for p in row['phases'])==1
                   and row['admission_seconds']>=0 for row in diagnostic.rows)
    finally:
        diagnostic.close()
        engine.dispose()
