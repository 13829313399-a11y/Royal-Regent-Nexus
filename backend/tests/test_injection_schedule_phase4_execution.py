import importlib
import json
from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.injection_schedule_phase4_engine import (
    choose_earliest_eligible_machine,
    normalize_priority_code,
    plan_lane_locally,
    prioritize_auto_orders,
)
from test_injection_schedule_phase3_recommendations import (
    configured_rules,
    create_machine,
    create_mold,
    create_order,
    login_admin,
    make_client,
)


def test_phase4_engine_is_deterministic_pass_only_and_preserves_barriers():
    assert [
        normalize_priority_code(value)
        for value in ("P0", "P1", "P2", "P3", "特急▲", "▲", "待通知")
    ] == ["P0", "P1", "P2", "P3", "P0", "P1", "P3"]
    orders = [
        {
            "id": f"O-{index:04d}",
            "priority_flag": (
                "P0"
                if index % 4 == 0
                else "P1"
                if index % 4 == 1
                else "P2"
                if index % 4 == 2
                else "P3"
            ),
            "delivery_due_date": f"2026-08-{(index % 28) + 1:02d}",
            "downstream_urgency": (index % 10) / 10,
            "outstanding_qty": 100 + index,
        }
        for index in range(1_500)
    ]
    started = perf_counter()
    first = prioritize_auto_orders(orders)
    second = prioritize_auto_orders(reversed(orders))
    assert [item["id"] for item in first] == [item["id"] for item in second]
    assert first[0]["priority_flag"] == "P0"
    first_priority_positions = {
        code: next(
            index
            for index, item in enumerate(first)
            if item["priority_flag"] == code
        )
        for code in ("P0", "P1", "P2", "P3")
    }
    assert list(first_priority_positions.values()) == sorted(
        first_priority_positions.values()
    )
    candidates = [
        {
            "rank": index + 1,
            "machine_id": f"M-{index:02d}",
            "target_index": 0,
            "status": "eligible",
            "eligible": True,
            "hard_constraints": [{"status": "pass"}],
        }
        for index in range(76)
    ]
    selected = [
        choose_earliest_eligible_machine(candidates)["machine_id"]
        for _ in range(1_500)
    ]
    assert set(selected) == {"M-00"}
    assert perf_counter() - started < 10.0

    candidate = choose_earliest_eligible_machine(
        [
            {
                "rank": None,
                "machine_id": "M-UNKNOWN",
                "target_index": 0,
                "status": "manual_review",
                "eligible": False,
                "hard_constraints": [{"status": "unknown"}],
            },
            {
                "rank": 1,
                "machine_id": "M-FAIL",
                "target_index": 0,
                "status": "eligible",
                "eligible": True,
                "hard_constraints": [{"status": "fail"}],
            },
            {
                "rank": 2,
                "machine_id": "M-PASS",
                "target_index": 0,
                "status": "eligible",
                "eligible": True,
                "hard_constraints": [{"status": "pass"}],
            },
        ]
    )
    assert candidate is not None
    assert candidate["machine_id"] == "M-PASS"

    planned = plan_lane_locally(
        [
            {
                "id": "locked",
                "planned_start_at": "2026-07-25 08:00:00",
                "planned_finish_at": "2026-07-25 10:00:00",
                "setup_hours": 0,
                "duration_hours": 2,
                "locked": True,
                "protected": False,
                "execution_status": "planned",
            },
            {
                "id": "movable",
                "planned_start_at": "2026-07-25 10:00:00",
                "planned_finish_at": "2026-07-25 12:00:00",
                "setup_hours": 0,
                "duration_hours": 2,
                "locked": False,
                "protected": False,
                "execution_status": "planned",
            },
        ],
        plan_base_at=datetime(2026, 7, 25, 8),
        unavailable_windows=[
            {
                "start_at": "2026-07-25 10:30:00",
                "end_at": "2026-07-25 13:00:00",
            }
        ],
    )
    assert planned[0]["planned_start_at"] == "2026-07-25 08:00:00"
    assert planned[1]["planned_start_at"] == "2026-07-25 13:00:00"
    assert planned[1]["planned_finish_at"] == "2026-07-25 15:00:00"


def test_phase4_priority_code_is_derived_and_database_checked(monkeypatch):
    client = make_client(monkeypatch)
    with client:
        login_admin(client)
        base = "/api/factories/huaxing/injection-schedule"
        order = create_order(
            client,
            base,
            "P4-PRIORITY",
            mold_code="P4-PRIORITY-MOLD",
            color="黑色",
            color_rank=10,
            material="ABS",
        )
        assert order["priority_flag"] == "normal"
        assert order["priority_code"] == "P3"

        urgent = client.patch(
            f"{base}/orders/{order['id']}",
            json={
                "expected_revision": order["revision"],
                "priority_flag": "特急▲",
            },
        )
        assert urgent.status_code == 200, urgent.text
        assert urgent.json()["priority_flag"] == "特急▲"
        assert urgent.json()["priority_code"] == "P0"

        p2 = client.patch(
            f"{base}/orders/{order['id']}",
            json={
                "expected_revision": urgent.json()["revision"],
                "priority_flag": "P2",
            },
        )
        assert p2.status_code == 200, p2.text
        assert p2.json()["priority_code"] == "P2"

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module(
            "app.models.injection_schedule"
        )
        with db_module.SessionLocal() as db:
            stored = db.get(
                schedule_models.InjectionOrderMaster,
                order["id"],
            )
            assert stored is not None
            stored.priority_code = "PX"
            with pytest.raises(IntegrityError) as priority_error:
                db.commit()
            assert "CHECK" in str(priority_error.value).upper()
            db.rollback()


