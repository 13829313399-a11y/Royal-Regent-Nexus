"""Corrections to receipt attribution leave the original stock evidence intact."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from importlib import import_module
from uuid import uuid4

import pytest
from test_fabric_procurement import BASE as PURCHASE, book, row, stored
from test_fabric_procurement_tracking import save
from test_material_handover import BASE, FACTORY, client, confirmed, issuer, receipt, workbook, workspace
from test_material_handover_procurement import counts, current, receipt_link_request, send, source_book
from test_warehouse_operations import payload as operation_payload, post as operation_post


PARAMS = {'factory_id': FACTORY}


def test_unlink_restores_only_the_wrong_documents_remainder_and_allows_relink(client):
    original = operation_post(client, operation_payload(client, 'RECEIPT', source_no='MISTYPED',
        item_code='01-01-00001', unit='码', counterparty='测试供应商', lot='LOT-1', quantity='20'))
    _, headers = issuer(client)
    wrong = confirmed(client, headers)
    wrong_url = f"{BASE}/documents/{wrong['id']}"
    candidate, = client.get(wrong_url, params=PARAMS).json()['prior_receipts']['L1']['items']
    response = client.post(wrong_url + '/link-receipt', json=receipt_link_request(wrong, candidate))
    assert response.status_code == 200, response.text
    linked = response.json()
    link_id = linked['movements'][0]['operation_id']
    posted, _ = send(client, linked, [receipt(amount='10')])
    assert posted['progress']['L1'] == {'processed': '30', 'remaining': '10'}
    before = counts(), workspace(client)
    body = dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=posted['revision'],
                link_id=link_id, expected_processed='20', reason='旧入库应挂另一张送货单')
    unlink_url = wrong_url + '/unlink-receipt'
    assert client.post(unlink_url, json=body).status_code == 409
    assert client.post(unlink_url, json={**body, 'expected_processed': '30', 'reason': ' '}).status_code == 422
    body['expected_processed'] = '30'
    response = client.post(unlink_url, json=body)
    assert response.status_code == 200, response.text
    revoked = response.json()
    assert revoked['progress']['L1'] == {'processed': '10', 'remaining': '30'}
    assert revoked['code'] == posted['code'] and len(revoked['movements']) == 1
    assert revoked['revoked_receipt_links'][0]['reason'] == body['reason']
    assert client.post(unlink_url, json=body).json() == revoked
    assert client.post(unlink_url, json={**body, 'expected_revision': revoked['revision'], 'request_id': str(uuid4())}).status_code == 409
    assert (counts(), workspace(client)) == before

    correct = confirmed(client, headers, workbook(title='送货单 单号：DOC-002 2026-07-18'), source='DOC-002')
    correct_url = f"{BASE}/documents/{correct['id']}"
    candidate, = client.get(correct_url, params=PARAMS).json()['prior_receipts']['L1']['items']
    assert candidate['id'] == original['id']
    response = client.post(correct_url + '/link-receipt', json=receipt_link_request(correct, candidate))
    assert response.status_code == 200, response.text
    assert response.json()['progress']['L1']['processed'] == '20'
    report = client.get(BASE + '/monthly', params={**PARAMS, 'month': '2026-07'}).json()
    assert {item['source_no']: Decimal(item['month_received']) for item in report['details']} == {'DOC-001': 10, 'DOC-002': 20}
    assert (counts(), workspace(client)) == before
    public = client.get(f"{BASE}/external/documents/{wrong['id']}", headers=headers).json()
    assert public['progress'] == revoked['progress'] and 'revoked_receipt_links' not in public


@pytest.mark.parametrize('reverse_first', [False, True])
def test_pending_purchase_attributes_effective_splits_once_and_follows_later_reversal(client, monkeypatch, reverse_first):
    save(client, source_book(订单号='PO-B', 合同号='CT-B'))
    unrelated = stored(client)['items'][0]['id']
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(
        headers=['物料编码', '物料名称', '数量', '单位', '缸号', '采购明细ID'],
        rows=[['01-01-00001', '测试布料', '40', '码', 'LOT-1', 'K2']],
    ))
    reason = '正确合同尚未导入追货表'
    splits = [receipt(amount='12'), receipt(amount='8', location='fabric-A02')]
    send(client, doc, splits, status=422)
    pending, _ = send(client, doc, [{**part, 'procurement_pending_reason': reason} for part in splits])
    assert pending['progress']['L1'] == {'processed': '20', 'remaining': '20'}
    assert Decimal(current(client, unrelated)['warehouse_outstanding_quantity']) == 100
    first, second = [movement['operation_id'] for movement in pending['movements']]
    history_url = PURCHASE + '/receipts'
    history_params = {**PARAMS, 'unified': True, 'purchase_status': 'PENDING'}
    history = client.get(history_url, params=history_params).json()
    assert history['can_link_purchase'] and {item['id'] for item in history['items']} == {first, second}
    assert all(item['procurement_pending_reason'] == reason for item in history['items'])

    if reverse_first:
        operation_post(client, operation_payload(client, 'CORRECTION', original_id=first, reason='第一仓位录错',
            business_date='2026-08-01'))
    save(client, book([row(订单号='PO-A', 合同号='CT-A', 采购明细ID='K2', 供应商='测试供应商',
        物料编码='01-01-00001', 物料名称='测试布料', 入库数量=0, 交货明细='')]))
    url = f'{BASE}/receipts/{second}'
    response = client.get(url + '/purchase-review', params=PARAMS)
    assert response.status_code == 200, response.text
    review = response.json()
    valid_ids = [second] if reverse_first else [first, second]
    quantity = 8 if reverse_first else 20
    assert review['operation_ids'] == valid_ids and Decimal(review['quantity']) == quantity
    source = next(item for item in review['sources'] if item['order_no'] == 'PO-A')
    before = counts(), sum(Decimal(item['quantity']) for item in workspace(client)['stock'])
    body = dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=review['expected_revision'],
                operation_ids=[first, second] if reverse_first else [second], purchase_source_id=source['id'],
                expected_source_revision=source['revision'], expected_receipt_count=source['receipt_count'])
    assert client.post(url + '/purchase-link', json=body).status_code == 409
    body['operation_ids'] = review['operation_ids']
    service = import_module('app.services.material_handover_purchase_review')
    with monkeypatch.context() as denied:
        denied.setattr(service, 'can_link_purchase', lambda actor: False)
        assert client.get(url + '/purchase-review', params=PARAMS).status_code == 403
        assert client.post(url + '/purchase-link', json=body).status_code == 403
    competing = [body, {**body, 'request_id': str(uuid4())}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda request: client.post(url + '/purchase-link', json=request), competing))
    assert sorted(response.status_code for response in results) == [200, 409]
    body, result = next((request, response) for request, response in zip(competing, results) if response.status_code == 200)
    assert result.status_code == 200, result.text
    assert result.json()['purchase_order_no'] == 'PO-A'
    assert client.post(url + '/purchase-link', json=body).json() == result.json()
    assert client.post(url + '/purchase-link', json={**body, 'request_id': str(uuid4())}).status_code == 409
    assert (counts(), sum(Decimal(item['quantity']) for item in workspace(client)['stock'])) == before
    assert Decimal(current(client, source['id'])['warehouse_outstanding_quantity']) == 100 - quantity
    assert Decimal(current(client, unrelated)['warehouse_outstanding_quantity']) == 100
    assert client.get(history_url, params=history_params).json()['total'] == 0
    history = client.get(history_url, params={**PARAMS, 'unified': True}).json()
    corrected = next(item for item in history['items'] if item['id'] == second)
    assert corrected['purchase_status'] == 'LINKED' and corrected['facts']['order_no'] == 'PO-A'
    operation_post(client, operation_payload(client, 'CORRECTION', original_id=second, reason='复核原单后冲销',
        business_date='2026-08-02'))
    assert Decimal(current(client, source['id'])['warehouse_outstanding_quantity']) == 100 - quantity + 8
    detail = client.get(f"{BASE}/documents/{doc['id']}", params=PARAMS).json()
    assert detail['progress']['L1'] == {'processed': str(quantity - 8), 'remaining': str(48 - quantity)}
