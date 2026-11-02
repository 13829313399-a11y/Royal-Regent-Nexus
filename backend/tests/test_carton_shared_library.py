"""Shared library user journeys on disposable SQLite, never the business store."""
import json
from uuid import uuid4
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_asset_quick import BASE, F, ok, upload, enable, grant, action
from test_carton_supplier_portal import setup_portal, supplier_login, grant_supplier_permissions
from test_carton_procurement_api import _order_payload


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED','false')


def test_private_supplier_share_confirm_cross_factory_links_and_revoke(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client,'admin');enable(monkeypatch)
        ok(client.post('/api/carton-procurement/customers',json=dict(factory_id='huakang-a',customer_code='DICKIE',customer_name='Dickie')))
        payload=_order_payload();payload.update(factory_id='huakang-a',contract_no='SC-SHARED-A')
        order=ok(client.post('/api/carton-procurement/orders',json=payload))
        order=ok(client.post('/api/carton-procurement/orders/'+order['order_no']+'/submit-supplier',json=dict(factory_id='huakang-a',expected_revision=order['revision'])))
        issued=client.post('/api/carton-procurement/orders/'+order['order_no']+'/purchase-order-issues.xlsx',json=dict(factory_id='huakang-a',expected_revision=order['revision']))
        assert issued.status_code==200,issued.text
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        supplier_login(client)
        asset=ok(upload(client,owner_department='supplier',text='supplier proof'))
        assert asset['shared_factory_ids']==[]
        login_as(client,'admin')
        for factory in ['huaxing','huakang-a']:
            assert client.get(BASE+'/'+asset['id']+'/document',params={'factory_id':factory}).status_code==404
            assert asset['id'] not in {x['id'] for x in ok(client.get(BASE,params={'factory_id':factory}))['items']}
        supplier_login(client)
        request=dict(revision=asset['revision'],request_id=uuid4().hex,shared_factory_ids=['huakang-a'])
        asset=ok(client.post(BASE+'/'+asset['id']+'/sharing',params=F,json=request))
        assert ok(client.post(BASE+'/'+asset['id']+'/sharing',params=F,json=request))['revision']==asset['revision']
        # The selected factory is a deliberate sharing boundary, not an upload hint.
        login_as(client,'admin');scope={'factory_id':'huakang-a'}
        assert client.get(BASE+'/'+asset['id']+'/document',params=F).status_code==404
        assert client.get(BASE+'/'+asset['id']+'/document',params=scope).content==b'supplier proof'
        asset=ok(client.get(BASE+'/'+asset['id'],params=scope))
        rows=ok(client.get(BASE+'/candidates',params={**scope,'owner_department':'sales-business'}))['items']
        selected=[{k:x[k] for k in ['kind','id','sheet','row','fingerprint']} for x in rows if x['id']==order['id']]
        assert selected
        link=dict(revision=asset['revision'],request_id=uuid4().hex,targets=selected)
        asset=ok(client.post(BASE+'/'+asset['id']+'/associations',params=scope,json=link))
        assert asset['targets'][0]['id']==order['id']
        assert ok(client.post(BASE+'/'+asset['id']+'/associations',params=scope,json=link))['revision']==asset['revision']
        change=dict(revision=asset['revision'],request_id=uuid4().hex,status='READY')
        asset=ok(client.post(BASE+'/'+asset['id']+'/classification',params=scope,json=change))
        assert asset['workflow']['status']=='READY'
        assert ok(client.post(BASE+'/'+asset['id']+'/classification',params=scope,json=change))['revision']==asset['revision']
        assert client.post(BASE+'/'+asset['id']+'/classification',params=scope,json={**change,'request_id':uuid4().hex}).status_code==409
        supplier_login(client)
        current=ok(client.get(BASE+'/'+asset['id'],params={**F,'supplier_view':True}))
        assert current['workflow']['status']=='READY'
        asset=ok(client.post(BASE+'/'+asset['id']+'/sharing',params=F,json=dict(revision=current['revision'],request_id=uuid4().hex,shared_factory_ids=[])))
        login_as(client,'admin')
        assert client.get(BASE+'/'+asset['id']+'/document',params=scope).status_code==404
        assert client.post(BASE+'/'+asset['id']+'/classification',params=scope,json=dict(revision=asset['revision'],request_id=uuid4().hex,status='PENDING')).status_code==404


def test_same_factory_unbound_sharing_history_and_original_session(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client);login_as(client,'admin');enable(monkeypatch)
        asset=ok(upload(client,text='unbound original',association='NONE'))
        grant('engineer_peer','pmc-warehouse');login_as(client,'engineer_peer')
        assert asset['id'] in {x['id'] for x in ok(client.get(BASE,params=F))['items']}
        asset=ok(action(client,asset,'READY'));asset=ok(action(client,asset,'HISTORY'))
        assert asset['workflow']['status']=='HISTORY'
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'));supplier_login(client)
        assert client.get(BASE+'/'+asset['id']+'/document',params={**F,'supplier_view':True}).status_code==404
        assert action(client,asset,'PENDING').status_code==403
        login_as(client,'admin')
        assert client.post('/api/carton-materials/old/actions',params={**F,'audience':'sales'},json={}).status_code==410
        from app.services import carton_asset_quick as service
        original=service.prepare
        def revoke(*args,**kwargs):
            result=original(*args,**kwargs)
            from app.db import SessionLocal
            from app.models.auth import AuthSession
            from sqlalchemy import update
            with SessionLocal() as db:
                db.execute(update(AuthSession).values(status='revoked'));db.commit()
            return result
        monkeypatch.setattr(service,'prepare',revoke)
        assert upload(client,text='revoked upload').status_code==401
        login_as(client,'admin')
        assert all(x['text']!='revoked upload' for x in ok(client.get(BASE,params=F))['items'])
