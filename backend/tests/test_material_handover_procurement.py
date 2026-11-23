"""Actual deliveries reduce purchase chase once across both receiving paths."""
import copy
import importlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test_material_handover import client, BASE, FACTORY, issuer, confirmed, workbook, workspace, posting, receipt
from test_fabric_procurement import BASE as PURCHASE, book, row, stored
from test_fabric_procurement_tracking import save, undo_preview
from test_fabric_receiving import request as manual_request, receive
from test_warehouse_operations import payload as operation_payload, post as operation_post


def sources(client, doc):
    response = client.get(BASE + '/documents/' + doc['id'] + '/purchase-sources', params={'factory_id': FACTORY})
    assert response.status_code == 200, response.text
    return response.json()['lines']


def source_book(**changes):
    return book([row(供应商='测试供应商', 物料编码='01-01-00001', 物料名称='测试布料',
        订单数量=100, 入库数量=0, 交货明细='', 采购明细ID='K1', **changes)])


def linked_part(client, doc, amount='80', line='L1', target=0, **changes):
    choice = sources(client, doc)[line][target]
    return {**receipt(line, amount), 'purchase_source_id': choice['id'],
        'expected_source_revision': choice['revision'], 'expected_receipt_count': choice['receipt_count'], **changes}


def send(client, doc, parts, status=200, body=None):
    body = body or posting(doc, workspace(client)['revision'], parts)
    response = client.post(BASE + '/documents/' + doc['id'] + '/post', json=body)
    assert response.status_code == status, response.text
    return response.json(), body


def current(client, source_id):
    return next(item for item in stored(client)['items'] if item['id'] == source_id)


def counts():
    db_module = importlib.import_module('app.db')
    receipt_model = importlib.import_module('app.models.fabric_receiving').FabricReceipt
    operation_model = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
    with db_module.SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(receipt_model)),
            db.scalar(select(func.count()).select_from(operation_model).where(operation_model.warehouse == 'fabric')))


def test_partial_and_complete_delivery_reduce_chase_without_duplicate_stock_or_monthly_totals(client):
    batch = save(client, source_book())
    source = stored(client)['items'][0]
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[['01-01-00001', '测试布料', '100', '码', 'LOT-1']]))
    part = linked_part(client, doc)
    result, body = send(client, doc, [part])
    assert send(client, doc, [part], body=body)[0] == result
    assert counts() == (0, 1)
    progress = current(client, source['id'])
    assert Decimal(progress['warehouse_received_quantity']) == 80
    assert Decimal(progress['warehouse_outstanding_quantity']) == 20
    assert stored(client, view='PARTIAL')['total'] == 1
    assert sum(Decimal(item['quantity']) for item in workspace(client)['stock']) == 80
    assert undo_preview(client, batch).status_code == 409
    result, _ = send(client, result, [linked_part(client, result, '20')])
    assert Decimal(current(client, source['id'])['warehouse_outstanding_quantity']) == 0
    assert stored(client, view='OUTSTANDING')['total'] == 0
    assert stored(client, view='ARRIVAL_REVIEW')['total'] == 0
    assert counts() == (0, 2)
    report = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-07'}).json()
    assert sum(Decimal(item['quantity']) for item in report['details'] if item['kind'] == 'RECEIPT') == 100
    # A procurement spreadsheet later reports our own receipts; the original zero
    # starting reference stays frozen and actual quantities aren't subtracted twice.
    save(client, book([], [row(供应商='测试供应商', 物料编码='01-01-00001', 物料名称='测试布料',
        入库数量=100, 交货明细='100', 采购明细ID='K1')]))
    updated = current(client, source['id'])
    assert Decimal(updated['warehouse_received_quantity']) == 100
    assert Decimal(updated['starting_chase_quantity']) == 100


def test_same_uploaded_note_blocks_both_manual_receiving_paths_but_different_notes_share_progress(client):
    save(client, source_book())
    source = stored(client)['items'][0]
    first = manual_request(source, delivery_reference='MANUAL-FIRST', batches=[
        {'quantity': '30', 'location': 'A01', 'dye_lot': 'LOT-1'}])
    assert receive(client, source, first).status_code == 200
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    source = current(client, source['id'])
    duplicate = manual_request(source, delivery_reference=doc['data']['source_no'])
    assert receive(client, source, duplicate).status_code == 409
    operation_post(client, operation_payload(client, 'RECEIPT', source_no=doc['data']['source_no'],
        item_code='01-01-00001', unit='码', counterparty='测试供应商'), status=409)
    result, _ = send(client, doc, [linked_part(client, doc, '40')])
    progress = current(client, source['id'])
    assert Decimal(progress['warehouse_received_quantity']) == 70
    assert Decimal(progress['warehouse_outstanding_quantity']) == 30
    # Even a fresh manual dialog and a new UUID cannot register the same delivery.
    assert receive(client, progress, manual_request(progress, delivery_reference=doc['data']['source_no'])).status_code == 409
    assert counts() == (1, 1)


