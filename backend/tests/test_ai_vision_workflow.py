from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.models.ai_task import AITaskStep
from app.schemas.ai import AIServerPageContext, AIToolErrorCode
from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.task import (
    AITaskCreate,
    AITaskEventType,
    AITaskStepCreate,
    AITaskType,
)
from app.schemas.ai.vision_observation import (
    AIVisionObservationData,
    AIVisionObservationRow,
    AIVisionProviderObservation,
)
from app.services.ai.artifacts.service import ArtifactNotFoundError
from app.services.ai.providers import ProviderToolCall
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_events import append_task_event
from app.services.ai.task_runner import _safe_tool_metadata
from app.services.ai.task_service import create_task
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.ai.tools import vision_workflow_tools as workflow
from app.services.ai.tools.vision_workflow_tools import (
    VisionCompareBacklogInput,
    compare_backlog_task,
)
from app.services.auth import AuthContext, AuthGrantContext
from app.services.injection_scheduling_execution import (
    InjectionSchedulingAIBacklogOrder,
    InjectionSchedulingAIBacklogPage,
)
from sqlalchemy import select
from tests.ai_task_worker_helpers import worker_database, worker_settings

ARTIFACT_ID = f"aiart-{'a' * 32}"
ARTIFACT_SHA = "b" * 64


def _user(*, can_read: bool = True) -> AuthContext:
    permissions = (
        frozenset({"injection_scheduling:read"}) if can_read else frozenset()
    )
    grant = AuthGrantContext(
        role_id="vision-reader-role",
        role_name="Vision Reader",
        role_code="vision_reader",
        factory_id="huaxing",
        department="production",
        permissions=permissions,
        binding_id="vision-reader-binding",
    )
    return AuthContext(
        id="owner",
        username="owner",
        display_name="Owner",
        roles=("Vision Reader",),
        role_codes=("vision_reader",),
        permissions=permissions,
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
        active_permission_codes=permissions,
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


def _settings():
    config = worker_settings()
    config.ai_semantic_gateway_enabled = True
    config.ai_artifacts_enabled = True
    config.ai_artifact_workflows_enabled = True
    config.ai_vision_tool_comparison_enabled = True
    return config


def _registry():
    return build_default_tool_registry(
        semantic_gateway_enabled=True,
        artifact_workflows_enabled=True,
        vision_tool_comparison_enabled=True,
    )


def _observation() -> AIVisionObservationData:
    return AIVisionObservationData(
        factory_id="huaxing",
        source_artifact_id=ARTIFACT_ID,
        source_sha256=ARTIFACT_SHA,
        as_of="2026-08-12T08:00:00+00:00",
        provider="qwen",
        model="qwen3.7-plus",
        observation=AIVisionProviderObservation(
            overall_confidence=0.95,
            instructions_detected=False,
            unreadable_region_count=0,
            rows=(
                AIVisionObservationRow(
                    row_index=1,
                    order_no="00123",
                    order_no_confidence=0.95,
                    item_no="0007",
                    item_no_confidence=0.95,
                    mold_no="M-001",
                    mold_no_confidence=0.95,
                    delivery_due_date="2026-08-31",
                    delivery_due_date_confidence=0.95,
                    outstanding_quantity="120",
                    outstanding_quantity_confidence=0.95,
                    row_confidence=0.95,
                ),
            ),
        ),
    )


def _formal_page() -> InjectionSchedulingAIBacklogPage:
    return InjectionSchedulingAIBacklogPage(
        factory_id="huaxing",
        as_of="2026-08-12T17:00:00+08:00",
        source_scope="GLOBAL_BACKLOG",
        total=1,
        limit=20,
        offset=0,
        items=(
            InjectionSchedulingAIBacklogOrder(
                order_id="order-1",
                order_no="00123",
                item_no="0007",
                product_name="测试产品",
                mold_no="M-001",
                priority_code="NORMAL",
                delivery_due_date="2026-08-31",
                order_quantity=200,
                outstanding_quantity=120,
                mold_enrichment_status="MATCHED",
                source_type="DEMAND_ORDER",
            ),
        ),
    )


def _completed_observation_task(factory, config, registry) -> str:
    payload = AITaskCreate(
        task_type=AITaskType.READ,
        factory_scope="huaxing",
        primary_skill_id="vision.screenshot_observation",
        proposed_tool_names=("vision.observe_injection_backlog_image",),
        proposed_max_steps=1,
        input_hash="c" * 64,
        idempotency_key="vision-observation-source-task",
        steps=(
            AITaskStepCreate(
                key="observe_image",
                kind=AITaskType.READ,
                label="生成图片 Observation",
                tool_name="vision.observe_injection_backlog_image",
                arguments={
                    "factory_id": "huaxing",
                    "artifact_id": ARTIFACT_ID,
                    "operation_id": "vision-observe-operation",
                    "consent": {
                        "accepted": True,
                        "notice_version": "aliyun-cn-beijing-image-v1",
                        "provider": "qwen",
                        "region": "cn-beijing",
                        "classification": "CONFIDENTIAL_BUSINESS",
                        "content_class": "IMAGE",
                        "artifact_ids": [ARTIFACT_ID],
                    },
                },
            ),
        ),
    )
    with factory() as db:
        task = create_task(
            db,
            payload=payload,
            user=_user(),
            settings=config,
            registry=registry,
            skill_registry=SkillRegistry(registry),
            server_page_context=_page_context(),
            allowed_factory_scopes=frozenset({"huaxing"}),
            request_id="vision-source-task-request",
        )
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task.id))
        assert step is not None
        task.state = "COMPLETED"
        step.state = "COMPLETED"
        step.result_metadata_json = json.dumps(
            {"vision_observation": _observation().model_dump(mode="json")}
        )
        evidence = AIEvidenceReferenceV1(
            evidence_id="vision:observation:source",
            source_level=AIEvidenceSourceLevel.USER_PROVIDED,
            source_name="vision.observe_injection_backlog_image",
            factory_id="huaxing",
            as_of=datetime(2026, 8, 12, 8, tzinfo=UTC),
            content_hash=f"sha256:{ARTIFACT_SHA}",
        )
        append_task_event(
            db,
            task=task,
            event_type=AITaskEventType.STEP_STATE_TRANSITION,
            actor_type="SYSTEM",
            step_id=step.id,
            transition_from="VERIFYING",
            transition_to="COMPLETED",
            reason_code="STEP_COMPLETED",
            evidence=(evidence,),
        )
        db.commit()
        return task.id


