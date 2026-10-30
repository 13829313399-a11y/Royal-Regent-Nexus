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
