import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import BASE, setup_portal, accept_all, ship_payload, receive_payload, supplier_login
from test_carton_settlement_collaboration import workspace, save, review
from test_carton_supplier_settlement_api import action


def begin(client, monkeypatch):
    setup_portal(client)
    from app.services import carton_procurement as core
    monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 11, 5, 12))
    order = accept_all(client)
    response = client.post(BASE + '/shipments', json=ship_payload(order))
    assert response.status_code == 201, response.text
    shipment = response.json()
    # Original supplier price evidence, independent of warehouse prices.
    from app.db import SessionLocal
    from app.models.carton_supplier_portal import SupplierShipmentLine
    with SessionLocal() as db:
        for line in shipment['lines']:
            row = db.get(SupplierShipmentLine, line['id'])
            row.snapshot_json = json.dumps(json.loads(row.snapshot_json) | {'delivery_unit_price': '2'})
        db.commit()
    login_as(client, 'warehouse_keeper')
    return order, shipment


def payload(client, shipment, quantity, day='2026-09-30', mode='WAIT'):
    data = receive_payload(client, shipment)
    data.update(remaining_action=mode, acceptance_date=day)
    for line in data['lines']:
        line.update(received_quantity=quantity, difference_reason='核对实物分批到货',
            location_allocations=[{**line['location_allocations'][0], 'quantity': quantity}] if quantity else [])
    return data


def post(client, shipment, data):
    response = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_two_batches_cross_month_idempotency_capacity_and_individual_reversal(monkeypatch):
    with make_client(monkeypatch) as client:
        order, original = begin(client, monkeypatch)
        first_data = payload(client, original, 6)
        first = post(client, original, first_data)
        assert first['status'] == 'SENT' and first['partially_received']
        assert all(Decimal(line['received_quantity']) == 6 and Decimal(line['remaining_quantity']) == 4 for line in first['lines'])
        assert post(client, original, first_data)['receipt_id'] == first['receipt_id']
        stale = {**first_data, 'request_id': str(uuid4())}
        assert client.post(BASE + f"/internal/shipments/{original['id']}/receive", json=stale).status_code == 409
        excess = payload(client, first, 5)
        assert client.post(BASE + f"/internal/shipments/{original['id']}/receive", json=excess).status_code == 422
        assert client.get(BASE + '/internal/shipments/pending', params={'factory_id': 'huaxing'}).json()['total'] == 1
        supplier_login(client)
        supplier = client.get(BASE + '/workspace', params={'factory_id': 'huaxing'}).json()
        assert all(Decimal(line['in_transit_quantity']) == 4 for line in supplier['orders'][0]['lines'])
        assert 'unit_price' not in json.dumps(supplier['shipments'])
        login_as(client, 'carton_supervisor')
        september = workspace(client)
        assert all(Decimal(line['quantity']) == 6 for line in september['collaboration']['lines'])
        doc = save(client, september)
        supplier_login(client)
        approved = review(client, doc)
        assert approved.status_code == 200, approved.text
        login_as(client, 'carton_supervisor')
        closed = action(client, approved.json())
        assert closed.status_code == 200, closed.text
        login_as(client, 'warehouse_keeper')
        denied_close = client.post(BASE + f"/internal/shipments/{first['id']}/receive", json=payload(client, first, 0, mode='CLOSE'))
        assert denied_close.status_code == 409  # Even a zero-stock closure cannot rewrite a closed month's vendor evidence.
        second = post(client, first, payload(client, first, 4, '2026-10-01'))
        assert second['status'] == 'RECEIVED' and second['receipt_id'] != first['receipt_id']
        assert all(Decimal(line['received_quantity']) == 10 and Decimal(line['remaining_quantity']) == 0 for line in second['lines'])
        assert len(second['acceptance_history']) == 2
        assert client.get(BASE + '/internal/shipments/pending', params={'factory_id': 'huaxing'}).json()['total'] == 0
        login_as(client, 'carton_supervisor')
        assert workspace(client)['collaboration']['source_fingerprint'] == september['collaboration']['source_fingerprint']
        october = workspace(client, '2026-10')
        assert all(Decimal(line['quantity']) == 4 for line in october['collaboration']['lines'])
        assert all(Decimal(line['amount']) == 8 for line in october['collaboration']['lines'])
        first_receipt = next(row for row in client.get('/api/carton-procurement/receipts', params={'factory_id': 'huaxing'}).json()['items'] if row['id'] == first['receipt_id'])
        reversal = {'factory_id': 'huaxing', 'expected_revision': first_receipt['revision'], 'reason': '核对第一批入库更正'}
        url = f"/api/carton-procurement/receipts/{first['receipt_id']}/reverse"
        assert client.post(url, json=reversal).status_code == 409  # Confirmed September is protected.
        assert action(client, closed.json(), 'reopen', reason='第一批入库凭证核实更正').status_code == 200
        reversed_first = client.post(url, json=reversal)
        assert reversed_first.status_code == 200, reversed_first.text
        login_as(client, 'warehouse_keeper')
        current = client.get(BASE + '/internal/workspace', params={'factory_id': 'huaxing'}).json()['shipments'][0]
        assert current['requires_correction']
        assert all(Decimal(line['received_quantity']) == 4 and Decimal(line['receivable_quantity']) == 6 for line in current['lines'])
        data = payload(client, current, 6, '2026-10-02')
        data['correction_reason'] = '核对第一批实物重新入库'
        corrected = post(client, current, data)
        assert corrected['status'] == 'RECEIVED'
        assert all(Decimal(line['received_quantity']) == 10 for line in corrected['lines'])
        login_as(client, 'carton_supervisor')
        assert not workspace(client)['sources']
        assert sorted(Decimal(line['quantity']) for line in workspace(client, '2026-10')['collaboration']['lines']) == [4, 4, 6, 6]


