from __future__ import annotations

import importlib
from decimal import Decimal

from sqlalchemy import select

from test_injection_scheduling_phase3_api import (
    ADMIN_TEST_PASSWORD,
    machine_payload,
    make_migrated_client,
)
from test_injection_scheduling_phase4_import import login

FACTORY_ID = "huaxing"
DEFINITION_ID = "mold-definition:manual-demand-test"
OUTPUT_ID = "mold-output:manual-demand-test"


def _seed_schedulable_shared_mold() -> None:
    db_module = importlib.import_module("app.db")
    shared = importlib.import_module("app.models.injection_scheduling_shared")
    timestamp = "2026-08-10T08:00:00+08:00"
    with db_module.SessionLocal() as db:
        definition = shared.InjectionSchedulingMoldDefinition(
            id=DEFINITION_ID,
            company_scope_id="company:royal-regent",
            canonical_mold_no="MANUAL-M-001",
            display_mold_no="MANUAL-M-001",
            standard_name="手工需求测试模具",
            recommended_machine_class_raw="14A",
            mold_a_class=14,
            default_arm_type="single",
            default_fixture_type="suction_cup",
            process_tags_json="[]",
            engineering_json="{}",
            status="ACTIVE",
            data_quality="APPROVED",
            revision=1,
            valid_from="2026-08-10",
            created_factory_id=FACTORY_ID,
            approved_by="system-test",
            created_at=timestamp,
            approved_at=timestamp,
        )
        output = shared.InjectionSchedulingMoldOutputSpec(
            id=OUTPUT_ID,
            mold_definition_id=DEFINITION_ID,
            customer_identity_id=None,
            item_no="MANUAL-ITEM-001",
            variant_code="",
            product_name="手工需求测试产品",
            cavity_count=2,
            units_per_shot=Decimal(2),
            whole_shot_net_weight_g=Decimal(120),
            whole_shot_gross_weight_g=Decimal(130),
            default_material="ABS",
            default_color="黑色",
            nominal_daily_capacity=Decimal(1000),
            status="ACTIVE",
            revision=1,
            valid_from="2026-08-10",
            created_at=timestamp,
        )
        capability = shared.InjectionSchedulingFactoryMoldCapability(
            id="capability:manual-demand-test",
            factory_id=FACTORY_ID,
            mold_definition_id=DEFINITION_ID,
            mold_output_spec_id=OUTPUT_ID,
            physical_asset_id=None,
            machine_class=14,
            applicability_key="manual-demand-test-output",
            required_arm_type="single",
            required_fixture_type="suction_cup",
            process_limits_json="{}",
            nominal_daily_capacity=Decimal(1000),
            setup_minutes=10,
            priority=100,
            status="ACTIVE",
            revision=1,
            valid_from=timestamp,
            approved_by="system-test",
            approved_at=timestamp,
            created_at=timestamp,
        )
        db.add_all([definition, output, capability])
        db.commit()


def _manual_payload(quantity: float = 200) -> dict:
    return {
        "factory_id": FACTORY_ID,
        "expected_revision": 0,
        "business_date": "2026-08-10",
        "mold_definition_id": DEFINITION_ID,
        "mold_output_spec_id": OUTPUT_ID,
        "planned_quantity": quantity,
        "quantity_basis": "UNITS",
        "item_no": "MANUAL-ITEM-001",
        "product_name": "手工需求测试产品",
        "delivery_due_date": "2026-08-12",
        "priority_code": "NORMAL",
        "material_readiness_status": "ready",
        "warehouse_text": "温少雄",
        "material_name": "ABS",
        "color_name": "黑色",
        "remark": "无需下单表建立",
    }


