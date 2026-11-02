"""Actual fixed-position grants must not turn into other departments' assets."""
from dataclasses import replace
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select


def position_user(role_id):
    from app.services.auth import AuthContext, AuthGrantContext
    from app.services.system_positions import get_system_position
    role = get_system_position(role_id)
    grant = AuthGrantContext(role_id=role.role_id, role_code=role.role_id, role_name=role.name,
        factory_id='huaxing', department=role.department, permissions=frozenset(role.permission_codes),
        scope_mode=role.scope_mode, unrestricted_department=True,
        read_permissions=frozenset(x for x in role.permission_codes if x.endswith(':read')))
    return AuthContext(id='synthetic-' + role_id, username=role_id, display_name=role.name,
        roles=(role.name,), role_codes=(role.role_id,), permissions=grant.permissions,
        factory_scopes=('huaxing',), department_scopes=(role.department,), grants=(grant,))


@pytest.mark.parametrize('role_id', [
    'position_sales_business', 'position_sales_supervisor', 'position_sales_manager',
    'position_warehouse_keeper', 'position_warehouse_supervisor', 'position_warehouse_manager',
    'position_carton_warehouse_keeper', 'position_carton_supervisor', 'position_carton_manager',
])
@pytest.mark.parametrize('action', ['read', 'manage', 'confirm'])
def test_fixed_position_asset_authority_stays_in_bound_department(role_id, action):
    from app.services.carton_asset_access import allowed, DEPARTMENTS
    user = position_user(role_id)
    for department in DEPARTMENTS:
        assert allowed(user, 'huaxing', department, action) == (department == user.grants[0].department)
    # Operating across factories is the original manager contract, not a new
    # grant to a salesperson or own-factory warehouse keeper.
    if action != 'read':
        cross_factory = role_id in {'position_warehouse_manager', 'position_carton_manager'}
        assert allowed(user, 'huakang-a', user.grants[0].department, action) == cross_factory
        assert not allowed(user, 'huakang-a', 'sales-business' if cross_factory else 'pmc-warehouse', action)


def test_actual_sales_position_cannot_manage_warehouse_internal_evidence(monkeypatch):
    from app.services.carton_asset_access import ensure, visible, owner
    monkeypatch.setenv('CARTON_ASSET_V1_ENABLED', 'true')
    monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED', 'true')
    user = position_user('position_sales_business')
    asset = SimpleNamespace(recognition_source='manual_orders', is_archived=False,
        owner_department='pmc-warehouse', owner_supplier_id=None, asset_purpose='EVIDENCE',
        kind='text', factory_id='huaxing', created_by='other-user')
    assert not visible(None, user, asset, library=True)
    for values in ({}, {'write': True}, {'write': True, 'confirm': True}):
        with pytest.raises(HTTPException) as error:
            ensure(None, user, asset, **values)
        assert error.value.status_code == 403
    assert owner(None, user, 'huaxing') == ('sales-business', None)
    with pytest.raises(HTTPException):
        owner(None, user, 'huaxing', 'pmc-warehouse')


