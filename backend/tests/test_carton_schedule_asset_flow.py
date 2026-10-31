"""Sales schedule -> warehouse purchase -> supplier source visibility, isolated DB."""
from uuid import uuid4
from test_carton_asset_quick import BASE,F,ok,upload,action,enable,schedule
from test_molding_sample_api import make_client,login_as
from test_carton_item_schedule import source_row
from test_carton_supplier_portal import setup_portal,supplier_login,grant_supplier_permissions
from test_carton_procurement_api import _order_payload,_submit_order


def test_schedule_asset_follows_explicit_purchase_and_current_supplier_issue(monkeypatch):
    with make_client(monkeypatch) as client:
        unrelated=setup_portal(client)
        grant_supplier_permissions(permissions=('carton_asset:read','carton_asset:manage'))
        login_as(client,'admin');enable(monkeypatch)
        batch=schedule(client,[source_row(),source_row(contract='UNORDERED',item='ITEM-2')])
        def candidates(asset=''):
            return ok(client.get(BASE+'/candidates',params={**F,'owner_department':'sales-business',
                'target_scope':'PENDING_SCHEDULE','asset_id':asset}))['items']
        rows=candidates();assert len(rows)==2 and all(x['kind']=='SCHEDULE' and not x['ordered'] for x in rows)
        target=next(x for x in rows if x['contract_no']=='53135')
        ref={k:target[k] for k in ('kind','id','sheet','row','fingerprint')}
        asset=ok(upload(client,contract_number='53135',target_scope='PENDING_SCHEDULE'))
        assert len(asset['targets'])==1
        def marks():return ok(client.get('/api/carton-mark/assets/schedule',params={**F,'batch_id':batch['id']}))['rows']
        assert any(asset['id'] in r['asset_ids'] and r['pending_count']==1 for r in marks())
        supplier_login(client)
        assert client.get(BASE+'/'+asset['id'],params={**F,'supplier_view':True}).status_code==404
        login_as(client,'admin')
        payload={**_order_payload(),'contract_no':'53135','item_no':'0040220-1','customer_po':'0989551378',
            'product_order_quantity':360,'customer_due_date':'2026-09-17',
            'schedule_source':{'batch_id':batch['id'],'source_sheet':target['sheet'],'source_row':target['row']}}
        order=ok(client.post('/api/carton-procurement/orders',json=payload))
        assert len(candidates())==1
        assert any(x['ordered'] for x in candidates(asset['id']))
        stale=upload(client,association='MANUAL',targets=[ref],target_scope='PENDING_SCHEDULE')
        assert stale.status_code==404
        assert any(asset['id'] in r['asset_ids'] for r in marks())
        # Existing associations remain editable after procurement.
        asset=ok(client.post(BASE+'/'+asset['id']+'/associations',params=F,json=dict(
            revision=asset['revision'],request_id=uuid4().hex,targets=[ref],target_scope='PENDING_SCHEDULE')))
        supplier_login(client)
        assert client.get(BASE+'/'+asset['id'],params={**F,'supplier_view':True}).status_code==404
        login_as(client,'admin')
        # Submit creates the current issued snapshot; exporting Excel is optional.
        order=_submit_order(client,order)
        def supplier_assets():return ok(client.get('/api/carton-supplier/carton-mark/assets',params=F))
        supplier_login(client)
        shown=next(x for x in supplier_assets() if x['id']==asset['id'])
        assert [o['id'] for o in shown['orders']]==[order['id']]
        assert unrelated['id'] not in [o['id'] for o in shown['orders']]
        assert shown['workflow']['status']=='PENDING'
        assert client.get('/api/carton-supplier/carton-mark/assets/'+asset['id']+'/document',params=F).status_code==200
        login_as(client,'admin');asset=ok(action(client,asset,'READY'))
        # Removing a row from a later schedule does not erase explicit purchase provenance.
        schedule(client,[source_row(contract='UNORDERED',item='ITEM-2')])
        retained=candidates(asset['id'])
        assert any(x['contract_no']=='53135' and x['ordered'] for x in retained)
        supplier_login(client)
        assert next(x for x in supplier_assets() if x['id']==asset['id'])['workflow']['status']=='READY'
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            db.get(CartonOrder,order['id']).customer_po='DIFFERENT-ORDER';db.commit()
        assert client.get(BASE+'/'+asset['id'],params={**F,'supplier_view':True}).status_code==404
        assert asset['id'] not in {x['id'] for x in supplier_assets()}


def test_duplicate_current_schedule_selection_is_exact_not_silently_lost(monkeypatch):
    from test_carton_item_schedule import _prepare_schedule_customer
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client);login_as(client,'admin');enable(monkeypatch)
        batch=schedule(client,[source_row(),source_row()])
        rows=ok(client.get(BASE+'/candidates',params={**F,'target_scope':'PENDING_SCHEDULE','owner_department':'sales-business'}))['items']
        ref={k:rows[1][k] for k in ('kind','id','sheet','row','fingerprint')}
        asset=ok(upload(client,association='MANUAL',targets=[ref],target_scope='PENDING_SCHEDULE'))
        assert len(asset['targets'])==1 and asset['targets'][0]['row']==ref['row']
        marks=ok(client.get('/api/carton-mark/assets/schedule',params={**F,'batch_id':batch['id']}))['rows']
        assert sum(asset['id'] in r['asset_ids'] for r in marks)==1
        ok(client.post('/api/carton-procurement/schedule-order-marks',json={**F,'batch_id':batch['id'],
            'source_sheet':rows[0]['sheet'],'source_row':rows[0]['row'],'marked':True}))
        current=ok(client.get(BASE+'/candidates',params={**F,'target_scope':'PENDING_SCHEDULE','owner_department':'sales-business'}))['items']
        assert len(current)==1 and current[0]['row']==ref['row']


def test_sales_schedule_link_does_not_require_warehouse_customer_assignment(monkeypatch):
    from test_carton_item_schedule import _prepare_schedule_customer
    from test_carton_asset_quick import grant
    from test_molding_sample_api import grant_permission_override
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client);login_as(client,'admin');enable(monkeypatch)
        schedule(client,[source_row()])
        grant('engineer','sales-business')
        login_as(client,'engineer')
        params={**F,'owner_department':'sales-business','target_scope':'PENDING_SCHEDULE'}
        # Warehouse fixture already assigns this customer to warehouse staff.
        assert not ok(client.get(BASE+'/candidates',params=params))['items']
        grant_permission_override('engineer','customer_order:read',factory_id='huaxing',department='sales-business')
        login_as(client,'engineer')
        rows=ok(client.get(BASE+'/candidates',params=params))['items']
        assert len(rows)==1
        ref={k:rows[0][k] for k in ('kind','id','sheet','row','fingerprint')}
        asset=ok(upload(client,association='MANUAL',targets=[ref],target_scope='PENDING_SCHEDULE'))
        assert len(asset['targets'])==1
        assert client.get('/api/carton-procurement/orders',params=F).status_code==403
        assert client.get(BASE+'/candidates',params={**params,'factory_id':'huakang-a'}).status_code==403
        grant_permission_override('engineer','customer_order:read',factory_id='huaxing',department='sales-business',effect='deny')
        login_as(client,'engineer')
        assert not ok(client.get(BASE+'/candidates',params=params))['items']
        assert upload(client,association='MANUAL',targets=[ref],target_scope='PENDING_SCHEDULE').status_code==404
