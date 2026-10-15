import importlib
from decimal import Decimal
from uuid import uuid4
import pytest
from test_material_handover import client
from test_fabric_receipt_corrections import original, reverse
from test_warehouse_operations import workspace, payload, post
from test_material_handover_procurement import source_book, issuer, confirmed, workbook, linked_part, send
from test_fabric_procurement_tracking import save
from test_fabric_procurement import stored
from test_fabric_receiving import request, receive


def report(client, **params):
    response = client.get('/api/warehouse-operations/fabric/order-summary', params={'factory_id': 'huakang-c', **params})
    assert response.status_code == 200, response.text
    return response.json()


def total(client):
    return sum((Decimal(row['quantity']) for row in workspace(client)['stock']), Decimal(0))


def test_original_split_receipt_issue_reversal_return_transfer_and_period_balance(client):
    source, receipt, _, _ = original(client)
    batch = receipt['batches'][0]['id']
    issue = post(client, payload(client, 'ISSUE', batch_id=batch, quantity='8', business_date='2026-10-10', counterparty='裁床一'))
    post(client, payload(client, 'CORRECTION', original_id=issue['id'], reason='领用方录错', business_date='2026-10-11'))
    issue2 = post(client, payload(client, 'ISSUE', batch_id=batch, quantity='6', business_date='2026-10-11', counterparty='车间二'))
    returned = post(client, payload(client, 'RETURN', original_id=issue2['id'], quantity='2', business_date='2026-10-11'))
    transfer = post(client, payload(client, 'TRANSFER', batch_id=returned['id'], quantity='1', location='A02', business_date='2026-10-12'))
    post(client, payload(client, 'CORRECTION', original_id=transfer['id'], reason='目标仓位录错', business_date='2026-10-12'))
    result = report(client, date_from='2026-10-01', date_to='2026-10-31')
    assert len(result['rows']) == 1
    row = result['rows'][0]
    assert row['source_line_id'] == source['id']
    assert {key: Decimal(row[key]) for key in ('opening', 'inbound', 'outbound', 'adjustment', 'balance')} == dict(opening=50, inbound=0, outbound=6, adjustment=2, balance=46)
    assert Decimal(row['balance']) == total(client)
    assert [Decimal(row['quantity']) for row in result['details'] if row['mode'] == 'OUTBOUND'] == [Decimal(6), Decimal(-8), Decimal(8)]
    assert len([row for row in result['details'] if row['mode'] == 'ADJUSTMENT']) == 3
    assert all(Decimal(row['quantity']) == 0 for row in result['details'] if '调仓' in row['label'])
    # Recipient search selects the order identity, never omits its earlier receipt.
    found = report(client, date_from='2026-10-01', search='车间二')
    assert found['rows'][0]['opening'] == row['opening'] and found['rows'][0]['balance'] == row['balance']
    assert len(found['details']) == len(result['details'])


def test_cross_month_original_receipt_correction_and_same_paper_reentry(client):
    source, receipt, _, _ = original(client)
    assert reverse(client, receipt)[0].status_code == 200
    source = stored(client)['items'][0]
    assert receive(client, source, request(source, receipt_date='2026-10-10', batches=[dict(quantity='7', location='A01', dye_lot='1')])).status_code == 200
    september = report(client, date_to='2026-09-30')['rows'][0]
    october = report(client, date_from='2026-10-01', date_to='2026-10-31')['rows'][0]
    assert Decimal(september['inbound']) == 50 and Decimal(september['balance']) == 50
    assert Decimal(october['opening']) == 50 and Decimal(october['inbound']) == -43 and Decimal(october['balance']) == total(client) == 7


def test_linked_scan_and_unlinked_manual_units_are_distinct_and_not_double_counted(client):
    save(client, source_book())
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[['01-01-00001', '测试布料', '100', '码', 'LOT-1']]))
    send(client, doc, [linked_part(client, doc, '80')])
    direct = post(client, payload(client, 'RECEIPT', unit='件', material_category='ACCESSORY', quantity='3'))
    post(client, payload(client, 'ISSUE', batch_id=direct['id'], quantity='1'))
    result = report(client)
    assert len(result['rows']) == 2
    assert {row['unit']: Decimal(row['balance']) for row in result['totals']} == {'码': Decimal(80), '件': Decimal(2)}
    assert sum(Decimal(row['balance']) for row in result['rows']) == total(client)
    assert any(not row['linked'] and not row['order_no'] for row in result['rows'])
    assert len([row for row in result['details'] if row['mode'] == 'INBOUND']) == 2
    linked = next(row for row in result['rows'] if row['linked'])
    assert linked['supplier'] == '测试供应商' and linked['order_no']
    subset = report(client, supplier='测试供应商')
    assert len(subset['rows']) == 1 and subset['rows'][0]['key'] == linked['key']


def test_order_summary_scope_and_invalid_dates_are_read_only(client, monkeypatch):
    assert client.get('/api/warehouse-operations/fabric/order-summary', params={'factory_id': 'huakang-a'}).status_code == 422
    for params in ({'date_from': '2026-02-30'}, {'date_from': '2026-10-10', 'date_to': '2026-10-01'}):
        assert client.get('/api/warehouse-operations/fabric/order-summary', params={'factory_id': 'huakang-c', **params}).status_code == 422
    assert total(client) == 0
    api = importlib.import_module('app.api.warehouse_operations')
    monkeypatch.setattr(api, 'can', lambda *args, **kwargs: False)
    assert client.get('/api/warehouse-operations/fabric/order-summary', params={'factory_id': 'huakang-c'}).status_code == 403
