"""Business regressions for weights, responsibilities, historical dates and shared originals."""
from decimal import Decimal
import importlib.util

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from test_molding_sample_api import login_as, make_client, ensure_test_user
from test_carton_procurement_api import _order_payload
from test_carton_history_preview_api import upload as history_upload
from test_carton_history_wide import workbook, row
from test_carton_mark_assets import upload, seed_order
from test_carton_mark_api import _workbook_bytes
from test_alembic_migrations import BACKEND_DIR

BASE = "/api/carton-procurement"
SCOPE = {"factory_id": "huaxing"}


def customer(client, code="DICKIE", name="Dickie"):
    response = client.post(BASE + "/customers", json={**SCOPE, "customer_code": code, "customer_name": name})
    assert response.status_code == 201, response.text
    return response.json()


def assign(client, entry, users):
    response = client.put(f"{BASE}/customers/{entry['id']}/responsibilities", json={**SCOPE,
        "user_ids": users, "expected_revision": entry["revision"], "reason": "客户订单责任交接"})
    assert response.status_code == 200, response.text
    return response.json()


def test_weights_master_copy_snapshot_and_partial_update_validation(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); customer(client)
        payload = _order_payload()
        papers = [{k: v for k, v in line.items() if k != "unit_price"} for line in payload["lines"]]
        papers[0].update(net_weight_kg="8.125", gross_weight_kg="9.25")
        papers[1].update(net_weight_kg="0.4", gross_weight_kg="0.5")
        master = client.post(BASE + "/master-data", json={**SCOPE, "kind": "CONFIG", "code": payload["item_no"],
            "data": {"product_name": "多文盒", "net_weight_kg": "77", "gross_weight_kg": "88", "lines": list(reversed(papers))},
            "reason": "维护纸品重量资料"})
        assert master.status_code == 201, master.text
        config = master.json()
        payload.update(master_config_id=config["id"], master_config_revision=config["revision"])
        response = client.post(BASE + "/orders", json=payload)
        assert response.status_code == 201, response.text
        order = response.json()
        assert order["net_weight_kg"] is None and order["gross_weight_kg"] is None
        assert [Decimal(line["net_weight_kg"]) for line in order["lines"]] == [Decimal("8.125"), Decimal("0.4")]
        assert [Decimal(line["gross_weight_kg"]) for line in order["lines"]] == [Decimal("9.25"), Decimal("0.5")]
        changed_papers = [{**line, "net_weight_kg": "10", "gross_weight_kg": "11"} for line in config["data"]["lines"]]
        changed = client.patch(BASE + f"/master-data/{config['id']}", json={**SCOPE, "kind": "CONFIG", "code": payload["item_no"],
            "expected_revision": config["revision"], "data": {**config["data"], "lines": changed_papers}, "reason": "修正新版纸品重量"})
        assert changed.status_code == 200, changed.text
        conflicting = {**payload, "contract_no": "WEIGHT-CONFLICT", "master_config_revision": changed.json()["revision"],
                       "lines": [{**payload["lines"][0], "net_weight_kg": "20"}, payload["lines"][1]]}
        assert client.post(BASE + "/orders", json=conflicting).status_code == 422
        cleared = {**conflicting, "contract_no": "WEIGHT-CLEARED", "lines": [
            {**payload["lines"][0], "net_weight_kg": None, "gross_weight_kg": None}, payload["lines"][1]]}
        response = client.post(BASE + "/orders", json=cleared)
        assert response.status_code == 201, response.text
        assert response.json()["lines"][0]["net_weight_kg"] is None
        assert Decimal(response.json()["lines"][1]["net_weight_kg"]) == Decimal("10")
        edit = {**payload, "expected_revision": order["revision"], "reason": "补充普通订单备注", "note": "只改备注", "master_config_id": "", "master_config_revision": 0}
        edit.pop("status")
        updated = client.patch(BASE + f"/orders/{order['order_no']}", json=edit)
        assert updated.status_code == 200, updated.text
        assert updated.json()["lines"] == order["lines"]
        edit.update(expected_revision=updated.json()["revision"], lines=[{**payload["lines"][0], "net_weight_kg": "20"}, payload["lines"][1]])
        assert client.patch(BASE + f"/orders/{order['order_no']}", json=edit).status_code == 422
        for bad in ({"net_weight_kg": "-1"}, {"net_weight_kg": "9", "gross_weight_kg": "8"}, {"gross_weight_kg": "NaN"}, {"net_weight_kg": "0.00001"}):
            invalid = {**_order_payload(), "lines": [{**payload["lines"][0], **bad}, payload["lines"][1]]}
            assert client.post(BASE + "/orders", json=invalid).status_code == 422
        issued = client.post(BASE + f"/orders/{order['order_no']}/submit-supplier", json={**SCOPE, "expected_revision": updated.json()["revision"]})
        assert issued.status_code == 200, issued.text
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        from sqlalchemy import select
        import json
        with SessionLocal() as db:
            snapshot = json.loads(db.scalar(select(CartonPurchaseOrderIssue.snapshot_json).where(CartonPurchaseOrderIssue.order_id == order["id"])))
        assert [Decimal(line["net_weight_kg"]) for line in snapshot["lines"]] == [Decimal("8.125"), Decimal("0.4")]
        edit["expected_revision"] = issued.json()["revision"]
        assert client.patch(BASE + f"/orders/{order['order_no']}", json=edit).status_code == 409



