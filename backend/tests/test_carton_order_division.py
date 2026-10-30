from decimal import Decimal
from uuid import uuid4

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _order_payload
from test_carton_supplier_portal import setup_portal, supplier_login, ship_payload, receive_payload

BASE = '/api/carton-procurement'
SUP = '/api/carton-supplier'


def command(order, *, full=False):
    return dict(factory_id='huaxing', expected_revision=order['revision'], request_id=uuid4().hex,
        reason='客户要求拆分独立订单', targets=[dict(contract_no='SC700145366', customer_po='DIVISION',
        product_quantity='3600' if full else '1200', due_date='2026-09-30',
        lines=[dict(order_line_id=p['id'], quantity=str(Decimal(p['required_quantity']) / (1 if full else 3))) for p in order['lines']])])


def divide(client, order, body=None):
    return client.post(BASE+f"/orders/{order['order_no']}/independent-splits", json=body or command(order))


def rows(client):
    return client.get(BASE+'/orders', params={'factory_id': 'huaxing'}).json()['items']


def test_unissued_division_creates_two_normal_orders_without_supplier_tasks(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        source = _create_order(client, submit_supplier=False)
        body = command(source)
        result = divide(client, source, body)
        assert result.status_code == 201, result.text
        assert not result.json()['supplier_notified']
        assert client.post(BASE+f"/orders/{source['order_no']}/print-splits", json={**body, 'print_changed':False}).status_code == 409
        assert divide(client, source, body).json()['id'] == result.json()['id']
        assert divide(client, source, {**body, 'request_id': uuid4().hex}).status_code == 409
        orders = rows(client)
        assert len(orders) == 2
        parent = next(o for o in orders if o['id'] == source['id'])
        child = next(o for o in orders if o['id'] != source['id'])
        assert parent['product_order_quantity'] == '2400.000000'
        assert Decimal(child['product_order_quantity']) == 1200
        assert {o['status'] for o in orders} == {'CONFIRMED'}
        assert {o['supplier_acceptance']['status'] for o in orders} == {'NOT_ISSUED'}
        assert child['order_split']['source_order_no'] == source['order_no']
        assert not child['print_split'] and not child['split_records']
        assert set(p['id'] for p in parent['lines']).isdisjoint(p['id'] for p in child['lines'])
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue, CartonInventoryMovement
        from sqlalchemy import select
        with SessionLocal() as db:
            assert not list(db.scalars(select(CartonPurchaseOrderIssue)))
            assert not list(db.scalars(select(CartonInventoryMovement)))
        # Subsequent changes are ordinary child changes, not source-order callbacks.
        updated = client.patch(BASE+f"/orders/{child['order_no']}", json={**_order_payload(),
            'expected_revision': child['revision'], 'reason': '子单独立维护测试', 'contract_no': child['contract_no'],
            'customer_po': child['customer_po'], 'product_order_quantity': '1200', 'note': '只修改子单备注'})
        assert updated.status_code == 200, updated.text
        assert next(o for o in rows(client) if o['id'] == source['id'])['note'] == source['note']


def test_issued_division_uses_regular_changes_and_independent_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        source = setup_portal(client)
        login_as(client, 'admin')
        result = divide(client, source)
        assert result.status_code == 201, result.text
        assert result.json()['supplier_notified']
        assert len(rows(client)) == 2  # Materialized before any supplier response.
        supplier_login(client)
        tasks = client.get(SUP+'/changes', params={'factory_id':'huaxing'}).json()['items']
        assert len(tasks) == 2 and all(t['source_kind'] == 'REGULAR' and t['pending'] for t in tasks)
        assert {t['action'] for t in tasks} == {'REDUCE', 'INITIAL'}
        for index, task in enumerate(tasks):
            body = dict(factory_id='huaxing', source_kind='REGULAR', source_id=task['source_id'],
                expected_revision=task['expected_revision'], request_id=uuid4().hex, action='READ')
            read = client.post(SUP+'/changes/respond', json=body)
            assert read.status_code == 200 and read.json()['pending']
            response = client.post(SUP+'/changes/respond', json={**body, 'request_id':uuid4().hex,
                'action':'ACCEPT', 'promised_date':f'2026-09-{28+index}'})
            assert response.status_code == 200, response.text
        workspace = client.get(SUP+'/workspace', params={'factory_id':'huaxing'}).json()['orders']
        child = next(o for o in workspace if o['id'] != source['id'])
        assert child['order_split']['source_order_no'] == source['order_no']
        shipment = client.post(SUP+'/shipments', json=ship_payload(child))
        assert shipment.status_code == 201, shipment.text
        login_as(client, 'warehouse_keeper')
        receipt = client.post(SUP+f"/internal/shipments/{shipment.json()['id']}/receive", json=receive_payload(client, shipment.json()))
        assert receipt.status_code == 200, receipt.text
        orders = rows(client)
        parent = next(o for o in orders if o['id'] == source['id'])
        received = next(o for o in orders if o['id'] == child['id'])
        assert all(Decimal(p['received_quantity']) == 0 for p in parent['lines'])
        assert all(Decimal(p['received_quantity']) == 8 for p in received['lines'])
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonInventoryMovement
        from sqlalchemy import select
        with SessionLocal() as db:
            moves = list(db.scalars(select(CartonInventoryMovement)))
            assert moves and all(m.order_line_id in {p['id'] for p in child['lines']} for m in moves)
            assert all(m.quantity == 8 and m.quantity * m.unit_price == 16 for m in moves)


def test_division_rollback_and_explicit_partial_papers(monkeypatch):
    with make_client(monkeypatch) as client:
        source = setup_portal(client)
        login_as(client, 'admin')
        from app.services import carton_procurement as core
        original = core.create_purchase_order_issue
        calls = 0
        def fail(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                from fastapi import HTTPException
                raise HTTPException(409, '模拟子单发布失败')
            return original(*args, **kwargs)
        monkeypatch.setattr(core, 'create_purchase_order_issue', fail)
        assert divide(client, source).status_code == 409
        orders = rows(client)
        assert len(orders) == 1 and Decimal(orders[0]['product_order_quantity']) == 3600
        monkeypatch.setattr(core, 'create_purchase_order_issue', original)
        payload = {**_order_payload(), 'contract_no':'EXPLICIT-001', 'quantity_basis':'EXPLICIT', 'product_order_quantity':None}
        payload['lines'] = [{**p, 'required_quantity':'100'} for p in payload['lines']]
        created = client.post(BASE+'/orders', json=payload)
        assert created.status_code == 201, created.text
        order = created.json()
        body = command(order)
        body['targets'][0].update(contract_no='EXPLICIT-002', product_quantity=None,
            lines=[dict(order_line_id=order['lines'][1]['id'], quantity='20')])
        response = divide(client, order, body)
        assert response.status_code == 201, response.text
        child = next(o for o in rows(client) if o['contract_no']=='EXPLICIT-002')
        parent = next(o for o in rows(client) if o['id']==order['id'])
        assert len(child['lines']) == 1 and child['lines'][0]['packaging_type'] == order['lines'][1]['packaging_type']
        assert [Decimal(p['required_quantity']) for p in parent['lines']] == [100, 80]


def test_legacy_conversion_and_full_split_keep_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        source = setup_portal(client)
        login_as(client, 'admin')
        from test_carton_print_split import seed_legacy_split
        identifier, target = seed_legacy_split(source)
        body = command(source)
        body.update(legacy_splits={identifier:1})
        body['targets'][0]['customer_po'] = target['customer_po']
        assert divide(client, source).status_code == 409
        response = divide(client, source, body)
        assert response.status_code == 201, response.text
        parent = next(o for o in rows(client) if o['id']==source['id'])
        assert parent['split_records'][0]['status'] == 'CANCELLED'
        full = command(parent)
        full['targets'][0].update(contract_no='FULL-CHILD', product_quantity=parent['product_order_quantity'],
            lines=[dict(order_line_id=p['id'], quantity=p['required_quantity']) for p in parent['lines']])
        response = divide(client, parent, full)
        assert response.status_code == 201, response.text
        supplier_login(client)
        tasks = client.get(SUP+'/changes', params={'factory_id':'huaxing'}).json()['items']
        cancelled = next(t for t in tasks if t['order_id']==source['id'])
        assert cancelled['is_cancellation'] and cancelled['pending']
        response = client.post(SUP+'/changes/respond', json=dict(factory_id='huaxing', source_kind='REGULAR',
            source_id=cancelled['source_id'], expected_revision=cancelled['expected_revision'], request_id=uuid4().hex, action='ACK_CANCEL'))
        assert response.status_code == 200, response.text
        assert client.get(BASE+f"/orders/{source['order_no']}/independent-splits", params={'factory_id':'huaxing'}).status_code == 403


def test_material_links_are_automatic_and_stock_and_scope_are_protected(monkeypatch):
    with make_client(monkeypatch) as client:
        source = setup_portal(client)
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset, CartonMarkAssetOrderBinding
        from app.models.auth import AuthUser
        from sqlalchemy import select
        import hashlib
        with SessionLocal() as db:
            actor = db.scalar(select(AuthUser).where(AuthUser.username=='admin'))
            data = b'%PDF-1.4 division test'
            asset = CartonMarkAsset(id='DIVISION-MATERIAL', factory_id='huaxing', kind='pdf', file_name='original.pdf',
                content_type='application/pdf', size_bytes=len(data), content=data, sha256=hashlib.sha256(data).hexdigest(),
                revision=1, recognition_source='manual_orders', asset_purpose='MATERIAL', owner_department='pmc-warehouse',
                created_by=actor.id, created_by_name=actor.display_name, created_at='2026-10-30', updated_at='2026-10-30',
                order_bindings=[CartonMarkAssetOrderBinding(factory_id='huaxing', order_id=source['id'])])
            db.add(asset)
            db.flush()
            from app.services import carton_asset_targets as targets, carton_procurement as core
            core._audit(db, actor, 'huaxing', targets.EVENT, 'carton_mark_asset', asset.id,
                {'targets':targets.legacy_targets(db,asset,current_authorized=True)})
            db.commit()
        wrong = {**command(source), 'factory_id':'huadeng'}
        assert divide(client, source, wrong).status_code in {403,404}
        result = divide(client, source)
        assert result.status_code == 201, result.text
        child_id = next(m['order_id'] for m in result.json()['members'] if m['role']=='CHILD')
        with SessionLocal() as db:
            from app.services import carton_mark_assets as assets
            asset = db.get(CartonMarkAsset, 'DIVISION-MATERIAL')
            assert {o.id for o in assets.matching_asset_orders(asset, assets.available_orders(db, 'huaxing'))} == {source['id'], child_id}
        supplier_login(client)
        assert divide(client, source).status_code == 403
        login_as(client, 'admin')
        parent = next(o for o in rows(client) if o['id']==source['id'])
        from test_carton_print_split import seed_legacy_split
        # Seed integer historical quantities from the original demand (one third
        # of the remaining parent would be fractional for this counting unit).
        identifier, target = seed_legacy_split(source, stock=True)
        body = command(source)
        body['expected_revision'] = parent['revision']
        body.update(legacy_splits={identifier:1})
        body['targets'][0].update(contract_no=target['contract_no'], customer_po=target['customer_po'])
        rejected = divide(client, parent, body)
        assert rejected.status_code == 409 and '库存分配' in rejected.text, rejected.text


def test_split_all_unreceived_demand_preserves_receipts_and_allows_reduction_ack(monkeypatch):
    from test_carton_order_split import receive
    with make_client(monkeypatch) as client:
        source = setup_portal(client)
        login_as(client, 'warehouse_keeper')
        received = {p['id']: Decimal(p['required_quantity']) / 3 for p in source['lines']}
        for paper in source['lines']:
            response = receive(client, {**source, 'lines':[paper]}, str(received[paper['id']]))
            assert response.status_code == 201, response.text
        parent = rows(client)[0]
        body = command(parent)
        body['targets'][0].update(product_quantity='2400',
            lines=[dict(order_line_id=p['id'], quantity=str(Decimal(p['required_quantity']) - received[p['id']])) for p in parent['lines']])
        result = divide(client, parent, body)
        assert result.status_code == 201, result.text
        parent = next(o for o in rows(client) if o['id'] == source['id'])
        assert parent['status'] == 'PARTIALLY_RECEIVED'
        assert all(Decimal(p['required_quantity']) == Decimal(p['received_quantity']) == received[p['id']] for p in parent['lines'])
        supplier_login(client)
        tasks = client.get(SUP+'/changes', params={'factory_id':'huaxing'}).json()['items']
        task = next(t for t in tasks if t['order_id'] == source['id'])
        response = client.post(SUP+'/changes/respond', json=dict(factory_id='huaxing', source_kind='REGULAR',
            source_id=task['source_id'], expected_revision=task['expected_revision'], action='ACCEPT',
            promised_date='2026-09-30', request_id=uuid4().hex))
        assert response.status_code == 200, response.text
        login_as(client, 'warehouse_keeper')
        parent = next(o for o in rows(client) if o['id'] == source['id'])
        assert parent['status'] == 'COMPLETED'
        assert all(Decimal(p['received_quantity']) == received[p['id']] for p in parent['lines'])
