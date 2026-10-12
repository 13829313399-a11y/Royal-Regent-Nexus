"""Public document isolation and atomic integration with the existing fabric ledger."""
import copy
import importlib
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from warehouse_location_fixtures import make_client
from test_molding_sample_api import login_as

BASE = '/api/material-handover'
FACTORY = 'huakang-c'


def workbook(headers=None, rows=None, title='送货单 单号：DOC-001 2026-07-18'):
    book = Workbook(); sheet = book.active
    sheet.append([title])
    sheet.append(headers or ['物料编码', '物料名称', '数量', '单位', '缸号'])
    for row in rows or [['01-01-00001', '测试布料', '40', '码', 'LOT-1']]:
        sheet.append(row)
    out = BytesIO(); book.save(out)
    return out.getvalue()


@pytest.fixture
def client(monkeypatch):
    with make_client(monkeypatch) as instance:
        parser = importlib.import_module('app.services.material_handover_parser')
        files = importlib.import_module('app.services.material_handover_files')
        monkeypatch.setattr(files, 'extract', parser.parse)
        login_as(instance, 'admin')
        yield instance


def issuer(client, name='测试供应商', kind='SUPPLIER'):
    supplier_id=''
    if kind=='SUPPLIER':
        records=client.get('/api/fabric-warehouse/master',params=dict(factory_id=FACTORY,kind='SUPPLIER')).json()['items']
        found=next((row for row in records if row['name']==name),None)
        if not found:
            created=client.post('/api/fabric-warehouse/master',json=dict(factory_id=FACTORY,request_id=str(uuid4()),
                id=None,expected_revision=0,kind='SUPPLIER',code='SUP-'+uuid4().hex,name=name,status='ACTIVE',data={}))
            assert created.status_code==200,created.text
            found=created.json()
        supplier_id=found['id']
    result = client.post(BASE + '/issuers', json=dict(factory_id=FACTORY, name=name, supplier_id=supplier_id,kind=kind, valid_days=30))
    assert result.status_code == 200, result.text
    return result.json(), {'X-Handover-Key': result.json()['token']}


def upload(client, headers, content=None):
    result = client.post(BASE + '/external/documents/upload', headers=headers,
        data={'request_id': str(uuid4())}, files={'file': ('任意送货单.xlsx', content or workbook(), 'application/octet-stream')})
    assert result.status_code == 200, result.text
    return result.json()


def confirmed(client, headers, content=None, source='DOC-001'):
    doc = upload(client, headers, content)
    body = copy.deepcopy(doc['data']); body.update(source_no=source, document_date='2026-07-18')
    result = client.put(BASE + '/external/documents/' + doc['id'], headers=headers,
        json=dict(request_id=str(uuid4()), expected_revision=doc['revision'], data=body))
    assert result.status_code == 200, result.text
    doc = result.json()
    result = client.post(BASE + '/external/documents/' + doc['id'] + '/confirm', headers=headers,
        json=dict(request_id=str(uuid4()), expected_revision=doc['revision'], acknowledge_warnings=True))
    assert result.status_code == 200, result.text
    return result.json()


def workspace(client):
    result = client.get(BASE + '/workspace', params={'factory_id': FACTORY})
    assert result.status_code == 200, result.text
    return result.json()['inventory']


def posting(doc, revision, lines):
    return dict(factory_id=FACTORY, request_id=str(uuid4()), expected_revision=doc['revision'],
        expected_inventory_revision=revision, code_version=doc['code_version'], business_date='2026-07-18', lines=lines)


def receipt(line='L1', amount='15', location='fabric-A01'):
    return dict(line_id=line, quantity=amount, location_id=location, lot='LOT-1')


