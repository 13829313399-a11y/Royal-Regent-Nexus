import json
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, revoke_supplier_permission, grant_supplier_permissions, PASSWORD
from test_carton_mark_asset_images import photo_bytes
from test_carton_special_requests import command, create_body, ok, BASE as SPECIAL, SUP as SPECIAL_SUP

BASE = '/api/carton-mark/assets'
SUP = '/api/carton-supplier/carton-mark'
SCOPE = {'factory_id': 'huaxing'}


def upload(client, mode='SUPPLIER', supplier_id=''):
    response = client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([
        {'status': 'PENDING', 'sharing_mode': mode, 'supplier_id': supplier_id}])},
        files=[('files', ('camera.png', photo_bytes(), 'image/png'))])
    assert response.status_code == 200, response.text
    return response.json()[0]


def test_unbound_shared_visibility_internal_revocation_and_confirmed_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        asset = upload(client)['asset']
        assert asset['sharing_mode'] == 'SUPPLIER' and asset['orders'] == []
        private = upload(client, 'INTERNAL')['asset']
        supplier_login(client)
        visible = ok(client.get(SUP + '/assets', params=SCOPE))
        assert [x['id'] for x in visible] == [asset['id']]
        assert client.get(SUP + f"/assets/{private['id']}/document", params=SCOPE).status_code == 404
        assert client.get(SUP + f"/assets/{asset['id']}/document", params=SCOPE).content == photo_bytes()
        proposed = ok(client.put(SUP + f"/assets/{asset['id']}/binding", params=SCOPE,
            json={'revision': asset['revision'], 'order_ids': [order['id']]}))
        assert proposed['orders'] == [] and len(proposed['pending_bindings']) == 1
        login_as(client, 'admin')
        confirmed = ok(client.post(BASE + f"/{asset['id']}/bindings/{proposed['pending_bindings'][0]['id']}/confirm",
            params=SCOPE, json={'revision': proposed['revision']}))
        assert confirmed['orders'][0]['id'] == order['id'] and not confirmed['pending_bindings']
        private_now = ok(client.put(BASE + f"/{asset['id']}/sharing", params=SCOPE,
            json={'revision': confirmed['revision'], 'sharing_mode': 'INTERNAL'}))
        supplier_login(client)
        assert ok(client.get(SUP + '/assets', params=SCOPE)) == []
        assert client.get(SUP + f"/assets/{asset['id']}/document", params=SCOPE).status_code == 404
        assert client.put(SUP + f"/assets/{asset['id']}/binding", params=SCOPE,
            json={'revision': private_now['revision'], 'order_ids': [order['id']]}).status_code == 404


def test_supplier_unbound_upload_remains_pending_and_permission_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        response = client.post(SUP + '/assets/upload', data={**SCOPE, 'shared_unbound': 'true'},
            files=[('files', ('camera.png', photo_bytes(), 'image/png'))])
        assert response.status_code == 201, response.text
        asset = response.json()[0]['asset']
        assert asset['orders'] == [] and asset['workflow']['status'] == 'PENDING'
        assert client.get(SUP + f"/assets/{asset['id']}/document", params={'factory_id': 'huakang-b'}).status_code == 403
        revoke_supplier_permission('carton_supplier:read')
        assert client.get(SUP + '/assets', params=SCOPE).status_code == 403
        login_as(client, 'admin')
        assert any(x['id'] == asset['id'] for x in ok(client.get(BASE, params=SCOPE)))


def test_multiple_recipients_require_choice_and_legacy_assets_stay_hidden(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id='OTHER', factory_id='huaxing', supplier_code='OTHER', supplier_name='其他供应商',
                status='ACTIVE', created_at='2026-10-19', updated_at='2026-10-19'))
            db.commit()
        assert upload(client)['status'] == 'failed'
        other = upload(client, supplier_id='OTHER')['asset']
        legacy = upload(client, 'ORDER_BOUND')['asset']
        supplier_login(client)
        assert not ok(client.get(SUP + '/assets', params=SCOPE))
        for asset in (other, legacy):
            assert client.get(SUP + f"/assets/{asset['id']}/document", params=SCOPE).status_code == 404


