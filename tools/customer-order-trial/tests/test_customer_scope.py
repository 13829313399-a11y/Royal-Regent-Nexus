from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.history import History

BASE = 'http://127.0.0.1:8765'
HEADERS = {'X-Order-Trial': '1'}


def test_green_toys_package_restricts_customer_on_server_and_keeps_scope_after_restart(tmp_path):
    for _ in range(2):
        with TestClient(create_app(tmp_path, factory_id='huakang-a', customer_codes=['green-toys']), base_url=BASE) as client:
            assert [c['code'] for c in client.get('/api/config').json()['customers']] == ['green-toys']
            for path in ('history/customers','schedule/customers'):
                result=client.get('/api/customer-order-ledger/'+path, params={'factory_id':'huakang-a'})
                assert [row['code'] for row in result.json()['items']]==['green-toys']
            assert client.get('/api/config').json()['capabilities']['workbook_tools'] is False
            response=client.post('/api/customer-order-ledger/schedule/organize-360?factory_id=huakang-a',
                files={'schedule_file':('360.xlsx',b'must not parse')},headers=HEADERS)
            assert response.status_code==400 and '未开放' in response.text
            assert client.get('/api/orders/exports').json()['total']==0
            files = [('po_files', ('other.pdf', b'not parsed')), ('schedule_file', ('test.xlsx', b'not parsed'))]
            fields = dict(customer_code='headstart', factory_id='huakang-a', received_date='2026-11-19')
            response = client.post('/api/orders/preview', data=fields, files=files, headers=HEADERS)
            assert response.status_code == 400 and '未开放' in response.text
            response = client.post('/api/customer-order-ledger/imports/headstart', data={**fields, 'confirmed':'true', 'preview_fingerprint':'x'}, files=files, headers=HEADERS)
            assert response.status_code == 400 and '未开放' in response.text
    with TestClient(create_app(tmp_path/'full', factory_id='huakang-a'), base_url=BASE) as client:
        assert {c['code'] for c in client.get('/api/config').json()['customers']} == {'green-toys','headstart','zuru','360'}


def test_restricted_package_preserves_and_refuses_other_customer_history(tmp_path):
    history = History(tmp_path, 'huakang-a')
    row = history.save('headstart', 'original.xlsx', b'untouched evidence', 1, {})
    with pytest.raises(RuntimeError, match='范围外'):
        create_app(tmp_path, factory_id='huakang-a', customer_codes=['green-toys'])
    assert History(tmp_path,'huakang-a').get(row['id'])['content'] == b'untouched evidence'


@pytest.mark.parametrize('codes', [[], ['not-a-customer'], 'green-toys'])
def test_invalid_scope_does_not_initialize_database(tmp_path, codes):
    with pytest.raises(ValueError, match='客户范围'):
        create_app(tmp_path, factory_id='huakang-a', customer_codes=codes)
    assert not (tmp_path/'order_trial.sqlite3').exists()


@pytest.mark.parametrize('factory,code,other',[('huakang-a','zuru','green-toys'),('huadeng','casdon','jakks')])
def test_single_customer_scope(factory,code,other,tmp_path):
    for _ in range(2):
        with TestClient(create_app(tmp_path,factory_id=factory,customer_codes=[code]),base_url=BASE) as client:
            assert [r['code'] for r in client.get('/api/config').json()['customers']]==[code]
            for path in ('history/customers','schedule/customers'):
                r=client.get('/api/customer-order-ledger/'+path,params={'factory_id':factory})
                assert [v['code'] for v in r.json()['items']]==[code]
            fields=dict(customer_code=other,factory_id=factory,received_date='2026-11-19',confirmed='true',preview_fingerprint='x')
            files=[('po_files',('other.pdf',b'unparsed')),('schedule_file',('schedule.xlsx',b'unparsed'))]
            for endpoint in ('/api/orders/preview', '/api/customer-order-ledger/imports/'+other):
                r=client.post(endpoint,data=fields,files=files,headers=HEADERS)
                assert r.status_code==400 and '未开放' in r.text