def test_note_previously_received_manually_cannot_be_received_again_by_handover(client):
    save(client, source_book())
    source = stored(client)['items'][0]
    assert receive(client, source, manual_request(source, delivery_reference='DOC-001', batches=[
        {'quantity': '20', 'location': 'A01', 'dye_lot': 'LOT-1'}])).status_code == 200
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    send(client, doc, [linked_part(client, doc, '20')], status=409)
    assert counts() == (1, 0)


def test_standalone_manual_receipt_before_upload_also_blocks_handover_reposting(client):
    save(client, source_book())
    operation_post(client, operation_payload(client, 'RECEIPT', source_no='DOC-001', item_code='01-01-00001',
        unit='码', counterparty='测试供应商', quantity='20'))
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    send(client, doc, [linked_part(client, doc, '20')], status=409)
    assert counts() == (0, 1)


def receipt_link_request(doc, candidate, line_id='L1'):
    return dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=doc['revision'],
                line_id=line_id, receipt_id=candidate['id'])


@pytest.mark.parametrize('purchase_entry', [False, True])
def test_link_existing_receipt_updates_progress_without_reposting(client, purchase_entry):
    save(client, source_book())
    source = stored(client)['items'][0]
    if purchase_entry:
        response = receive(client, source, manual_request(source, delivery_reference='DOC-001',
            receipt_date='2026-07-18', batches=[
                {'quantity': '12', 'location': 'A01', 'dye_lot': 'LOT-1', 'roll_no': 'R1'},
                {'quantity': '8', 'location': 'A02', 'dye_lot': 'LOT-1', 'roll_no': 'R2'},
            ]))
        assert response.status_code == 200, response.text
    else:
        operation_post(client, operation_payload(client, 'RECEIPT', source_no='DOC-001', item_code='01-01-00001',
            unit='码', counterparty='测试供应商', lot='LOT-1', quantity='20'))
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    document_url = BASE + '/documents/' + doc['id']
    scanned = client.post(BASE + '/scan', json=dict(factory_id=FACTORY, code=doc['code'])).json()
    candidate, = scanned['prior_receipts']['L1']['items']
    assert candidate['exact_reference'] and candidate['blocks_posting'] and candidate['can_link']
    assert len(candidate['parts']) == (2 if purchase_entry else 1)
    before = counts(), workspace(client), current(client, source['id'])['warehouse_received_quantity']
    body = receipt_link_request(doc, candidate)
    result = client.post(document_url + '/link-receipt', json=body)
    assert result.status_code == 200, result.text
    linked = result.json()
    assert linked['progress']['L1'] == {'processed': '20', 'remaining': '20'}
    assert linked['processing_status'] == 'PARTIAL' and linked['code'] == doc['code']
    assert linked['prior_receipts'] == {}
    assert client.post(document_url + '/link-receipt', json=body).json() == linked
    assert client.post(document_url + '/link-receipt', json=receipt_link_request(linked, candidate)).status_code == 409
    assert (counts(), workspace(client), current(client, source['id'])['warehouse_received_quantity']) == before
    public = client.get(BASE + '/external/documents/' + doc['id'], headers=headers).json()
    assert public['progress'] == linked['progress']
    assert 'prior_receipts' not in public and 'manual_reference' not in public['movements'][0]
    assert candidate['id'] not in str(public)

    send(client, linked, [linked_part(client, linked, '21')], status=409)
    completed, _ = send(client, linked, [linked_part(client, linked, '20')])
    assert completed['processing_status'] == 'COMPLETE'
    pending = client.get(BASE + '/pending-deliveries', params={'factory_id': FACTORY}).json()
    assert not any(item['id'] == doc['id'] for item in pending['items'])
    report = client.get(BASE + '/monthly', params={'factory_id': FACTORY, 'month': '2026-07'}).json()
    assert Decimal(report['details'][0]['month_received']) == 40
    assert not report['unlinked_receipts']
    assert sum(Decimal(item['quantity']) for item in workspace(client)['stock']) == 40
    assert Decimal(current(client, source['id'])['warehouse_received_quantity']) == (40 if purchase_entry else 20)

    operation_post(client, operation_payload(client, 'CORRECTION', original_id=candidate['id'],
        reason='原实收需要冲销核对', business_date='2026-08-01', confirmed=True))
    reopened = client.get(document_url, params={'factory_id': FACTORY}).json()
    assert reopened['progress']['L1'] == {'processed': '20', 'remaining': '20'}
    assert next(item for item in reopened['movements'] if 'manual_reference' in item)['reversed']
    pending = client.get(BASE + '/pending-deliveries', params={'factory_id': FACTORY}).json()
    assert any(item['id'] == doc['id'] and item['processing_status'] == 'PARTIAL' for item in pending['items'])
    report = client.get(BASE + '/monthly', params={'factory_id': FACTORY, 'month': '2026-08'}).json()
    assert Decimal(report['details'][0]['month_reversed']) == 20
    failed, _ = send(client, reopened, [linked_part(client, reopened, '20')], status=409)
    assert '冲销日期' in failed['detail']


