import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{TEST_TMP_DIR / f'injection_phase3_{uuid4().hex}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def make_migrated_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_path = TEST_TMP_DIR / f"injection_phase3_migrated_{uuid4().hex}.db"
    database_url = f"sqlite:///{database_path}"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    migration = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND_DIR / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert migration.returncode == 0, migration.stderr
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(
    client: TestClient,
    username: str,
    password: str = "123456",
) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def ensure_user(
    username: str,
    role_id: str,
    *,
    factory_id: str,
    department: str,
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash("123456")
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=username,
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.add(
            auth_models.AuthUserRole(
                id=f"{user_id}:{role_id}:{factory_id}:{department}",
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.commit()


def machine_payload(factory_id: str, machine_code: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "machine_code": machine_code,
        "area": "A区",
        "position": "A-02",
        "machine_class": "32A",
        "clamping_force_tons": 320,
        "injection_capacity_g": 617,
        "tie_bar_x_mm": 680,
        "tie_bar_y_mm": 680,
        "platen_x_mm": 820,
        "platen_y_mm": 820,
        "min_mold_thickness_mm": 250,
        "max_mold_thickness_mm": 850,
        "opening_stroke_mm": 700,
        "machine_type": "standard",
        "robot_capabilities": ["single", "dual"],
        "fixture_capabilities": ["suction_cup"],
        "process_restrictions": [],
        "status": "available",
    }


def order_payload(factory_id: str, order_no: str, quantity: float = 100) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "order_no": order_no,
        "item_no": f"ITEM-{order_no}",
        "product_name": "测试注塑件",
        "order_quantity": quantity,
        "source_completed_quantity": 10,
        "delivery_start_date": "2026-08-01",
        "delivery_due_date": "2026-08-03",
        "priority_code": "URGENT",
        "material_readiness_status": "ready",
        "warehouse_text": "B库",
        "remark": "阶段3测试",
        "source_ref": "manual-test",
        "source_version": "v1",
        "lineage": {"source": "phase3-test"},
    }


def mold_payload(factory_id: str, mold_no: str) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": 0,
        "mold_no": mold_no,
        "name": "并行模具",
        "length_mm": 550,
        "width_mm": 450,
        "height_mm": 850,
        "weight_kg": None,
        "recommended_machine_class": "32A",
        "whole_shot_net_weight_g": 379,
        "whole_shot_gross_weight_g": None,
        "required_arm_type": "dual",
        "required_fixture_type": "suction_cup",
        "material_code": "ABS",
        "material_name": "ABS",
        "color_profile": "",
        "process_requirements": [],
        "copy_count": 2,
        "data_quality_status": "complete",
        "status": "available",
    }


def task_payload(
    factory_id: str,
    expected_revision: int,
    machine_id: str,
    order_id: str,
    sequence_no: int,
) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": expected_revision,
        "machine_id": machine_id,
        "order_id": order_id,
        "sequence_no": sequence_no,
        "execution_status": "QUEUED",
        "planned_start": f"2026-08-01T0{sequence_no}:00:00",
        "planned_finish": f"2026-08-01T0{sequence_no + 1}:00:00",
        "shift_target_quantity": 40,
        "locked": False,
        "manual_override_reason": "",
    }


def shift_report_payload(
    factory_id: str,
    expected_revision: int,
    request_id: str,
    reported_quantity: float,
    *,
    quantity_mode: str = "INCREMENTAL",
    reported_status: str = "RUNNING",
) -> dict:
    return {
        "factory_id": factory_id,
        "expected_revision": expected_revision,
        "request_id": request_id,
        "business_date": "2026-08-01",
        "shift_code": "DAY",
        "quantity_mode": quantity_mode,
        "reported_quantity": reported_quantity,
        "shift_target_quantity": 40,
        "downtime_minutes": 0,
        "exception_code": "",
        "exception_detail": "",
        "reported_status": reported_status,
    }


def test_phase3_plan_publish_report_rollback_and_polling_contract(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"

        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "A区3号机"),
        )
        assert machine.status_code == 201, machine.text
        machine_id = machine.json()["id"]

        first_order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "BJB260801-1"),
        )
        second_order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "BJB260801-2", 80),
        )
        assert first_order.status_code == 201, first_order.text
        assert second_order.status_code == 201, second_order.text
        first_order_id = first_order.json()["id"]
        second_order_id = second_order.json()["id"]

        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        )
        assert draft.status_code == 201, draft.text
        plan_id = draft.json()["id"]

        first_task_response = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(factory_id, 1, machine_id, first_order_id, 1),
        )
        assert first_task_response.status_code == 201, first_task_response.text
        assert first_task_response.json()["revision"] == 2
        first_task_id = first_task_response.json()["tasks"][0]["id"]

        second_task_response = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(factory_id, 2, machine_id, second_order_id, 2),
        )
        assert second_task_response.status_code == 201, second_task_response.text
        assert second_task_response.json()["revision"] == 3
        second_task_id = next(
            item["id"]
            for item in second_task_response.json()["tasks"]
            if item["order_id"] == second_order_id
        )

        stale_update = client.patch(
            f"/api/injection-scheduling/plans/{plan_id}/tasks/{first_task_id}",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "expected_plan_revision": 2,
                "locked": True,
                "manual_override_reason": "交期优先",
            },
        )
        assert stale_update.status_code == 409
        assert stale_update.json()["detail"]["current_revision"] == 3

        updated = client.patch(
            f"/api/injection-scheduling/plans/{plan_id}/tasks/{first_task_id}",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "expected_plan_revision": 3,
                "locked": True,
                "manual_override_reason": "交期优先",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 4
        assert next(
            item for item in updated.json()["tasks"] if item["id"] == first_task_id
        )["revision"] == 2

        publish_payload = {
            "factory_id": factory_id,
            "expected_revision": 4,
            "request_id": "publish-phase3-001",
        }
        published = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json=publish_payload,
        )
        assert published.status_code == 200, published.text
        assert published.json()["plan"]["status"] == "PUBLISHED"
        assert published.json()["plan"]["revision"] == 5
        assert published.json()["snapshot_id"].startswith("issnapshot-")
        assert published.json()["idempotent_replay"] is False
        assert all(item["active_execution"] for item in published.json()["plan"]["tasks"])
        db_module = importlib.import_module("app.db")
        execution_models = importlib.import_module(
            "app.models.injection_scheduling_execution"
        )
        with db_module.SessionLocal() as db:
            plan_revisions = list(
                db.scalars(
                    select(execution_models.InjectionSchedulingPlanRevision)
                    .where(
                        execution_models.InjectionSchedulingPlanRevision.plan_id
                        == plan_id
                    )
                    .order_by(
                        execution_models.InjectionSchedulingPlanRevision.plan_revision
                    )
                ).all()
            )
            published_snapshot_count = db.scalar(
                select(func.count())
                .select_from(execution_models.InjectionSchedulingPublishedSnapshot)
                .where(
                    execution_models.InjectionSchedulingPublishedSnapshot.plan_id
                    == plan_id
                )
            )
        assert [item.plan_revision for item in plan_revisions] == [1, 2, 3, 4, 5]
        assert [
            json.loads(item.snapshot_json)["plan_revision"] for item in plan_revisions
        ] == [1, 2, 3, 4, 5]
        assert published_snapshot_count == 1

        publish_replay = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json=publish_payload,
        )
        assert publish_replay.status_code == 200, publish_replay.text
        assert publish_replay.json()["idempotent_replay"] is True
        assert publish_replay.json()["snapshot_id"] == published.json()["snapshot_id"]

        conflicting_publish = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={**publish_payload, "expected_revision": 3},
        )
        assert conflicting_publish.status_code == 409

        immutable = client.patch(
            f"/api/injection-scheduling/plans/{plan_id}/tasks/{first_task_id}",
            json={
                "factory_id": factory_id,
                "expected_revision": 2,
                "expected_plan_revision": 5,
                "planned_finish": "2026-08-01T06:00:00",
            },
        )
        assert immutable.status_code == 409
        assert immutable.json()["detail"] == "已发布计划不可修改"

        first_report_payload = shift_report_payload(
            factory_id,
            2,
            "shift-report-phase3-001",
            20,
        )
        tampered_projection = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json={
                **first_report_payload,
                "request_id": "shift-report-phase3-tampered",
                "estimated_finish": "2099-01-01T00:00:00",
            },
        )
        assert tampered_projection.status_code == 422
        first_report = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=first_report_payload,
        )
        assert first_report.status_code == 200, first_report.text
        assert first_report.json()["report"]["normalized_increment_quantity"] == 20
        assert first_report.json()["task"]["reported_quantity"] == 20
        assert first_report.json()["task"]["revision"] == 3
        assert first_report.json()["order"]["completed_quantity"] == 30
        assert first_report.json()["task"]["estimated_remaining_shifts"] == 2
        assert first_report.json()["task"]["estimated_finish"]
        assert first_report.json()["order"]["estimated_completion_at"]
        assert first_report.json()["order"]["estimated_remaining_shifts"] == 2
        assert first_report.json()["idempotent_replay"] is False

        first_report_replay = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=first_report_payload,
        )
        assert first_report_replay.status_code == 200, first_report_replay.text
        assert first_report_replay.json()["idempotent_replay"] is True
        assert first_report_replay.json()["report"]["id"] == first_report.json()["report"]["id"]

        conflicting_report = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json={**first_report_payload, "reported_quantity": 21},
        )
        assert conflicting_report.status_code == 409

        stale_report = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                2,
                "shift-report-phase3-stale",
                5,
            ),
        )
        assert stale_report.status_code == 409
        assert stale_report.json()["detail"]["current_revision"] == 3

        cumulative_report = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                3,
                "shift-report-phase3-002",
                25,
                quantity_mode="CUMULATIVE",
                reported_status="BLOCKED",
            ),
        )
        assert cumulative_report.status_code == 200, cumulative_report.text
        assert cumulative_report.json()["report"]["normalized_increment_quantity"] == 5
        assert cumulative_report.json()["task"]["reported_quantity"] == 25
        assert cumulative_report.json()["order"]["completed_quantity"] == 35
        queue_after_recalculation = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        )
        assert queue_after_recalculation.status_code == 200
        queue_tasks = queue_after_recalculation.json()["plan"]["tasks"]
        first_projection = next(
            item for item in queue_tasks if item["id"] == first_task_id
        )
        second_projection = next(
            item for item in queue_tasks if item["id"] == second_task_id
        )
        assert second_projection["estimated_start"] >= first_projection["estimated_finish"]

        decreasing_cumulative = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                4,
                "shift-report-phase3-decreasing",
                24,
                quantity_mode="CUMULATIVE",
            ),
        )
        assert decreasing_cumulative.status_code == 409

        second_running = client.post(
            f"/api/injection-scheduling/tasks/{second_task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                second_projection["revision"],
                "shift-report-phase3-003",
                10,
            ),
        )
        assert second_running.status_code == 200, second_running.text

        running_conflict = client.post(
            f"/api/injection-scheduling/tasks/{first_task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                4,
                "shift-report-phase3-running-conflict",
                1,
            ),
        )
        assert running_conflict.status_code == 409
        assert running_conflict.json()["detail"] == "同一机台已有正在生产任务"

        current = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        )
        assert current.status_code == 200, current.text
        assert current.json()["plan"]["id"] == plan_id
        assert current.json()["polling_revision"] >= published.json()["audit_sequence"]

        events = client.get(
            "/api/injection-scheduling/events",
            params={"factory_id": factory_id, "after_sequence": 0},
        )
        assert events.status_code == 200, events.text
        assert events.json()["retry_after_seconds"] == 12
        assert events.json()["latest_sequence"] == events.json()["events"][-1]["sequence"]
        assert {item["factory_id"] for item in events.json()["events"]} == {factory_id}
        assert {
            "plan_published",
            "shift_report_recorded",
        } <= {item["event_type"] for item in events.json()["events"]}

        rollback_payload = {
            "factory_id": factory_id,
            "expected_revision": 5,
            "request_id": "rollback-phase3-001",
            "business_date": "2026-08-02",
        }
        rolled_back = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json=rollback_payload,
        )
        assert rolled_back.status_code == 200, rolled_back.text
        assert rolled_back.json()["plan"]["status"] == "DRAFT"
        assert rolled_back.json()["plan"]["based_on_plan_id"] == plan_id
        assert rolled_back.json()["plan"]["business_date"] == "2026-08-02"
        assert rolled_back.json()["idempotent_replay"] is False
        assert all(
            item["reported_quantity"] == 0
            and item["active_execution"] is False
            and item["execution_status"] in {"QUEUED", "BLOCKED"}
            for item in rolled_back.json()["plan"]["tasks"]
        )

        rollback_replay = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json=rollback_payload,
        )
        assert rollback_replay.status_code == 200, rollback_replay.text
        assert rollback_replay.json()["idempotent_replay"] is True
        assert rollback_replay.json()["plan"]["id"] == rolled_back.json()["plan"]["id"]
        with db_module.SessionLocal() as db:
            rollback_revision_count = db.scalar(
                select(func.count())
                .select_from(execution_models.InjectionSchedulingPlanRevision)
                .where(
                    execution_models.InjectionSchedulingPlanRevision.plan_id
                    == rolled_back.json()["plan"]["id"]
                )
            )
        assert rollback_revision_count == 1

        hidden_other_factory = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json={
                **rollback_payload,
                "factory_id": "huakang-b",
                "request_id": "rollback-phase3-other-factory",
            },
        )
        assert hidden_other_factory.status_code == 404


