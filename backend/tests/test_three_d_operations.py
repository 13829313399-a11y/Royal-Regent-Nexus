import importlib
import json
from uuid import uuid4

from sqlalchemy import select
from test_three_d_connector import environment as environment_fixture
from test_three_d_connector import event, post, session
from test_three_d_run_reconciliation import seed_product

environment = environment_fixture
BASE = "/api/three-d-printing/operations"


def save(env, kind, data, **changes):
    payload = {
        "resource_key": uuid4().hex,
        "revision": 0,
        "idempotency_key": uuid4().hex,
        "reason": "isolated verification",
        "data": data,
    }
    payload.update(changes)
    response = env[0].post(f"{BASE}/resources/{kind}", json=payload)
    return response, payload


def action(env, item, name, expected=200, **changes):
    payload = dict(
        action=name,
        revision=item["revision"],
        idempotency_key=uuid4().hex,
        reason="verified request",
        **changes,
    )
    response = env[0].post(f"{BASE}/resources/{item['id']}/actions", json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_spool_revision_idempotency_slot_and_no_stock_repost(environment):
    env = environment
    seed_product(env)
    data = {
        "material": "PLA",
        "lot": "lot-01",
        "initial_g": 1000,
        "remaining_g": 800,
        "machine_no": 1,
        "slot": 0,
    }
    response, payload = save(env, "spool", data)
    assert response.status_code == 200, response.text
    item = response.json()
    assert (
        env[0].post(f"{BASE}/resources/spool", json=payload).json()["id"] == item["id"]
    )
    assert save(env, "spool", data)[0].status_code == 409
    assert (
        save(env, "spool", data, resource_key=item["resource_key"], revision=8)[
            0
        ].status_code
        == 409
    )
    assert save(env, "spool", {**data, "remaining_g": 1001})[0].status_code == 422
    updated, _ = save(
        env,
        "spool",
        {**data, "remaining_g": 500},
        resource_key=item["resource_key"],
        revision=1,
    )
    assert updated.json()["revision"] == 2
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingInventory, "stock").stock_g == 100
        assert not list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))


def test_request_approval_schedule_completion_evidence(environment):
    env = environment
    seed_product(env)
    response, _ = save(
        env,
        "request",
        {
            "department": "three-d-printing",
            "cost_center": "R&D",
            "product_id": "product-0",
            "quantity": 2,
            "due_date": "2026-09-30",
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()
    action(env, item, "schedule", 409)
    item = action(env, item, "approve")
    item = action(env, item, "schedule")
    assert item["data"]["schedule_id"]
    action(env, item, "complete", 409, target_id="no-proof")
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    post(env, "/events", event(env, ref, 2, "FINISH"))
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        record_id = record.id
    item = action(env, item, "complete", target_id=record_id, feedback="尺寸核验通过")
    assert item["status"] == "completed"
    with env[1].SessionLocal() as db:
        assert (
            db.get(env[2].ThreeDPrintingSchedule, item["data"]["schedule_id"]).status
            == "done"
        )
    thread = env[0].get(f"{BASE}/thread/{record_id}")
    assert thread.status_code == 200, thread.text
    assert thread.json()["requests"][0]["data"]["feedback"] == "尺寸核验通过"


def test_file_version_is_frozen_on_run_and_download_scoped(environment):
    env = environment
    seed_product(env)
    file = env[0].post(
        f"{BASE}/files",
        files={
            "file": (
                "part.gcode",
                b"; harmless test fixture",
                "application/octet-stream",
            )
        },
    )
    assert file.status_code == 200, file.text
    file_id = file.json()["id"]
    assert env[0].get(f"{BASE}/files/{file_id}").content == b"; harmless test fixture"
    response, _ = save(
        env,
        "file_alias",
        {
            "product_id": "product-0",
            "file_name": "design-v1.gcode",
            "version": "v1",
            "file_id": file_id,
        },
    )
    assert response.status_code == 200, response.text
    alias = response.json()
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="design-v1.gcode"))
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        record_id = record.id
        assert record.product_id == "product-0"
    save(
        env,
        "file_alias",
        {
            "product_id": "product-0",
            "file_name": "design-v1.gcode",
            "version": "v2",
            "file_id": file_id,
        },
        resource_key=alias["resource_key"],
        revision=1,
    )
    assert (
        env[0].get(f"{BASE}/thread/{record_id}").json()["file_versions"][0]["version"]
        == "v1"
    )
    assert env[0].get(f"{BASE}/files/{file_id}?factory_id=huaxing").status_code == 400
    assert (
        env[0]
        .post(f"{BASE}/files", files={"file": ("unsafe.html", b"html")})
        .status_code
        == 422
    )
    env[0].post("/api/auth/logout")
    assert env[0].get(f"{BASE}/files/{file_id}").status_code == 401


