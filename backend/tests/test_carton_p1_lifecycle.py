"""Independent P1 journeys: reading, agreement, stop notices and stale-page safety."""
from uuid import uuid4

import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import (
    setup_portal, supplier_login, revoke_supplier_permission,
    restore_supplier_permission, ship_payload,
)
from test_carton_special_requests import command, create_body, ok


FACTORY = "huaxing"
PORTAL = "/api/carton-supplier"
INTERNAL = "/api/carton-procurement"
SPECIAL = "/api/carton-special-requests"


@pytest.fixture(autouse=True)
def isolated_test_database(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, "TEST_TMP_DIR", tmp_path)


def task_for(client, kind, order_id):
    result = ok(client.get(PORTAL + "/changes", params={"factory_id": FACTORY}))
    return next(row for row in result["items"] if row["source_kind"] == kind and row["order_id"] == order_id)


def respond(client, task, action, **extra):
    return client.post(PORTAL + "/changes/respond", json={
        "factory_id": FACTORY, "source_kind": task["source_kind"], "source_id": task["source_id"],
        "expected_revision": task["expected_revision"], "action": action, "request_id": uuid4().hex,
        **extra,
    })


def no_inventory_writes():
    from sqlalchemy import func, select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonReceipt, CartonInventoryMovement
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CartonReceipt)) == 0
        assert db.scalar(select(func.count()).select_from(CartonInventoryMovement)) == 0


def test_read_dispute_and_stop_receipts_never_authorize_stale_execution(monkeypatch):
    with make_client(monkeypatch) as client:
        raw = setup_portal(client)
        order = ok(client.get(PORTAL + "/workspace", params={"factory_id": FACTORY}))["orders"][0]
        task = task_for(client, "REGULAR", raw["id"])
        assert task["pending"] and not task["read"]
        first = ok(respond(client, task, "READ"))
        second = ok(respond(client, task, "READ"))
        assert first["pending"] and second["pending"]
        assert first["read_at"] == second["read_at"]

        revoke_supplier_permission("carton_supplier:approve")
        supplier_login(client)
        assert respond(client, task, "READ").status_code == 200
        assert respond(client, task, "ACCEPT", promised_date="2026-10-25").status_code == 403
        restore_supplier_permission("carton_supplier:approve")
        supplier_login(client)
        assert respond(client, task, "ACCEPT", factory_id="huadeng", promised_date="2026-10-25").status_code in {403, 404, 409}
        acceptance_request = uuid4().hex
        accepted = ok(respond(client, task, "ACCEPT", promised_date="2026-10-25", request_id=acceptance_request))
        assert ok(respond(client, task, "ACCEPT", promised_date="2026-10-25", request_id=acceptance_request)) == accepted
        assert respond(client, task, "ACCEPT", promised_date="2026-10-26", request_id=acceptance_request).status_code == 409
        assert not accepted["pending"]
        disputed = ok(respond(client, task, "DISPUTE", reason="交期需双方重新核实"))
        assert disputed["pending"] and disputed["status"] == "DISPUTED"
        assert task_for(client, "REGULAR", raw["id"])["status"] == "DISPUTED"
        assert client.post(PORTAL + "/shipments", json=ship_payload(order)).status_code == 409
        stale_acceptance = client.put(PORTAL + f"/papers/{order['lines'][0]['id']}/commitment", json={
            "factory_id": FACTORY, "issue_id": task["source_id"], "expected_revision": 1,
            "promised_date": "2026-10-25"})
        assert stale_acceptance.status_code == 409, stale_acceptance.text
        ok(respond(client, task, "ACCEPT", promised_date="2026-10-26"))

        login_as(client, "admin")
        stop = ok(client.post(INTERNAL + f"/orders/{raw['order_no']}/cancel", json={
            "factory_id": FACTORY, "expected_revision": raw["revision"], "reason": "客户明确取消未执行需求"}))
        delete_payload = {"factory_id": FACTORY, "expected_revision": stop["revision"], "reason": "已取消订单完成归档"}
        delete_path = INTERNAL + f"/orders/{raw['order_no']}/delete"
        assert client.post(delete_path, json=delete_payload).status_code == 409
        supplier_login(client)
        assert respond(client, task, "ACCEPT", promised_date="2026-10-26").status_code == 409
        cancellation = task_for(client, "REGULAR", raw["id"])
        assert cancellation["is_cancellation"] and cancellation["pending"]
        assert ok(respond(client, cancellation, "READ"))["pending"]
        acknowledged = ok(respond(client, cancellation, "ACK_CANCEL"))
        assert not acknowledged["pending"]
        login_as(client, "admin")
        assert client.post(delete_path, json=delete_payload).status_code == 204
        supplier_login(client)
        assert not ok(client.get(PORTAL + "/changes", params={"factory_id": FACTORY}))["items"]
        assert client.post(PORTAL + "/shipments", json=ship_payload(order)).status_code in {404, 409}
        assert client.put(PORTAL + f"/papers/{order['lines'][0]['id']}/commitment", json={
            "factory_id": FACTORY, "issue_id": task["source_id"], "expected_revision": 2,
            "promised_date": "2026-10-26"}).status_code in {404, 409}
        no_inventory_writes()


def test_special_new_requirement_and_cancellation_each_need_exact_response(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        login_as(client, "admin")
        row = ok(client.post(SPECIAL, json=create_body()), 201)
        row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
        supplier_login(client)

        def shipment(current):
            return client.post(PORTAL + f"/special-requests/{current['id']}/ship", json=command(current,
                version_id=current["current_version_id"], delivery_note_no="P1-SP-" + uuid4().hex[:12],
                delivery_date="2026-10-18", lines=[{"line_id": current["lines"][0]["id"],
                    "quantity": "1", "unit_price": "2"}]))

        original = task_for(client, "SPECIAL", row["id"])
        assert shipment(row).status_code == 409
        ok(respond(client, original, "ACCEPT", promised_date="2026-10-20"))
        login_as(client, "admin")
        adjustment = create_body()
        adjustment.update(expected_revision=row["revision"], reason="客户调整实际需要数量")
        adjustment["lines"][0].update(id=row["lines"][0]["id"], quantity="80")
        row = ok(client.post(SPECIAL + f"/{row['id']}/adjust", json=adjustment))
        supplier_login(client)
        changed = task_for(client, "SPECIAL", row["id"])
        assert changed["source_id"] != original["source_id"] and changed["pending"]
        assert respond(client, original, "ACCEPT", promised_date="2026-10-20").status_code == 409
        assert shipment(row).status_code == 409
        ok(respond(client, changed, "DISPUTE", reason="已生产部分需要核对"))
        assert shipment(row).status_code == 409
        ok(respond(client, changed, "ACCEPT", promised_date="2026-10-21"))
        login_as(client, "admin")
        row = ok(client.post(SPECIAL + f"/{row['id']}/cancel", json=command(row)))
        delete_payload = command(row, reason="完成停止通知后归档")
        assert client.post(SPECIAL + f"/{row['id']}/delete", json=delete_payload).status_code == 409
        supplier_login(client)
        cancellation = task_for(client, "SPECIAL", row["id"])
        assert cancellation["is_cancellation"] and cancellation["pending"]
        assert ok(respond(client, cancellation, "READ"))["pending"]
        ok(respond(client, cancellation, "ACK_CANCEL"))
        login_as(client, "admin")
        ok(client.post(SPECIAL + f"/{row['id']}/delete", json=delete_payload))
        supplier_login(client)
        assert shipment(row).status_code in {404, 409}
        no_inventory_writes()
