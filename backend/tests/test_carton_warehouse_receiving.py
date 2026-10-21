from copy import deepcopy
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import select, func
from test_molding_sample_api import make_client, login_as
from test_carton_special_requests import setup, created, create_body, command, ok, BASE, FACTORY, isolated_database_directory


def batch(client, place):
    from app.db import SessionLocal
    from app.models.carton_master import CartonMasterRecord
    with SessionLocal() as db:
        db.add(CartonMasterRecord(id='batch-workshop', factory_id=FACTORY, kind='WORKSHOP', identity='batch-workshop', code='混合验收车间', data_json='{}', status='ACTIVE'))
        db.commit()
    sample_body = create_body(); sample_body['lines'][0]['mark_mode'] = 'PENDING'
    sample = ok(client.post(BASE, json=sample_body), 201)
    sample = ok(client.post(BASE + f"/{sample['id']}/confirm", json=command(sample)))
    body = create_body('WORKSHOP_MISC'); body['workshop_id'] = 'batch-workshop'
    misc = ok(client.post(BASE, json=body), 201)
    misc = ok(client.post(BASE + f"/{misc['id']}/confirm", json=command(misc)))
    order = ok(client.get('/api/carton-procurement/orders', params={'factory_id': FACTORY}))['items'][0]
    def allocation(): return [{'location_id': place['id'], 'quantity': '10'}]
    payload = command(delivery_note_no='WB-' + uuid4().hex[:16], delivery_date='2026-10-18', acceptance_date='2026-10-18',
        order_revisions={order['order_no']: order['revision']},
        formal_lines=[dict(source_type='FORMAL_ORDER', order_line_id=order['lines'][0]['id'], delivered_quantity='10', received_quantity='10', unit_price='1', location_allocations=allocation())],
        special_requests=[dict(id=row['id'], expected_revision=row['revision'], lines=[dict(line_id=row['lines'][0]['id'], received_quantity='10', unit_price=None, location_allocations=allocation())]) for row in (sample, misc)])
    return payload, sample, misc


