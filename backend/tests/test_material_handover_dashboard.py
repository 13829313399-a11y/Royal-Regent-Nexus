"""Dashboard counts use confirmed documents and effective stock, including reversals."""
import importlib
from uuid import uuid4

from test_material_handover import client, issuer, confirmed, upload, workbook, posting, receipt, workspace, BASE, FACTORY


def report(client, **params):
    result = client.get(BASE + '/pending-deliveries', params={'factory_id': FACTORY, **params})
    assert result.status_code == 200, result.text
    assert 'no-store' in result.headers['cache-control']
    return result.json()


def test_pending_counts_documents_excluding_drafts_voids_requests_and_completed(client):
    _, headers = issuer(client)
    upload(client, headers, workbook(title='送货单 单号：DRAFT 2026-07-18'))
    first = confirmed(client, headers, workbook(title='送货单 单号：PENDING 2026-07-18'), source='PENDING')
    second = confirmed(client, headers, workbook(rows=[['A','布A',20,'码','A'], ['B','布B',10,'码','B']]), source='PARTIAL')
    result = client.post(BASE + '/documents/' + second['id'] + '/post', json=posting(second, 0, [receipt(amount='5')]))
    assert result.status_code == 200, result.text
    _, request_headers = issuer(client, '领用车间', 'REQUESTOR')
    confirmed(client, request_headers, source='ISSUE')
    voided = confirmed(client, headers, workbook(title='送货单 单号：VOID 2026-07-18'), source='VOID')
    result = client.post(BASE + '/documents/' + voided['id'] + '/actions/void', params={'factory_id': FACTORY}, json={
        'request_id': str(uuid4()), 'expected_revision': voided['revision'], 'reason': '取消未送货单据'})
    assert result.status_code == 200, result.text
    done = confirmed(client, headers, workbook(title='送货单 单号：COMPLETE 2026-07-18'), source='COMPLETE')
    result = client.post(BASE + '/documents/' + done['id'] + '/post', json=posting(done, 1, [receipt(amount='40')]))
    assert result.status_code == 200, result.text
    page = report(client, limit=1)
    assert page['total'] == 2 and len(page['items']) == 1
    next_page = report(client, limit=1, offset=1)
    rows = page['items'] + next_page['items']
    assert {row['id'] for row in rows} == {first['id'], second['id']}
    partial = next(row for row in rows if row['id'] == second['id'])
    assert partial['pending_line_count'] == 2 and partial['processing_status'] == 'PARTIAL'
    assert all('lines' not in row['data'] and 'raw_text' not in row and 'code' not in row for row in rows)


def test_complete_reversal_restores_pending_and_keeps_exact_unit_totals(client):
    _, headers = issuer(client)
    first = confirmed(client, headers, workbook(rows=[['A','布料','0.1','码','A']]), source='FIRST')
    result = client.post(BASE + '/documents/' + first['id'] + '/post', json=posting(first, 0, [receipt(amount='0.1')]))
    assert result.status_code == 200, result.text
    original = workspace(client)['documents'][0]['id']
    for index, (value, unit) in enumerate([('0.2', '码'), ('0.3', '米')], 1):
        doc = confirmed(client, headers, workbook(rows=[['A','布料',value,unit,'A']]), source=f'NEXT-{index}')
        result = client.post(BASE + '/documents/' + doc['id'] + '/post', json=posting(doc, index, [receipt(amount=value)]))
        assert result.status_code == 200, result.text
    result = report(client)
    assert result['total'] == 0
    assert {r['unit']: r['quantity'] for r in result['stock_totals']} == {'码': '0.3', '米': '0.3'}
    reversed_result = client.post('/api/warehouse-operations/fabric/documents', json=dict(
        factory_id=FACTORY, request_id=str(uuid4()), expected_revision=3, kind='CORRECTION',
        business_date='2026-07-18', original_id=original, reason='核实实收后纠正'))
    assert reversed_result.status_code == 200, reversed_result.text
    result = report(client)
    assert result['total'] == 1 and result['items'][0]['id'] == first['id']
    assert result['items'][0]['processing_status'] == 'PENDING'
    assert {r['unit']: r['quantity'] for r in result['stock_totals']} == {'码': '0.2', '米': '0.3'}


def test_pending_dashboard_preserves_staff_and_factory_guards(client, monkeypatch):
    assert client.get(BASE + '/pending-deliveries', params={'factory_id': 'huakang-b'}).status_code == 422
    service = importlib.import_module('app.services.material_handover')
    monkeypatch.setattr(service, 'can', lambda *args: False)
    assert client.get(BASE + '/pending-deliveries', params={'factory_id': FACTORY}).status_code == 403
    client.cookies.clear()
    assert client.get(BASE + '/pending-deliveries', params={'factory_id': FACTORY}).status_code == 401