def test_phase4_idempotency_rechecks_after_lock_and_unique_race(monkeypatch):
    phase4 = importlib.import_module(
        "app.services.injection_schedule_phase4"
    )
    schemas = importlib.import_module("app.schemas.injection_schedule")
    actor = SimpleNamespace(id="admin", display_name="管理员")

    correction_payload = (
        schemas.InjectionScheduleShiftActualCorrectionRequest(
            expected_revision=1,
            expected_version_revision=1,
            expected_order_revision=1,
            actual_qty=10,
            reason="并发更正重放",
            request_id="phase4-correction-race",
        )
    )
    correction_hash = phase4.sha256(
        phase4.canonical_json(
            correction_payload.model_dump()
        ).encode("utf-8")
    ).hexdigest()
    correction_ledger = SimpleNamespace(
        actual_id="ACTUAL-RACE",
        payload_hash=correction_hash,
        response_json=json.dumps(
            {
                "actual": {"id": "ACTUAL-RACE", "revision": 2},
                "idempotent_replay": False,
            }
        ),
    )
    correction_lookups = iter([None, correction_ledger])
    monkeypatch.setattr(
        phase4,
        "_load_correction_request",
        lambda *_args, **_kwargs: next(correction_lookups),
    )
    monkeypatch.setattr(
        phase4,
        "_load_actual",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    correction_result = phase4.correct_shift_actual(
        SimpleNamespace(),
        "huaxing",
        "ACTUAL-RACE",
        correction_payload,
        actor,
    )
    assert correction_result["idempotent_replay"] is True
    assert correction_result["actual"]["revision"] == 2

    create_payload = schemas.InjectionScheduleShiftActualCreateRequest(
        version_id="VERSION-RACE",
        task_id="TASK-RACE",
        order_id="ORDER-RACE",
        machine_id="MACHINE-RACE",
        shift_date="2026-07-25",
        shift="day",
        actual_qty=10,
        expected_version_revision=1,
        expected_order_revision=1,
        reason="并发实绩重放",
        request_id="phase4-create-race",
    )
    create_hash = phase4.sha256(
        phase4.canonical_json(
            create_payload.model_dump()
        ).encode("utf-8")
    ).hexdigest()
    created_actual = SimpleNamespace(payload_hash=create_hash)
    actual_lookups = iter([None, created_actual])
    monkeypatch.setattr(
        phase4,
        "_load_actual_request",
        lambda *_args, **_kwargs: next(actual_lookups),
    )
    monkeypatch.setattr(
        phase4,
        "load_version",
        lambda *_args, **_kwargs: SimpleNamespace(revision=1),
    )
    monkeypatch.setattr(
        phase4,
        "_actual_response",
        lambda *_args, idempotent_replay: {
            "idempotent_replay": idempotent_replay,
        },
    )
    create_result = phase4.create_shift_actual(
        SimpleNamespace(),
        "huaxing",
        create_payload,
        actor,
    )
    assert create_result == {"idempotent_replay": True}

    class UniqueRaceDb:
        def __init__(self):
            self.rolled_back = False

        def add(self, _value):
            return None

        def flush(self):
            raise IntegrityError(
                "insert",
                {},
                Exception("duplicate request id"),
            )

        def rollback(self):
            self.rolled_back = True

    race_db = UniqueRaceDb()
    monkeypatch.setattr(phase4, "version_summary", lambda *_args: {})
    monkeypatch.setattr(
        phase4,
        "build_version_data_hash",
        lambda *_args: "d" * 64,
    )
    monkeypatch.setattr(phase4, "add_audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        phase4,
        "_load_replan_replay",
        lambda *_args, **_kwargs: {"replayed": True},
    )
    replan_result = phase4._finish_replan(
        race_db,
        SimpleNamespace(factory_id="huaxing", id="SOURCE", revision=1),
        SimpleNamespace(id="TARGET", revision=1),
        trigger_type="auto_draft",
        context_hash="e" * 64,
        request_id="phase4-replan-race",
        reason="并发重排重放",
        affected_machine_ids=set(),
        affected_order_ids=set(),
        affected_task_ids=set(),
        impact={},
        actor=actor,
        ip_address="",
        dry_run=False,
    )
    assert race_db.rolled_back is True
    assert replan_result == {"replayed": True}


def test_phase4_auto_draft_replan_actual_idempotency_and_cas(monkeypatch):
    client = make_client(monkeypatch)
    with client:
        login_admin(client)
        base = "/api/factories/huaxing/injection-schedule"
        configured_rules(client, base)
        machine = create_machine(client, base, "P4-01")
        create_mold(client, base, "P4-MOLD", material="ABS")
        order = create_order(
            client,
            base,
            "P4-ORDER",
            mold_code="P4-MOLD",
            color="浅灰",
            color_rank=2,
            material="ABS",
        )
        source_response = client.post(
            f"{base}/versions",
            json={
                "name": "Phase4 源版本",
                "business_date": "2026-07-25",
                "plan_base_at": "2026-07-25 08:00:00",
            },
        )
        assert source_response.status_code == 201, source_response.text
        source = source_response.json()

        auto_payload = {
            "expected_revision": 1,
            "reason": "生成 Phase4 自动排程草稿",
            "order_ids": [order["id"]],
            "request_id": "phase4-auto-1",
        }
        versions_before_preview = client.get(f"{base}/versions").json()
        audit_before_preview = client.get(f"{base}/audit").json()
        preview = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-preview",
                "dry_run": True,
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["run"]["status"] == "previewed"
        assert client.get(f"{base}/versions").json() == versions_before_preview
        assert client.get(f"{base}/audit").json() == audit_before_preview
        invalid_horizon = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-invalid-horizon",
                "planning_horizon_end_at": source["plan_base_at"],
                "dry_run": True,
            },
        )
        assert invalid_horizon.status_code == 422
        assert (
            invalid_horizon.json()["detail"]["code"]
            == "invalid_planning_horizon"
        )
        stale_context = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-stale-context",
                "expected_context_hash": "0" * 64,
            },
        )
        assert stale_context.status_code == 409
        stale_revision = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-stale-revision",
                "expected_revision": 2,
            },
        )
        assert stale_revision.status_code == 409
        assert client.get(f"{base}/versions").json() == versions_before_preview
        changed_machine = client.patch(
            f"{base}/machines/{machine['id']}",
            json={
                "expected_revision": machine["revision"],
                "machine_name": "Phase4 依赖哈希变更机台",
            },
        )
        assert changed_machine.status_code == 200, changed_machine.text
        dependency_changed = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-dependency-changed",
                "expected_context_hash": preview.json()["run"][
                    "context_hash"
                ],
            },
        )
        assert dependency_changed.status_code == 409
        assert (
            dependency_changed.json()["detail"]["code"]
            == "replan_context_changed"
        )
        refreshed_preview = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-refreshed-preview",
                "dry_run": True,
            },
        )
        assert refreshed_preview.status_code == 200, refreshed_preview.text
        assert (
            refreshed_preview.json()["run"]["context_hash"]
            != preview.json()["run"]["context_hash"]
        )
        repeated_preview = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "request_id": "phase4-auto-repeated-preview",
                "dry_run": True,
            },
        )
        assert repeated_preview.status_code == 200, repeated_preview.text
        assert (
            repeated_preview.json()["run"]["context_hash"]
            == refreshed_preview.json()["run"]["context_hash"]
        )
        refreshed_task = refreshed_preview.json()["tasks"][0]
        repeated_task = repeated_preview.json()["tasks"][0]
        for key in (
            "machine_id",
            "sequence_no",
            "planned_start_at",
            "planned_finish_at",
            "setup_hours",
            "duration_hours",
            "recommendation_score",
            "score_breakdown",
            "constraint_snapshot",
            "recommendation_context_hash",
        ):
            assert repeated_task[key] == refreshed_task[key]
        auto_payload["expected_context_hash"] = refreshed_preview.json()["run"][
            "context_hash"
        ]
        auto_response = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json=auto_payload,
        )
        assert auto_response.status_code == 200, auto_response.text
        auto = auto_response.json()
        assert auto["run"]["status"] == "applied"
        assert auto["run"]["impact"]["scheduled_order_count"] == 1
        assert auto["version"]["base_version_id"] == source["id"]
        assert auto["version"]["status"] == "draft"
        assert len(auto["tasks"]) == 1
        task = auto["tasks"][0]
        assert task["source"] == "auto"
        assert task["execution_status"] == "planned"
        assert task["protected"] is False
        planned_start = datetime.fromisoformat(task["planned_start_at"])
        planned_finish = datetime.fromisoformat(task["planned_finish_at"])
        assert planned_finish > planned_start
        assert task["duration_hours"] > 0
        assert task["constraint_snapshot"]
        assert {
            item["status"] for item in task["constraint_snapshot"]
        } == {"pass"}

        replay = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json=auto_payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["run"]["id"] == auto["run"]["id"]
        conflict = client.post(
            f"{base}/versions/{source['id']}/auto-draft",
            json={
                **auto_payload,
                "reason": "同键不同请求",
                "expected_context_hash": "",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"

        urgent_order = create_order(
            client,
            base,
            "P4-URGENT",
            mold_code="P4-MOLD",
            color="深灰",
            color_rank=8,
            material="ABS",
        )
        versions_before_urgent_preview = client.get(f"{base}/versions").json()
        audit_before_urgent_preview = client.get(f"{base}/audit").json()
        urgent_payload = {
            "expected_revision": auto["version"]["revision"],
            "trigger": {
                "type": "urgent_order",
                "order_id": urgent_order["id"],
                "reason": "客户急单",
            },
            "scope": {
                "max_affected_machines": 1,
                "max_affected_tasks": 10,
            },
            "reason": "急单局部插入预览",
            "request_id": "phase4-urgent-apply",
        }
        urgent_preview = client.post(
            f"{base}/versions/{auto['version']['id']}/replan",
            json={
                **urgent_payload,
                "request_id": "phase4-urgent-preview",
                "dry_run": True,
            },
        )
        assert urgent_preview.status_code == 200, urgent_preview.text
        assert urgent_preview.json()["run"]["status"] == "previewed"
        assert (
            client.get(f"{base}/versions").json()
            == versions_before_urgent_preview
        )
        assert client.get(f"{base}/audit").json() == audit_before_urgent_preview
        urgent_payload["expected_context_hash"] = urgent_preview.json()["run"][
            "context_hash"
        ]
        source_before_urgent = client.get(
            f"{base}/versions/{auto['version']['id']}"
        ).json()
        urgent_apply = client.post(
            f"{base}/versions/{auto['version']['id']}/replan",
            json=urgent_payload,
        )
        assert urgent_apply.status_code == 200, urgent_apply.text
        urgent_body = urgent_apply.json()
        assert urgent_body["version"]["base_version_id"] == auto["version"]["id"]
        assert urgent_body["affected_machine_ids"] == [machine["id"]]
        assert len(urgent_body["affected_task_ids"]) == 2
        urgent_task = next(
            item
            for item in urgent_body["tasks"]
            if item["order_id"] == urgent_order["id"]
        )
        shifted_task = next(
            item
            for item in urgent_body["tasks"]
            if item["order_id"] == order["id"]
        )
        assert urgent_task["sequence_no"] == 0
        assert shifted_task["sequence_no"] == 1
        assert shifted_task["planned_finish_at"] != task["planned_finish_at"]
        assert {
            row["task_id"]
            for row in urgent_body["run"]["impact"]["rows"]
        } == set(urgent_body["affected_task_ids"])
        assert (
            client.get(f"{base}/versions/{auto['version']['id']}").json()
            == source_before_urgent
        )

        downtime_payload = {
            "expected_revision": auto["version"]["revision"],
            "trigger": {
                "type": "machine_downtime",
                "machine_id": machine["id"],
                "start_at": "2026-07-25 10:00:00",
                "end_at": "2026-07-25 12:00:00",
                "reason": "设备临时检修",
            },
            "scope": {
                "max_affected_machines": 1,
                "max_affected_tasks": 10,
            },
            "reason": "设备停机后仅重排受影响机台",
            "request_id": "phase4-downtime-1",
        }
        versions_before_downtime_preview = client.get(f"{base}/versions").json()
        audit_before_downtime_preview = client.get(f"{base}/audit").json()
        downtime_preview = client.post(
            f"{base}/versions/{auto['version']['id']}/replan",
            json={
                **downtime_payload,
                "request_id": "phase4-downtime-preview",
                "dry_run": True,
            },
        )
        assert downtime_preview.status_code == 200, downtime_preview.text
        assert (
            client.get(f"{base}/versions").json()
            == versions_before_downtime_preview
        )
        assert (
            client.get(f"{base}/audit").json()
            == audit_before_downtime_preview
        )
        downtime_payload["expected_context_hash"] = downtime_preview.json()[
            "run"
        ]["context_hash"]
        downtime = client.post(
            f"{base}/versions/{auto['version']['id']}/replan",
            json=downtime_payload,
        )
        assert downtime.status_code == 200, downtime.text
        downtime_body = downtime.json()
        assert downtime_body["run"]["trigger_type"] == "machine_downtime"
        assert downtime_body["affected_machine_ids"] == [machine["id"]]
        assert (
            downtime_body["tasks"][0]["planned_finish_at"]
            != task["planned_finish_at"]
        )

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module(
            "app.models.injection_schedule"
        )
        with db_module.SessionLocal() as db:
            persisted_urgent_run = db.get(
                schedule_models.InjectionScheduleReplanRun,
                urgent_body["run"]["id"],
            )
            assert persisted_urgent_run is not None
            assert set(
                json.loads(persisted_urgent_run.affected_task_ids_json)
            ) == set(urgent_body["affected_task_ids"])
            published_version = db.get(
                schedule_models.InjectionScheduleVersion,
                auto["version"]["id"],
            )
            assert published_version is not None
            published_version.status = "published"
            published_version.published_by = "admin"
            published_version.published_by_name = "管理员"
            published_version.published_at = "2026-07-25 12:00:00"
            factory_state = db.get(
                schedule_models.InjectionScheduleFactoryState,
                "huaxing",
            )
            assert factory_state is not None
            factory_state.current_published_version_id = published_version.id
            db.commit()
        published_source_before_actual = client.get(
            f"{base}/versions/{auto['version']['id']}"
        ).json()
        assert published_source_before_actual["version"]["status"] == "published"

        order_before_actual = next(
            item
            for item in client.get(f"{base}/orders").json()
            if item["id"] == order["id"]
        )
        actual_payload = {
            "version_id": auto["version"]["id"],
            "task_id": task["id"],
            "order_id": order["id"],
            "machine_id": machine["id"],
            "shift_date": "2026-07-25",
            "shift": "day",
            "source": "workbook",
            "legacy_shift_code": "A",
            "target_qty": 500,
            "actual_qty": 400,
            "expected_version_revision": auto["version"]["revision"],
            "expected_order_revision": order_before_actual["revision"],
            "reason": "回写 A 班白班实绩",
            "request_id": "phase4-actual-1",
        }
        blank_actual_request = client.post(
            f"{base}/actuals",
            json={**actual_payload, "request_id": "   "},
        )
        assert blank_actual_request.status_code == 422
        actual_response = client.post(f"{base}/actuals", json=actual_payload)
        assert actual_response.status_code == 201, actual_response.text
        actual = actual_response.json()
        assert actual["idempotent_replay"] is False
        assert actual["actual"]["legacy_shift_code"] == "A"
        assert actual["actual"]["variance_qty"] == -100
        assert actual["actual"]["source_version_id"] == auto["version"]["id"]
        assert actual["actual"]["source_task_id"] == task["id"]
        assert actual["actual"]["lineage_sequence"] == 1
        assert actual["updated_order"]["outstanding_qty"] == 600
        assert actual["version"]["status"] == "draft"
        assert actual["version"]["base_version_id"] == auto["version"]["id"]
        assert actual["version"]["id"] != auto["version"]["id"]
        actual_task = next(
            item
            for item in actual["tasks"]
            if item["id"] == actual["actual"]["task_id"]
        )
        assert actual_task["parent_task_id"] == task["id"]
        assert actual_task["execution_status"] == "running"
        assert actual_task["protected"] is True
        assert actual_task["planned_qty"] == 600
        assert (
            client.get(f"{base}/versions/{auto['version']['id']}").json()
            == published_source_before_actual
        )

        actual_replay = client.post(f"{base}/actuals", json=actual_payload)
        assert actual_replay.status_code == 201, actual_replay.text
        assert actual_replay.json()["idempotent_replay"] is True
        assert actual_replay.json()["actual"]["id"] == actual["actual"]["id"]

        duplicate_shift = client.post(
            f"{base}/actuals",
            json={
                **actual_payload,
                "version_id": actual["version"]["id"],
                "task_id": actual_task["id"],
                "expected_version_revision": actual["version"]["revision"],
                "expected_order_revision": actual["updated_order"]["revision"],
                "request_id": "phase4-actual-duplicate-shift",
            },
        )
        assert duplicate_shift.status_code == 409
        assert (
            duplicate_shift.json()["detail"]["code"]
            == "actual_shift_already_recorded"
        )

        grandchild_payload = {
            "expected_revision": actual["version"]["revision"],
            "trigger": {
                "type": "machine_downtime",
                "machine_id": machine["id"],
                "start_at": "2026-08-01 00:00:00",
                "end_at": "2026-08-01 01:00:00",
                "reason": "验证孙版本追溯",
            },
            "scope": {
                "max_affected_machines": 1,
                "max_affected_tasks": 10,
            },
            "reason": "滚动草稿再生成局部重排孙版本",
            "request_id": "phase4-grandchild-apply",
        }
        grandchild_preview = client.post(
            f"{base}/versions/{actual['version']['id']}/replan",
            json={
                **grandchild_payload,
                "request_id": "phase4-grandchild-preview",
                "dry_run": True,
            },
        )
        assert grandchild_preview.status_code == 200, grandchild_preview.text
        grandchild_payload["expected_context_hash"] = (
            grandchild_preview.json()["run"]["context_hash"]
        )
        grandchild_response = client.post(
            f"{base}/versions/{actual['version']['id']}/replan",
            json=grandchild_payload,
        )
        assert grandchild_response.status_code == 200, grandchild_response.text
        grandchild = grandchild_response.json()
        assert grandchild["version"]["base_version_id"] == actual["version"]["id"]
        grandchild_task = next(
            item
            for item in grandchild["tasks"]
            if item["parent_task_id"] == actual_task["id"]
        )

        night_payload = {
            "version_id": grandchild["version"]["id"],
            "task_id": grandchild_task["id"],
            "order_id": order["id"],
            "machine_id": machine["id"],
            "shift_date": "2026-07-25",
            "shift": "night",
            "source": "workbook",
            "legacy_shift_code": "B",
            "target_qty": 500,
            "actual_qty": 300,
            "expected_version_revision": grandchild["version"]["revision"],
            "expected_order_revision": actual["updated_order"]["revision"],
            "reason": "回写 B 班夜班实绩",
            "request_id": "phase4-actual-2",
        }
        night_response = client.post(f"{base}/actuals", json=night_payload)
        assert night_response.status_code == 201, night_response.text
        night = night_response.json()
        assert night["updated_order"]["produced_qty"] == 700
        assert night["updated_order"]["outstanding_qty"] == 300
        assert night["actual"]["source_version_id"] == auto["version"]["id"]
        assert night["actual"]["source_task_id"] == task["id"]
        assert night["actual"]["lineage_sequence"] == 2
        night_task = next(
            item
            for item in night["tasks"]
            if item["id"] == night["actual"]["task_id"]
        )
        assert night_task["planned_qty"] == 300

        no_longer_latest = client.patch(
            f"{base}/actuals/{actual['actual']['id']}",
            json={
                "expected_revision": 1,
                "expected_version_revision": night["version"]["revision"],
                "expected_order_revision": night["updated_order"]["revision"],
                "actual_qty": 500,
                "reason": "主管核对后更正白班完成数",
                "request_id": "phase4-actual-correction-1",
            },
        )
        assert no_longer_latest.status_code == 409
        assert (
            no_longer_latest.json()["detail"]["code"]
            == "actual_correction_not_latest"
        )
        correction_payload = {
            "expected_revision": 1,
            "expected_version_revision": night["version"]["revision"],
            "expected_order_revision": night["updated_order"]["revision"],
            "actual_qty": 350,
            "reason": "主管核对后更正夜班完成数",
            "request_id": "phase4-actual-correction-2",
        }
        blank_correction_request = client.patch(
            f"{base}/actuals/{night['actual']['id']}",
            json={**correction_payload, "request_id": "   "},
        )
        assert blank_correction_request.status_code == 422
        correction = client.patch(
            f"{base}/actuals/{night['actual']['id']}",
            json=correction_payload,
        )
        assert correction.status_code == 200, correction.text
        corrected = correction.json()
        assert corrected["actual"]["revision"] == 2
        assert corrected["actual"]["correction_count"] == 1
        assert corrected["updated_order"]["produced_qty"] == 750
        assert corrected["updated_order"]["outstanding_qty"] == 250
        second_correction_payload = {
            "expected_revision": corrected["actual"]["revision"],
            "expected_version_revision": corrected["version"]["revision"],
            "expected_order_revision": corrected["updated_order"]["revision"],
            "actual_qty": 325,
            "reason": "主管第二次核对夜班完成数",
            "request_id": "phase4-actual-correction-3",
        }
        second_correction = client.patch(
            f"{base}/actuals/{night['actual']['id']}",
            json=second_correction_payload,
        )
        assert second_correction.status_code == 200, second_correction.text
        corrected_twice = second_correction.json()
        assert corrected_twice["actual"]["revision"] == 3
        assert corrected_twice["actual"]["correction_count"] == 2
        assert corrected_twice["updated_order"]["produced_qty"] == 725
        assert corrected_twice["updated_order"]["outstanding_qty"] == 275

        old_correction_replay = client.patch(
            f"{base}/actuals/{night['actual']['id']}",
            json=correction_payload,
        )
        assert old_correction_replay.status_code == 200
        assert old_correction_replay.json()["idempotent_replay"] is True
        assert old_correction_replay.json()["actual"]["revision"] == 2
        assert old_correction_replay.json()["updated_order"]["produced_qty"] == 750

        cross_actual_request_reuse = client.patch(
            f"{base}/actuals/{actual['actual']['id']}",
            json=second_correction_payload,
        )
        assert cross_actual_request_reuse.status_code == 409
        assert (
            cross_actual_request_reuse.json()["detail"]["code"]
            == "idempotency_key_conflict"
        )
        stale = client.patch(
            f"{base}/actuals/{night['actual']['id']}",
            json={
                "expected_revision": 1,
                "expected_version_revision": corrected_twice["version"][
                    "revision"
                ],
                "expected_order_revision": corrected_twice["updated_order"][
                    "revision"
                ],
                "actual_qty": 550,
                "reason": "过期页面再次更正",
                "request_id": "phase4-actual-correction-stale",
            },
        )
        assert stale.status_code == 409

        cross_factory = client.get(
            "/api/factories/huadeng/injection-schedule/actuals"
        )
        assert cross_factory.status_code == 200
        assert cross_factory.json() == []
        actuals = client.get(
            f"{base}/actuals",
            params={
                "version_id": auto["version"]["id"],
                "date_from": "2026-07-25",
                "date_to": "2026-07-25",
            },
        )
        assert actuals.status_code == 200, actuals.text
        assert {item["id"] for item in actuals.json()} == {
            actual["actual"]["id"],
            night["actual"]["id"],
        }
        assert {
            item["source_version_id"] for item in actuals.json()
        } == {auto["version"]["id"]}
        assert {
            item["source_task_id"] for item in actuals.json()
        } == {task["id"]}
        current_night_actual = next(
            item
            for item in actuals.json()
            if item["id"] == night["actual"]["id"]
        )
        assert current_night_actual["revision"] == 3
        assert current_night_actual["actual_qty"] == 325
        with db_module.SessionLocal() as db:
            rolling_order_tasks = list(
                db.scalars(
                    select(schedule_models.InjectionScheduleTask).where(
                        schedule_models.InjectionScheduleTask.factory_id
                        == "huaxing",
                        schedule_models.InjectionScheduleTask.version_id
                        == corrected_twice["version"]["id"],
                        schedule_models.InjectionScheduleTask.order_id
                        == order["id"],
                    )
                ).all()
            )
            assert rolling_order_tasks
            assert {
                item.order_revision_snapshot
                for item in rolling_order_tasks
            } == {corrected_twice["updated_order"]["revision"]}

            corrections = list(
                db.scalars(
                    select(
                        schedule_models.InjectionScheduleActualCorrection
                    ).where(
                        schedule_models.InjectionScheduleActualCorrection.factory_id
                        == "huaxing",
                        schedule_models.InjectionScheduleActualCorrection.actual_id
                        == night["actual"]["id"],
                    )
                ).all()
            )
            assert {
                item.request_id for item in corrections
            } == {
                "phase4-actual-correction-2",
                "phase4-actual-correction-3",
            }
            for correction_row in corrections:
                response_snapshot = json.loads(
                    correction_row.response_json
                )
                assert response_snapshot["actual"]["revision"] == (
                    correction_row.result_actual_revision
                )
                assert response_snapshot["tasks"]

            duplicate_correction_key = (
                schedule_models.InjectionScheduleActualCorrection(
                    id="IAC-DUPLICATE-REQUEST",
                    factory_id="huaxing",
                    actual_id=night["actual"]["id"],
                    request_id="phase4-actual-correction-2",
                    payload_hash="a" * 64,
                    previous_actual_qty=325,
                    corrected_actual_qty=325,
                    previous_actual_revision=3,
                    result_actual_revision=4,
                    reason="并发重复键验证",
                    response_json='{"idempotent_replay":false}',
                    created_by="admin",
                    created_by_name="管理员",
                    created_at="2026-07-25 23:00:00",
                )
            )
            db.add(duplicate_correction_key)
            with pytest.raises(IntegrityError) as duplicate_request_error:
                db.commit()
            assert "UNIQUE" in str(duplicate_request_error.value).upper()
            db.rollback()

        with db_module.SessionLocal() as db:
            duplicate_correction_revision = (
                schedule_models.InjectionScheduleActualCorrection(
                    id="IAC-DUPLICATE-REVISION",
                    factory_id="huaxing",
                    actual_id=night["actual"]["id"],
                    request_id="phase4-correction-duplicate-revision",
                    payload_hash="d" * 64,
                    previous_actual_qty=350,
                    corrected_actual_qty=325,
                    previous_actual_revision=2,
                    result_actual_revision=3,
                    reason="同一实绩更正序列重复验证",
                    response_json='{"idempotent_replay":false}',
                    created_by="admin",
                    created_by_name="管理员",
                    created_at="2026-07-25 23:05:00",
                )
            )
            db.add(duplicate_correction_revision)
            with pytest.raises(IntegrityError) as duplicate_revision_error:
                db.commit()
            assert "UNIQUE" in str(duplicate_revision_error.value).upper()
            db.rollback()

        def invalid_actual(**overrides):
            values = {
                "id": "ISA-COMPOSITE-FK",
                "factory_id": "huaxing",
                "version_id": grandchild["version"]["id"],
                "task_id": actual_task["id"],
                "source_version_id": auto["version"]["id"],
                "source_task_id": task["id"],
                "lineage_sequence": 90,
                "order_id": order["id"],
                "machine_id": machine["id"],
                "shift_date": "2026-07-31",
                "shift": "day",
                "legacy_shift_code": "A",
                "source": "manual",
                "target_qty": 1,
                "actual_qty": 1,
                "variance_qty": 0,
                "variance_reason": "",
                "produced_baseline_qty": 0,
                "outstanding_qty_before": 1,
                "outstanding_qty_after": 0,
                "shortage_qty": 0,
                "task_planned_qty_before": 1,
                "request_id": "phase4-invalid-composite-current",
                "payload_hash": "b" * 64,
                "projection_json": "[]",
                "revision": 1,
                "correction_count": 0,
                "created_by": "admin",
                "created_by_name": "管理员",
                "created_at": "2026-07-25 23:10:00",
                "corrected_by": "",
                "corrected_by_name": "",
                "corrected_at": "",
                "last_correction_request_id": "",
                "last_correction_payload_hash": "",
            }
            values.update(overrides)
            return schedule_models.InjectionScheduleShiftActual(**values)

        with db_module.SessionLocal() as db:
            db.connection().exec_driver_sql("PRAGMA foreign_keys = ON")
            db.add(invalid_actual())
            with pytest.raises(IntegrityError) as current_pair_error:
                db.commit()
            assert "FOREIGN KEY" in str(current_pair_error.value).upper()
            db.rollback()

        with db_module.SessionLocal() as db:
            db.connection().exec_driver_sql("PRAGMA foreign_keys = ON")
            db.add(
                invalid_actual(
                    id="ISA-COMPOSITE-SOURCE-FK",
                    task_id=grandchild_task["id"],
                    source_version_id=actual["version"]["id"],
                    lineage_sequence=91,
                    shift_date="2026-08-02",
                    request_id="phase4-invalid-composite-source",
                    payload_hash="c" * 64,
                )
            )
            with pytest.raises(IntegrityError) as source_pair_error:
                db.commit()
            assert "FOREIGN KEY" in str(source_pair_error.value).upper()
            db.rollback()


def test_phase4_urgent_replan_pushes_only_movable_suffix(monkeypatch):
    client = make_client(monkeypatch)
    with client:
        login_admin(client)
        base = "/api/factories/huaxing/injection-schedule"
        configured_rules(client, base)
        machine = create_machine(client, base, "P4-SUFFIX-01")
        other_machine = create_machine(
            client,
            base,
            "P4-SUFFIX-02",
            status="maintenance",
        )
        mold = create_mold(client, base, "P4-SUFFIX-MOLD", material="ABS")
        prefix_order = create_order(
            client,
            base,
            "P4-PROTECTED-PREFIX",
            mold_code="P4-SUFFIX-MOLD",
            color="浅灰",
            color_rank=2,
            material="ABS",
        )
        suffix_order = create_order(
            client,
            base,
            "P4-MOVABLE-SUFFIX",
            mold_code="P4-SUFFIX-MOLD",
            color="深灰",
            color_rank=8,
            material="ABS",
        )
        other_order = create_order(
            client,
            base,
            "P4-OTHER-LANE",
            mold_code="P4-SUFFIX-MOLD",
            color="黑色",
            color_rank=10,
            material="ABS",
        )
        urgent_order = create_order(
            client,
            base,
            "P4-UNPLANNED-URGENT",
            mold_code="P4-SUFFIX-MOLD",
            color="白色",
            color_rank=1,
            material="ABS",
        )
        source_response = client.post(
            f"{base}/versions",
            json={
                "name": "Phase4 局部后缀源版本",
                "business_date": "2026-07-25",
                "plan_base_at": "2026-07-25 08:00:00",
            },
        )
        assert source_response.status_code == 201, source_response.text
        source = source_response.json()

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module(
            "app.models.injection_schedule"
        )
        schedule_service = importlib.import_module(
            "app.services.injection_schedule"
        )
        validation_service = importlib.import_module(
            "app.services.injection_schedule_validation"
        )
        excel_service = importlib.import_module(
            "app.services.injection_schedule_excel"
        )
        timestamp = "2026-07-25 08:00:00"

        def seeded_task(
            *,
            task_id: str,
            order: dict,
            target_machine: dict,
            sequence_no: int,
            start_at: str,
            finish_at: str,
            locked: bool,
            execution_status: str = "planned",
            protected: bool = False,
        ):
            return schedule_models.InjectionScheduleTask(
                id=task_id,
                factory_id="huaxing",
                version_id=source["id"],
                order_id=order["id"],
                machine_id=target_machine["id"],
                mold_id=mold["id"],
                sequence_no=sequence_no,
                planned_qty=order["outstanding_qty"],
                planned_start_at=start_at,
                planned_finish_at=finish_at,
                setup_hours=0,
                duration_hours=2,
                locked=locked,
                split_group_id="",
                parent_task_id="",
                order_no_snapshot=order["order_no"],
                product_code_snapshot=order["product_code"],
                product_name_snapshot=order["product_name"],
                delivery_due_date_snapshot=order["delivery_due_date"],
                mold_code_snapshot=mold["mold_code"],
                color_snapshot=order["color"],
                color_rank_snapshot=order["color_rank"],
                material_snapshot=order["material"],
                machine_code_snapshot=target_machine["machine_code"],
                source="manual",
                execution_status=execution_status,
                protected=protected,
                recommendation_score=None,
                score_breakdown_json="[]",
                constraint_snapshot_json="[]",
                recommendation_context_hash="",
                risk_level="normal",
                risk_reasons_json="[]",
                order_revision_snapshot=order["revision"],
                machine_revision_snapshot=target_machine["revision"],
                mold_revision_snapshot=mold["revision"],
                revision=1,
                created_by="admin",
                created_at=timestamp,
                updated_by="admin",
                updated_at=timestamp,
            )

        with db_module.SessionLocal() as db:
            version = db.get(
                schedule_models.InjectionScheduleVersion,
                source["id"],
            )
            assert version is not None
            db.add_all(
                [
                    seeded_task(
                        task_id="P4-PREFIX-TASK",
                        order=prefix_order,
                        target_machine=machine,
                        sequence_no=0,
                        start_at="2026-07-25 08:00:00",
                        finish_at="2026-07-25 10:00:00",
                        locked=True,
                        execution_status="running",
                        protected=True,
                    ),
                    seeded_task(
                        task_id="P4-SUFFIX-TASK",
                        order=suffix_order,
                        target_machine=machine,
                        sequence_no=1,
                        start_at="2026-07-25 10:00:00",
                        finish_at="2026-07-25 12:00:00",
                        locked=False,
                    ),
                    seeded_task(
                        task_id="P4-OTHER-TASK",
                        order=other_order,
                        target_machine=other_machine,
                        sequence_no=0,
                        start_at="2026-07-25 08:00:00",
                        finish_at="2026-07-25 10:00:00",
                        locked=True,
                    ),
                ]
            )
            db.flush()
            version.summary_json = excel_service.canonical_json(
                schedule_service.version_summary(db, version)
            )
            version.data_hash = validation_service.build_version_data_hash(
                db,
                version,
            )
            db.commit()

        source_before = client.get(
            f"{base}/versions/{source['id']}"
        ).json()
        payload = {
            "expected_revision": source["revision"],
            "trigger": {
                "type": "urgent_order",
                "order_id": urgent_order["id"],
                "reason": "客户临时急单",
            },
            "scope": {
                "max_affected_machines": 1,
                "max_affected_tasks": 2,
            },
            "reason": "只移动执行屏障后的可移动任务",
            "request_id": "phase4-suffix-apply",
        }
        preview = client.post(
            f"{base}/versions/{source['id']}/replan",
            json={
                **payload,
                "request_id": "phase4-suffix-preview",
                "dry_run": True,
            },
        )
        assert preview.status_code == 200, preview.text
        payload["expected_context_hash"] = preview.json()["run"][
            "context_hash"
        ]
        applied = client.post(
            f"{base}/versions/{source['id']}/replan",
            json=payload,
        )
        assert applied.status_code == 200, applied.text
        body = applied.json()
        result_prefix = next(
            item
            for item in body["tasks"]
            if item["order_id"] == prefix_order["id"]
        )
        result_urgent = next(
            item
            for item in body["tasks"]
            if item["order_id"] == urgent_order["id"]
        )
        result_suffix = next(
            item
            for item in body["tasks"]
            if item["order_id"] == suffix_order["id"]
        )
        result_other = next(
            item
            for item in body["tasks"]
            if item["order_id"] == other_order["id"]
        )
        assert result_prefix["sequence_no"] == 0
        assert result_prefix["planned_start_at"] == "2026-07-25 08:00:00"
        assert result_prefix["planned_finish_at"] == "2026-07-25 10:00:00"
        assert result_urgent["sequence_no"] == 1
        assert result_suffix["sequence_no"] == 2
        assert result_suffix["planned_start_at"] != "2026-07-25 10:00:00"
        assert result_other["planned_start_at"] == "2026-07-25 08:00:00"
        assert result_other["planned_finish_at"] == "2026-07-25 10:00:00"
        assert body["affected_machine_ids"] == [machine["id"]]
        assert set(body["affected_task_ids"]) == {
            result_urgent["id"],
            result_suffix["id"],
        }
        assert {
            row["task_id"] for row in body["run"]["impact"]["rows"]
        } == set(body["affected_task_ids"])
        assert (
            client.get(f"{base}/versions/{source['id']}").json()
            == source_before
        )


def test_phase4_service_auto_draft_76_by_1500_is_bounded_and_zero_write(
    monkeypatch,
):
    client = make_client(monkeypatch)
    with client:
        login_admin(client)
        base = "/api/factories/huaxing/injection-schedule"
        rules = configured_rules(client, base)

        db_module = importlib.import_module("app.db")
        schedule_models = importlib.import_module(
            "app.models.injection_schedule"
        )
        schedule_service = importlib.import_module(
            "app.services.injection_schedule_phase4"
        )
        schedule_schemas = importlib.import_module(
            "app.schemas.injection_schedule"
        )
        excel_service = importlib.import_module(
            "app.services.injection_schedule_excel"
        )
        timestamp = "2026-07-25 08:00:00"
        machines = [
            schedule_models.InjectionMachineMaster(
                id=f"P4-PERF-M-{index:03d}",
                factory_id="huaxing",
                machine_code=f"P4-PERF-{index:03d}",
                machine_name=f"性能机台 {index:03d}",
                workshop="new" if index >= 39 else "old",
                machine_class="160T",
                tonnage_t=160,
                process_type="standard",
                screw_type="standard",
                robot_type="three-axis",
                fixture_type="standard",
                max_shot_weight_g=1000,
                tie_bar_x_mm=800,
                tie_bar_y_mm=800,
                mold_thickness_min_mm=100,
                mold_thickness_max_mm=600,
                opening_stroke_mm=700,
                ejector_stroke_mm=200,
                status="available",
                available_at="",
                capabilities_json='["hot-runner"]',
                material_rules_json='["ABS"]',
                quality_status="verified",
                provenance_json="{}",
                source_batch_id="",
                revision=1,
                created_by="admin",
                created_at=timestamp,
                updated_by="admin",
                updated_at=timestamp,
            )
            for index in range(76)
        ]
        mold = schedule_models.InjectionMoldMaster(
            id="P4-PERF-MOLD-ID",
            factory_id="huaxing",
            mold_code="P4-PERF-MOLD",
            normalized_mold_code="P4-PERF-MOLD",
            mold_name="性能测试模具",
            machine_class="160T",
            robot_type="three-axis",
            fixture_type="standard",
            length_mm=400,
            width_mm=300,
            height_mm=250,
            mold_weight_kg=500,
            gross_shot_weight_g=100,
            mold_thickness_mm=250,
            required_opening_stroke_mm=300,
            required_screw_type="standard",
            cavities=1,
            cycle_seconds=30,
            required_capabilities_json='["hot-runner"]',
            material_rules_json='["ABS"]',
            quality_status="verified",
            provenance_json="{}",
            source_batch_id="",
            revision=1,
            created_by="admin",
            created_at=timestamp,
            updated_by="admin",
            updated_at=timestamp,
        )
        orders = [
            schedule_models.InjectionOrderMaster(
                id=f"P4-PERF-O-{index:04d}",
                factory_id="huaxing",
                natural_key=f"P4-PERF-NK-{index:04d}",
                order_no=f"P4-PERF-{index:04d}",
                product_code=f"P4-P-{index:04d}",
                product_name=f"性能订单 {index:04d}",
                mold_code="P4-PERF-MOLD",
                color="浅灰",
                pigment="GY",
                material="ABS",
                machine_class="160T",
                order_qty=1000,
                produced_qty=0,
                outstanding_qty=1000,
                daily_target_qty=24000,
                delivery_due_date="2026-12-31",
                priority_flag=("P0", "P1", "P2", "P3")[index % 4],
                priority_code=("P0", "P1", "P2", "P3")[index % 4],
                color_rank=2,
                downstream_urgency=0.5,
                warehouse_buffer_hours=12,
                downstream_buffer_hours=12,
                special_handling_reason="",
                status="open",
                imported_assigned_machine_code="",
                imported_plan_start_at="",
                imported_plan_finish_at="",
                source_sheet="performance",
                source_row=index + 1,
                source_batch_id="",
                source_values_json="{}",
                quality_status="verified",
                provenance_json="{}",
                revision=1,
                created_by="admin",
                created_at=timestamp,
                updated_by="admin",
                updated_at=timestamp,
            )
            for index in range(1_500)
        ]
        with db_module.SessionLocal() as db:
            db.add_all([*machines, mold, *orders])
            db.commit()

        source_response = client.post(
            f"{base}/versions",
            json={
                "name": "Phase4 76x1500 性能源版本",
                "business_date": "2026-07-25",
                "plan_base_at": "2026-07-25 08:00:00",
            },
        )
        assert source_response.status_code == 201, source_response.text
        source = source_response.json()
        assert rules["availability_calendar_verified_through"]

        actor = SimpleNamespace(id="admin", display_name="管理员")
        request = schedule_schemas.InjectionScheduleAutoDraftRequest(
            expected_revision=source["revision"],
            reason="76 台机 1500 订单服务级只读性能验收",
            request_id="phase4-performance-preview",
            dry_run=True,
        )
        with db_module.SessionLocal() as db:
            before_counts = {
                "versions": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleVersion
                    )
                ),
                "tasks": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleTask
                    )
                ),
                "runs": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleReplanRun
                    )
                ),
                "actuals": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleShiftActual
                    )
                ),
                "corrections": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleActualCorrection
                    )
                ),
                "audits": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleAuditEvent
                    )
                ),
            }
            state_before = db.get(
                schedule_models.InjectionScheduleFactoryState,
                "huaxing",
            )
            assert state_before is not None
            next_version_before = state_before.next_version_no

            sql_count = 0

            def count_sql(*_args):
                nonlocal sql_count
                sql_count += 1

            event.listen(
                db_module.engine,
                "before_cursor_execute",
                count_sql,
            )
            started = perf_counter()
            try:
                response = schedule_service.generate_auto_draft(
                    db,
                    "huaxing",
                    source["id"],
                    request,
                    actor,
                )
            finally:
                elapsed = perf_counter() - started
                event.remove(
                    db_module.engine,
                    "before_cursor_execute",
                    count_sql,
                )

            assert elapsed < 10.0, f"elapsed={elapsed:.6f}s"
            assert sql_count <= 80, f"sql_count={sql_count}"
            assert response["run"]["status"] == "previewed"
            assert response["run"]["impact"]["considered_order_count"] == 1_500
            assert response["run"]["impact"]["scheduled_order_count"] == 1_500
            assert response["run"]["impact"]["manual_review_order_count"] == 0
            assert response["run"]["impact"]["blocked_order_count"] == 0
            assert len(response["tasks"]) == 1_500
            assert len(response["affected_task_ids"]) == 1_500
            assert {item["source"] for item in response["tasks"]} == {"auto"}
            assert all(
                datetime.fromisoformat(item["planned_finish_at"])
                > datetime.fromisoformat(item["planned_start_at"])
                and item["duration_hours"] > 0
                and {
                    constraint["status"]
                    for constraint in item["constraint_snapshot"]
                }
                == {"pass"}
                for item in response["tasks"]
            )

            after_counts = {
                "versions": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleVersion
                    )
                ),
                "tasks": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleTask
                    )
                ),
                "runs": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleReplanRun
                    )
                ),
                "actuals": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleShiftActual
                    )
                ),
                "corrections": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleActualCorrection
                    )
                ),
                "audits": db.scalar(
                    select(func.count()).select_from(
                        schedule_models.InjectionScheduleAuditEvent
                    )
                ),
            }
            assert after_counts == before_counts
            state_after = db.get(
                schedule_models.InjectionScheduleFactoryState,
                "huaxing",
            )
            assert state_after is not None
            assert state_after.next_version_no == next_version_before
            assert db.scalar(
                select(func.count())
                .select_from(schedule_models.InjectionOrderMaster)
                .where(
                    schedule_models.InjectionOrderMaster.produced_qty != 0
                )
            ) == 0
