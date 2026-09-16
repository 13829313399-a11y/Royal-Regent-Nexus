"""Warehouse manager scope, existing bindings, and real inventory API isolation."""

import importlib
from dataclasses import replace

import pytest
from sqlalchemy import select

from test_raw_material_api import create_fixed_position_user, login_fixed_position_user
from test_system_position_catalog import make_client
from test_auth_api import make_client as make_mode_client


FACTORIES = ("huaxing", "huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng")
POSITIONS = ("manager", "supervisor", "keeper")


def create_users():
    for position in POSITIONS:
        create_fixed_position_user(
            f"warehouse-{position}", f"position_warehouse_{position}", "pmc-warehouse"
        )


def test_persisted_warehouse_permissions_and_explicit_deny(monkeypatch):
    with make_client(monkeypatch):
        create_users()
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        auth = importlib.import_module("app.services.auth")
        positions = importlib.import_module("app.services.system_positions")
        with db_module.SessionLocal() as db:
            contexts = {
                position: auth.build_auth_context(db, db.get(models.AuthUser, f"user-warehouse-{position}"))
                for position in POSITIONS
            }
        for position, context in contexts.items():
            for factory in FACTORIES:
                for permission in positions.WAREHOUSE_PERMISSION_CODES:
                    expected = position == "manager" or factory == "huaxing" or permission == "molding_sample:production_read"
                    assert auth.can(context, permission, factory, "pmc-warehouse") is expected, (position, factory, permission)
                for permission in (
                    "molding_sample:create", "molding_sample:supervisor_review",
                    "molding_sample:production_start", "molding_sample:dispatch",
                    "carton_procurement:customer_manage", "carton_procurement:order_adjust",
                    "internal_quote:engineering_edit", "customer_order:write",
                    "injection_scheduling:plan", "system:user_manage",
                ):
                    assert not auth.can(context, permission, factory, "*")

        manager = contexts["manager"]
        for factory in FACTORIES:
            assert auth.can(manager, "molding_sample:notification_read", factory, "warehouse")
            assert not auth.can(manager, "molding_sample:notification_read", factory, "engineering")
            for permission in ("customer_order:inbox_read", "customer_order:inbox_receive"):
                assert auth.can(manager, permission, factory, "warehouse")
                assert not auth.can(manager, permission, factory, "production")
                assert not auth.can(manager, permission, factory, "molding")
        denied = replace(manager, overrides=(auth.AuthOverrideContext(
            id="deny-huadeng-issue", permission_code="molding_sample:inventory_issue",
            effect="deny", factory_id="huadeng", department="*",
        ),))
        assert not auth.can(denied, "molding_sample:inventory_issue", "huadeng", "pmc-warehouse")
        assert auth.can(denied, "molding_sample:inventory_issue", "huakang-a", "pmc-warehouse")


