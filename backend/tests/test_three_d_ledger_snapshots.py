"""PR-04 HTTP regressions against disposable databases (never the business DB)."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_three_d_printing_api import (
    ADMIN_TEST_PASSWORD,
    ensure_three_d_operator,
    login,
    make_client,
)

BASE = "/api/three-d-printing"
FACTORY = "huakang-a"


@pytest.fixture
def client(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        response = client.post(
            BASE + "/materials",
            json={"factory_id": FACTORY, "name": "PR04-PLA", "price_per_kg": 100},
        )
        assert response.status_code == 201, response.text
        yield client


def dashboard(client):
    response = client.get(BASE + "/dashboard", params={"factory_id": FACTORY})
    assert response.status_code == 200, response.text
    return response.json()


def stock(client, amount=1000, material="PR04-PLA", key=None):
    response = client.post(
        BASE + "/inventory/stock-in",
        json={
            "factory_id": FACTORY,
            "business_date": "2026-09-04",
            "material_name": material,
            "amount_g": amount,
            "idempotency_key": key or str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def payload(**kwargs):
    return dict(
        factory_id=FACTORY,
        business_date="2026-09-04",
        machine_no=1,
        status="running",
        product_name="原名",
        material_name="PR04-PLA",
        weight_g=100,
        quantity=2,
        duration_hours=1,
        quoted_price=50,
        idempotency_key=str(uuid4()),
        **kwargs,
    )


def create(client, data=None):
    response = client.post(BASE + "/records", json=data or payload())
    assert response.status_code == 201, response.text
    return response.json()


def edit(client, row, **changes):
    data = {
        **row,
        "reason": "纠正实际生产数据",
        "idempotency_key": str(uuid4()),
        **changes,
    }
    response = client.put(BASE + "/records/" + row["id"], json=data)
    assert response.status_code == 200, response.text
    return response.json()


def balance(client, name="PR04-PLA"):
    return next(
        x["stock_g"]
        for x in dashboard(client)["inventory"]
        if x["material_name"] == name
    )


def delete(client, row, key=None):
    params = {
        "factory_id": FACTORY,
        "revision": row["revision"],
        "reason": "取消订单",
        "idempotency_key": key or str(uuid4()),
    }
    result = client.delete(BASE + "/records/" + row["id"], params=params)
    assert result.status_code == 204, result.text
    return params


def restore(client, row, key=None):
    result = client.post(
        BASE + "/records/" + row["id"] + "/restore",
        json={
            "factory_id": FACTORY,
            "revision": row["revision"],
            "reason": "恢复订单",
            "idempotency_key": key or str(uuid4()),
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def deleted(client):
    response = client.get(BASE + "/records/deleted", params={"factory_id": FACTORY})
    assert response.status_code == 200, response.text
    return response.json()


def test_shortage_is_not_partial_and_retry_is_source_bound(client):
    stock(client, 100, key="stock-repeat")
    stock(client, 100, key="stock-repeat")
    assert balance(client) == 100
    data = payload()
    row = create(client, data)
    assert (
        row["material_status"] == "material_shortage" and not row["inventory_consumed"]
    )
    assert balance(client) == 100
    assert create(client, data)["id"] == row["id"]
    assert (
        client.post(BASE + "/records", json={**data, "weight_g": 101}).status_code
        == 409
    )
    stock(client, 500)
    row = edit(client, row)
    assert row["inventory_consumed"] and balance(client) == 400
    assert (
        len(
            [
                m
                for m in dashboard(client)["inventory_movements"]
                if m["movement_type"] == "production_consume"
            ]
        )
        == 1
    )


def test_edit_reverse_delete_restore_and_zero_quantity(client):
    stock(client)
    row = create(client)
    assert balance(client) == 800
    original = next(
        x
        for x in dashboard(client)["inventory_movements"]
        if x["movement_type"] == "production_consume"
    )
    row = edit(client, row, weight_g=150, quantity=3)
    assert balance(client) == 550
    movement = next(
        x for x in dashboard(client)["inventory_movements"] if x["id"] == original["id"]
    )
    assert movement == original  # old evidence is immutable
    params = delete(client, row, "delete-repeat")
    assert (
        client.delete(BASE + "/records/" + row["id"], params=params).status_code == 204
    )
    assert balance(client) == 1000
    removed = deleted(client)[0]
    row = restore(client, removed, "restore-repeat")
    restore(client, removed, "restore-repeat")
    assert balance(client) == 550
    row = edit(client, row, quantity=0)
    assert balance(client) == 1000 and not row["inventory_consumed"]
    assert row["frozen_totals"]["materialCost"] == 0
    row = edit(client, row, quantity=1)
    assert balance(client) == 850


def test_material_switch_shortage_and_restore_shortage(client):
    stock(client)
    row = create(client)
    row = edit(client, row, material_name="PR04-PETG")
    assert balance(client) == 1000 and row["material_status"] == "material_shortage"
    assert row["frozen_totals"]["materialCost"] is None
    stock(client, 300, "PR04-PETG")
    row = edit(client, row)
    assert balance(client, "PR04-PETG") == 100
    delete(client, row)
    inventory = next(
        x for x in dashboard(client)["inventory"] if x["material_name"] == "PR04-PETG"
    )
    adjusted = client.post(
        BASE + "/inventory/adjust",
        json={
            "factory_id": FACTORY,
            "material_name": "PR04-PETG",
            "target_stock_g": 50,
            "reason": "盘点",
            "revision": inventory["revision"],
            "idempotency_key": "adjust-petg",
        },
    )
    assert adjusted.status_code == 200, adjusted.text
    row = restore(client, deleted(client)[0])
    assert (
        row["material_status"] == "material_shortage"
        and balance(client, "PR04-PETG") == 50
    )


def test_day_off_atomic_reversal_revision_and_recovery(client):
    stock(client)
    create(client)
    create(client)
    data = {
        "factory_id": FACTORY,
        "business_date": "2026-09-04",
        "is_day_off": True,
        "revision": 0,
        "reason": "停工",
        "idempotency_key": "day-off",
    }
    response = client.put(BASE + "/day-status", json=data)
    assert response.status_code == 200, response.text
    assert client.put(BASE + "/day-status", json=data).status_code == 200
    assert balance(client) == 1000 and len(deleted(client)) == 2
    assert client.post(BASE + "/records", json=payload()).status_code == 409
    assert (
        client.put(
            BASE + "/day-status",
            json={**data, "is_day_off": False, "idempotency_key": "stale"},
        ).status_code
        == 409
    )
    response = client.put(
        BASE + "/day-status",
        json={**data, "revision": 1, "is_day_off": False, "idempotency_key": "workday"},
    )
    assert response.status_code == 200, response.text
    for row in deleted(client):
        restore(client, row)
    assert balance(client) == 600


def test_frozen_costs_and_product_rename_do_not_rewrite_history(client):
    stock(client)
    product_data = {
        "factory_id": FACTORY,
        "name": "原名",
        "material_name": "PR04-PLA",
        "weight_g": 100,
        "duration_hours": 1,
        "default_quantity": 2,
        "quoted_price": 50,
    }
    product = client.post(BASE + "/products", json=product_data).json()
    row = create(client, {**payload(), "product_id": product["id"]})
    before = dashboard(client)["summary"]
    response = client.put(
        BASE + "/products/" + product["id"],
        json={**product_data, "name": "新名", "revision": product["revision"]},
    )
    assert response.status_code == 200, response.text
    settings = dashboard(client)["settings"]
    response = client.put(
        BASE + "/settings",
        json={**settings, "labor_per_day": 999, "material_loss_rate": 2},
    )
    assert response.status_code == 200, response.text
    material = next(
        x for x in dashboard(client)["materials"] if x["name"] == "PR04-PLA"
    )
    response = client.put(
        BASE + "/materials/" + material["id"], json={**material, "price_per_kg": 999}
    )
    assert response.status_code == 200, response.text
    unchanged = next(x for x in dashboard(client)["records"] if x["id"] == row["id"])
    assert unchanged == row
    assert dashboard(client)["summary"] == before
    changed = edit(client, row, remark="只改备注")
    assert changed["calculated_cost_snapshot"] == row["calculated_cost_snapshot"]
    changed = edit(client, changed, weight_g=200)
    assert (
        changed["calculated_cost_snapshot"]["material_price_kg"]
        == row["calculated_cost_snapshot"]["material_price_kg"]
    )
    assert (
        changed["frozen_totals"]["materialCost"]
        == row["frozen_totals"]["materialCost"] * 2
    )


def test_concurrent_consumption_and_stale_edits(client):
    stock(client, 300)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post(BASE + "/records", json=payload()), range(2))
        )
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert sum(r.json()["inventory_consumed"] for r in responses) == 1
    assert balance(client) == 100
    row = next(r.json() for r in responses if r.json()["inventory_consumed"])
    edit(client, row, weight_g=110)
    stale = client.put(
        BASE + "/records/" + row["id"],
        json={**row, "reason": "并发编辑", "idempotency_key": "stale"},
    )
    assert stale.status_code == 409 and balance(client) == 80


def test_negative_stock_requires_supervisor_and_explicit_reason(client):
    stock(client, 50)
    row = create(
        client,
        {**payload(), "allow_negative_stock": True, "reason": "主管批准本单先生产"},
    )
    assert balance(client) == -150 and row["inventory_consumed"]
    assert "negative_inventory_approved" in row["data_quality_flags"]
    ensure_three_d_operator("pr04-operator")
    login(client, "pr04-operator")
    assert (
        client.post(
            BASE + "/records",
            json={**payload(), "allow_negative_stock": True, "reason": "越权"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            BASE + "/records/deleted", params={"factory_id": FACTORY}
        ).status_code
        == 403
    )
    assert (
        client.post(
            BASE + "/records", json={**payload(), "factory_id": "huaxing"}
        ).status_code
        == 400
    )
    assert balance(client) == -150


def test_missing_ledger_rolls_back_entire_day_and_legacy_balance_is_not_replayed(
    client,
):
    stock(client)
    good = create(client)
    bad = create(client)
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.three_d_printing")
    with dbm.SessionLocal() as db:
        row = db.get(models.ThreeDPrintingProductionRecord, bad["id"])
        # Simulate pre-upgrade inconsistent data with missing evidence.
        from sqlalchemy import delete as sql_delete

        db.execute(
            sql_delete(models.ThreeDPrintingInventoryMovement).where(
                models.ThreeDPrintingInventoryMovement.source_record_id == row.id
            )
        )
        db.commit()
    response = client.put(
        BASE + "/day-status",
        json={
            "factory_id": FACTORY,
            "business_date": "2026-09-04",
            "is_day_off": True,
            "revision": 0,
            "idempotency_key": "rollback",
            "reason": "全日撤销",
        },
    )
    assert response.status_code == 409
    assert balance(client) == 600 and deleted(client) == []
    with dbm.SessionLocal() as db:
        row = db.get(models.ThreeDPrintingProductionRecord, bad["id"])
        row.source_system = "legacy-sqlite"
        row.inventory_consumed = False
        db.commit()
    delete(client, bad)
    restored = restore(client, deleted(client)[0])
    assert not restored["inventory_consumed"] and balance(client) == 600
    assert (
        client.put(
            BASE + "/records/" + bad["id"],
            json={
                **restored,
                "weight_g": 400,
                "reason": "无凭证纠错",
                "idempotency_key": "legacy-correction",
            },
        ).status_code
        == 409
    )
    assert (
        next(r for r in dashboard(client)["records"] if r["id"] == good["id"])[
            "revision"
        ]
        == good["revision"]
    )


def test_simultaneous_identical_requests_post_only_one_consumption(client):
    stock(client)
    data = payload()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post(BASE + "/records", json=data), range(2))
        )
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert balance(client) == 800
    assert len(dashboard(client)["records"]) == 1


def test_material_rename_keeps_original_balance_and_reversal_bucket(client):
    stock(client)
    row = create(client)
    material = next(
        x for x in dashboard(client)["materials"] if x["name"] == "PR04-PLA"
    )
    response = client.put(
        BASE + "/materials/" + material["id"], json={**material, "name": "PLA-renamed"}
    )
    assert response.status_code == 200, response.text
    assert balance(client) == 800
    delete(client, row)
    assert balance(client) == 1000
    assert not any(
        x["material_name"] == "PLA-renamed" for x in dashboard(client)["inventory"]
    )


def test_legacy_cost_snapshots_and_missing_evidence_never_use_current_rates(client):
    import json

    row = create(client)
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.three_d_printing")
    with dbm.SessionLocal() as db:
        saved = db.get(models.ThreeDPrintingProductionRecord, row["id"])
        snapshot = json.loads(saved.calculated_cost_snapshot_json)
        snapshot["formula_version"] = "legacy-v1"
        snapshot["basis"] = "source_snapshot_rates_not_historical_cost_evidence"
        saved.source_system = "legacy-sqlite"
        saved.cost_profile_version = "legacy-v1"
        saved.data_quality_flags_json = "[]"
        saved.calculated_cost_snapshot_json = json.dumps(snapshot)
        db.commit()
    before = dashboard(client)
    row = before["records"][0]
    settings = before["settings"]
    response = client.put(BASE + "/settings", json={**settings, "labor_per_day": 5000})
    assert response.status_code == 200, response.text
    assert dashboard(client)["summary"] == before["summary"]
    row = edit(client, row, remark="Historical note correction")
    assert (
        row["calculated_cost_snapshot"]
        == before["records"][0]["calculated_cost_snapshot"]
    )
    assert row["cost_profile_version"] == "legacy-v1"
    with dbm.SessionLocal() as db:
        saved = db.get(models.ThreeDPrintingProductionRecord, row["id"])
        saved.calculated_cost_snapshot_json = "{}"
        db.commit()
    result = dashboard(client)
    assert result["summary"]["incompleteCostRecordCount"] == 1
    assert result["records"][0]["frozen_totals"]["materialCost"] is None
    assert result["summary"]["materialCost"] == 0


def test_history_only_correction_requires_explicit_scope_and_preserves_balance(client):
    stock(client)
    row = create(client)
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.three_d_printing")
    with dbm.SessionLocal() as db:
        saved = db.get(models.ThreeDPrintingProductionRecord, row["id"])
        saved.source_system = "legacy-sqlite"
        saved.inventory_consumed = False
        db.commit()
    data = {
        **row,
        "weight_g": 300,
        "reason": "Historical source correction",
        "idempotency_key": "history-only",
    }
    assert client.put(BASE + "/records/" + row["id"], json=data).status_code == 409
    response = client.put(
        BASE + "/records/" + row["id"], json={**data, "history_only_correction": True}
    )
    assert response.status_code == 200, response.text
    assert balance(client) == 800
    assert (
        response.json()["frozen_totals"]["materialCost"]
        == row["frozen_totals"]["materialCost"] * 3
    )
    no_key = payload()
    no_key.pop("idempotency_key")
    assert client.post(BASE + "/records", json=no_key).status_code == 422
    ensure_three_d_operator("history-operator")
    login(client, "history-operator")
    assert (
        client.put(
            BASE + "/records/" + row["id"],
            json={
                **response.json(),
                "reason": "operator correction",
                "history_only_correction": True,
                "idempotency_key": "operator-history",
            },
        ).status_code
        == 403
    )
