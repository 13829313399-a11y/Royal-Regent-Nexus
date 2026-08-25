import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{TEST_TMP_DIR / f'injection_workbench_{uuid4().hex}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text


def machine_payload(factory_id: str, code: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "machine_code": code,
        "area": "A区",
        "position": code,
        "machine_class": "12A",
        "clamping_force_tons": 160,
        "injection_capacity_g": 300,
        "tie_bar_x_mm": None,
        "tie_bar_y_mm": None,
        "platen_x_mm": None,
        "platen_y_mm": None,
        "min_mold_thickness_mm": None,
        "max_mold_thickness_mm": None,
        "opening_stroke_mm": None,
        "machine_type": "standard",
        "robot_capabilities": ["single", "dual"],
        "fixture_capabilities": ["clamp"],
        "process_restrictions": ["no_pvc"],
        "remarks": "双臂五轴，不能啤 PVC",
        "status": "available",
    }


def mold_payload(factory_id: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "mold_no": "M-001",
        "name": "脱敏模具",
        "length_mm": None,
        "width_mm": None,
        "height_mm": None,
        "weight_kg": None,
        "recommended_machine_class": "12A",
        "whole_shot_net_weight_g": 18,
        "whole_shot_gross_weight_g": 20,
        "required_arm_type": "dual",
        "required_fixture_type": "clamp",
        "material_code": "ABS",
        "material_name": "ABS",
        "color_profile": "浅蓝",
        "process_requirements": [],
        "copy_count": 1,
        "data_quality_status": "complete",
        "status": "available",
    }


def order_payload(factory_id: str, order_no: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "order_no": order_no,
        "item_no": "000123",
        "product_name": "脱敏产品",
        "order_quantity": 1000,
        "source_completed_quantity": 100,
        "delivery_start_date": "2026-08-24",
        "delivery_due_date": "2026-08-27",
        "priority_code": "URGENT",
        "material_readiness_status": "ready",
        "warehouse_text": "B仓",
        "remark": "保持来源备注",
        "source_ref": "workbench-fixture",
        "source_version": "v1",
        "lineage": {
            "source_mold_no": "M-001",
            "mold_name": "脱敏模具",
            "material_name": "ABS",
            "color_name": "浅蓝",
            "color_powder_code": "C-01",
            "sprue_ratio": 0.1,
            "spray_required": "false",
            "source_daily_capacity": 500,
            "mold_enrichment_status": "MATCHED",
        },
    }


def test_workbench_aggregates_authoritative_plan_and_factory_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get(
            "/api/injection-scheduling/workbench",
            params={"factory_id": "huaxing"},
        )
        assert anonymous.status_code == 401
        login(client)

        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huaxing", "12A-03"),
        )
        assert machine.status_code == 201, machine.text
        other_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload("huakang-b", "12A-03"),
        )
        assert other_machine.status_code == 201, other_machine.text
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload("huaxing"),
        )
        assert mold.status_code == 201, mold.text
        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload("huaxing", "SO-0001"),
        )
        assert order.status_code == 201, order.text
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": "huaxing",
                "expected_revision": 0,
                "business_date": "2026-08-25",
            },
        )
        assert draft.status_code == 201, draft.text
        task = client.post(
            f"/api/injection-scheduling/plans/{draft.json()['id']}/tasks",
            json={
                "factory_id": "huaxing",
                "expected_revision": draft.json()["revision"],
                "machine_id": machine.json()["id"],
                "order_id": order.json()["id"],
                "mold_id": mold.json()["id"],
                "mold_copy_no": 1,
                "sequence_no": 0,
                "execution_status": "QUEUED",
                "planned_start": "2026-08-25T08:00:00",
                "planned_finish": "2026-08-26T08:00:00",
                "shift_target_quantity": 500,
                "locked": False,
                "manual_override_reason": "",
            },
        )
        assert task.status_code == 201, task.text

        response = client.get(
            "/api/injection-scheduling/workbench",
            params={"factory_id": "huaxing", "search": "000123"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["factory_id"] == "huaxing"
        assert body["plan_mode"] == "PLANNING"
        assert len(body["machines"]) == 1
        assert body["machines"][0]["code"] == "12A-03"
        assert body["machines"][0]["available_for_auto_schedule"] is True
        assert "不能啤 PVC" in body["machines"][0]["parsed_constraint_summary"]
        assert len(body["jobs"]) == 1
        job = body["jobs"][0]
        assert job["status"] == "PLANNED"
        assert job["machine_code"] == "12A-03"
        assert job["item_no"] == "000123"
        assert job["mold_no"] == "M-001"
        assert job["required_machine_a"] == 12
        assert job["spray_required"] is False
        assert job["completed_quantity"] == 100
        assert job["outstanding_quantity"] == 900
        assert job["completion_rate"] == 0.1
        assert body["summary"]["unplanned_count"] == 0

        bulk_update = client.post(
            "/api/injection-scheduling/workbench/jobs/bulk-update",
            json={
                "factory_id": "huaxing",
                "expected_plan_revision": body["plan_revision"],
                "request_id": "workbench-paste-0001",
                "changes": [
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "shift_target_quantity",
                        "value": 640,
                    },
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "warehouse_text",
                        "value": "C仓",
                    },
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "locked",
                        "value": True,
                    },
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "manual_override_reason",
                        "value": "人工锁定急单",
                    },
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "order_remark",
                        "value": "批量保存备注",
                    },
                ],
            },
        )
        assert bulk_update.status_code == 200, bulk_update.text
        updated_job = bulk_update.json()["jobs"][0]
        assert updated_job["shift_target_quantity"] == 640
        assert updated_job["warehouse_text"] == "C仓"
        assert updated_job["locked"] is True
        assert updated_job["manual_override_reason"] == "人工锁定急单"
        assert updated_job["order_remark"] == "批量保存备注"
        assert updated_job["task_revision"] == job["task_revision"] + 1
        assert updated_job["order_revision"] == job["order_revision"] + 1

        stale_bulk_update = client.post(
            "/api/injection-scheduling/workbench/jobs/bulk-update",
            json={
                "factory_id": "huaxing",
                "expected_plan_revision": body["plan_revision"],
                "request_id": "workbench-paste-stale",
                "changes": [
                    {
                        "job_id": job["id"],
                        "expected_task_revision": job["task_revision"],
                        "expected_order_revision": job["order_revision"],
                        "field": "shift_target_quantity",
                        "value": 720,
                    }
                ],
            },
        )
        assert stale_bulk_update.status_code == 409

        filtered = client.get(
            "/api/injection-scheduling/workbench",
            params={"factory_id": "huaxing", "status": "UNPLANNED"},
        )
        assert filtered.status_code == 200
        assert filtered.json()["jobs"] == []


def test_workbench_exposes_unscheduled_order_without_fabricating_task(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client)
        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload("huakang-b", "SO-BACKLOG-01"),
        )
        assert order.status_code == 201, order.text

        response = client.get(
            "/api/injection-scheduling/workbench",
            params={"factory_id": "huakang-b"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["plan_mode"] == "EMPTY"
        assert len(body["jobs"]) == 1
        job = body["jobs"][0]
        assert job["status"] == "UNPLANNED"
        assert job["task_id"] is None
        assert job["machine_id"] is None
        assert job["machine_code"] == ""
        assert body["summary"]["unplanned_count"] == 1
