"""v1a contracts on disposable SQLite only; no business database access."""
import hashlib,json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from test_molding_sample_api import make_client,login_as,grant_permission_override
from test_carton_item_schedule import _prepare_schedule_customer,workbook,source_row

BASE='/api/carton-mark/assets/quick'
F={'factory_id':'huaxing'}


def ok(response):
    assert response.status_code in {200,201},response.text
    return response.json()


def upload(client,**values):
    body=dict(request_id=uuid4().hex,owner_department='sales-business',text='synthetic text',**{})
    body.update(values)
    return client.post(BASE,params=F,data={'metadata':json.dumps(body)})


def action(client,asset,status,**values):
    return client.post(BASE+f"/{asset['id']}/classification",params=F,json=dict(revision=asset['revision'],request_id=uuid4().hex,status=status,**values))


def enable(monkeypatch):
    monkeypatch.setenv('CARTON_ASSET_V1_ENABLED','true')
    monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED','true')


def schedule(client,rows):
    return ok(client.post('/api/carton-procurement/weekly-imports',params=F,data={'customer_code':'DICKIE'},
        files={'file':('synthetic.xlsx',workbook(rows))}))


def grant(username,department,confirm=False):
    for action_name in ['read','manage']+(['confirm'] if confirm else []):
        grant_permission_override(username,'carton_asset:'+action_name,factory_id='huaxing',department=department)


def test_text_scope_idempotency_and_safe_rollback(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,'admin');enable(monkeypatch)
        assert upload(client,owner_department=None).status_code==422
        request=uuid4().hex;text='<script>alert(1)</script> 合成文字'
        a=ok(upload(client,text=text,request_id=request))
        assert a['kind']=='text' and a['workflow']['status']=='PENDING' and not a['targets']
        assert a['sha256']==hashlib.sha256(text.encode()).hexdigest()
        assert ok(upload(client,text=text,request_id=request))['id']==a['id']
        assert upload(client,text='changed',request_id=request).status_code==409
        r=client.get(BASE+f"/{a['id']}/document",params={**F,'preview':True})
        assert r.content==text.encode() and r.headers['content-type'].startswith('text/plain')
        assert r.headers['x-content-type-options']=='nosniff' and r.headers['content-security-policy'].startswith('sandbox')
        a=ok(action(client,a,'READY'));assert a['workflow']['status']=='READY'
        assert a['workflow']['confirmed_by_name']
        b=ok(upload(client,previous_asset_id=a['id'],previous_revision=a['revision'],text='new pending'))
        assert b['workflow']['status']=='PENDING'
        assert ok(client.get(BASE+'/'+a['id'],params=F))['workflow']['status']=='READY'
        b=ok(action(client,b,'READY'))
        assert ok(client.get(BASE+'/'+a['id'],params=F))['workflow']['status']=='HISTORY'
        assert action(client,b,'DRAFT').status_code==200
        assert action(client,b,'READY').status_code==409
        monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED','false')
        assert upload(client).status_code==403
        assert client.get(BASE+'/'+b['id'],params=F).status_code==200
        assert client.put('/api/carton-mark/assets/'+b['id']+'/classification',params=F,
            json=dict(revision=b['revision'],status='READY')).status_code==403


def test_department_download_guard_legacy_routes_and_historical_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,'admin');enable(monkeypatch)
        business=ok(upload(client))
        warehouse=ok(upload(client,owner_department='pmc-warehouse'))
        grant('engineer','sales-business',True);grant('engineer_peer','pmc-warehouse')
        login_as(client,'engineer')
        own=ok(client.get(BASE,params=F))
        assert {x['id'] for x in own['items']}=={business['id'],warehouse['id']}
        assert client.get(BASE+'/'+warehouse['id'],params=F).status_code==200
        assert client.get('/api/carton-mark/assets/'+warehouse['id']+'/document',params=F).status_code==200
        assert {x['id'] for x in ok(client.get('/api/carton-mark/assets',params=F))}=={business['id'],warehouse['id']}
        assert client.get(BASE+'/'+business['id'],params={'factory_id':'huakang-a'}).status_code==404
        assert upload(client,owner_department='pmc-warehouse').status_code==403
        assert client.put('/api/carton-mark/assets/'+warehouse['id']+'/sharing',params=F,
            json=dict(revision=warehouse['revision'],sharing_mode='INTERNAL')).status_code==403
        warehouse=ok(client.get(BASE+'/'+warehouse['id'],params=F))
        assert client.post('/api/carton-mark/assets/'+warehouse['id']+'/bindings/missing/confirm',params=F,
            json=dict(revision=warehouse['revision'])).status_code in {403,404,422}
        # New source permissions do not grant template/QC or procurement writes.
        assert client.get('/api/carton-procurement/orders',params=F).status_code==403
        assert client.post('/api/carton-mark/templates',data={'factory_id':'huaxing'}).status_code in {403,422}
        login_as(client,'engineer_peer')
        assert client.get(BASE+'/'+business['id'],params=F).status_code==200
        warehouse=ok(action(client,warehouse,'READY'))
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        with SessionLocal() as db:
            db.get(CartonMarkAsset,warehouse['id']).owner_department=None;db.commit()
        assert [x['id'] for x in ok(client.get(BASE,params={**F,'history':True}))['items']]==[warehouse['id']]
        login_as(client,'admin')
        assert [x['id'] for x in ok(client.get(BASE,params={**F,'history':True}))['items']]==[warehouse['id']]


