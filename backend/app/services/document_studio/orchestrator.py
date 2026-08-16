from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_artifact import AIArtifact
from app.models.ai_task import AITask, AITaskStep
from app.schemas.ai.task import (
    AIArtifactReference,
    AITaskCreate,
    AITaskStepCreate,
    AITaskStepState,
    AITaskType,
)
from app.schemas.ai.tool import AIToolRiskLevel
from app.schemas.document_studio import (
    DocumentJobCreate,
    DocumentJobDetail,
    DocumentJobEvent,
    DocumentJobEventPage,
    DocumentJobList,
    DocumentJobOperationalMetrics,
    DocumentJobResult,
    DocumentJobReviewRequest,
    DocumentJobSummary,
    DocumentPreflightResult,
    DocumentQualityReport,
    DocumentSnapshot,
    DocumentStudioTaskOptions,
)
from app.services.ai.artifacts.scanner import ArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactNotFoundError,
    get_owned_artifact,
)
from app.services.ai.artifacts.storage import ArtifactStorage
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_events import read_task_events
from app.services.ai.task_service import (
    AITaskError,
    AITaskNotFoundError,
    create_task,
    get_owned_task,
    request_task_cancellation,
    request_task_resume,
    transition_step,
)
from app.services.ai.tool_registry import ToolRegistry, build_default_tool_registry
from app.services.auth import AuthContext
from app.services.document_studio.contracts import (
    DocumentJobState,
    DocumentRouteDecision,
)
from app.services.document_studio.metadata import (
    create_metadata_artifact,
    load_metadata_artifact,
)
from app.services.document_studio.preflight import preflight_document
from app.services.document_studio.providers.qwen_document import (
    get_document_provider_status,
)
from app.services.document_studio.quality import build_quality_report
from app.services.document_studio.review import (
    DocumentReviewError,
    apply_review_patches,
)
from app.services.document_studio.routing import (
    DOCUMENT_STUDIO_PRIMARY_SKILLS,
    DOCUMENT_STUDIO_TOOL_NAMES,
    available_document_job_types,
    map_task_state,
)
from app.services.document_translation import document_translation_status


class DocumentJobError(RuntimeError):
    code = "DOCUMENT_JOB_ERROR"
    status_code = 422
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


class DocumentJobNotFoundError(DocumentJobError):
    code = "DOCUMENT_JOB_NOT_FOUND"
    status_code = 404


class DocumentJobConflictError(DocumentJobError):
    code = "DOCUMENT_JOB_CONFLICT"
    status_code = 409


class DocumentJobUnavailableError(DocumentJobError):
    code = "DOCUMENT_JOB_UNAVAILABLE"
    status_code = 503
    retryable = True


class DocumentJobReviewUnavailableError(DocumentJobError):
    code = "DOCUMENT_JOB_REVIEW_NOT_READY"
    status_code = 409


def build_document_tool_registry(settings: Settings) -> ToolRegistry:
    return build_default_tool_registry(
        controlled_apply_enabled=False,
        semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
        knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
        artifact_workflows_enabled=settings.ai_artifact_workflows_enabled,
        document_studio_enabled=settings.ai_document_studio_enabled,
        vision_tool_comparison_enabled=settings.ai_vision_tool_comparison_enabled,
    )


def task_runtime_available(settings: Settings) -> bool:
    database_driver = settings.database_url.split(":", 1)[0].casefold()
    return bool(
        settings.ai_document_studio_enabled
        and settings.ai_enabled
        and settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
        and settings.ai_tasks_enabled
        and settings.ai_nif_runtime_enabled
        and settings.ai_skill_router_enabled
        and settings.ai_evidence_v1_enabled
        and settings.ai_task_worker_enabled
        and database_driver.startswith("postgresql")
        and settings.ai_artifact_scanner_backend == "clamav"
    )


def office_renderer_available(settings: Settings) -> bool:
    return settings.document_office_renderer_enabled


def _download_preflight(
    *,
    source: AIArtifact,
    data: bytes,
    payload,
    settings: Settings,
) -> DocumentPreflightResult:
    return preflight_document(
        source=source,
        data=data,
        job_type=payload.job_type,
        processing_mode=payload.processing_mode,
        task_runtime_available=task_runtime_available(settings),
        cloud_ocr_available=get_document_provider_status(settings).available,
        local_translation_available=bool(
            document_translation_status(settings.document_translation_model_dir)[
                "available"
            ]
        ),
        office_renderer_available=office_renderer_available(settings),
    )