def test_special_library_binding_is_draft_until_internal_confirm_and_upload_roundtrip(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        body = create_body(); body['lines'][0]['mark_mode'] = 'PENDING'
        row = ok(client.post(SPECIAL, json=body), 201)
        row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
        asset = upload(client)['asset']
        supplier_login(client)
        options = ok(client.get(SPECIAL_SUP + '/mark-options', params={**SCOPE, 'request_id': row['id']}))
        assert any(x['id'] == asset['id'] for x in options)
        draft = ok(client.post(SPECIAL_SUP + f"/{row['id']}/lines/{row['lines'][0]['id']}/mark",
            json=command(row, mark_mode='EXISTING', asset_id=asset['id'], asset_revision=asset['revision'])))
        assert not draft['lines'][0]['mark_ready'] and draft['attachments'][-1]['role'] == 'DRAFT'
        login_as(client, 'admin')
        confirmed = ok(client.post(SPECIAL + f"/{row['id']}/lines/{row['lines'][0]['id']}/mark",
            json=command(draft, mark_mode='UPLOAD', attachment_id=draft['attachments'][-1]['id'])))
        assert confirmed['lines'][0]['mark_ready']
        assert confirmed['lines'][0]['mark_asset_id'] == asset['id']
        source = next(x for x in ok(client.get(BASE, params=SCOPE)) if x['id'] == asset['id'])
        assert source['workflow']['status'] == 'READY'
        assert any(x['confirmed'] for x in source['special_orders'])
        uploaded = ok(client.post(SPECIAL + f"/{row['id']}/attachments", data={**command(confirmed),
            'role': 'DRAFT', 'line_id': row['lines'][0]['id']}, files={'file': ('other.png', photo_bytes(), 'image/png')}), 201)
        library = ok(client.get(BASE, params=SCOPE))
        assert len(library) == 2 and any(x['special_orders'] for x in library)
        assert ok(client.get(BASE + '/binding-targets', params=SCOPE))
        supplier_login(client)
        assert len(ok(client.get(SUP + '/assets', params=SCOPE))) == 2
        assert ok(client.get(SUP + '/binding-targets', params=SCOPE))


def test_special_source_cannot_change_supplier_or_cross_customer_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        row = ok(client.post(SPECIAL, json=create_body()), 201)
        row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
        ok(client.post(SPECIAL + f"/{row['id']}/attachments", data={**command(row),
            'role': 'DRAFT', 'line_id': row['lines'][0]['id']}, files={'file': ('mark.png', photo_bytes(), 'image/png')}), 201)
        asset = ok(client.get(BASE, params=SCOPE))[0]
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            db.add(CartonSupplier(id='OTHER', factory_id='huaxing', supplier_code='OTHER', supplier_name='其他供应商',
                status='ACTIVE', created_at='2026-10-19', updated_at='2026-10-19'))
            db.commit()
        response = client.put(BASE + f"/{asset['id']}/sharing", params=SCOPE,
            json={'revision': asset['revision'], 'sharing_mode': 'SUPPLIER', 'supplier_id': 'OTHER'})
        assert response.status_code == 422, response.text
        revision = client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([
            {'status': 'PENDING', 'previous_asset_id': asset['id'], 'previous_revision': asset['revision']}])},
            files=[('files', ('updated.png', photo_bytes(), 'image/png'))])
        assert revision.status_code == 200, revision.text
        revised = revision.json()[0]['asset']
        assert revised and revised['sharing_mode'] == 'SUPPLIER'
        supplier_login(client)
        for source in (revised, {**asset, 'revision': asset['revision'] + 1}):
            response = client.put(SUP + f"/assets/{source['id']}/binding", params=SCOPE,
                json={'revision': source['revision'], 'order_ids': [order['id']]})
            assert response.status_code == 422, response.text


