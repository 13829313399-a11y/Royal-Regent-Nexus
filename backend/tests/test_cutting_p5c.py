"""P5c synthetic history baseline, SQLite restore and actual export print contracts.

Bulk history amplifies one correction chain; it is NOT a many-order capacity SLA.
All database access comes from pytest-owned fixtures, never application settings.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json
import os
import sqlite3
import statistics

import pytest
from sqlalchemy import select, insert, update
from test_cutting_exports import (client, flow, planned, production, accounting, custody, bridge,
    month_client, paid_setup, fees, fresh_auth, download, request, lock, act, save, decision,
    reviewer, ok, BASE)
from test_cutting_reporting import read as reports
from app.models.cutting_ops import CuttingProductionEvent, CuttingOrderRevision, CuttingOrder


def evidence(tmp_path):
    path = Path(os.environ.get('CUTTING_P5C_EVIDENCE', str(tmp_path/'evidence')))
    path.mkdir(parents=True, exist_ok=True)
    return path


def logical_digest(path):
    with sqlite3.connect(path) as db:
        return sha256('\n'.join(db.iterdump()).encode()).hexdigest()


@pytest.mark.parametrize('count', [100, 1000, 5000])
def test_long_correction_history_read_baseline(month_client, tmp_path, count):
    p = month_client
    before = reports(p)['summary']
    # Expand an existing legal posted correction and corresponding order revisions.
    # Only synthetic fixture setup bypasses commands; measured reads use real APIs.
    event_table, revision_table = CuttingProductionEvent.__table__, CuttingOrderRevision.__table__
    with p.engine.begin() as conn:
        event = dict(conn.execute(select(event_table).where(event_table.c.document_id == p.report_id)
                                 .order_by(event_table.c.version.desc())).mappings().first())
        revision = dict(conn.execute(select(revision_table).where(revision_table.c.line_id == 'line-1')
                                    .order_by(revision_table.c.version.desc())).mappings().first())
        version = revision['version']
        conn.execute(insert(event_table), [deepcopy(event) | {'id': uuid4().hex, 'version': version+i+1,
                     'reason': 'P5c synthetic history amplification'} for i in range(count)])
        conn.execute(insert(revision_table), [deepcopy(revision) | {'version': version+i+1,
                     'reason': 'P5c synthetic history amplification'} for i in range(count)])
        conn.execute(update(CuttingOrder).where(CuttingOrder.line_id == 'line-1').values(version=version+count))
    digest_before = logical_digest(p.engine.url.database)
    endpoints = {
        'reports': lambda: p.get(BASE+'/orders/line-1/reports', params={'factory_id':'huakang-c'}),
        'closing': lambda: p.get(BASE+'/orders/line-1/closing-preview', params={'factory_id':'huakang-c','month':'2026-10'}),
        'cutover': lambda: p.post(BASE+'/cutover/preview', json={'factory_id':'huakang-c','month':'2026-11','scope':'internal','batch_size':1}),
    }
    metrics = {}
    for name, call in endpoints.items():
        timings = []
        for _ in range(3):
            start = perf_counter(); response = call(); timings.append(perf_counter()-start)
            assert response.status_code == 200, response.text[:1000]
            if name == 'reports':
                assert response.json()['summary'] == before
        metrics[name] = {'seconds':timings, 'median_seconds':statistics.median(timings),
                         'max_seconds':max(timings), 'response_bytes':len(response.content)}
    # The browser requests bounded history, but summary/effective balances are
    # identical to the full replay used by immutable closing/export workflows.
    paged = {}
    for name, endpoint in [('reports', '/reports'), ('closing', '/closing-preview')]:
        params = dict(factory_id='huakang-c', history_page=1)
        if name == 'closing': params['month'] = '2026-10'
        start = perf_counter()
        response = p.get(BASE+'/orders/line-1'+endpoint, params=params)
        elapsed = perf_counter()-start
        assert response.status_code == 200, response.text[:1000]
        value = response.json()
        full = endpoints[name]().json()
        for key in (('summary','tasks') if name == 'reports' else ('production','materials','issues','basis')):
            assert value[key] == full[key]
        count_in_page = sum(len(d['history']) for d in value.get('documents', value.get('production_documents', [])))
        assert count_in_page <= 20
        assert len(response.content) < metrics[name]['response_bytes']
        paged[name] = dict(seconds=elapsed, response_bytes=len(response.content),
                           history=value['history_pagination'])
    assert logical_digest(p.engine.url.database) == digest_before
    (evidence(tmp_path)/f'history-{count}.json').write_text(json.dumps({
        'additional_correction_events':count, 'orders':1, 'engine':'SQLite', 'concurrent_readers':1,
        'scope':'in-process API, warm serial reads; not HTTP/network or production SLA',
        'metrics':metrics, 'paged':paged, 'read_only':True, 'quantity_unchanged':True}, indent=2), encoding='utf-8')


def test_isolated_sqlite_backup_restores_frozen_rows_and_guards(month_client, tmp_path):
    p = month_client
    lock(p)
    original = Path(p.engine.url.database).resolve()
    assert original.is_relative_to(tmp_path.parent.resolve())
    restored = tmp_path/'restored.db'
    start = perf_counter()
    with sqlite3.connect(original) as source, sqlite3.connect(restored) as target:
        source.backup(target)
    seconds = perf_counter()-start
    assert logical_digest(original) == logical_digest(restored)
    with sqlite3.connect(restored) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        triggers = db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        assert triggers
        row = db.execute('SELECT id FROM cutting_ops_production_events LIMIT 1').fetchone()
        with pytest.raises(sqlite3.DatabaseError):
            db.execute('DELETE FROM cutting_ops_production_events WHERE id=?', row)
    (evidence(tmp_path)/'restore.json').write_text(json.dumps({'engine':'SQLite','seconds':seconds,
        'bytes':restored.stat().st_size,'logical_digest':logical_digest(restored),'integrity':'ok',
        'foreign_keys':'ok','immutable_delete_blocked':True,'trigger_count':len(triggers),
        'scope':'synthetic database only; excludes attachments, secrets and PostgreSQL'}), encoding='utf-8')


def test_browser_history_contract_rejects_stale_versions_and_invalid_pages(month_client):
    p = month_client
    params = dict(factory_id='huakang-c', history_page=1)
    response = p.get(BASE+'/orders/line-1/reports', params=params)
    assert response.status_code == 200
    value = response.json()
    full = reports(p)
    assert value['summary'] == full['summary']
    assert p.get(BASE+'/orders/line-1/reports', params=dict(params, expected_version=value['version']+1)).status_code == 409
    assert p.get(BASE+'/orders/line-1/reports', params=dict(params, history_page=0)).status_code == 422
    assert p.get(BASE+'/orders/line-1/reports', params=dict(params, factory_id='huakang-b')).status_code == 422
    params['month'] = '2026-10'
    response = p.get(BASE+'/orders/line-1/closing-preview', params=params)
    assert response.status_code == 200
    assert 'costs' not in response.json()
    assert p.get(BASE+'/orders/line-1/closing-preview', params=dict(params, expected_history_token='old')).status_code == 409
    assert p.get(BASE+'/orders/line-1/closing-preview', params=dict(params, history_scope='bad')).status_code == 422


def retain_export(p, body, name, tmp_path):
    start = perf_counter()
    wb, preview, response = download(p, body)
    seconds = perf_counter()-start
    for ws in wb:
        assert ws.print_area and ws.print_title_rows == '$1:$2'
        assert ws.page_setup.orientation == 'landscape' and ws.page_setup.paperSize == 8
        assert ws.freeze_panes == 'B3'
        assert '&P' in ws.oddFooter.center.text
        assert all(cell.data_type != 'f' for row in ws for cell in row)
    folder = evidence(tmp_path)
    (folder/(name+'.xlsx')).write_bytes(response.content)
    (folder/(name+'.json')).write_text(json.dumps({'preview':preview,'sha256':sha256(response.content).hexdigest(),
         'sheets':wb.sheetnames,'preview_download_readback_seconds':seconds,'bytes':len(response.content),
         'scope':'file contract only; native pagination requires separate inspection'}, ensure_ascii=False,indent=2),encoding='utf-8')


def test_period_current_and_historical_print_files(month_client, tmp_path):
    event = lock(month_client)
    body = request('period',event_id=event['id'])
    retain_export(month_client,body,'period',tmp_path)
    act(month_client,'reopen')
    retain_export(month_client,body,'period-history',tmp_path)


def test_payment_and_settlement_print_files(paid_setup, tmp_path):
    p = paid_setup
    one = save(p)
    ok(decision(p,one,'submit')); reviewer(p); ok(decision(p,one,'confirm'))
    retain_export(p,request(),'payments',tmp_path)
    value = ok(p.get(BASE+'/settlements/2026-10',params={'factory_id':'huakang-c','document_id':p.one}))
    retain_export(p,request('settlement',document_id=p.one,event_id=value['event_id']),'settlement',tmp_path)