@pytest.mark.parametrize("position", POSITIONS)
@pytest.mark.parametrize("authz_mode", ("legacy", "shadow", "enforce"))
def test_warehouse_inventory_and_inbox_api_factory_boundary(monkeypatch, position, authz_mode):
    with make_mode_client(monkeypatch, AUTHZ_MODE=authz_mode, AUTHZ_WRITES_ENABLED="false") as client:
        create_fixed_position_user(f"warehouse-{position}", f"position_warehouse_{position}", "pmc-warehouse")
        profile = login_fixed_position_user(client, f"warehouse-{position}")
        grant = next(item for item in profile["grants"] if item["role_id"] == f"position_warehouse_{position}")
        assert grant["scope_mode"] == ("cross_factory_operate" if position == "manager" else "own_factory")
        for factory in ("huaxing", "huakang-a", "huakang-b", "huadeng"):
            allowed = position == "manager" or factory == "huaxing"
            batch = client.post("/api/inventory-batches", json={
                "factory_id": factory, "material": "scope-test-ABS", "batch_no": f"scope-{factory}",
                "location": "A-01", "initial_weight_kg": 10,
            })
            assert batch.status_code == (201 if allowed else 403), batch.text
            if allowed:
                assert batch.json()["factory_id"] == factory
            listed = client.get("/api/inventory-batches", params={"factory_id": factory})
            assert listed.status_code == (200 if allowed else 403), listed.text
            if allowed:
                assert {row["factory_id"] for row in listed.json()} == {factory}
            raw_material = client.post("/api/raw-materials", json={
                "factory_id": factory, "material_name": f"scope-{factory}", "category": "ABS", "unit": "KG",
            })
            assert raw_material.status_code == (201 if allowed else 403), raw_material.text
            caps = client.get("/api/customer-order-ledger/capabilities", params={"factory_id": factory, "recipient": "pmc"})
            assert caps.status_code == 200
            assert caps.json()["inbox_read"] is allowed
            assert caps.json()["inbox_receive"] is allowed
            assert caps.json()["write"] is False
            inbox = client.get("/api/customer-order-ledger/inbox", params={"factory_id": factory, "recipient": "pmc"})
            assert inbox.status_code == (200 if allowed else 403), inbox.text
        if position == "manager":
            caps = client.get("/api/customer-order-ledger/capabilities", params={"factory_id": "huadeng", "recipient": "injection"})
            assert caps.json()["inbox_read"] is False
            assert caps.json()["inbox_receive"] is False
            assert client.get("/api/customer-order-ledger/inbox", params={"factory_id": "huadeng", "recipient": "injection"}).status_code == 403
            assert client.post("/api/customer-order-ledger/inbox/missing/receive", params={"factory_id": "huadeng", "recipient": "injection"}).status_code == 403
        unfiltered = client.get("/api/inventory-batches")
        assert unfiltered.status_code == 200
        expected_factories = {"huaxing", "huakang-a", "huakang-b", "huadeng"} if position == "manager" else {"huaxing"}
        assert {row["factory_id"] for row in unfiltered.json()} == expected_factories
        if position == "manager":
            # A separate, valid injection position must remain independent of
            # the warehouse grant's department restriction in every mode.
            db_module = importlib.import_module("app.db")
            models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                db.add(models.AuthUserRole(
                    id="warehouse-manager-extra-injection", user_id="user-warehouse-manager",
                    role_id="position_molding_manager", factory_id="huadeng", department="production",
                ))
                db.commit()
            caps = client.get("/api/customer-order-ledger/capabilities", params={"factory_id": "huadeng", "recipient": "injection"})
            assert caps.json()["inbox_read"] is True
            assert caps.json()["inbox_receive"] is True


def test_existing_manager_binding_reconciles_without_relogin(monkeypatch):
    with make_client(monkeypatch) as client:
        create_users()
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        reconcile = importlib.import_module("app.services.system_position_reconcile")
        role_id = "position_warehouse_manager"
        user_id = "user-warehouse-manager"
        with db_module.SessionLocal() as db:
            metadata = db.get(models.AuthRoleMetadata, role_id)
            metadata.scope_mode = "own_factory"
            db.commit()
        login_fixed_position_user(client, "warehouse-manager")
        assert client.get("/api/inventory-batches", params={"factory_id": "huadeng"}).status_code == 403
        with db_module.SessionLocal() as db:
            bindings = [(row.id, row.factory_id, row.department) for row in db.scalars(select(models.AuthUserRole).where(models.AuthUserRole.user_id == user_id))]
            before_revision = db.get(models.AuthUserAuthorizationRevision, user_id).revision
            result = reconcile.reconcile_system_position_catalog(db)
            assert result.changed_role_ids == (role_id,)
            assert result.changed_user_ids == (user_id,)
            assert db.get(models.AuthUserAuthorizationRevision, user_id).revision == before_revision + 1
            assert bindings == [(row.id, row.factory_id, row.department) for row in db.scalars(select(models.AuthUserRole).where(models.AuthUserRole.user_id == user_id))]
            for position in ("supervisor", "keeper"):
                assert db.get(models.AuthRoleMetadata, f"position_warehouse_{position}").scope_mode == "own_factory"
            assert reconcile.reconcile_system_position_catalog(db).changed_role_ids == ()
            db.commit()
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["authorization_version"] == before_revision + 1
        assert client.get("/api/inventory-batches", params={"factory_id": "huadeng"}).status_code == 200