def test_restricted_customer_cannot_use_legacy_routes_for_shared_original(monkeypatch):
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin')
        asset = upload(client)['asset']
        asset = ok(client.put(BASE + f"/{asset['id']}/binding", params=SCOPE,
            json={'revision': asset['revision'], 'order_ids': [order['id']]}))
        legacy = client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([
            {'status': 'PENDING', 'sharing_mode': 'ORDER_BOUND'}])},
            files=[('files', ('legacy.png', photo_bytes(color='blue'), 'image/png'))])
        legacy = ok(legacy)[0]['asset']
        legacy = ok(client.put(BASE + f"/{legacy['id']}/binding", params=SCOPE,
            json={'revision': legacy['revision'], 'order_ids': [order['id']]}))
        from app.db import SessionLocal
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.models.carton_procurement import CartonCustomer
        from app.models.auth import AuthUser
        from sqlalchemy import select
        with SessionLocal() as db:
            customer = db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == 'huaxing',
                CartonCustomer.customer_code == order['customer_code']))
            admin = db.scalar(select(AuthUser).where(AuthUser.username == 'admin'))
            db.add(CartonCustomerAssignment(factory_id='huaxing', customer_id=customer.id, user_id=admin.id))
            db.commit()
        grant_supplier_permissions(permissions=('carton_mark:read', 'carton_mark:template_upload',
            'carton_procurement:read', 'carton_procurement:order_write'))
        ok(client.post('/api/auth/login', json={'username': 'supplier-test', 'password': PASSWORD}))
        assert asset['id'] not in {x['id'] for x in ok(client.get(BASE, params=SCOPE))}
        choices = ok(client.get(SPECIAL + '/mark-options', params=SCOPE))
        assert not {asset['id'], legacy['id']} & {x['id'] for x in choices}
        assert not any(x['id'] == order['id'] for x in ok(client.get(BASE + '/binding-orders', params=SCOPE)))
        assert not any(x['order_id'] == order['id'] for x in ok(client.get(BASE + '/binding-targets', params=SCOPE)))
        for suffix in ('/document', '/classification-history'):
            assert client.get(BASE + f"/{asset['id']}" + suffix, params=SCOPE).status_code == 403
        assert client.put(BASE + f"/{asset['id']}/classification", params=SCOPE,
            json={'revision': asset['revision'], 'status': 'READY'}).status_code == 403
        assert client.put(BASE + f"/{asset['id']}/binding", params=SCOPE,
            json={'revision': asset['revision'], 'order_ids': [order['id']]}).status_code == 403
        assert client.delete(BASE + f"/{asset['id']}", params={**SCOPE, 'revision': asset['revision']}).status_code == 403
        result = client.post(BASE + '/batch', data={**SCOPE, 'options_json': json.dumps([
            {'previous_asset_id': asset['id'], 'previous_revision': asset['revision']}])},
            files=[('files', ('new.png', photo_bytes(), 'image/png'))])
        assert result.status_code == 200 and result.json()[0]['status'] == 'failed'


def test_explicit_shared_file_enables_authorized_service_factory_without_orders(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        assert 'huakang-b' not in {x['factory_id'] for x in ok(client.get('/api/carton-supplier/memberships'))}
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        from sqlalchemy import select
        with SessionLocal() as db:
            supplier = db.scalar(select(CartonSupplier).where(CartonSupplier.factory_id == 'huakang-b',
                CartonSupplier.supplier_code == 'HEYUAN-DONGKANG'))
            if supplier is None:
                supplier = CartonSupplier(id='SHARED-B', factory_id='huakang-b', supplier_code='HEYUAN-DONGKANG',
                    supplier_name='河源东康', status='ACTIVE', created_at='2026-10-19', updated_at='2026-10-19')
                db.add(supplier)
            db.commit()
            supplier_id = supplier.id
        response = client.post(BASE + '/batch', data={'factory_id': 'huakang-b', 'options_json': json.dumps([
            {'sharing_mode': 'SUPPLIER', 'supplier_id': supplier_id}])},
            files=[('files', ('camera.png', photo_bytes(), 'image/png'))])
        assert response.status_code == 200, response.text
        asset = response.json()[0]['asset']
        assert asset, response.text
        supplier_login(client)
        assert 'huakang-b' in {x['factory_id'] for x in ok(client.get('/api/carton-supplier/memberships'))}
        visible = ok(client.get(SUP + '/assets', params={'factory_id': 'huakang-b'}))
        assert [x['id'] for x in visible] == [asset['id']] and visible[0]['orders'] == []
        login_as(client, 'admin')
        ok(client.put(BASE + f"/{asset['id']}/sharing", params={'factory_id': 'huakang-b'},
            json={'sharing_mode': 'INTERNAL', 'revision': asset['revision']}))
        supplier_login(client)
        assert 'huakang-b' not in {x['factory_id'] for x in ok(client.get('/api/carton-supplier/memberships'))}
        assert client.get(SUP + f"/assets/{asset['id']}/document", params={'factory_id': 'huakang-b'}).status_code == 403
