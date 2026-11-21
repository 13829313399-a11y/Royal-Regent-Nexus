"""Manual intake, purchase attribution and inbound correction share one stock receipt."""
from decimal import Decimal
from uuid import uuid4

from test_fabric_procurement import BASE as PURCHASE, stored
from test_fabric_procurement_tracking import save
from test_fabric_receipt_corrections import preview, quantities, reverse
from test_fabric_receipt_history import history
from test_fabric_receiving import receive, request
from test_material_handover import BASE as HANDOVER, FACTORY, client, confirmed, issuer, posting, workbook
from test_material_handover_procurement import current, linked_part, receipt_link_request, send, source_book
from test_warehouse_operations import payload as operation_payload, post, workspace


PARAMS = {'factory_id': FACTORY}
MASTER = '/api/fabric-warehouse/master'
INTAKE = PURCHASE + '/receipts/manual'


def manual_body(client, supplier, **changes):
    result = client.post(MASTER, json=dict(**PARAMS, request_id=str(uuid4()),
        kind='MATERIAL', code='01-01-00001', name='测试布料', status='ACTIVE', data={'category': 'FABRIC', 'unit': '码'}))
    assert result.status_code == 200, result.text
    material = result.json()
    return dict(**PARAMS, request_id=str(uuid4()), receipt_date='2026-07-18', delivery_reference='DOC-001',
        delivery_quantity='10', material_category='FABRIC', material_id=material['id'], material_revision=material['revision'],
        supplier_id=supplier['id'], supplier_revision=supplier['revision'], procurement_pending_reason='现场凭证缺采购明细',
        batches=[dict(quantity='3', location='A01', location_id='fabric-A01', dye_lot='LOT-1', roll_no='R1'),
                 dict(quantity='7', location='A02', location_id='fabric-A02', dye_lot='LOT-1', roll_no='R2')], confirmed=True) | changes


