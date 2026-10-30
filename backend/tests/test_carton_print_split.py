from decimal import Decimal
from uuid import uuid4
import hashlib
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, ship_payload

BASE = '/api/carton-procurement'
SUP = '/api/carton-supplier'


def legacy_post(route, *, json):
    """Construct pre-upgrade proposals only; current HTTP creation is retired."""
    from types import SimpleNamespace
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services import carton_print_split as service
    from app.schemas.carton_print_split import PrintSplitCreate, PrintSplitAction
    with SessionLocal() as db:
        actor = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == 'admin')))
        try:
            if '/orders/' in route:
                result = service.create(db, route.split('/orders/')[1].split('/')[0], PrintSplitCreate(**json), actor)
                status = 201
            else:
                identifier, action = route.split('/print-splits/')[1].split('/')
                result = service.act(db, identifier, action, PrintSplitAction(**json), actor)
                status = 200
            return SimpleNamespace(status_code=status, text=str(result), json=lambda: result)
        except HTTPException as exc:
            db.rollback()
            return SimpleNamespace(status_code=exc.status_code, text=str(exc.detail))


def seed_legacy_split(order, *, stock=False):
    """Persist a pre-upgrade allocation; the retired HTTP write is not used."""
    from app.db import SessionLocal
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services import carton_procurement as core
    from sqlalchemy import select
    identifier = 'CS-legacy-' + uuid4().hex
    target = dict(contract_no='SC700145366', customer_po='LEGACY', product_quantity='1200',
        lines=[dict(order_line_id=p['id'], target_line_id='CSL-'+uuid4().hex,
            pending_quantity=str(Decimal(p['required_quantity'])/3), stock=[dict(location_id='old',quantity='1')] if stock else [],
            packaging_type=p['packaging_type'], paper_quality=p['paper_quality'], specification=p['specification'],
            unit=p['unit'], dimension_unit='') for p in order['lines']])
    with SessionLocal() as db:
        actor=build_auth_context(db,db.scalar(select(AuthUser).where(AuthUser.username=='admin')))
        core._audit(db,actor,'huaxing','ORDER_SPLIT_CREATED','carton_order_split',identifier,{'plan':dict(
            id=identifier,order_id=order['id'],order_no=order['order_no'],factory_id='huaxing',status='ACTIVE',
            customer_code=order['customer_code'],customer_name=order['customer_name'],item_no=order['item_no'],
            original_contract_no=order['contract_no'],supplier_id=order['supplier_id'],reason='历史数量分配',targets=[target])})
        db.commit()
    return identifier, target


def test_same_print_legacy_conversion_creates_real_child_and_independent_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        original=setup_portal(client)
        login_as(client,'admin')
        identifier,target=seed_legacy_split(original)
        from test_carton_order_split import receive
        blocked=receive(client,original,'1')
        assert blocked.status_code==409 and '独立订单' in blocked.text
        body=dict(factory_id='huaxing',request_id=uuid4().hex,expected_revision=original['revision'],
            reason='旧分配转为独立订单',print_changed=False,legacy_splits={identifier:1},original_asset_ids=[],
            targets=[dict(contract_no=target['contract_no'],customer_po=target['customer_po'],product_quantity=target['product_quantity'],
                due_date='2026-09-30',asset_ids=[],lines=[dict(order_line_id=l['order_line_id'],quantity=l['pending_quantity']) for l in target['lines']])])
        route=BASE+f"/orders/{original['order_no']}/print-splits"
        stale=legacy_post(route,json={**body,'legacy_splits':{identifier:2}})
        assert stale.status_code==409
        created=legacy_post(route,json=body)
        assert created.status_code==201,created.text
        plan=act(client,created.json(),'send')
        supplier_login(client)
        # Same print may already be produced in full; no print-change cap at retained qty.
        response,command=respond(client,plan,produced_quantities={p['id']:p['before_quantity'] for p in plan['papers']})
        assert response.status_code==200,response.text
        assert client.post(SUP+'/changes/respond',json=command).status_code==200
        rows=client.get(SUP+'/workspace',params={'factory_id':'huaxing'}).json()['orders']
        parent=next(r for r in rows if r['id']==original['id']);child=next(r for r in rows if r['id']!=original['id'])
        assert [Decimal(p['required_quantity']) for p in parent['lines']]==[Decimal(p['required_quantity'])*2/3 for p in original['lines']]
        assert [Decimal(p['required_quantity']) for p in child['lines']]==[Decimal(p['required_quantity'])/3 for p in original['lines']]
        assert child['print_split']['print_changed'] is False
        shipped=client.post(SUP+'/shipments',json=ship_payload(child))
        assert shipped.status_code==201,shipped.text
        from test_carton_supplier_portal import receive_payload
        login_as(client,'warehouse_keeper')
        received=client.post(SUP+f"/internal/shipments/{shipped.json()['id']}/receive",json=receive_payload(client,shipped.json()))
        assert received.status_code==200,received.text
        orders=client.get(BASE+'/orders',params={'factory_id':'huaxing'}).json()['items']
        saved_parent=next(r for r in orders if r['id']==parent['id']);saved_child=next(r for r in orders if r['id']==child['id'])
        assert all(Decimal(p['received_quantity'])==0 for p in saved_parent['lines'])
        assert all(Decimal(p['received_quantity'])==8 for p in saved_child['lines'])
        assert all(p['status']=='CANCELLED' for p in saved_parent['split_records'])