def test_phase3_clerk_can_edit_and_report_but_supervisor_controls_release(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huakang-b"
        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "B区1号机"),
        )
        assert machine.status_code == 201, machine.text
        machine_id = machine.json()["id"]

        ensure_user(
            "phase3-clerk",
            "molding_clerk",
            factory_id=factory_id,
            department="molding",
        )
        ensure_user(
            "phase3-supervisor",
            "position_molding_supervisor",
            factory_id=factory_id,
            department="molding",
        )

        clerk = login(client, "phase3-clerk")
        assert "injection_scheduling:edit" in clerk["permissions"]
        assert "injection_scheduling:report" in clerk["permissions"]
        assert "injection_scheduling:publish" not in clerk["permissions"]

        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "CLERK-ORDER"),
        )
        assert order.status_code == 201, order.text
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        )
        assert draft.status_code == 201, draft.text
        plan_id = draft.json()["id"]
        planned = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(factory_id, 1, machine_id, order.json()["id"], 1),
        )
        assert planned.status_code == 201, planned.text
        task_id = planned.json()["tasks"][0]["id"]

        clerk_override = client.patch(
            f"/api/injection-scheduling/plans/{plan_id}/tasks/{task_id}",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "expected_plan_revision": 2,
                "locked": True,
                "manual_override_reason": "文员无权人工覆盖",
            },
        )
        assert clerk_override.status_code == 403

        clerk_publish = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": 2,
                "request_id": "clerk-publish-denied",
            },
        )
        assert clerk_publish.status_code == 403

        supervisor = login(client, "phase3-supervisor")
        assert "injection_scheduling:publish" in supervisor["permissions"]
        published = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": 2,
                "request_id": "supervisor-publish-001",
            },
        )
        assert published.status_code == 200, published.text

        login(client, "phase3-clerk")
        report = client.post(
            f"/api/injection-scheduling/tasks/{task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                1,
                "clerk-shift-report-001",
                10,
            ),
        )
        assert report.status_code == 200, report.text

        clerk_rollback = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json={
                "factory_id": factory_id,
                "expected_revision": 3,
                "request_id": "clerk-rollback-denied",
            },
        )
        assert clerk_rollback.status_code == 403


