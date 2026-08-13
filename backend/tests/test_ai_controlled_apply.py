import importlib
import json

from sqlalchemy import func, select
from test_injection_scheduling_phase3_api import (
    ADMIN_TEST_PASSWORD,
    login,
    machine_payload,
    make_migrated_client,
    mold_payload,
    order_payload,
)


def _enable_controlled_apply(monkeypatch) -> None:
    values = {
        "AI_ENABLED": "true",
        "AI_PROVIDER": "fake",
        "AI_DEFAULT_MODEL": "fake-model",
        "AI_PILOT_ENABLED": "true",
        "AI_PILOT_USER_IDS": "user-admin",
        "AI_PILOT_FACTORY_IDS": "huaxing",
        "AI_PILOT_PUBLIC_TLS_VERIFIED": "true",
        "AI_RUNTIME_DISABLE_PATH": "",
        "AI_ACTION_GATEWAY_ENABLED": "true",
        "AI_CONTROLLED_APPLY_ENABLED": "true",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _create_preview(client) -> tuple[dict, dict]:
    factory_id = "huaxing"
    machine_data = machine_payload(factory_id, "AI-CONTROLLED-7A")
    machine_data["machine_class"] = "7A"
    machine_data["injection_capacity_g"] = 220
    machine = client.post(
        "/api/injection-scheduling/machines",
        json=machine_data,
    )
    assert machine.status_code == 201, machine.text
    mold_data = mold_payload(factory_id, "AI-CONTROLLED-MOLD")
    mold_data.update(
        recommended_machine_class="7A",
        whole_shot_net_weight_g=120,
        material_code="ABS",
        color_profile="浅蓝",
        copy_count=1,
    )
    mold = client.post("/api/injection-scheduling/molds", json=mold_data)
    assert mold.status_code == 201, mold.text
    order_data = order_payload(factory_id, "AI-CONTROLLED-ORDER", 80)
    order_data["mold_id"] = mold.json()["id"]
    order_data["delivery_due_date"] = "2026-08-16"
    order = client.post("/api/injection-scheduling/orders", json=order_data)
    assert order.status_code == 201, order.text
    draft = client.post(
        "/api/injection-scheduling/plans/drafts",
        json={
            "factory_id": factory_id,
            "expected_revision": 0,
            "business_date": "2026-08-12",
        },
    )
    assert draft.status_code == 201, draft.text
    draft_data = draft.json()
    preview = client.post(
        "/api/injection-scheduling/auto-schedule/runs",
        headers={"X-Request-ID": "ai-controlled-preview-1"},
        json={
            "factory_id": factory_id,
            "plan_id": draft_data["id"],
            "expected_plan_revision": draft_data["revision"],
            "rule_revision": draft_data["rule_revision"],
            "mode": "PREVIEW",
            "horizon_start": "2026-08-12T08:00:00+08:00",
            "horizon_end": "2026-08-18T20:00:00+08:00",
            "order_ids": [order.json()["id"]],
            "respect_locked_tasks": True,
            "solver": "HEURISTIC",
            "time_limit_seconds": 10,
        },
    )
    assert preview.status_code == 201, preview.text
    assert preview.json()["status"] == "SUCCEEDED"
    assert preview.json()["summary"]["scheduled_count"] == 1
    return draft_data, preview.json()


def test_controlled_apply_requires_persisted_confirmation_and_replays_once(
    monkeypatch,
) -> None:
    _enable_controlled_apply(monkeypatch)
    with make_migrated_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        draft, preview = _create_preview(client)

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        auth_service = importlib.import_module("app.services.auth")
        tool_module = importlib.import_module(
            "app.services.ai.tools.controlled_apply_tools"
        )
        tool_executor = importlib.import_module("app.services.ai.tool_executor")
        action_schema = importlib.import_module("app.schemas.ai.action_confirmation")
        ai_api = importlib.import_module("app.api.ai")
        assert ai_api.tool_registry.resolve("injection_scheduling.propose_apply")
        assert ai_api.tool_registry.resolve("injection_scheduling.apply_preview_run") is None

        with db_module.SessionLocal() as db:
            admin = db.get(auth_models.AuthUser, "user-admin")
            user = auth_service.build_auth_context(db, admin)
            proposal = tool_module.propose_apply(
                tool_executor.ToolExecutionContext(
                    db=db,
                    user=user,
                    request_id="ai-controlled-proposal-1",
                    tool_call_id="tool-call-controlled-proposal-1",
                ),
                action_schema.InjectionSchedulingApplyProposalInput(
                    factory_id="huaxing",
                    run_id=preview["id"],
                ),
            )
            assert proposal.status == "PENDING"
            assert proposal.action_summary.assignment_count == 1
            assert proposal.action_summary.review_required_count == 0
            assert proposal.action_summary.effect_label == "应用到 DRAFT，不会发布生产"
            confirmation_id = proposal.confirmation_id
            args_hash = proposal.args_hash

        gateway_before = client.get(
            f"/api/ai/actions/{confirmation_id}",
            params={"factory_id": "huaxing"},
        )
        assert gateway_before.status_code == 200, gateway_before.text
        assert gateway_before.json()["lifecycle_status"] == "WAITING_APPROVAL"
        assert gateway_before.json()["compatibility_confirmation_id"] == confirmation_id

        wrong_factory = client.post(
            f"/api/ai/action-confirmations/{confirmation_id}/confirm",
            json={
                "factory_id": "huakang-a",
                "expected_args_hash": args_hash,
            },
        )
        assert wrong_factory.status_code == 403
        assert wrong_factory.json()["detail"]["code"] == (
            "CONFIRMATION_FACTORY_MISMATCH"
        )

        confirmed = client.post(
            f"/api/ai/action-confirmations/{confirmation_id}/confirm",
            json={
                "factory_id": "huaxing",
                "expected_args_hash": args_hash,
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "CONFIRMED"
        gateway_approved = client.get(
            f"/api/ai/actions/{confirmation_id}",
            params={"factory_id": "huaxing"},
        )
        assert gateway_approved.status_code == 200, gateway_approved.text
        assert gateway_approved.json()["lifecycle_status"] == "APPROVED"

        execution_payload = {
            "factory_id": "huaxing",
            "expected_args_hash": args_hash,
            "execution_request_id": "web-ai-controlled-execute-1",
            "review_override_reason": "",
        }
        executed = client.post(
            f"/api/ai/action-confirmations/{confirmation_id}/execute",
            json=execution_payload,
        )
        assert executed.status_code == 200, executed.text
        result = executed.json()
        assert result["confirmation"]["status"] == "EXECUTED"
        assert result["result"] == {
            "run_id": preview["id"],
            "run_status": "APPLIED",
            "plan_id": draft["id"],
            "plan_revision": draft["revision"] + 1,
            "plan_status": "DRAFT",
            "audit_sequence": result["result"]["audit_sequence"],
            "idempotent_replay": False,
            "outcome_label": "已应用到 DRAFT，尚未发布生产",
        }

        replay = client.post(
            f"/api/ai/action-confirmations/{confirmation_id}/execute",
            json=execution_payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["result"]["idempotent_replay"] is True
        gateway_executed = client.get(
            f"/api/ai/actions/{confirmation_id}",
            params={"factory_id": "huaxing"},
        )
        assert gateway_executed.status_code == 200, gateway_executed.text
        gateway_data = gateway_executed.json()
        assert gateway_data["lifecycle_status"] == "EXECUTED"
        assert gateway_data["verification"]["entity_status"] == "DRAFT"
        assert gateway_data["verification"]["domain_audit_id"].startswith(
            "injection_scheduling_audit_events:"
        )
        different_request = client.post(
            f"/api/ai/action-confirmations/{confirmation_id}/execute",
            json=execution_payload
            | {"execution_request_id": "web-ai-controlled-execute-2"},
        )
        assert different_request.status_code == 409
        assert different_request.json()["detail"]["code"] == (
            "CONFIRMATION_ALREADY_EXECUTED"
        )

        confirmation_model = importlib.import_module("app.models.ai_action")
        scheduling_models = importlib.import_module(
            "app.models.injection_scheduling_execution"
        )
        with db_module.SessionLocal() as db:
            confirmation = db.get(
                confirmation_model.AIActionConfirmation,
                confirmation_id,
            )
            assert confirmation.status == "EXECUTED"
            assert "review_override_reason" not in confirmation.normalized_action_json
            assert json.loads(confirmation.normalized_action_json) == {
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "factory_id": "huaxing",
                "plan_id": draft["id"],
                "run_id": preview["id"],
                "run_revision": 1,
            }
            plan = db.get(scheduling_models.InjectionSchedulingPlan, draft["id"])
            assert plan.status == "DRAFT"
            audit_count = db.scalar(
                select(func.count(scheduling_models.InjectionSchedulingAuditEvent.id))
                .where(
                    scheduling_models.InjectionSchedulingAuditEvent.event_type
                    == "auto_schedule_run_applied",
                    scheduling_models.InjectionSchedulingAuditEvent.request_id
                    == execution_payload["execution_request_id"],
                )
            )
            assert audit_count == 1


def test_controlled_apply_is_separately_feature_flagged() -> None:
    registry_module = importlib.import_module("app.services.ai.tool_registry")
    assert (
        registry_module.build_default_tool_registry().resolve(
            "injection_scheduling.propose_apply"
        )
        is None
    )
    assert registry_module.build_default_tool_registry(
        controlled_apply_enabled=True
    ).resolve("injection_scheduling.propose_apply") is not None