def test_schedule_unique_ambiguous_none_reimport_and_counts(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client)
        batch=schedule(client,[source_row(contract='QUICK-ONLY',item='QUICK-ONE'),source_row(contract='QUICK-MULTI',item='QUICK-A'),source_row(contract='QUICK-MULTI',item='QUICK-B')])
        login_as(client,'admin')
        enable(monkeypatch)
        a=ok(upload(client,contract_number='QUICK-ONLY'))
        assert len(a['targets'])==1 and a['targets'][0]['kind']=='SCHEDULE'
        multi=ok(upload(client,contract_number='QUICK-MULTI'));assert len(multi['targets'])==2
        assert not ok(upload(client,contract_number='NO-TARGET'))['targets']
        assert not ok(upload(client,contract_number='QUICK-ONLY',association='NONE'))['targets']
        candidates=ok(client.get(BASE+'/candidates',params={**F,'owner_department':'sales-business','contract_number':'QUICK-MULTI'}))['items']
        chosen={k:candidates[0][k] for k in ['kind','id','sheet','row','fingerprint']}
        linked=ok(client.post(BASE+'/'+multi['id']+'/associations',params=F,json=dict(revision=multi['revision'],request_id=uuid4().hex,target=chosen)))
        assert len(linked['targets'])==1
        def marks(current):return ok(client.get('/api/carton-mark/assets/schedule',params={**F,'batch_id':current['id']}))
        projected=marks(batch)
        assert projected['source_policy']=='ASSET_V1'
        found=next(x for x in projected['rows'] if x['asset_ids']==[a['id']])
        assert found['has_materials'] and found['pending_count']==1 and found['confirmed_count']==0
        a=ok(action(client,a,'READY'));assert next(x for x in marks(batch)['rows'] if a['id'] in x['asset_ids'])['confirmed_count']==1
        # Reimport moves rows; a unique same-business identity carries only its explicit reference.
        new=schedule(client,[source_row(contract='QUICK-MULTI',item='QUICK-A'),source_row(contract='QUICK-ONLY',item='QUICK-ONE')])
        assert sum(a['id'] in x['asset_ids'] for x in marks(new)['rows'])==1
        duplicate=schedule(client,[source_row(contract='QUICK-ONLY',item='QUICK-ONE'),source_row(contract='QUICK-ONLY',item='QUICK-ONE')])
        assert all(a['id'] not in x['asset_ids'] for x in marks(duplicate)['rows'])
        assert client.post(BASE+'/'+multi['id']+'/associations',params=F,json=dict(revision=linked['revision'],request_id=uuid4().hex,target=chosen)).status_code==404