def test_unmatched_run_manual_resolution_consumes_once(environment):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="unknown.gcode"))
    with env[1].SessionLocal() as db:
        row = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        rid = row.id
        rev = row.revision
    payload = {
        "action": "match",
        "target_id": "product-0",
        "revision": rev,
        "idempotency_key": uuid4().hex,
        "reason": "人工核对文件",
    }
    response = env[0].post(f"{BASE}/runs/{rid}/match", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["inventory_consumed"]
    assert env[0].post(f"{BASE}/runs/{rid}/match", json=payload).status_code == 200
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingInventory, "stock").stock_g == 80
        assert (
            len(list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))) == 1
        )


def test_paginated_workspace_totals_filters_and_timeline_redaction(environment):
    env = environment
    seed_product(env)
    with env[1].SessionLocal() as db:
        for n in range(137):
            db.add(
                env[2].ThreeDPrintingProduct(
                    id=f"p-{n:04}",
                    factory_id="huakang-a",
                    name=f"large-{n:04}",
                    material_name="PLA",
                    created_at="2026-09-04",
                    updated_at="2026-09-04",
                )
            )
        db.commit()
    url = "/api/three-d-printing/collections/products?factory_id=huakang-a"
    first = (
        env[0]
        .get(url, params={"factory_id": "huakang-a", "q": "large-", "page_size": 50})
        .json()
    )
    second = (
        env[0]
        .get(
            url,
            params={
                "factory_id": "huakang-a",
                "q": "large-",
                "page": 2,
                "page_size": 50,
            },
        )
        .json()
    )
    assert first["total"] == 137 and len(first["items"]) == 50
    assert not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})
    assert (
        env[0]
        .get(url, params={"factory_id": "huakang-a", "quality": "missing_image"})
        .status_code
        == 200
    )
    compact = (
        env[0]
        .get(
            "/api/three-d-printing/dashboard",
            params={"compact": True, "factory_id": "huakang-a"},
        )
        .json()
    )
    assert len(compact["products"]) == 50 and compact["summary"]["productCount"] == 138
    ref = session(env)
    post(env, "/events", event(env, ref))
    timeline = env[0].get(
        f"/api/three-d-printing/printers/{env[5][0]}/timeline?factory_id=huakang-a"
    )
    assert timeline.status_code == 200, timeline.text
    assert (
        "credential_ref" not in timeline.text
        and "lan_host" not in timeline.text
        and "leader_lease" not in timeline.text
    )


def test_advice_is_network_gated_and_analytics_is_non_mutating(environment):
    env = environment
    response = env[0].get(f"{BASE}/analytics")
    assert response.status_code == 200, response.text
    assert len(response.json()["machines"]) == 11
    assert all(row["oee"] is None for row in response.json()["machines"])
    assert all(row["availability"] is None for row in response.json()["machines"])
    network = importlib.import_module("app.services.three_d_network_health")
    with env[1].SessionLocal() as db:
        gateway = db.scalar(
            select(env[2].ThreeDPrintingAuditEvent).where(
                env[2].ThreeDPrintingAuditEvent.entity_type == "network_health"
            )
        )
        payload = json.loads(gateway.detail_json)
        payload["tunnel"] = "failed"
        from datetime import UTC, datetime

        payload["observed_at"] = datetime.now(UTC).isoformat()
        # Audit events are immutable; submit a failed probe through the domain API.
        network.store_network_health(
            db, network.NetworkHealthReport.model_validate(payload)
        )
    response = env[0].get(f"{BASE}/recommendations")
    assert response.status_code == 200
    assert response.json()["mode"] == "recommend_only"
    assert response.json()["blocked_reason"]