def preflight_owned_document(
    db: Session,
    *,
    payload,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    settings: Settings,
) -> DocumentPreflightResult:
    from app.services.ai.artifacts.service import download_artifact

    download = download_artifact(
        db,
        artifact_id=payload.source_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )
    if download.record.factory_id != payload.factory_id:
        raise DocumentJobNotFoundError("文档 Artifact 不存在。")
    return _download_preflight(
        source=download.record,
        data=download.data,
        payload=payload,
        settings=settings,
    )


def _canonical_input(payload: DocumentJobCreate) -> str:
    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _task_arguments(payload: DocumentJobCreate) -> DocumentStudioTaskOptions:
    return DocumentStudioTaskOptions(
        operation_id=payload.operation_id,
        factory_id=payload.factory_id,
        source_artifact_id=payload.source_artifact_id,
        source_sha256=payload.source_sha256,
        job_type=payload.job_type,
        processing_mode=payload.processing_mode,
        page_range=payload.page_range,
        options=payload.options,
        cloud_consent=payload.cloud_consent,
    )


def create_document_job(
    db: Session,
    *,
    payload: DocumentJobCreate,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    settings: Settings,
    request_id: str,
    registry: ToolRegistry | None = None,
) -> DocumentJobDetail:
    if not task_runtime_available(settings):
        raise DocumentJobUnavailableError("Document Job 运行时尚未开放。")
    source = get_owned_artifact(
        db,
        artifact_id=payload.source_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    if source.factory_id != payload.factory_id:
        raise DocumentJobNotFoundError("文档 Artifact 不存在。")
    if source.sha256 != payload.source_sha256:
        raise DocumentJobConflictError("源文件哈希已变化，请重新预检。")
    preflight = preflight_owned_document(
        db,
        payload=payload,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
        settings=settings,
    )
    supported_types = available_document_job_types(
        local_translation_available=bool(
            document_translation_status(settings.document_translation_model_dir)[
                "available"
            ]
        ),
        office_renderer_available=office_renderer_available(settings),
    )
    if payload.job_type not in supported_types or preflight.route_decision not in {
        DocumentRouteDecision.TASK_LOCAL,
        DocumentRouteDecision.TASK_AI_ENHANCED,
    }:
        raise DocumentJobUnavailableError("当前文档任务管线尚未开放。")

    active_registry = registry or build_document_tool_registry(settings)
    if any(active_registry.resolve(name) is None for name in DOCUMENT_STUDIO_TOOL_NAMES):
        raise DocumentJobUnavailableError("Document Job 工具运行时不可用。")
    try:
        skill_registry = SkillRegistry(active_registry)
        skill_registry.resolve(DOCUMENT_STUDIO_PRIMARY_SKILLS[payload.job_type], "1.0.0")
    except SkillRegistryError as exc:
        raise DocumentJobUnavailableError("Document Job Skill 运行时不可用。") from exc

    arguments = _task_arguments(payload).model_dump(mode="json")
    step_contracts = (
        ("inspect_document", AITaskType.READ, "检查源文档", "artifacts.inspect_document"),
        ("extract_document", AITaskType.PREVIEW, "提取文档内容", "artifacts.extract_document"),
        ("reconcile_document", AITaskType.PREVIEW, "核对文档结构", "artifacts.reconcile_document"),
        ("review_document", AITaskType.PREVIEW, "检查人工复核项", "artifacts.review_document"),
        ("render_document", AITaskType.PREVIEW, "生成派生文档", "artifacts.render_document"),
        ("verify_document", AITaskType.READ, "验证派生结果", "artifacts.verify_document"),
    )
    task_payload = AITaskCreate(
        task_type=AITaskType.PREVIEW,
        factory_scope=payload.factory_id,
        primary_skill_id=DOCUMENT_STUDIO_PRIMARY_SKILLS[payload.job_type],
        primary_skill_version="1.0.0",
        proposed_tool_names=DOCUMENT_STUDIO_TOOL_NAMES,
        proposed_max_steps=6,
        proposed_maximum_risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        proposed_token_budget=2_000,
        input_hash=hashlib.sha256(_canonical_input(payload).encode("utf-8")).hexdigest(),
        idempotency_key=payload.idempotency_key,
        steps=tuple(
            AITaskStepCreate(
                key=key,
                kind=kind,
                label=label,
                tool_name=tool_name,
                arguments=arguments,
            )
            for key, kind, label, tool_name in step_contracts
        ),
    )
    try:
        task = create_task(
            db,
            payload=task_payload,
            user=user,
            settings=settings,
            registry=active_registry,
            skill_registry=skill_registry,
            server_page_context=None,
            allowed_factory_scopes=allowed_factory_ids,
            request_id=request_id,
        )
    except AITaskError as exc:
        if exc.status_code == 409:
            raise DocumentJobConflictError("文档任务幂等键已被其他请求使用。") from exc
        raise DocumentJobError("文档任务请求无效。") from exc
    return document_job_detail(
        db,
        task=task,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )


def _task_arguments_from_record(db: Session, task: AITask) -> DocumentStudioTaskOptions:
    step = db.scalar(
        select(AITaskStep)
        .where(AITaskStep.task_id == task.id)
        .order_by(AITaskStep.ordinal.asc())
        .limit(1)
    )
    if step is None:
        raise DocumentJobNotFoundError("文档任务不存在。")
    try:
        return DocumentStudioTaskOptions.model_validate_json(step.arguments_json)
    except Exception as exc:
        raise DocumentJobNotFoundError("文档任务不存在。") from exc


def _step_result_artifact_id(
    db: Session, task: AITask, step_key: str
) -> str | None:
    step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task.id,
            AITaskStep.step_key == step_key,
        )
    )
    if step is None or not step.result_metadata_json:
        return None
    try:
        metadata = json.loads(step.result_metadata_json)
    except json.JSONDecodeError:
        return None
    artifact_id = metadata.get("result_artifact_id") if isinstance(metadata, dict) else None
    return artifact_id if isinstance(artifact_id, str) else None