def test_remaining_closure_zero_wait_and_defects_do_not_reserve_twice(monkeypatch):
    with make_client(monkeypatch) as client:
        _, original = begin(client, monkeypatch)
        zero = payload(client, original, 0)
        waiting = post(client, original, zero)
        assert waiting['status'] == 'SENT' and not waiting['receipt_id']
        assert post(client, original, zero)['revision'] == waiting['revision']
        data = payload(client, waiting, 6)
        data['lines'][0]['rejected_quantity'] = 1
        data['lines'][0]['location_allocations'][0]['quantity'] = 5
        first = post(client, waiting, data)
        assert Decimal(first['lines'][0]['remaining_quantity']) == 4
        ended = post(client, first, payload(client, first, 0, mode='CLOSE'))
        assert ended['status'] == 'RECEIVED' and ended['receipt_id'] == first['receipt_id']
        assert all(Decimal(line['closed_quantity']) == 4 for line in ended['lines'])
        supplier_login(client)
        work = client.get(BASE + '/workspace', params={'factory_id': 'huaxing'}).json()
        assert all(Decimal(line['in_transit_quantity']) == 0 for line in work['orders'][0]['lines'])
        assert [Decimal(line['received_quantity']) for line in work['orders'][0]['lines']] == [5, 6]


def test_concurrent_batches_have_one_winner_and_cannot_over_receive(monkeypatch):
    with make_client(monkeypatch) as client:
        _, shipment = begin(client, monkeypatch)
        first = post(client, shipment, payload(client, shipment, 6))
        bodies = [payload(client, first, 4), payload(client, first, 4)]
        barrier = Barrier(2)
        def send(body):
            barrier.wait(timeout=10)
            return client.post(BASE + f"/internal/shipments/{shipment['id']}/receive", json=body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [job.result(timeout=30) for job in [pool.submit(send, body) for body in bodies]]
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(i for i, response in enumerate(responses) if response.status_code == 200)
        assert post(client, shipment, bodies[winner])['receipt_id'] == responses[winner].json()['receipt_id']
        receipts = client.get('/api/carton-procurement/receipts', params={'factory_id': 'huaxing'}).json()
        assert receipts['total'] == 2
        assert sum(Decimal(line['effective_quantity']) for row in receipts['items'] for line in row['lines']) == 20
