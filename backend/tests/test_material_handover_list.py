"""Document search filters the authorized metadata set before pagination."""
import importlib
import json
from datetime import date, timedelta
from uuid import uuid4

from test_material_handover import client, issuer, confirmed, upload, workbook, BASE, FACTORY


def listing(client, headers=None, **params):
    path = BASE + ('/external/documents' if headers else '/documents')
    result = client.get(path, headers=headers, params={**({} if headers else {'factory_id': FACTORY}), **params})
    assert result.status_code == 200, result.text
    return result.json()


def test_warehouse_sees_all_issuers_but_supplier_queries_keep_original_ownership(client):
    first, headers = issuer(client, '甲供应商')
    second, other = issuer(client, '乙供应商')
    _, requestor = issuer(client, '裁床车间', 'REQUESTOR')
    a = confirmed(client, headers, source='SHIP-A')
    b = upload(client, other)
    c = upload(client, requestor)
    internal = client.post(BASE + '/documents/upload', data={'factory_id': FACTORY, 'request_id': str(uuid4())},
        files={'file': ('仓库原件.xlsx', workbook(title='送货单 单号：INTERNAL 2026-07-18'), 'application/octet-stream')})
    assert internal.status_code == 200, internal.text
    assert listing(client)['total'] == 4
    assert listing(client, supplier_id=first['supplier_id'])['items'][0]['id'] == a['id']
    assert listing(client, supplier_id=second['supplier_id'], status='DRAFT')['items'][0]['id'] == b['id']
    assert listing(client, kind='ISSUE')['items'][0]['id'] == c['id']
    assert listing(client, search='ship-a', status='CONFIRMED', kind='DELIVERY')['total'] == 1
    assert listing(client, search='测试布料')['total'] == 4
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
                owner_key='issuer:' + party['id'], status='DRAFT', revision=1, code_version=0,
                data_json=json.dumps(body), extraction_json='{}', created_at='2026-01-01',
                updated_at=(date(2026, 1, 1) + timedelta(days=index)).isoformat()))
        db.commit()
    assert listing(client)['total'] == 56
    first = listing(client, search=' find-me ', supplier_id=party['supplier_id'], limit=1)
    second = listing(client, search='find-me', supplier_id=party['supplier_id'], limit=1, offset=1)
    assert first['total'] == second['total'] == 2
    assert [first['items'][0]['data']['source_no'], second['items'][0]['data']['source_no']] == ['BULK-1', 'BULK-0']
    assert listing(client, headers=headers, search='find-me', offset=2)['items'] == []
    assert 'lines' not in first['items'][0]['data']
    assert not {'raw_text', 'extraction_json', 'owner_key', 'bound_supplier_id'} & first['items'][0].keys()
