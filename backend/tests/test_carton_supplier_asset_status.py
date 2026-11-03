"""Supplier progress cannot become confirmation or authority over shared sources."""
import json
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client,login_as
from test_carton_supplier_portal import setup_portal,supplier_login,grant_supplier_permissions,revoke_supplier_permission
from test_carton_mark_asset_images import photo_bytes

F={'factory_id':'huaxing'}
BASE='/api/carton-supplier/carton-mark/assets'

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED','false')
    # Settings also reads backend/.env; absence does not disable a local flag.
    monkeypatch.setenv('CARTON_ASSET_V1_ENABLED','false')
    monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED','false')

def own(client):
    supplier_login(client)
    response=client.post(BASE+'/upload',data={**F,'shared_unbound':'true','targets_json':'[]','request_id':uuid4().hex},files=[('files',('supplier.png',photo_bytes(),'image/png'))])
    assert response.status_code==201,response.text
    row=response.json()[0];assert row['status']=='created',row
    return row['asset']

def classify(client,asset,status='DRAFT',request_id=None,revision=None,factory='huaxing'):
    return client.put(BASE+'/'+asset['id']+'/classification',params={'factory_id':factory},json=dict(
        revision=asset['revision'] if revision is None else revision,status=status,request_id=request_id or uuid4().hex))

def listing(client):
    response=client.get(BASE,params=F);assert response.status_code==200,response.text
    return {x['id']:x for x in response.json()}

def test_legacy_own_progress_revision_retry_and_no_confirmation(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client);asset=own(client);assert asset['can_classify']
        original=client.get(BASE+'/'+asset['id']+'/document',params=F).content
        rid=uuid4().hex
        response=classify(client,asset,request_id=rid);assert response.status_code==200,response.text
        saved=response.json();assert saved['revision']==asset['revision']+1 and saved['workflow']['status']=='DRAFT'
        assert classify(client,asset,request_id=rid).json()['revision']==saved['revision']
        assert classify(client,asset,status='PENDING',request_id=rid).status_code==409
        assert classify(client,asset,status='PENDING').status_code==409
        for status in ['READY','HISTORY','UNCLASSIFIED']:
            assert classify(client,saved,status).status_code==422
        assert client.get(BASE+'/'+asset['id']+'/document',params=F).content==original
        row=listing(client)[asset['id']];assert row['workflow']['status']=='DRAFT' and row['can_classify']

@pytest.mark.parametrize('state',['READY','HISTORY'])
def test_supplier_cannot_revert_confirmed_or_history(monkeypatch,state):
    with make_client(monkeypatch) as client:
        setup_portal(client);asset=own(client)
        login_as(client,'admin')
        response=client.put('/api/carton-mark/assets/'+asset['id']+'/classification',params=F,json=dict(revision=asset['revision'],status=state))
        assert response.status_code==200,response.text
        supplier_login(client);row=listing(client)[asset['id']]
        assert not row['can_classify']
        assert classify(client,row).status_code==403

def test_visibility_and_creator_alone_never_grant_classification(monkeypatch):
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        setup_portal(client);asset=own(client)
        # Preserve creator/visibility; destroy only trustworthy supplier provenance.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            event=db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.entity_id==asset['id'],CartonAuditEvent.event_type=='CARTON_MARK_ASSET_CREATED'))
            event.actor_user_id='user-admin';db.commit()
        assert not listing(client)[asset['id']]['can_classify']
        assert classify(client,asset).status_code==403

def test_shared_internal_source_other_factory_and_revoked_edit_denied(monkeypatch):
    with make_client(monkeypatch) as client:
        order=setup_portal(client);asset=own(client)
        assert classify(client,asset,factory='huakang-a').status_code in {403,404}
        login_as(client,'admin')
        response=client.post('/api/carton-mark/assets/batch',data={**F,'options_json':json.dumps([dict(status='PENDING',sharing_mode='SUPPLIER',supplier_id=order['supplier_id'])])},files=[('files',('internal.png',photo_bytes(color='green'),'image/png'))])
        assert response.status_code==200,response.text
        shared=response.json()[0]['asset'];assert shared,response.text
        supplier_login(client);assert not listing(client)[shared['id']]['can_classify']
        assert classify(client,shared).status_code==403
        revoke_supplier_permission('carton_supplier:edit')
        assert not listing(client)[asset['id']]['can_classify']
        assert classify(client,asset).status_code==403