def test_explicit_department_grants_denies_expiry_and_pinned_permissions(monkeypatch):
    from app.services.auth import AuthOverrideContext
    from app.services.carton_asset_access import allowed, owner
    sales = position_user('position_sales_business')
    warehouse = position_user('position_warehouse_keeper')
    multi = replace(sales, grants=sales.grants + warehouse.grants)
    assert allowed(multi, 'huaxing', 'pmc-warehouse', 'manage')
    assert allowed(multi, 'huaxing', 'sales-business', 'manage')
    assert not allowed(multi, 'huaxing', 'carton', 'manage')
    with pytest.raises(HTTPException) as error:
        owner(None, multi, 'huaxing')
    assert error.value.status_code == 422
    assert owner(None, multi, 'huaxing', 'pmc-warehouse') == ('pmc-warehouse', None)
    denied = replace(multi, overrides=(AuthOverrideContext(id='deny', permission_code='carton_asset:manage',
        effect='deny', factory_id='huaxing', department='pmc-warehouse'),))
    assert not allowed(denied, 'huaxing', 'pmc-warehouse', 'manage')
    assert allowed(denied, 'huaxing', 'sales-business', 'manage')
    expired = replace(sales, grants=(replace(sales.grants[0], valid_until='2000-01-01 00:00:00'),))
    assert not allowed(expired, 'huaxing', 'sales-business')
    pinned = replace(sales, grants=(replace(sales.grants[0], permissions=frozenset()),))
    assert not allowed(pinned, 'huaxing', 'sales-business', 'manage')
    # Explicit supplier mapping must still not establish an internal identity.
    supplier = replace(sales, grants=(), overrides=tuple(AuthOverrideContext(id=action,
        permission_code='carton_asset:' + action, effect='allow', factory_id='*', department='*')
        for action in ['read', 'manage']))
    assert allowed(supplier, 'huaxing', 'supplier', 'manage')
    assert not allowed(supplier, 'huaxing', 'pmc-warehouse', 'manage')


