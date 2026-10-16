from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.services.carton_quantity import requirements
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order, _freeze_carton_time

BASE = '/api/carton-procurement'


def payload():
    data = _order_payload()
    data['product_order_quantity'] = '1001'
    data['lines'][0]['usage_quantity'] = '12'
    data['lines'][1].update(packaging_type='刀卡', usage_quantity=None, quantity_rule={
        'mode': 'PER_CARTON', 'carton_line_no': 1, 'per_carton_quantity': '3'})
    return data


def start(client, monkeypatch):
    login_as(client, 'admin')
    _freeze_carton_time(monkeypatch)
    _ensure_dickie_customer(client)
    login_as(client, 'carton_supervisor')


def create(client, data):
    response = client.post(BASE + '/orders', json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_parent_rounding_manual_override_and_invalid_graphs():
    lines = payload()['lines']
    assert requirements(1001, lines) == [84, 252]
    lines[0]['quantity_rule'] = {'mode': 'PACKING', 'manual_quantity': 85}
    assert requirements(1001, lines) == [85, 255]
    lines[1]['quantity_rule']['manual_quantity'] = 260
    assert requirements(2000, lines) == [85, 260]
    lines[0]['quantity_rule']['manual_quantity'] = None
    assert requirements(2000, lines) == [167, 260]
    lines[1]['quantity_rule']['manual_quantity'] = None
    assert requirements(2000, lines) == [167, 501]
    for parent in (2, 3):
        lines[1]['quantity_rule']['carton_line_no'] = parent
        with pytest.raises(HTTPException):
            requirements(1001, lines)
    lines[0]['quantity_rule'] = {'mode': 'PER_CARTON', 'carton_line_no': 2, 'per_carton_quantity': 1}
    lines[1]['quantity_rule']['carton_line_no'] = 1
    with pytest.raises(HTTPException):
        requirements(1001, lines)


def test_paper_only_adjustment_preserves_explicit_child_total_after_parent_changes():
    from app.models.carton_procurement import CartonOrderLine
    from app.services.carton_procurement import _apply_manual_targets
    import json
    box = CartonOrderLine(id='box', usage_quantity=Decimal(12), required_quantity=Decimal(100))
    card = CartonOrderLine(id='card', required_quantity=Decimal(300), quantity_rule_json=json.dumps({
        'mode': 'PER_CARTON', 'carton_line_no': 1, 'per_carton_quantity': '3'}))
    _apply_manual_targets([box, card], {'box': Decimal(110), 'card': Decimal(300)}, Decimal(1200))
    assert requirements(2400, [box, card]) == [110, 300]


def test_manual_quantity_survives_reopen_edit_and_export_restore_automatic(monkeypatch):
    with make_client(monkeypatch) as client:
        start(client, monkeypatch)
        data = payload()
        data['lines'][1]['quantity_rule']['manual_quantity'] = '260'
        order = create(client, data)
        assert [Decimal(line['required_quantity']) for line in order['lines']] == [84, 260]
        rows = client.get(BASE + '/orders', params={'factory_id': 'huaxing'}).json()['items']
        assert Decimal(rows[0]['lines'][1]['quantity_rule']['manual_quantity']) == 260
        data['product_order_quantity'] = '1200'
        response = client.patch(BASE + '/orders/' + order['order_no'], json={**data, 'expected_revision': order['revision'], 'reason': '核对产品订单数量'})
        assert response.status_code == 200, response.text
        order = response.json()
        assert [Decimal(line['required_quantity']) for line in order['lines']] == [100, 260]
        # Export uses the stored manual demand, never an old divide formula.
        from app import db as app_db
        from app.services.carton_procurement import get_order_by_no, _order_lines
        from app.services import carton_procurement_export as exports
        with app_db.SessionLocal() as db:
            stored = get_order_by_no(db, 'huaxing', order['order_no'])
            from datetime import datetime
            content = exports.build_purchase_order_workbook(stored, _order_lines(db, stored.id), generated_at=datetime(2026, 8, 5))
            sheet = load_workbook(BytesIO(content)).active
            assert sheet['G11'].value == 260
        data['lines'][1]['quantity_rule']['manual_quantity'] = None
        response = client.patch(BASE + '/orders/' + order['order_no'], json={**data, 'expected_revision': order['revision'], 'reason': '恢复自动计算数量'})
        assert response.status_code == 200, response.text
        assert [Decimal(line['required_quantity']) for line in response.json()['lines']] == [100, 300]


def test_issued_changes_keep_supplier_snapshots_and_receipt_protection(monkeypatch):
    with make_client(monkeypatch) as client:
        start(client, monkeypatch)
        order = _submit_order(client, create(client, payload()))
        url = BASE + '/orders/' + order['order_no']
        response = client.post(url + '/append', json={'factory_id': 'huaxing', 'expected_revision': order['revision'], 'additional_quantity': '199', 'issue_to_supplier': True})
        assert response.status_code == 200, response.text
        order = response.json()
        assert [Decimal(line['required_quantity']) for line in order['lines']] == [100, 300]
        response = client.post(url + '/append', json={'factory_id': 'huaxing', 'expected_revision': order['revision'], 'issue_to_supplier': True,
            'line_quantities': [{'order_line_id': line['id'], 'required_quantity': q} for line, q in zip(order['lines'], [100, 310])]})
        assert response.status_code == 200, response.text
        order = response.json()
        assert Decimal(order['product_order_quantity']) == 1200
        assert Decimal(order['lines'][1]['quantity_rule']['manual_quantity']) == 310
        context = client.get(url + '/purchase-order-context', params={'factory_id': 'huaxing'}).json()
        assert context['issues'][0]['document_type'] == 'APPEND'
        receipt = client.post(BASE + '/receipts', json={'factory_id': 'huaxing', 'delivery_note_no': 'CARD-TEST', 'delivery_date': '2026-08-05', 'acceptance_date': '2026-08-05',
            'lines': [{'order_line_id': order['lines'][1]['id'], 'delivered_quantity': 200, 'received_quantity': 200, 'location': ''}]})
        assert receipt.status_code == 201, receipt.text
        def reduce(card):
            return client.post(url + '/reduce', json={'factory_id': 'huaxing', 'expected_revision': order['revision'], 'issue_to_supplier': True,
                'line_quantities': [{'order_line_id': line['id'], 'required_quantity': q} for line, q in zip(order['lines'], [100, card])]})
        assert reduce(199).status_code == 409
        response = reduce(250)
        assert response.status_code == 200, response.text
        order = response.json()
        assert Decimal(order['lines'][1]['quantity_rule']['manual_quantity']) == 250
        response = client.post(url + '/append', json={'factory_id': 'huaxing', 'expected_revision': order['revision'], 'additional_quantity': 120, 'issue_to_supplier': True})
        assert response.status_code == 200, response.text
        assert [Decimal(line['required_quantity']) for line in response.json()['lines']] == [110, 250]


def test_master_reuses_formula_without_order_manual_override_and_split_uses_boxes(monkeypatch):
    with make_client(monkeypatch) as client:
        start(client, monkeypatch)
        data = payload()
        data['product_order_quantity'] = 1200
        data['lines'][1]['quantity_rule']['manual_quantity'] = 310
        order = _submit_order(client, create(client, data))
        workspace = client.get(BASE + '/master-data', params={'factory_id': 'huaxing'}).json()
        config = next(row for row in workspace['records'] if row['kind'] == 'CONFIG')
        assert config['data']['lines'][1]['quantity_rule']['manual_quantity'] is None
        assert config['data']['lines'][1]['usage_quantity'] is None
        # Manual card quantities are allocated explicitly; normal boxes still follow packing.
        body = {'factory_id': 'huaxing', 'request_id': uuid4().hex, 'expected_revision': order['revision'], 'reason': '核对按箱配套拆单',
            'targets': [{'contract_no': 'SPLIT-CARD', 'customer_po': 'NEW-CARD', 'product_quantity': 600,
                'lines': [{'order_line_id': line['id'], 'pending_quantity': q, 'stock': []} for line, q in zip(order['lines'], [50, 155])]}]}
        response = client.post(BASE + '/orders/' + order['order_no'] + '/splits', json=body)
        assert response.status_code == 201, response.text


def test_additive_migration_keeps_all_old_quantities():
    path = Path(__file__).parents[1] / 'alembic/versions/20261016_0163_carton_quantity_rules.py'
    spec = importlib.util.spec_from_file_location('quantity_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE carton_order_lines (id TEXT PRIMARY KEY, required_quantity NUMERIC, usage_quantity NUMERIC)'))
        connection.execute(text("INSERT INTO carton_order_lines VALUES ('old-card', 123, 12)"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert tuple(connection.execute(text('SELECT required_quantity, usage_quantity, quantity_rule_json FROM carton_order_lines')).one()) == (123, 12, None)