def test_supplier_own_shared_evidence_and_confirmation(monkeypatch):
    from test_carton_supplier_portal import setup_portal,supplier_login,grant_supplier_permissions
    with make_client(monkeypatch) as client:
        setup_portal(client);_prepare_schedule_customer(client)
        schedule(client,[source_row(contract='QUICK-DONGKANG',item='Q-DK')])
        login_as(client,'admin')
        enable(monkeypatch)
        shared=ok(upload(client,contract_number='QUICK-DONGKANG'))
        evidence=ok(upload(client,contract_number='QUICK-DONGKANG',purpose='EVIDENCE'))
        assert action(client,evidence,'READY').status_code==422
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        supplier_login(client)
        own=ok(upload(client,owner_department='supplier'))
        assert own['owner_supplier_id'] and own['owner_department']=='supplier'
        own=ok(action(client,own,'READY'))
        assert upload(client,owner_department='supplier',purpose='EVIDENCE').status_code==403
        # Pre-purchase internal material remains visible to the warehouse; the
        # supplier receives it through its own issued order, not factory access.
        assert client.get(BASE+'/'+shared['id'],params={**F,'supplier_view':True}).status_code==404
        assert client.get(BASE+'/'+evidence['id'],params={**F,'supplier_view':True}).status_code==404
        assert client.get(BASE+'/'+evidence['id'],params=F).status_code==404
        assert upload(client,owner_department='sales-business').status_code==403
        assert client.get('/api/carton-mark/assets/'+evidence['id']+'/document',params=F).status_code==403
        originals=ok(client.get(BASE,params={**F,'owner_department':'supplier'}))['items']
        assert {x['id'] for x in originals}=={own['id']}
        assert client.put('/api/carton-supplier/carton-mark/assets/'+shared['id']+'/associations',params=F,
            json=dict(revision=shared['revision'],request_id=uuid4().hex,targets=[])).status_code==404
        # No internal actor can alter supplier ownership by guessing an ID.
        login_as(client,'admin')
        assert action(client,own,'READY').status_code in {403,404}
        assert client.put('/api/carton-mark/assets/'+evidence['id']+'/sharing',params=F,
            json=dict(revision=evidence['revision'],sharing_mode='SUPPLIER',supplier_id=own['owner_supplier_id'])).status_code==403


def test_legacy_revisions_groups_explicit_bindings_and_concurrent_commands(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from test_carton_mark_asset_images import photo_bytes
    from test_carton_mark_assets import seed_order
    import app.models.carton_procurement as models
    with make_client(monkeypatch) as client:
        login_as(client,'admin');enable(monkeypatch)
        from app.db import SessionLocal
        with SessionLocal() as db:
            seed_order(db,models,'quick-regular-a',contract='Q-REG-ONLY')
            seed_order(db,models,'quick-regular-b',contract='Q-REG-MULTI')
            seed_order(db,models,'quick-regular-c',contract='Q-REG-MULTI',item='different')
            seed_order(db,models,'quick-regular-foreign',contract='Q-REG-ONLY',factory='huakang-a')
        assert len(ok(upload(client,contract_number='Q-REG-ONLY'))['targets'])==1
        assert len(ok(upload(client,contract_number='Q-REG-MULTI'))['targets'])==2
        def photo(name,options):
            return ok(client.post('/api/carton-mark/assets/batch',data={**F,'options_json':json.dumps([options])},
                files=[('files',(name,photo_bytes(),'image/png'))]))[0]
        a=photo('one.png',dict(owner_department='pmc-warehouse',status='PENDING'))['asset']
        bad=photo('revision.png',dict(owner_department='sales-business',status='PENDING',previous_asset_id=a['id'],previous_revision=a['revision']))
        assert bad['status']=='failed' and '归属' in bad['message']
        b=photo('two.png',dict(owner_department='pmc-warehouse',status='PENDING'))['asset']
        group=ok(client.post('/api/carton-mark/assets/photo-groups',params=F,json=dict(
            assets=[dict(id=x['id'],revision=x['revision']) for x in [a,b]],order_id='quick-regular-a')))
        assert all(ok(client.get(BASE+'/'+x['id'],params=F))['targets'][0]['id']=='quick-regular-a' for x in group)
        group=ok(client.put('/api/carton-mark/assets/photo-groups/'+group[0]['photo_group_id']+'/binding',params=F,
            json=dict(assets=[dict(id=x['id'],revision=x['revision']) for x in group],contract_number='')))
        assert all(not ok(client.get(BASE+'/'+x['id'],params=F))['targets'] for x in group)
        # Same request races must create one original, and stale revision races
        # must commit only one classification event.
        request=uuid4().hex;barrier=Barrier(2)
        def create(_):
            barrier.wait();return upload(client,text='concurrent synthetic',request_id=request)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(create,range(2)))
        assert [x.status_code for x in responses]==[200,200],[x.text for x in responses]
        assert responses[0].json()['id']==responses[1].json()['id']
        a=responses[0].json();barrier=Barrier(2)
        def classify(_):barrier.wait();return action(client,a,'DRAFT')
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(classify,range(2)))
        assert sorted(x.status_code for x in responses)==[200,409],[x.text for x in responses]


def test_permission_revocation_and_atomic_rejection(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client,'admin');enable(monkeypatch)
        a=ok(upload(client));before=ok(client.get(BASE+'/'+a['id'],params=F))
        grant('engineer','sales-business',True);login_as(client,'engineer')
        grant_permission_override('engineer','carton_asset:confirm',factory_id='huaxing',department='sales-business',effect='deny')
        assert action(client,a,'READY').status_code==403
        grant_permission_override('engineer','carton_asset:manage',factory_id='huaxing',department='sales-business',effect='deny')
        assert upload(client).status_code==403
        login_as(client,'admin');assert ok(client.get(BASE+'/'+a['id'],params=F))==before


