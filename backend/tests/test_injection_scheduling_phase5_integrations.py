from decimal import Decimal

from test_injection_scheduling_phase3_api import (
    ADMIN_TEST_PASSWORD,
    login,
    machine_payload,
    make_client,
    mold_payload,
    order_payload,
    task_payload,
)


def _erp_item(external_version: str, quantity: float = 100) -> dict:
    return {
        "external_id": "ERP-HX-ORDER-001",
        "external_version": external_version,
        "order_no": "ERP-HX-ORDER-001",
        "item_no": "ITEM-ERP-001",
        "product_name": "ERP 增量订单",
        "order_quantity": quantity,
        "source_completed_quantity": 0,
        "delivery_start_date": "2026-08-04",
        "delivery_due_date": "2026-08-10",
        "priority_code": "URGENT",
        "material_readiness_status": "ready",
        "warehouse_text": "ERP-A",
        "remark": "ERP Phase 5",
        "occurred_at": "2026-08-04T08:00:00+08:00",
        "lineage": {"erp_document": "SO-001"},
    }


def test_phase5_erp_incremental_sync_is_idempotent_versioned_and_factory_scoped(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        payload = {
            "factory_id": "huaxing",
            "source_key": "erp-primary",
            "cursor": "cursor-001",
            "orders": [_erp_item("v1")],
        }
        created = client.post(
            "/api/injection-scheduling/integrations/erp/order-batches",
            headers={"X-Request-ID": "phase5-erp-batch-001"},
            json=payload,
        )
        assert created.status_code == 200, created.text
        assert created.json()["created_count"] == 1
        assert created.json()["updated_count"] == 0
        assert created.json()["integration"]["cursor"] == "cursor-001"

        replay = client.post(
            "/api/injection-scheduling/integrations/erp/order-batches",
            headers={"X-Request-ID": "phase5-erp-batch-001-replay"},
            json=payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["skipped_count"] == 1

        conflicting_event = client.post(
            "/api/injection-scheduling/integrations/erp/order-batches",
            json={**payload, "orders": [_erp_item("v1", 101)]},
        )
        assert conflicting_event.status_code == 409

        updated = client.post(
            "/api/injection-scheduling/integrations/erp/order-batches",
            headers={"X-Request-ID": "phase5-erp-batch-002"},
            json={
                **payload,
                "cursor": "cursor-002",
                "orders": [_erp_item("v2", 120)],
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["updated_count"] == 1
        order_id = updated.json()["order_ids"][0]

        huaxing_backlog = client.get(
            "/api/injection-scheduling/backlog", params={"factory_id": "huaxing"}
        ).json()["items"]
        assert (
            next(item for item in huaxing_backlog if item["id"] == order_id)[
                "order_quantity"
            ]
            == 120
        )
        other_factory = client.get(
            "/api/injection-scheduling/backlog", params={"factory_id": "huakang-a"}
        ).json()["items"]
        assert all(item["id"] != order_id for item in other_factory)


def _published_device_fixture(client):
    factory_id = "huaxing"
    machine = client.post(
        "/api/injection-scheduling/machines",
        json=machine_payload(factory_id, "P5-DEVICE-MACHINE"),
    ).json()
    mold = client.post(
        "/api/injection-scheduling/molds",
        json=mold_payload(factory_id, "P5-DEVICE-MOLD"),
    ).json()
    order_data = order_payload(factory_id, "P5-DEVICE-ORDER", 60)
    order_data["mold_id"] = mold["id"]
    order = client.post("/api/injection-scheduling/orders", json=order_data).json()
    draft = client.post(
        "/api/injection-scheduling/plans/drafts",
        json={
            "factory_id": factory_id,
            "expected_revision": 0,
            "business_date": "2026-08-04",
        },
    ).json()
    planned_response = client.post(
        f"/api/injection-scheduling/plans/{draft['id']}/tasks",
        json={
            **task_payload(
                factory_id, draft["revision"], machine["id"], order["id"], 1
            ),
            "planned_start": "2026-08-04T08:00:00",
            "planned_finish": "2026-08-04T10:00:00",
        },
    )
    assert planned_response.status_code == 201, planned_response.text
    planned = planned_response.json()
    task = planned["tasks"][0]
    published = client.post(
        f"/api/injection-scheduling/plans/{draft['id']}/publish",
        json={
            "factory_id": factory_id,
            "expected_revision": planned["revision"],
            "request_id": "phase5-device-publish-001",
        },
    )
    assert published.status_code == 200, published.text
    return factory_id, machine, mold, order, task


def test_phase5_device_events_calibrate_speed_and_feed_analytics(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id, machine, mold, order, task = _published_device_fixture(client)
        events = []
        for index, cumulative in enumerate((10, 20, 50), start=1):
            events.append(
                {
                    "external_event_id": f"device-reading-{index}",
                    "machine_code": machine["machine_code"],
                    "task_id": task["id"],
                    "occurred_at": f"2026-08-04T{7 + index:02d}:30:00+08:00",
                    "cumulative_quantity": cumulative,
                    "cycle_seconds": 30,
                    "units_per_cycle": 1,
                    "downtime_minutes": 0,
                    "status": "COMPLETED" if index == 3 else "RUNNING",
                    "exception_code": "",
                    "exception_detail": "",
                }
            )
        payload = {
            "factory_id": factory_id,
            "source_key": "edge-huaxing-01",
            "cursor": "device-cursor-003",
            "events": events,
        }
        ingested = client.post(
            "/api/injection-scheduling/integrations/devices/production-events",
            headers={"X-Request-ID": "phase5-device-batch-001"},
            json=payload,
        )
        assert ingested.status_code == 200, ingested.text
        body = ingested.json()
        assert body["applied_count"] == 3
        assert body["calibrated_mold_count"] == 1, body
        assert all(item["observation_created"] for item in body["events"])

        replay = client.post(
            "/api/injection-scheduling/integrations/devices/production-events",
            headers={"X-Request-ID": "phase5-device-batch-001-replay"},
            json=payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["skipped_count"] == 3

        overview = client.get(
            "/api/injection-scheduling/analytics/overview",
            params={
                "factory_id": factory_id,
                "date_from": "2026-08-04",
                "date_to": "2026-08-04",
            },
        )
        assert overview.status_code == 200, overview.text
        analytics = overview.json()
        assert analytics["device_interface_configured"] is True
        assert analytics["machine_utilization"]["sample_count"] == 3
        assert analytics["machine_utilization"]["value"] > 0
        speed = next(
            item for item in analytics["speed_models"] if item["mold_id"] == mold["id"]
        )
        assert speed["status"] == "ACTIVE"
        assert speed["sample_count"] == 3
        assert speed["calibrated_units_per_hour"] == 120

        from app.models.injection_scheduling_execution import InjectionSchedulingOrder
        from app.services.injection_scheduling_scheduler.duration import (
            production_minutes,
        )

        model_order = InjectionSchedulingOrder(
            order_quantity=Decimal(60),
            completed_quantity=Decimal(10),
            mold_id=mold["id"],
        )
        calibrated_minutes = production_minutes(
            model_order,
            {
                "default_units_per_hour": 40,
                "speed_models": {
                    mold["id"]: {
                        "status": "ACTIVE",
                        "units_per_hour": speed["calibrated_units_per_hour"],
                    }
                },
            },
        )
        assert calibrated_minutes == 25
        assert order["id"] == body["events"][-1]["order_id"]