def test_manual_demand_auto_creates_draft_schedules_shared_mold_and_auto_binds_default_asset(
    monkeypatch,
):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        _seed_schedulable_shared_mold()
        machine_data = machine_payload(FACTORY_ID, "MANUAL-DEMAND-14A")
        machine_data.update(
            machine_class="14A",
            injection_capacity_g=300,
            robot_capabilities=["single"],
            fixture_capabilities=[],
        )
        machine = client.post("/api/injection-scheduling/machines", json=machine_data)
        assert machine.status_code == 201, machine.text

        created = client.post(
            "/api/injection-scheduling/manual-demands",
            headers={"X-Request-ID": "manual-demand-create-0001"},
            json=_manual_payload(),
        )
        assert created.status_code == 201, created.text
        order = created.json()
        assert order["order_no"].startswith("MPD-")
        assert order["source_type"] == "MANUAL_PLANNING_DEMAND"
        assert order["mold_id"] is None
        assert order["mold_definition_id"] == DEFINITION_ID
        assert order["mold_output_spec_id"] == OUTPUT_ID

        current = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": FACTORY_ID},
        )
        assert current.status_code == 200, current.text
        draft = current.json()["plan"]
        assert draft["status"] == "DRAFT"
        assert draft["tasks"] == []

        preview = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "manual-demand-preview-0001"},
            json={
                "factory_id": FACTORY_ID,
                "plan_id": draft["id"],
                "expected_plan_revision": draft["revision"],
                "rule_revision": draft["rule_revision"],
                "mode": "PREVIEW",
                "horizon_start": "2026-08-10T08:00:00+08:00",
                "horizon_end": "2026-08-14T20:00:00+08:00",
                "order_ids": [order["id"]],
                "respect_locked_tasks": True,
                "solver": "HEURISTIC",
                "time_limit_seconds": 10,
            },
        )
        assert preview.status_code == 201, preview.text
        run = preview.json()
        assert run["summary"]["scheduled_count"] == 1
        assert run["summary"]["review_count"] == 0
        assert run["summary"]["unassigned_count"] == 0
        assert run["assignments"][0]["mold_id"] is None

        db_module = importlib.import_module("app.db")
        shared = importlib.import_module("app.models.injection_scheduling_shared")
        with db_module.SessionLocal() as db:
            capability = db.get(
                shared.InjectionSchedulingFactoryMoldCapability,
                "capability:manual-demand-test",
            )
            capability.revision = 2
            db.commit()
        stale_apply = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{run['id']}/apply",
            json={
                "factory_id": FACTORY_ID,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "manual-demand-stale-apply-0001",
                "review_override_reason": "",
            },
        )
        assert stale_apply.status_code == 409, stale_apply.text
        assert stale_apply.json()["detail"]["message"] == (
            "预览输入已变化，请重新生成自动排期"
        )
        with db_module.SessionLocal() as db:
            capability = db.get(
                shared.InjectionSchedulingFactoryMoldCapability,
                "capability:manual-demand-test",
            )
            capability.revision = 1
            db.commit()

        applied = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{run['id']}/apply",
            json={
                "factory_id": FACTORY_ID,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "manual-demand-apply-0001",
                "review_override_reason": "",
            },
        )
        assert applied.status_code == 200, applied.text
        applied_plan = applied.json()["plan"]
        assert len(applied_plan["tasks"]) == 1
        assert applied_plan["tasks"][0]["mold_id"] is None
        assert applied_plan["tasks"][0]["physical_mold_asset_id"] is None

        publish = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/publish",
            json={
                "factory_id": FACTORY_ID,
                "expected_revision": applied_plan["revision"],
                "request_id": "manual-demand-publish-0001",
            },
        )
        assert publish.status_code == 200, publish.text
        published_plan = publish.json()["plan"]
        assert published_plan["status"] == "PUBLISHED"
        physical_asset_id = published_plan["tasks"][0]["physical_mold_asset_id"]
        assert physical_asset_id
        with db_module.SessionLocal() as db:
            asset = db.get(
                shared.InjectionSchedulingPhysicalMoldAsset,
                physical_asset_id,
            )
            assert asset is not None
            assert asset.mold_definition_id == DEFINITION_ID
            assert asset.current_factory_id == FACTORY_ID
            assert asset.owner_scope_type == "FACTORY"
            assert asset.owner_scope_id == FACTORY_ID
            assert asset.status == "AVAILABLE"
            assert asset.source_copy_no == 1
            assert asset.asset_code.startswith("DEFAULT-MANUAL-M-001-")