def test_legacy_conversion_does_not_rewrite_stock_or_hide_failed_transaction(monkeypatch):
    with make_client(monkeypatch) as client:
        original=setup_portal(client);login_as(client,'admin')
        identifier,target=seed_legacy_split(original)
        body=dict(factory_id='huaxing',request_id=uuid4().hex,expected_revision=original['revision'],
            reason='旧分配转为独立订单',print_changed=False,legacy_splits={identifier:1},original_asset_ids=[],
            targets=[dict(contract_no=target['contract_no'],customer_po=target['customer_po'],product_quantity=target['product_quantity'],
                due_date='2026-09-30',asset_ids=[],lines=[dict(order_line_id=l['order_line_id'],quantity=l['pending_quantity']) for l in target['lines']])])
        created=legacy_post(BASE+f"/orders/{original['order_no']}/print-splits",json=body);assert created.status_code==201,created.text
        plan=act(client,created.json(),'send');supplier_login(client)
        from app.services import carton_procurement as core
        from fastapi import HTTPException
        def fail(*args,**kwargs): raise HTTPException(409,'模拟子单生成失败')
        with monkeypatch.context() as m:
            m.setattr(core,'create_order',fail)
            failed,_=respond(client,plan)
            assert failed.status_code==409
        login_as(client,'admin')
        context=client.get(BASE+f"/orders/{original['order_no']}/splits",params={'factory_id':'huaxing'}).json()
        assert context['plans'][0]['status']=='ACTIVE'
        assert context['revision']==original['revision']
        assert [Decimal(l['required_quantity']) for l in context['lines']]==[Decimal(l['required_quantity']) for l in original['lines']]
        # Retired API cannot create additional virtual rows even on a stale browser.
        from test_carton_order_split import split_body
        old=client.post(BASE+f"/orders/{original['order_no']}/splits",json=split_body(original))
        assert old.status_code==409 and '停用' in old.text


def test_same_print_inherits_bound_files_and_rejects_false_print_change(monkeypatch):
    with make_client(monkeypatch) as client:
        order,_=prepare(client)
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkAssetOrderBinding
        with SessionLocal() as db:
            asset = db.get(CartonMarkAsset, 'PRINT-A')
            asset.recognition_source = 'manual_orders'
            asset.order_bindings.append(CartonMarkAssetOrderBinding(factory_id='huaxing',order_id=order['id']))
            db.flush()
            from app.services import carton_asset_targets as targets, carton_procurement as core
            from app.models.auth import AuthUser
            # Owned originals require an audited identity snapshot; a naked
            # foreign key alone intentionally does not authorize association.
            core._audit(db, db.get(AuthUser, asset.created_by), 'huaxing', targets.EVENT,
                'carton_mark_asset', asset.id, {'targets':targets.legacy_targets(db,asset,current_authorized=True)})
            db.commit()
        body=dict(factory_id='huaxing',request_id=uuid4().hex,expected_revision=order['revision'],
            reason='相同印刷拆为独立单',print_changed=False,original_asset_ids=[],targets=[dict(
                contract_no='SC700145366',customer_po='SAME',product_quantity='1200',due_date='2026-09-30',asset_ids=[],
                lines=[dict(order_line_id=p['id'],quantity=str(Decimal(p['required_quantity'])/3)) for p in order['lines']])])
        route=BASE+f"/orders/{order['order_no']}/print-splits"
        wrong={**body,'targets':[{**body['targets'][0],'asset_ids':['PRINT-B']}]}
        assert legacy_post(route,json=wrong).status_code==422
        created=legacy_post(route,json=body)
        assert created.status_code==201,created.text
        assert [f['id'] for f in created.json()['original_files']]==['PRINT-A']
        assert created.json()['targets'][0]['files']==created.json()['original_files']
        # Stock-bearing legacy histories must not be silently recast as new demand.
        identifier,target=seed_legacy_split(order,stock=True)
        blocked=legacy_post(route,json={**body,'request_id':uuid4().hex,'legacy_splits':{identifier:1},
            'targets':[{**body['targets'][0],'customer_po':target['customer_po']}]})
        assert blocked.status_code==409 and '库存分配' in blocked.text