def _job_id(task_id: str) -> str:
    return f"docjob-{task_id.removeprefix('aitask-')}"


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _optional_date(value: str) -> datetime | None:
    return _date(value) if value else None


def _require_document_task(task: AITask) -> None:
    if task.primary_skill_id not in set(DOCUMENT_STUDIO_PRIMARY_SKILLS.values()):
        raise DocumentJobNotFoundError("文档任务不存在。")


def _task_source_record(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
) -> AIArtifact:
    source = db.get(AIArtifact, artifact_id)
    if (
        source is None
        or source.owner_user_id != user.id
        or source.factory_id not in allowed_factory_ids
        or (
            "*" not in user.factory_scopes
            and source.factory_id not in user.factory_scopes
        )
    ):
        raise DocumentJobNotFoundError("文档任务不存在。")
    return source


def document_job_detail(
    db: Session,
    *,
    task: AITask,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage | None = None,
) -> DocumentJobDetail:
    _require_document_task(task)
    arguments = _task_arguments_from_record(db, task)
    source = _task_source_record(
        db,
        artifact_id=arguments.source_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    if source.factory_id != task.factory_scope or arguments.factory_id != task.factory_scope:
        raise DocumentJobNotFoundError("文档任务不存在。")
    snapshot_id = _step_result_artifact_id(
        db, task, "reconcile_document"
    ) or _step_result_artifact_id(db, task, "extract_document")
    quality_id = _step_result_artifact_id(db, task, "review_document")
    result_id = _step_result_artifact_id(db, task, "verify_document")
    if result_id is None:
        result_id = _step_result_artifact_id(db, task, "render_document")
    quality_report = None
    snapshot_sha = None
    if storage is not None and snapshot_id is not None:
        try:
            _, snapshot = load_metadata_artifact(
                db,
                artifact_id=snapshot_id,
                user=user,
                allowed_factory_ids=allowed_factory_ids,
                storage=storage,
                model=DocumentSnapshot,
            )
            snapshot_sha = hashlib.sha256(
                snapshot.model_dump_json(exclude_none=True).encode("utf-8")
            ).hexdigest()
        except ArtifactNotFoundError:
            snapshot_id = None
    if storage is not None and quality_id is not None:
        try:
            _, quality_report = load_metadata_artifact(
                db,
                artifact_id=quality_id,
                user=user,
                allowed_factory_ids=allowed_factory_ids,
                storage=storage,
                model=DocumentQualityReport,
            )
        except ArtifactNotFoundError:
            quality_id = None
    state = map_task_state(task.state)
    failure_code = task.failure_code
    if source.status != "ACTIVE":
        state = DocumentJobState.EXPIRED
        result_id = None
        snapshot_id = None
        quality_id = None
        quality_report = None
        snapshot_sha = None
    if result_id is not None:
        result = db.get(AIArtifact, result_id)
        if result is None or result.status == "EXPIRED":
            state = DocumentJobState.EXPIRED
            result_id = None
    if state == DocumentJobState.COMPLETED and result_id is None:
        state = DocumentJobState.FAILED
        failure_code = "DOCUMENT_RESULT_MISSING"
    return DocumentJobDetail(
        id=_job_id(task.id),
        task_id=task.id,
        operation_id=arguments.operation_id,
        factory_id=task.factory_scope,
        source_artifact_id=source.id,
        source_filename=source.original_filename,
        job_type=arguments.job_type,
        processing_mode=arguments.processing_mode,
        state=state,
        revision=task.revision,
        created_at=_date(task.created_at),
        updated_at=_date(task.updated_at),
        terminal_at=_optional_date(task.terminal_at),
        page_range=arguments.page_range,
        snapshot_artifact_id=snapshot_id,
        result_artifact_id=result_id,
        quality_report_artifact_id=quality_id,
        quality_report=quality_report,
        snapshot_sha256=snapshot_sha,
        input_hash=task.input_hash,
        runtime_plan_hash=task.runtime_plan_hash,
        failure_code=failure_code if state == DocumentJobState.FAILED else "",
    )


def document_job_snapshot(
    db: Session,
    *,
    task_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
) -> DocumentSnapshot:
    detail = get_document_job(
        db,
        task_id=task_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )
    if detail.snapshot_artifact_id is None:
        raise DocumentJobConflictError("文档任务尚未生成可查看的 Snapshot。")
    try:
        _, snapshot = load_metadata_artifact(
            db,
            artifact_id=detail.snapshot_artifact_id,
            user=user,
            allowed_factory_ids=allowed_factory_ids,
            storage=storage,
            model=DocumentSnapshot,
        )
        return snapshot
    except ArtifactNotFoundError as exc:
        raise DocumentJobConflictError("文档 Snapshot 已过期或不存在。") from exc


def get_document_job(
    db: Session,
    *,
    task_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage | None = None,
) -> DocumentJobDetail:
    try:
        task = get_owned_task(
            db,
            task_id=task_id,
            user=user,
            allowed_factory_scopes=allowed_factory_ids,
        )
        return document_job_detail(
            db,
            task=task,
            user=user,
            allowed_factory_ids=allowed_factory_ids,
            storage=storage,
        )
    except (AITaskNotFoundError, ArtifactNotFoundError) as exc:
        raise DocumentJobNotFoundError("文档任务不存在。") from exc


def list_document_jobs(
    db: Session,
    *,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    factory_id: str | None,
    limit: int,
    storage: ArtifactStorage | None = None,
) -> DocumentJobList:
    query = select(AITask).where(
        AITask.owner_user_id == user.id,
        AITask.primary_skill_id.in_(tuple(DOCUMENT_STUDIO_PRIMARY_SKILLS.values())),
    )
    if factory_id is not None:
        if factory_id not in allowed_factory_ids:
            raise DocumentJobNotFoundError("文档任务不存在。")
        query = query.where(AITask.factory_scope == factory_id)
    records = list(
        db.scalars(query.order_by(AITask.updated_at.desc(), AITask.id.desc()).limit(limit)).all()
    )
    items: list[DocumentJobSummary] = []
    for task in records:
        try:
            detail = document_job_detail(
                db,
                task=task,
                user=user,
                allowed_factory_ids=allowed_factory_ids,
                storage=storage,
            )
        except (DocumentJobError, ArtifactNotFoundError):
            continue
        items.append(
            DocumentJobSummary(
                **{
                    name: getattr(detail, name)
                    for name in DocumentJobSummary.model_fields
                }
            )
        )
    return DocumentJobList(items=tuple(items))


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def document_job_operational_metrics(
    db: Session,
    *,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    factory_id: str | None,
    storage: ArtifactStorage,
) -> DocumentJobOperationalMetrics:
    query = select(AITask).where(
        AITask.owner_user_id == user.id,
        AITask.primary_skill_id.in_(tuple(DOCUMENT_STUDIO_PRIMARY_SKILLS.values())),
        AITask.factory_scope.in_(tuple(allowed_factory_ids)),
    )
    if factory_id is not None:
        if factory_id not in allowed_factory_ids:
            raise DocumentJobNotFoundError("厂区文档指标不存在。")
        query = query.where(AITask.factory_scope == factory_id)
    tasks = list(
        db.scalars(query.order_by(AITask.created_at.desc()).limit(500)).all()
    )
    completed = failed = cancelled = active = reviews = cloud_pages = 0
    durations: list[int] = []
    confidences: list[float] = []
    for task in tasks:
        state = map_task_state(task.state)
        if state == DocumentJobState.COMPLETED:
            completed += 1
        elif state == DocumentJobState.FAILED:
            failed += 1
        elif state == DocumentJobState.CANCELLED:
            cancelled += 1
        else:
            active += 1
        if state == DocumentJobState.REVIEW_REQUIRED:
            reviews += 1
        if task.terminal_at:
            started = _date(task.created_at)
            terminal = _date(task.terminal_at)
            durations.append(max(0, round((terminal - started).total_seconds() * 1000)))
        steps = list(
            db.scalars(select(AITaskStep).where(AITaskStep.task_id == task.id)).all()
        )
        for step in steps:
            try:
                metadata = json.loads(step.result_metadata_json or "{}")
            except json.JSONDecodeError:
                continue
            metrics = metadata.get("document_metrics")
            if isinstance(metrics, dict):
                value = metrics.get("cloud_page_count")
                if isinstance(value, int) and value >= 0:
                    cloud_pages += value
        quality_id = _step_result_artifact_id(db, task, "review_document")
        if quality_id is not None:
            try:
                _, report = load_metadata_artifact(
                    db,
                    artifact_id=quality_id,
                    user=user,
                    allowed_factory_ids=allowed_factory_ids,
                    storage=storage,
                    model=DocumentQualityReport,
                )
                confidences.append(report.overall_confidence)
            except ArtifactNotFoundError:
                pass
    total = len(tasks)
    terminal_total = completed + failed
    return DocumentJobOperationalMetrics(
        total_jobs=total,
        completed_jobs=completed,
        failed_jobs=failed,
        cancelled_jobs=cancelled,
        active_jobs=active,
        review_jobs=reviews,
        success_rate=round(completed / terminal_total, 6) if terminal_total else 0,
        review_rate=round(reviews / total, 6) if total else 0,
        p50_duration_ms=_percentile(durations, 0.5),
        p95_duration_ms=_percentile(durations, 0.95),
        cloud_page_count=cloud_pages,
        average_quality_confidence=(
            round(sum(confidences) / len(confidences), 6) if confidences else None
        ),
    )


def document_job_events(
    db: Session,
    *,
    task: AITask,
    after: int,
    limit: int,
) -> DocumentJobEventPage:
    _require_document_task(task)
    page = read_task_events(db, task_id=task.id, after=after, limit=limit)
    step_keys = {
        step.id: step.step_key
        for step in db.scalars(select(AITaskStep).where(AITaskStep.task_id == task.id)).all()
    }
    current_state = map_task_state(task.state)
    items: list[DocumentJobEvent] = []
    for event in page.items:
        state = current_state
        if event.step_id is None and event.transition_to:
            try:
                state = map_task_state(event.transition_to.value)
            except (KeyError, ValueError):
                state = current_state
        elif event.transition_to == AITaskStepState.WAITING_INPUT:
            state = DocumentJobState.REVIEW_REQUIRED
        elif event.transition_to == AITaskStepState.VERIFYING:
            state = DocumentJobState.VERIFYING
        elif event.transition_to == AITaskStepState.FAILED:
            state = DocumentJobState.FAILED
        elif event.transition_to == AITaskStepState.CANCELLED:
            state = DocumentJobState.CANCELLED
        items.append(
            DocumentJobEvent(
                sequence=event.sequence,
                task_id=task.id,
                step_key=step_keys.get(event.step_id) if event.step_id else None,
                state=state,
                reason_code=event.reason_code,
                created_at=event.created_at,
            )
        )
    return DocumentJobEventPage(items=tuple(items), next_after=page.next_after)


def cancel_document_job(
    db: Session,
    *,
    task: AITask,
    user: AuthContext,
    expected_revision: int,
    reason_code: str,
    settings: Settings,
) -> None:
    _require_document_task(task)
    try:
        request_task_cancellation(
            db,
            task=task,
            user=user,
            expected_revision=expected_revision,
            reason_code=reason_code,
            settings=settings,
        )
        db.commit()
    except AITaskError as exc:
        db.rollback()
        raise DocumentJobConflictError("文档任务状态已变化，请刷新后重试。") from exc


def _replace_step_result_artifact(
    step: AITaskStep, *, source: AIArtifact, result: AIArtifact, review_required: bool
) -> None:
    try:
        metadata = json.loads(step.result_metadata_json) if step.result_metadata_json else {}
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "source_artifact_id": source.id,
            "source_sha256": source.sha256,
            "result_artifact_id": result.id,
            "result_file_name": result.original_filename,
            "review_required": review_required,
            "artifact_refs": [
                {"artifact_id": source.id, "role": "SOURCE", "sha256": source.sha256},
                {
                    "artifact_id": result.id,
                    "role": "RESULT",
                    "sha256": result.sha256,
                    "parser_version": result.parser_version,
                    "model_version": result.model_version,
                },
            ],
        }
    )
    step.result_metadata_json = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    step.result_hash = hashlib.sha256(step.result_metadata_json.encode()).hexdigest()


