from decimal import Decimal

import pytest

from test_carton_procurement_api import _create_order, _freeze_carton_time
from test_carton_replenishment_api import setup, body, replenish
from test_molding_sample_api import login_as, make_client


@pytest.mark.parametrize("username", ["warehouse_keeper", "carton_warehouse", "carton_supervisor"])
def test_warehouse_and_supervisor_append_reduce_and_return_submitted_order(monkeypatch, username):
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = _create_order(client)
        profile = login_as(client, username)
        assert ("carton_procurement:order_adjust" in profile["permissions"]) == (username == "carton_supervisor")
        for action, quantity, expected_quantity, expected_status in [
            ("append", "600", "4200", "PENDING_SUPPLIER"),
            ("reduce", "600", "3600", "PENDING_SUPPLIER"),
            ("reduce", "3600", "3600", "CANCELLED"),
        ]:
            response = client.post(f"/api/carton-procurement/orders/{row['order_no']}/{action}", json={
                "factory_id": "huaxing", "expected_revision": row["revision"],
                "additional_quantity" if action == "append" else "reduction_quantity": quantity,
            })
            assert response.status_code == 200, response.text
            row = response.json()
            assert Decimal(row["product_order_quantity"]) == Decimal(expected_quantity)
            assert row["status"] == expected_status


@pytest.mark.parametrize("username", ["warehouse_keeper", "carton_warehouse"])
@pytest.mark.parametrize("replace_stock", [False, True])
def test_warehouse_keeps_replenishment_and_can_append_after_completed_or_partial_receipt(monkeypatch, username, replace_stock):
    with make_client(monkeypatch) as client:
        row, stocks = setup(client, monkeypatch)
        assert row["status"] == "COMPLETED"
        login_as(client, username)
        if replace_stock:
            response = replenish(client, row, body(row, stocks))
            assert response.status_code == 201, response.text
            row = response.json()["order"]
            assert row["status"] == "PARTIALLY_RECEIVED"
        response = client.post(f"/api/carton-procurement/orders/{row['order_no']}/append", json={
            "factory_id": "huaxing", "expected_revision": row["revision"], "additional_quantity": "10",
        })
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "PARTIALLY_RECEIVED"


@pytest.mark.parametrize("case", ["order_only", "inventory_only", "foreign_inventory", "other_department", "deny_inventory", "deny_order", "supervisor_only"])
def test_adjustment_checks_each_scoped_permission_and_explicit_denies(monkeypatch, case):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login_as(client, "warehouse_keeper")
        _freeze_carton_time(monkeypatch)
        row = _create_order(client)
        from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user

        def grant(permission, factory="huaxing", department="pmc-warehouse"):
            return AuthGrantContext("test-role", "Test role", factory, department, frozenset({f"carton_procurement:{permission}"}))

        grants = [grant("order_write")]
        if case == "inventory_only":
            grants = [grant("inventory_write")]
        elif case == "supervisor_only":
            grants = [grant("order_adjust")]
        elif case != "order_only":
            grants.append(grant("inventory_write", "huadeng" if case == "foreign_inventory" else "huaxing",
                                "qc" if case == "other_department" else "pmc-warehouse"))
        overrides = ()
        if case.startswith("deny_"):
            permission = "inventory_write" if case == "deny_inventory" else "order_write"
            overrides = (AuthOverrideContext("test-deny", f"carton_procurement:{permission}", "deny", "huaxing", "pmc-warehouse"),)
        actor = AuthContext("user-warehouse", "scoped_operator", "Scoped operator", (), (),
                            frozenset(p for g in grants for p in g.permissions), ("huaxing",), ("pmc-warehouse",),
                            grants=tuple(grants), overrides=overrides)
        client.app.dependency_overrides[get_current_user] = lambda: actor
        for action in ("append", "reduce"):
            response = client.post(f"/api/carton-procurement/orders/{row['order_no']}/{action}", json={
                "factory_id": "huaxing", "expected_revision": row["revision"],
                "additional_quantity" if action == "append" else "reduction_quantity": "600",
            })
            expected = 200 if case == "supervisor_only" and action == "reduce" else 403
            assert response.status_code == expected, response.text
        client.app.dependency_overrides.clear()
        current = client.get("/api/carton-procurement/orders", params={"factory_id": "huaxing"}).json()["items"][0]
        assert current["revision"] == row["revision"] + (1 if case == "supervisor_only" else 0)