def test_mistyped_reference_requires_review_and_can_be_used_by_the_real_delivery(client):
    operation_post(client, operation_payload(client, 'RECEIPT', source_no='DOC-002', item_code='01-01-00001',
        unit='码', counterparty='测试供应商', lot='LOT-1', quantity='20'))
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    details_url = BASE + '/documents/' + doc['id']
    review = client.get(details_url, params={'factory_id': FACTORY}).json()['prior_receipts']['L1']
    candidate, = review['items']
    assert not candidate['exact_reference'] and not candidate['blocks_posting'] and candidate['can_link']
    send(client, doc, [receipt(amount='20')], status=409)
    assert counts() == (0, 1)
    linked = client.post(details_url + '/link-receipt', json=receipt_link_request(doc, candidate))
    assert linked.status_code == 200, linked.text
    assert linked.json()['progress']['L1']['processed'] == '20'

    second = confirmed(client, headers, workbook(title='送货单 单号：DOC-002 2026-07-18'), source='DOC-002')
    second_url = BASE + '/documents/' + second['id']
    review = client.get(second_url, params={'factory_id': FACTORY}).json()['prior_receipts']['L1']
    resolved, = review['items']
    assert resolved['exact_reference'] and not resolved['blocks_posting'] and not resolved['can_link']
    assert client.post(second_url + '/link-receipt', json=receipt_link_request(second, resolved)).status_code == 409
    part = receipt(amount='12')
    send(client, second, [part], status=409)
    body = posting(second, workspace(client)['revision'], [part])
    body['manual_receipt_reviews'] = {'L1': review['review_token']}
    result, _ = send(client, second, [part], body=body)
    assert result['progress']['L1']['processed'] == '12' and counts() == (0, 2)


def test_exact_number_from_another_lot_requires_review_but_does_not_block_new_receiving(client):
    operation_post(client, operation_payload(client, 'RECEIPT', source_no='DOC-001', item_code='01-01-00001',
        unit='码', counterparty='测试供应商', lot='LOT-1', quantity='20'))
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[
        ['01-01-00001', '测试布料', '20', '码', 'LOT-1'],
        ['01-01-00001', '测试布料', '20', '码', 'LOT-2'],
    ]))
    url = BASE + '/documents/' + doc['id']
    reviews = client.get(url, params={'factory_id': FACTORY}).json()['prior_receipts']
    assert reviews['L1']['items'][0]['blocks_posting']
    other_lot, = reviews['L2']['items']
    assert other_lot['exact_reference'] and not other_lot['blocks_posting'] and not other_lot['can_link']
    part = receipt(line='L2', amount='15') | {'lot': 'LOT-2'}
    send(client, doc, [part], status=409)
    body = posting(doc, workspace(client)['revision'], [part])
    body['manual_receipt_reviews'] = {'L2': reviews['L2']['review_token']}
    posted, _ = send(client, doc, [part], body=body)
    assert posted['progress']['L1']['processed'] == '0' and posted['progress']['L2']['processed'] == '15'
    response = client.post(url + '/link-receipt', json=receipt_link_request(posted, reviews['L1']['items'][0]))
    assert response.status_code == 200, response.text
    assert response.json()['progress']['L1']['remaining'] == '0'
    assert counts() == (0, 2)


def test_historical_receipt_can_be_linked_after_supplier_deactivation(client):
    operation_post(client, operation_payload(client, 'RECEIPT', source_no='DOC-001', item_code='01-01-00001',
        unit='码', counterparty='测试供应商', lot='LOT-1', quantity='20'))
    issuer_record, headers = issuer(client)
    doc = confirmed(client, headers)
    master_url = '/api/fabric-warehouse/master'
    records = client.get(master_url, params=dict(factory_id=FACTORY, kind='SUPPLIER')).json()['items']
    master = next(row for row in records if row['id'] == issuer_record['supplier_id'])
    disabled = client.post(master_url, json=dict(factory_id=FACTORY, request_id=str(uuid4()),
        id=master['id'], expected_revision=master['revision'], kind='SUPPLIER', code=master['code'],
        name=master['name'], status='INACTIVE', data=master['data']))
    assert disabled.status_code == 200, disabled.text
    url = BASE + '/documents/' + doc['id']
    candidate, = client.get(url, params={'factory_id': FACTORY}).json()['prior_receipts']['L1']['items']
    response = client.post(url + '/link-receipt', json=receipt_link_request(doc, candidate))
    assert response.status_code == 200, response.text
    assert response.json()['progress']['L1']['processed'] == '20'
    assert counts() == (0, 1)


