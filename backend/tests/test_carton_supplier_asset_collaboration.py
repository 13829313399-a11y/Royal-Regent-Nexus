"""Supplier collaboration with internal originals; disposable SQLite only."""
from uuid import uuid4
import pytest
from sqlalchemy import select
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, grant_supplier_permissions
from test_carton_supplier_asset_status import internal_asset
from test_carton_asset_quick import BASE, F, enable
from test_carton_procurement_api import _order_payload, _submit_order


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('QC_DEPARTMENT_MANAGED', 'false')


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def target(row):
    return {key: row[key] for key in ('kind', 'id', 'sheet', 'row', 'fingerprint')}


def source_state(identifier):
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    from app.services import carton_asset_targets as targets
    with SessionLocal() as db:
        asset = db.get(CartonMarkAsset, identifier)
        return (targets.current(db, asset), sorted(row.order_id for row in asset.order_bindings), asset.owner_department)


def make_additional_order(client):
    payload = _order_payload()
    payload.update(contract_no='COLLAB-SECOND-TEST', customer_po='COLLAB-PO')
    order = _submit_order(client, ok(client.post('/api/carton-procurement/orders', json=payload), 201))
    response = client.post('/api/carton-procurement/orders/' + order['order_no'] + '/purchase-order-issues.xlsx',
        json={'factory_id':'huaxing', 'expected_revision':order['revision']})
    assert response.status_code == 200, response.text
    return order


def test_supplier_overlay_replaces_only_visible_projection_and_preserves_source(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        second = make_additional_order(client)
        asset = internal_asset(client, order)
        source = source_state(asset['id'])
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = ok(client.get(BASE + '/' + asset['id'], params={**F, 'supplier_view':True}))
        assert row['can_associate'] and row['can_share']
        candidates = ok(client.get(BASE + '/candidates', params={**F, 'owner_department':'supplier', 'asset_id':asset['id']}))['items']
        chosen = next(item for item in candidates if item['id'] == second['id'])
        url = BASE + '/' + asset['id'] + '/associations'
        request = dict(revision=row['revision'], request_id=uuid4().hex, targets=[])
        empty = ok(client.post(url, params=F, json=request))
        assert empty['targets'] == [] and source_state(asset['id']) == source
        assert ok(client.post(url, params=F, json=request))['revision'] == empty['revision']
        assert client.post(url, params=F, json={**request, 'targets':[target(chosen)]}).status_code == 409
        assert client.post(url, params=F, json={**request, 'request_id':uuid4().hex}).status_code == 409
        rebound = ok(client.post(url, params=F, json=dict(revision=empty['revision'], request_id=uuid4().hex, targets=[target(chosen)])))
        assert {item['id'] for item in rebound['targets']} == {second['id']}
        assert source_state(asset['id']) == source
        # The original order remains the authorization anchor despite an empty or different overlay.
        login_as(client, 'admin')
        current = ok(client.get(BASE + '/' + asset['id'], params=F))
        changed = client.put('/api/carton-mark/assets/' + asset['id'] + '/sharing', params=F,
            json={'revision':current['revision'], 'sharing_mode':'INTERNAL'})
        assert changed.status_code == 200, changed.text
        supplier_login(client)
        assert client.get(BASE + '/' + asset['id'], params={**F, 'supplier_view':True}).status_code == 404
        assert client.post(url, params=F, json=dict(revision=rebound['revision'], request_id=uuid4().hex, targets=[target(chosen)])).status_code in (403,404)
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id='COLLAB-OTHER', factory_id='huaxing', supplier_code='OTHER', supplier_name='其他供应商',
                status='ACTIVE', created_at='2026-10-19', updated_at='2026-10-19'))
            db.commit()
        current = ok(client.get(BASE + '/' + asset['id'], params=F))
        result = client.put('/api/carton-mark/assets/' + asset['id'] + '/sharing', params=F,
            json={'revision':current['revision'], 'sharing_mode':'SUPPLIER', 'supplier_id':'COLLAB-OTHER'})
        assert result.status_code == 422  # The original issued order belongs to a different supplier.
        foreign_asset = internal_asset(client, order, mode='INTERNAL')
        result = client.put('/api/carton-mark/assets/' + foreign_asset['id'] + '/sharing', params=F,
            json={'revision':foreign_asset['revision'], 'sharing_mode':'SUPPLIER', 'supplier_id':'COLLAB-OTHER'})
        assert result.status_code == 200, result.text
        supplier_login(client)
        assert client.get(BASE + '/' + foreign_asset['id'], params={**F,'supplier_view':True}).status_code == 404