def _enable_global_settings(monkeypatch) -> None:
    monkeypatch.setattr(workflow.settings, "ai_vision_tool_comparison_enabled", True)
    monkeypatch.setattr(workflow.settings, "ai_artifacts_enabled", True)
    monkeypatch.setattr(workflow.settings, "ai_artifact_workflows_enabled", True)
    monkeypatch.setattr(workflow.settings, "ai_semantic_gateway_enabled", True)
    monkeypatch.setattr(workflow.settings, "ai_pilot_factory_ids", "huaxing")


def test_stage_b_reauthorizes_and_performs_a_fixed_fresh_formal_read(
    monkeypatch,
    tmp_path,
) -> None:
    factory = worker_database(
        f"sqlite:///{(tmp_path / 'vision-stage-b.db').as_posix()}"
    )
    config = _settings()
    registry = _registry()
    task_id = _completed_observation_task(factory, config, registry)
    _enable_global_settings(monkeypatch)
    monkeypatch.setattr(
        workflow,
        "get_owned_artifact",
        lambda *_args, **_kwargs: SimpleNamespace(id=ARTIFACT_ID),
    )
    formal_calls: list[tuple[str, int, int]] = []

    def fresh_formal_read(_db, factory_id: str, *, limit: int, offset: int):
        formal_calls.append((factory_id, limit, offset))
        return _formal_page()

    monkeypatch.setattr(workflow, "list_backlog_orders_page", fresh_formal_read)

    with factory() as db:
        result = compare_backlog_task(
            ToolExecutionContext(
                db=db,
                user=_user(),
                request_id="vision-stage-b-request",
                page_context=_page_context(),
            ),
            VisionCompareBacklogInput(
                factory_id="huaxing",
                observation_task_id=task_id,
                operation_id="vision-compare-operation",
            ),
        )

    assert formal_calls == [("huaxing", 20, 0)]
    assert result.formal_backlog.as_of == "2026-08-12T17:00:00+08:00"
    assert result.observation.rows[0].order_no == "00123"
    assert result.matched_count == 1
    assert result.no_write_performed is True

    with factory() as db:
        allowed = asyncio.run(
            ToolExecutor(registry, config).execute(
                ProviderToolCall(
                    call_id="stage-b-allowed",
                    name="vision.compare_injection_backlog",
                    arguments_json=json.dumps(
                        {
                            "factory_id": "huaxing",
                            "observation_task_id": task_id,
                            "operation_id": "vision-allowed-operation",
                        }
                    ),
                ),
                ToolExecutionContext(
                    db=db,
                    user=_user(),
                    request_id="vision-stage-b-allowed",
                    page_context=_page_context(),
                ),
            )
        )
    assert allowed.ok is True
    metadata, evidence, artifact_refs = _safe_tool_metadata(allowed)
    assert metadata["vision_comparison"]["no_write_performed"] is True
    assert {item.source_level for item in evidence} == {
        AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE,
        AIEvidenceSourceLevel.USER_PROVIDED,
    }
    assert [item.artifact_kind for item in artifact_refs] == ["USER_IMAGE"]

    denied_executor = ToolExecutor(registry, config)
    denied = asyncio.run(
        denied_executor.execute(
            ProviderToolCall(
                call_id="stage-b-denied",
                name="vision.compare_injection_backlog",
                arguments_json=json.dumps(
                    {
                        "factory_id": "huaxing",
                        "observation_task_id": task_id,
                        "operation_id": "vision-denied-operation",
                    }
                ),
            ),
            ToolExecutionContext(
                db=None,
                user=_user(can_read=False),
                request_id="stage-b-denied-request",
                page_context=_page_context(),
            ),
        )
    )
    assert denied.ok is False
    assert denied.error_code == AIToolErrorCode.PERMISSION_DENIED.value
    assert formal_calls == [("huaxing", 20, 0), ("huaxing", 20, 0)]