def test_concurrent_purchase_and_handover_entry_cannot_receive_the_same_note_twice(client):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    part = linked_part(client, doc, '30')
    linked_body = posting(doc, workspace(client)['revision'], [part])
    source = current(client, part['purchase_source_id'])
    manual_body = manual_request(source, delivery_reference=doc['data']['source_no'], batches=[
        {'quantity': '30', 'location': 'A01', 'dye_lot': 'LOT-1'}])
    requests = [lambda: client.post(BASE + '/documents/' + doc['id'] + '/post', json=linked_body),
        lambda: receive(client, source, manual_body)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda request: request(), requests))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert counts() == (0, 1)
    assert Decimal(current(client, source['id'])['warehouse_outstanding_quantity']) == 70


def test_concurrent_distinct_delivery_notes_share_purchase_versions_and_only_one_stale_form_succeeds(client):
    save(client, source_book())
    _, headers = issuer(client)
    first = confirmed(client, headers, source='DN-1')
    second = confirmed(client, headers, workbook(title='送货单 单号：DN-2 2026-07-18'), source='DN-2')
    revision = workspace(client)['revision']
    bodies = [posting(doc, revision, [linked_part(client, doc, '30')]) for doc in (first, second)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: client.post(BASE + '/documents/' + pair[0]['id'] + '/post', json=pair[1]), zip((first, second), bodies)))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert counts() == (0, 1)
    assert Decimal(stored(client)['items'][0]['warehouse_outstanding_quantity']) == 70


def test_ambiguous_matching_sources_require_explicit_choice_and_cannot_bypass_linking(client):
    save(client, book([row(供应商='测试供应商', 物料编码='01-01-00001', 入库数量=0, 交货明细='',
        订单号='PO-SAME', 生产单号='P001', 订单数量=ordered, 采购明细ID=f'LINE-{ordered}') for ordered in [2152, 5768]]))
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(
        headers=['订单号/货号', '物料编码', '物料名称', '数量', '单位', '缸号'],
        rows=[['PO-SAME/测试货号 下单5768码', '01-01-00001', '测试布料', '40', '码', '1#']],
    ))
    assert doc['data']['lines'][0]['purchase_order_no'] == 'PO-SAME'
    assert doc['data']['lines'][0]['ordered_quantity'] == '5768'
    choices = sources(client, doc)['L1']
    assert [choice['ordered_quantity'] for choice in choices] == ['5768', '2152']
    assert [choice['ordered_quantity_matches'] for choice in choices] == [True, False]
    assert all(choice['primary_match'] and not choice['suggested'] for choice in choices)
    send(client, doc, [receipt()], status=422)
    part = linked_part(client, doc, '15', target=0)
    wrong_split = linked_part(client, doc, '10', target=1)
    rejected, _ = send(client, doc, [part, wrong_split], status=422)
    assert '同一条采购来源' in rejected['detail']
    assert counts() == (0, 0)
    result, _ = send(client, doc, [part])
    assert Decimal(current(client, part['purchase_source_id'])['warehouse_received_quantity']) == 15
    assert sorted(Decimal(item['warehouse_received_quantity']) for item in stored(client)['items']) == [0, 15]
    assert counts() == (0, 1)


@pytest.mark.parametrize('line_refs, header_refs, status, first, exact_count', [
    ({'purchase_detail_id': 'system-2'}, {}, 'MATCHED', 'system-2', 1),
    ({'purchase_detail_id': 'upstream-2'}, {}, 'MATCHED', 'system-2', 1),
    ({'purchase_order_no': 'PO-2'}, {'purchase_order_no': 'PO-1'}, 'MATCHED', 'system-2', 1),
    ({'contract_no': 'C-2'}, {}, 'MATCHED', 'system-2', 1),
    ({'production_no': 'P-2'}, {}, 'MATCHED', 'system-2', 1),
    ({'contract_no': 'C-2', 'production_no': 'P-1', 'ordered_quantity': '2152'}, {}, 'CONFLICT', 'system-1', 0),
    ({'purchase_detail_id': 'missing', 'purchase_order_no': 'PO-2'}, {}, 'CONFLICT', 'system-2', 0),
    ({'purchase_order_no': 'missing', 'plan_no': 'PLAN-2'}, {}, 'NOT_FOUND', 'system-2', 0),
    ({'ordered_quantity': '5768.00'}, {}, 'NO_REFERENCE', 'system-2', 0),
])
def test_rank_purchase_choices_checks_all_primary_references_and_uses_hints_only_to_sort(
        line_refs, header_refs, status, first, exact_count):
    from app.schemas.material_handover import HandoverData, HandoverLine
    from app.services.material_handover_procurement import rank_purchase_choices

    line = HandoverLine(id='L1', **line_refs)
    choices = [
        (SimpleNamespace(id='system-1'), dict(source_line_id='system-2', order_no='PO-1', contract_no='C-1',
            production_no='P-1', plan_no='PLAN-1', ordered_quantity='2152')),
        (SimpleNamespace(id='system-2'), dict(source_line_id='upstream-2', order_no='PO-2', contract_no='C-2',
            production_no='P-2', plan_no='PLAN-2', ordered_quantity='5768')),
    ]
    result, ranked, count = rank_purchase_choices(HandoverData(**header_refs), line, choices)
    assert (result, ranked[0][0].id, count) == (status, first, exact_count)
    assert sum(exact for _, _, exact, _ in ranked) == exact_count


