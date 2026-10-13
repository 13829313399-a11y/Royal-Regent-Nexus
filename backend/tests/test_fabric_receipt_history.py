"""Unified receipt query uses real posting paths and never posts inventory."""
import importlib

import pytest
from test_material_handover import FACTORY
from test_fabric_procurement import BASE, book, row, stored
from test_fabric_receiving import request, receive
from decimal import Decimal

from test_material_handover import client, issuer, confirmed, workbook, receipt
from test_material_handover_procurement import save, source_book, linked_part, send
from test_fabric_receipt_corrections import original, reverse
from test_warehouse_operations import payload, post, workspace

PATH = '/api/fabric-warehouse/procurement/receipts'


def history(client, **filters):
    response = client.get(PATH, params=dict(factory_id='huakang-c', unified=True, **filters))
    assert response.status_code == 200, response.text
    return response.json()


def test_original_splits_and_operations_share_filter_sort_and_pagination_without_nonreceipts(client):
    _, purchase, _, _ = original(client, batches=[dict(quantity='2', location='A01', dye_lot='001'),
                                                dict(quantity='3', location='A02', dye_lot='002')])
    manual = post(client, payload(client, 'RECEIPT', source_no='MANUAL-EXACT', counterparty='独立供应商'))
    issue = post(client, payload(client, 'ISSUE', batch_id=manual['id'], quantity='3'))
    post(client, payload(client, 'RETURN', original_id=issue['id'], quantity='1'))
    post(client, payload(client, 'TRANSFER', batch_id=manual['id'], location='A02', quantity='1'))
    before = workspace(client)
    result = history(client)
    assert result['total'] == 2
    assert {r['receipt_origin'] for r in result['items']} == {'PROCUREMENT', 'MANUAL'}
    row = next(r for r in result['items'] if r['receipt_origin'] == 'PROCUREMENT')
    assert row['id'] == purchase['id'] and len(row['batches']) == 2 and Decimal(row['quantity']) == 5
    assert history(client, search='MANUAL-EXACT')['items'][0]['id'] == manual['id']
    assert history(client, supplier='独立供应商', category='FABRIC', channel='MANUAL')['total'] == 1
    assert history(client, channel='HANDOVER')['total'] == 0
    assert history(client, receipt_to='2026-07-31')['items'][0]['id'] == manual['id']
    combined = history(client, sort='RECEIPT_ASC')['items']
    pages = [history(client, sort='RECEIPT_ASC', limit=1, offset=i)['items'][0] for i in range(2)]
    assert [r['history_key'] for r in pages] == [r['history_key'] for r in combined]
    assert history(client, offset=2, limit=1)['items'] == []
    assert workspace(client) == before
    # Old consumers still receive the original receipt-only API contract.
    assert client.get(PATH, params={'factory_id': 'huakang-c'}).json()['total'] == 1


def test_linked_delivery_partial_receipts_count_once_each_and_unreceived_notes_are_absent(client):
    save(client, source_book(生产单号='PROD-FROZEN-001'))
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[['01-01-00001', '测试布料', '100', '码', 'LOT-1']]))
    assert history(client)['total'] == 0
    result, first_body = send(client, doc, [linked_part(client, doc, '10')])
    # Exact replay doesn't add an entry to the unified history.
    send(client, doc, [linked_part(client, result, '10')], body=first_body)
    result, _ = send(client, result, [linked_part(client, result, '20')])
    rows = history(client, channel='HANDOVER')['items']
    assert len(rows) == 2 and sum(Decimal(r['quantity']) for r in rows) == 30
    assert all(r['handover_document_id'] == doc['id'] and r['operation_id'] == r['id'] for r in rows)
    assert all(r['facts']['order_no'] for r in rows)
    assert all(r['facts']['production_no'] == 'PROD-FROZEN-001' for r in rows)
    assert history(client, search='PROD-FROZEN-001')['total'] == 2
    assert history(client, search=doc['data']['source_no'])['total'] == 2
    confirmed(client, headers, source='NOT-RECEIVED')
    assert history(client)['total'] == 2


def test_unified_permissions_do_not_expand_procurement_only_readers(client, monkeypatch):
    original(client)
    post(client, payload(client, 'RECEIPT', counterparty='不可泄露的收发单位'))
    api = importlib.import_module('app.api.fabric_procurement')
    real = api.can
    monkeypatch.setattr(api, 'can', lambda actor, permission, *args: False if permission == 'fabric_operations:read' else real(actor, permission, *args))
    result = history(client)
    assert result['total'] == 1 and result['operations_included'] is False and result['can_reverse'] is False
    assert '不可泄露的收发单位' not in result['options']['suppliers']
    assert history(client, channel='MANUAL')['total'] == 0
    monkeypatch.setattr(api, 'can', lambda actor, permission, *args: False if permission == 'fabric_warehouse:read' else real(actor, permission, *args))
    assert client.get(PATH, params={'factory_id': 'huakang-c', 'unified': True}).status_code == 403
    assert client.get(PATH, params={'factory_id': 'huakang-b', 'unified': True}).status_code in (403, 422)


def test_unlinked_delivery_is_visible_and_opening_count_events_are_not_receipts(client):
    from test_fabric_inventory_setup import book, preview, apply, count, act
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    send(client, doc, [receipt(amount='4')])
    result = history(client, channel='HANDOVER')
    assert result['total'] == 1
    assert result['items'][0]['facts']['order_no'] == ''
    assert result['items'][0]['quantity'] == '4'
    content = book()
    opened = apply(client, content, preview(client, content).json())
    assert opened.status_code == 200, opened.text
    draft = count(client, [result['items'][0]['id']])
    assert act(client, draft, actual='3')[0].status_code == 200
    assert history(client)['total'] == 1
    assert history(client)['items'][0]['quantity'] == '4'


def test_reversed_sources_preserve_original_quantities_and_their_own_identifiers(client):
    _, purchase, _, _ = original(client)
    assert reverse(client, purchase)[0].status_code == 200
    manual = post(client, payload(client, 'RECEIPT'))
    correction = post(client, payload(client, 'CORRECTION', original_id=manual['id']))
    result = history(client, state='REVERSED')
    assert result['total'] == 2 and history(client, state='ACTIVE')['total'] == 0
    rows = {r['receipt_origin']: r for r in result['items']}
    assert rows['PROCUREMENT']['unit_price'] == '5' and rows['PROCUREMENT']['amount'] == '250.00'
    assert Decimal(rows['PROCUREMENT']['quantity']) == 50
    assert rows['MANUAL']['reversal']['id'] == correction['id'] and rows['MANUAL']['quantity'] == '10'
    assert 'operation_id' not in rows['PROCUREMENT']


@pytest.mark.parametrize('unified', [False, True])
def test_history_filters_dates_status_and_stable_sorting_before_pagination(client, monkeypatch, unified):
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
        response = client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, unified=unified, **filters))
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
        assert client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, unified=unified, **filters)).status_code == 422
    api = importlib.import_module('app.api.fabric_procurement')
    monkeypatch.setattr(api, 'can', lambda *_: False)
    assert client.get(BASE + '/receipts', params=dict(factory_id=FACTORY, supplier='Alpha')).status_code == 403