def prepare(client, *, full=False):
    order = setup_portal(client)
    login_as(client, 'admin')
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    from app.models.auth import AuthUser
    from sqlalchemy import select
    with SessionLocal() as db:
        actor = db.scalar(select(AuthUser).where(AuthUser.username == 'admin'))
        for name in ['A', 'B']:
            content = b'%PDF-1.4 print ' + name.encode()
            db.add(CartonMarkAsset(id='PRINT-' + name, factory_id='huaxing', kind='pdf',
                file_name=name + '.pdf', content_type='application/pdf', size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(), content=content, revision=1,
                created_by=actor.id, created_by_name=actor.display_name, created_at='2026-08-05',
                updated_at='2026-08-05', owner_department='pmc-warehouse', asset_purpose='MATERIAL'))
        db.commit()
    body = dict(factory_id='huaxing', request_id=uuid4().hex, expected_revision=order['revision'],
        reason='客户要求更换拆单印刷', original_asset_ids=['PRINT-A'], targets=[dict(
            contract_no='SC700145366', customer_po='PRINT-B', product_quantity='3600' if full else '1200', due_date='2026-09-30',
            asset_ids=['PRINT-B'], lines=[dict(order_line_id=p['id'], quantity=str(Decimal(p['required_quantity']) / (1 if full else 3)))
                for p in order['lines']])])
    response = legacy_post(BASE + f"/orders/{order['order_no']}/print-splits", json=body)
    assert response.status_code == 201, response.text
    plan = response.json()
    assert legacy_post(BASE + f"/orders/{order['order_no']}/print-splits", json=body).json()['id'] == plan['id']
    return order, plan


def act(client, plan, action):
    result = legacy_post(BASE + f"/print-splits/{plan['id']}/{action}", json=dict(
        factory_id='huaxing', request_id=uuid4().hex, expected_revision=plan['revision'], reason='核对印刷拆单方案'))
    assert result.status_code == 200, result.text
    return result.json()


def respond(client, plan, action='ACCEPT', **changes):
    body = dict(factory_id='huaxing', source_kind='PRINT', source_id=plan['id'],
        expected_revision=plan['revision'], request_id=uuid4().hex, action=action,
        promised_date='2026-09-30', produced_quantities={p['id']: '0' for p in plan['papers']})
    body.update(changes)
    return client.post(SUP + '/changes/respond', json=body), body


