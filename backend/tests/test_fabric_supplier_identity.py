"""Supplier renames must retain identity without reusing another supplier's name."""
import importlib

from test_fabric_master_chase import MASTER, master
from test_fabric_procurement import BASE, book, row, stored
from test_fabric_procurement_tracking import save
from test_fabric_receiving import request, receive
from test_molding_sample_api import login_as
from test_warehouse_operations import payload, post
from warehouse_location_fixtures import make_client


def save_supplier(client, name='采购供应商', code='SUP-1', record=None, status='ACTIVE'):
    response = client.post(MASTER, json=master('SUPPLIER', code, name, status=status,
        id=record['id'] if record else None, expected_revision=record['revision'] if record else 0))
    assert response.status_code == 200, response.text
    return response.json()


def test_renamed_supplier_keeps_receipt_identity_and_is_not_a_new_candidate(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        save(client, book([row(采购明细ID='K1', 入库数量=0, 交货明细='')]))
        original = save_supplier(client)
        renamed = save_supplier(client, name='采购供应商新名称', record=original)
        candidates = client.get(MASTER + '/candidates', params={'factory_id': 'huakang-c', 'kind': 'SUPPLIER'}).json()
        assert candidates['items'] == []
        line = stored(client)['items'][0]
        body = request(line)
        receipt = receive(client, line, body)
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()['master_references']['supplier']['id'] == original['id']
        assert receipt.json()['master_references']['supplier']['name'] == renamed['name']
        assert receipt.json()['facts']['supplier'] == '采购供应商'
        inactive = save_supplier(client, name=renamed['name'], record=renamed, status='INACTIVE')
        # Replay is the original result; new receipt requests must check current status.
        assert receive(client, line, body).json() == receipt.json()
        current = stored(client)['items'][0]
        blocked = receive(client, current, request(current, delivery_reference='DN2'))
        assert blocked.status_code == 422 and '停用' in blocked.text
        for name in ('采购供应商', inactive['name']):
            blocked = post(client, payload(client, 'RECEIPT', counterparty=name), status=422)
            assert '停用' in blocked['detail']
        history = client.get(BASE + '/receipts', params={'factory_id': 'huakang-c'}).json()['items']
        assert len(history) == 1 and history[0]['master_references']['supplier']['status'] == 'ACTIVE'


def test_supplier_old_names_cannot_be_reused_and_rename_back_is_allowed(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        first = save_supplier(client)
        changed = save_supplier(client, name='新名称', record=first)
        assert client.post(MASTER, json=master('SUPPLIER', 'SUP-2', '采购供应商')).status_code == 409
        second = save_supplier(client, name='另一供应商', code='SUP-2')
        assert client.post(MASTER, json=master('SUPPLIER', 'SUP-2', '采购供应商',
            id=second['id'], expected_revision=second['revision'])).status_code == 409
        restored = save_supplier(client, record=changed)
        assert restored['id'] == first['id']


def test_internal_monthly_keeps_renamed_supplier_together_without_any_scanned_receipt(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        save(client, book([row(采购明细ID='K1', 入库数量=0, 交货明细='')]))
        supplier = save_supplier(client)
        post(client, payload(client, 'RECEIPT', counterparty=supplier['name']))
        renamed = save_supplier(client, name='供应商新名称', record=supplier)
        post(client, payload(client, 'RECEIPT', counterparty=renamed['name']))
        line = stored(client)['items'][0]
        assert receive(client, line, request(line, receipt_date='2026-07-18')).status_code == 200
        result = client.get('/api/warehouse-operations/fabric/monthly', params={
            'factory_id': 'huakang-c', 'month': '2026-07', 'direction': 'IN',
            'party_key': 'supplier:' + supplier['id']})
        assert result.status_code == 200, result.text
        report = result.json()
        assert len(report['details']) == 3
        assert report['totals'][0]['net_received'] == '70.0'
        assert {item['recorded_party'] for item in report['details']} == {supplier['name'], renamed['name']}
        assert {item['party_name'] for item in report['details']} == {renamed['name']}


def test_ambiguous_legacy_supplier_name_cannot_post_receipts(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        save(client, book([row(采购明细ID='K1', 入库数量=0, 交货明细='')]))
        first = save_supplier(client)
        save_supplier(client, name='新名称', record=first)
        database = importlib.import_module('app.db')
        model = importlib.import_module('app.models.fabric_master').FabricMasterRecord
        with database.SessionLocal() as db:
            db.add(model(id='legacy-other', factory_id='huakang-c', kind='SUPPLIER', code='LEGACY',
                name='采购供应商', status='ACTIVE', revision=1, data_json='{}', updated_at='2026-07-18'))
            db.commit()
        line = stored(client)['items'][0]
        blocked = receive(client, line, request(line))
        assert blocked.status_code == 422 and '多个供应商' in blocked.text
        assert '多个供应商' in post(client, payload(client, 'RECEIPT', counterparty='采购供应商'), status=422)['detail']
        # Existing ambiguous records can still be disabled to contain the problem.
        response = client.post(MASTER, json=master('SUPPLIER', 'LEGACY', '采购供应商',
            id='legacy-other', expected_revision=1, status='INACTIVE'))
        assert response.status_code == 200, response.text
