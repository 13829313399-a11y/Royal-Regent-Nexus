"""Zero receipts distinguish free goods from unresolved prices without blocking stock."""
from decimal import Decimal
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, confirm, ledger
from test_carton_direct_receipt_api import payload


def test_zero_price_declarations_post_once_and_keep_monthly_meaning(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        body['acceptance_date'] = '2026-08-05'
        for line, kind in zip(body['lines'], ['FREE', 'PENDING']):
            line.update(unit_price='0', zero_price_kind=kind)
        for value in ['-1', '2']:
            body['lines'][0]['unit_price'] = value
            assert client.post(BASE + '/receipts', json=body).status_code == 422
            assert ledger(client) == []
        body['lines'][0]['unit_price'] = '0'
        response = client.post(BASE + '/receipts', json=body)
        assert response.status_code == 201, response.text
        receipt = response.json()
        assert receipt['status'] == 'POSTED'
        assert [line['zero_price_kind'] for line in receipt['lines']] == ['FREE', 'PENDING']
        assert client.post(BASE + '/receipts', json=body).json() == receipt
        assert len(ledger(client)) == 2
        from app.db import SessionLocal
        from app.services.carton_supplier_settlement import sources
        with SessionLocal() as db:
            rows, *_ = sources(db, 'huaxing', row['supplier_id'], '2026-08', 'CNY')
            by_id = {item['source_key']: item for item in rows}
            free = by_id['RECEIPT:' + receipt['lines'][0]['id']]
            pending = by_id['RECEIPT:' + receipt['lines'][1]['id']]
            assert Decimal(free['unit_price']) == 0 and Decimal(free['amount']) == 0
            assert not free['issues']
            assert pending['unit_price'] is None and pending['amount'] is None
            assert '入库单价待核实' in pending['issues']
        movements = ledger(client)
        free_movement = next(m for m in movements if m['source_line_id'] == receipt['lines'][0]['id'])
        pending_movement = next(m for m in movements if m['source_line_id'] == receipt['lines'][1]['id'])
        assert Decimal(free_movement['cost_amount']) == 0
        assert pending_movement['cost_amount'] is None
        saved = client.post(BASE + f"/inventory/movements/{pending_movement['id']}/price-confirmation", json={
            'factory_id': 'huaxing', 'unit_price': '2.5', 'reason': '供应商报价核实'})
        assert saved.status_code == 204, saved.text
        with SessionLocal() as db:
            rows, *_ = sources(db, 'huaxing', row['supplier_id'], '2026-08', 'CNY')
            assert all(item['unit_price'] is not None for item in rows)


def test_unclassified_zero_and_legacy_drafts_default_to_pending(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'warehouse_keeper')
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        body['post_immediately'] = False
        body['lines'][1]['unit_price'] = '0'
        saved = client.post(BASE + '/receipts', json=body)
        assert saved.status_code == 201, saved.text
        posted = confirm(client, saved.json())
        assert posted.status_code == 200, posted.text
        assert posted.json()['lines'][1]['zero_price_kind'] == 'PENDING'
        assert len(ledger(client)) == 2


def test_ad_hoc_gift_has_explicit_zero_payable(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'warehouse_keeper')
        _freeze_carton_time(monkeypatch)
        row = order(client)
        body = payload(row)
        body['lines'] = [{'source_type': 'AD_HOC', 'customer_code': row['customer_code'],
            'item_no': 'GIFT', 'packaging_type': '外箱', 'paper_quality': 'A33',
            'specification': '30*20*15', 'delivered_quantity': '2', 'received_quantity': '2',
            'unit_price': '0', 'zero_price_kind': 'FREE'}]
        response = client.post(BASE + '/receipts', json=body)
        assert response.status_code == 201, response.text
        assert response.json()['lines'][0]['zero_price_kind'] == 'FREE'
        assert len(ledger(client)) == 1