def review_document_job(
    db: Session,
    *,
    task: AITask,
    payload: DocumentJobReviewRequest,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    scanner: ArtifactScanner,
    settings: Settings,
) -> None:
    _require_document_task(task)
    if task.state != "WAITING_INPUT" or task.revision != payload.expected_revision:
        raise DocumentJobConflictError("复核任务状态已变化，请刷新后重试。")
    if (
        task.input_hash != payload.expected_input_hash
        or task.runtime_plan_hash != payload.expected_runtime_plan_hash
    ):
        raise DocumentJobConflictError("复核任务绑定已变化，请重新打开任务。")
    arguments = _task_arguments_from_record(db, task)
    source = _task_source_record(
        db,
        artifact_id=arguments.source_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    extract_step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task.id,
            AITaskStep.step_key == "extract_document",
        )
    )
    review_step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task.id,
            AITaskStep.step_key == "review_document",
        )
    )
    reconcile_step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task.id,
            AITaskStep.step_key == "reconcile_document",
        )
    )
    reconcile_snapshot_id = _step_result_artifact_id(db, task, "reconcile_document")
    snapshot_id = reconcile_snapshot_id or _step_result_artifact_id(
        db, task, "extract_document"
    )
    snapshot_step = reconcile_step if reconcile_snapshot_id else extract_step
    quality_id = _step_result_artifact_id(db, task, "review_document")
    if (
        extract_step is None
        or snapshot_step is None
        or review_step is None
        or review_step.state != AITaskStepState.WAITING_INPUT.value
        or snapshot_id is None
        or quality_id is None
    ):
        raise DocumentJobConflictError("文档任务没有可提交的复核项。")
    _, snapshot = load_metadata_artifact(
        db,
        artifact_id=snapshot_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
        model=DocumentSnapshot,
    )
    _, report = load_metadata_artifact(
        db,
        artifact_id=quality_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
        model=DocumentQualityReport,
    )
    patch_issue_ids = {item.issue_id for item in payload.patches}
    report_issue_ids = {item.issue_id for item in report.issues}
    if patch_issue_ids != report_issue_ids or any(
        item.expected_snapshot_sha256 != report.snapshot_sha256
        for item in payload.patches
    ):
        raise DocumentJobConflictError("复核项或 Snapshot 已变化，请刷新后重试。")
    try:
        patched = apply_review_patches(
            snapshot,
            patches=payload.patches,
            issue_targets={item.issue_id: item.target_id for item in report.issues},
        )
    except DocumentReviewError as exc:
        raise DocumentJobConflictError(str(exc)) from exc
    patched_report = build_quality_report(
        patched,
        review_threshold=arguments.options.review_threshold,
    )
    if patched_report.review_required:
        raise DocumentJobConflictError("仍有未解决的复核项，不能恢复任务。")
    patched_artifact = create_metadata_artifact(
        db,
        parent=source,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        operation_id=arguments.operation_id,
        kind="document-snapshot",
        revision=patched.revision,
        value=patched,
        storage=storage,
        scanner=scanner,
        settings=settings,
        parser_version="document-studio-review-v1",
    )
    quality_artifact = create_metadata_artifact(
        db,
        parent=source,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        operation_id=arguments.operation_id,
        kind="document-quality",
        revision=patched.revision,
        value=patched_report,
        storage=storage,
        scanner=scanner,
        settings=settings,
        parser_version="document-studio-review-v1",
    )
    _replace_step_result_artifact(
        snapshot_step,
        source=source,
        result=patched_artifact,
        review_required=False,
    )
    _replace_step_result_artifact(
        review_step,
        source=source,
        result=quality_artifact,
        review_required=False,
    )
    transition_step(
        db,
        task=task,
        step=review_step,
        requested_state=AITaskStepState.RUNNING,
        actor_type="USER",
        actor_user_id=user.id,
        reason_code="USER_DOCUMENT_REVIEW_APPLIED",
    )
    transition_step(
        db,
        task=task,
        step=review_step,
        requested_state=AITaskStepState.COMPLETED,
        actor_type="USER",
        actor_user_id=user.id,
        reason_code="USER_DOCUMENT_REVIEW_COMPLETED",
        artifacts=(
            AIArtifactReference(
                artifact_id=patched_artifact.id,
                artifact_kind="DERIVED_FILE",
                content_hash=f"sha256:{patched_artifact.sha256}",
            ),
            AIArtifactReference(
                artifact_id=quality_artifact.id,
                artifact_kind="DERIVED_FILE",
                content_hash=f"sha256:{quality_artifact.sha256}",
            ),
        ),
    )
    registry = build_document_tool_registry(settings)
    try:
        request_task_resume(
            db,
            task=task,
            user=user,
            expected_revision=payload.expected_revision,
            expected_input_hash=payload.expected_input_hash,
            expected_runtime_plan_hash=payload.expected_runtime_plan_hash,
            registry=registry,
            skill_registry=SkillRegistry(registry),
            settings=settings,
        )
        db.commit()
    except (AITaskError, SkillRegistryError) as exc:
        db.rollback()
        raise DocumentJobConflictError(
            "复核结果未能安全提交，请刷新后重试。"
        ) from exc