def test_supplier_shares_internal_original_cross_factory_then_revokes(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        ok(client.post('/api/carton-procurement/customers', json=dict(factory_id='huakang-a',customer_code='DICKIE',customer_name='Dickie')), 201)
        payload = _order_payload()
        payload.update(factory_id='huakang-a', contract_no='COLLAB-FACTORY-A')
        other = ok(client.post('/api/carton-procurement/orders', json=payload), 201)
        other = ok(client.post('/api/carton-procurement/orders/' + other['order_no'] + '/submit-supplier',
            json={'factory_id':'huakang-a', 'expected_revision':other['revision']}))
        issue = client.post('/api/carton-procurement/orders/' + other['order_no'] + '/purchase-order-issues.xlsx',
            json={'factory_id':'huakang-a', 'expected_revision':other['revision']})
        assert issue.status_code == 200, issue.text
        asset = internal_asset(client, order)
        original = source_state(asset['id'])
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        current = ok(client.get(BASE + '/' + asset['id'], params={**F, 'supplier_view':True}))
        assert current['can_share'] and current['required_shared_factory_ids'] == ['huaxing']
        body = dict(revision=current['revision'], request_id=uuid4().hex, shared_factory_ids=['huakang-a'])
        url = BASE + '/' + asset['id'] + '/sharing'
        result = ok(client.post(url, params=F, json=body))
        assert set(result['shared_factory_ids']) == {'huaxing','huakang-a'}
        assert ok(client.post(url, params=F, json=body))['revision'] == result['revision']
        assert client.post(url, params=F, json={**body,'request_id':uuid4().hex}).status_code == 409
        login_as(client, 'admin')
        projected = ok(client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}))
        assert projected['id'] == asset['id'] and projected['factory_id'] == 'huaxing'
        assert projected['owner_department'] == original[2] and projected['owner_supplier_id'] is None
        assert client.get(BASE + '/' + asset['id'] + '/document', params={'factory_id':'huakang-a'}).content
        assert client.get('/api/carton-mark/assets/' + asset['id'] + '/document', params={'factory_id':'huakang-a'}).status_code == 404
        assert ok(client.get(BASE + '/' + asset['id'], params=F))['id'] == asset['id']
        supplier_login(client)
        revoked = ok(client.post(url, params=F, json=dict(revision=result['revision'],request_id=uuid4().hex,shared_factory_ids=[])))
        assert revoked['shared_factory_ids'] == ['huaxing'] and source_state(asset['id']) == original
        login_as(client, 'admin')
        assert client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}).status_code == 404
        assert client.get(BASE + '/' + asset['id'] + '/document', params={'factory_id':'huakang-a'}).status_code == 404
        assert ok(client.get(BASE + '/' + asset['id'], params=F))['id'] == asset['id']
        supplier_login(client)
        again = ok(client.post(url, params=F, json=dict(revision=revoked['revision'],request_id=uuid4().hex,shared_factory_ids=['huakang-a'])))
        from test_carton_supplier_portal import revoke_supplier_permission, restore_supplier_permission
        revoke_supplier_permission('carton_supplier:edit')
        assert client.post(url, params=F, json=dict(revision=again['revision'],request_id=uuid4().hex,shared_factory_ids=[])).status_code == 403
        assert client.post(BASE + '/' + asset['id'] + '/associations', params=F,
            json=dict(revision=again['revision'],request_id=uuid4().hex,targets=[])).status_code == 403
        login_as(client, 'admin')
        assert client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}).status_code == 404
        restore_supplier_permission('carton_supplier:edit')
        assert ok(client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}))['id'] == asset['id']
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'carton_asset:manage'))
            db.add(AuthUserPermissionOverride(id='collaboration-deny', user_id='supplier-test', permission_id=permission.id,
                effect='deny', factory_id='huaxing', department='supplier', status='active', reason='测试明确撤权'))
            db.commit()
        assert client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}).status_code == 404
        supplier_login(client)
        assert client.post(url, params=F, json=dict(revision=again['revision'],request_id=uuid4().hex,shared_factory_ids=[])).status_code == 403
        login_as(client, 'admin')
        with SessionLocal() as db:
            db.get(AuthUserPermissionOverride, 'collaboration-deny').status = 'revoked'
            db.commit()
        assert ok(client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}))['id'] == asset['id']
        current = ok(client.get(BASE + '/' + asset['id'], params=F))
        assert current['revision'] == again['revision']
        changed = client.put('/api/carton-mark/assets/' + asset['id'] + '/sharing', params=F,
            json={'revision':current['revision'], 'sharing_mode':'INTERNAL'})
        assert changed.status_code == 200, changed.text
        assert client.get(BASE + '/' + asset['id'], params={'factory_id':'huakang-a'}).status_code == 404
        assert client.get(BASE + '/' + asset['id'] + '/document', params={'factory_id':'huakang-a'}).status_code == 404
        assert ok(client.get(BASE + '/' + asset['id'], params=F))['id'] == asset['id']