def test_phase3_lifecycle_runs_against_migrated_database_guards(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "迁移库1号机"),
        )
        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "MIGRATED-ORDER"),
        )
        assert machine.status_code == 201, machine.text
        assert order.status_code == 201, order.text
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        )
        assert draft.status_code == 201, draft.text
        plan_id = draft.json()["id"]
        planned = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(
                factory_id,
                1,
                machine.json()["id"],
                order.json()["id"],
                1,
            ),
        )
        assert planned.status_code == 201, planned.text
        task_id = planned.json()["tasks"][0]["id"]
        published = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": 2,
                "request_id": "migrated-publish-001",
            },
        )
        assert published.status_code == 200, published.text
        reported = client.post(
            f"/api/injection-scheduling/tasks/{task_id}/shift-reports",
            json=shift_report_payload(
                factory_id,
                1,
                "migrated-shift-report-001",
                10,
            ),
        )
        assert reported.status_code == 200, reported.text

        rolled_back = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json={
                "factory_id": factory_id,
                "expected_revision": 3,
                "request_id": "migrated-rollback-001",
            },
        )
        assert rolled_back.status_code == 200, rolled_back.text
        rollback_plan_id = rolled_back.json()["plan"]["id"]
        republished = client.post(
            f"/api/injection-scheduling/plans/{rollback_plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "request_id": "migrated-publish-002",
            },
        )
        assert republished.status_code == 200, republished.text
        assert republished.json()["plan"]["status"] == "PUBLISHED"

        db_module = importlib.import_module("app.db")
        execution_models = importlib.import_module(
            "app.models.injection_scheduling_execution"
        )
        with db_module.SessionLocal() as db:
            previous_plan = db.get(execution_models.InjectionSchedulingPlan, plan_id)
            previous_task = db.get(execution_models.InjectionSchedulingTask, task_id)
            assert previous_plan.status == "ARCHIVED"
            assert previous_task.active_execution is False