def test_atomic_mixed_note_sources_retry_history_and_original_group_correction(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        payload, sample, misc = batch(client, place)
        path = '/api/carton-unified-deliveries/warehouse-receive'
        result = ok(client.post(path, json=payload))
        assert len(result['receipts']) == 3
        assert all(row['status'] == 'POSTED' for row in result['receipts'])
        assert ok(client.post(path, json=payload)) == result
        changed = deepcopy(payload); changed['formal_lines'][0]['unit_price'] = '2'
        assert client.post(path, json=changed).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_special_requests import UnifiedDelivery
        from app.models.carton_procurement import CartonInventoryMovement
        from app.models.carton_price_review import CartonPriceReview
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(UnifiedDelivery)) == 1
            assert db.scalar(select(func.sum(CartonInventoryMovement.quantity)).where(CartonInventoryMovement.movement_type == 'INBOUND')) == Decimal(30)
            reviews = list(db.scalars(select(CartonPriceReview)))
            assert len(reviews) == 3 and all(row.original_unit_price is None and row.status != 'CONFIRMED' for row in reviews)
        history = ok(client.get('/api/carton-procurement/receipt-history', params={'factory_id': FACTORY, 'business_kind': 'SAMPLE', 'search': sample['request_no']}))
        assert history['total'] == 1 and history['items'][0]['source_requests'][0]['id'] == sample['id']
        assert history['items'][0]['delivery_id'] == result['delivery_id']
        balances = ok(client.get('/api/carton-procurement/inventory/balances', params={'factory_id': FACTORY}))
        source_ids = {source['id'] for row in balances for source in row['source_requests']}
        assert {sample['id'], misc['id']} <= source_ids
        positions = ok(client.get('/api/carton-procurement/inventory/positions', params={'factory_id': FACTORY}))
        assert {sample['id'], misc['id']} <= {source['id'] for row in positions for source in row['source_requests']}
        settlement = ok(client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': FACTORY, 'period': '2026-10'}))
        linked = [row for row in settlement['sources'] if row.get('special_request_id') == sample['id']]
        assert linked and linked[0]['special_request_no'] == sample['request_no'] and linked[0]['delivery_id'] == result['delivery_id']
        duplicate = deepcopy(payload); duplicate['request_id'] = uuid4().hex
        assert client.post(path, json=duplicate).status_code == 409
        receipt = next(row for row in result['receipts'] if row.get('special_request_id') == sample['id'])
        ok(client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse", json={'factory_id': FACTORY, 'expected_revision': receipt['revision'], 'reason': '更正原单验收记录'}))
        group = ok(client.get('/api/carton-unified-deliveries/' + result['delivery_id'], params={'factory_id': FACTORY}))
        assert group['requires_correction']
        request = next(row for row in group['special'] if row['id'] == sample['id'])
        shipment = request['shipments'][0]
        correction = command(acceptance_date='2026-10-18', special=[dict(request_id=sample['id'], shipment_id=shipment['id'], expected_revision=request['revision'], lines=[dict(shipment_line_id=shipment['lines'][0]['id'], received_quantity='10', price_action='PENDING', location_allocations=[{'location_id': place['id'], 'quantity': '10'}])])])
        updated = ok(client.post('/api/carton-unified-deliveries/' + group['id'] + '/receive', json=correction))
        assert not updated['requires_correction']
        from fastapi import HTTPException
        from app.services import carton_special_requests as service
        with monkeypatch.context() as scoped:
            def denied(*args, **kwargs): raise HTTPException(403, '当前客户责任已撤销')
            scoped.setattr(service, 'ensure_customer_operation', denied)
            assert client.post(path, json=payload).status_code == 403
        from test_carton_supplier_portal import supplier_login
        supplier_login(client)
        assert client.post(path, json=payload).status_code == 403


def test_mixed_note_rolls_back_all_sources_when_last_bin_is_invalid(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        payload, _, _ = batch(client, place)
        payload['special_requests'][-1]['lines'][0]['location_allocations'][0]['location_id'] = 'other-factory-bin'
        response = client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload)
        assert response.status_code in (404, 409, 422), response.text
        from app.db import SessionLocal
        from app.models.carton_special_requests import UnifiedDelivery, SpecialShipment
        from app.models.carton_supplier_portal import SupplierShipment
        from app.models.carton_procurement import CartonInventoryMovement, CartonReceipt
        with SessionLocal() as db:
            for model in (UnifiedDelivery, SpecialShipment, SupplierShipment, CartonInventoryMovement, CartonReceipt):
                assert db.scalar(select(func.count()).select_from(model)) == 0, model


def test_concurrent_retry_and_explicit_warehouse_zero_remain_one_unconfirmed_proposal(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    with make_client(monkeypatch) as client:
        place = setup(client)
        payload, _, _ = batch(client, place)
        payload['formal_lines'][0].update(unit_price='0', zero_price_kind='FREE')
        path = '/api/carton-unified-deliveries/warehouse-receive'
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: client.post(path, json=payload), range(2)))
        assert ok(results[0]) == ok(results[1])
        from app.db import SessionLocal
        from app.models.carton_price_review import CartonPriceReview
        from app.models.carton_special_requests import UnifiedDelivery
        with SessionLocal() as db:
            row = db.scalar(select(CartonPriceReview).where(CartonPriceReview.source_kind == 'REGULAR'))
            assert row.original_unit_price is None and row.proposed_unit_price == 0 and row.status == 'PROPOSED'
            assert db.scalar(select(func.count()).select_from(UnifiedDelivery)) == 1


def test_pre_bridge_direct_and_unified_receipt_request_fingerprints_remain_replayable():
    import hashlib, json
    from types import SimpleNamespace
    from app.schemas.carton_supplier_portal import ShipmentReceive
    from app.schemas.carton_unified_deliveries import Receive
    from app.services import carton_supplier_portal as portal, carton_special_requests as special
    direct = ShipmentReceive.model_validate(command(expected_revision=1, acceptance_date='2026-10-18', lines=[dict(shipment_line_id='original-paper', received_quantity='1', unit_price='1')]))
    legacy = direct.model_dump(mode='json'); legacy['lines'][0].pop('replenishment_issue_id')
    # The portal has other established compatibility omissions.
    normalized = json.loads(json.dumps(legacy))
    normalized.pop('new_delivery_confirmation')
    normalized.pop('remaining_action')
    for line in normalized['lines']:
        line.pop('price_action'); line.pop('price_reason')
    expected = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert portal.fingerprint(direct) == expected
    root = Receive.model_validate(command(acceptance_date='2026-10-18', formal=direct.model_dump(mode='json', include={'expected_revision', 'lines'})))
    legacy = root.model_dump(mode='json'); legacy['formal']['lines'][0].pop('replenishment_issue_id')
    digest = hashlib.sha256(special.pack(dict(action='UNIFIED_RECEIVE', id='old-group', payload=legacy, extra=None)).encode()).hexdigest()
    event = SimpleNamespace(detail_json=special.pack(dict(fingerprint=digest, response={'saved': True})))
    db = SimpleNamespace(scalar=lambda _: event)
    assert special.replay(db, SimpleNamespace(id='original-actor'), root, 'UNIFIED_RECEIVE', 'old-group')[1] == {'saved': True}


def test_free_replacement_keeps_original_stock_cost_and_no_extra_payable(monkeypatch):
    from test_carton_replenishment_api import setup as replacement_setup, body, replenish
    with make_client(monkeypatch) as client:
        order, stocks = replacement_setup(client, monkeypatch)
        updated = ok(replenish(client, order, body(order, stocks, 'SUPPLIER', 2)), 201)
        order, issue = updated['order'], updated['issue']
        place = next(row['location_id'] for row in stocks if row['order_line_id'] == order['lines'][0]['id'])
        payload = command(delivery_note_no='WB-REPLACEMENT', delivery_date='2026-08-05', acceptance_date='2026-08-05',
            order_revisions={order['order_no']: order['revision']}, formal_lines=[dict(source_type='FORMAL_ORDER',
                order_line_id=order['lines'][0]['id'], delivered_quantity='2', received_quantity='2', unit_price='0',
                zero_price_kind='FREE', replenishment_issue_id=issue['id'], location_allocations=[dict(location_id=place, quantity='2')])])
        result = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload))
        line = result['receipts'][0]['lines'][0]
        assert line['replenishment_issue_id'] == issue['id'] and Decimal(line['unit_price']) == 2
        assert Decimal(line['settlement_unit_price']) == 0
        statement = ok(client.get('/api/carton-procurement/supplier-settlements/workspace', params={'factory_id': FACTORY, 'period': '2026-08'}))
        assert not any(row['source_key'] == 'RECEIPT:' + line['id'] for row in statement['sources'])
        receipt = result['receipts'][0]
        ok(client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse", json=dict(factory_id=FACTORY, expected_revision=receipt['revision'], reason='按原补单核实更正')))
        group = ok(client.get('/api/carton-unified-deliveries/' + result['delivery_id'], params={'factory_id': FACTORY}))
        correction = command(acceptance_date='2026-08-05', formal=dict(expected_revision=group['formal']['revision'], correction_reason='按原批次更正补货', new_delivery_confirmation=True,
            lines=[dict(shipment_line_id=group['formal']['lines'][0]['id'], received_quantity='2', unit_price='0', price_action='PENDING', price_reason='原免费补单价格待核', location_allocations=[dict(location_id=place, quantity='2')])]))
        corrected = ok(client.post('/api/carton-unified-deliveries/' + group['id'] + '/receive', json=correction))
        active = next(row for row in corrected['receipts'] if row['status'] == 'POSTED')
        detail = ok(client.get('/api/carton-procurement/receipts/' + (active.get('id') or active['receipt_id']), params={'factory_id': FACTORY}))
        assert detail['lines'][0]['replenishment_issue_id'] == issue['id']
        assert Decimal(detail['lines'][0]['unit_price']) == 2 and Decimal(detail['lines'][0]['settlement_unit_price']) == 0


def test_all_rejected_superseded_receipt_keeps_original_delivery_link(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        payload, _, _ = batch(client, place)
        payload['special_requests'] = []
        payload['formal_lines'][0].update(rejected_quantity='10', location_allocations=[])
        result = ok(client.post('/api/carton-unified-deliveries/warehouse-receive', json=payload))
        receipt = result['receipts'][0]
        ok(client.post(f"/api/carton-procurement/receipts/{receipt['id']}/reverse", json={'factory_id': FACTORY, 'expected_revision': receipt['revision'], 'reason': '核实原批退回记录'}))
        group = ok(client.get('/api/carton-unified-deliveries/' + result['delivery_id'], params={'factory_id': FACTORY}))
        correction = command(acceptance_date='2026-10-18', formal=dict(expected_revision=group['formal']['revision'], correction_reason='按原单更正退回数量',
            new_delivery_confirmation=True, lines=[dict(shipment_line_id=group['formal']['lines'][0]['id'], received_quantity='10', unit_price='1',
                price_action='PROPOSE', price_reason='仓库记录待双方核实', location_allocations=[dict(location_id=place['id'], quantity='10')])]))
        ok(client.post('/api/carton-unified-deliveries/' + group['id'] + '/receive', json=correction))
        original = ok(client.get('/api/carton-procurement/receipts/' + receipt['id'], params={'factory_id': FACTORY}))
        assert original['delivery_id'] == result['delivery_id'] and original['status'] == 'REVERSED'
