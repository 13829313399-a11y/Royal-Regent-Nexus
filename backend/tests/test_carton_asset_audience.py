"""Supplier audience and purchase links are independent, on disposable stores."""
import json
from uuid import uuid4

import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_asset_quick import BASE, F, ok, upload, enable, action
from test_carton_supplier_portal import setup_portal, supplier_login, grant_supplier_permissions, revoke_supplier_permission
from test_carton_procurement_api import _create_order


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')


def scope(client, asset, mode, **values):
    return client.post(BASE + '/' + asset['id'] + '/audience', params=F,
        json=dict(revision=asset['revision'], request_id=uuid4().hex, sharing_mode=mode, **values))


def test_unassociated_material_library_download_revocation_and_zero_order_projection(monkeypatch):
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = ok(upload(client, association='NONE', sharing_mode='SUPPLIER'))
        internal = ok(upload(client, association='NONE', sharing_mode='INTERNAL', text='private original'))
        evidence = ok(upload(client, association='NONE', purpose='EVIDENCE', text='private evidence'))
        assert shared['sharing_mode'] == 'SUPPLIER' and shared['targets'] == []
        assert internal['sharing_mode'] == 'INTERNAL'
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        assert ok(client.get(BASE + '/' + shared['id'], params={**F, 'supplier_view': True}))['id'] == shared['id']
        assert client.get(BASE + '/' + shared['id'] + '/document', params={**F, 'supplier_view': True}).content == b'synthetic text'
        assert {row['id'] for row in ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items']} == {shared['id']}
        projected = ok(client.get('/api/carton-supplier/carton-mark/assets', params=F))
        assert next(row for row in projected if row['id'] == shared['id'])['orders'] == []
        for asset in [internal, evidence]:
            assert client.get(BASE + '/' + asset['id'], params={**F, 'supplier_view': True}).status_code == 404
            assert client.get(BASE + '/' + asset['id'] + '/document', params={**F, 'supplier_view': True}).status_code == 404
        assert scope(client, shared, 'INTERNAL').status_code == 403
        assert client.get(BASE + '/' + shared['id'] + '/document', params={'factory_id': 'huadeng', 'supplier_view': True}).status_code in {403, 404}
        shared = ok(action(client, shared, 'READY'))
        login_as(client, 'admin')
        # Linking to an actual order must not publish an explicitly private source.
        rows = ok(client.get(BASE + '/candidates', params={**F, 'owner_department': 'sales-business'}))['items']
        chosen = next(row for row in rows if row['id'] == order['id'])
        ref = {key: chosen[key] for key in ('kind', 'id', 'sheet', 'row', 'fingerprint')}
        internal = ok(client.post(BASE + '/' + internal['id'] + '/associations', params=F,
            json=dict(revision=internal['revision'], request_id=uuid4().hex, targets=[ref])))
        assert internal['sharing_mode'] == 'INTERNAL'
        request = dict(revision=shared['revision'], request_id=uuid4().hex, sharing_mode='INTERNAL')
        revoked = ok(client.post(BASE + '/' + shared['id'] + '/audience', params=F, json=request))
        assert ok(client.post(BASE + '/' + shared['id'] + '/audience', params=F, json=request))['revision'] == revoked['revision']
        assert scope(client, shared, 'SUPPLIER').status_code == 409
        supplier_login(client)
        assert client.get(BASE + '/' + shared['id'] + '/document', params={**F, 'supplier_view': True}).status_code == 404
        assert action(client, revoked, 'PENDING').status_code == 404
        assert ok(client.get('/api/carton-supplier/carton-mark/assets', params=F)) == []
        login_as(client, 'admin')
        visible = ok(scope(client, revoked, 'SUPPLIER'))
        assert visible['targets'] == []
        supplier_login(client)
        assert client.get(BASE + '/' + visible['id'], params={**F, 'supplier_view': True}).status_code == 200
        revoke_supplier_permission('carton_asset:read')
        # An expired allow alone is not an explicit deny; supplier-source access
        # is still an audience grant. A real deny must take precedence.
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        from sqlalchemy import select
        with SessionLocal() as db:
            permission=db.scalar(select(AuthPermission).where(AuthPermission.code=='carton_asset:read'))
            db.add(AuthUserPermissionOverride(id='audience-deny',user_id='supplier-test',permission_id=permission.id,
                factory_id='huaxing',department='supplier',effect='deny',status='active',reason='explicit deny regression'))
            db.commit()
        supplier_login(client)
        assert client.get(BASE + '/' + visible['id'] + '/document', params={**F, 'supplier_view': True}).status_code == 404


def test_named_audience_works_before_first_issued_order_and_parent_privacy_is_retained(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin'); enable(monkeypatch)
        _create_order(client, submit_supplier=False)
        from app.db import SessionLocal
        from app.models.auth import AuthUser, AuthUserAuthorizationRevision, EmployeeProfile
        from app.services.auth import make_password_hash
        from test_carton_supplier_portal import PASSWORD
        salt, digest = make_password_hash(PASSWORD)
        with SessionLocal() as db:
            db.add(AuthUser(id='supplier-test', username='supplier-test', display_name='supplier test', password_salt=salt,
                password_hash=digest, status='active', force_password_change=0, created_at='2026-11-04', updated_at='2026-11-04'))
            db.add(AuthUserAuthorizationRevision(user_id='supplier-test', revision=1, updated_at='2026-11-04'))
            db.add(EmployeeProfile(user_id='supplier-test', primary_factory_id='huaxing', primary_department='pmc-warehouse',
                position='supplier contact', confirmation_status='confirmed', created_at='2026-11-04', updated_at='2026-11-04'))
            db.commit()
        grant_supplier_permissions()
        login_as(client, 'admin')
        source = ok(upload(client, association='NONE', sharing_mode='SUPPLIER'))
        private = ok(upload(client, association='NONE', sharing_mode='INTERNAL'))
        child = ok(upload(client, association='NONE', previous_asset_id=private['id'], previous_revision=private['revision'], text='private revision'))
        assert child['sharing_mode'] == 'INTERNAL'
        supplier_login(client)
        assert ok(client.get('/api/carton-supplier/workspace', params=F))['orders'] == []
        assert ok(client.get(BASE, params={**F, 'owner_department': 'supplier'}))['items'][0]['id'] == source['id']
        assert client.get(BASE + '/' + child['id'] + '/document', params={**F, 'supplier_view': True}).status_code == 404


def test_audience_rejects_missing_supplier_evidence_and_foreign_factory(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin'); enable(monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        from sqlalchemy import update
        with SessionLocal() as db:
            db.execute(update(CartonSupplier).where(CartonSupplier.factory_id=='huaxing').values(status='INACTIVE'))
            db.commit()
        assert upload(client, sharing_mode='SUPPLIER').status_code == 422
        private = ok(upload(client, sharing_mode='INTERNAL'))
        assert scope(client, private, 'SUPPLIER').status_code == 422
        assert upload(client, purpose='EVIDENCE', sharing_mode='SUPPLIER').status_code == 403
        assert client.post(BASE + '/' + private['id'] + '/audience', params={'factory_id': 'huadeng'},
            json=dict(revision=private['revision'], request_id=uuid4().hex, sharing_mode='SUPPLIER')).status_code == 404


def test_both_audience_routes_recheck_the_owners_current_customer_responsibility(monkeypatch):
    from test_carton_asset_quick import grant
    with make_client(monkeypatch) as client:
        order=setup_portal(client)
        enable(monkeypatch)
        grant('engineer_peer','pmc-warehouse')
        login_as(client,'engineer_peer')
        asset=ok(upload(client,owner_department='pmc-warehouse',association='NONE',sharing_mode='INTERNAL'))
        login_as(client,'admin')
        rows=ok(client.get(BASE+'/candidates',params={**F,'owner_department':'pmc-warehouse'}))['items']
        target=next(row for row in rows if row['id']==order['id'])
        asset=ok(client.post(BASE+'/'+asset['id']+'/associations',params=F,json=dict(
            revision=asset['revision'],request_id=uuid4().hex,
            targets=[{key:target[key] for key in ('kind','id','sheet','row','fingerprint')}])) )
        login_as(client,'engineer_peer')
        assert scope(client,asset,'SUPPLIER').status_code==403
        assert client.put('/api/carton-mark/assets/'+asset['id']+'/sharing',params=F,
            json=dict(revision=asset['revision'],sharing_mode='SUPPLIER')).status_code==403
        login_as(client,'admin')
        current=ok(client.get(BASE+'/'+asset['id'],params=F))
        assert current['sharing_mode']=='INTERNAL' and current['revision']==asset['revision']


def test_new_and_legacy_audiences_validate_multiple_customer_schedule_targets(monkeypatch):
    from test_carton_item_schedule import workbook,source_row
    with make_client(monkeypatch) as client:
        setup_portal(client);login_as(client,'admin');enable(monkeypatch)
        ok(client.post('/api/carton-procurement/customers',json=dict(factory_id='huaxing',customer_code='ALT',customer_name='ALT')))
        for customer,contract in [('DICKIE','SCOPE-A'),('ALT','SCOPE-B')]:
            ok(client.post('/api/carton-procurement/weekly-imports',params=F,data={'customer_code':customer},
                files={'file':('synthetic.xlsx',workbook([source_row(contract=contract,item=contract)]))}))
        rows=ok(client.get(BASE+'/candidates',params={**F,'owner_department':'sales-business'}))['items']
        refs=[{key:row[key] for key in ('kind','id','sheet','row','fingerprint')}
            for row in rows if row['kind']=='SCHEDULE' and row['contract_no'] in {'SCOPE-A','SCOPE-B'}]
        assert len(refs)==2
        assert upload(client,association='MANUAL',targets=refs,sharing_mode='SUPPLIER').status_code==422
        asset=ok(upload(client,association='MANUAL',targets=refs,sharing_mode='INTERNAL'))
        assert scope(client,asset,'SUPPLIER').status_code==422
        assert client.put('/api/carton-mark/assets/'+asset['id']+'/sharing',params=F,
            json=dict(revision=asset['revision'],sharing_mode='SUPPLIER')).status_code==422
        asset=ok(client.post(BASE+'/'+asset['id']+'/associations',params=F,
            json=dict(revision=asset['revision'],request_id=uuid4().hex,targets=refs[:1])))
        asset=ok(scope(client,asset,'SUPPLIER'))
        assert client.post(BASE+'/'+asset['id']+'/associations',params=F,
            json=dict(revision=asset['revision'],request_id=uuid4().hex,targets=refs)).status_code==422
        current=ok(client.get(BASE+'/'+asset['id'],params=F))
        assert current['revision']==asset['revision'] and len(current['targets'])==1
