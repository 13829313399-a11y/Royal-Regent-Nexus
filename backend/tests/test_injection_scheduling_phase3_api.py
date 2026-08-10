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
        order_created_event = next(
            item
            for item in events.json()["events"]
            if item["event_type"] == "order_created"
        )
        task_created_event = next(
            item
            for item in events.json()["events"]
            if item["event_type"] == "plan_task_created"
        )
        assert order_created_event["detail"]["order"]["id"]
        assert task_created_event["detail"]["task"]["id"]
        assert task_created_event["detail"]["order"]["id"]

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
        rollback_tasks = rolled_back.json()["plan"]["tasks"]
        assert all(
            item["active_execution"] is False
            and item["source_task_id"]
            and item["origin"] == "successor_clone"
            for item in rollback_tasks
        )
        assert sum(item["reported_quantity"] for item in rollback_tasks) == 35
        assert {item["execution_status"] for item in rollback_tasks} == {
            "RUNNING",
            "BLOCKED",
        }

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


def test_phase3_clerk_can_edit_report_and_publish_but_not_override_or_rollback(monkeypatch):
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
                "request_id": "clerk-publish-allowed",
            },
        )
        assert clerk_publish.status_code == 200, clerk_publish.text
        assert clerk_publish.json()["plan"]["status"] == "PUBLISHED"

        supervisor = login(client, "phase3-supervisor")
        assert "injection_scheduling:publish" in supervisor["permissions"]

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


def test_phase3_clerk_withdraws_published_order_into_successor_backlog(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "撤回测试机"),
        )
        assert machine.status_code == 201, machine.text
        first_order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "WITHDRAW-ORDER-1"),
        )
        second_order = client.post(
            "/api/injection-scheduling/orders",
            json=order_payload(factory_id, "WITHDRAW-ORDER-2"),
        )
        assert first_order.status_code == 201, first_order.text
        assert second_order.status_code == 201, second_order.text

        ensure_user(
            "withdraw-clerk",
            "molding_clerk",
            factory_id=factory_id,
            department="molding",
        )
        login(client, "withdraw-clerk")
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
        first_task_plan = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(
                factory_id,
                1,
                machine.json()["id"],
                first_order.json()["id"],
                1,
            ),
        )
        second_task_plan = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/tasks",
            json=task_payload(
                factory_id,
                2,
                machine.json()["id"],
                second_order.json()["id"],
                2,
            ),
        )
        assert first_task_plan.status_code == 201, first_task_plan.text
        assert second_task_plan.status_code == 201, second_task_plan.text

        published = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": second_task_plan.json()["revision"],
                "request_id": "withdraw-publish-source",
            },
        )
        assert published.status_code == 200, published.text
        published_plan = published.json()["plan"]
        first_task = next(
            item
            for item in published_plan["tasks"]
            if item["order_id"] == first_order.json()["id"]
        )
        withdraw_payload = {
            "factory_id": factory_id,
            "expected_plan_revision": published_plan["revision"],
            "expected_task_revision": first_task["revision"],
            "expected_planning_revision": None,
            "request_id": "withdraw-published-order-001",
            "reason": "订单暂停，退回待排池",
        }
        withdrawn = client.post(
            f"/api/injection-scheduling/tasks/{first_task['id']}/withdraw-to-backlog",
            json=withdraw_payload,
        )
        assert withdrawn.status_code == 200, withdrawn.text
        result = withdrawn.json()
        assert result["successor_created"] is True
        assert result["source_plan_id"] == plan_id
        assert result["source_task_id"] == first_task["id"]
        assert result["order_id"] == first_order.json()["id"]
        assert result["plan"]["status"] == "DRAFT"
        assert {
            item["order_id"] for item in result["plan"]["tasks"]
        } == {second_order.json()["id"]}
        first_state = next(
            item
            for item in result["plan"]["plan_order_states"]
            if item["order_id"] == first_order.json()["id"]
        )
        assert first_state["status"] == "BACKLOG"

        replay = client.post(
            f"/api/injection-scheduling/tasks/{first_task['id']}/withdraw-to-backlog",
            json=withdraw_payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["plan"]["id"] == result["plan"]["id"]

        context = client.get(
            "/api/injection-scheduling/plans/context",
            params={"factory_id": factory_id},
        )
        assert context.status_code == 200, context.text
        assert context.json()["execution_published_plan"]["id"] == plan_id
        assert context.json()["planning_draft_plan"]["id"] == result["plan"]["id"]
        backlog = client.get(
            "/api/injection-scheduling/backlog",
            params={"factory_id": factory_id},
        )
        assert backlog.status_code == 200, backlog.text
        assert first_order.json()["id"] in {
            item["id"] for item in backlog.json()["items"]
        }

        replacement = client.post(
            f"/api/injection-scheduling/plans/{result['plan']['id']}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": result["plan"]["revision"],
                "request_id": "withdraw-publish-replacement",
            },
        )
        assert replacement.status_code == 200, replacement.text
        assert replacement.json()["plan"]["status"] == "PUBLISHED"
        assert {
            item["order_id"] for item in replacement.json()["plan"]["tasks"]
        } == {second_order.json()["id"]}


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


