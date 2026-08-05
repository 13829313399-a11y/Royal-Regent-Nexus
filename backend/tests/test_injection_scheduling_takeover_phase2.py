from __future__ import annotations

import importlib

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from test_injection_scheduling_phase3_api import make_migrated_client
from test_injection_scheduling_phase4_import import (
    ADMIN_TEST_PASSWORD,
    ensure_user,
    login,
)
from test_injection_scheduling_profile_canonical import _huakang_b_fixture


def _report_payload(factory_id: str, revision: int, request_id: str, quantity: int):
    return {
        "factory_id": factory_id,
        "expected_revision": revision,
        "request_id": request_id,
        "business_date": "2026-08-05",
        "shift_code": "DAY",
        "quantity_mode": "INCREMENTAL",
        "reported_quantity": quantity,
        "shift_target_quantity": 50,
        "downtime_minutes": 0,
        "exception_code": "",
        "exception_detail": "",
        "reported_status": "RUNNING",
    }


def test_phase2_master_approval_takeover_successor_rebase_and_stale_pointer(
    monkeypatch,
):
    factory_id = "huakang-b"
    source = _huakang_b_fixture()
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        preview = client.post(
            "/api/injection-scheduling/imports/preview",
            data={"factory_id": factory_id, "expected_revision": "0"},
            files={
                "file": (
                    "huakang-b-contract.xlsx",
                    source,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers={"x-request-id": "phase2-takeover-preview-0001"},
        )
        assert preview.status_code == 201, preview.text
        batch = preview.json()
        assert batch["batch_state"] == "MASTER_REVIEW_REQUIRED"
        assert batch["summary"]["scheduled_baseline_count"] == 1
        assert batch["summary"]["backlog_count"] == 1
        difference_keys = [
            f"{item['entity_type']}:{item['business_key']}"
            for item in batch["master_differences"]
        ]
        assert difference_keys

        blocked_confirm = client.post(
            f"/api/injection-scheduling/imports/{batch['id']}/confirm",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "expected_plan_revision": 0,
                "request_id": "phase2-takeover-confirm-blocked",
                "confirm_mode": "create_draft",
                "business_date": "2026-08-05",
                "acknowledged_blocking_issue_ids": [],
            },
        )
        assert blocked_confirm.status_code == 409
        assert blocked_confirm.json()["detail"]["code"] == "CANONICAL_BATCH_NOT_READY"

        approved = client.post(
            f"/api/injection-scheduling/imports/{batch['id']}/master-differences/approve",
            json={
                "factory_id": factory_id,
                "expected_revision": 1,
                "request_id": "phase2-master-approval-0001",
                "reason": "核对脱敏样本后批准主数据",
                "differences": difference_keys,
            },
        )
        assert approved.status_code == 200, approved.text
        approved_batch = approved.json()
        assert approved_batch["revision"] == 2
        assert approved_batch["batch_state"] == "PREVIEW_READY"
        assert approved_batch["summary"]["master_difference_count"] == 0
        assert all(
            item["action_type"] in {"CREATE_ORDER", "CREATE_BASELINE_TASK", "CREATE_BACKLOG_ORDER"}
            for item in approved_batch["reconciliation_actions"]
        )
        db_module = importlib.import_module("app.db")
        master_models = importlib.import_module("app.models.injection_scheduling")
        with db_module.SessionLocal() as db:
            machine_codes = list(
                db.scalars(
                    select(master_models.InjectionSchedulingMachine.machine_code)
                ).all()
            )
            mold_nos = list(
                db.scalars(select(master_models.InjectionSchedulingMold.mold_no)).all()
            )
        assert machine_codes, approved_batch["master_differences"]
        assert mold_nos, approved_batch["master_differences"]

        confirm = client.post(
            f"/api/injection-scheduling/imports/{batch['id']}/confirm",
            json={
                "factory_id": factory_id,
                "expected_revision": 2,
                "expected_plan_revision": 0,
                "request_id": "phase2-takeover-confirm-0001",
                "confirm_mode": "create_draft",
                "business_date": "2026-08-05",
                "acknowledged_blocking_issue_ids": [],
                "expected_action_fingerprint": approved_batch["action_fingerprint"],
            },
        )
        assert confirm.status_code == 200, confirm.text
        confirmed = confirm.json()
        plan_id = confirmed["confirmed_plan_id"]
        assert confirmed["result"]["locked_baseline"] is True
        assert confirmed["result"]["backlog_without_tasks"] is True
        assert confirmed["result"]["created_machines"] == 0
        assert confirmed["result"]["created_molds"] == 0

        context = client.get(
            "/api/injection-scheduling/plans/context",
            params={"factory_id": factory_id},
        )
        assert context.status_code == 200, context.text
        draft = context.json()["planning_draft_plan"]
        assert draft["id"] == plan_id
        assert context.json()["execution_published_plan"] is None
        assert len(draft["tasks"]) == 1
        assert draft["tasks"][0]["locked"] is True
        assert draft["tasks"][0]["origin"] == "excel_baseline"
        assert len(draft["plan_order_states"]) == 2
        assert {item["status"] for item in draft["plan_order_states"]} == {
            "SCHEDULED",
            "COMPLETED",
        }
        assert (
            sum(
                item["takeover_source_completed_quantity"]
                for item in draft["plan_order_states"]
            )
            == 70
        )

        ensure_user(
            "phase2-clerk",
            "molding_clerk",
            factory_id=factory_id,
            department="molding",
        )
        client.post("/api/auth/logout")
        login(client, "phase2-clerk")
        locked_edit = client.patch(
            f"/api/injection-scheduling/plans/{plan_id}/tasks/{draft['tasks'][0]['id']}",
            json={
                "factory_id": factory_id,
                "expected_revision": draft["tasks"][0]["revision"],
                "expected_plan_revision": draft["revision"],
                "planned_finish": "2026-08-05T21:00:00",
            },
        )
        assert locked_edit.status_code == 403, locked_edit.text
        assert locked_edit.json()["detail"] == "修改或解除锁定基线需要发布权限"

        client.post("/api/auth/logout")
        login(client, "admin", ADMIN_TEST_PASSWORD)

        publish = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": draft["revision"],
                "request_id": "phase2-publish-0001",
            },
        )
        assert publish.status_code == 200, publish.text
        published = publish.json()["plan"]
        source_task = published["tasks"][0]

        report_one = client.post(
            f"/api/injection-scheduling/tasks/{source_task['id']}/shift-reports",
            json=_report_payload(
                factory_id,
                source_task["revision"],
                "phase2-report-0001",
                5,
            ),
        )
        assert report_one.status_code == 200, report_one.text
        assert report_one.json()["order"]["completed_quantity"] == 15

        rollback = client.post(
            f"/api/injection-scheduling/plans/{plan_id}/rollback",
            json={
                "factory_id": factory_id,
                "expected_revision": published["revision"],
                "request_id": "phase2-successor-0001",
                "business_date": "2026-08-06",
            },
        )
        assert rollback.status_code == 200, rollback.text
        successor = rollback.json()["plan"]
        successor_task = successor["tasks"][0]
        assert successor_task["source_task_id"] == source_task["id"]
        assert successor_task["reported_quantity"] == 5
        assert successor_task["inherited_report_counter"] == 5

        report_two = client.post(
            f"/api/injection-scheduling/tasks/{source_task['id']}/shift-reports",
            json=_report_payload(
                factory_id,
                report_one.json()["task"]["revision"],
                "phase2-report-0002",
                3,
            ),
        )
        assert report_two.status_code == 200, report_two.text

        publish_successor = client.post(
            f"/api/injection-scheduling/plans/{successor['id']}/publish",
            json={
                "factory_id": factory_id,
                "expected_revision": successor["revision"],
                "request_id": "phase2-publish-successor-0001",
            },
        )
        assert publish_successor.status_code == 200, publish_successor.text
        published_successor = publish_successor.json()["plan"]
        rebased_task = published_successor["tasks"][0]
        assert rebased_task["reported_quantity"] == 8
        assert rebased_task["inherited_report_counter"] == 8
        assert rebased_task["execution_status"] == "RUNNING"

        stale_report = client.post(
            f"/api/injection-scheduling/tasks/{source_task['id']}/shift-reports",
            json=_report_payload(
                factory_id,
                report_two.json()["task"]["revision"],
                "phase2-stale-report-0001",
                1,
            ),
        )
        assert stale_report.status_code == 409
        assert stale_report.json()["detail"] == {
            "code": "STALE_EXECUTION_TASK",
            "message": "只能对当前已发布计划回报生产数据",
            "stale_task_id": source_task["id"],
            "successor_task_id": rebased_task["id"],
        }

        state = next(
            item
            for item in published_successor["plan_order_states"]
            if item["order_id"] == rebased_task["order_id"]
        )
        adjustment = client.post(
            "/api/injection-scheduling/progress-adjustments",
            json={
                "factory_id": factory_id,
                "plan_id": published_successor["id"],
                "order_id": state["order_id"],
                "task_id": rebased_task["id"],
                "expected_state_revision": state["revision"],
                "signed_quantity": -1,
                "reason": "主管复核修正重复计数",
                "request_id": "phase2-progress-adjust-0001",
            },
        )
        assert adjustment.status_code == 200, adjustment.text
        assert adjustment.json()["state"]["completed_quantity"] == 17
        replay = client.post(
            "/api/injection-scheduling/progress-adjustments",
            json={
                "factory_id": factory_id,
                "plan_id": published_successor["id"],
                "order_id": state["order_id"],
                "task_id": rebased_task["id"],
                "expected_state_revision": state["revision"],
                "signed_quantity": -1,
                "reason": "主管复核修正重复计数",
                "request_id": "phase2-progress-adjust-0001",
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True

        db_module = importlib.import_module("app.db")
        execution_models = importlib.import_module(
            "app.models.injection_scheduling_execution"
        )
        with db_module.SessionLocal() as db:
            adjustment_row = db.scalar(
                select(execution_models.InjectionSchedulingProgressAdjustment).where(
                    execution_models.InjectionSchedulingProgressAdjustment.request_id
                    == "phase2-progress-adjust-0001"
                )
            )
            adjustment_row.reason = "禁止修改"
            try:
                db.commit()
            except SQLAlchemyError as exc:  # SQLite trigger is the contract.
                assert "append-only" in str(exc)
                db.rollback()
            else:  # pragma: no cover - guard failure should be loud
                raise AssertionError("progress adjustment append-only guard did not fire")