def test_stale_source_or_receipt_versions_and_wrong_identity_do_not_post_stock(client):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    part = linked_part(client, doc, '10')
    invalid = {**part, 'purchase_source_id': 'someone-elses-source'}
    send(client, doc, [invalid], status=422)
    send(client, doc, [{**part, 'expected_source_revision': part['expected_source_revision'] + 1}], status=409)
    source = current(client, part['purchase_source_id'])
    assert receive(client, source, manual_request(source, delivery_reference='OTHER-NOTE', batches=[
        {'quantity': '10', 'location': 'A01', 'dye_lot': 'LOT-1'}])).status_code == 200
    send(client, doc, [part], status=409)
    assert counts() == (1, 0)


def test_aggregate_overreceipt_and_any_invalid_physical_line_roll_back_all_changes(client):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[['01-01-00001', '测试布料', '100', '码', 'LOT-1'],
        ['01-01-00001', '测试布料', '100', '码', 'LOT-2']]))
    parts = [linked_part(client, doc, '70', 'L1'), linked_part(client, doc, '40', 'L2')]
    send(client, doc, parts, status=422)
    assert counts() == (0, 0)
    parts[1]['quantity'] = '20'
    parts[1]['location_id'] = 'missing-location'
    send(client, doc, parts, status=422)
    assert counts() == (0, 0)
    assert Decimal(current(client, parts[0]['purchase_source_id'])['warehouse_outstanding_quantity']) == 100
    parts[1]['location_id'] = 'fabric-A01'
    result, _ = send(client, doc, parts)
    assert Decimal(current(client, parts[0]['purchase_source_id'])['warehouse_outstanding_quantity']) == 10
    assert counts() == (0, 2)


def test_one_delivery_line_receives_into_two_warehouses_in_one_transaction(client):
    save(client, source_book(单价=8.5))
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(
        headers=['物料编码', '物料名称', '数量', '单位', '缸号', '单价', '币种', '计价单位'],
        rows=[['01-01-00001', '测试布料', '40', '码', 'LOT-1', 7, 'HKD', '码']],
    ))
    reference = {'unit_price': '8.5', 'price_unit': '码', 'currency': 'CNY'}
    assert sources(client, doc)['L1'][0]['purchase_price'] == reference
    location = client.post('/api/fabric-warehouse/master', json={
        'factory_id': FACTORY, 'request_id': str(uuid4()), 'kind': 'LOCATION', 'code': 'B-01',
        'name': 'B-01', 'status': 'ACTIVE', 'data': {'warehouse': '布料二仓', 'category': 'FABRIC'},
    })
    assert location.status_code == 200, location.text
    second_location_id = location.json()['id']
    first = linked_part(client, doc, '12.5')
    second = {**first, 'quantity': '17.5', 'location_id': second_location_id}
    send(client, doc, [first, {**second, 'quantity': '28'}], status=409)
    send(client, doc, [first, {**second, 'location_id': 'missing-location'}], status=422)
    assert counts() == (0, 0)
    assert workspace(client)['stock'] == []

    result, body = send(client, doc, [first, second])
    progress = result['progress']['L1']
    assert Decimal(progress['processed']) == 30
    assert Decimal(progress['remaining']) == 10
    assert result['data'] == doc['data']
    assert {item['location_id']: Decimal(item['quantity']) for item in workspace(client)['stock']} == {
        'fabric-A01': Decimal('12.5'), second_location_id: Decimal('17.5'),
    }
    assert Decimal(current(client, first['purchase_source_id'])['warehouse_outstanding_quantity']) == 70
    assert send(client, doc, [first, second], body=body)[0] == result
    assert counts() == (0, 2)

    save(client, source_book(单价=9.25))
    assert sources(client, result)['L1'][0]['purchase_price']['unit_price'] == '9.25'
    history = client.get(PURCHASE + '/receipts', params={'factory_id': FACTORY, 'unified': 'true'})
    assert history.status_code == 200, history.text
    monthly = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-07'})
    assert monthly.status_code == 200, monthly.text
    for rows in (history.json()['items'], monthly.json()['details']):
        assert len(rows) == 2
        for item in rows:
            assert item['purchase_price'] == reference
            assert (item['unit_price'], item['currency'], item['price_unit']) == ('7', 'HKD', '码')
            assert not item.get('amount')

    public_doc = client.get(BASE + '/external/documents/' + doc['id'], headers=headers)
    assert public_doc.status_code == 200, public_doc.text
    assert 'purchase_price' not in public_doc.text
    public_report = client.get(BASE + '/external/monthly', headers=headers, params={'month': '2026-07'})
    assert public_report.status_code == 200, public_report.text
    assert 'purchase_price' not in public_report.text and public_report.json()['details'][0]['unit_price'] == '7'