def test_v2_phase2_bulk_move_revalidates_eligibility_and_revisions(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        first_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "V2-P2-32A-1"),
        ).json()
        second_machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "V2-P2-32A-2"),
        ).json()
        small_payload = machine_payload(factory_id, "V2-P2-12A")
        small_payload["machine_class"] = "12A"
        small_machine = client.post(
            "/api/injection-scheduling/machines",
            json=small_payload,
        ).json()
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(factory_id, "V2-P2-MOLD"),
        ).json()

        first_order_payload = order_payload(factory_id, "V2-P2-ORDER-1")
        first_order_payload["mold_id"] = mold["id"]
        second_order_payload = order_payload(factory_id, "V2-P2-ORDER-2")
        second_order_payload["mold_id"] = mold["id"]
        first_order = client.post(
            "/api/injection-scheduling/orders", json=first_order_payload
        ).json()
        second_order = client.post(
            "/api/injection-scheduling/orders", json=second_order_payload
        ).json()
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks",
            json=task_payload(
                factory_id,
                1,
                first_machine["id"],
                first_order["id"],
                1,
            ),
        )
        second_plan = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks",
            json=task_payload(
                factory_id,
                2,
                first_machine["id"],
                second_order["id"],
                2,
            ),
        ).json()
        second_task = next(
            item
            for item in second_plan["tasks"]
            if item["order_id"] == second_order["id"]
        )
        move_payload = {
            "factory_id": factory_id,
            "expected_plan_revision": 3,
            "expected_rule_revision": draft["rule_revision"],
            "request_id": "v2-phase2-bulk-move-001",
            "moves": [
                {
                    "task_id": second_task["id"],
                    "expected_revision": second_task["revision"],
                    "machine_id": second_machine["id"],
                    "sequence_no": 0,
                    "planned_start": second_task["planned_start"],
                    "planned_finish": second_task["planned_finish"],
                    "override_reason": "",
                }
            ],
        }
        moved = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks/bulk-move",
            json=move_payload,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["plan"]["revision"] == 4
        assert moved.json()["moves"][0]["match"]["decision"] == "PASS"
        moved_task = next(
            item
            for item in moved.json()["plan"]["tasks"]
            if item["id"] == second_task["id"]
        )
        assert moved_task["machine_id"] == second_machine["id"]
        assert moved_task["sequence_no"] == 0

        replay = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks/bulk-move",
            json=move_payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True

        hard_fail_payload = {
            **move_payload,
            "expected_plan_revision": 4,
            "request_id": "v2-phase2-bulk-move-fail",
            "moves": [
                {
                    **move_payload["moves"][0],
                    "expected_revision": moved_task["revision"],
                    "machine_id": small_machine["id"],
                }
            ],
        }
        hard_fail = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks/bulk-move",
            json=hard_fail_payload,
        )
        assert hard_fail.status_code == 409
        assert hard_fail.json()["detail"]["match"]["decision"] == "FAIL"
        unchanged = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        ).json()["plan"]
        assert unchanged["revision"] == 4

        order_after_schedule = next(
            item
            for item in moved.json()["plan"]["orders"]
            if item["id"] == first_order["id"]
        )
        order_update = client.patch(
            f"/api/injection-scheduling/orders/{first_order['id']}",
            headers={"X-Request-ID": "v2-phase2-order-edit-001"},
            json={
                "factory_id": factory_id,
                "expected_revision": order_after_schedule["revision"],
                "warehouse_text": "V2 成品仓",
                "remark": "Phase 2 单元格编辑",
            },
        )
        assert order_update.status_code == 200, order_update.text
        assert order_update.json()["warehouse_text"] == "V2 成品仓"
        stale_order_update = client.patch(
            f"/api/injection-scheduling/orders/{first_order['id']}",
            json={
                "factory_id": factory_id,
                "expected_revision": order_after_schedule["revision"],
                "remark": "不应覆盖",
            },
        )
        assert stale_order_update.status_code == 409
        assert (
            stale_order_update.json()["detail"]["diff"]["remark"]
            == "Phase 2 单元格编辑"
        )