def test_fixed_sales_http_old_and_quick_routes_and_authorized_warehouse_admin(monkeypatch):
    from test_molding_sample_api import make_client, login_as, TEST_USER_SPECS, grant_permission_override
    from test_carton_asset_quick import upload, ok, enable, action, BASE, F
    monkeypatch.setitem(TEST_USER_SPECS, 'asset_sales', ('test-asset-sales', '资料业务测试',
        'position_sales_business', 'huaxing', 'sales-business'))
    monkeypatch.setitem(TEST_USER_SPECS, 'asset_warehouse', ('test-asset-warehouse', '资料仓库测试',
        'position_warehouse_keeper', 'huaxing', 'pmc-warehouse'))
    monkeypatch.setitem(TEST_USER_SPECS, 'asset_department_admin', ('test-asset-dept-admin', '部门权限管理员测试',
        'department_permission_admin', 'huaxing', 'pmc-warehouse'))
    with make_client(monkeypatch) as client:
        login_as(client, 'admin'); enable(monkeypatch)
        warehouse = ok(upload(client, owner_department='pmc-warehouse', text='warehouse ordinary'))
        evidence = ok(upload(client, owner_department='pmc-warehouse', purpose='EVIDENCE', text='warehouse evidence'))
        business = ok(upload(client, text='sales ordinary'))
        from test_carton_mark_asset_images import photo_bytes
        photos = [ok(client.post(BASE, params=F, data={'metadata': json.dumps(dict(
            request_id=uuid4().hex, owner_department='pmc-warehouse'))},
            files={'file': (name + '.png', photo_bytes(color=color), 'image/png')}))
            for name, color in [('warehouse-one', 'red'), ('warehouse-two', 'blue')]]
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonAuditEvent
        def originals():
            with SessionLocal() as db:
                return ([(x.id, x.revision, bytes(x.content), x.owner_department, x.asset_purpose, x.is_archived)
                    for x in db.scalars(select(CartonMarkAsset).order_by(CartonMarkAsset.id))],
                    [(x.id, x.detail_json) for x in db.scalars(select(CartonAuditEvent).where(
                        CartonAuditEvent.entity_type == 'carton_mark_asset').order_by(CartonAuditEvent.sequence))])
        before = originals()
        login = login_as(client, 'asset_sales')
        assert any(x['role_id'] == 'position_sales_business' and x['unrestricted_department'] for x in login['grants'])
        # Before the fix this real account could create a warehouse-owned file.
        assert upload(client, owner_department='pmc-warehouse').status_code == 403
        assert client.get(BASE, params={**F, 'owner_department': 'pmc-warehouse'}).status_code == 403
        assert {x['id'] for x in ok(client.get(BASE, params=F))['items']} == {business['id'], warehouse['id'], *(x['id'] for x in photos)}
        assert {x['id'] for x in ok(client.get('/api/carton-mark/assets', params=F))} == {business['id'], warehouse['id'], *(x['id'] for x in photos)}
        old_upload = ok(client.post('/api/carton-mark/assets/batch', data={**F, 'options_json': json.dumps([
            dict(owner_department='pmc-warehouse', status='PENDING')])},
            files=[('files', ('legacy.png', photo_bytes(), 'image/png'))]))[0]
        assert old_upload['status'] == 'failed' and old_upload['asset'] is None
        assert client.post('/api/carton-mark/assets/photo-groups', params=F,
            json=dict(assets=[dict(id=x['id'], revision=x['revision']) for x in photos])).status_code == 403
        for asset in [evidence]:
            identifier, revision = asset['id'], asset['revision']
            old = '/api/carton-mark/assets/' + identifier
            for url in [BASE + '/' + identifier, BASE + '/' + identifier + '/document',
                        old + '/document', old + '/classification-history']:
                assert client.get(url, params=F).status_code == 403, url
            for status in ['DRAFT', 'READY']:
                assert action(client, asset, status).status_code == 403
                assert client.put(old + '/classification', params=F, json=dict(revision=revision, status=status)).status_code == 403
            assert client.post(BASE + '/' + identifier + '/associations', params=F,
                json=dict(revision=revision, request_id=uuid4().hex, target=None)).status_code == 403
            assert client.put(old + '/associations', params=F,
                json=dict(revision=revision, request_id=uuid4().hex, targets=[])).status_code == 403
            assert client.put(old + '/binding', params=F, json=dict(revision=revision, contract_number='')).status_code == 403
            assert client.put(old + '/sharing', params=F, json=dict(revision=revision, sharing_mode='INTERNAL')).status_code == 403
            assert client.delete(old, params={**F, 'revision': revision}).status_code == 403
        assert client.delete('/api/carton-mark/assets/'+warehouse['id'], params={**F,'revision':warehouse['revision']}).status_code == 403
        assert originals() == before
        warehouse = ok(action(client, warehouse, 'READY'))
        assert client.get(BASE + '/' + warehouse['id'], params={'factory_id': 'huakang-a'}).status_code == 404
        own = ok(upload(client, owner_department=None, text='sales own upload'))
        assert own['owner_department'] == 'sales-business'
        assert ok(action(client, own, 'READY'))['workflow']['status'] == 'READY'
        login_as(client, 'asset_warehouse')
        assert client.get(BASE + '/' + business['id'], params=F).status_code == 200
        assert client.get('/api/carton-mark/assets/' + warehouse['id'] + '/document', params=F).content == b'warehouse ordinary'
        warehouse = ok(action(client, warehouse, 'READY'))
        warehouse = ok(client.put('/api/carton-mark/assets/' + warehouse['id'] + '/classification', params=F,
            json=dict(revision=warehouse['revision'], status='PENDING')))
        assert warehouse['workflow']['status'] == 'PENDING'
        assert ok(upload(client, owner_department=None))['owner_department'] == 'pmc-warehouse'
        login_as(client, 'asset_department_admin')
        # IAM administration alone does not implicitly grant file access.
        assert client.get(BASE + '/' + warehouse['id'], params=F).status_code == 403
        for code in ['read', 'manage', 'confirm']:
            grant_permission_override('asset_department_admin', 'carton_asset:' + code,
                factory_id='huaxing', department='pmc-warehouse')
        login_as(client, 'asset_department_admin')
        assert client.get(BASE + '/' + warehouse['id'], params=F).status_code == 200
        assert client.get(BASE + '/' + business['id'], params=F).status_code == 200
        assert ok(action(client, warehouse, 'READY'))['workflow']['status'] == 'READY'
        assert ok(upload(client, owner_department=None))['owner_department'] == 'pmc-warehouse'
