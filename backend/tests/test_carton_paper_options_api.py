from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare, create, read, payload
from test_carton_transaction_guards_api import BASE


def test_paper_options_are_privileged_revisioned_and_preserve_existing_orders(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        old = create(client)
        workspace = read(client)
        assert workspace['records'] == []  # Pending orders must not enroll full configurations.
        for field in ('packaging_type', 'paper_quality', 'specification'):
            assert old['lines'][0][field] in workspace['paper_history'][field]
        request = {'factory_id': 'huaxing', 'kind': 'RULE', 'code': '', 'customer_code': '',
                   'data': {'lead_days': 7, 'paper_types': [' 底卡 ', '底卡'], 'paper_qualities': ['A33'], 'specifications': ['30*20*15']},
                   'reason': '维护纸品选项'}
        response = client.post(BASE + '/master-data', json=request)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved['data']['paper_types'] == ['底卡']
        assert saved['data']['lead_days'] == 7
        login_as(client, 'warehouse_keeper')
        assert client.patch(BASE + '/master-data/' + saved['id'], json=payload(saved)).status_code == 403
        assert client.get(BASE + '/master-data', params={'factory_id': 'huadeng'}).status_code == 403
        login_as(client, 'admin')
        changed = {**saved['data'], 'paper_types': ['展示盒'], 'hidden_paper_types': [old['lines'][0]['packaging_type']]}
        assert client.patch(BASE + '/master-data/' + saved['id'], json=payload(saved, data=changed)).status_code == 200
        assert client.patch(BASE + '/master-data/' + saved['id'], json=payload(saved)).status_code == 409
        current = client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['items']
        assert next(row for row in current if row['id'] == old['id'])['lines'] == old['lines']
        assert next(row for row in read(client)['records'] if row['kind'] == 'RULE')['data']['paper_types'] == ['展示盒']


def test_saved_paper_history_is_factory_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        old = create(client)
        response = client.get(BASE + '/master-data', params={'factory_id': 'huadeng'})
        assert response.status_code == 200, response.text
        assert all(not values for values in response.json()['paper_history'].values())
        assert old['lines'][0]['paper_quality'] in read(client)['paper_history']['paper_quality']
