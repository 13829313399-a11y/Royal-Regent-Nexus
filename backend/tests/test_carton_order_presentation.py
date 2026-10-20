"""Order menu contracts and genuine stock-origin labels, using disposable data."""
from decimal import Decimal
from types import SimpleNamespace
import json
import pytest
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_supplier_portal import grant_supplier_permissions, supplier_login
from test_carton_special_requests import setup, created, create_body, command, ok, ship, receive, BASE, SUP, FACTORY


@pytest.fixture(autouse=True)
def isolated_directory(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def test_delete_is_audited_idempotent_hidden_from_both_ledgers_and_read_only(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        row = ok(client.post(BASE, json=create_body()), 201)
        assert row["permissions"]["can_delete"]
        path = BASE + f"/{row['id']}/delete"
        payload = command(row, reason="重复录入需求")
        assert client.post(path, json={**payload, "expected_revision": row["revision"] + 1}).status_code == 409
        assert client.post(path, json={**payload, "reason": "短"}).status_code == 422
        result = ok(client.post(path, json=payload))
        assert result["deleted"] and result["status"] == "CANCELLED"
        assert all(value is False for value in result["permissions"].values())
        assert result["history"][-1]["snapshot"]["reason"] == payload["reason"]
        assert ok(client.post(path, json=payload)) == result
        assert client.post(path, json={**payload, "reason": "改动删除原因"}).status_code == 409
        assert row["id"] not in {item["id"] for item in ok(client.get(BASE, params={"factory_id": FACTORY}))["items"]}
        combined = ok(client.get('/api/carton-unified-orders', params={"factory_id": FACTORY, "kind": "SAMPLE", "status_filter": "CANCELLED"}))
        assert combined["total"] == 0
        assert ok(client.get(BASE + f"/{row['id']}", params={"factory_id": FACTORY}))["deleted"]
        assert client.put(BASE + f"/{row['id']}", json={**create_body(), "expected_revision": result["revision"]}).status_code == 409
        supplier_login(client)
        assert row["id"] not in {item["id"] for item in ok(client.get(SUP, params={"factory_id": FACTORY}))["items"]}


def test_delete_rechecks_permission_factory_and_supplier_activity(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client)
        row = created(client)
        ensure_test_user('engineer')
        grant_supplier_permissions('user-engineer', permissions=('carton_procurement:order_write',))
        login_as(client, 'engineer')
        assert client.post(BASE + f"/{row['id']}/delete", json=command(row, reason="测试权限边界")).status_code == 403
        login_as(client, 'admin')
        assert client.post(BASE + f"/{row['id']}/delete", json={**command(row, reason="测试厂区边界"), "factory_id": "huakang-a"}).status_code in {403, 404}
        row = ship(client, row, quantity='20')
        login_as(client, 'admin')
        assert not ok(client.get(BASE + f"/{row['id']}", params={"factory_id": FACTORY}))["permissions"]["can_delete"]
        assert client.post(BASE + f"/{row['id']}/delete", json=command(row, reason="已有送货证据")).status_code == 409


def test_customer_linked_sample_stock_uses_its_actual_receipt_source(monkeypatch):
    with make_client(monkeypatch) as client:
        place = setup(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        from sqlalchemy import select
        with SessionLocal() as db:
            code = db.scalar(select(CartonCustomer.customer_code).where(CartonCustomer.factory_id == FACTORY))
        row = ok(client.post(BASE, json={**create_body(), "customer_code": code}), 201)
        row = ok(client.post(BASE + f"/{row['id']}/send", json=command(row)))
        row = ship(client, row, quantity='20')
        receive(client, row, place, quantity='20')
        positions = ok(client.get('/api/carton-procurement/inventory/positions', params={"factory_id": FACTORY}))
        stock = next(item for item in positions if item['location_id'] == place['id'])
        assert stock['customer_code'] == code
        assert stock['business_kinds'] == ['SAMPLE']
        assert Decimal(stock['balance']) == 20


def test_origin_projection_preserves_mixed_pool_and_excludes_reversed_sources(monkeypatch):
    from app.services.carton_inventory_types import annotate_types
    from app.services.carton_inventory_identity import inventory_key
    # Source-link queries are covered by the real receipt integration tests;
    # this unit double only supplies the stock-origin classification rows.
    monkeypatch.setattr('app.services.carton_source_links.line_sources', lambda *_: {})
    def movement(identifier, receipt, quantity='10', **extra):
        data = dict(id=identifier, customer_code='LINKED-CUSTOMER', contract_no='', item_no='ITEM', packaging_type='外箱',
            paper_quality='A33', specification='10*20*30 cm', unit='个', order_line_id=None, quantity=Decimal(quantity),
            source_line_id=receipt, source_type='RECEIPT', movement_type='INBOUND', reversal_of_movement_id=None)
        return SimpleNamespace(**(data | extra))
    db = SimpleNamespace(execute=lambda _: [('RS', json.dumps({'kind': 'SAMPLE'}), 'SAMPLE', 'INTERNAL'),
        ('RM', json.dumps({'kind': 'WORKSHOP_MISC'}), 'WORKSHOP_MISC', 'INTERNAL')])
    sample, misc = movement('S', 'RS'), movement('M', 'RM')
    balance = SimpleNamespace(inventory_key=inventory_key(sample), balance=Decimal(20))
    annotate_types(db, FACTORY, [balance], [sample, misc, movement('OUT', '', '-5', movement_type='OUTBOUND', source_type='MANUAL')])
    assert balance.business_kinds == ['SAMPLE', 'WORKSHOP_MISC']
    assert balance.balance == 20
    reversal = movement('REV', '', '-10', movement_type='REVERSAL', source_type='REVERSAL', reversal_of_movement_id='S')
    annotate_types(db, FACTORY, [balance], [sample, misc, reversal])
    assert balance.business_kinds == ['WORKSHOP_MISC']