def test_correction_restores_pending_and_document_remainder_without_rewriting_history(client):
    batch = save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    part = linked_part(client, doc, '30')
    result, _ = send(client, doc, [part])
    before = current(client, part['purchase_source_id'])
    old_manual = manual_request(before, delivery_reference='AFTER-CORRECTION', batches=[
        {'quantity': '10', 'location': 'A01', 'dye_lot': 'LOT-1'}])
    original = result['movements'][0]['operation_id']
    operation_post(client, operation_payload(client, 'CORRECTION', original_id=original,
        reason='核对原件后全额冲回', business_date='2026-08-01'))
    progress = current(client, part['purchase_source_id'])
    assert Decimal(progress['warehouse_received_quantity']) == 0
    assert Decimal(progress['warehouse_outstanding_quantity']) == 100
    assert progress['receipt_count'] == 1
    assert progress['revision'] == before['revision'] + 1
    assert receive(client, before, old_manual).status_code == 409
    assert stored(client, view='OUTSTANDING')['total'] == 1
    assert undo_preview(client, batch).status_code == 409
    doc = client.get(BASE + '/documents/' + doc['id'], params={'factory_id': FACTORY}).json()
    assert Decimal(doc['progress']['L1']['remaining']) == 40
    july = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-07'}).json()
    august = client.get('/api/warehouse-operations/fabric/monthly', params={'factory_id': FACTORY, 'month': '2026-08'}).json()
    assert sum(Decimal(item['quantity']) for item in july['details']) == 30
    assert sum(Decimal(item['quantity']) for item in august['details']) == -30


def test_source_permissions_are_rechecked_and_public_portal_cannot_read_purchase_candidates(client, monkeypatch):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(
        headers=['物料编码', '物料名称', '数量', '单位', '缸号', '采购明细ID'],
        rows=[['01-01-00001', '测试布料', '40', '码', 'LOT-1', 'K1']],
    ))
    assert doc['data']['lines'][0]['purchase_detail_id'] == ''
    assert sources(client, doc)['L1'][0]['suggested'] is True
    detail = client.get(BASE + '/documents/' + doc['id'], params={'factory_id': FACTORY}).json()
    assert detail['data']['lines'][0]['purchase_detail_id'] == 'K1'
    part = linked_part(client, doc, '10')
    # There is deliberately no public /external purchase-source endpoint.
    assert client.get(BASE + '/external/documents/' + doc['id'] + '/purchase-sources', headers=headers).status_code != 200
    module = importlib.import_module('app.services.material_handover_procurement')
    original = module.can
    monkeypatch.setattr(module, 'can', lambda actor, permission, *args: False if permission.startswith('fabric_warehouse:') else original(actor, permission, *args))
    assert client.get(BASE + '/documents/' + doc['id'] + '/purchase-sources', params={'factory_id': FACTORY}).status_code == 403
    send(client, doc, [part], status=403)
    assert counts() == (0, 0)


@pytest.mark.parametrize('linked', [False, True])
def test_re_receiving_cannot_predate_the_same_handover_line_reversal(client, linked):
    if linked:
        save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    part = linked_part(client, doc, '30') if linked else receipt(amount='30')
    result, original_body = send(client, doc, [part])
    operation_post(client, operation_payload(client, 'CORRECTION',
        original_id=result['movements'][0]['operation_id'], reason='实收数量录错', business_date='2026-08-01'))
    doc = client.get(BASE + '/documents/' + doc['id'], params={'factory_id': FACTORY}).json()
    part = linked_part(client, doc, '20') if linked else receipt(amount='20')
    replacement = posting(doc, workspace(client)['revision'], [part])
    response, _ = send(client, doc, [part], status=409, body=replacement)
    assert '冲销日期' in response['detail']
    assert counts() == (0, 2)
    assert send(client, doc, [part], body=original_body)[0] == result
    replacement['business_date'] = '2026-08-01'
    send(client, doc, [part], body=replacement)
    assert sum(Decimal(item['quantity']) for item in workspace(client)['stock']) == 20
    if linked:
        assert Decimal(current(client, part['purchase_source_id'])['warehouse_received_quantity']) == 20
    for month, expected in [('2026-07', 30), ('2026-08', -10)]:
        report = client.get('/api/warehouse-operations/fabric/monthly',
            params={'factory_id': FACTORY, 'month': month}).json()
        assert sum(Decimal(item['quantity']) for item in report['details']) == expected


