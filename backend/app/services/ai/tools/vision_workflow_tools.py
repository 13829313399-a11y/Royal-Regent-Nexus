from __future__ import annotations

import json

from pydantic import Field, ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel, StrictToolInput
from app.schemas.ai.artifact import (
    AIArtifactEgressConsent,
    AIArtifactReferenceInput,
)
from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.task import AITaskState, AITaskStepState
from app.schemas.ai.vision_observation import (
    AIVisionComparisonData,
    AIVisionObservationData,
)
from app.services.ai.artifacts.service import (
    ArtifactInvalidError,
    get_owned_artifact,
)
from app.services.ai.artifacts.storage import LocalImmutableArtifactStorage
from app.services.ai.artifacts.vision_adapter import prepare_vision_artifacts
from app.services.ai.attachment_service import clear_prepared_attachments
from app.services.ai.provider_factory import build_provider
from app.services.ai.serializers.scheduling import serialize_backlog_page
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.ai.vision_comparison import compare_observation_to_formal_backlog
from app.services.ai.vision_observation import observe_injection_backlog_image
from app.services.auth import ALLOWED_FACTORY_IDS
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS
from app.services.injection_scheduling_execution import list_backlog_orders_page

_OPERATION_ID = r"^[A-Za-z0-9._-]{8,128}$"


class VisionObserveBacklogInput(StrictToolInput):
    factory_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    artifact_id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    operation_id: str = Field(pattern=_OPERATION_ID)
    consent: AIArtifactEgressConsent


class VisionCompareBacklogInput(StrictToolInput):
    factory_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    observation_task_id: str = Field(pattern=r"^aitask-[a-f0-9]{32}$")
    operation_id: str = Field(pattern=_OPERATION_ID)


def _allowed_factories() -> frozenset[str]:
    return frozenset(
        value.strip()
        for value in settings.ai_pilot_factory_ids.split(",")
        if value.strip() in ALLOWED_FACTORY_IDS
    )


def _require_enabled() -> None:
    if not (
        settings.ai_vision_tool_comparison_enabled
        and settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
        and settings.ai_semantic_gateway_enabled
    ):
        raise ArtifactInvalidError(
            "两段式图片核对尚未启用。",
            code="AI_VISION_COMPARISON_DISABLED",
        )


async def observe_backlog_image_task(
    context: ToolExecutionContext,
    arguments: VisionObserveBacklogInput,
) -> AIVisionObservationData:
    _require_enabled()
    if context.session_factory is None:
        raise ValueError("Vision Observation Task requires a session factory")
    prepared = ()
    source_id = ""
    source_sha256 = ""
    with context.session_factory() as db:
        source = get_owned_artifact(
            db,
            artifact_id=arguments.artifact_id,
            user=context.user,
            allowed_factory_ids=_allowed_factories(),
        )
        if source.factory_id != arguments.factory_id:
            raise ArtifactInvalidError(
                "图片厂区与 Task 厂区不一致。",
                code="AI_ARTIFACT_VISION_SCOPE_INVALID",
            )
        prepared = prepare_vision_artifacts(
            db,
            references=[AIArtifactReferenceInput(artifact_id=source.id)],
            consent=arguments.consent,
            user=context.user,
            factory_id=arguments.factory_id,
            allowed_factory_ids=_allowed_factories(),
            storage=LocalImmutableArtifactStorage(settings.ai_artifact_storage_dir),
            settings=settings,
        )
        source_id = source.id
        source_sha256 = source.sha256
    provider = None
    try:
        provider = build_provider(settings, require_vision=True)
        return await observe_injection_backlog_image(
            attachment=prepared[0],
            source_artifact_id=source_id,
            source_sha256=source_sha256,
            factory_id=arguments.factory_id,
            provider=provider,
            settings=settings,
            request_id=context.request_id,
        )
    finally:
        if provider is not None:
            await provider.aclose()
        clear_prepared_attachments(prepared)


def _observation_step(db, task_id: str) -> AITaskStep:
    step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task_id,
            AITaskStep.tool_name == "vision.observe_injection_backlog_image",
            AITaskStep.state == AITaskStepState.COMPLETED.value,
        )
    )
    if step is None:
        raise ArtifactInvalidError(
            "图片 Observation Task 尚未完成或不可用。",
            code="AI_VISION_OBSERVATION_TASK_INVALID",
        )
    return step