def test_v2_phase2_bulk_shift_reports_are_atomic(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machines = [
            client.post(
                "/api/injection-scheduling/machines",
                json=machine_payload(factory_id, f"V2-P2-REPORT-{index}"),
            ).json()
            for index in (1, 2)
        ]
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(factory_id, "V2-P2-REPORT-MOLD"),
        ).json()
        orders = []
        for index in (1, 2):
            payload = order_payload(factory_id, f"V2-P2-REPORT-ORDER-{index}")
            payload["mold_id"] = mold["id"]
            orders.append(
                client.post("/api/injection-scheduling/orders", json=payload).json()
            )
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        plan = draft
        for index, (machine, order) in enumerate(zip(machines, orders, strict=True)):
            task = task_payload(
                factory_id,
                index + 1,
                machine["id"],
                order["id"],
                1,
            )
            task["mold_copy_no"] = index + 1
            plan = client.post(
                f"/api/injection-scheduling/plans/{draft['id']}/tasks",
                json=task,
            ).json()
        published = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": plan["revision"],
                "request_id": "v2-phase2-publish-reports",
            },
        ).json()["plan"]
        tasks = sorted(published["tasks"], key=lambda item: item["machine_id"])

        def report_item(task: dict, suffix: str, expected_revision: int) -> dict:
            return {
                "task_id": task["id"],
                "expected_revision": expected_revision,
                "request_id": f"v2-phase2-bulk-report-{suffix}",
                "business_date": "2026-08-04",
                "shift_code": "DAY",
                "quantity_mode": "CUMULATIVE",
                "reported_quantity": 12,
                "shift_target_quantity": 40,
                "downtime_minutes": 5,
                "exception_code": "",
                "exception_detail": "",
                "reported_status": "RUNNING",
            }

        first_batch = client.post(
            "/api/injection-scheduling/tasks/shift-reports/bulk",
            json={
                "factory_id": factory_id,
                "reports": [
                    report_item(tasks[0], "001", tasks[0]["revision"]),
                    report_item(tasks[1], "002", tasks[1]["revision"]),
                ],
            },
        )
        assert first_batch.status_code == 200, first_batch.text
        assert len(first_batch.json()["results"]) == 2
        assert all(
            item["task"]["reported_quantity"] == 12
            for item in first_batch.json()["results"]
        )

        refreshed = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        ).json()["plan"]
        refreshed_tasks = sorted(refreshed["tasks"], key=lambda item: item["machine_id"])
        rollback_batch = client.post(
            "/api/injection-scheduling/tasks/shift-reports/bulk",
            json={
                "factory_id": factory_id,
                "reports": [
                    {
                        **report_item(
                            refreshed_tasks[0],
                            "rollback-first",
                            refreshed_tasks[0]["revision"],
                        ),
                        "reported_quantity": 15,
                    },
                    report_item(refreshed_tasks[1], "rollback-stale", 999),
                ],
            },
        )
        assert rollback_batch.status_code == 409
        after_rollback = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        ).json()["plan"]
        after_tasks = sorted(after_rollback["tasks"], key=lambda item: item["machine_id"])
        assert after_tasks[0]["reported_quantity"] == 12
        assert after_tasks[0]["revision"] == refreshed_tasks[0]["revision"]


