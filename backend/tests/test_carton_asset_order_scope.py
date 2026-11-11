"""Order-only picking retains upstream schedule links on disposable SQLite."""
from uuid import uuid4

import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_asset_quick import BASE, F, enable, ok, schedule, upload
from test_carton_item_schedule import source_row
from test_carton_supplier_portal import setup_portal, supplier_login, grant_supplier_permissions


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('QC_DEPARTMENT_MANAGED', 'false')


def ref(row):
    return {key: row[key] for key in ('kind', 'id', 'sheet', 'row', 'fingerprint')}


def test_order_scope_excludes_schedule_and_preserves_existing_schedule_links(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        schedule(client, [source_row()])
        def choices(scope, department='pmc-warehouse'):
            return ok(client.get(BASE + '/candidates', params={**F, 'owner_department': department,
                'target_scope': scope}))['items']
        business = choices('PENDING_SCHEDULE', 'sales-business')
        schedule_target = next(row for row in business if row['kind'] == 'SCHEDULE')
        asset = ok(upload(client, association='MANUAL', targets=[ref(schedule_target)],
            target_scope='PENDING_SCHEDULE', sharing_mode='INTERNAL'))
        original = client.get(BASE + '/' + asset['id'] + '/document', params=F).content
        all_choices = choices('ALL')
        warehouse = choices('ORDERS')
        assert any(row['kind'] == 'SCHEDULE' for row in all_choices)
        assert all(row['kind'] != 'SCHEDULE' for row in warehouse)
        key = lambda row: (row['kind'], row['id'], row['sheet'], row['row'])
        assert {key(row) for row in warehouse} == {key(row) for row in all_choices if row['kind'] != 'SCHEDULE'}
        regular = next(row for row in warehouse if row['kind'] == 'REGULAR' and row['id'] == order['id'])
        def change(targets):
            return client.post(BASE + '/' + asset['id'] + '/associations', params=F, json=dict(
                revision=asset['revision'], request_id=uuid4().hex, target_scope='ORDERS', targets=targets))
        assert change([ref(schedule_target)]).status_code == 404
        asset = ok(change([ref(regular)]))
        assert {(row['kind'], row['id']) for row in asset['targets']} == {
            ('SCHEDULE', schedule_target['id']), ('REGULAR', order['id'])}
        asset = ok(change([]))
        assert [(row['kind'], row['id'], row['sheet'], row['row']) for row in asset['targets']] == [key(schedule_target)]
        assert client.get(BASE + '/' + asset['id'] + '/document', params=F).content == original
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        supplier_all = choices('ALL', 'supplier')
        supplier_orders = choices('ORDERS', 'supplier')
        assert any(row['kind'] == 'REGULAR' and row['id'] == order['id'] for row in supplier_orders)
        assert all(row['kind'] != 'SCHEDULE' for row in supplier_orders)
        assert {key(row) for row in supplier_orders} == {key(row) for row in supplier_all if row['kind'] != 'SCHEDULE'}


def test_special_candidates_show_original_order_time_and_number_without_changing_fingerprint(monkeypatch):
    from app.services.carton_asset_targets import digest
    with make_client(monkeypatch) as client:
        regular = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_special_requests import SpecialRequest
        with SessionLocal() as db:
            for identifier, kind in [('synthetic-sample', 'SAMPLE'), ('synthetic-misc', 'WORKSHOP_MISC')]:
                db.add(SpecialRequest(id=identifier, factory_id='huaxing', supplier_id=regular['supplier_id'],
                    request_no='ORDER-' + identifier, kind=kind, title='synthetic', requester_name='synthetic',
                    workshop_id='', customer_code='DICKIE', customer_name='Dickie', purpose='isolated regression',
                    required_date='2026-10-20', status='SENT', revision=2, current_version_id='version-' + identifier,
                    created_by='user-admin', created_at='2026-10-01T09:12:13', updated_at='2026-10-21T18:45:00'))
            db.commit()
        rows = ok(client.get(BASE + '/candidates', params={**F, 'owner_department': 'pmc-warehouse', 'target_scope': 'ORDERS'}))['items']
        selected = [next(row for row in rows if row['id'] == identifier) for identifier in ('synthetic-sample', 'synthetic-misc')]
        assert [row['kind'] for row in selected] == ['SAMPLE', 'MISC']
        for row in selected:
            assert row['order_no'] == 'ORDER-' + row['id']
            assert row['ordered_at'] == '2026-10-01T09:12:13'
            # This is the exact pre-extension fingerprint input; display metadata
            # cannot make an already loaded target stale.
            prior = {key: value for key, value in row.items() if key not in {'fingerprint', 'order_no', 'ordered_at'}}
            assert row['fingerprint'] == digest(prior)
        asset = ok(upload(client, association='NONE', sharing_mode='INTERNAL'))
        associated = ok(client.post(BASE + '/' + asset['id'] + '/associations', params=F,
            json=dict(revision=asset['revision'], request_id=uuid4().hex, target_scope='ORDERS',
                targets=[ref(row) for row in selected])))
        assert {(row['kind'], row['id']) for row in associated['targets']} == {
            ('SAMPLE', 'synthetic-sample'), ('MISC', 'synthetic-misc')}
