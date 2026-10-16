from fastapi import HTTPException
from test_carton_procurement_api import _freeze_carton_time
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, accept_all, supplier_login, BASE as SUPPLIER

BASE = '/api/carton-procurement'


def test_quantity_and_date_changes_issue_atomically_and_require_new_acceptance(monkeypatch):
    with make_client(monkeypatch) as client:
        _freeze_carton_time(monkeypatch)
        setup_portal(client)
        old = accept_all(client)
        login_as(client, 'admin')
        def current():
            return client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['items'][0]
        row = current()
        initial_issue = old['issue_id']
        for operation, fields in [('append', {'additional_quantity': '120'}),
                                  ('reduce', {'reduction_quantity': '120'}),
                                  ('dates', {'due_date': '2026-08-15', 'reason': '客户改期同步'})]:
            response = client.post(BASE + f"/orders/{row['order_no']}/{operation}", json={
                'factory_id': 'huaxing', 'expected_revision': row['revision'], 'issue_to_supplier': True, **fields})
            assert response.status_code == 200, response.text
            row = response.json()
            supplier_login(client)
            portal = client.get(SUPPLIER + '/workspace', params={'factory_id': 'huaxing'}).json()['orders'][0]
            assert not portal['awaiting_issue']
            assert portal['issue_id'] != initial_issue
            assert not any(line['accepted'] for line in portal['lines'])
            assert portal['planned_date'] == row['due_date']
            assert [line['required_quantity'] for line in portal['lines']] == [line['required_quantity'] for line in row['lines']]
            initial_issue = portal['issue_id']
            for line in portal['lines']:
                accepted = client.put(SUPPLIER + f"/papers/{line['id']}/commitment", json={
                    'factory_id': 'huaxing', 'issue_id': portal['issue_id'],
                    'expected_revision': line['commitment_revision'], 'promised_date': '2026-09-23'})
                assert accepted.status_code == 200, accepted.text
            login_as(client, 'admin')
        # A supplier issue failure must roll back the warehouse edit too.
        import app.services.carton_procurement as service
        def fail(*args, **kwargs):
            raise HTTPException(409, '模拟同步失败')
        monkeypatch.setattr(service, 'create_purchase_order_issue', fail)
        before = current()
        response = client.post(BASE + f"/orders/{row['order_no']}/append", json={
            'factory_id': 'huaxing', 'expected_revision': before['revision'],
            'additional_quantity': '120', 'issue_to_supplier': True})
        assert response.status_code == 409
        assert current() == before