def test_v2_phase3_heuristic_preview_is_deterministic_and_applies_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        small_machine_payload = machine_payload(factory_id, "V2-P3-7A")
        small_machine_payload["machine_class"] = "7A"
        small_machine_payload["injection_capacity_g"] = 220
        large_machine_payload = machine_payload(factory_id, "V2-P3-14A")
        large_machine_payload["machine_class"] = "14A"
        large_machine_payload["injection_capacity_g"] = 450
        small_machine = client.post(
            "/api/injection-scheduling/machines", json=small_machine_payload
        ).json()
        large_machine = client.post(
            "/api/injection-scheduling/machines", json=large_machine_payload
        ).json()
        mold_data = mold_payload(factory_id, "V2-P3-MOLD-7A")
        mold_data.update(
            recommended_machine_class="7A",
            whole_shot_net_weight_g=120,
            material_code="ABS",
            color_profile="浅蓝",
            copy_count=1,
        )
        mold = client.post("/api/injection-scheduling/molds", json=mold_data).json()
        orders = []
        for index in (1, 2):
            payload = order_payload(factory_id, f"V2-P3-AUTO-{index}", 80)
            payload["mold_id"] = mold["id"]
            payload["delivery_due_date"] = "2026-08-08"
            orders.append(
                client.post("/api/injection-scheduling/orders", json=payload).json()
            )
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        run_payload = {
            "factory_id": factory_id,
            "plan_id": draft["id"],
            "expected_plan_revision": draft["revision"],
            "rule_revision": draft["rule_revision"],
            "mode": "PREVIEW",
            "horizon_start": "2026-08-04T08:00:00+08:00",
            "horizon_end": "2026-08-10T20:00:00+08:00",
            "order_ids": [item["id"] for item in orders],
            "respect_locked_tasks": True,
            "solver": "HEURISTIC",
            "time_limit_seconds": 10,
        }
        first = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase3-preview-001"},
            json=run_payload,
        )
        assert first.status_code == 201, first.text
        first_payload = first.json()
        assert first_payload["status"] == "SUCCEEDED"
        assert first_payload["summary"]["scheduled_count"] == 2
        assert first_payload["summary"]["review_count"] == 0
        assert first_payload["summary"]["unassigned_count"] == 0
        assert all(
            item["machine_id"] == small_machine["id"]
            for item in first_payload["assignments"]
        )
        assert first_payload["assignments"][0]["planned_finish"] <= first_payload["assignments"][1]["planned_start"]

        second = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase3-preview-002"},
            json=run_payload,
        )
        assert second.status_code == 201, second.text
        comparable = lambda response: [
            {
                key: item[key]
                for key in (
                    "order_id",
                    "machine_id",
                    "mold_copy_no",
                    "sequence_no",
                    "planned_start",
                    "planned_finish",
                    "decision",
                    "score",
                )
            }
            for item in response.json()["assignments"]
        ]
        assert comparable(first) == comparable(second)

        applied = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{first_payload['id']}/apply",
            json={
                "factory_id": factory_id,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "v2-phase3-apply-001",
                "review_override_reason": "",
            },
        )
        assert applied.status_code == 200, applied.text
        applied_payload = applied.json()
        assert applied_payload["run"]["status"] == "APPLIED"
        assert applied_payload["plan"]["revision"] == draft["revision"] + 1
        assert len(applied_payload["plan"]["tasks"]) == 2
        assert all(
            item["auto_schedule_run_id"] == first_payload["id"]
            and item["manual_adjusted"] is False
            for item in applied_payload["plan"]["tasks"]
        )
        replay = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{first_payload['id']}/apply",
            json={
                "factory_id": factory_id,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "v2-phase3-apply-001",
                "review_override_reason": "",
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True
        other_factory = client.get(
            f"/api/injection-scheduling/auto-schedule/runs/{first_payload['id']}",
            params={"factory_id": "huakang-a"},
        )
        assert other_factory.status_code == 404
        assert small_machine["id"] != large_machine["id"]


def test_v2_phase3_batch_reasons_and_apply_revalidate_snapshot(monkeypatch):
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine_data = machine_payload(factory_id, "V2-P3-SNAPSHOT-7A")
        machine_data["machine_class"] = "7A"
        machine_data["injection_capacity_g"] = 200
        machine = client.post(
            "/api/injection-scheduling/machines", json=machine_data
        ).json()
        mold_data = mold_payload(factory_id, "V2-P3-SNAPSHOT-14A")
        mold_data["recommended_machine_class"] = "14A"
        mold_data["whole_shot_net_weight_g"] = 250
        mold = client.post("/api/injection-scheduling/molds", json=mold_data).json()
        order_data = order_payload(factory_id, "V2-P3-UNASSIGNED")
        order_data["mold_id"] = mold["id"]
        order = client.post(
            "/api/injection-scheduling/orders", json=order_data
        ).json()
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        batch = client.post(
            "/api/injection-scheduling/matches/evaluate-batch",
            json={
                "factory_id": factory_id,
                "order_ids": [order["id"]],
                "machine_ids": [machine["id"]],
                "rule_revision": draft["rule_revision"],
            },
        )
        assert batch.status_code == 200, batch.text
        result = batch.json()["evaluations"][0]["results"][0]
        assert result["decision"] == "FAIL"
        assert {item["rule_code"] for item in result["hard_failures"]} >= {
            "A_CLASS_EXCEEDED",
            "SHOT_CAPACITY_EXCEEDED",
        }
        preview = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase3-unassigned-preview"},
            json={
                "factory_id": factory_id,
                "plan_id": draft["id"],
                "expected_plan_revision": draft["revision"],
                "rule_revision": draft["rule_revision"],
                "horizon_start": "2026-08-04T08:00:00+08:00",
                "horizon_end": "2026-08-06T20:00:00+08:00",
                "order_ids": [order["id"]],
            },
        )
        assert preview.status_code == 201, preview.text
        assert preview.json()["status"] == "PARTIAL"
        assert preview.json()["assignments"][0]["unassigned_reason_code"] == "NO_ELIGIBLE_MACHINE"
        no_apply = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{preview.json()['id']}/apply",
            json={
                "factory_id": factory_id,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "v2-phase3-no-assignments",
            },
        )
        assert no_apply.status_code == 409


