"""Claim authority, receipt isolation and preservation of independent originals."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select

from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_customer_packaging import customer, assign, BASE, SCOPE
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_mark_assets import upload
from test_carton_mark_api import _workbook_bytes


def test_claim_cannot_grant_iam_or_cross_factory_and_delegation_is_owner_only(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        entry = customer(client)
        ensure_test_user("warehouse_keeper"); ensure_test_user("carton_warehouse"); ensure_test_user("a_warehouse_keeper")
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        with SessionLocal() as db:
            ids = dict(db.execute(select(AuthUser.username, AuthUser.id)).all())
        login_as(client, "warehouse_keeper")
        claimed = client.post(f"{BASE}/customers/{entry['id']}/claim", json={**SCOPE, "expected_revision": 1})
        assert claimed.status_code == 200, claimed.text
        current = next(row for row in claimed.json()["customers"] if row["id"] == entry["id"])
        before = login_as(client, "warehouse_keeper")["permissions"]
        for selected in [[ids["a_warehouse_keeper"]], [ids["warehouse_keeper"], ids["a_warehouse_keeper"]]]:
            response = client.put(f"{BASE}/customers/{entry['id']}/responsibilities", json={**SCOPE,
                "user_ids": selected, "expected_revision": current["revision"], "reason": "跨厂授权应被拒绝"})
            assert response.status_code == 422, response.text
        assert client.put(f"{BASE}/customers/{entry['id']}/responsibilities", json={**SCOPE,
            "user_ids": [ids["warehouse_keeper"], ids["carton_warehouse"]], "owner_user_id": ids["carton_warehouse"],
            "expected_revision": current["revision"], "reason": "不能自行转交负责人"}).status_code == 403
        result = assign(client, current, [ids["warehouse_keeper"], ids["carton_warehouse"]])
        assert login_as(client, "warehouse_keeper")["permissions"] == before
        current = next(row for row in result["customers"] if row["id"] == entry["id"])
        login_as(client, "carton_warehouse")
        assert client.put(f"{BASE}/customers/{entry['id']}/responsibilities", json={**SCOPE,
            "user_ids": [ids["carton_warehouse"]], "expected_revision": current["revision"], "reason": "协作人员不能转授权"}).status_code == 403
        login_as(client, "a_warehouse_keeper")
        assert client.post(f"{BASE}/customers/{entry['id']}/claim", json={**SCOPE, "expected_revision": current["revision"]}).status_code == 403
        login_as(client, "admin")
        transferred = client.put(f"{BASE}/customers/{entry['id']}/responsibilities", json={**SCOPE,
            "user_ids": [ids["carton_warehouse"]], "owner_user_id": ids["carton_warehouse"],
            "expected_revision": current["revision"], "reason": "主管指定新客户负责人"})
        assert transferred.status_code == 200, transferred.text
        assert next(row for row in transferred.json()["customers"] if row["id"] == entry["id"])["owner"]["id"] == ids["carton_warehouse"]


def test_others_orders_and_receipts_are_readable_but_writes_require_authorization(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); entry = customer(client)
        response = client.post(BASE + "/orders", json=_order_payload())
        order = _submit_order(client, response.json())
        payload = {**SCOPE, "delivery_note_no": "CLAIM-RECEIPT-1", "delivery_date": "2026-08-05",
            "lines": [{"order_line_id": order["lines"][0]["id"], "delivered_quantity": "1", "received_quantity": "1"}]}
        receipt = client.post(BASE + "/receipts", json=payload)
        assert receipt.status_code == 201, receipt.text
        ensure_test_user("warehouse_keeper"); ensure_test_user("carton_warehouse")
        login_as(client, "carton_warehouse")
        claimed = client.post(f"{BASE}/customers/{entry['id']}/claim", json={**SCOPE, "expected_revision": 1})
        assert claimed.status_code == 200, claimed.text
        login_as(client, "warehouse_keeper")
        assert client.get(BASE + "/receipts", params=SCOPE).json()["total"] == 0
        assert client.post(BASE + f"/receipts/{receipt.json()['id']}/confirm", json={**SCOPE, "expected_revision": 1}).status_code == 403
        assert client.post(BASE + "/receipts", json={**payload, "delivery_note_no": "UNAUTHORIZED-NOTE"}).status_code == 403
        assert client.get(BASE + f"/orders/{order['order_no']}/purchase-order-context", params=SCOPE).status_code == 200
        assert client.get(BASE + "/orders", params={**SCOPE, "responsibility_scope": "ALL"}).json()["total"] == 1
        assert client.get(BASE + "/receipts", params={**SCOPE, "responsibility_scope": "ALL"}).json()["total"] == 1
        assert client.get(BASE + "/inventory/balances", params=SCOPE).status_code == 200
        login_as(client, "carton_supervisor")
        assert client.get(BASE + "/receipts", params=SCOPE).json()["total"] == 1


def test_simultaneous_claims_choose_exactly_one_owner(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        entry = customer(client)
        ensure_test_user("warehouse_keeper")
        ensure_test_user("carton_warehouse")
        from fastapi import HTTPException
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.models.carton_customer_assignment import CartonCustomerAssignment, CartonCustomerOwner
        from app.schemas.carton_customer_assignment import CartonCustomerClaim
        from app.services.auth import build_auth_context
        from app.services.carton_customer_assignment import claim
        barrier = Barrier(2)

        def attempt(username):
            with SessionLocal() as db:
                user = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == username)))
                # Finish the auth read transaction before competing for the write lock.
                db.rollback()
                barrier.wait(timeout=10)
                try:
                    result = claim(db, user, entry["id"], CartonCustomerClaim(**SCOPE, expected_revision=1))
                    return 200, result["own_customer_codes"]
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code, []

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["warehouse_keeper", "carton_warehouse"]))
        assert sorted(status for status, _ in results) == [200, 409]
        with SessionLocal() as db:
            owners = list(db.scalars(select(CartonCustomerOwner)))
            assignments = list(db.scalars(select(CartonCustomerAssignment)))
            assert len(owners) == len(assignments) == 1
            assert owners[0].user_id == assignments[0].user_id


def test_same_filename_and_identical_bytes_are_independent_and_archive_does_not_restore(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        content = _workbook_bytes("No contract")
        first, second = upload(client, [("箱唛格式参考.xlsx", content), ("箱唛格式参考.xlsx", content)])
        assert first["status"] == second["status"] == "created"
        a, b = first["asset"], second["asset"]
        assert a["file_name"] == b["file_name"] and a["id"] != b["id"] and a["sha256"] == b["sha256"]
        assert client.delete(f"/api/carton-mark/assets/{a['id']}", params={**SCOPE, "revision": 1}).status_code == 204
        assert client.get(f"/api/carton-mark/assets/{a['id']}/document", params=SCOPE).status_code == 404
        assert client.get(f"/api/carton-mark/assets/{b['id']}/document", params=SCOPE).content == content
        third = upload(client, [("箱唛格式参考.xlsx", content)])[0]["asset"]
        assert third["id"] not in {a["id"], b["id"]}


def test_claim_migration_preserves_original_bytes_bindings_and_existing_assignments():
    migration_path = Path(__file__).parents[1] / "alembic/versions/20261008_0146_carton_customer_claims.py"
    spec = importlib.util.spec_from_file_location("claims_migration", migration_path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for sql in [
            "CREATE TABLE auth_users (id VARCHAR(64) PRIMARY KEY)",
            "CREATE TABLE carton_customers (id VARCHAR(96) PRIMARY KEY, factory_id VARCHAR(64), UNIQUE(id,factory_id))",
            "CREATE TABLE carton_customer_assignments (customer_id VARCHAR(96),factory_id VARCHAR(64),user_id VARCHAR(64),PRIMARY KEY(customer_id,user_id))",
            "CREATE TABLE carton_mark_assets (id VARCHAR(96) PRIMARY KEY,factory_id VARCHAR(64),sha256 VARCHAR(64),content BLOB,CONSTRAINT uq_carton_mark_asset_factory_sha UNIQUE(factory_id,sha256),UNIQUE(id,factory_id))",
            "CREATE TABLE carton_mark_asset_order_bindings (asset_id VARCHAR(96),factory_id VARCHAR(64),order_id VARCHAR(96),FOREIGN KEY(asset_id,factory_id) REFERENCES carton_mark_assets(id,factory_id))",
            "INSERT INTO auth_users VALUES ('one'),('two')",
            "INSERT INTO carton_customers VALUES ('single','huaxing'),('multiple','huaxing')",
            "INSERT INTO carton_customer_assignments VALUES ('single','huaxing','one'),('multiple','huaxing','one'),('multiple','huaxing','two')",
            "INSERT INTO carton_mark_assets VALUES ('original','huaxing','hash',X'000102FF')",
            "INSERT INTO carton_mark_asset_order_bindings VALUES ('original','huaxing','order-a')",
        ]: connection.exec_driver_sql(sql)
        before = connection.exec_driver_sql("SELECT * FROM carton_customer_assignments ORDER BY customer_id,user_id").fetchall()
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.exec_driver_sql("SELECT * FROM carton_customer_owners").fetchall() == [("single", "huaxing", "one")]
        assert connection.exec_driver_sql("SELECT * FROM carton_customer_assignments ORDER BY customer_id,user_id").fetchall() == before
        assert connection.exec_driver_sql("SELECT content FROM carton_mark_assets WHERE id='original'").scalar() == bytes([0, 1, 2, 255])
        assert connection.exec_driver_sql("SELECT * FROM carton_mark_asset_order_bindings").fetchall() == [("original", "huaxing", "order-a")]
        connection.exec_driver_sql("INSERT INTO carton_mark_assets VALUES ('copy','huaxing','hash',X'000102FF')")
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
