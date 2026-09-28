import pytest

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _create_order, _freeze_carton_time
from test_carton_receipt_correction_api import receipt, reverse
from test_carton_history_delete_and_exception_bulk import historical


BASE = "/api/carton-procurement"


def delete_body(order, **changes):
    return {"factory_id": "huaxing", "expected_revision": order["revision"],
            "reason": "订单重复录入需删除", **changes}


def current_orders(client):
    return client.get(f"{BASE}/orders", params={"factory_id": "huaxing"}).json()["items"]


@pytest.mark.parametrize("status", ["CONFIRMED", "PENDING_SUPPLIER", "CANCELLED"])
def test_supervisor_deletes_unused_ordinary_orders_with_full_audit(monkeypatch, status):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        submitted = status == "PENDING_SUPPLIER"
        order = _create_order(client, submit_supplier=submitted)
        login_as(client, "admin")
        if status == "CANCELLED":
            response = client.post(f"{BASE}/orders/{order['order_no']}/cancel", json=delete_body(order))
            assert response.status_code == 200, response.text
            order = response.json()
        assert order["status"] == status
        assert order["can_delete"] and not order["can_delete_history"]
        path = f"{BASE}/orders/{order['order_no']}/delete"
        assert client.post(path, json=delete_body(order, reason="   错")).status_code == 422
        assert client.post(path, json=delete_body(order, expected_revision=99)).status_code == 409
        assert client.post(path, json=delete_body(order, factory_id="huadeng")).status_code == 404
        assert client.post(path, json=delete_body(order)).status_code == 204
        assert not current_orders(client)
        assert client.post(path, json=delete_body(order)).status_code == 404
        audits = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        event = next(row for row in audits if row["event_type"] == "ORDER_DELETED")
        assert event["actor_user_id"] and event["detail"]["reason"] == delete_body(order)["reason"]
        assert event["detail"]["order"]["lines"]
        assert event["detail"]["order"]["status"] == status
        assert bool(event["detail"]["purchase_issues"]) == submitted
        if status == "CANCELLED":
            assert any(row["event_type"] == "ORDER_CANCELLED" and row["entity_id"] == order["id"] for row in audits)
        assert client.get(f"{BASE}/customers", params={"factory_id": "huaxing"}).json()["total"] == 1


@pytest.mark.parametrize("mode", ["pending", "posted", "reversed", "voided", "returned"])
def test_ordinary_order_with_receipt_evidence_cannot_be_deleted(monkeypatch, mode):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        order = _create_order(client)
        login_as(client, "admin")
        doc = receipt(client, order, post=mode in {"posted", "reversed", "returned"})
        if mode == "reversed":
            assert reverse(client, doc).status_code == 200
        if mode == "voided":
            response = reverse(client, doc, reason="待收记录作废测试")
            assert response.status_code == 200, response.text
        if mode == "returned":
            current = next(row for row in current_orders(client) if row["id"] == order["id"])
            response = client.post(f"{BASE}/orders/{order['order_no']}/return", json=delete_body(current))
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "CANCELLED"
        current = next(row for row in current_orders(client) if row["id"] == order["id"])
        assert not current["can_delete"] and "收料" in current["deletion_block_reason"]
        response = client.post(f"{BASE}/orders/{order['order_no']}/delete", json=delete_body(current))
        assert response.status_code == 409, response.text
        assert len(current_orders(client)) == 1


@pytest.mark.parametrize("mixed", [False, True])
def test_supervisor_bulk_deletes_cancelled_orders_and_preserves_cancellation_audits(monkeypatch, mixed):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        rows = []
        for index in range(2):
            row = _create_order(client, submit_supplier=False)
            login_as(client, "admin")
            if not mixed or index == 0:
                response = client.post(f"{BASE}/orders/{row['order_no']}/cancel", json=delete_body(row))
                assert response.status_code == 200, response.text
                row = response.json()
            assert row["can_delete"]
            rows.append(row)
        body = {"factory_id": "huaxing", "reason": "清理已取消及重复订单", "items": [
            {"order_no": row["order_no"], "expected_revision": row["revision"]} for row in rows]}
        stale = {**body, "items": [body["items"][0], {**body["items"][1], "expected_revision": 99}]}
        assert client.post(f"{BASE}/orders/bulk-delete", json=stale).status_code == 409
        assert {row["id"] for row in current_orders(client)} == {row["id"] for row in rows}
        assert client.post(f"{BASE}/orders/bulk-delete", json=body).status_code == 204
        assert not current_orders(client)
        audits = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        deleted = [event for event in audits if event["event_type"] == "ORDER_DELETED"]
        assert len(deleted) == 2
        assert len({event["detail"]["operation_id"] for event in deleted}) == 1
        assert {event["detail"]["order"]["status"] for event in deleted} == (
            {"CONFIRMED", "CANCELLED"} if mixed else {"CANCELLED"})
        cancelled = [event for event in audits if event["event_type"] == "ORDER_CANCELLED"]
        assert len(cancelled) == (1 if mixed else 2)