def test_print_split_materializes_once_and_child_ships_own_fixed_version(monkeypatch):
    with make_client(monkeypatch) as client:
        original, plan = prepare(client)
        plan = act(client, plan, 'send')
        supplier_login(client)
        task = next(t for t in client.get(SUP+'/changes', params={'factory_id':'huaxing'}).json()['items'] if t['source_kind']=='PRINT')
        assert task['pending'] and task['print_split']['targets'][0]['files'][0]['file_name']=='B.pdf'
        workspace = client.get(SUP+'/workspace', params={'factory_id':'huaxing'}).json()
        assert workspace['orders'][0]['lines'][0]['shipping_blocked_reason']
        response, body = respond(client, plan)
        assert response.status_code == 200, response.text
        assert client.post(SUP+'/changes/respond', json=body).status_code == 200
        rows = client.get(SUP+'/workspace', params={'factory_id':'huaxing'}).json()['orders']
        assert len(rows)==2
        parent = next(r for r in rows if r['id']==original['id'])
        child = next(r for r in rows if r['id']!=original['id'])
        assert Decimal(parent['lines'][0]['required_quantity'])==20
        assert Decimal(child['lines'][0]['required_quantity'])==10
        assert child['print_split']['role']=='CHILD'
        assert child['lines'][0]['id']!=parent['lines'][0]['id']
        file = client.get(SUP+f"/print-splits/{plan['id']}/files/PRINT-B", params={'factory_id':'huaxing'})
        assert file.status_code==200 and file.content.endswith(b'B')
        shipped=client.post(SUP+'/shipments', json=ship_payload(child))
        assert shipped.status_code==201, shipped.text
        from test_carton_supplier_portal import receive_payload
        login_as(client, 'warehouse_keeper')
        receipt=client.post(SUP+f"/internal/shipments/{shipped.json()['id']}/receive", json=receive_payload(client,shipped.json()))
        assert receipt.status_code==200, receipt.text
        from app.db import SessionLocal
        from app.models.carton_supplier_portal import SupplierShipmentLine
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            line=db.scalar(select(SupplierShipmentLine).where(SupplierShipmentLine.shipment_id==shipped.json()['id']))
            assert json.loads(line.snapshot_json)['file_manifest'][0]['asset_id']=='PRINT-B'
            from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
            received=list(db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id==receipt.json()['receipt_id'])))
            child_ids={p['id'] for p in child['lines']}
            assert {p.order_line_id for p in received}==child_ids
            movements=list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.order_line_id.in_(child_ids))))
            assert movements and all(m.quantity==8 and m.quantity*m.unit_price==16 for m in movements)
            assert not list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.order_line_id.in_([p['id'] for p in parent['lines']]))))

        login_as(client,'admin')
        current=next(o for o in client.get(BASE+'/orders',params={'factory_id':'huaxing'}).json()['items'] if o['id']==child['id'])
        again=dict(factory_id='huaxing',request_id=uuid4().hex,expected_revision=current['revision'],reason='再次拆出不同印刷',original_asset_ids=['PRINT-A'],targets=[dict(contract_no='SC700145367',customer_po='AGAIN',product_quantity='240',due_date='2026-09-30',asset_ids=['PRINT-A'],lines=[dict(order_line_id=p['id'],quantity=str(Decimal(p['required_quantity'])/5)) for p in current['lines']])])
        wrong=legacy_post(BASE+f"/orders/{child['order_no']}/print-splits",json=again)
        assert wrong.status_code==409 and '沿用固定原件' in wrong.text
        with SessionLocal() as db:
            from app.models.carton_mark import CartonMarkAsset
            db.get(CartonMarkAsset,'PRINT-B').is_archived=True
            db.commit()
        same=legacy_post(BASE+f"/orders/{child['order_no']}/print-splits",json={**again,'request_id':uuid4().hex,'original_asset_ids':['PRINT-B']})
        assert same.status_code==201,same.text
        # An archived fixed version is inherited, never silently upgraded or lost.
        act(client,same.json(),'send')


def test_print_dispute_and_withdraw_require_supplier_release(monkeypatch):
    with make_client(monkeypatch) as client:
        order, plan=prepare(client)
        plan=act(client,plan,'send')
        supplier_login(client)
        response,_=respond(client,plan,'DISPUTE',reason='已经印刷超过保留量')
        assert response.status_code==200, response.text
        plan=response.json()['print_split']
        login_as(client,'admin')
        plan=act(client,plan,'withdraw')
        assert plan['status']=='WITHDRAWING'
        supplier_login(client)
        response,_=respond(client,plan,'ACK_CANCEL')
        assert response.status_code==200, response.text
        assert response.json()['print_split']['status']=='CANCELLED'
        rows=client.get(SUP+'/workspace',params={'factory_id':'huaxing'}).json()['orders']
        assert len(rows)==1 and Decimal(rows[0]['lines'][0]['required_quantity'])==30
        assert not rows[0]['lines'][0]['shipping_blocked_reason']


def test_acceptance_failure_rolls_back_all_members(monkeypatch):
    with make_client(monkeypatch) as client:
        order,plan=prepare(client)
        plan=act(client,plan,'send')
        supplier_login(client)
        from app.services import carton_procurement as core
        original=core.create_purchase_order_issue
        count=0
        def fail(*args,**kwargs):
            nonlocal count
            count+=1
            if count==2:
                from fastapi import HTTPException
                raise HTTPException(409,'模拟子单发布失败')
            return original(*args,**kwargs)
        monkeypatch.setattr(core,'create_purchase_order_issue',fail)
        response,_=respond(client,plan)
        assert response.status_code==409, response.text
        rows=client.get(SUP+'/workspace',params={'factory_id':'huaxing'}).json()['orders']
        assert len(rows)==1 and Decimal(rows[0]['lines'][0]['required_quantity'])==30
        assert rows[0]['print_split']['status']=='SENT'


