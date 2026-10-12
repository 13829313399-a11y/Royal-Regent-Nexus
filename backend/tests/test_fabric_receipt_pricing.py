import importlib
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_material_handover import client
from test_fabric_procurement import book, row, stored
from test_fabric_procurement_tracking import save
from test_fabric_receiving import request, receive


@pytest.mark.parametrize('quantity,price,expected', [
    ('0.125', '0.04', '0.01'), ('0.1', '0.2', '0.02'), ('50', '0', '0.00'),
    ('999999999999.999999', '999999999999.999999', '999999999999999998000000.00'),
])
def test_exact_full_receipt_amount_and_zero(quantity, price, expected):
    pricing = importlib.import_module('app.services.fabric_receipt_pricing')
    result = pricing.evidence(Decimal(quantity), '码', {'unit_price': price, 'price_unit': '码', 'currency': 'CNY'})
    assert result['amount'] == expected


@pytest.mark.parametrize('values', [
    {'unit_price': '-1', 'currency': 'CNY', 'price_unit': '码'},
    {'unit_price': 'NaN', 'currency': 'CNY', 'price_unit': '码'},
    {'unit_price': '1.1234567', 'currency': 'CNY', 'price_unit': '码'},
    {'unit_price': '1000000000000', 'currency': 'CNY', 'price_unit': '码'},
    {'unit_price': '1', 'currency': '', 'price_unit': '码'},
    {'unit_price': '1', 'currency': 'CNY', 'price_unit': '米'},
])
def test_invalid_price_or_unknown_currency_or_unit_cannot_calculate(values):
    pricing = importlib.import_module('app.services.fabric_receipt_pricing')
    with pytest.raises(HTTPException): pricing.evidence(Decimal('10'), '码', values)
    assert pricing.evidence(Decimal('10'), '码', {}) == {}


def test_saved_receipt_price_is_frozen_replay_safe_and_visible_in_monthly(client):
    save(client, book([row(订单日期='2026/7/18', 单价=8.99)]))
    source = stored(client)['items'][0]
    body = request(source, receipt_date='2026-07-18', unit_price='2.345', price_unit='码', currency='CNY')
    result = receive(client, source, body)
    assert result.status_code == 200, result.text
    record = result.json()
    assert record['quantity'] == '50.0' and record['amount'] == '117.25'
    assert record['unit_price'] == '2.345' and record['facts']['unit_price'] == '8.99'
    assert receive(client, source, body).json() == record
    assert receive(client, source, {**body, 'unit_price': '9'}).status_code == 409
    assert receive(client, source, {**body, 'amount': '0'}).status_code == 422
    monthly = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': 'huakang-c', 'month': '2026-07'}).json()
    assert monthly['details'][0]['unit_price'] == '2.345' and monthly['details'][0]['amount'] == '117.25'
    assert monthly['details'][0]['price_unit'] == '码' and monthly['details'][0]['currency'] == 'CNY'
    save(client, book([row(订单日期='2026/7/18', 单价=19.99)]))
    history = client.get('/api/fabric-warehouse/procurement/receipts', params={'factory_id': 'huakang-c'}).json()
    assert history['items'][0]['unit_price'] == '2.345' and history['items'][0]['amount'] == '117.25'
    # Invalid price does not append a receipt/batch or advance physical stock.
    source = stored(client)['items'][0]
    invalid = request(source, receipt_date='2026-07-19', delivery_reference='DN-INVALID', unit_price='-1', price_unit='码', currency='CNY')
    assert receive(client, source, invalid).status_code == 422
    assert client.get('/api/fabric-warehouse/procurement/receipts', params={'factory_id': 'huakang-c'}).json()['total'] == 1


def test_batch_prices_are_per_item_atomic_and_legacy_retry_hash_is_unchanged(client):
    save(client, book([row(), row(订单号='SECOND', 采购明细ID='SECOND')]))
    sources = stored(client)['items']
    def item(source, **pricing):
        body = request(source)
        return dict(source_line_id=source['id'], expected_source_revision=source['revision'], expected_receipt_count=0,
                    material_category='FABRIC', difference_reason='', batches=body['batches'], **pricing)
    body = dict(factory_id='huakang-c', request_id=str(uuid4()), receipt_date='2026-09-16', delivery_reference='BATCH-PRICE', confirmed=True,
        items=[item(sources[0], unit_price='0', price_unit='码', currency='CNY'), item(sources[1], unit_price='-1', price_unit='码', currency='HKD')])
    base = '/api/fabric-warehouse/procurement/receipts/batch'
    assert client.post(base, json=body).status_code == 422
    assert client.get('/api/fabric-warehouse/procurement/receipts', params={'factory_id': 'huakang-c'}).json()['total'] == 0
    body['items'][1]['unit_price'] = '0.1'
    response = client.post(base, json=body)
    assert response.status_code == 200, response.text
    assert [r['amount'] for r in response.json()['receipts']] == ['0.00', '5.00']
    assert client.post(base, json=body).json() == response.json()
    pricing = importlib.import_module('app.services.fabric_receipt_pricing')
    schema = importlib.import_module('app.schemas.fabric_receiving')
    # Original clients omit the optional fields. Explicit empty new defaults hash the same.
    old = request(sources[0])
    decoded = schema.ReceiveSourceRequest(**old).model_dump(mode='json')
    assert pricing.omit_empty_prices(decoded) == {**old, 'accounting_month': None, 'delivery_note_date': None,
        'prior_received_quantity': None, 'difference_reason': '', 'note': ''}
    old_batch = {**body, 'items': [item(source) for source in sources]}
    assert pricing.omit_empty_prices(schema.ReceiveSourcesRequest(**old_batch).model_dump(mode='json')) == {
        **old_batch, 'delivery_note_date': None, 'note': ''}
