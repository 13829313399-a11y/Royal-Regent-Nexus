import asyncio
import json
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.models.injection_scheduling_scheduler import InjectionSchedulingRun
from app.schemas.ai import AIServerPageContext, AIToolRiskLevel
from app.schemas.ai.scheduling_advisor import InjectionSchedulingPreviewIntentInput
from app.services.ai import scheduling_advisor
from app.services.ai.providers import ProviderToolCall
from app.services.ai.scheduling_advisor import intent_to_run_create
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import ToolRegistry, ToolSpec
from app.services.ai.tools.scheduling_advisor_tools import (
    scheduling_advisor_tool_specs,
)
from app.services.auth import AuthContext, AuthGrantContext
from pydantic import ValidationError


def _user(*, include_edit: bool = True) -> AuthContext:
    permissions = {"injection_scheduling:read"}
    if include_edit:
        permissions.add("injection_scheduling:edit")
    grant = AuthGrantContext(
        role_id="role-scheduling-advisor",
        role_name="排产顾问测试",
        factory_id="huaxing",
        department="production",
        permissions=frozenset(permissions),
        binding_id="binding-scheduling-advisor",
    )
    return AuthContext(
        id="user-scheduling-advisor",
        username="scheduling-advisor",
        display_name="排产顾问测试",
        roles=("排产顾问测试",),
        role_codes=("scheduling-advisor",),
        permissions=frozenset(permissions),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
        active_permission_codes=frozenset(permissions),
    )


def _page_context() -> AIServerPageContext:
    return AIServerPageContext(
        verified_route_name="injection-scheduling-v2",
        verified_path="/modules/production/injection-scheduling",
        verified_factory_id="huaxing",
        verified_module_id="injection-scheduling",
        knowledge_id="injection-scheduling",
        allowed_tool_groups=("injection_scheduling",),
    )


def _run(**overrides: object) -> InjectionSchedulingRun:
    values: dict[str, object] = {
        "id": "isrun-ai-1",
        "factory_id": "huaxing",
        "plan_id": "plan-draft-1",
        "expected_plan_revision": 7,
        "rule_set_id": "rules-1",
        "rule_revision": 3,
        "mode": "PREVIEW",
        "solver_type": "HEURISTIC",
        "solver_version": "phase3-v1",
        "requested_solver": "AUTO",
        "solver_status": "HEURISTIC",
        "fallback_used": False,
        "fallback_reason": "",
        "scenario_group_id": "scenario-1",
        "scenario_name": "AI 交期优先",
        "alternative_no": 1,
        "replay_of_run_id": None,
        "status": "SUCCEEDED",
        "horizon_start": "2026-08-12T08:00:00+08:00",
        "horizon_end": "2026-08-26T20:00:00+08:00",
        "input_snapshot_json": json.dumps(
            {"orders": [{"id": "order-1"}, {"id": "order-2"}]}
        ),
        "objective_config_json": "{}",
        "summary_json": json.dumps(
            {
                "input_order_count": 2,
                "scheduled_count": 1,
                "review_count": 1,
                "unassigned_count": 0,
                "moved_task_count": 0,
                "overdue": {"before": 2, "after": 1, "change": -1},
                "mold_changes": {"before": 3, "after": 2, "change": -1},
                "dark_to_light_changes": {"before": 1, "after": 0, "change": -1},
                "machine_loads": [
                    {"machine_id": "secret-machine-a", "load_ratio": 0.5},
                    {"machine_id": "secret-machine-b", "load_ratio": 0.75},
                ],
                "solver_elapsed_ms": 12.5,
            }
        ),
        "request_id": "ai-preview-request",
        "payload_hash": "a" * 64,
        "error_detail": "",
        "started_at": "2026-08-12T08:00:00+08:00",
        "finished_at": "2026-08-12T08:00:01+08:00",
        "applied_at": "",
        "created_by": "user-scheduling-advisor",
        "created_by_name": "排产顾问测试",
        "applied_by": "",
        "applied_by_name": "",
        "created_at": "2026-08-12T08:00:00+08:00",
        "revision": 1,
    }
    values.update(overrides)
    return InjectionSchedulingRun(**values)


def test_scheduling_intent_is_closed_and_rejects_unsupported_constraints() -> None:
    with pytest.raises(ValidationError):
        InjectionSchedulingPreviewIntentInput.model_validate(
            {
                "factory_id": "huaxing",
                "objective": "MAXIMIZE_PROFIT",
                "sql_constraint": "DROP TABLE tasks",
            }
        )
    with pytest.raises(ValidationError, match="SELECTED"):
        InjectionSchedulingPreviewIntentInput(
            factory_id="huaxing",
            order_scope="SELECTED",
        )
    with pytest.raises(ValidationError, match="ALL_ELIGIBLE"):
        InjectionSchedulingPreviewIntentInput(
            factory_id="huaxing",
            order_ids=["order-1"],
        )


def test_intent_maps_only_to_existing_preview_scheduler_contract() -> None:
    plan = SimpleNamespace(
        id="plan-draft-1",
        revision=7,
        business_date="2026-08-12",
    )
    intent = InjectionSchedulingPreviewIntentInput(
        factory_id="huaxing",
        objective="DELIVERY_PRIORITY",
        solver="CP_SAT",
        horizon_days=10,
        scenario_name="交期优先",
    )

    payload = intent_to_run_create(
        plan=plan,
        rule_revision=3,
        intent=intent,
    )

    assert payload.mode == "PREVIEW"
    assert payload.respect_locked_tasks is True
    assert payload.plan_id == "plan-draft-1"
    assert payload.expected_plan_revision == 7
    assert payload.rule_revision == 3
    assert payload.horizon_start == "2026-08-12T08:00:00+08:00"
    assert payload.horizon_end == "2026-08-22T20:00:00+08:00"
    assert payload.objective_weights.tardiness_weight == 300
    assert payload.order_ids == []
    assert not hasattr(payload, "apply")
    assert not hasattr(payload, "publish")