def test_responsibility_default_deny_binding_revocation_and_atomic_batch(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        first = customer(client); second = customer(client, "OTHER", "另一个客户")
        ensure_test_user("carton_warehouse")
        ensure_test_user("warehouse_keeper")
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from sqlalchemy import select
        with SessionLocal() as db:
            operator = db.scalar(select(AuthUser).where(AuthUser.username == "warehouse_keeper"))
            operator_id = operator.id
        own = client.post(BASE + "/orders", json=_order_payload()).json()
        other = client.post(BASE + "/orders", json={**_order_payload(), "customer_code": "OTHER", "customer_name": "另一个客户", "contract_no": "OTHER-001"}).json()
        login_as(client, "warehouse_keeper")
        assert client.post(BASE + "/orders", json=_order_payload()).status_code == 403
        assert client.get(BASE + "/customer-responsibilities", params=SCOPE).json()["own_customer_codes"] == []
        # Maintaining a new customer never self-grants order responsibility.
        customer(client, "NEW", "新建待分配客户")
        assert client.post(BASE + "/orders", json={**_order_payload(), "customer_code": "NEW"}).status_code == 403
        assert client.put(BASE + f"/customers/{first['id']}/responsibilities", json={**SCOPE, "user_ids": [operator_id], "expected_revision": 1, "reason": "自行扩大客户范围"}).status_code == 403
        login_as(client, "admin"); scope = assign(client, first, [operator_id])
        summary = client.get(BASE + "/customer-responsibilities", params={**SCOPE, "summary": True}).json()
        assert summary["unrestricted"] is True and summary["users"] == [] and summary["customers"] == []
        current = next(item for item in scope["customers"] if item["id"] == first["id"])
        rename = client.patch(BASE + f"/customers/{first['id']}", json={**SCOPE,
            "expected_revision": current["revision"], "customer_code": "RENAMED"})
        assert rename.status_code == 409, rename.text
        login_as(client, "warehouse_keeper")
        assert client.get(BASE + "/customer-responsibilities", params=SCOPE).json()["own_customer_codes"] == ["DICKIE"]
        assert client.post(BASE + "/orders/bulk-submit-supplier", json={**SCOPE, "items": [
            {"order_no": entry["order_no"], "expected_revision": entry["revision"]} for entry in [own, other]]}).status_code == 403
        assert {entry["status"] for entry in client.get(BASE + "/orders", params=SCOPE).json()["items"]} == {"CONFIRMED"}
        assert client.post(BASE + f"/orders/{other['order_no']}/append", json={**SCOPE, "expected_revision": 1, "additional_quantity": 1}).status_code == 403
        assert client.post(BASE + f"/orders/{own['order_no']}/submit-supplier", json={**SCOPE, "expected_revision": 1}).status_code == 200
        login_as(client, "admin")
        assign(client, {**first, "revision": current["revision"]}, [])
        stale = client.put(BASE + f"/customers/{first['id']}/responsibilities", json={**SCOPE, "user_ids": [operator_id], "expected_revision": current["revision"], "reason": "使用过期责任版本"})
        assert stale.status_code == 409
        login_as(client, "warehouse_keeper")
        assert client.post(BASE + f"/orders/{own['order_no']}/append", json={**SCOPE, "expected_revision": 2, "additional_quantity": 1}).status_code == 403
        # Warehouse reads/stock work retain their independent role authorization.
        assert client.get(BASE + "/inventory/movements", params=SCOPE).status_code == 200
        login_as(client, "carton_supervisor")
        assert client.post(BASE + f"/orders/{own['order_no']}/append", json={**SCOPE, "expected_revision": 2, "additional_quantity": 1}).status_code == 200


def test_history_customer_due_fallback_preserves_plan_and_explicit_customer_due(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); customer(client, "DICKIE", "迪奇")
        rules = client.post(BASE + "/master-data", json={**SCOPE, "kind": "RULE", "customer_code": "DICKIE",
            "data": {"lead_days": 5}, "reason": "维护客户采购保护期"})
        assert rules.status_code == 201, rules.text
        content = workbook([row(历史订单号="H-1"), row(历史订单号="H-2", 合同号="4500219760-20", 客户交期="2026-09-20")])
        preview = history_upload(client, content).json()
        assert preview["errors"] == []
        assert [order["customer_due_date"] for order in preview["orders"]] == ["2026-09-15", "2026-09-20"]
        assert all(order["due_date"] == "2026-09-10" for order in preview["orders"])
        assert "保护期 5" in " ".join(preview["orders"][0]["warnings"])
        result = history_upload(client, content, preview=False, fingerprint=preview["source_fingerprint"])
        assert result.status_code == 201, result.text
        orders = client.get(BASE + "/orders", params=SCOPE).json()["items"]
        assert {order["customer_due_date"] for order in orders} == {"2026-09-15", "2026-09-20"}
        assert {order["due_date"] for order in orders} == {"2026-09-10"}


def test_source_multiple_contracts_atomic_revision_and_deleted_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models import carton_procurement as model
        with SessionLocal() as db:
            seed_order(db, model, "ONE", contract="CONTRACT-001")
            seed_order(db, model, "TWO", contract="CONTRACT-002")
            seed_order(db, model, "OTHER", contract="OTHER-003", customer="OTHER")
            seed_order(db, model, "FOREIGN", contract="FOREIGN-004", factory="huakang-a")
        asset = upload(client, [("unnamed.xlsx", _workbook_bytes())])[0]["asset"]
        url = f"/api/carton-mark/assets/{asset['id']}/binding"
        response = client.put(url, params=SCOPE, json={"order_ids": ["ONE", "TWO"], "revision": 1})
        assert response.status_code == 200, response.text
        assert {order["id"] for order in response.json()["orders"]} == {"ONE", "TWO"}
        for order_id in ["ONE", "TWO"]:
            assert len(client.get("/api/carton-mark/assets", params={**SCOPE, "order_id": order_id}).json()) == 1
        assert client.put(url, params=SCOPE, json={"order_ids": ["ONE"], "revision": 1}).status_code == 409
        assert client.put(url, params=SCOPE, json={"order_ids": ["ONE", "OTHER"], "revision": 2}).status_code == 422
        assert client.put(url, params=SCOPE, json={"order_ids": ["ONE", "FOREIGN"], "revision": 2}).status_code == 404
        repeated = client.put(url, params=SCOPE, json={"order_ids": ["ONE", "TWO"], "revision": 2})
        assert repeated.status_code == 200, repeated.text
        assert set(repeated.json()["bound_order_ids"]) == {"ONE", "TWO"}
        narrowed = client.put(url, params=SCOPE, json={"order_ids": ["TWO"], "revision": 3})
        assert narrowed.status_code == 200, narrowed.text
        assert narrowed.json()["bound_order_ids"] == ["TWO"]
        with SessionLocal() as db:
            db.execute(text("DELETE FROM carton_orders WHERE id IN ('ONE', 'TWO')")); db.commit()
            seed_order(db, model, "REPLACEMENT", contract="CONTRACT-001")
        saved = client.get("/api/carton-mark/assets", params=SCOPE).json()[0]
        assert saved["orders"] == [] and saved["bound_order_ids"] == []
        assert saved["recognition_source"] == "manual_orders"


def test_additive_migration_preserves_rows_and_enforces_factory_foreign_keys():
    spec = importlib.util.spec_from_file_location("carton_packaging_migration", BACKEND_DIR / "alembic/versions/20261008_0144_carton_customer_packaging.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for name in ["carton_customers", "carton_orders", "carton_mark_assets"]:
            connection.exec_driver_sql(f"CREATE TABLE {name} (id TEXT PRIMARY KEY, factory_id TEXT NOT NULL, UNIQUE(id,factory_id))")
            connection.exec_driver_sql(f"INSERT INTO {name} VALUES ('original','huaxing'),('foreign','huakang-a')")
        connection.exec_driver_sql("CREATE TABLE auth_users (id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO auth_users VALUES ('operator')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT id,net_weight_kg,gross_weight_kg FROM carton_orders ORDER BY id").fetchall() == [("foreign", None, None), ("original", None, None)]
            for sql in ["UPDATE carton_orders SET net_weight_kg=-1", "UPDATE carton_orders SET net_weight_kg=10,gross_weight_kg=9", "INSERT INTO carton_customer_assignments VALUES ('foreign','operator','huaxing')", "INSERT INTO carton_mark_asset_order_bindings VALUES ('original','foreign','huaxing')"]:
                with pytest.raises(Exception): connection.exec_driver_sql(sql)
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
            with pytest.raises(RuntimeError, match="禁止降级"): migration.downgrade()


def test_paper_weight_migration_preserves_legacy_values_and_checks_each_line():
    spec = importlib.util.spec_from_file_location("carton_paper_weights", BACKEND_DIR / "alembic/versions/20261008_0145_carton_paper_weights.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE carton_order_lines (id TEXT PRIMARY KEY, required_quantity NUMERIC NOT NULL)")
        connection.exec_driver_sql("INSERT INTO carton_order_lines VALUES ('original', 123.5)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT * FROM carton_order_lines").fetchall() == [("original", 123.5, None, None)]
            for sql in ["UPDATE carton_order_lines SET net_weight_kg=-1", "UPDATE carton_order_lines SET net_weight_kg=10,gross_weight_kg=9"]:
                with pytest.raises(Exception): connection.exec_driver_sql(sql)
            connection.exec_driver_sql("UPDATE carton_order_lines SET net_weight_kg=0,gross_weight_kg=0")
            with pytest.raises(RuntimeError, match="禁止降级"): migration.downgrade()


def test_omitted_weights_preserve_duplicate_paper_slots_on_order_edits():
    from app.schemas.carton_procurement import CartonOrderLineCreate
    from app.services.carton_procurement import _merge_paper_weights
    line = _order_payload()["lines"][0]
    sources = [CartonOrderLineCreate(**{**line, "net_weight_kg": "1", "gross_weight_kg": "2"}),
               CartonOrderLineCreate(**{**line, "net_weight_kg": "3", "gross_weight_kg": "4"})]
    merged = _merge_paper_weights([CartonOrderLineCreate(**line), CartonOrderLineCreate(**line)], sources, preserve_positions=True)
    assert [(entry.net_weight_kg, entry.gross_weight_kg) for entry in merged] == [(Decimal(1), Decimal(2)), (Decimal(3), Decimal(4))]


def test_paper_configuration_identity_ignores_legacy_header_weights():
    from app.services.carton_master import configuration
    paper = {**_order_payload()["lines"][0], "net_weight_kg": "1.2000", "gross_weight_kg": "2.0000"}
    current = {"product_name": "多文盒", "lines": [paper]}
    assert configuration({**current, "net_weight_kg": "77", "gross_weight_kg": "88"}) == configuration(current)
    assert configuration(current) != configuration({**current, "lines": [{**paper, "net_weight_kg": "1.3"}]})
    assert configuration({"lines": [{}]}) == configuration({"lines": [{"net_weight_kg": None, "gross_weight_kg": None}]})


def test_formal_paper_order_reuses_legacy_master_identity(monkeypatch):
    import json
    from sqlalchemy import select
    from app.services.carton_master import configuration, digest, encoded, sync_history
    with make_client(monkeypatch) as client:
        login_as(client, "admin"); customer(client)
        payload = _order_payload()
        papers = [{**{k: v for k, v in line.items() if k != "unit_price"},
                   "net_weight_kg": "1", "gross_weight_kg": "2"} for line in payload["lines"]]
        data = {"product_name": payload["product_name"], "lines": papers, "net_weight_kg": "77", "gross_weight_kg": "88"}
        response = client.post(BASE + "/master-data", json={**SCOPE, "kind": "CONFIG", "code": payload["item_no"],
            "data": data, "reason": "兼容历史整单重量资料"})
        assert response.status_code == 201, response.text
        master = response.json()
        # An already-saved legacy fingerprint must remain unchanged.
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord, CartonMasterSource
        old_identity = digest([payload["item_no"], {**configuration(data), "net_weight_kg": "77", "gross_weight_kg": "88"}])
        with SessionLocal() as db:
            db.get(CartonMasterRecord, master["id"]).identity = old_identity
            db.commit()
        response = client.post(BASE + "/orders", json={**payload,
            "master_config_id": master["id"], "master_config_revision": master["revision"]})
        assert response.status_code == 201, response.text
        order = response.json()
        response = client.post(BASE + f"/orders/{order['order_no']}/submit-supplier",
            json={**SCOPE, "expected_revision": order["revision"]})
        assert response.status_code == 200, response.text
        with SessionLocal() as db:
            rows = list(db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.factory_id == "huaxing",
                CartonMasterRecord.kind == "CONFIG", CartonMasterRecord.code == payload["item_no"])))
            assert len(rows) == 1 and rows[0].id == master["id"]
            assert rows[0].identity == old_identity
            assert json.loads(rows[0].data_json)["net_weight_kg"] == "77"
            source = db.scalar(select(CartonMasterSource).where(CartonMasterSource.record_id == master["id"]))
            evidence = json.loads(source.snapshot_json)
            evidence["configuration"].update(net_weight_kg="77", gross_weight_kg="88")
            original_snapshot = source.snapshot_json = encoded(evidence)
            source.signature = digest(evidence["configuration"])
            # Even after a maintained correction, the old source remains an
            # alias without rewriting it or enrolling duplicate evidence.
            corrected = json.loads(rows[0].data_json)
            corrected["lines"][0]["net_weight_kg"] = "1.5"
            rows[0].data_json = encoded(corrected)
            db.commit()
            sync_history(db, "huaxing")
            db.commit()
            rows = list(db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.factory_id == "huaxing",
                CartonMasterRecord.kind == "CONFIG", CartonMasterRecord.code == payload["item_no"])))
            sources = list(db.scalars(select(CartonMasterSource).where(CartonMasterSource.record_id == master["id"])))
            assert len(rows) == 1 and rows[0].identity == old_identity
            assert len(sources) == 1 and sources[0].snapshot_json == original_snapshot


def test_schema_guard_requires_the_paper_weight_migration(monkeypatch):
    from app import db
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
    monkeypatch.setattr(db, "engine", engine)
    with pytest.raises(RuntimeError) as error:
        db.ensure_carton_master_schema_ready()
    assert "20261008_0145" in str(error.value)
    assert "carton_order_lines.net_weight_kg" in str(error.value)