def test_v2_phase3_keeps_locked_task_and_rejects_changed_machine_snapshot(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine_data = machine_payload(factory_id, "V2-P3-LOCKED-32A")
        machine = client.post(
            "/api/injection-scheduling/machines", json=machine_data
        ).json()
        mold_data = mold_payload(factory_id, "V2-P3-LOCKED-MOLD")
        mold = client.post("/api/injection-scheduling/molds", json=mold_data).json()
        order_payloads = [
            {**order_payload(factory_id, f"V2-P3-LOCKED-{index}"), "mold_id": mold["id"]}
            for index in (1, 2)
        ]
        orders = [
            client.post("/api/injection-scheduling/orders", json=item).json()
            for item in order_payloads
        ]
        draft = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        locked_payload = task_payload(
            factory_id, draft["revision"], machine["id"], orders[0]["id"], 1
        )
        locked_payload.update(
            mold_id=mold["id"],
            planned_start="2026-08-04T08:00:00",
            planned_finish="2026-08-04T10:00:00",
            locked=True,
            manual_override_reason="主管锁定当前生产准备",
        )
        plan_response = client.post(
            f"/api/injection-scheduling/plans/{draft['id']}/tasks",
            json=locked_payload,
        )
        assert plan_response.status_code == 201, plan_response.text
        plan = plan_response.json()
        locked_task = plan["tasks"][0]
        preview = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase3-locked-preview"},
            json={
                "factory_id": factory_id,
                "plan_id": plan["id"],
                "expected_plan_revision": plan["revision"],
                "rule_revision": plan["rule_revision"],
                "horizon_start": "2026-08-04T08:00:00+08:00",
                "horizon_end": "2026-08-10T20:00:00+08:00",
                "order_ids": [orders[1]["id"]],
            },
        )
        assert preview.status_code == 201, preview.text
        preview_data = preview.json()
        assert preview_data["summary"]["frozen_task_count"] == 1
        assert preview_data["assignments"][0]["planned_start"] >= locked_task["planned_finish"]

        changed_machine_payload = {
            **machine_data,
            "expected_revision": machine["revision"],
            "status": "maintenance",
        }
        changed_machine = client.put(
            f"/api/injection-scheduling/machines/{machine['id']}",
            json=changed_machine_payload,
        )
        assert changed_machine.status_code == 200, changed_machine.text
        rejected = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{preview_data['id']}/apply",
            json={
                "factory_id": factory_id,
                "expected_plan_revision": plan["revision"],
                "expected_rule_revision": plan["rule_revision"],
                "request_id": "v2-phase3-snapshot-changed",
            },
        )
        assert rejected.status_code == 409
        assert "预览输入已变化" in rejected.json()["detail"]["message"]
        current = client.get(
            "/api/injection-scheduling/plans/current",
            params={"factory_id": factory_id},
        ).json()["plan"]
        current_locked = next(item for item in current["tasks"] if item["id"] == locked_task["id"])
        assert current_locked["machine_id"] == locked_task["machine_id"]
        assert current_locked["sequence_no"] == locked_task["sequence_no"]
        assert current_locked["planned_start"] == locked_task["planned_start"]
        assert current_locked["planned_finish"] == locked_task["planned_finish"]