def test_manual_demand_can_be_updated_and_cancelled_before_scheduling(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        _seed_schedulable_shared_mold()
        created = client.post(
            "/api/injection-scheduling/manual-demands",
            headers={"X-Request-ID": "manual-demand-create-0002"},
            json=_manual_payload(100),
        )
        assert created.status_code == 201, created.text
        order = created.json()
        update_payload = _manual_payload(160)
        update_payload.pop("business_date")

        updated = client.patch(
            f"/api/injection-scheduling/manual-demands/{order['id']}",
            headers={"X-Request-ID": "manual-demand-update-0002"},
            json={
                **update_payload,
                "expected_revision": order["revision"],
            },
        )
        assert updated.status_code == 200, updated.text
        changed = updated.json()
        assert changed["order_quantity"] == 160
        assert changed["revision"] == order["revision"] + 1

        cancelled = client.post(
            f"/api/injection-scheduling/manual-demands/{order['id']}/cancel",
            headers={"X-Request-ID": "manual-demand-cancel-0002"},
            json={
                "factory_id": FACTORY_ID,
                "expected_revision": changed["revision"],
                "reason": "测试取消需求",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"

        backlog = client.get(
            "/api/injection-scheduling/backlog",
            params={"factory_id": FACTORY_ID},
        )
        assert backlog.status_code == 200, backlog.text
        assert all(item["id"] != order["id"] for item in backlog.json()["items"])


def test_imported_backlog_order_can_be_audit_cancelled_without_deleting_source(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        _seed_schedulable_shared_mold()
        created = client.post(
            "/api/injection-scheduling/manual-demands",
            headers={"X-Request-ID": "backlog-cancel-create-0001"},
            json=_manual_payload(120),
        )
        assert created.status_code == 201, created.text
        order = created.json()

        db_module = importlib.import_module("app.db")
        execution = importlib.import_module(
            "app.models.injection_scheduling_execution"
        )
        with db_module.SessionLocal() as db:
            stored = db.get(execution.InjectionSchedulingOrder, order["id"])
            assert stored is not None
            stored.source_type = "DEMAND_ORDER_VERSION"
            stored.source_ref = "demand-version:preserved-0001"
            db.commit()

        current = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": FACTORY_ID},
        )
        assert current.status_code == 200, current.text
        draft = current.json()["plan"]

        stale = client.post(
            f"/api/injection-scheduling/backlog/{order['id']}/cancel",
            headers={"X-Request-ID": "backlog-cancel-stale-0001"},
            json={
                "factory_id": FACTORY_ID,
                "expected_revision": order["revision"],
                "expected_plan_id": draft["id"],
                "expected_plan_revision": draft["revision"] + 1,
                "reason": "重复下单",
            },
        )
        assert stale.status_code == 409, stale.text

        cancelled = client.post(
            f"/api/injection-scheduling/backlog/{order['id']}/cancel",
            headers={"X-Request-ID": "backlog-cancel-confirm-0001"},
            json={
                "factory_id": FACTORY_ID,
                "expected_revision": order["revision"],
                "expected_plan_id": draft["id"],
                "expected_plan_revision": draft["revision"],
                "reason": "重复下单",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["source_type"] == "DEMAND_ORDER_VERSION"

        backlog = client.get(
            "/api/injection-scheduling/backlog",
            params={"factory_id": FACTORY_ID},
        )
        assert backlog.status_code == 200, backlog.text
        assert all(item["id"] != order["id"] for item in backlog.json()["items"])

        with db_module.SessionLocal() as db:
            stored = db.get(execution.InjectionSchedulingOrder, order["id"])
            assert stored is not None
            assert stored.status == "CANCELLED"
            assert stored.source_ref == "demand-version:preserved-0001"
            state = db.scalar(
                select(execution.InjectionSchedulingPlanOrderState).where(
                    execution.InjectionSchedulingPlanOrderState.plan_id == draft["id"],
                    execution.InjectionSchedulingPlanOrderState.order_id == order["id"],
                )
            )
            assert state is not None
            assert state.status == "CANCELLED"
            audit = db.scalar(
                select(execution.InjectionSchedulingAuditEvent).where(
                    execution.InjectionSchedulingAuditEvent.request_id
                    == "backlog-cancel-confirm-0001"
                )
            )
            assert audit is not None
            assert audit.event_type == "backlog_order_cancelled"