def test_partial_receipts_replay_overflow_and_immutable_evidence(client):
    _, headers = issuer(client)
    doc = confirmed(client, headers)
    assert doc['code'].startswith('MH1:')
    assert workspace(client)['stock'] == []  # confirmation alone never moves inventory
    assert client.get(BASE + '/external/documents/' + doc['id'] + '/qr', headers=headers).content.startswith(b'<?xml')
    assert client.post(BASE + '/scan', json={'factory_id': FACTORY, 'code': doc['code']}).status_code == 200
    body = posting(doc, 0, [receipt()])
    result = client.post(BASE + '/documents/' + doc['id'] + '/post', json=body)
    assert result.status_code == 200, result.text
    first = result.json()
    assert first['progress']['L1'] == {'processed': '15', 'remaining': '25'}
    assert first['processing_status'] == 'PARTIAL'
    assert client.post(BASE + '/documents/' + doc['id'] + '/post', json=body).json() == first
    assert workspace(client)['revision'] == 1
    altered = copy.deepcopy(body); altered['lines'][0]['quantity'] = '16'
    assert client.post(BASE + '/documents/' + doc['id'] + '/post', json=altered).status_code == 409
    overflow = posting(first, 1, [receipt(amount='26')])
    assert client.post(BASE + '/documents/' + doc['id'] + '/post', json=overflow).status_code == 409
    second = client.post(BASE + '/documents/' + doc['id'] + '/post', json=posting(first, 1, [receipt(amount='25')]))
    assert second.status_code == 200, second.text
    assert second.json()['processing_status'] == 'COMPLETE'
    assert sum(float(s['quantity']) for s in workspace(client)['stock']) == 40
    public = client.get(BASE + '/external/documents/' + doc['id'], headers=headers).json()
    assert 'actor_name' not in public['movements'][0] and 'batch_id' not in public['movements'][0]
    assert client.put(BASE + '/external/documents/' + doc['id'], headers=headers,
        json=dict(request_id=str(uuid4()), expected_revision=public['revision'], data=public['data'])).status_code == 409
    database = importlib.import_module('app.db')
    with database.SessionLocal() as db:
        for statement in ("DELETE FROM material_handover_sources", "UPDATE material_handover_events SET actor_name='x'"):
            with pytest.raises(DatabaseError):
                db.execute(text(statement))
            db.rollback()