def test_quality_spool_snapshot_and_operator_cannot_approve(environment):
    from test_three_d_printing_api import ensure_three_d_operator, login

    env = environment
    seed_product(env)
    spool, _ = save(
        env,
        "spool",
        {
            "material": "PLA",
            "lot": "original-lot",
            "initial_g": 1000,
            "remaining_g": 500,
        },
    )
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    with env[1].SessionLocal() as db:
        rid = db.scalar(select(env[2].ThreeDPrintingProductionRecord)).id
    proof, _ = save(
        env,
        "run_evidence",
        {
            "record_id": rid,
            "spool_ids": [spool.json()["id"]],
            "quality": "passed",
            "note": "核对通过",
        },
    )
    assert proof.status_code == 200, proof.text
    updated = spool.json()
    save(
        env,
        "spool",
        {
            "material": "PLA",
            "lot": "changed-lot",
            "initial_g": 1000,
            "remaining_g": 400,
        },
        resource_key=updated["resource_key"],
        revision=updated["revision"],
    )
    thread = env[0].get(f"{BASE}/thread/{rid}").json()
    assert (
        thread["run_evidence"][0]["data"]["spool_snapshots"][0]["data"]["lot"]
        == "original-lot"
    )
    request, _ = save(
        env,
        "request",
        {
            "department": "three-d-printing",
            "cost_center": "C1",
            "product_id": "product-0",
            "quantity": 1,
            "due_date": "2026-09-30",
        },
    )
    ensure_three_d_operator("request-operator")
    login(env[0], "request-operator")
    action(env, request.json(), "approve", 403)
    assert (
        save(
            env,
            "request",
            {
                "department": "engineering",
                "cost_center": "C1",
                "product_id": "product-0",
                "quantity": 1,
                "due_date": "2026-09-30",
            },
        )[0].status_code
        == 403
    )


def test_advice_reserves_spool_quantity_without_mutating_jobs(environment):
    env = environment
    seed_product(env)
    with env[1].SessionLocal() as db:
        db.get(env[2].ThreeDPrintingProduct, "product-0").duration_hours = 1
        for name in ("job-a", "job-b"):
            db.add(
                env[2].ThreeDPrintingSchedule(
                    id=name,
                    factory_id="huakang-a",
                    business_date="2026-09-30",
                    product_id="product-0",
                    product_name="part",
                    material_name="PLA",
                    weight_g=10,
                    quantity=3,
                    machine_no=0,
                    created_at="2026-09-04",
                    updated_at="2026-09-04",
                )
            )
        db.commit()
    assert (
        save(env, "profile", {"machine_no": 1, "materials": ["PLA"]})[0].status_code
        == 200
    )
    assert (
        save(
            env,
            "spool",
            {
                "material": "PLA",
                "lot": "available",
                "initial_g": 1000,
                "remaining_g": 50,
                "machine_no": 1,
                "slot": 0,
            },
        )[0].status_code
        == 200
    )
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    response = env[0].get(f"{BASE}/recommendations")
    assert response.status_code == 200, response.text
    advice = response.json()["items"]
    assert advice[0]["schedule_id"] == "job-a" and advice[0]["machine_no"] == 1
    assert advice[1]["machine_no"] is None
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingSchedule, "job-a").machine_no == 0
        spool = db.scalar(
            select(env[2].ThreeDPrintingOperationsItem).where(
                env[2].ThreeDPrintingOperationsItem.kind == "spool"
            )
        )
        assert json.loads(spool.data_json)["remaining_g"] == 50
    post(
        env,
        "/events",
        event(
            env,
            ref,
            2,
            current_file="part.3mf",
            nozzle_temperature=350,
            error_code="test-error",
        ),
    )
    counters = env[0].get(f"{BASE}/analytics").json()["machines"][0]
    assert counters["temperature_alarm_events"] == 1 and counters["maintenance_due"]