def test_stage_b_rejects_factory_mismatch_and_deleted_or_expired_source(
    monkeypatch,
    tmp_path,
) -> None:
    factory = worker_database(
        f"sqlite:///{(tmp_path / 'vision-stage-b-invalid.db').as_posix()}"
    )
    config = _settings()
    registry = _registry()
    task_id = _completed_observation_task(factory, config, registry)
    _enable_global_settings(monkeypatch)

    with factory() as db, pytest.raises(Exception) as mismatch_info:
        compare_backlog_task(
            ToolExecutionContext(
                db=db,
                user=_user(),
                request_id="vision-factory-mismatch",
            ),
            VisionCompareBacklogInput(
                factory_id="huakang-a",
                observation_task_id=task_id,
                operation_id="vision-mismatch-operation",
            ),
        )
    assert getattr(mismatch_info.value, "code", "") == (
        "AI_VISION_OBSERVATION_TASK_INVALID"
    )

    monkeypatch.setattr(
        workflow,
        "get_owned_artifact",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ArtifactNotFoundError("文件不存在。")
        ),
    )
    with factory() as db, pytest.raises(ArtifactNotFoundError):
        compare_backlog_task(
            ToolExecutionContext(
                db=db,
                user=_user(),
                request_id="vision-deleted-artifact",
            ),
            VisionCompareBacklogInput(
                factory_id="huaxing",
                observation_task_id=task_id,
                operation_id="vision-deleted-operation",
            ),
        )