def test_multi_line_rollback_and_issue_matches_real_batch(client):
    _, headers = issuer(client)
    doc = confirmed(client, headers, workbook(rows=[['01-01-00001','测试布料',40,'码','LOT-1'], ['01-01-00002','第二种布',10,'码','LOT-1']]))
    before = workspace(client)
    result = client.post(BASE + '/documents/' + doc['id'] + '/post', json=posting(doc, 0, [receipt(), receipt('L2','5','unknown')]))
    assert result.status_code == 422, result.text
    assert workspace(client)['revision'] == before['revision']
    assert workspace(client)['stock'] == before['stock']
    assert client.get(BASE + '/external/documents/' + doc['id'], headers=headers).json()['revision'] == doc['revision']
    result = client.post(BASE + '/documents/' + doc['id'] + '/post', json=posting(doc, 0, [receipt(amount='40')]))
    assert result.status_code == 200, result.text
    batch = workspace(client)['stock'][0]
    _, request_headers = issuer(client, '测试车间', 'REQUESTOR')
    request = confirmed(client, request_headers, source='ISSUE-001')
    body = posting(request, 1, [dict(line_id='L1', quantity='12', batch_id=batch['id'])])
    result = client.post(BASE + '/documents/' + request['id'] + '/post', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['progress']['L1']['processed'] == '12'
    assert workspace(client)['stock'][0]['quantity'] == '28'
    assert client.post(BASE + '/documents/' + request['id'] + '/post', json=body).json() == result.json()
    request = result.json()
    assert client.post(BASE + '/documents/' + request['id'] + '/post', json=posting(request, 2,
        [dict(line_id='L1', quantity='28.1', batch_id=batch['id'])])).status_code in (409,422)


def test_public_link_isolation_revocation_duplicate_and_void(client):
    person, headers = issuer(client)
    _, other = issuer(client, '其他供应商')
    content = workbook()
    doc = upload(client, headers, content)
    assert upload(client, headers, content)['id'] == doc['id']
    assert client.get(BASE + '/external/documents/' + doc['id'], headers=other).status_code == 404
    assert client.get(BASE + '/external/documents/' + doc['id'] + '/source', headers=other).status_code == 404
    assert client.get(BASE + '/external/documents', headers=other).json()['items'] == []
    assert client.get(BASE + '/workspace', params={'factory_id': 'huakang-d'}).status_code == 422
    response = client.get(BASE + '/external/context', headers=headers)
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'token' not in response.json()
    request = dict(request_id=str(uuid4()), expected_revision=doc['revision'], reason='重复原件')
    assert client.post(BASE + '/external/documents/' + doc['id'] + '/void', headers=headers, json=request).status_code == 200
    assert client.get(BASE + '/external/documents/' + doc['id'] + '/qr', headers=headers).status_code == 409
    assert client.post(BASE + '/issuers/' + person['id'] + '/revoke', json={'factory_id': FACTORY, 'expected_revision': 1}).status_code == 200
    assert client.get(BASE + '/external/documents/' + doc['id'], headers=headers).status_code == 401


def test_confirmation_requires_review_and_fresh_revision(client):
    _, headers = issuer(client)
    doc = upload(client, headers, workbook(headers=['物料编码','物料名称','计划用量','单位'], rows=[['01-01-00001','预算布',40,'码']], title='制单预算用料 单号：PLAN-001 2026-07-18'))
    assert doc['warnings'] and doc['data']['lines'][0]['quantity'] == '40'
    body = copy.deepcopy(doc['data']); body.update(source_no='PLAN-001',document_date='2026-07-18')
    result = client.put(BASE + '/external/documents/' + doc['id'], headers=headers,
        json=dict(request_id=str(uuid4()),expected_revision=doc['revision'],data=body)); assert result.status_code == 200
    updated = result.json()
    invalid=copy.deepcopy(updated['data']);invalid['lines'][0]['quantity']='NaN'
    assert client.put(BASE+'/external/documents/'+doc['id'],headers=headers,
        json=dict(request_id=str(uuid4()),expected_revision=updated['revision'],data=invalid)).status_code == 422
    assert client.post(BASE + '/external/documents/' + doc['id'] + '/confirm', headers=headers,
        json=dict(request_id=str(uuid4()),expected_revision=doc['revision'],acknowledge_warnings=True)).status_code == 409
    assert client.post(BASE + '/external/documents/' + doc['id'] + '/confirm', headers=headers,
        json=dict(request_id=str(uuid4()),expected_revision=updated['revision'])).status_code == 422
    assert workspace(client)['stock'] == []


def test_layout_mapping_retains_repeated_rows_and_leading_zeroes():
    parser = importlib.import_module('app.services.material_handover_parser')
    data = parser.parse('不同布局.xlsx', workbook(headers=['备注','合计数量','布料名称-色号','额外信息','单位'],
        rows=[['缸1', '2000Y','01-01-10-00002 58寸黑布','unused',''], ['缸2','152Y','01-01-10-00002 58寸黑布','unused','']]))
    lines = data['data']['lines']
    assert len(lines) == 2
    assert [line['quantity'] for line in lines] == ['2000','152']
    assert all(line['unit'] == '码' and line['item_code'] == '01-01-10-00002' for line in lines)
    assert data['evidence']['L1']['quantity']['source']['cell']


def test_access_revalidated_after_recognition_and_public_cannot_post(client, monkeypatch):
    person, headers = issuer(client)
    parser = importlib.import_module('app.services.material_handover_parser')
    files = importlib.import_module('app.services.material_handover_files')
    database = importlib.import_module('app.db')
    def revoke_during_extract(name, content):
        value = parser.parse(name,content)
        with database.SessionLocal() as db:
            db.execute(text('UPDATE material_handover_issuers SET active=0 WHERE id=:id'),{'id':person['id']}); db.commit()
        return value
    monkeypatch.setattr(files,'extract',revoke_during_extract)
    result = client.post(BASE + '/external/documents/upload', headers=headers,
        data={'request_id':str(uuid4())}, files={'file':('单据.xlsx',workbook())})
    assert result.status_code == 401
    with database.SessionLocal() as db:
        assert db.scalar(text('SELECT count(*) FROM material_handover_documents')) == 0
    client.cookies.clear()
    assert client.get(BASE + '/workspace',params={'factory_id':FACTORY},headers=headers).status_code == 401
    assert client.post(BASE + '/scan',json={'factory_id':FACTORY,'code':'MH1:any:1'},headers=headers).status_code == 401


def test_concurrent_scans_can_only_post_once_and_reversal_restores_progress(client):
    from concurrent.futures import ThreadPoolExecutor
    _,headers=issuer(client); doc=confirmed(client,headers)
    body1=posting(doc,0,[receipt(amount='30')]);body2=copy.deepcopy(body1);body2['request_id']=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda body:client.post(BASE+'/documents/'+doc['id']+'/post',json=body),[body1,body2]))
    assert sorted(r.status_code for r in results)==[200,409]
    view=workspace(client)
    assert view['revision']==1 and view['stock'][0]['quantity']=='30'
    original=view['documents'][0]['id']
    result=client.post('/api/warehouse-operations/fabric/documents',json=dict(factory_id=FACTORY,request_id=str(uuid4()),
        expected_revision=1,kind='CORRECTION',business_date='2026-07-18',original_id=original,reason='实收数量录错，核对原件后全额冲回'))
    assert result.status_code==200,result.text
    updated=client.get(BASE+'/external/documents/'+doc['id'],headers=headers).json()
    assert updated['progress']['L1']=={'processed':'0','remaining':'40'}
    assert updated['movements'][0]['reversed'] is True
