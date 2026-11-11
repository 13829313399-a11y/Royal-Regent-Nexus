"""Phase 4.1: original input vs confirmed date, using isolated QC stores only."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4
import json
import sqlite3

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services import qc_workflow as wf, qc_inspection_sheet as sheet, qc_inspection_summary as summary
from test_customer_order_ledger import engine, db, ingest
from test_qc_workflow import ACTOR, qc_user
from test_qc_flow_completion import push, entries


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(wf.settings, 'qc_department_data_dir', str(tmp_path / 'companies'))


def scheduled(db, n=1, start='2026-11-05', end='2026-11-07'):
    src = wf.create_schedule('huaxing', {'requestKey': uuid4().hex, 'row': dict(
        dateFrom=start, dateTo=end, customer='Phase 4.1 隔离验收', poNo=f'TEST-{n:04}',
        country='UK', productNo='SAME-SKU', productName=f'日期验收 {n}', quantity='100',
        unitsPerCarton='10', cartonCount='10', production='测试', agency='行验',
        customerPo='', remark='仅隔离测试')}, ACTOR)
    task = push(db, [src])['items'][0]
    row = next(r for r in entries(db) if r['workflowId'] == task['id'])
    return row


def save(row, actual, *, review=False, result='PASS'):
    return sheet.save('huaxing', row['id'], dict(revision=row['revision'], result=result,
        remark=row['remark'], inspectionExecution={'actualDate': actual}), ACTOR, review=review)


def transition(row, action='confirm', key=None):
    response = sheet.review_batch('huaxing', action, dict(
        entries=[dict(id=row['id'], revision=row['revision'])], requestKey=key or uuid4().hex), ACTOR)
    assert response['succeeded'] == 1, response
    return response['results'][0]['item']


def submit(row):
    return sheet.submit('huaxing', row['id'], {'revision': row['revision']}, ACTOR)


def reread(row):
    with sheet.store() as c:
        return sheet.unpack(c, sheet.get(c, 'huaxing', row['id']))


@pytest.mark.parametrize('actual,expected,origin', [
    ('2026-11-06', '2026-11-06', 'qc_manual'),
    ('', '2026-11-05', 'schedule'),
    ('2026-11-05', '2026-11-05', 'qc_manual'),
    ('2028-02-29', '2028-02-29', 'qc_manual'),
    (None, '2026-11-05', 'schedule'),
])
def test_date_decided_only_on_confirmation_and_recovered_verbatim(db, actual, expected, origin, monkeypatch):
    row = scheduled(db)
    original = deepcopy(row)
    row = save(row, actual)
    assert reread(row)['inspectionExecution']['actualDate'] == (actual or '')
    assert row['sourceRecord'] == original['sourceRecord']
    assert 'inspectionDate' not in row and 'inspectionDateSource' not in row
    pending = submit(row)
    assert 'inspectionDate' not in pending and summary.listing('huaxing', {})['total'] == 0
    row = transition(pending)
    assert row['actualDate'] == (actual or '')
    assert row['inspectionExecution']['actualDate'] == (actual or '')
    assert (row['inspectionDate'], row['inspectionDateSource']) == (expected, origin)
    assert row['dateFrom'] == '2026-11-05' and row['dateTo'] == '2026-11-07'
    with sheet.store() as c:
        detail = c.execute('SELECT * FROM entry_details WHERE entry_id=?', (row['id'],)).fetchone()
        assert 'inspectionDate' not in json.loads(detail['submitted_snapshot'])
        snap = json.loads(detail['approved_snapshot'])
        event = json.loads(c.execute("SELECT snapshot FROM changes WHERE entry_id=? AND action='confirm'", (row['id'],)).fetchone()[0])
        assert snap == event == row
    assert reread(row)['inspectionDate'] == expected
    with summary.store(True) as c:
        c.execute('DELETE FROM records')  # Simulate a missing projection in this isolated database.
    monkeypatch.setattr(summary, 'resolve_inspection_date', lambda _: pytest.fail('Reads must not recalculate'))
    item = summary.listing('huaxing', {})['items'][0]
    assert (item['inspectionDate'], item['inspectionDateSource']) == (expected, origin)
    assert item['actualDate'] == (actual or '') and item['sourceRecord'] == original['sourceRecord']
    before = deepcopy(item)
    assert summary.listing('huaxing', {})['items'][0] == before


def test_clear_override_preserves_other_execution_source_and_audit(db):
    row = submit(save(scheduled(db), '2026-11-06'))
    row = sheet.save('huaxing', row['id'], dict(revision=row['revision'], result=row['result'],
        remark=row['remark'], inspectionExecution={'reportNo': 'KEEP', 'sampleQuantity': '0'}), ACTOR, review=True)
    row = sheet.return_to_inspection('huaxing', row['id'], dict(revision=row['revision'], requestKey=uuid4().hex), ACTOR)['item']
    original = deepcopy(row['sourceRecord'])
    row = save(row, '')
    row = reread(row)
    assert row['actualDate'] == row['inspectionExecution']['actualDate'] == ''
    assert row['inspectionExecution']['reportNo'] == 'KEEP'
    assert row['inspectionExecution']['sampleQuantity'] == '0'
    assert row['sourceRecord'] == original
    change = sheet.audit('huaxing', row['id'])['items'][0]
    assert change['changes']['inspectionExecution.actualDate'] == {'before': '2026-11-06', 'after': ''}
    row = transition(submit(row))
    assert row['inspectionDate'] == '2026-11-05' and row['inspectionDateSource'] == 'schedule'


@pytest.mark.parametrize('patch', [
    {'actualDate': '2026-02-30'}, {'actualDate': '11/05'}, {'actualDate': '20261105'},
    {'actualDate': '2026-11-05T00:00:00Z'}, {'actualDate': True},
    {'actualDate': '2026-11-06', 'reportNo': 'FORBIDDEN'}, {'inspector': 'FORBIDDEN'},
    {'actualDate': '', 'actualQuantity': '5'}, {'inspectionDateSource': 'qc_manual'}, [],
])
def test_invalid_or_out_of_scope_workbench_patch_never_writes(db, patch):
    row = scheduled(db)
    before = deepcopy(reread(row))
    with pytest.raises(HTTPException) as error:
        sheet.save('huaxing', row['id'], dict(revision=row['revision'], result='PASS',
            remark=row['remark'], inspectionExecution=patch), ACTOR)
    assert error.value.status_code == 422
    assert reread(row) == before


def test_actual_date_cas_noop_factory_and_approved_lock(db):
    original = scheduled(db)
    row = save(original, '2026-11-06')
    assert save(row, '2026-11-06') == row
    with pytest.raises(HTTPException) as conflict:
        save(original, '2026-11-08')
    assert conflict.value.status_code == 409 and reread(row) == row
    with pytest.raises(HTTPException) as factory:
        sheet.save('huadeng', row['id'], dict(revision=row['revision'], result='PASS', remark='',
            inspectionExecution={'actualDate': '2026-11-08'}), ACTOR)
    assert factory.value.status_code == 404
    row = transition(submit(row))
    for review in (False, True):
        with pytest.raises(HTTPException):
            save(row, '', review=review)
    assert reread(row)['inspectionDate'] == '2026-11-06'


@pytest.mark.parametrize('actual,plan,expected,origin', [
    ('', '', '', None), ('', 'invalid', '', None),
    ('invalid', '2026-11-05', '2026-11-05', 'schedule'),
    ('2026-11-06', '', '2026-11-06', 'qc_manual'),
])
def test_no_clock_or_shipping_or_end_date_fallback(actual, plan, expected, origin):
    data = {'actualDate': actual, 'dateFrom': plan, 'dateTo': '2026-11-07',
        'shipDate': '2026-11-10', 'submittedAt': '2026-11-08', 'confirmedAt': '2026-11-09'}
    before = deepcopy(data)
    assert summary.resolve_inspection_date(data) == {'inspectionDate': expected, 'inspectionDateSource': origin}
    assert data == before


def test_unscheduled_historical_manual_row_can_stay_empty():
    base = sheet.base_fields({'customer': '历史手工记录', 'productNo': 'UNSCHEDULED'})
    row = sheet.sync('huaxing', [('legacy:123', base, '', '', [])])['items'][0]
    row = transition(submit(save(row, '')))
    assert row['inspectionDate'] == '' and row['inspectionDateSource'] is None
    assert row['actualDate'] == ''
    assert summary.listing('huaxing', {})['unknownDates'] == 1


def test_confirmation_rolls_back_projection_snapshot_and_event_together(db, monkeypatch):
    row = submit(save(scheduled(db), ''))
    history = sheet.audit('huaxing', row['id'])
    original = summary.upsert
    def fail_after_projection(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError('isolated interrupted confirmation')
    with monkeypatch.context() as patch:
        patch.setattr(summary, 'upsert', fail_after_projection)
        with pytest.raises(sqlite3.OperationalError):
            transition(row)
    assert reread(row) == row and sheet.audit('huaxing', row['id']) == history
    with sheet.store() as c:
        assert c.execute('SELECT approved_snapshot FROM entry_details WHERE entry_id=?', (row['id'],)).fetchone()[0] == ''
    assert summary.listing('huaxing', {})['total'] == 0
    assert transition(row)['inspectionDate'] == '2026-11-05'


@pytest.mark.parametrize('actual', ['', '2026-11-06'])
def test_old_confirmations_and_summary_payloads_unchanged_on_reads(db, monkeypatch, actual):
    pending = submit(save(scheduled(db), actual))
    # A pre-Phase 4.1 confirmation has no final-date marker.
    with monkeypatch.context() as patch:
        patch.setattr(summary, 'resolve_inspection_date', lambda _: {})
        old = transition(pending)
    with sheet.store() as c:
        snapshots = [tuple(r) for r in c.execute('SELECT submitted_snapshot,approved_snapshot FROM entry_details')]
        events = [tuple(r) for r in c.execute('SELECT * FROM changes')]
    with summary.store() as c:
        payloads = [tuple(r) for r in c.execute('SELECT * FROM records')]
    monkeypatch.setattr(summary, 'resolve_inspection_date', lambda _: pytest.fail('Historical date recalculation'))
    for _ in range(2):
        item = summary.listing('huaxing', {'dateBasis': 'actual'})['items'][0]
        assert item['inspectionDate'] == actual and 'inspectionDateSource' not in item
        summary.detail('huaxing', item['id'])
        assert 'inspectionDateSource' not in reread(old)
    with sheet.store() as c:
        assert [tuple(r) for r in c.execute('SELECT submitted_snapshot,approved_snapshot FROM entry_details')] == snapshots
        assert [tuple(r) for r in c.execute('SELECT * FROM changes')] == events
    with summary.store() as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM records')] == payloads


def test_confirmed_plan_is_frozen_revoke_reconfirm_and_retry(db):
    row = transition(submit(save(scheduled(db), '')))
    old = deepcopy(row)
    with wf.store(True) as c:
        src = deepcopy(row['sourceRecord'])
        src.update(dateFrom='2030-01-01', dateTo='2030-01-03', sourceRevision=2)
        c.execute('UPDATE manual_schedules SET payload=? WHERE id=?', (wf.dump(src), row['sourceId']))
    assert entries(db)[0]['dateFrom'] == '2026-11-05'
    assert summary.listing('huaxing', {})['items'][0]['inspectionDate'] == '2026-11-05'
    row = transition(row, 'revoke')
    assert 'inspectionDate' not in row and summary.listing('huaxing', {})['total'] == 0
    row = save(row, '2026-11-09', review=True)
    key = uuid4().hex
    confirmed = transition(row, key=key)
    assert transition(row, key=key) == confirmed
    assert confirmed['inspectionDate'] == '2026-11-09' and confirmed['inspectionDateSource'] == 'qc_manual'
    with sheet.store() as c:
        snapshots = [json.loads(r[0]) for r in c.execute("SELECT snapshot FROM changes WHERE action='confirm' ORDER BY id")]
    assert snapshots[0] == old and len(snapshots) == 2
    assert confirmed['dateFrom'] == '2026-11-05' and confirmed['dateTo'] == '2026-11-07'


@pytest.mark.parametrize('result', ['PASS', 'FAIL', 'PENDING', 'LG'])
def test_result_contract_unaffected(db, result):
    row = transition(submit(save(scheduled(db), '', result=result)))
    assert row['result'] == result and row['inspectionDateSource'] == 'schedule'


def test_final_date_listing_filter_sort_and_details_share_same_basis(db):
    for n, start, actual in [(1, '2026-11-05', '2026-12-02'), (2, '2026-12-10', '2026-11-06'),
                             (3, '2026-11-05', '')]:
        transition(submit(save(scheduled(db, n, start, start), actual)))
    result = summary.listing('huaxing', {'dateBasis': 'actual'})
    assert [r['inspectionDate'] for r in result['items']] == ['2026-11-05', '2026-11-06', '2026-12-02']
    filters = {'dateBasis': 'actual', 'year': '2026', 'month': '11'}
    selected = summary.listing('huaxing', filters)['items']
    assert len(selected) == 2
    assert summary.listing('huaxing', dict(filters, day='6'))['total'] == 1
    assert summary.listing('huadeng', filters)['total'] == 0
    detail = summary.detail('huaxing', selected[1]['id'])
    assert detail['scheduleDate'] == '2026-12-10' and detail['inspectionDate'] == '2026-11-06'


def test_formal_sales_source_stable_ids_batches_and_no_upstream_writes(db):
    line = ingest(db)
    line.data = {**line.data, 'planned_inspection_date': '2026-11-05',
                 'planned_inspection_date_to': '2026-11-07', 'inspection_agency': '行验'}
    db.commit()
    original = deepcopy(line.data)
    for batch in ['首验', '重验']:
        wf.create_tasks(db, 'huaxing', {'requestKey': uuid4().hex, 'items': [dict(
            sourceId=line.id, sourceRevision=line.revision, method='internal', batch=batch,
            plannedDate='2026-11-05', plannedQuantity='100')]}, ACTOR)
    rows = entries(db)
    assert len(rows) == 2 and rows[0]['id'] != rows[1]['id']
    for row in rows:
        actual = '2026-11-06' if row['batch'] == '首验' else ''
        confirmed = transition(submit(save(row, actual)))
        assert confirmed['sourceId'] == line.id
        assert confirmed['inspectionDate'] == (actual or '2026-11-05')
    db.refresh(line)
    assert line.data == original


def test_http_workbench_date_save_reread_confirm_and_permissions(db, monkeypatch):
    from app.api import qc_department as gateway
    from app.db import get_db
    from app.services import auth
    from app.services.auth import get_current_user
    monkeypatch.setattr(auth, 'add_auth_audit', lambda *a, **k: None)
    async def upstream(*args):
        return httpx.Response(200, json={'records': []})
    monkeypatch.setattr(gateway, 'upstream', upstream)
    app = FastAPI()
    app.include_router(gateway.router)
    current = [qc_user()]
    app.dependency_overrides[get_current_user] = lambda: current[0]
    app.dependency_overrides[get_db] = lambda: db
    row = scheduled(db)
    with TestClient(app) as client:
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url'] + 'api/'
        url = base + 'inspection-sheet/entries/' + row['id']
        body = dict(revision=row['revision'], result='PASS', remark='HTTP日期',
                    inspectionExecution={'actualDate': '2026-11-06'})
        response = client.post(url + '/save', json=body)
        assert response.status_code == 200, response.text
        saved = response.json()
        assert client.get(base + 'inspection-sheet/entries').json()['items'][0]['actualDate'] == '2026-11-06'
        body['revision'] = saved['revision']
        forbidden = dict(body, inspectionExecution={'reportNo': 'FORBIDDEN'})
        assert client.post(url + '/save', json=forbidden).status_code == 422
        current[0] = replace(current[0], permissions=frozenset({'qc_inspection:read'}), grants=())
        assert client.post(url + '/save', json=body).status_code == 403
        current[0] = qc_user()
        pending = client.post(url + '/submit', json={'revision': saved['revision']}).json()
        assert 'inspectionDate' not in pending
        response = client.post(base + 'inspection-sheet/review/confirm', json=dict(
            entries=[dict(id=row['id'], revision=pending['revision'])], requestKey=uuid4().hex))
        assert response.status_code == 200 and response.json()['succeeded'] == 1
        final = client.get(base + 'inspection-summary/records?dateBasis=actual').json()['items'][0]
        assert final['inspectionDate'] == '2026-11-06' and final['inspectionDateSource'] == 'qc_manual'