def _observation_data(step: AITaskStep) -> AIVisionObservationData:
    try:
        metadata = json.loads(step.result_metadata_json)
        return AIVisionObservationData.model_validate(metadata["vision_observation"])
    except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
        raise ArtifactInvalidError(
            "图片 Observation Task 结果无效。",
            code="AI_VISION_OBSERVATION_TASK_INVALID",
        ) from exc


def _observation_evidence(db, task_id: str) -> AIEvidenceReferenceV1:
    events = db.scalars(
        select(AITaskEvent)
        .where(AITaskEvent.task_id == task_id)
        .order_by(AITaskEvent.sequence.asc())
    ).all()
    for event in events:
        try:
            evidence = [
                AIEvidenceReferenceV1.model_validate(item)
                for item in json.loads(event.evidence_json)
            ]
        except (json.JSONDecodeError, TypeError, ValidationError):
            continue
        for item in evidence:
            if (
                item.source_level is AIEvidenceSourceLevel.USER_PROVIDED
                and item.source_name == "vision.observe_injection_backlog_image"
            ):
                return item
    raise ArtifactInvalidError(
        "图片 Observation Evidence 不可用。",
        code="AI_VISION_OBSERVATION_EVIDENCE_MISSING",
    )


def compare_backlog_task(
    context: ToolExecutionContext,
    arguments: VisionCompareBacklogInput,
) -> AIVisionComparisonData:
    _require_enabled()
    if context.db is None:
        raise ValueError("Vision Comparison Task requires a managed database")
    task = context.db.get(AITask, arguments.observation_task_id)
    if (
        task is None
        or task.owner_user_id != context.user.id
        or task.factory_scope != arguments.factory_id
        or task.state != AITaskState.COMPLETED.value
        or task.primary_skill_id != "vision.screenshot_observation"
    ):
        raise ArtifactInvalidError(
            "图片 Observation Task 不存在。",
            code="AI_VISION_OBSERVATION_TASK_INVALID",
        )
    observation = _observation_data(_observation_step(context.db, task.id))
    if observation.factory_id != arguments.factory_id:
        raise ArtifactInvalidError(
            "图片 Observation 厂区不匹配。",
            code="AI_ARTIFACT_VISION_SCOPE_INVALID",
        )
    get_owned_artifact(
        context.db,
        artifact_id=observation.source_artifact_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
    )
    evidence = _observation_evidence(context.db, task.id)

    # The formal query is fixed and fresh. No recognized image text is copied
    # into its arguments, filter, Tool name, factory or authorization context.
    formal_page = list_backlog_orders_page(
        context.db,
        arguments.factory_id,
        limit=20,
        offset=0,
    )
    formal = serialize_backlog_page(formal_page)
    return compare_observation_to_formal_backlog(
        observation_task_id=task.id,
        observation_data=observation,
        observation_evidence=evidence,
        formal_backlog=formal,
    )


def serialize_observation(value: object) -> AIVisionObservationData:
    return AIVisionObservationData.model_validate(value)


def serialize_comparison(value: object) -> AIVisionComparisonData:
    return AIVisionComparisonData.model_validate(value)


def vision_workflow_tool_specs() -> tuple[ToolSpec, ...]:
    departments = frozenset(SCHEDULING_DEPARTMENTS)
    return (
        ToolSpec(
            name="vision.observe_injection_backlog_image",
            description=(
                "Stage A：仅从用户图片生成严格的注塑 Backlog Observation；"
                "一次 Provider 调用且不开放任何 Tool。"
            ),
            input_model=VisionObserveBacklogInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=observe_backlog_image_task,
            serializer=serialize_observation,
            display_label="正在生成图片 Observation",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=departments,
            factory_argument="factory_id",
            requires_db=False,
            max_result_rows=20,
            timeout_seconds=120,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
            version="1.0.0",
        ),
        ToolSpec(
            name="vision.compare_injection_backlog",
            description=(
                "Stage B：重新鉴权并固定读取当前正式注塑 Backlog，"
                "再以确定性字段匹配器比较已保存的 Observation。"
            ),
            input_model=VisionCompareBacklogInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=compare_backlog_task,
            serializer=serialize_comparison,
            display_label="正在核对正式注塑 Backlog",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=departments,
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=50,
            timeout_seconds=15,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
            version="1.0.0",
        ),
    )
