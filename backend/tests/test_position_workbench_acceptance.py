"""Additional acceptance on synthetic databases; no live-data access."""
import importlib
import importlib.util
import json
import time
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select, func, event
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_position_reviews import client, employee, submit, plan, commit
from test_identity_changes import draft, commit as identity_commit
from test_iam_api import login, create_user


def test_business_write_revoked_in_existing_employee_session(client):
    employee(client)
    cookie = client.cookies.get('rr_session')
    def business_request():
        return client.post('/api/injection', json={'order': {'id': 'position-qa-' + uuid4().hex,
            'factory_id': 'huakang-a', 'product_name': '隔离权限验收', 'date': '2026-10-13'}, 'items': []})
    before = business_request()
    assert before.status_code == 201, before.text
    review = client.post('/api/auth/me/position-reviews', json={'declaration': {'org_unit_id':'huakang-a','department_code':'pmc-warehouse','position':'仓管员','note':''}}).json()['review']
    login(client, 'admin')
    key, _, preview = plan(client, review, role='position_warehouse_keeper')
    assert any(t['permission_code'] == 'molding_sample:create' for t in preview['permission_diffs']['removed'])
    assert commit(client, key, preview)[0].status_code == 200
    client.cookies.clear()
    client.cookies.set('rr_session', cookie)
    assert client.get('/api/auth/me/position-profile').json()['official_position']['position'] == '仓管员'
    after = business_request()
    assert after.status_code == 403, after.text


def test_freeze_leave_and_actor_loss_block_workbench_commit(client):
    uid = employee(client)
    review = submit(client)
    login(client, 'admin')
    key, _, preview = plan(client, review)
    assert identity_commit(client, draft(client, uid, 'freeze')).status_code == 200
    assert commit(client, key, preview)[0].status_code == 409
    assert identity_commit(client, draft(client, uid, 'unfreeze')).status_code == 200
    key, _, preview = plan(client, review)
    assert identity_commit(client, draft(client, uid, 'leave')).status_code == 200
    assert commit(client, key, preview)[0].status_code == 409
    dbm = importlib.import_module('app.db')
    models = importlib.import_module('app.models.position_review')
    with dbm.SessionLocal() as db:
        assert db.get(models.PositionReview, review['id']).status == 'invalidated'
    # A second administrator loses authority after preview, while its session remains.
    employee(client, 'position-second')
    second = submit(client)
    login(client, 'admin')
    actor = create_user('position-reviewer', 'admin', '*', '*')
    login(client, 'position-reviewer')
    key, _, preview = plan(client, second)
    auth = importlib.import_module('app.models.auth')
    with dbm.SessionLocal() as db:
        for binding in db.scalars(select(auth.AuthUserRole).where(auth.AuthUserRole.user_id == actor)):
            db.delete(binding)
        db.commit()
    rejected = commit(client, key, preview)[0]
    assert rejected.status_code == 403, rejected.text


