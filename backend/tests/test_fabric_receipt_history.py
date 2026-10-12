"""Receipt-history queries use frozen facts and filter/sort before pagination."""
import importlib

from test_material_handover import client, FACTORY
from test_fabric_procurement import BASE, book, row, stored
from test_fabric_procurement_tracking import save
from test_fabric_receiving import request, receive
from test_fabric_receipt_corrections import reverse


def test_history_filters_dates_status_and_stable_sorting_before_pagination(client, monkeypatch):
    specifications = [
        ('A', 'Alpha', 'FABRIC', '2026-10-01', '2026-10-04T10:00:00+08:00'),
        ('B', 'Zeta', 'THREAD', '2026-10-03', '2026-10-05T10:00:00+08:00'),
        ('C', 'Alpha', 'ACCESSORY', '2026-10-03', '2026-10-06T10:00:00+08:00'),
        ('D', 'Beta', 'FABRIC', '2026-09-30', '2026-10-07T10:00:00+08:00'),
    ]
    save(client, book([row(订单号=key, 采购明细ID=key, 供应商=supplier, 入库数量=0, 交货明细='')
        for key, supplier, *_ in specifications]))
    sources = {item['facts']['order_no']: item for item in stored(client)['items']}
    receipts = {}
    for key, supplier, category, day, _ in specifications:
        response = receive(client, sources[key], request(sources[key], receipt_date=day, delivery_reference='DN-' + key,
            material_category=category, batches=[{'quantity': '1', 'location': 'A01', 'dye_lot': '001' if category == 'FABRIC' else ''}]))
        assert response.status_code == 200, response.text
        receipts[key] = response.json()
    database = importlib.import_module('app.db')
    model = importlib.import_module('app.models.fabric_receiving').FabricReceipt
    with database.SessionLocal() as db:
        for key, *_, timestamp in specifications:
            db.get(model, receipts[key]['id']).occurred_at = timestamp
        db.commit()
    response, _ = reverse(client, receipts['A'])
    assert response.status_code == 200, response.text

    def query(**filters):
        response = client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, **filters))
        assert response.status_code == 200, response.text
        return response.json()

    def keys(result):
        return [item['facts']['order_no'] for item in result['items']]

    assert keys(query()) == ['C', 'B', 'A', 'D']
    assert keys(query(sort='RECEIPT_ASC')) == ['D', 'A', 'C', 'B']
    assert keys(query(sort='RECORDED_DESC')) == ['D', 'C', 'B', 'A']
    assert keys(query(sort='SUPPLIER')) == ['C', 'A', 'D', 'B']
    assert keys(query(sort='SUPPLIER', offset=1, limit=1)) == ['A']
    matched = query(supplier='Alpha', receipt_from='2026-10-01', receipt_to='2026-10-03', offset=1, limit=1)
    assert matched['total'] == 2 and keys(matched) == ['A']
    assert matched['options']['suppliers'] == ['Alpha', 'Beta', 'Zeta']
    assert keys(query(receipt_from='2026-10-03', receipt_to='2026-10-03')) == ['C', 'B']
    assert keys(query(receipt_to='2026-10-01')) == ['A', 'D']
    assert keys(query(category='FABRIC', state='ACTIVE')) == ['D']
    assert keys(query(supplier='Alpha', category='ACCESSORY', state='ACTIVE', search='DN-C')) == ['C']
    reversed_only = query(state='REVERSED', search='dn-a')
    assert keys(reversed_only) == ['A'] and reversed_only['items'][0]['reversed']
    assert reversed_only['items'][0]['quantity'] == '1'  # Immutable original, not current balance.
    assert query(supplier='Missing')['total'] == 0
    assert query(offset=20)['total'] == 4 and query(offset=20)['items'] == []
    # Frozen historical supplier options are not current master/source names.
    source_model = importlib.import_module('app.models.fabric_procurement').FabricProcurementLine
    with database.SessionLocal() as db:
        original = db.get(model, receipts['A']['id'])
        frozen = (original.source_json, original.payload_json, original.quantity)
        source = db.get(source_model, sources['A']['id'])
        source.supplier = 'Renamed'
        source.payload_json = source.payload_json.replace('Alpha', 'Renamed')
        db.commit()
    assert query(supplier='Alpha')['total'] == 2
    with database.SessionLocal() as db:
        original = db.get(model, receipts['A']['id'])
        assert (original.source_json, original.payload_json, original.quantity) == frozen
    for filters in ({'receipt_from': '2026-10-04', 'receipt_to': '2026-10-01'}, {'receipt_from': 'invalid'},
                    {'sort': 'QUANTITY'}, {'state': 'UNKNOWN'}, {'category': 'UNKNOWN'}):
        assert client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, **filters)).status_code == 422
    api = importlib.import_module('app.api.fabric_procurement')
    monkeypatch.setattr(api, 'can', lambda *_: False)
    assert client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, supplier='Alpha')).status_code == 403