def retry_document_job(
    db: Session,
    *,
    task: AITask,
    user: AuthContext,
    expected_revision: int,
    settings: Settings,
) -> None:
    _require_document_task(task)
    registry = build_document_tool_registry(settings)
    try:
        skill_registry = SkillRegistry(registry)
        request_task_resume(
            db,
            task=task,
            user=user,
            expected_revision=expected_revision,
            expected_input_hash=task.input_hash,
            expected_runtime_plan_hash=task.runtime_plan_hash,
            registry=registry,
            skill_registry=skill_registry,
            settings=settings,
        )
        db.commit()
    except (AITaskError, SkillRegistryError) as exc:
        db.rollback()
        raise DocumentJobConflictError(
            "文档任务当前不可安全重试，请刷新状态或重新提交。"
        ) from exc


def document_job_result(
    db: Session,
    *,
    detail: DocumentJobDetail,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
) -> DocumentJobResult:
    if detail.state != DocumentJobState.COMPLETED or detail.result_artifact_id is None:
        raise DocumentJobConflictError("文档任务尚未生成可下载结果。")
    artifact = get_owned_artifact(
        db,
        artifact_id=detail.result_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    return DocumentJobResult(
        task_id=detail.task_id,
        artifact_id=artifact.id,
        filename=artifact.original_filename,
        mime_type=artifact.detected_mime_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        download_url=f"/api/ai/artifacts/{artifact.id}/download",
    )