def test_v2_phase3_local_improvement_batches_same_mold_deterministically():
    from types import SimpleNamespace

    from app.services.injection_scheduling_scheduler.heuristic import (
        _locally_batch_orders,
    )

    def order(order_id: str, order_no: str, mold_id: str):
        return SimpleNamespace(
            id=order_id,
            order_no=order_no,
            mold_id=mold_id,
            delivery_due_date="2026-08-08",
            delivery_slack_days=4,
            priority_code="NORMAL",
        )

    orders = [
        order("order-a1", "A-001", "mold-a"),
        order("order-b1", "B-001", "mold-b"),
        order("order-a2", "C-001", "mold-a"),
    ]
    molds = {
        "mold-a": SimpleNamespace(mold_no="MOLD-A"),
        "mold-b": SimpleNamespace(mold_no="MOLD-B"),
    }

    first, first_moves = _locally_batch_orders(orders, molds)
    second, second_moves = _locally_batch_orders(orders, molds)

    assert [item.id for item in first] == ["order-a1", "order-a2", "order-b1"]
    assert [item.id for item in second] == [item.id for item in first]
    assert first_moves == second_moves == 2


def test_v2_phase3_manual_append_uses_shared_projection_and_stale_guard(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "V2-P3-MANUAL-32A"),
        ).json()
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(factory_id, "V2-P3-MANUAL-MOLD"),
        ).json()
        order_data = order_payload(factory_id, "V2-P3-MANUAL-ORDER", 100)
        order_data["mold_id"] = mold["id"]
        order = client.post(
            "/api/injection-scheduling/orders",
            json=order_data,
        ).json()
        plan = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-04",
            },
        ).json()
        preview_payload = {
            "factory_id": factory_id,
            "order_id": order["id"],
            "machine_id": machine["id"],
            "expected_plan_revision": plan["revision"],
            "expected_order_revision": order["revision"],
            "expected_rule_revision": plan["rule_revision"],
        }
        preview = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/manual-append/preview",
            json=preview_payload,
        )
        assert preview.status_code == 200, preview.text
        preview_data = preview.json()
        assert preview_data["decision"] == "PASS"
        assert preview_data["planned_quantity"] == 90
        assert preview_data["calculation"]["outstanding_quantity"] == 90
        assert preview_data["calculation"]["estimated_remaining_shifts"] == 3
        assert preview_data["calculation"]["production_minutes"] == 135
        assert preview_data["calculation"]["calculation_version"] == (
            "injection-scheduling-calculation-v2"
        )
        assert preview_data["calculation"]["speed_source"] == "RULE_DEFAULT"
        assert {item["code"] for item in preview_data["warnings"]} >= {
            "SPEED_MODEL_MISSING"
        }
        assert len(preview_data["input_fingerprint"]) == 64

        stale = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/manual-append/confirm",
            json={
                **preview_payload,
                "request_id": "manual-append-stale-001",
                "expected_input_fingerprint": "0" * 64,
                "override_reason": "",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "MANUAL_APPEND_PREVIEW_STALE"

        confirmed = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/manual-append/confirm",
            json={
                **preview_payload,
                "request_id": "manual-append-confirm-001",
                "expected_input_fingerprint": preview_data["input_fingerprint"],
                "override_reason": "",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()
        assert result["plan_revision"] == plan["revision"] + 1
        assert result["task"]["mold_id"] == mold["id"]
        assert result["task"]["origin"] == "manual_append"
        assert result["task"]["allocated_quantity"] == 90
        assert result["task"]["production_minutes"] == 135
        assert result["task"]["manual_adjusted"] is True

        duplicate = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/manual-append/preview",
            json={
                **preview_payload,
                "expected_plan_revision": result["plan_revision"],
                "expected_order_revision": order["revision"] + 1,
            },
        )
        assert duplicate.status_code == 409
        assert "BACKLOG" in duplicate.json()["detail"]


def test_v2_phase3_manual_append_advances_after_zero_sequence(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id = "huaxing"
        machine = client.post(
            "/api/injection-scheduling/machines",
            json=machine_payload(factory_id, "V2-P3-SEQUENCE-32A"),
        ).json()
        mold = client.post(
            "/api/injection-scheduling/molds",
            json=mold_payload(factory_id, "V2-P3-SEQUENCE-MOLD"),
        ).json()
        first_payload = order_payload(factory_id, "V2-P3-SEQUENCE-FIRST", 100)
        first_payload["mold_id"] = mold["id"]
        first = client.post(
            "/api/injection-scheduling/orders", json=first_payload
        ).json()
        second_payload = order_payload(factory_id, "V2-P3-SEQUENCE-SECOND", 80)
        second_payload["mold_id"] = mold["id"]
        second = client.post(
            "/api/injection-scheduling/orders", json=second_payload
        ).json()
        plan = client.post(
            "/api/injection-scheduling/plans/drafts",
            json={
                "factory_id": factory_id,
                "expected_revision": 0,
                "business_date": "2026-08-01",
            },
        ).json()
        with_first = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/tasks",
            json=task_payload(factory_id, plan["revision"], machine["id"], first["id"], 0),
        )
        assert with_first.status_code == 201, with_first.text
        current_plan = with_first.json()
        preview = client.post(
            f"/api/injection-scheduling/plans/{plan['id']}/manual-append/preview",
            json={
                "factory_id": factory_id,
                "order_id": second["id"],
                "machine_id": machine["id"],
                "expected_plan_revision": current_plan["revision"],
                "expected_order_revision": second["revision"],
                "expected_rule_revision": current_plan["rule_revision"],
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["sequence_no"] == 1