def test_supplier_candidates_cannot_cross_customer_or_use_unissued_order(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        asset = internal_asset(client, order)
        ok(client.post('/api/carton-procurement/customers', json=dict(factory_id='huaxing', customer_code='OTHER', customer_name='其他合成客户')), 201)
        payload = _order_payload(); payload.update(customer_code='OTHER', customer_name='其他合成客户', contract_no='OTHER-CUSTOMER-TEST')
        foreign = _submit_order(client, ok(client.post('/api/carton-procurement/orders', json=payload), 201))
        issued = client.post('/api/carton-procurement/orders/' + foreign['order_no'] + '/purchase-order-issues.xlsx',
            json={'factory_id':'huaxing', 'expected_revision':foreign['revision']})
        assert issued.status_code == 200, issued.text
        payload = _order_payload(); payload['contract_no'] = 'NOT-ISSUED-TEST'
        draft = ok(client.post('/api/carton-procurement/orders', json=payload), 201)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = ok(client.get(BASE + '/' + asset['id'], params={**F,'supplier_view':True}))
        unrestricted = ok(client.get(BASE + '/candidates', params={**F, 'owner_department':'supplier'}))['items']
        foreign_target = next(item for item in unrestricted if item['id'] == foreign['id'])
        scoped = ok(client.get(BASE + '/candidates', params={**F,'owner_department':'supplier','asset_id':asset['id']}))['items']
        assert foreign['id'] not in {item['id'] for item in scoped}
        assert draft['id'] not in {item['id'] for item in unrestricted}
        url = BASE + '/' + asset['id'] + '/associations'
        assert client.post(url, params=F, json=dict(revision=row['revision'],request_id=uuid4().hex,targets=[target(foreign_target)])).status_code == 404
        fake = dict(kind='REGULAR',id=draft['id'],sheet='',row=0,fingerprint='0'*64)
        assert client.post(url, params=F, json=dict(revision=row['revision'],request_id=uuid4().hex,targets=[fake])).status_code == 404


def test_supplier_empty_overlay_does_not_remove_business_schedule(monkeypatch):
    from test_carton_asset_quick import upload, schedule
    from test_carton_item_schedule import source_row
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        batch = schedule(client, [source_row()])
        candidates = ok(client.get(BASE + '/candidates', params={**F,'owner_department':'sales-business',
            'target_scope':'PENDING_SCHEDULE'}))['items']
        entry = next(item for item in candidates if item['contract_no'] == '53135')
        asset = ok(upload(client,contract_number='53135',target_scope='PENDING_SCHEDULE'))
        payload = {**_order_payload(), 'contract_no':'53135', 'item_no':'0040220-1', 'customer_po':'0989551378',
            'product_order_quantity':360, 'customer_due_date':'2026-09-17',
            'schedule_source':{'batch_id':batch['id'],'source_sheet':entry['sheet'],'source_row':entry['row']}}
        order = _submit_order(client, ok(client.post('/api/carton-procurement/orders', json=payload), 201))
        original = source_state(asset['id'])
        assert any(row['kind'] == 'SCHEDULE' for row in original[0])
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        supplier_login(client)
        visible = ok(client.get(BASE + '/' + asset['id'], params={**F,'supplier_view':True}))
        assert visible['can_associate'] and order['id'] in {row['id'] for row in visible['targets']}
        result = ok(client.post(BASE + '/' + asset['id'] + '/associations', params=F,
            json=dict(revision=visible['revision'], request_id=uuid4().hex, targets=[])))
        assert result['targets'] == [] and source_state(asset['id']) == original
        login_as(client, 'admin')
        projected = ok(client.get(BASE + '/' + asset['id'], params=F))
        assert any(row['kind'] == 'SCHEDULE' for row in projected['targets'])
