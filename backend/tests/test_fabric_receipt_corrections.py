"""Original purchase receipts reverse atomically without overwriting evidence."""
import copy
import importlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select, func
from test_material_handover import client, FACTORY
from test_fabric_procurement import BASE, row, book, stored
from test_fabric_procurement_tracking import save, undo_preview
from test_fabric_receiving import request, receive
from test_warehouse_operations import workspace, payload, post


def original(client, **overrides):
    batch = save(client, book([row(入库数量=0, 交货明细='', 采购明细ID='K1')]))
    source = stored(client)['items'][0]
    body = request(source, unit_price='5', price_unit='码', currency='CNY', **overrides)
    result = receive(client, source, body)
    assert result.status_code == 200, result.text
    return source, result.json(), body, batch


def preview(client, receipt):
    response = client.get(BASE + '/receipts/' + receipt['id'] + '/reversal-preview', params={'factory_id': FACTORY})
    assert response.status_code == 200, response.text
    return response.json()


def reverse(client, receipt, version=None, **values):
    body = dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=version if version is not None else preview(client, receipt)['expected_revision'],
        business_date='2026-10-10', reason='原单数量录错，整单冲销后重录', confirmed=True)
    body.update(values)
    return client.post(BASE + '/receipts/' + receipt['id'] + '/reverse', json=body), body


def quantities(client):
    return sum(Decimal(row['quantity']) for row in workspace(client)['stock'])


def test_whole_receipt_reversal_preserves_original_price_and_evidence_restores_chase_and_allows_correct_reentry(client):
    source, receipt, body, batch = original(client)
    database = importlib.import_module('app.db')
    model = importlib.import_module('app.models.fabric_receiving').FabricReceipt
    with database.SessionLocal() as db:
        saved = db.get(model, receipt['id'])
        frozen = (saved.source_json, saved.payload_json, saved.quantity, saved.request_hash)
    before = preview(client, receipt)
    assert before['can_reverse'] and Decimal(before['quantity']) == 50
    response, correction = reverse(client, receipt, before['expected_revision'])
    assert response.status_code == 200, response.text
    assert quantities(client) == 0
    assert client.post(BASE + '/receipts/' + receipt['id'] + '/reverse', json=correction).json() == response.json()
    assert reverse(client, receipt)[0].status_code == 409
    source = stored(client)['items'][0]
    assert Decimal(source['warehouse_received_quantity']) == 0 and Decimal(source['warehouse_outstanding_quantity']) == 100
    assert source['revision'] == 2
    history = client.get(BASE + '/receipts', params={'factory_id': FACTORY}).json()
    old = history['items'][0]
    assert old['reversed'] and old['reversal']['reason'] == correction['reason']
    assert old['unit_price'] == '5' and old['amount'] == '250.00'
    assert receive(client, source, body).json()['id'] == receipt['id']  # exact old UUID can't receive again
    assert quantities(client) == 0
    with database.SessionLocal() as db:
        saved = db.get(model, receipt['id'])
        assert (saved.source_json, saved.payload_json, saved.quantity, saved.request_hash) == frozen
    corrected = request(source, receipt_date='2026-10-10', unit_price='6', price_unit='码', currency='CNY',
        batches=[{'quantity': '7.5', 'location': 'A01', 'dye_lot': '00001'}])
    new = receive(client, source, corrected)
    assert new.status_code == 200, new.text
    assert new.json()['id'] != receipt['id'] and new.json()['delivery_reference'] == body['delivery_reference']
    assert new.json()['replaces_receipt_ids'] == [receipt['id']]
    assert quantities(client) == Decimal('7.5')
    assert Decimal(stored(client)['items'][0]['warehouse_outstanding_quantity']) == Decimal('92.5')
    assert undo_preview(client, batch).status_code == 409
    september = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-09'}).json()
    october = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-10'}).json()
    assert sum(Decimal(row['quantity']) for row in september['details']) == 50
    assert sum(Decimal(row['quantity']) for row in october['details']) == Decimal('-42.5')


def test_reversal_requires_confirmation_reason_current_version_and_correct_permission(client, monkeypatch):
    source, receipt, _, _ = original(client)
    assert reverse(client, receipt, confirmed=False)[0].status_code == 422
    assert reverse(client, receipt, reason='')[0].status_code == 422
    assert reverse(client, receipt, version=99)[0].status_code == 409
    assert quantities(client) == 50
    api = importlib.import_module('app.api.fabric_procurement')
    real = api.can
    monkeypatch.setattr(api, 'can', lambda actor, permission, *args: False if permission == 'fabric_operations:correct' else real(actor, permission, *args))
    assert client.get(BASE + '/receipts/' + receipt['id'] + '/reversal-preview', params={'factory_id': FACTORY}).status_code == 403
    assert reverse(client, receipt, version=0)[0].status_code == 403
    assert not client.get(BASE + '/receipts', params={'factory_id': FACTORY}).json()['can_reverse']
    assert quantities(client) == 50


def test_downstream_issue_blocks_whole_original_receipt_reversal(client):
    _, receipt, _, _ = original(client)
    stock = workspace(client)['stock'][0]
    post(client, payload(client, 'ISSUE', batch_id=stock['id'], quantity='1', counterparty='车间A', business_date='2026-10-10'))
    assert not preview(client, receipt)['can_reverse']
    assert reverse(client, receipt)[0].status_code == 409
    assert quantities(client) == 49


def test_concurrent_whole_reversals_only_create_one_correction(client):
    _, receipt, _, _ = original(client)
    version = preview(client, receipt)['expected_revision']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: reverse(client, receipt, version)[0], range(2)))
    assert sorted(result.status_code for result in responses) == [200, 409]
    assert quantities(client) == 0
    assert len([row for row in workspace(client)['documents'] if row['kind'] == 'CORRECTION']) == 1


def test_concurrent_issue_and_whole_reversal_cannot_consume_reversed_stock(client):
    _, receipt, _, _ = original(client)
    stock = workspace(client)['stock'][0]
    issue = payload(client, 'ISSUE', batch_id=stock['id'], quantity='1', counterparty='车间A', business_date='2026-10-10')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda operation: operation(), [lambda: reverse(client, receipt, version=0)[0],
            lambda: client.post('/api/warehouse-operations/fabric/documents', json=issue)]))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert quantities(client) in (0, 49)


def test_correct_reentry_cannot_backdate_before_its_reversal(client):
    _, receipt, _, _ = original(client)
    assert reverse(client, receipt)[0].status_code == 200
    source = stored(client)['items'][0]
    assert receive(client, source, request(source, receipt_date='2026-09-16')).status_code == 422
    assert quantities(client) == 0