def test_v1_ownership_and_write_switch_are_authoritative(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        monkeypatch.setenv('CARTON_ASSET_V1_ENABLED','true');monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED','true')
        supplier_login(client)
        response=client.post('/api/carton-mark/assets/quick',params=F,data={'metadata':json.dumps(dict(request_id=uuid4().hex,owner_department='supplier',text='synthetic supplier only'))})
        assert response.status_code==200,response.text
        asset=response.json();assert asset['can_classify']
        response=classify(client,asset);assert response.status_code==200,response.text
        saved=response.json();assert saved['workflow']['status']=='DRAFT'
        monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED','false')
        assert classify(client,saved,status='PENDING').status_code==403
        row=client.get('/api/carton-mark/assets/quick/'+asset['id'],params={**F,'supplier_view':True}).json()
        assert not row['can_classify'] and row['workflow']['status']=='DRAFT'


def internal_asset(client, order, *, mode='SUPPLIER', purpose='MATERIAL', previous=None):
    options = dict(owner_department='sales-business', status='PENDING', sharing_mode=mode,
                   supplier_id=order['supplier_id'] if mode == 'SUPPLIER' else '', purpose=purpose)
    if mode == 'SUPPLIER':
        context = client.get('/api/carton-procurement/orders/' + order['order_no'] + '/purchase-order-context', params=F)
        assert context.status_code == 200, context.text
        issue = context.json()['issues'][0]
        options['targets'] = [dict(order_kind='REGULAR', order_id=order['id'], expected_revision=order['revision'], issue_id=issue['id'])]
    if previous:
        options.update(previous_asset_id=previous['id'], previous_revision=previous['revision'])
    response = client.post('/api/carton-mark/assets/batch', data={**F, 'options_json': json.dumps([options])},
                           files=[('files', ('sales.png', photo_bytes(color='green'), 'image/png'))])
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row['asset'], row
    return row['asset']


def test_v1_supplier_can_classify_and_collaborate_on_shared_internal_material(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, grant, action, upload
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = internal_asset(client, order)
        private = internal_asset(client, order, mode='INTERNAL')
        evidence_response = upload(client, purpose='EVIDENCE', text='仅内部凭据')
        assert evidence_response.status_code == 200, evidence_response.text
        evidence = evidence_response.json()
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonReceipt
        from sqlalchemy import select
        def physical_state():
            with SessionLocal() as db:
                current = db.get(CartonOrder, order['id'])
                return (current.revision, current.status, tuple(db.scalars(select(CartonReceipt.id)).all()))
        baseline = physical_state()
        grant('warehouse_keeper', 'pmc-warehouse')
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = client.get(QUICK + '/' + shared['id'], params={**F, 'supplier_view': True})
        assert row.status_code == 200, row.text
        asset = row.json()
        assert asset['can_classify'] and asset['can_associate'] and asset['can_share']
        assert {'DRAFT', 'PENDING', 'READY', 'HISTORY'}.issubset(asset['allowed_statuses'])
        assert classify(client, shared, 'DRAFT').status_code in (403, 404)
        assert client.get(QUICK + '/' + private['id'], params={**F, 'supplier_view': True}).status_code == 404
        assert action(client, private, 'READY').status_code in (403, 404)
        assert client.get(QUICK + '/' + evidence['id'], params={**F, 'supplier_view': True}).status_code == 404
        assert action(client, evidence, 'READY').status_code in (403, 404)
        request_id = uuid4().hex
        body = dict(revision=asset['revision'], request_id=request_id, status='READY')
        url = QUICK + '/' + asset['id'] + '/classification'
        response = client.post(url, params=F, json=body)
        assert response.status_code == 200, response.text
        asset = response.json()
        assert asset['workflow']['status'] == 'READY' and asset['workflow']['updated_by_name'] == '供应商测试'
        replay = client.post(url, params=F, json=body)
        assert replay.status_code == 200 and replay.json()['revision'] == asset['revision']
        assert client.post(url, params=F, json={**body, 'status': 'DRAFT'}).status_code == 409
        assert client.post(url, params=F, json={**body, 'request_id': uuid4().hex}).status_code == 409
        for status in ('DRAFT', 'HISTORY'):
            result = action(client, asset, status)
            assert result.status_code == 200, result.text
            asset = result.json()
            assert asset['workflow']['status'] == status and asset['can_associate'] and asset['can_share']
        for username in ('warehouse_keeper', 'admin'):
            login_as(client, username)
            result = client.get(QUICK + '/' + asset['id'], params=F)
            assert result.status_code == 200, result.text
            assert result.json()['workflow']['status'] == 'HISTORY'
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.entity_id == asset['id'],
                CartonAuditEvent.event_type == 'CARTON_MARK_ASSET_CLASSIFIED')))
            assert len(events) >= 3 and events[-1].actor_user_id == 'supplier-test'
        assert physical_state() == baseline