def test_comparison_alternative_reuses_persisted_snapshot_scope() -> None:
    plan = SimpleNamespace(
        id="plan-draft-1",
        revision=7,
        business_date="2026-08-12",
    )
    base = _run()
    payload = intent_to_run_create(
        plan=plan,
        rule_revision=3,
        intent=InjectionSchedulingPreviewIntentInput(
            factory_id="huaxing",
            objective="LOAD_BALANCE",
            compare_with_run_id=base.id,
            scenario_name="负载均衡",
        ),
        comparison_base=base,
    )

    assert payload.order_ids == ["order-1", "order-2"]
    assert payload.horizon_start == base.horizon_start
    assert payload.horizon_end == base.horizon_end
    assert payload.scenario_group_id == "scenario-1"
    assert payload.alternative_no == 2
    assert payload.objective_weights.load_balance_weight == 100


def test_generate_preview_calls_existing_scheduler_and_returns_persisted_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = SimpleNamespace(
        id="plan-draft-1",
        revision=7,
        business_date="2026-08-12",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(scheduling_advisor, "_draft_plan", lambda _db, _factory: plan)
    monkeypatch.setattr(
        scheduling_advisor,
        "current_rule_set",
        lambda _db, _factory: SimpleNamespace(revision=3),
    )

    def fake_create_run(_db, payload, user, request_id):
        captured.update(payload=payload, user=user, request_id=request_id)
        return _run()

    monkeypatch.setattr(scheduling_advisor, "create_run", fake_create_run)
    intent = InjectionSchedulingPreviewIntentInput(
        factory_id="huaxing",
        objective="DELIVERY_PRIORITY",
    )
    context = ToolExecutionContext(
        db=object(),
        user=_user(),
        request_id="request-ai-preview",
        page_context=_page_context(),
        tool_call_id="call-ai-preview",
    )

    result = scheduling_advisor.generate_preview(
        context.db,
        intent,
        context.user,
        context,
    )

    assert captured["user"] is context.user
    assert str(captured["request_id"]).startswith("ai-preview-")
    assert result.candidate_label == "候选方案，尚未应用"
    assert result.applied is False
    assert result.run.metrics.scheduled_count == 1
    assert result.run.metrics.overdue.change == -1
    assert result.run.metrics.load_ratio_average == 0.625
    manifest = result.run.preview_manifest
    assert manifest is not None
    assert manifest.preview_type == "injection_scheduling.run"
    assert manifest.status == "READY"
    assert manifest.can_propose_action is True
    assert manifest.action_capability == "CREATE_PROPOSAL_ONLY"
    assert manifest.no_write_performed is True
    assert manifest.source_revision_hash != manifest.input_hash
    assert manifest.evidence_refs[0].source_level == "FORMAL_DOMAIN_SERVICE"
    serialized = result.model_dump(mode="json")
    assert "secret-machine-a" not in json.dumps(serialized)
    assert "assignments" not in serialized["run"]


def test_registry_exposes_preview_only_with_edit_permission_and_executor_allows_it() -> None:
    preview_spec, comparison_spec = scheduling_advisor_tool_specs()
    assert preview_spec.risk_level == AIToolRiskLevel.PREVIEW_WITH_AUDIT
    assert preview_spec.required_permission == "injection_scheduling:edit"
    assert comparison_spec.risk_level == AIToolRiskLevel.READ_ONLY
    registry = ToolRegistry((preview_spec, comparison_spec))
    allowed_context = ToolExecutionContext(
        None,
        _user(),
        "request-preview-registry",
        _page_context(),
    )
    read_only_context = ToolExecutionContext(
        None,
        _user(include_edit=False),
        "request-preview-read-only",
        _page_context(),
    )
    assert [item.name for item in registry.provider_definitions(allowed_context)] == [
        "injection_scheduling.compare_previews",
        "injection_scheduling.generate_preview",
    ]
    assert [item.name for item in registry.provider_definitions(read_only_context)] == [
        "injection_scheduling.compare_previews"
    ]

    executed: list[str] = []
    safe_spec = ToolSpec(
        name="injection_scheduling.test_preview",
        description="测试 PREVIEW_WITH_AUDIT 执行边界。",
        input_model=InjectionSchedulingPreviewIntentInput,
        risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        executor=lambda _context, _arguments: executed.append("preview")
        or {"candidate_label": "候选方案，尚未应用"},
        serializer=lambda value: value,
        display_label="正在生成测试候选方案",
        tool_group="injection_scheduling",
        required_permission="injection_scheduling:edit",
        allowed_departments=frozenset({"production"}),
        factory_argument="factory_id",
    )
    outcome = asyncio.run(
        ToolExecutor(ToolRegistry((safe_spec,)), Settings(_env_file=None)).execute(
            ProviderToolCall(
                call_id="preview-call-1",
                name=safe_spec.name,
                arguments_json=json.dumps({"factory_id": "huaxing"}),
            ),
            allowed_context,
        )
    )
    assert outcome.ok
    assert executed == ["preview"]
