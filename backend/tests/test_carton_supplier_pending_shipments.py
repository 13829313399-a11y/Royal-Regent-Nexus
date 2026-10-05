"""Factory receiving reminders must reflect shipment state, not personal duties."""
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import (
    BASE, setup_portal, accept_all, ship_payload, receive_payload,
)

ENDPOINT = BASE + "/internal/shipments/pending"


def pending(client, factory="huaxing", **params):
    response = client.get(ENDPOINT, params={"factory_id": factory, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_dashboard_tracks_receipt_completion_and_reversed_corrections(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = accept_all(client)
        shipment = client.post(BASE + "/shipments", json=ship_payload(order)).json()
        login_as(client, "admin")
        # Administrators deliberately do not inherit every employee's personal duty.
        personal = client.get("/api/work-center/snapshot", params={
            "view": "todo", "module": "carton_supplier", "factory_scope": "huaxing"})
        assert personal.status_code == 200, personal.text
        assert personal.json()["items"] == []
        result = pending(client)
        assert result["total"] == 1
        assert result["items"][0] == {
            "id": shipment["id"], "delivery_note_no": shipment["delivery_note_no"],
            "delivery_date": shipment["delivery_date"], "requires_correction": False,
        }
        login_as(client, "warehouse_keeper")
        assert pending(client)["total"] == 1
        received = client.post(BASE + f"/internal/shipments/{shipment['id']}/receive",
                               json=receive_payload(client, shipment))
        assert received.status_code == 200, received.text
        assert pending(client) == {"factory_id": "huaxing", "total": 0, "items": []}
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonReceipt
        from app.models.carton_supplier_portal import SupplierShipment
        with SessionLocal() as db:
            revision = db.get(CartonReceipt, received.json()["receipt_id"]).revision
        reversed_receipt = client.post(
            f"/api/carton-procurement/receipts/{received.json()['receipt_id']}/reverse",
            json={"factory_id": "huaxing", "expected_revision": revision,
                  "reason": "复核实际数量需要更正验收"})
        assert reversed_receipt.status_code == 200, reversed_receipt.text
        assert pending(client)["items"][0]["requires_correction"] is True
        # Legacy reversals may retain RECEIVED; the read must include them without repairs.
        with SessionLocal() as db:
            db.get(SupplierShipment, shipment["id"]).status = "RECEIVED"
            db.commit()
        assert pending(client)["total"] == 1
        with SessionLocal() as db:
            assert db.get(SupplierShipment, shipment["id"]).status == "RECEIVED"


def test_pending_shipment_count_is_bounded_and_factory_supplier_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        assert client.get(ENDPOINT, params={"factory_id": "huaxing"}).status_code == 401
        raw = setup_portal(client)
        login_as(client, "admin")
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        from app.models.carton_supplier_portal import SupplierShipment
        with SessionLocal() as db:
            db.add(CartonSupplier(id="other-vendor", factory_id="huaxing", supplier_code="OTHER",
                supplier_name="其他供应商", status="ACTIVE", created_at="2026-09-21", updated_at="2026-09-21"))
            other_factory_supplier = db.scalar(select(CartonSupplier).where(
                CartonSupplier.factory_id == "huakang-a", CartonSupplier.supplier_code == "HEYUAN-DONGKANG"))
            assert other_factory_supplier is not None
            db.flush()
            sources = [(f"pending-{i}", "huaxing", raw["supplier_id"], "SENT") for i in range(5)]
            sources += [("not-arrived", "huaxing", raw["supplier_id"], "NOT_RECEIVED"),
                        ("other-vendor-note", "huaxing", "other-vendor", "SENT"),
                        ("other-factory-note", "huakang-a", other_factory_supplier.id, "SENT")]
            for identifier, factory, supplier, state in sources:
                db.add(SupplierShipment(id=identifier, factory_id=factory, supplier_id=supplier,
                    delivery_note_no=identifier, delivery_date="2026-09-24", status=state,
                    revision=1, request_id=str(uuid4()), fingerprint="test", created_by="admin",
                    created_at="2026-09-24T09:00:00+08:00"))
            db.commit()
        result = pending(client, limit=3)
        assert result["total"] == 5
        assert [item["id"] for item in result["items"]] == ["pending-4", "pending-3", "pending-2"]
        assert pending(client, "huakang-a")["items"][0]["id"] == "other-factory-note"
        login_as(client, "warehouse_keeper")
        assert pending(client)["total"] == 5
        assert client.get(ENDPOINT, params={"factory_id": "huakang-a"}).status_code == 403
        for limit in (0, 101):
            assert client.get(ENDPOINT, params={"factory_id": "huaxing", "limit": limit}).status_code == 422


@pytest.mark.parametrize("permission", ["carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write"])
def test_pending_shipments_require_all_receiving_permissions(monkeypatch, permission):
    with make_client(monkeypatch) as client:
        from app.services.auth import settings
        # Canonical explicit denies are enforced only in the configurable IAM mode.
        monkeypatch.setattr(settings, "authz_mode", "enforce")
        setup_portal(client)
        assert client.get(ENDPOINT, params={"factory_id": "huaxing"}).status_code == 403
        profile = login_as(client, "warehouse_keeper")
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        with SessionLocal() as db:
            permission_id = db.scalar(select(AuthPermission.id).where(AuthPermission.code == permission))
            db.add(AuthUserPermissionOverride(id=f"pending-deny-{permission}", user_id=profile["id"],
                permission_id=permission_id, effect="deny", factory_id="huaxing", department="*",
                status="active", reason="测试收料权限边界"))
            db.commit()
        assert client.get(ENDPOINT, params={"factory_id": "huaxing"}).status_code == 403


def test_pending_count_and_preview_share_a_snapshot_during_supplier_dispatch(monkeypatch):
    from threading import Event, Thread
    from fastapi.testclient import TestClient
    from sqlalchemy import Table, event
    from sqlalchemy.sql.visitors import iterate

    with make_client(monkeypatch) as supplier_client:
        setup_portal(supplier_client)
        order = accept_all(supplier_client)
        reader_client = TestClient(supplier_client.app)
        login_as(reader_client, "admin")
        from app.db import engine
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        read_started, dispatch_committed = Event(), Event()
        reading = {}

        def pause_snapshot(connection, cursor, statement, parameters, context, executemany):
            compiled = context.compiled
            if (not connection.info.get("snapshot_reader") or read_started.is_set()
                    or not compiled or not compiled.statement.is_select):
                return
            if any(isinstance(node, Table) and node.name == "carton_supplier_shipments"
                   for node in iterate(compiled.statement)):
                read_started.set()
                assert dispatch_committed.wait(20), "Supplier dispatch did not finish"

        # Mark only the reader request's connection; supplier writes use a separate session.
        from app.db import get_db
        original_get_db = get_db
        from fastapi import Request

        def reader_db(request: Request):
            for db in original_get_db():
                connection = db.connection()
                is_reader = request.headers.get("x-test-snapshot-reader") == "yes"
                if is_reader:
                    connection.info["snapshot_reader"] = True
                try:
                    yield db
                finally:
                    if is_reader:
                        connection.info.pop("snapshot_reader", None)

        supplier_client.app.dependency_overrides[get_db] = reader_db

        def read_pending():
            try:
                reading["response"] = reader_client.get(ENDPOINT,
                    params={"factory_id": "huaxing"}, headers={"x-test-snapshot-reader": "yes"})
            except BaseException as error:
                reading["error"] = error

        event.listen(engine, "after_cursor_execute", pause_snapshot)
        reader = Thread(target=read_pending, daemon=True)
        try:
            reader.start()
            assert read_started.wait(20), "Pending shipment read did not reach its snapshot"
            sent = supplier_client.post(BASE + "/shipments", json=ship_payload(order))
            assert sent.status_code == 201, sent.text
        finally:
            dispatch_committed.set()
            reader.join(timeout=20)
            event.remove(engine, "after_cursor_execute", pause_snapshot)
            supplier_client.app.dependency_overrides.pop(get_db, None)
        assert not reader.is_alive()
        assert "error" not in reading, reading.get("error")
        assert reading["response"].status_code == 200, reading["response"].text
        assert reading["response"].json() == {"factory_id": "huaxing", "total": 0, "items": []}
        fresh = pending(reader_client)
        assert fresh["total"] == 1
        assert fresh["items"][0]["id"] == sent.json()["id"]
        reader_client.close()