def test_supplier_acceptance_blocks_order_deletion(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        order = _create_order(client)
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        from app.models.carton_supplier_portal import SupplierCommitment
        from sqlalchemy import select
        with SessionLocal() as db:
            issue = db.scalar(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == order["id"]))
            db.add(SupplierCommitment(order_line_id=order["lines"][0]["id"], factory_id="huaxing",
                issue_id=issue.id, promised_date="2026-08-12", revision=1,
                accepted_by="supplier", accepted_at="2026-08-05T10:00:00+08:00"))
            db.commit()
        current = current_orders(client)[0]
        assert not current["can_delete"] and "供应商" in current["deletion_block_reason"]
        assert client.post(f"{BASE}/orders/{order['order_no']}/delete", json=delete_body(current)).status_code == 409


@pytest.mark.parametrize("operation", ["delete", "bulk-delete", "delete-history", "bulk-delete-history"])
def test_warehouse_operator_cannot_bypass_supervisor_gate(monkeypatch, operation):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        order = historical(client) if "history" in operation else _create_order(client)
        login_as(client, "warehouse_keeper")
        if operation.startswith("bulk"):
            path = f"{BASE}/orders/{operation}"
            body = {"factory_id": "huaxing", "reason": "订单重复录入需删除", "items": [
                {"order_no": order["order_no"], "expected_revision": order["revision"]}]}
        else:
            path, body = f"{BASE}/orders/{order['order_no']}/{operation}", delete_body(order)
        assert client.post(path, json=body).status_code == 403
        login_as(client, "admin")
        assert len(current_orders(client)) == 1


@pytest.mark.parametrize("scope", ["own", "foreign", "department", "denied", "no_write"])
def test_deletion_requires_both_factory_scoped_supervisor_and_write_permissions(monkeypatch, scope):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        order = _create_order(client)
        from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
        permissions = frozenset({"carton_procurement:order_adjust"} | (
            set() if scope == "no_write" else {"carton_procurement:order_write"}))
        grant = AuthGrantContext("position_carton_supervisor", "纸箱主管",
            "huadeng" if scope == "foreign" else "huaxing", "qc" if scope == "department" else "carton", permissions)
        overrides = (AuthOverrideContext("deny-delete", "carton_procurement:order_adjust", "deny", "huaxing", "carton"),) if scope == "denied" else ()
        actor = AuthContext("supervisor", "supervisor", "纸箱主管", ("主管",), (grant.role_id,),
            permissions, (grant.factory_id,), (grant.department,), grants=(grant,), overrides=overrides)
        client.app.dependency_overrides[get_current_user] = lambda: actor
        response = client.post(f"{BASE}/orders/{order['order_no']}/delete", json=delete_body(order))
        assert response.status_code == (204 if scope == "own" else 403), response.text


def test_bulk_delete_rejects_whole_selection_if_one_order_received(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        _freeze_carton_time(monkeypatch)
        first, second = _create_order(client), _create_order(client)
        login_as(client, "admin")
        receipt(client, second, post=True)
        rows = current_orders(client)
        response = client.post(f"{BASE}/orders/bulk-delete", json={
            "factory_id": "huaxing", "reason": "订单重复录入需删除", "items": [
                {"order_no": row["order_no"], "expected_revision": row["revision"]} for row in rows]})
        assert response.status_code == 409, response.text
        assert current_orders(client) == rows
        assert any(row["id"] == first["id"] for row in rows)
        audits = client.get(f"{BASE}/audit-events", params={"factory_id": "huaxing"}).json()["items"]
        assert not any(row["event_type"] == "ORDER_DELETED" for row in audits)