def test_v1_shared_material_supplier_permission_and_write_switches(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = internal_asset(client, order)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = client.get(QUICK + '/' + shared['id'], params={**F, 'supplier_view': True}).json()
        assert row['can_classify']
        assert client.post(QUICK + '/' + row['id'] + '/classification', params={'factory_id': 'huakang-a'},
            json=dict(revision=row['revision'], request_id=uuid4().hex, status='READY')).status_code in (403, 404)
        monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED', 'false')
        assert action(client, row, 'READY').status_code == 403
        assert not client.get(QUICK + '/' + row['id'], params={**F, 'supplier_view': True}).json()['can_classify']
        monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED', 'true')
        revoke_supplier_permission('carton_supplier:edit')
        assert action(client, row, 'READY').status_code == 403
        assert not client.get(QUICK + '/' + row['id'], params={**F, 'supplier_view': True}).json()['can_classify']


def test_v1_supplier_cannot_confirm_child_if_parent_is_no_longer_shared(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        parent = internal_asset(client, order)
        parent = action(client, parent, 'READY').json()
        child = internal_asset(client, order, previous=parent)
        parent = client.get(QUICK + '/' + parent['id'], params=F).json()
        response = client.put('/api/carton-mark/assets/' + parent['id'] + '/sharing', params=F,
            json=dict(revision=parent['revision'], sharing_mode='INTERNAL'))
        assert response.status_code == 200, response.text
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        current = client.get(QUICK + '/' + child['id'], params={**F, 'supplier_view': True})
        assert current.status_code == 200, current.text
        denied = action(client, current.json(), 'READY')
        assert denied.status_code in (403, 404, 409), denied.text
        login_as(client, 'admin')
        assert client.get(QUICK + '/' + parent['id'], params=F).json()['workflow']['status'] == 'READY'
        assert client.get(QUICK + '/' + child['id'], params=F).json()['workflow']['status'] == 'PENDING'


@pytest.mark.parametrize('denied_code', ['carton_asset:read', 'carton_asset:manage'])
def test_v1_shared_material_explicit_permission_deny_wins(monkeypatch, denied_code):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = internal_asset(client, order)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = client.get(QUICK + '/' + shared['id'], params={**F, 'supplier_view': True}).json()
        assert row['can_classify']
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == denied_code))
            db.add(AuthUserPermissionOverride(id='deny-shared-' + denied_code, user_id='supplier-test',
                permission_id=permission.id, effect='deny', factory_id='huaxing', department='supplier',
                status='active', reason='合成权限边界测试'))
            db.commit()
        supplier_login(client)
        assert action(client, row, 'READY').status_code in (403, 404)


def test_v1_shared_material_rejects_disabled_supplier_session(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = internal_asset(client, order)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = client.get(QUICK + '/' + shared['id'], params={**F, 'supplier_view': True}).json()
        assert row['can_classify']
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        with SessionLocal() as db:
            db.get(AuthUser, 'supplier-test').status = 'disabled'
            db.commit()
        assert action(client, row, 'READY').status_code in (401, 403)


def test_v1_shared_child_ready_archives_authorized_parent(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        parent = internal_asset(client, order)
        parent = action(client, parent, 'READY').json()
        child = internal_asset(client, order, previous=parent)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        supplier_login(client)
        row = client.get(QUICK + '/' + child['id'], params={**F, 'supplier_view': True}).json()
        response = action(client, row, 'READY')
        assert response.status_code == 200, response.text
        assert response.json()['workflow']['status'] == 'READY'
        old = client.get(QUICK + '/' + parent['id'], params={**F, 'supplier_view': True})
        assert old.status_code == 200, old.text
        assert old.json()['workflow']['status'] == 'HISTORY'


def test_v1_explicit_confirm_deny_blocks_ready_but_not_progress(monkeypatch):
    from test_carton_asset_quick import BASE as QUICK, enable, action
    from sqlalchemy import select
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        login_as(client, 'admin'); enable(monkeypatch)
        shared = internal_asset(client, order)
        grant_supplier_permissions(permissions=('carton_asset:read', 'carton_asset:manage'))
        owned = own(client)
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'carton_asset:confirm'))
            db.add(AuthUserPermissionOverride(id='deny-shared-confirm', user_id='supplier-test',
                permission_id=permission.id, effect='deny', factory_id='huaxing', department='supplier',
                status='active', reason='合成权限边界测试'))
            db.commit()
        supplier_login(client)
        row = client.get(QUICK + '/' + shared['id'], params={**F, 'supplier_view': True}).json()
        assert row['can_classify'] and set(row['allowed_statuses']) == {'DRAFT', 'PENDING', 'HISTORY'}
        assert action(client, row, 'READY').status_code == 403
        own_row = client.get(QUICK + '/' + owned['id'], params={**F, 'supplier_view': True}).json()
        assert own_row['can_classify'] and 'READY' not in own_row['allowed_statuses']
        assert action(client, own_row, 'READY').status_code == 403
        assert action(client, own_row, 'DRAFT').status_code == 200
        for status in ('DRAFT', 'PENDING', 'HISTORY'):
            result = action(client, row, status)
            assert result.status_code == 200, result.text
            row = result.json()
            assert row['workflow']['status'] == status
