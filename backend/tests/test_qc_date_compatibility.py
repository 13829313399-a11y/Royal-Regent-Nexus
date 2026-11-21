"""Persistent date compatibility: no invented history or lossy projection recovery."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import HTTPException

from app.services import qc_inspection_sheet as sheet, qc_inspection_summary as summary
from test_customer_order_ledger import engine, db
from test_qc_actual_date import isolated, scheduled, save, submit, transition, reread


def projection_rows():
    with summary.store() as c:
        return [tuple(r) for r in c.execute('SELECT * FROM records ORDER BY id')]


@pytest.mark.parametrize('patch', [
    {'inspectionDate': None}, {'inspectionDate': ''}, {'inspectionDate': '2026-02-30'},
    {'inspectionDate': '20261105'}, {'inspectionDateSource': 'unknown'},
    {'inspectionDateSource': None}, {'inspectionDateSource': 'schedule', 'remove_date': True},
])
def test_corrupt_marked_snapshot_cannot_blank_valid_projection(db, patch):
    row = transition(submit(save(scheduled(db), '')))
    before = projection_rows()
    corrupted = {**row, **{k: v for k, v in patch.items() if k != 'remove_date'}}
    if patch.get('remove_date'):
        corrupted.pop('inspectionDate')
    with sheet.store(True) as c:
        c.execute('UPDATE entry_details SET approved_snapshot=? WHERE entry_id=?',
                  (json.dumps(corrupted), row['id']))
    for read in [lambda: summary.listing('huaxing', {}), lambda: reread(row)]:
        with pytest.raises(HTTPException) as error:
            read()
        assert error.value.status_code == 409
        assert '快照' in error.value.detail
        assert projection_rows() == before
    with sheet.store() as c:
        # Do not "repair" authoritative evidence as a side effect of reading.
        stored = c.execute('SELECT approved_snapshot FROM entry_details WHERE entry_id=?', (row['id'],)).fetchone()[0]
        assert json.loads(stored) == corrupted


def test_lost_marker_downgrade_cannot_replace_a_new_confirmation_with_blank(db):
    row = transition(submit(save(scheduled(db), '')))
    before = projection_rows()
    legacy = {k: v for k, v in row.items() if k not in {'inspectionDate', 'inspectionDateSource'}}
    with sheet.store(True) as c:
        c.execute('UPDATE entry_details SET approved_snapshot=? WHERE entry_id=?',
                  (json.dumps(legacy), row['id']))
    with pytest.raises(HTTPException) as error:
        summary.listing('huaxing', {})
    assert error.value.status_code == 409
    assert '版本不兼容' in error.value.detail
    assert projection_rows() == before


@pytest.mark.parametrize('planned', ['2026-11-05', ''])
def test_explicit_clear_then_reconfirm_is_not_confused_with_lossy_recovery(db, planned):
    row = scheduled(db)
    if not planned:
        # An existing unscheduled task is a supported historical case.
        with sheet.store(True) as c:
            raw = json.loads(c.execute('SELECT base FROM entries WHERE id=?', (row['id'],)).fetchone()[0])
            raw.update(dateFrom='', dateTo='')
            c.execute('UPDATE entries SET base=? WHERE id=?', (json.dumps(raw), row['id']))
        row = reread(row)
    first = transition(submit(save(row, '2026-11-06')))
    pending = transition(first, 'revoke')
    final = transition(save(pending, '', review=True))
    assert final['inspectionDate'] == planned
    assert final['inspectionDateSource'] == ('schedule' if planned else None)
    assert final['actualDate'] == ''
    item = summary.listing('huaxing', {})['items'][0]
    assert item['inspectionDate'] == planned
    with sheet.store() as c:
        events = [json.loads(r[0]) for r in c.execute("SELECT snapshot FROM changes WHERE action='confirm' ORDER BY id")]
    assert events[0] == first and len(events) == 2


def test_mixed_old_new_manual_fallback_missing_and_imported_dates(db, monkeypatch):
    # Generate legacy confirmations through the unchanged legacy rule, then retain their bytes.
    old = []
    for n, actual in enumerate(['', '2026-10-31'], 1):
        pending = submit(save(scheduled(db, n), actual))
        with monkeypatch.context() as m:
            m.setattr(summary, 'resolve_inspection_date', lambda _: {})
            old.append(transition(pending))
    manual = transition(submit(save(scheduled(db, 3), '2026-11-06')))
    fallback = transition(submit(save(scheduled(db, 4), '')))
    from test_qc_inspection_summary import preview, history
    receipt = preview(history())
    # Historical import exercises its separate parser/projection contract.
    summary.commit_history('huaxing', 'operator', receipt['id'])
    before = projection_rows()
    for _ in range(2):
        result = summary.listing('huaxing', {})
        by_entry = {v.get('entryId'): v for v in result['items'] if v.get('entryId')}
        assert by_entry[old[0]['id']]['inspectionDate'] == ''
        assert by_entry[old[1]['id']]['inspectionDate'] == '2026-10-31'
        assert 'inspectionDateSource' not in by_entry[old[0]['id']]
        assert by_entry[manual['id']]['inspectionDate'] == '2026-11-06'
        assert by_entry[fallback['id']]['inspectionDate'] == '2026-11-05'
        for item in result['items']:
            summary.detail('huaxing', item['id'])
    assert projection_rows() == before


def test_real_process_restart_recovers_frozen_projection(db, monkeypatch, tmp_path):
    row = transition(submit(save(scheduled(db), '')))
    original = deepcopy(row)
    with summary.store(True) as c:
        c.execute('DELETE FROM records')
    code = '''
import json
from app.services import qc_inspection_summary as summary
def forbidden(_): raise AssertionError('Read recalculated confirmation')
summary.resolve_inspection_date = forbidden
data = summary.listing('huaxing', {})
assert len(data['items']) == 1
print(json.dumps(data['items'][0]))
'''
    env = {**os.environ, 'QC_DEPARTMENT_DATA_DIR': sheet.settings.qc_department_data_dir,
           'QC_DEPARTMENT_MANAGED': 'false', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run([sys.executable, '-c', code], env=env, text=True, capture_output=True, check=True)
    restored = json.loads(result.stdout)
    assert restored['inspectionDate'] == '2026-11-05'
    assert restored['inspectionDateSource'] == 'schedule' and restored['actualDate'] == ''
    assert reread(row) == original


def test_two_http_clients_date_conflict_partial_confirmation_and_retry(db, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from uuid import uuid4
    from app.api import qc_department as gateway
    from app.db import get_db
    from app.services import auth
    from app.services.auth import get_current_user
    from test_qc_workflow import qc_user
    monkeypatch.setattr(auth, 'add_auth_audit', lambda *a, **k: None)
    async def upstream(*args):
        return httpx.Response(200, json={'records': []})
    monkeypatch.setattr(gateway, 'upstream', upstream)
    app = FastAPI()
    app.include_router(gateway.router)
    app.dependency_overrides[get_current_user] = qc_user
    app.dependency_overrides[get_db] = lambda: db
    first, second = scheduled(db, 101), scheduled(db, 102)
    with TestClient(app) as a, TestClient(app) as b:
        base = a.get('/api/qc-department/huaxing/api/health').json()['frame_url'] + 'api/'
        url = base + 'inspection-sheet/entries/' + first['id']
        body = dict(revision=first['revision'], result='PASS', remark='',
                    inspectionExecution={'actualDate': '2026-11-09'})
        saved = a.post(url + '/save', json=body)
        assert saved.status_code == 200
        stale = b.post(url + '/save', json={**body, 'inspectionExecution': {'actualDate': ''}})
        assert stale.status_code == 409 and reread(first)['actualDate'] == '2026-11-09'
        pending = a.post(url + '/submit', json={'revision': saved.json()['revision']}).json()
        second = submit(save(second, ''))
        request = dict(requestKey=uuid4().hex, entries=[
            dict(id=first['id'], revision=pending['revision']),
            dict(id=second['id'], revision=second['revision'] - 1)])
        for client in (a, b):
            result = client.post(base + 'inspection-sheet/review/confirm', json=request)
            assert result.status_code == 200
            assert (result.json()['succeeded'], result.json()['failed']) == (1, 1)
        assert reread(first)['inspectionDate'] == '2026-11-09'
        assert reread(second)['reviewState'] == 'pending'
        assert summary.listing('huaxing', {})['total'] == 1
        with sheet.store() as c:
            assert c.execute("SELECT count(*) FROM changes WHERE entry_id=? AND action='confirm'", (first['id'],)).fetchone()[0] == 1


def test_missing_approved_snapshot_is_identifiable_without_inventing_a_date(db):
    row = transition(submit(save(scheduled(db), '')))
    before = projection_rows()
    with sheet.store(True) as c:
        c.execute("UPDATE entry_details SET approved_snapshot='' WHERE entry_id=?", (row['id'],))
    # Read-only preflight locates records that must be reviewed before deployment.
    with sheet.store() as c:
        missing = c.execute("SELECT entry_id FROM entry_details WHERE flow_version=2 AND review_state='approved' AND coalesce(approved_snapshot,'')='' ").fetchall()
    assert [r[0] for r in missing] == [row['id']]
    summary.listing('huaxing', {})
    assert projection_rows() == before