def test_phase3_rejects_machine_and_physical_mold_overlap(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        first_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "冲突测试1号机"),
        )
        second_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "冲突测试2号机"),
        )
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(factory_id, "MOLD-COPY-2"),
        )
        assert first_machine.status_code == 201, first_machine.text
        assert second_machine.status_code == 201, second_machine.text
        assert mold.status_code == 201, mold.text
        orders = [
            client.post(
                "/api/injection-scheduling/orders",
                json=order_payload(factory_id, f"OVERLAP-{index}"),
            )
            for index in range(1, 4)
        ]
        assert all(response.status_code == 201 for response in orders)
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        )
        assert draft.status_code == 201, draft.text
        plan_id = draft.json()["id"]
        first_task = {
            **task_payload(
                factory_id,
                1,
                first_machine.json()["id"],
                orders[0].json()["id"],
                1,
            ),
            "mold_id": mold.json()["id"],
            "mold_copy_no": 1,
        }
        added = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=first_task,
        )
        assert added.status_code == 201, added.text

        overlapping_window = {
            "planned_start": "2026-08-01T01:30:00",
            "planned_finish": "2026-08-01T02:30:00",
        }
        same_machine = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json={
                **task_payload(
                    factory_id,
                    2,
                    first_machine.json()["id"],
                    orders[1].json()["id"],
                    2,
                ),
                **overlapping_window,
                "mold_id": mold.json()["id"],
                "mold_copy_no": 2,
            },
        )
        assert same_machine.status_code == 409
        assert same_machine.json()["detail"] == "同一机台的排产时间不可重叠"

        same_physical_mold = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json={
                **task_payload(
                    factory_id,
                    2,
                    second_machine.json()["id"],
                    orders[1].json()["id"],
                    1,
                ),
                **overlapping_window,
                "mold_id": mold.json()["id"],
                "mold_copy_no": 1,
            },
        )
        assert same_physical_mold.status_code == 409
        assert same_physical_mold.json()["detail"] == "同一实体模具副本不可重叠排产"

        unavailable_copy = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json={
                **task_payload(
                    factory_id,
                    2,
                    second_machine.json()["id"],
                    orders[1].json()["id"],
                    1,
                ),
                **overlapping_window,
                "mold_id": mold.json()["id"],
                "mold_copy_no": 3,
            },
        )
        assert unavailable_copy.status_code == 409
        assert unavailable_copy.json()["detail"] == "模具副本号超过可用副本数量"

        second_copy = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json={
                **task_payload(
                    factory_id,
                    2,
                    second_machine.json()["id"],
                    orders[2].json()["id"],
                    1,
                ),
                **overlapping_window,
                "mold_id": mold.json()["id"],
                "mold_copy_no": 2,
            },
        )
        assert second_copy.status_code == 201, second_copy.text
