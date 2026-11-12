"""Document search filters the authorized metadata set before pagination."""
import importlib
import json
from datetime import date, timedelta
from uuid import uuid4

from test_material_handover import client, issuer, confirmed, upload, workbook, posting, receipt, BASE, FACTORY


def listing(client, headers=None, **params):
    path = BASE + ('/external/documents' if headers else '/documents')
    result = client.get(path, headers=headers, params={**({} if headers else {'factory_id': FACTORY}), **params})
    assert result.status_code == 200, result.text
    return result.json()


def test_warehouse_sees_confirmed_supplier_documents_but_supplier_drafts_stay_private(client):
    first, headers = issuer(client, '甲供应商')
    second, other = issuer(client, '乙供应商')
    _, requestor = issuer(client, '裁床车间', 'REQUESTOR')
    a = confirmed(client, headers, source='SHIP-A')
    b = upload(client, other)
    c = upload(client, requestor)
    internal = client.post(BASE + '/documents/upload', data={'factory_id': FACTORY, 'request_id': str(uuid4())},
        files={'file': ('仓库原件.xlsx', workbook(title='送货单 单号：INTERNAL 2026-07-18'), 'application/octet-stream')})
    assert internal.status_code == 200, internal.text
    assert listing(client)['total'] == 3
    assert listing(client, supplier_id=first['supplier_id'])['items'][0]['id'] == a['id']
    assert listing(client, supplier_id=second['supplier_id'], status='DRAFT')['total'] == 0
    assert listing(client, headers=other, status='DRAFT')['items'][0]['id'] == b['id']
    assert listing(client, kind='ISSUE')['items'][0]['id'] == c['id']
    assert listing(client, search='ship-a', status='CONFIRMED', kind='DELIVERY')['total'] == 1
    assert listing(client, search='测试布料')['total'] == 3
    assert listing(client, headers=headers, status='CONFIRMED')['items'][0]['id'] == a['id']
    # Unknown supplier query parameters never override the external token's ownership scope.
    assert listing(client, headers=other, search='SHIP-A', supplier_id=first['supplier_id'])['total'] == 0
    assert listing(client, headers=headers, search='INTERNAL')['total'] == 0
    assert listing(client, headers=headers, kind='ISSUE')['total'] == 0
    assert listing(client, headers=headers)['total'] == 1
    assert client.get(BASE + '/external/documents/' + internal.json()['id'], headers=headers).status_code == 404
    assert client.get(BASE + '/documents', params={'factory_id': 'huakang-b'}).status_code == 422
    assert client.get(BASE + '/documents', params={'factory_id': FACTORY, 'status': 'invalid'}).status_code == 422


def test_search_pagination_finds_older_documents_and_returns_only_list_metadata(client):
    party, headers = issuer(client)
    original = upload(client, headers)
    database = importlib.import_module('app.db')
    model = importlib.import_module('app.models.material_handover').HandoverDocument
    with database.SessionLocal() as db:
        # More than one page, with the only search matches at the end of the unfiltered ordering.
        for index in range(55):
            body = {**original['data'], 'source_no': f'BULK-{index}', 'production_no': 'FIND-ME' if index < 2 else ''}
            db.add(model(id=f'fixture-{index:02d}', factory_id=FACTORY, issuer_id=party['id'],
                owner_key='issuer:' + party['id'], status='CONFIRMED', revision=2, code_version=1,
                data_json=json.dumps(body), extraction_json='{}', created_at='2026-01-01',
                updated_at=(date(2026, 1, 1) + timedelta(days=index)).isoformat()))
        db.commit()
    assert listing(client)['total'] == 55
    first = listing(client, search=' find-me ', supplier_id=party['supplier_id'], limit=1)
    second = listing(client, search='find-me', supplier_id=party['supplier_id'], limit=1, offset=1)
    assert first['total'] == second['total'] == 2
    assert [first['items'][0]['data']['source_no'], second['items'][0]['data']['source_no']] == ['BULK-1', 'BULK-0']
    assert listing(client, headers=headers, search='find-me', offset=2)['items'] == []
    assert 'lines' not in first['items'][0]['data']
    assert not {'raw_text', 'extraction_json', 'owner_key', 'bound_supplier_id'} & first['items'][0].keys()


def test_staff_delivery_list_tracks_effective_receipts_and_includes_void_history(client):
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    voided = confirmed(client, headers, workbook(title='送货单 单号：VOIDED 2026-07-18'), source='VOIDED')
    result = client.post(BASE + '/external/documents/' + voided['id'] + '/void', headers=headers, json={
        'request_id': str(uuid4()), 'expected_revision': voided['revision'], 'reason': '取消未送货单据',
    })
    assert result.status_code == 200, result.text

    rows = {item['id']: item for item in listing(client)['items']}
    assert rows[doc['id']]['processing_status'] == 'PENDING'
    assert rows[voided['id']]['status'] == 'VOID'
    assert 'processing_status' not in rows[voided['id']]
    assert all('processing_status' not in item for item in listing(client, headers=headers)['items'])

    url = BASE + '/documents/' + doc['id'] + '/post'
    first = client.post(url, json=posting(doc, 0, [receipt(amount='15')]))
    assert first.status_code == 200, first.text
    assert listing(client, search='DOC-001')['items'][0]['processing_status'] == 'PARTIAL'
    second = client.post(url, json=posting(first.json(), 1, [receipt(amount='25')]))
    assert second.status_code == 200, second.text
    assert listing(client, search='DOC-001')['items'][0]['processing_status'] == 'COMPLETE'

    reversed_receipt = client.post('/api/warehouse-operations/fabric/documents', json={
        'factory_id': FACTORY, 'request_id': str(uuid4()), 'expected_revision': 2,
        'kind': 'CORRECTION', 'business_date': '2026-07-18',
        'original_id': first.json()['movements'][0]['operation_id'], 'reason': '复核后冲回本批实收',
    })
    assert reversed_receipt.status_code == 200, reversed_receipt.text
    assert listing(client, search='DOC-001')['items'][0]['processing_status'] == 'PARTIAL'
