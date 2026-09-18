from test_qc_inspection_api import _event_payload
from test_qc_schedule_review_import import review_workbook
from test_molding_sample_api import make_client, login_as


def test_pending_order_result_guards_replay_and_preserves_event_history(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'qc_inspector')
        batch = client.post('/api/qc-inspections/schedule-imports/preview',
            data={'factory_id': 'huaxing', 'week_key': '2026-W38', 'request_id': 'daily-preview'},
            files={'file': ('review.xlsx', review_workbook())}).json()
        response = client.post(f"/api/qc-inspections/schedule-imports/{batch['id']}/confirm", json={
            'factory_id': 'huaxing', 'expected_revision': batch['revision'], 'request_id': 'daily-import',
            'decisions': [{'row_id': row['id'], 'action': 'CREATE'} for row in batch['rows'][:2]]})
        assert response.status_code == 200, response.text
        orders = client.get('/api/qc-inspections/orders', params={'factory_id': 'huaxing'}).json()['items']
        order = orders[0]
        endpoint = f"/api/qc-inspections/orders/{order['id']}/events"
        payload = {**_event_payload(order['id'], 'daily-result'), 'expected_pending_order_revision': order['revision']}
        stale = client.post(endpoint, json={**payload, 'expected_pending_order_revision': order['revision'] + 1})
        assert stale.status_code == 409
        assert client.post(endpoint, json={**payload, 'factory_id': 'huakang-a'}).status_code == 403
        response = client.post(endpoint, json=payload)
        assert response.status_code == 201, response.text
        event = response.json()
        assert client.post(endpoint, json=payload).json() == event
        assert client.post(endpoint, json={**payload, 'request_id': 'different-request'}).status_code == 409
        updated = client.get(f"/api/qc-inspections/orders/{order['id']}", params={'factory_id': 'huaxing'}).json()
        assert updated['inspection_result'] == 'FAIL' and updated['status'] == 'COMPLETED'
        assert updated['problem_count'] == 1
        assert client.post(endpoint, json={**payload, 'request_id': 'already-completed', 'expected_pending_order_revision': updated['revision']}).status_code == 409
        assert len(client.get(endpoint, params={'factory_id': 'huaxing'}).json()['items']) == 1

        second = orders[1]
        second_endpoint = f"/api/qc-inspections/orders/{second['id']}/events"
        draft_payload = {**_event_payload(second['id'], 'pending-draft'), 'inspection_result': 'PENDING'}
        draft = client.post(second_endpoint, json=draft_payload).json()
        second_updated = client.get(f"/api/qc-inspections/orders/{second['id']}", params={'factory_id': 'huaxing'}).json()
        final_payload = {**draft_payload, 'request_id': 'complete-draft', 'inspection_result': 'FAIL',
            'expected_revision': draft['revision'], 'expected_pending_order_revision': second_updated['revision'], 'reason': '批量登记结果'}
        final_endpoint = f"{second_endpoint}/{draft['id']}"
        assert client.patch(final_endpoint, json={**final_payload, 'expected_pending_order_revision': second['revision']}).status_code == 409
        final = client.patch(final_endpoint, json=final_payload)
        assert final.status_code == 200, final.text
        assert final.json()['attempt_no'] == 1
        assert final.json()['defects'][0]['description'] == draft['defects'][0]['description']
        assert client.patch(final_endpoint, json=final_payload).json() == final.json()
        assert len(client.get(second_endpoint, params={'factory_id': 'huaxing'}).json()['items']) == 1
