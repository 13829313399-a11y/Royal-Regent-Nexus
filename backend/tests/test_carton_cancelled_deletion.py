"""Cancelled ledger removal must never cascade into accounting or supplier evidence."""
import importlib.util
import json
from pathlib import Path
import pytest
from sqlalchemy import select, text, create_engine, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_molding_sample_api import make_client, login_as
from test_carton_order_delete import BASE, delete_body, current_orders
from test_carton_receipt_correction_api import receipt, reverse
from test_carton_supplier_portal import setup_portal, accept_all, ship_payload, receive_payload


@pytest.mark.parametrize("receipt_mode", ["pending", "posted", "reversed"])
def test_cancelled_removal_preserves_all_references_and_batch_is_atomic(monkeypatch, receipt_mode):
    with make_client(monkeypatch) as client:
        original = setup_portal(client)
        supplier_order = accept_all(client)
        shipment = client.post("/api/carton-supplier/shipments", json=ship_payload(supplier_order))
        assert shipment.status_code == 201, shipment.text
        login_as(client, "admin")
        sent = shipment.json()
        not_received = receive_payload(client, sent)
        for line in not_received["lines"]:
            line.update(received_quantity=0, location_allocations=[], difference_reason="该次送货整单未收到")
        response = client.post(f"/api/carton-supplier/internal/shipments/{sent['id']}/receive", json=not_received)
        assert response.status_code == 200 and response.json()["status"] == "NOT_RECEIVED", response.text
        doc = receipt(client, original, post=receipt_mode != "pending")
        if receipt_mode == "reversed":
            assert reverse(client, doc).status_code == 200
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonAuditEvent, CartonException
        from app.models.carton_supplier_portal import SupplierAttachment
        watched = ("carton_order_lines", "carton_purchase_order_issues", "carton_receipts", "carton_receipt_lines",
                   "carton_inventory_movements", "carton_supplier_commitments", "carton_supplier_shipments",
                   "carton_supplier_shipment_lines", "carton_supplier_attachments")
        with SessionLocal() as db:
            # Emulate a legacy cancelled record with evidence; do not weaken ordinary cancellation rules.
            order = db.get(CartonOrder, original["id"])
            order.status = "CANCELLED"
            db.add(SupplierAttachment(id="attachment-old", factory_id="huaxing", order_id=order.id,
                filename="original.pdf", media_type="application/pdf", version=1, size=3,
                sha256="old", content=b"pdf", created_by="admin", created_at="old"))
            db.add(CartonAuditEvent(factory_id="huaxing", id="split-old", event_type="ORDER_SPLIT_CREATED",
                entity_type="carton_order_split", entity_id="split-old", actor_user_id="admin", actor_name="Admin",
                created_at="old", detail_json=json.dumps({"plan": {"id": "split-old", "factory_id": "huaxing",
                    "order_id": order.id, "status": "CANCELLED", "targets": []}})))
            db.add(CartonException(id="owned-task", factory_id="huaxing", exception_no="EX-OLD", source_type="ORDER",
                source_id=order.id, category="TEST", severity="LOW", title="旧任务", status="OPEN", revision=1,
                created_by="admin", updated_by="admin", created_at="old", updated_at="old"))
            db.commit()
            before = {table: db.execute(text(f'SELECT * FROM "{table}"')).all() for table in watched}
        current = current_orders(client)[0]
        assert current["can_delete"] and current["split_records"]
        body = {"factory_id": "huaxing", "reason": "清理已取消历史订单", "items": [
            {"order_no": current["order_no"], "expected_revision": current["revision"]},
            {"order_no": "missing", "expected_revision": 1}]}
        assert client.post(BASE + "/orders/bulk-delete", json=body).status_code == 404
        assert current_orders(client)[0] == current
        login_as(client, "warehouse_keeper")
        assert client.post(f"{BASE}/orders/{current['order_no']}/delete", json=delete_body(current)).status_code == 403
        login_as(client, "admin")
        assert client.post(f"{BASE}/orders/{current['order_no']}/delete", json=delete_body(current)).status_code == 204
        assert not current_orders(client)
        assert client.post(f"{BASE}/orders/{current['order_no']}/delete", json=delete_body(current)).status_code == 404
        assert client.post(f"{BASE}/orders/{current['order_no']}/submit-supplier", json=delete_body(current)).status_code == 404
        assert client.patch(BASE + "/exceptions/owned-task", json={"factory_id": "huaxing",
            "expected_revision": 2, "status": "OPEN"}).status_code == 409
        with SessionLocal() as db:
            retained = db.get(CartonOrder, current["id"])
            assert retained.status == "CANCELLED" and retained.deleted_at and retained.revision == current["revision"] + 1
            assert db.get(CartonException, "owned-task").status == "CLOSED"
            for table, rows in before.items():
                assert db.execute(text(f'SELECT * FROM "{table}"')).all() == rows
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        workspace = client.get("/api/carton-supplier/internal/workspace", params={"factory_id": "huaxing"})
        assert workspace.status_code == 200, workspace.text
        assert not workspace.json()["orders"]
        assert len(workspace.json()["shipments"]) == 1


def test_deletion_migration_is_additive_and_guard_rejects_old_schema(monkeypatch):
    backend = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("cancelled_deletion_migration",
        backend / "alembic/versions/20260929_0126_cancelled_order_deletion.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
        connection.exec_driver_sql("CREATE TABLE carton_orders (id TEXT PRIMARY KEY, status TEXT)")
        connection.exec_driver_sql("CREATE TABLE children (id TEXT, order_id TEXT REFERENCES carton_orders(id) ON DELETE CASCADE)")
        connection.exec_driver_sql("INSERT INTO carton_orders VALUES ('O1','CANCELLED')")
        connection.exec_driver_sql("INSERT INTO children VALUES ('C1','O1')")
    from app import db
    monkeypatch.setattr(db, "engine", engine)
    with pytest.raises(RuntimeError, match="0126"):
        db.ensure_carton_order_deletion_schema_ready()
    assert "deleted_at" not in {column["name"] for column in inspect(engine).get_columns("carton_orders")}
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            with pytest.raises(RuntimeError):
                migration.downgrade()
        assert connection.exec_driver_sql("SELECT * FROM carton_orders").all() == [("O1", "CANCELLED", None)]
        assert connection.exec_driver_sql("SELECT * FROM children").all() == [("C1", "O1")]
    db.ensure_carton_order_deletion_schema_ready()
    engine.dispose()