def registered(client, body):
    response = client.post(INTAKE, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def supplier_record(client):
    result = client.get(MASTER, params={**PARAMS, 'kind': 'SUPPLIER'}).json()['items']
    return next(row for row in result if row['name'] == '测试供应商')


def test_manual_splits_link_once_to_purchase_and_later_delivery_and_reverse_as_one(client):
    save(client, source_book())
    purchase, = stored(client)['items']
    _, headers = issuer(client)
    body = manual_body(client, supplier_record(client))
    refused = registered(client, {**body, 'request_id': str(uuid4()), 'batches': [
        {**body['batches'][0], 'quantity': '0', 'counted_quantity': '10', 'rejected_quantity': '10'},
    ]})
    assert not refused['stock_posted'] and not preview(client, refused)['can_reverse']
    receipt = registered(client, body)
    assert registered(client, body) == receipt
    assert client.post(INTAKE, json={**body, 'request_id': str(uuid4())}).status_code == 409
    duplicate = receive(client, purchase, request(purchase, delivery_reference='doc-001'))
    assert duplicate.status_code == 409, duplicate.text
    assert '已有入库记录' in duplicate.json()['detail']

    rows = history(client, channel='MANUAL_ENTRY', purchase_status='PENDING')['items']
    assert [item['id'] for item in rows] == [receipt['id']]
    assert len(rows[0]['batches']) == 2 and quantities(client) == 10
    assert Decimal(current(client, purchase['id'])['warehouse_outstanding_quantity']) == 100
    children = [batch['id'] for batch in receipt['batches']]
    assert {row['receipt_record_id'] for row in workspace(client)['documents'] if row['kind'] == 'RECEIPT'} == {receipt['id']}
    post(client, operation_payload(client, 'CORRECTION', original_id=children[0], confirmed=True), status=422)
    assert quantities(client) == 10

    review_url = f"{HANDOVER}/receipts/{receipt['operation_id']}"
    review_result = client.get(review_url + '/purchase-review', params=PARAMS)
    assert review_result.status_code == 200, review_result.text
    review = review_result.json()
    assert review['operation_ids'] == children and Decimal(review['quantity']) == 10
    choice, = review['sources']
    link_body = dict(**PARAMS, request_id=str(uuid4()), expected_revision=review['expected_revision'],
        operation_ids=children, purchase_source_id=choice['id'], expected_source_revision=choice['revision'],
        expected_receipt_count=choice['receipt_count'])
    link = client.post(review_url + '/purchase-link', json=link_body)
    assert link.status_code == 200, link.text
    assert client.post(review_url + '/purchase-link', json=link_body).json() == link.json()
    assert history(client, purchase_status='PENDING')['total'] == 0
    source = current(client, purchase['id'])
    assert Decimal(source['warehouse_outstanding_quantity']) == 90 and source['receipt_count'] == 1
    assert quantities(client) == 10

    delivery = confirmed(client, headers)
    delivery_url = f"{HANDOVER}/documents/{delivery['id']}"
    candidate, = client.get(delivery_url, params=PARAMS).json()['prior_receipts']['L1']['items']
    assert candidate['id'] == children[0] and Decimal(candidate['quantity']) == 10
    result = client.post(delivery_url + '/link-receipt', json=receipt_link_request(delivery, candidate))
    assert result.status_code == 200, result.text
    assert result.json()['progress']['L1'] == {'processed': '10', 'remaining': '30'}
    assert quantities(client) == 10

    report = '/api/warehouse-operations/fabric/monthly'
    july = client.get(report, params={**PARAMS, 'month': '2026-07'}).json()
    monthly_receipt, = july['details']
    assert Decimal(monthly_receipt['quantity']) == 10
    before = preview(client, receipt)
    assert before['can_reverse'] and before['affects_purchase'] and before['affects_delivery']
    assert len(before['locations']) == 2
    correction, retry = reverse(client, receipt, before['expected_revision'])
    assert correction.status_code == 200, correction.text
    assert client.post(f"{PURCHASE}/receipts/{receipt['id']}/reverse", json=retry).json() == correction.json()
    assert quantities(client) == 0
    assert Decimal(current(client, purchase['id'])['warehouse_outstanding_quantity']) == 100
    assert client.get(delivery_url, params=PARAMS).json()['progress']['L1'] == {'processed': '0', 'remaining': '40'}
    old, = history(client, search=receipt['id'])['items']
    assert old['reversed'] and len(old['batches']) == 2 and old['reversal']['reason'] == retry['reason']
    october = client.get(report, params={**PARAMS, 'month': '2026-10'}).json()
    monthly_reversal, = october['details']
    assert Decimal(monthly_reversal['quantity']) == -10


def test_manual_and_handover_validate_only_known_rolls_within_the_same_bin(client):
    issuer(client)
    body = manual_body(client, supplier_record(client))
    first = {**body['batches'][0], 'quantity': '5'}
    duplicate = client.post(INTAKE, json={**body, 'batches': [first, first]})
    assert duplicate.status_code == 422 and quantities(client) == 0

    blank = {**first, 'roll_no': ''}
    empty_rolls = registered(client, {**body, 'request_id': str(uuid4()), 'batches': [blank, blank]})
    assert len(empty_rolls['batches']) == 2 and quantities(client) == 10
    other_bin = {**first, 'location': 'A02', 'location_id': 'fabric-A02'}
    split = registered(client, {**body, 'request_id': str(uuid4()), 'delivery_reference': 'DOC-DIFFERENT-BINS',
        'batches': [first, other_bin]})
    assert len(split['batches']) == 2 and quantities(client) == 20

    _, headers = issuer(client, '扫码复核供应商')
    doc = confirmed(client, headers, workbook(headers=['物料编码','物料名称','数量','单位','缸号','卷号'],
        rows=[['01-01-00001','测试布料','40','码','LOT-1','R1']]))
    assert doc['data']['lines'][0]['roll_no'] == 'R1'
    part = dict(line_id='L1', quantity='5', location_id='fabric-A01', lot='LOT-1', roll_no='')
    route = f"{HANDOVER}/documents/{doc['id']}/post"
    revision = workspace(client)['revision']
    duplicate = client.post(route, json=posting(doc, revision, [part, part]))
    assert duplicate.status_code == 422 and quantities(client) == 20
    rejected = {**part, 'quantity': '0', 'receipt_counts': {'counted_quantity': '5', 'rejected_quantity': '5'}}
    for parts in ([rejected, rejected], [rejected, part]):
        duplicate = client.post(route, json=posting(doc, revision, parts))
        assert duplicate.status_code == 422 and '重复' in duplicate.json()['detail']
    assert workspace(client)['revision'] == revision

    blank = {**part, 'roll_no_is_blank': True}
    accepted = client.post(route, json=posting(doc, revision, [blank, blank]))
    assert accepted.status_code == 200, accepted.text
    result = accepted.json()
    assert result['progress']['L1'] == {'processed': '10', 'remaining': '30'}
    new_batch_ids = {move['operation_id'] for move in result['movements']}
    assert len(new_batch_ids) == 2 and quantities(client) == 30
    assert [row['roll_no'] for row in workspace(client)['stock'] if row['id'] in new_batch_ids] == ['', '']


def test_manual_reversal_is_atomic_if_a_later_split_is_used(client):
    issuer(client)
    receipt = registered(client, manual_body(client, supplier_record(client)))
    post(client, operation_payload(client, 'ISSUE', batch_id=receipt['batches'][1]['id'], quantity='2'))
    before = preview(client, receipt)
    assert not before['can_reverse'] and before['blocked_reason']
    failed, _ = reverse(client, receipt, before['expected_revision'])
    assert failed.status_code == 409, failed.text
    assert quantities(client) == 8
    assert all(row['kind'] != 'CORRECTION' for row in workspace(client)['documents'])


def test_original_online_delivery_receipt_reverses_from_inbound_history(client):
    save(client, source_book())
    purchase, = stored(client)['items']
    _, headers = issuer(client)
    delivery = confirmed(client, headers)
    processed, _ = send(client, delivery, [linked_part(client, delivery, amount='12')])
    receipt, = history(client, channel='HANDOVER')['items']
    assert receipt['id'] == processed['movements'][0]['operation_id']
    before = preview(client, receipt)
    assert before['can_reverse'] and before['affects_delivery'] and before['affects_purchase']
    response, _ = reverse(client, receipt, before['expected_revision'])
    assert response.status_code == 200, response.text
    assert quantities(client) == 0
    assert Decimal(current(client, purchase['id'])['warehouse_outstanding_quantity']) == 100
    doc = client.get(f"{HANDOVER}/documents/{delivery['id']}", params=PARAMS).json()
    assert doc['progress']['L1'] == {'processed': '0', 'remaining': '40'}
