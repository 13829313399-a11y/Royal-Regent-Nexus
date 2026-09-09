"""Warehouse removal must never erase a previously used physical identity."""
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from test_molding_sample_api import make_client, login_as
from test_carton_master_api import prepare, create, read
from test_carton_procurement_api import _submit_order
from test_carton_transaction_guards_api import BASE, draft, confirm, outbound


def warehouse(client, name="EMPTY"):
    response = client.post(BASE + "/inventory/warehouses", json={"factory_id": "huaxing",
        "warehouse": name, "bin_code": "01", "reason": "测试建立空仓"})
    assert response.status_code == 201, response.text
    return response.json()[0]


def request(*locations):
    return {"factory_id": "huaxing", "warehouse": locations[0]["warehouse"],
        "expected_locations": {row["id"]: row["revision"] for row in locations}, "reason": "删除从未使用空仓"}


def remove(client, payload):
    return client.post(BASE + "/inventory/warehouses/delete", json=payload)


def test_empty_delete_requires_master_full_revisions_and_cleans_grants(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        first = warehouse(client)
        second = client.post(BASE + "/inventory/locations", json={"factory_id": "huaxing",
            "warehouse": "EMPTY", "bin_code": "02", "reason": "增加仓库第二仓位"}).json()
        assert remove(client, request(first)).status_code == 409
        args = request(first, second)
        assert remove(client, {**args, "expected_locations": {first["id"]: 99, second["id"]: 1}}).status_code == 409
        assert remove(client, {**args, "reason": ""}).status_code == 422
        login_as(client, "warehouse_keeper")
        user = client.get("/api/auth/me").json()
        assert remove(client, args).status_code == 403
        login_as(client, "admin")
        grant = client.post(BASE + "/master-data", json={"factory_id": "huaxing", "kind": "ACCESS",
            "code": user["id"], "data": {"warehouses": ["EMPTY", "OTHER"]}, "reason": "限定仓库维护权限"}).json()
        login_as(client, "warehouse_keeper")
        assert remove(client, args).status_code == 403  # bin maintenance is not warehouse deletion
        login_as(client, "admin")
        assert remove(client, {**args, "factory_id": "huakang"}).status_code in (403, 404, 422)
        assert len([row for row in read(client)["locations"] if row["warehouse"] == "EMPTY"]) == 2
        result = remove(client, args)
        assert result.status_code == 200, result.text
        assert result.json() == {"deleted": True}
        current = read(client)
        assert not any(row["warehouse"] == "EMPTY" for row in current["locations"])
        updated = next(row for row in current["records"] if row["id"] == grant["id"])
        assert updated["data"]["warehouses"] == ["OTHER"]
        assert updated["revision"] == grant["revision"] + 1
        events = client.get(BASE + "/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        deleted = next(event for event in events if event["event_type"] == "MASTER_WAREHOUSE_DELETED")
        assert {row["id"] for row in deleted["detail"]["before"]} == {first["id"], second["id"]}
        assert deleted["detail"]["reason"] == args["reason"]
        assert remove(client, args).status_code == 404
        rebuilt = warehouse(client)
        assert rebuilt["id"] not in args["expected_locations"]
        login_as(client, "warehouse_keeper")
        assert read(client)["warehouses"] == ["OTHER"]


def test_used_warehouse_cannot_delete_when_depleted_or_renamed(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        loc = warehouse(client, "USED")
        order = _submit_order(client, create(client))
        received = draft(client, order, 10, lines=[{"order_line_id": order["lines"][0]["id"],
            "delivered_quantity": "10", "received_quantity": "10", "unit_price": "2",
            "location_allocations": [{"location_id": loc["id"], "quantity": "10"}]}])
        assert received.status_code == 201, received.text
        blocked = remove(client, request(loc))
        assert blocked.status_code == 409 and "收料单" in blocked.text
        assert confirm(client, received.json()).status_code == 200
        assert remove(client, request(loc)).status_code == 409
        issued = client.post(BASE + "/inventory/movements", json=outbound(order, 10, location_id=loc["id"]))
        assert issued.status_code == 201, issued.text
        balances = client.get(BASE + "/inventory/positions", params={"factory_id": "huaxing"}).json()
        assert sum(Decimal(row["balance"]) for row in balances if row["location_id"] == loc["id"]) == 0
        renamed = client.patch(BASE + "/inventory/warehouses", json={**request(loc), "new_name": "RENAMED"})
        assert renamed.status_code == 200, renamed.text
        blocked = remove(client, request(renamed.json()[0]))
        assert blocked.status_code == 409 and "历史" in blocked.text
        stopped = client.patch(BASE + "/inventory/locations/" + loc["id"], json={"factory_id": "huaxing",
            "warehouse": "RENAMED", "bin_code": "01", "status": "INACTIVE", "expected_revision": 2,
            "reason": "保留历史停用仓位"})
        assert stopped.status_code == 200, stopped.text
        assert remove(client, request(stopped.json())).status_code == 409
        history = client.get(BASE + "/receipts", params={"factory_id": "huaxing"}).json()["items"]
        assert any(row["id"] == received.json()["id"] for row in history)


def test_legacy_labels_cancelled_counts_and_business_audit_prevent_delete(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
        from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
        from app.services.carton_positions import unknown_location
        legacy = warehouse(client, "LEGACY")
        # Legacy stock may have been allocated to the unknown location by migration.
        with SessionLocal() as db:
            db.add(CartonInventoryMovement(id="legacy", factory_id="huaxing", customer_code="DICKIE",
                customer_name="迪奇", contract_no="C", item_no="I", packaging_type="外箱", paper_quality="A33",
                specification="1", unit="个", currency="CNY", movement_type="INBOUND", quantity=1, unit_price=2,
                location="LEGACY / 01", document_no="OLD", source_type="MANUAL", source_id="OLD", source_line_id="1",
                actor_user_id="admin", actor_name="管理", occurred_at="2026-08-01T10:00:00+08:00"))
            db.commit()
        renamed = client.patch(BASE + "/inventory/warehouses", json={**request(legacy), "new_name": "LEGACY-NEW"})
        assert renamed.status_code == 200
        blocked = remove(client, request(renamed.json()[0]))
        assert blocked.status_code == 409 and "历史库存" in blocked.text
        counted = warehouse(client, "COUNTED")
        audited = warehouse(client, "AUDITED")
        with SessionLocal() as db:
            db.add(CartonStocktake(id="count", factory_id="huaxing", status="CANCELLED", created_by="admin",
                created_by_name="管理员", created_at="2026-08-01T10:00:00+08:00"))
            db.flush()
            db.add(CartonStocktakeLine(id="line", stocktake_id="count", factory_id="huaxing", inventory_key="legacy-key",
                reference_movement_id="legacy", snapshot_json=json.dumps({"location_id": counted["id"]}),
                initial_quantity=0, count_book_quantity=0))
            db.add(CartonAuditEvent(id=uuid4().hex, factory_id="huaxing", event_type="INVENTORY_LOCATION_CHANGED",
                entity_type="carton_inventory_location", entity_id="old-transfer", actor_user_id="admin", actor_name="管理",
                created_at="2026-08-01T10:00:00+08:00", detail_json=json.dumps({"request": {"location_id": audited["id"]}})))
            unknown = unknown_location(db, "huaxing")
            unknown_data = {"id": unknown.id, "warehouse": unknown.warehouse, "revision": unknown.revision}
            db.commit()
        assert "盘点" in remove(client, request(counted)).text
        assert "业务操作" in remove(client, request(audited)).text
        assert remove(client, request(unknown_data)).status_code == 422


def test_concurrent_delete_has_one_effect_and_foreign_history_is_isolated(monkeypatch):
    with make_client(monkeypatch) as client:
        prepare(client)
        loc = warehouse(client)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            db.add(CartonAuditEvent(id=uuid4().hex, factory_id="huakang", event_type="INVENTORY_LOCATION_CHANGED",
                entity_type="carton_inventory_location", entity_id="other", actor_user_id="admin", actor_name="管理",
                created_at="2026-08-01T10:00:00+08:00", detail_json=json.dumps({"location": "EMPTY／01"})))
            db.commit()
        gate = Barrier(2)
        def send():
            gate.wait(timeout=10)
            return remove(client, request(loc))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))
        assert sorted(row.status_code for row in results) == [200, 404]
        events = client.get(BASE + "/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        assert len([row for row in events if row["event_type"] == "MASTER_WAREHOUSE_DELETED"]) == 1
