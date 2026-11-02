"""Isolated API regressions for replenishment promise notices."""
from datetime import date, timedelta

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, ship_payload, receive_payload
from test_carton_history_identity_api import _orders
from test_carton_replenishment_api import body, replenish
from test_carton_transaction_guards_api import BASE

SUPPLIER = '/api/carton-supplier'


@pytest.fixture(autouse=True)
def isolate_storage(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('QC_DEPARTMENT_MANAGED', 'false')


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def accept(client, issue, line, revision, promised):
    return ok(client.put(SUPPLIER + '/commitments/batch', json={
        'factory_id': 'huaxing', 'lines': [{'order_line_id': line, 'issue_id': issue,
        'expected_revision': revision, 'promised_date': promised}]}))


def notices(client, **params):
    return ok(client.get(BASE + '/supplier-promise-changes', params={'factory_id': 'huaxing', **params}))


def ack(client, key):
    ok(client.post(BASE + '/promise-notices/ack', json={'factory_id': 'huaxing', 'key': key}))


def prepare(client, count=1):
    setup_portal(client)
    order = ok(client.get(SUPPLIER + '/workspace', params={'factory_id': 'huaxing'}))['orders'][0]
    for line in order['lines']:
        accept(client, order['issue_id'], line['id'], 0, order['planned_date'])
    shipped = ok(client.post(SUPPLIER + '/shipments', json=ship_payload(order)), 201)
    login_as(client, 'warehouse_keeper')
    ok(client.post(SUPPLIER + f"/internal/shipments/{shipped['id']}/receive", json=receive_payload(client, shipped)))
    login_as(client, 'admin')
    issues = []
    for _ in range(count):
        current = _orders(client)[0]
        stocks = ok(client.get(BASE + '/inventory/positions', params={'factory_id': 'huaxing'}))
        issues.append(ok(replenish(client, current, body(current, stocks, 'OWN', qty=1)), 201)['issue'])
    supplier_login(client)
    order = ok(client.get(SUPPLIER + '/workspace', params={'factory_id': 'huaxing'}))['orders'][0]
    return [next(source for source in order['replenishment_sources'] if source['issue_id'] == issue['id']) for issue in issues]


def b_rows(result, section):
    return [row for row in result[section] if row.get('source_kind') == 'REPLENISHMENT']


def test_b_notices_are_independent_acknowledged_and_reappear_only_for_real_date_changes(monkeypatch):
    with make_client(monkeypatch) as client:
        first, second = prepare(client, 2)
        line = first['lines'][0]['id']
        planned = date.fromisoformat(first['planned_date'])
        day2, day4 = [(planned + timedelta(days=n)).isoformat() for n in (2, 4)]
        accept(client, first['issue_id'], line, 0, day2)
        accept(client, second['issue_id'], second['lines'][0]['id'], 0, day2)
        login_as(client, 'warehouse_keeper')
        initial = b_rows(notices(client), 'late')
        assert {row['issue_id'] for row in initial} == {first['issue_id'], second['issue_id']}
        a = next(row for row in initial if row['issue_id'] == first['issue_id'])
        b = next(row for row in initial if row['issue_id'] == second['issue_id'])
        assert a['key'] != b['key']
        assert a['order_line_id'] == line and a['planned_date'] == planned.isoformat()
        assert a['document_no']
        ack(client, a['key'])
        page = notices(client, limit=1, offset=0)
        assert [row['issue_id'] for row in b_rows(page, 'late')] == [second['issue_id']]
        ack(client, b['key'])
        supplier_login(client)
        accept(client, first['issue_id'], line, 1, day2)
        login_as(client, 'warehouse_keeper')
        assert not b_rows(notices(client), 'late')
        supplier_login(client)
        accept(client, first['issue_id'], line, 2, day4)
        login_as(client, 'warehouse_keeper')
        result = notices(client)
        late = b_rows(result, 'late')
        assert len(late) == 1 and late[0]['issue_id'] == first['issue_id'] and late[0]['key'] != a['key']
        changes = b_rows(result, 'changes')
        assert any(row['issue_id'] == first['issue_id'] and row['previous_promised_date'] == day2 and row['promised_date'] == day4 for row in changes)
        tasks = ok(client.get(SUPPLIER + '/internal/changes', params={'factory_id': 'huaxing'}))['items']
        task = next(item for item in tasks if item['source_id'] == first['issue_id'])
        assert next(item for item in task['lines'] if item['id'] == line)['promised_date'] == day4
        ack(client, late[0]['key'])
        supplier_login(client)
        accept(client, first['issue_id'], line, 3, day2)
        login_as(client, 'warehouse_keeper')
        returned = b_rows(notices(client), 'late')
        assert len(returned) == 1 and returned[0]['key'] not in (a['key'], late[0]['key'])
        assert any(row['previous_promised_date'] == day4 and row['promised_date'] == day2 for row in b_rows(notices(client), 'changes'))


def test_disputed_b_stops_late_notice_until_valid_acceptance(monkeypatch):
    from test_carton_p1_lifecycle import task_for, respond
    with make_client(monkeypatch) as client:
        source = prepare(client)[0]
        day = (date.fromisoformat(source['planned_date']) + timedelta(days=2)).isoformat()
        accept(client, source['issue_id'], source['lines'][0]['id'], 0, day)
        later = (date.fromisoformat(source['planned_date']) + timedelta(days=4)).isoformat()
        accept(client, source['issue_id'], source['lines'][0]['id'], 1, later)
        order = ok(client.get(SUPPLIER + '/workspace', params={'factory_id': 'huaxing'}))['orders'][0]
        login_as(client, 'warehouse_keeper')
        assert any(row['issue_id'] == source['issue_id'] for row in b_rows(notices(client), 'late'))
        supplier_login(client)
        result = respond(client, task_for(client, 'REPLENISHMENT', order['id']), 'DISPUTE', reason='核实补单交期')
        assert result.status_code == 200, result.text
        login_as(client, 'warehouse_keeper')
        result = notices(client)
        assert not any(row['issue_id'] == source['issue_id'] for row in b_rows(result, 'late'))
        changes = [row for row in b_rows(result, 'changes') if row['issue_id'] == source['issue_id']]
        assert len(changes) == 1 and changes[0]['previous_promised_date'] == day and changes[0]['promised_date'] == later
        ack(client, changes[0]['key'])
        assert not any(row['issue_id'] == source['issue_id'] for row in b_rows(notices(client), 'changes'))



def test_fully_received_b_no_longer_creates_late_notice(monkeypatch):
    from test_carton_direct_receipt_api import payload as receipt_payload
    with make_client(monkeypatch) as client:
        source = prepare(client)[0]
        day = (date.fromisoformat(source['planned_date']) + timedelta(days=2)).isoformat()
        accept(client, source['issue_id'], source['lines'][0]['id'], 0, day)
        login_as(client, 'warehouse_keeper')
        assert any(row['issue_id'] == source['issue_id'] for row in b_rows(notices(client), 'late'))
        login_as(client, 'admin')
        order = _orders(client)[0]
        receipt = receipt_payload(order)
        receipt['lines'] = receipt['lines'][:1]
        receipt['lines'][0].update(delivered_quantity=1, received_quantity=1,
                                   replenishment_issue_id=source['issue_id'])
        ok(client.post(BASE + '/receipts', json=receipt), 201)
        login_as(client, 'warehouse_keeper')
        assert not any(row['issue_id'] == source['issue_id'] for row in b_rows(notices(client), 'late'))