def test_position_downgrade_refuses_history_and_write_gate_preserves_rows(client, monkeypatch):
    employee(client)
    row = submit(client)
    login(client, 'admin')
    config = importlib.import_module('app.core.config')
    monkeypatch.setattr(config.settings, 'iam_position_workbench_enabled', False)
    detail = client.get('/api/iam/position-workbench/items/position:' + row['id'])
    assert detail.status_code == 200 and 'preview' not in detail.json()['available_actions']
    login(client, 'position-clerk')
    profile = client.get('/api/auth/me/position-profile').json()
    assert profile['open_review']['id'] == row['id'] and not profile['can_submit']
    rejected = client.post('/api/auth/me/position-reviews', json={'declaration': row['declaration']})
    assert rejected.status_code == 403
    dbm = importlib.import_module('app.db')
    reviews = importlib.import_module('app.models.position_review')
    path = Path(dbm.__file__).parents[1] / 'alembic/versions/20261013_0160_position_reviews.py'
    spec = importlib.util.spec_from_file_location('position_migration_qa', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with dbm.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        with pytest.raises(RuntimeError, match='history exists'):
            migration.downgrade()
    with dbm.SessionLocal() as db:
        assert db.get(reviews.PositionReview, row['id']).status == 'pending'
        assert db.scalar(select(func.count()).select_from(reviews.PositionReviewEvent)) == 1


def test_queue_has_bounded_queries_and_record_local_timing(client):
    dbm = importlib.import_module('app.db')
    reviews = importlib.import_module('app.models.position_review')
    records = []
    for index in range(50):
        uid = create_user(f'queue-perf-{index:02d}', 'position_engineering_engineer', 'huakang-a', 'engineering')
        records.append(reviews.PositionReview(id=uuid4().hex, user_id=uid, employment_epoch=1, origin='employee',
            initiator_user_id=uid, status='pending', revision=1,
            declared_snapshot_json=json.dumps({'org_unit_id':'huakang-a','department_code':'engineering','position':'验收岗位','note':''}),
            base_official_snapshot_json='{}', base_identity_version=0, base_authorization_version=0,
            created_at='2026-10-13T00:00:00Z', updated_at='2026-10-13T00:00:00Z', last_submitted_at='2026-10-13T00:00:00Z'))
    with dbm.SessionLocal() as db:
        db.add_all(records)
        db.commit()
    timings = []
    counts = []
    for size in (1, 20, 50):
        count = [0]
        def count_query(*args): count[0] += 1
        event.listen(dbm.engine, 'before_cursor_execute', count_query)
        try:
            started = time.perf_counter()
            response = client.get('/api/iam/position-workbench/queue', params={'page_size':size})
            timings.append(round((time.perf_counter()-started)*1000, 2))
            counts.append(count[0])
        finally:
            event.remove(dbm.engine, 'before_cursor_execute', count_query)
        assert response.status_code == 200, response.text
        assert response.json()['total'] == 50
        assert len(response.json()['items']) == size
    assert max(counts) - min(counts) <= 2, counts
    print('QUEUE_SYNTHETIC_50', json.dumps({'page_sizes':[1,20,50], 'ms':timings, 'sql_counts':counts}))
    pages = [client.get('/api/iam/position-workbench/queue', params={'page_size':20, 'page':page}).json() for page in (1,2,3)]
    keys = [item['item_key'] for page in pages for item in page['items']]
    assert len(keys) == len(set(keys)) == 50
    samples = []
    for _ in range(10):
        started = time.perf_counter()
        assert client.get('/api/iam/position-workbench/queue', params={'page_size':20}).status_code == 200
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    print('QUEUE_WARM_10', json.dumps({'p50_ms':round((ordered[4]+ordered[5])/2,2), 'p95_nearest_rank_ms':round(ordered[9],2)}))


def test_group_scope_self_escalation_and_changed_idempotency_payload(client):
    employee(client)
    review = submit(client, '总经理')
    login(client, 'admin')
    key, body, preview = plan(client, review)
    functional = {**body, 'confirmed_profile': {'org_unit_id':'group-management','department_code':'management','position':'总务'}}
    rejected = client.post(f'/api/iam/position-workbench/items/{key}/preview', json=functional)
    assert rejected.status_code == 422 and rejected.json()['code'] == 'INVALID_SCOPE', rejected.text
    response, command = commit(client, key, preview)
    assert response.status_code == 200, response.text
    mismatch = client.post(f'/api/iam/position-workbench/items/{key}/commit', json={**command, 'risk_acknowledged':False})
    assert mismatch.json()['code'] == 'IDEMPOTENCY_PAYLOAD_MISMATCH', mismatch.text
    # Self-targeting may not turn a readable catalog into a grant capability.
    own = client.post('/api/iam/position-workbench/admin-adjustments', json={'target_user_id':'user-admin',
        'proposed_profile': {'org_unit_id':'huakang-a','department_code':'engineering','position':'自增权尝试'}, 'reason':'隔离验收'})
    assert own.status_code == 200, own.text
    own_row = own.json()['review']
    own_body = {**body, 'expected_source_revision':'position:1', 'confirmed_profile':{k:v for k,v in own_row['declaration'].items() if k != 'note'}}
    blocked = client.post('/api/iam/position-workbench/items/' + own.json()['item_key'] + '/preview', json=own_body)
    assert blocked.status_code == 403 and blocked.json()['code'] == 'SELF_ESCALATION', blocked.text