def test_uploaded_note_preserves_original_manual_correction_path(client):
    original_body = operation_payload(client, 'RECEIPT', source_no='DOC-001', item_code='01-01-00001',
        unit='码', counterparty='测试供应商', quantity='20')
    original = operation_post(client, original_body)
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    operation_post(client, operation_payload(client, 'CORRECTION', original_id=original['id'],
        reason='更正原手工实收', business_date='2026-08-01'))
    replacement = {**original_body, 'request_id': str(uuid4()), 'expected_revision': workspace(client)['revision'],
        'quantity': '15'}
    response = operation_post(client, replacement, status=409)
    assert '冲销日期' in response['detail']
    replacement['business_date'] = '2026-08-01'
    operation_post(client, {**replacement, 'source_line': 'another-line'}, status=409)
    corrected = operation_post(client, replacement)
    assert corrected['data']['replaces_id'] == original['id']
    assert operation_post(client, replacement) == corrected
    send(client, doc, [receipt(amount='15')], status=409)
    operation_post(client, {**replacement, 'request_id': str(uuid4()),
        'expected_revision': workspace(client)['revision']}, status=409)
    assert counts() == (0, 3)
    assert sum(Decimal(item['quantity']) for item in workspace(client)['stock']) == 15


def test_receipt_observations_follow_splits_and_post_only_the_net(client):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    first = {**linked_part(client, doc, '12'), 'receipt_counts': {
        'counted_quantity': '14', 'damaged_quantity': '1', 'rejected_quantity': '1',
    }}
    zero = {**receipt(amount='0', location=''), 'receipt_counts': {'counted_quantity': '3', 'rejected_quantity': '3'}}
    second = {**first, 'quantity': '18', 'roll_no': 'R2', 'receipt_counts': {
        'counted_quantity': '20', 'other_unusable_quantity': '2',
    }}
    body = posting(doc, workspace(client)['revision'], [first, zero, second])
    body['delivery_quantities'] = {'L1': '40'}
    url = BASE + '/documents/' + doc['id'] + '/post'
    wrong_net = {**body, 'lines': [{**first, 'quantity': '13'}, zero, second]}
    assert client.post(url, json=wrong_net).status_code == 422
    too_small = {**body, 'delivery_quantities': {'L1': '36'}}
    assert client.post(url, json=too_small).status_code == 422
    assert counts() == (0, 0)

    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['progress']['L1'] == {'processed': '30', 'remaining': '10'}
    assert result['data'] == doc['data']
    assert counts() == (0, 2)
    assert Decimal(current(client, first['purchase_source_id'])['warehouse_outstanding_quantity']) == 70
    observation = result['receipt_observations'][0]['lines'][0]
    assert (observation['delivered_quantity'], observation['shortage_quantity']) == ('40', '3')
    assert [part['accepted_quantity'] for part in observation['parts']] == ['12', '0', '18']
    assert observation['parts'][0]['damaged_quantity'] == '1'
    assert observation['parts'][1]['rejected_quantity'] == '3'
    assert 'operation_id' not in observation['parts'][1]
    assert observation['parts'][2]['other_unusable_quantity'] == '2'
    assert 'full_rejection' not in observation and 'receipt_rejection' not in result
    assert client.post(url, json=body).json() == result
    changed = {**body, 'delivery_quantities': {'L1': '41'}}
    assert client.post(url, json=changed).status_code == 409
    scan = client.post(BASE + '/scan', json={'factory_id': FACTORY, 'code': doc['code']})
    assert scan.json()['receipt_observations'] == result['receipt_observations']
    public = client.get(BASE + '/external/documents/' + doc['id'], headers=headers)
    assert public.status_code == 200
    assert 'receipt_observations' not in public.json()