def test_legacy_target_customer_guard_evidence_revision_and_frozen_backfill(monkeypatch):
    from test_carton_supplier_portal import setup_portal,supplier_login,grant_supplier_permissions
    from test_carton_mark_asset_images import photo_bytes
    from sqlalchemy import delete,select
    with make_client(monkeypatch) as client:
        order=setup_portal(client)
        login_as(client,'engineer_peer')
        login_as(client,'admin');enable(monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        from app.models.carton_procurement import CartonAuditEvent,CartonOrder,CartonCustomer
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from app.models.auth import AuthUser
        with SessionLocal() as db:
            customer=db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id=='huaxing',CartonCustomer.customer_code==order['customer_code']))
            assert customer
            peer=db.scalar(select(AuthUser).where(AuthUser.username=='engineer_peer'))
            db.add(CartonCustomerAssignment(customer_id=customer.id,user_id=peer.id,factory_id='huaxing'));db.commit()
        grant('engineer','sales-business',True);login_as(client,'engineer')
        a=ok(upload(client))
        assert not ok(client.get(BASE+'/candidates',params={**F,'owner_department':'sales-business','contract_number':order['contract_no']}))['items']
        # A legacy ORDER_BOUND source must still check the chosen customer's owner.
        with SessionLocal() as db:
            db.execute(delete(CartonAuditEvent).where(CartonAuditEvent.entity_id==a['id'],CartonAuditEvent.event_type=='CARTON_MARK_ASSET_SHARED'));db.commit()
        assert client.put('/api/carton-mark/assets/'+a['id']+'/binding',params=F,
            json=dict(revision=a['revision'],order_id=order['id'])).status_code==403
        assert not ok(client.get(BASE+'/'+a['id'],params=F))['targets']
        login_as(client,'admin')
        evidence=ok(client.post(BASE,params=F,data={'metadata':json.dumps(dict(request_id=uuid4().hex,
            owner_department='sales-business',purpose='EVIDENCE'))},files={'file':('evidence.png',photo_bytes(),'image/png')}))
        revision=ok(client.post('/api/carton-mark/assets/batch',data={**F,'options_json':json.dumps([dict(owner_department='sales-business',status='PENDING',
            previous_asset_id=evidence['id'],previous_revision=evidence['revision'])])},files=[('files',('revision.png',photo_bytes(),'image/png'))]))[0]
        assert revision['status']=='created' and revision['asset']['asset_purpose']=='EVIDENCE'
        # Strip v1 target audit to emulate a migration-backfilled supplier asset.
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        supplier_login(client)
        supplier_order=ok(client.get('/api/carton-supplier/carton-mark/upload-orders',params=F))[0]
        saved=ok(client.post('/api/carton-supplier/carton-mark/assets/upload',data={**F,'order_id':order['id'],'issue_id':supplier_order['issue_id']},
            files=[('files',('old-supplier.png',photo_bytes(color='blue'),'image/png'))]))[0]
        assert saved['status']=='created',saved
        identifier=saved['asset']['id']
        with SessionLocal() as db:
            db.execute(delete(CartonAuditEvent).where(CartonAuditEvent.entity_id==identifier,CartonAuditEvent.event_type=='CARTON_ASSET_TARGETS_V1'));db.commit()
        login_as(client,'admin')
        assert ok(client.get(BASE+'/'+identifier,params=F))['targets'][0]['id']==order['id']
        with SessionLocal() as db:
            db.get(CartonOrder,order['id']).customer_code='OTHER-CUSTOMER';db.commit()
        assert not ok(client.get(BASE+'/'+identifier,params={**F,'supplier_view':True}))['targets']
        login_as(client,'admin');ordinary=ok(upload(client))
        # Confirmation is a separate authority: it need not grant management.
        grant_permission_override('engineer_peer','carton_asset:read',factory_id='huaxing',department='sales-business')
        grant_permission_override('engineer_peer','carton_asset:confirm',factory_id='huaxing',department='sales-business')
        grant_permission_override('engineer_peer','carton_asset:manage',factory_id='huaxing',department='sales-business',effect='deny')
        login_as(client,'engineer_peer')
        ordinary=ok(action(client,ordinary,'READY'))
        assert action(client,ordinary,'DRAFT').status_code==403