def test_full_split_preserves_history_but_has_zero_original_demand(monkeypatch):
    with make_client(monkeypatch) as client:
        order,plan=prepare(client,full=True)
        plan=act(client,plan,'send')
        supplier_login(client)
        response,_=respond(client,plan)
        assert response.status_code==200,response.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonPurchaseOrderIssue
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            original=db.get(CartonOrder,order['id'])
            assert original.status=='CANCELLED' and original.product_order_quantity is None
            assert all(p.required_quantity==0 for p in db.scalars(select(CartonOrderLine).where(CartonOrderLine.order_id==order['id'])))
            snapshots=[json.loads(i.snapshot_json) for i in db.scalars(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id==order['id']))]
            assert any(Decimal(str(s.get('after_product_quantity') or 0))==3600 for s in snapshots)


def test_print_hold_and_production_capacity_and_fixed_file_integrity(monkeypatch):
    with make_client(monkeypatch) as client:
        order,plan=prepare(client)
        plan=act(client,plan,'send')
        # A competing purchase version cannot bypass the aggregate hold.
        r=client.post(BASE+f"/orders/{order['order_no']}/purchase-order-issues.xlsx",json={'factory_id':'huaxing','expected_revision':order['revision']})
        assert r.status_code==409,r.text
        from test_carton_order_split import receive
        blocked=receive(client,order,'1',post=False)
        assert blocked.status_code==409 and '印刷拆单' in blocked.text
        supplier_login(client)
        denied=client.get(BASE+f"/orders/{order['order_no']}/print-splits",params={'factory_id':'huaxing'})
        assert denied.status_code==403
        body=dict(factory_id='huaxing',source_kind='PRINT',source_id=plan['id'],expected_revision=plan['revision'],request_id=uuid4().hex,action='ACCEPT',promised_date='2026-09-30',produced_quantities={p['id']:p['before_quantity'] for p in plan['papers']})
        r=client.post(SUP+'/changes/respond',json=body)
        assert r.status_code==409 and '生产' in r.text
        assert client.post(SUP+'/changes/respond',json={**body,'request_id':''}).status_code==422
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset
        with SessionLocal() as db:
            db.get(CartonMarkAsset,'PRINT-B').content=b'corrupt'
            db.commit()
        r,_=respond(client,plan)
        assert r.status_code==409 and '固定印刷' in r.text
        assert client.get(SUP+'/workspace',params={'factory_id':'huaxing'}).json()['orders'][0]['print_split']['status']=='SENT'
        assert client.get(SUP+f"/print-splits/{plan['id']}/files/PRINT-A",params={'factory_id':'huakang_a'}).status_code!=200


def test_archived_workspace_version_can_be_explicitly_pinned(monkeypatch):
    monkeypatch.setenv('CARTON_MATERIALS_V2_WRITES_ENABLED','true')
    with make_client(monkeypatch) as client:
        order,old=prepare(client)
        from app.api.carton_materials import retired_writes
        client.app.dependency_overrides[retired_writes]=lambda:None
        import json
        from test_carton_item_schedule import workbook, source_row
        scope={'factory_id':'huaxing','audience':'warehouse'}
        r=client.post('/api/carton-materials',params=scope,json={'request_id':uuid4().hex,'target':{'kind':'PURCHASE','id':order['id']}})
        assert r.status_code==200,r.text
        folder=r.json()
        r=client.post('/api/carton-materials/'+folder['id']+'/versions',params=scope,data={'metadata':json.dumps({'revision':folder['revision'],'request_id':uuid4().hex,'title':'印刷原稿','role':'ORIGINAL'})},files={'file':('print.xlsx',workbook([source_row()]))})
        assert r.status_code==200,r.text
        candidates=client.get(BASE+f"/orders/{order['order_no']}/print-splits",params={'factory_id':'huaxing'})
        assert candidates.status_code==200,candidates.text
        file=next(f for f in candidates.json()['files'] if f['id'].startswith('CMVREF|'))
        body={**old['body'],'request_id':uuid4().hex,'original_asset_ids':[file['id']]}
        body['targets'][0]['asset_ids']=[file['id']]
        r=legacy_post(BASE+f"/orders/{order['order_no']}/print-splits",json=body)
        assert r.status_code==201,r.text
        plan=act(client,r.json(),'send')
        supplier_login(client)
        r,_=respond(client,plan)
        assert r.status_code==200,r.text
        download=client.get(SUP+f"/print-splits/{plan['id']}/files/{file['id']}",params={'factory_id':'huaxing'})
        assert download.status_code==200 and download.content.startswith(b'PK')