def test_zero_net_receipt_saves_a_difference_without_moving_stock_or_purchase(client, monkeypatch):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    part = {**receipt(amount='0', location=''), 'receipt_counts': {'counted_quantity': '40', 'rejected_quantity': '40'}}
    source_id = sources(client, doc)['L1'][0]['id']
    url = BASE + '/documents/' + doc['id'] + '/post'
    original_revision = workspace(client)['revision']
    body = posting(doc, original_revision, [part])
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['revision'] == doc['revision'] + 1
    assert result['progress'] == doc['progress']
    assert result['movements'] == []
    assert result['receipt_observations'][0]['lines'][0]['parts'][0]['rejected_quantity'] == '40'
    assert result['receipt_rejection'] == {'rejected_quantity': '40', 'unit': '码', 'status': None}
    assert counts() == (0, 0)
    assert workspace(client)['revision'] == original_revision
    assert Decimal(current(client, source_id)['warehouse_outstanding_quantity']) == 100
    assert client.post(url, json=body).json() == result
    stale = {**body, 'request_id': str(uuid4())}
    assert client.post(url, json=stale).status_code == 409
    assert client.get(BASE + '/documents/' + doc['id'], params={'factory_id': FACTORY}).json()['receipt_observations'] == result['receipt_observations']

    detail_url = BASE + '/documents/' + doc['id']
    pending_url = BASE + '/pending-deliveries'
    pending, = client.get(pending_url, params={'factory_id': FACTORY}).json()['items']
    assert pending['processing_status'] == 'PENDING' and pending['receipt_rejection'] == result['receipt_rejection']
    list_row, = client.get(BASE + '/documents', params={'factory_id': FACTORY}).json()['items']
    assert list_row['receipt_rejection'] == result['receipt_rejection']

    followup_url = detail_url + '/rejection-followup'
    followup = dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=result['revision'],
        observation_request_id=body['request_id'], line_id='L1', status='PENDING_REDELIVERY', reason='请供应商补送')
    assert client.post(followup_url, json={**followup, 'factory_id': 'huakang-b'}).status_code == 422
    assert client.post(followup_url, json={**followup, 'observation_request_id': str(uuid4())}).status_code == 422
    service = importlib.import_module('app.services.material_handover')
    can = service.can
    with monkeypatch.context() as scope:
        scope.setattr(service, 'can', lambda actor, permission, *args: permission != 'fabric_operations:operate' and can(actor, permission, *args))
        assert client.post(followup_url, json=followup).status_code == 403
    saved = client.post(followup_url, json=followup)
    assert saved.status_code == 200, saved.text
    pending = saved.json()
    assert pending['revision'] == result['revision'] + 1
    assert pending['progress'] == doc['progress'] and pending['receipt_rejection']['status'] == 'PENDING_REDELIVERY'
    event = pending['receipt_observations'][0]['lines'][0]['full_rejection']['followup']
    assert event['reason'] == followup['reason'] and event['actor_name'] and event['recorded_at']
    assert client.post(followup_url, json=followup).json() == pending
    assert client.post(followup_url, json={**followup, 'reason': '不同内容'}).status_code == 409
    assert client.post(followup_url, json={**followup, 'request_id': str(uuid4())}).status_code == 409

    closed = client.post(followup_url, json={**followup, 'request_id': str(uuid4()),
        'expected_revision': pending['revision'], 'status': 'RESOLVED', 'reason': '已核对本次差异'})
    assert closed.status_code == 200, closed.text
    resolved = closed.json()
    assert resolved['receipt_rejection']['status'] == 'RESOLVED' and resolved['processing_status'] == 'PENDING'
    assert resolved['progress'] == doc['progress'] and resolved['movements'] == []
    assert workspace(client)['revision'] == original_revision
    assert Decimal(current(client, source_id)['warehouse_outstanding_quantity']) == 100
    assert client.get(detail_url, params={'factory_id': FACTORY}).json()['receipt_observations'] == resolved['receipt_observations']
    for external_url in (BASE + '/external/documents/' + doc['id'], BASE + '/external/documents'):
        public = client.get(external_url, headers=headers).json()
        assert 'receipt_rejection' not in public.get('items', [public])[0]
        assert 'receipt_observations' not in public.get('items', [public])[0]

    redelivery, _ = send(client, resolved, [linked_part(client, resolved, '40')])
    assert redelivery['progress']['L1'] == {'processed': '40', 'remaining': '0'}
    assert redelivery['processing_status'] == 'COMPLETE' and redelivery['receipt_rejection']['status'] == 'RESOLVED'
    assert len(redelivery['movements']) == 1
    assert Decimal(current(client, source_id)['warehouse_outstanding_quantity']) == 60


def test_new_empty_posting_fields_preserve_original_retry_hash():
    from app.schemas.material_handover import PostingInput
    from app.services.material_handover import request_signature
    from app.services.fabric_procurement_parser import digest
    original = dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=3,
        expected_inventory_revision=0, code_version=1, business_date='2026-07-18',
        lines=[dict(line_id='L1', quantity='10', batch_id='', location_id='fabric-A01', lot='LOT-1', roll_no='')])
    assert request_signature('POST', 'MHD-old', PostingInput(**original)) == digest(['POST', 'MHD-old', original])
