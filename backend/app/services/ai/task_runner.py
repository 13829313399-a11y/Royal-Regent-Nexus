from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_conversation import AIMessage
from app.models.ai_task import AITask, AITaskStep
from app.models.auth import AuthUser
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.preview import AIPreviewManifestV1
from app.schemas.ai.task import AIArtifactReference, AITaskState, AITaskStepState
from app.services.ai.pilot_guard import (
    AIPilotGuard,
    AIPilotGuardError,
    AIPilotLease,
    build_pilot_guard,
)
from app.services.ai.prompts.compiler import PromptCompiler
from app.services.ai.provider_factory import ProviderConfigurationError, build_provider
from app.services.ai.providers import (
    LLMProvider,
    ProviderError,
    ProviderMessage,
    ProviderToolCall,
)
from app.services.ai.providers.router import (
    build_provider_request,
    resolve_provider_route,
)
from app.services.ai.runtime.plan import RuntimePlan
from app.services.ai.runtime_gate import is_ai_runtime_disabled
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_lease import (
    AITaskLeaseError,
    TaskLease,
    release_task_lease,
    require_live_task_lease,
)
from app.services.ai.task_service import transition_step, transition_task
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import (
    ToolRegistry,
    ToolRetryPolicy,
    ToolSideEffectClass,
)
from app.services.auth import AuthContext, build_auth_context

AuthLoader = Callable[[Session, AITask, Settings], AuthContext]


class AITaskRunnerError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    result_hash: str
    metadata: dict[str, object]
    evidence: tuple[AIEvidenceReferenceV1, ...] = ()
    artifacts: tuple[AIArtifactReference, ...] = ()


async def _run_with_guard_heartbeat(
    operation: Awaitable[StepExecutionResult],
    *,
    pilot_lease: AIPilotLease,
    settings: Settings,
    timeout_seconds: float | None = None,
) -> StepExecutionResult:
    interval = min(60.0, settings.ai_guard_lease_seconds / 3)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(interval)
            pilot_lease.renew()

    runner = asyncio.create_task(
        asyncio.wait_for(
            operation,
            timeout=timeout_seconds or settings.ai_request_timeout_seconds,
        ),
        name="ai-guarded-step",
    )
    guard_heartbeat = asyncio.create_task(
        heartbeat(),
        name="ai-guard-lease-heartbeat",
    )
    try:
        done, _pending = await asyncio.wait(
            {runner, guard_heartbeat},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if guard_heartbeat in done:
            error = guard_heartbeat.exception()
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
            if error is not None:
                raise error
            raise AITaskRunnerError("TASK_GUARD_HEARTBEAT_STOPPED")
        return await runner
    finally:
        if not runner.done():
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
        guard_heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await guard_heartbeat


def _hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _now_text(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_plan(task: AITask) -> RuntimePlan:
    try:
        return RuntimePlan.model_validate_json(task.runtime_plan_json)
    except ValidationError as exc:
        raise AITaskRunnerError("TASK_PLAN_CORRUPT") from exc


def _parse_page_context(task: AITask):
    from app.schemas.ai.context import AIServerPageContext

    try:
        payload = json.loads(task.server_page_context_json)
        return None if payload is None else AIServerPageContext.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AITaskRunnerError("TASK_CONTEXT_CORRUPT") from exc


def _load_current_user(db: Session, task: AITask, settings: Settings):
    row = db.get(AuthUser, task.owner_user_id)
    if row is None or row.status != "active" or row.force_password_change:
        raise AITaskRunnerError("TASK_OWNER_UNAVAILABLE")
    user = build_auth_context(db, row)
    try:
        guard = build_pilot_guard()
        access = guard.evaluate_access(user, settings)
        allowed_factories = guard.configured_factory_ids(settings)
    except AIPilotGuardError as exc:
        if exc.code == "AI_GUARD_UNAVAILABLE":
            raise AITaskRunnerError(
                "TASK_AI_GUARD_UNAVAILABLE",
                retryable=True,
            ) from exc
        raise AITaskRunnerError("TASK_PILOT_ACCESS_CHANGED") from exc
    if access.status == "DISABLED" and settings.ai_enabled:
        raise AITaskRunnerError("TASK_RUNTIME_DISABLED", retryable=True)
    if not access.granted or task.factory_scope not in allowed_factories:
        raise AITaskRunnerError("TASK_PILOT_ACCESS_CHANGED")
    return user


def _safe_tool_metadata(
    outcome,
) -> tuple[
    dict[str, object],
    tuple[AIEvidenceReferenceV1, ...],
    tuple[AIArtifactReference, ...],
]:
    try:
        envelope = json.loads(outcome.provider_output_json)
        evidence_raw = envelope.get("evidence") or []
        data = envelope.get("data")
        evidence = tuple(
            AIEvidenceReferenceV1.model_validate(item) for item in evidence_raw
        )
    except (json.JSONDecodeError, ValidationError, TypeError, AttributeError) as exc:
        raise AITaskRunnerError("TASK_TOOL_METADATA_INVALID") from exc
    metadata: dict[str, object] = {
        "kind": "TOOL_RESULT",
        "tool_name": outcome.tool_name,
        "row_count": outcome.row_count,
        "field_count": outcome.field_count,
        "byte_count": outcome.byte_count,
        "truncated": outcome.truncated,
    }
    artifacts: list[AIArtifactReference] = []
    if isinstance(data, dict):
        raw_manifests: list[object] = []
        if data.get("preview_manifest") is not None:
            raw_manifests.append(data["preview_manifest"])
        run = data.get("run")
        if isinstance(run, dict) and run.get("preview_manifest") is not None:
            raw_manifests.append(run["preview_manifest"])
        runs = data.get("runs")
        if isinstance(runs, list):
            raw_manifests.extend(
                item["preview_manifest"]
                for item in runs
                if isinstance(item, dict) and item.get("preview_manifest") is not None
            )
        if raw_manifests:
            try:
                manifests = tuple(
                    AIPreviewManifestV1.model_validate(item)
                    for item in raw_manifests
                )
            except ValidationError as exc:
                raise AITaskRunnerError("TASK_TOOL_METADATA_INVALID") from exc
            if len(manifests) > 4 or len(
                {item.preview_id for item in manifests}
            ) != len(manifests):
                raise AITaskRunnerError("TASK_TOOL_METADATA_INVALID")
            metadata["preview_manifests"] = [
                item.model_dump(mode="json") for item in manifests
            ]
            preview_evidence = {
                item.evidence_id: item
                for manifest in manifests
                for item in manifest.evidence_refs
            }
            evidence = (
                *evidence,
                *(
                    item
                    for evidence_id, item in preview_evidence.items()
                    if all(existing.evidence_id != evidence_id for existing in evidence)
                ),
            )
        source_id = data.get("source_artifact_id")
        result_id = data.get("result_artifact_id")
        source_sha = data.get("source_sha256")
        if isinstance(source_id, str) and isinstance(source_sha, str):
            metadata["source_artifact_id"] = source_id
            metadata["source_sha256"] = source_sha
            artifacts.append(
                AIArtifactReference(
                    artifact_id=source_id,
                    artifact_kind=(
                        "USER_IMAGE"
                        if data.get("result_type")
                        in {
                            "vision.injection_backlog_observation.v1",
                            "vision.injection_backlog_comparison.v1",
                        }
                        else "SOURCE_FILE"
                    ),
                    content_hash=f"sha256:{source_sha}",
                )
            )
        if isinstance(source_id, str) and isinstance(result_id, str):
            metadata["result_artifact_id"] = result_id
            if isinstance(data.get("result_file_name"), str):
                metadata["result_file_name"] = data["result_file_name"]
            metadata["artifact_refs"] = [
                {
                    "artifact_id": source_id,
                    "role": "SOURCE",
                    "sha256": str(data.get("source_sha256", "")),
                },
                {
                    "artifact_id": result_id,
                    "role": "RESULT",
                    "sha256": str(data.get("result_sha256", "")),
                    "parser_version": str(data.get("parser_version", "")),
                    "model_version": str(data.get("model_version", "")),
                },
            ]
            metadata["idempotent_replay"] = data.get("idempotent_replay") is True
            result_sha = data.get("result_sha256")
            if (
                result_id != source_id
                and isinstance(result_sha, str)
            ):
                artifacts.append(
                    AIArtifactReference(
                        artifact_id=result_id,
                        artifact_kind="DERIVED_FILE",
                        content_hash=f"sha256:{result_sha}",
                    )
                )
        result_type = data.get("result_type")
        if result_type == "vision.injection_backlog_observation.v1":
            metadata["vision_observation"] = data
        elif result_type == "vision.injection_backlog_comparison.v1":
            metadata["vision_comparison"] = data
            try:
                observation_evidence = AIEvidenceReferenceV1.model_validate(
                    data["observation_evidence"]
                )
            except (KeyError, ValidationError, TypeError) as exc:
                raise AITaskRunnerError("TASK_TOOL_METADATA_INVALID") from exc
            if all(
                item.evidence_id != observation_evidence.evidence_id
                for item in evidence
            ):
                evidence = (*evidence, observation_evidence)
    return metadata, evidence, tuple(artifacts)


def _tool_replay_safe(spec) -> bool:
    return bool(
        spec is not None
        and spec.retry_policy == ToolRetryPolicy.SAFE_TRANSIENT
        and (
            (
                spec.side_effect_class == ToolSideEffectClass.NONE
                and spec.idempotency.value == "IDEMPOTENT"
            )
            or (
                spec.side_effect_class == ToolSideEffectClass.PREVIEW_STATE
                and spec.idempotency.value == "IDEMPOTENT_WITH_KEY"
            )
        )
    )


async def _execute_tool_step(
    *,
    step: AITaskStep,
    task: AITask,
    user,
    registry: ToolRegistry,
    settings: Settings,
    session_factory: Callable[[], Session],
) -> StepExecutionResult:
    spec = registry.resolve(step.tool_name)
    if spec is None or spec.version != step.tool_version:
        raise AITaskRunnerError("TASK_TOOL_VERSION_CHANGED")
    if spec.side_effect_class not in {
        ToolSideEffectClass.NONE,
        ToolSideEffectClass.PREVIEW_STATE,
    }:
        raise AITaskRunnerError("TASK_TOOL_SIDE_EFFECT_PROHIBITED")
    call = ProviderToolCall(
        call_id=f"task-{uuid4().hex}",
        name=step.tool_name,
        arguments_json=step.arguments_json,
    )
    outcome = await ToolExecutor(registry, settings).execute(
        call,
        ToolExecutionContext(
            db=None,
            user=user,
            request_id=f"task:{task.id}:step:{step.id}:attempt:{step.attempt_count}",
            page_context=_parse_page_context(task),
            session_factory=session_factory,
        ),
    )
    if not outcome.ok:
        raise AITaskRunnerError(
            outcome.error_code or "TASK_TOOL_FAILED",
            retryable=(spec.retry_policy == ToolRetryPolicy.SAFE_TRANSIENT),
        )
    metadata, evidence, artifacts = _safe_tool_metadata(outcome)
    return StepExecutionResult(
        result_hash=_hash(outcome.provider_output_json),
        metadata=metadata,
        evidence=evidence,
        artifacts=artifacts,
    )


async def _execute_model_step(
    *,
    step: AITaskStep,
    task: AITask,
    user,
    registry: ToolRegistry,
    skill_registry: SkillRegistry,
    settings: Settings,
    provider: LLMProvider,
    pilot_lease: AIPilotLease,
) -> StepExecutionResult:
    plan = _parse_plan(task)
    context = ToolExecutionContext(
        db=None,
        user=user,
        request_id=f"task:{task.id}:step:{step.id}:attempt:{step.attempt_count}",
        page_context=_parse_page_context(task),
    )
    skill = skill_registry.resolve(plan.primary_skill_id, plan.primary_skill_version)
    compiled = PromptCompiler(skill_registry).compile(plan, context)
    user_text = "Execute the bounded Task step and return a concise result."
    if task.input_message_id:
        task_db = object_session(task)
        if task_db is None:
            raise AITaskRunnerError("TASK_SESSION_UNAVAILABLE")
        with task_db.no_autoflush:
            message = task_db.get(AIMessage, task.input_message_id)
        if message is None or message.conversation_id != task.conversation_id:
            raise AITaskRunnerError("TASK_INPUT_MESSAGE_UNAVAILABLE")
        user_text = message.body
    route = resolve_provider_route(
        settings,
        capability=skill.manifest.model_policy.capability,
        reasoning_policy=skill.manifest.model_policy.reasoning,
        legacy_model=settings.ai_default_model,
    )
    request = build_provider_request(
        route,
        request_id=context.request_id,
        input=(
            compiled.system_message,
            *compiled.data_messages,
            ProviderMessage(role="user", content=user_text),
        ),
        tools=(),
        max_output_tokens=settings.ai_pilot_max_output_tokens,
    )
    try:
        pilot_lease.mark_provider_started()
        response = await provider.generate(request)
    except ProviderError as exc:
        raise AITaskRunnerError(
            f"TASK_PROVIDER_{exc.code.value.upper()}",
            retryable=exc.retryable,
        ) from exc
    if response.tool_calls:
        raise AITaskRunnerError("TASK_PROVIDER_UNPLANNED_TOOL")
    pilot_lease.record_usage(response.usage.total_tokens)
    pilot_lease.mark_completed()
    return StepExecutionResult(
        result_hash=_hash(response.text),
        metadata={
            "kind": "MODEL_RESULT",
            "provider": provider.provider_name,
            "model": request.model,
            "response_id_hash": _hash(response.response_id)
            if response.response_id
            else "",
            "output_chars": len(response.text),
            "usage_total_tokens": response.usage.total_tokens,
        },
    )


def _can_retry(
    step: AITaskStep, error: AITaskRunnerError, registry: ToolRegistry
) -> bool:
    if (
        not error.retryable
        or not step.idempotent
        or step.attempt_count >= step.max_attempts
    ):
        return False
    if not step.tool_name:
        return step.side_effect_class == ToolSideEffectClass.NONE.value
    spec = registry.resolve(step.tool_name)
    return _tool_replay_safe(spec)


def _ensure_task_running(db: Session, task: AITask, settings: Settings) -> None:
    if task.state == AITaskState.CREATED.value:
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.UNDERSTOOD,
            actor_type="SYSTEM",
            reason_code="WORKER_UNDERSTOOD_TASK",
            settings=settings,
        )
    if task.state == AITaskState.UNDERSTOOD.value:
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.RUNNING,
            actor_type="SYSTEM",
            reason_code="WORKER_STARTED_TASK",
            settings=settings,
        )
    elif task.state in {AITaskState.PLANNED.value, AITaskState.RETRY_PENDING.value}:
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.RUNNING,
            actor_type="SYSTEM",
            reason_code="WORKER_RESUMED_TASK",
            settings=settings,
        )


def _recover_interrupted_step(
    db: Session,
    *,
    task: AITask,
    registry: ToolRegistry,
    settings: Settings,
) -> bool:
    step = db.scalar(
        select(AITaskStep)
        .where(
            AITaskStep.task_id == task.id,
            AITaskStep.state == AITaskStepState.RUNNING.value,
        )
        .order_by(AITaskStep.ordinal.asc())
        .limit(1)
    )
    if step is None:
        return True
    retry_safe = bool(step.idempotent)
    if step.tool_name:
        spec = registry.resolve(step.tool_name)
        retry_safe = bool(retry_safe and _tool_replay_safe(spec))
    else:
        retry_safe = bool(retry_safe and step.side_effect_class == "NONE")
    failure_code = (
        "TASK_WORKER_CRASH_RECOVERABLE"
        if retry_safe and step.attempt_count < step.max_attempts
        else "TASK_WORKER_CRASH_MANUAL_REVIEW"
    )
    transition_step(
        db,
        task=task,
        step=step,
        requested_state=AITaskStepState.FAILED,
        actor_type="SYSTEM",
        reason_code="WORKER_RECOVERED_EXPIRED_LEASE",
        failure_code=failure_code,
    )
    transition_task(
        db,
        task=task,
        requested_state=AITaskState.FAILED,
        actor_type="SYSTEM",
        reason_code="WORKER_RECOVERED_EXPIRED_LEASE",
        failure_code=failure_code,
        settings=settings,
    )
    if retry_safe and step.attempt_count < step.max_attempts:
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.RETRY_PENDING,
            actor_type="SYSTEM",
            reason_code="WORKER_RECOVERY_RETRY",
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.RETRY_PENDING,
            actor_type="SYSTEM",
            reason_code="WORKER_RECOVERY_RETRY",
            settings=settings,
        )
        return True
    return False


def _cancel_task(db: Session, task: AITask, settings: Settings) -> None:
    steps = list(
        db.scalars(select(AITaskStep).where(AITaskStep.task_id == task.id)).all()
    )
    for step in steps:
        if step.state in {
            AITaskStepState.PENDING.value,
            AITaskStepState.RUNNING.value,
            AITaskStepState.WAITING_INPUT.value,
        }:
            transition_step(
                db,
                task=task,
                step=step,
                requested_state=AITaskStepState.CANCELLED,
                actor_type="SYSTEM",
                reason_code="WORKER_OBSERVED_CANCEL",
            )
    transition_task(
        db,
        task=task,
        requested_state=AITaskState.CANCELLED,
        actor_type="SYSTEM",
        reason_code="WORKER_CANCELLED_TASK",
        settings=settings,
    )


async def run_claimed_task(
    *,
    session_factory: Callable[[], Session],
    lease: TaskLease,
    settings: Settings,
    registry: ToolRegistry,
    provider: LLMProvider | None = None,
    auth_loader: AuthLoader = _load_current_user,
    skill_registry: SkillRegistry | None = None,
    pilot_guard: AIPilotGuard | None = None,
) -> str:
    if is_ai_runtime_disabled(settings):
        raise AITaskRunnerError("TASK_RUNTIME_DISABLED")
    owned_provider = False
    active_provider = provider
    active_skill_registry = skill_registry or SkillRegistry(registry)
    active_pilot_guard = pilot_guard or build_pilot_guard(
        instance_id=lease.owner_instance
    )
    try:
        while True:
            with session_factory() as db:
                task = require_live_task_lease(db, lease=lease)
                if task.state == AITaskState.CANCELLING.value:
                    _cancel_task(db, task, settings)
                    db.commit()
                    release_task_lease(
                        db,
                        lease=lease,
                        reason_code="WORKER_CANCEL_COMPLETE",
                    )
                    return AITaskState.CANCELLED.value
                auth_loader(db, task, settings)
                if not _recover_interrupted_step(
                    db,
                    task=task,
                    registry=registry,
                    settings=settings,
                ):
                    db.commit()
                    release_task_lease(
                        db,
                        lease=lease,
                        reason_code="WORKER_RECOVERY_MANUAL_REVIEW",
                    )
                    return AITaskState.FAILED.value
                _ensure_task_running(db, task, settings)
                step = db.scalar(
                    select(AITaskStep)
                    .where(
                        AITaskStep.task_id == task.id,
                        AITaskStep.state.in_(
                            (
                                AITaskStepState.PENDING.value,
                                AITaskStepState.RETRY_PENDING.value,
                            )
                        ),
                    )
                    .order_by(AITaskStep.ordinal.asc())
                    .limit(1)
                )
                if step is None:
                    transition_task(
                        db,
                        task=task,
                        requested_state=AITaskState.VERIFYING,
                        actor_type="SYSTEM",
                        reason_code="WORKER_VERIFYING_TASK",
                        settings=settings,
                    )
                    transition_task(
                        db,
                        task=task,
                        requested_state=AITaskState.COMPLETED,
                        actor_type="SYSTEM",
                        reason_code="WORKER_COMPLETED_TASK",
                        settings=settings,
                    )
                    db.commit()
                    release_task_lease(
                        db,
                        lease=lease,
                        reason_code="WORKER_LEASE_COMPLETE",
                    )
                    return AITaskState.COMPLETED.value
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.RUNNING,
                    actor_type="SYSTEM",
                    reason_code="WORKER_STARTED_STEP",
                )
                step.attempt_count += 1
                step.last_attempt_id = uuid4().hex
                step.last_attempt_started_at = _now_text(business_now())
                db.commit()
                task_id = task.id
                step_id = step.id
                tool_name = step.tool_name

            try:
                with session_factory() as execution_db:
                    execution_task = require_live_task_lease(execution_db, lease=lease)
                    execution_step = execution_db.get(AITaskStep, step_id)
                    if execution_step is None:
                        raise AITaskRunnerError("TASK_STEP_UNAVAILABLE")
                    current_user = auth_loader(execution_db, execution_task, settings)
                    step_pilot_lease = active_pilot_guard.acquire(
                        user=current_user,
                        settings=settings,
                        input_chars=settings.ai_max_input_chars,
                        has_attachments=False,
                        factory_id=execution_task.factory_scope,
                    )
                    try:
                        if tool_name:
                            tool_spec = registry.resolve(tool_name)
                            if tool_spec is None:
                                raise AITaskRunnerError("TASK_TOOL_VERSION_CHANGED")
                            result = await _run_with_guard_heartbeat(
                                _execute_tool_step(
                                    step=execution_step,
                                    task=execution_task,
                                    user=current_user,
                                    registry=registry,
                                    settings=settings,
                                    session_factory=session_factory,
                                ),
                                pilot_lease=step_pilot_lease,
                                settings=settings,
                                timeout_seconds=tool_spec.timeout_seconds,
                            )
                        else:
                            if active_provider is None:
                                active_provider = build_provider(settings)
                                owned_provider = True
                            result = await _run_with_guard_heartbeat(
                                _execute_model_step(
                                    step=execution_step,
                                    task=execution_task,
                                    user=current_user,
                                    registry=registry,
                                    skill_registry=active_skill_registry,
                                    settings=settings,
                                    provider=active_provider,
                                    pilot_lease=step_pilot_lease,
                                ),
                                pilot_lease=step_pilot_lease,
                                settings=settings,
                            )
                    except ProviderConfigurationError as exc:
                        raise AITaskRunnerError(
                            "TASK_PROVIDER_CONFIGURATION"
                        ) from exc
                    finally:
                        step_pilot_lease.close()
            except Exception as exc:
                error = (
                    exc
                    if isinstance(exc, AITaskRunnerError)
                    else AITaskRunnerError(
                        f"TASK_{exc.code}", retryable=exc.retryable
                    )
                    if isinstance(exc, AIPilotGuardError)
                    else AITaskRunnerError("TASK_STEP_TIMEOUT", retryable=True)
                    if isinstance(exc, TimeoutError)
                    else AITaskRunnerError("TASK_STEP_UNEXPECTED")
                )
                with session_factory() as db:
                    task = require_live_task_lease(db, lease=lease)
                    step = db.get(AITaskStep, step_id)
                    if step is None:
                        raise
                    if task.state == AITaskState.CANCELLING.value:
                        _cancel_task(db, task, settings)
                        db.commit()
                        release_task_lease(
                            db,
                            lease=lease,
                            reason_code="WORKER_CANCEL_COMPLETE",
                        )
                        return AITaskState.CANCELLED.value
                    step.last_attempt_finished_at = _now_text(business_now())
                    failure_code = (
                        error.code
                        if error.code.startswith("TASK_")
                        else "TASK_STEP_FAILED"
                    )
                    transition_step(
                        db,
                        task=task,
                        step=step,
                        requested_state=AITaskStepState.FAILED,
                        actor_type="SYSTEM",
                        reason_code="WORKER_STEP_FAILED",
                        failure_code=failure_code,
                    )
                    transition_task(
                        db,
                        task=task,
                        requested_state=AITaskState.FAILED,
                        actor_type="SYSTEM",
                        reason_code="WORKER_TASK_FAILED",
                        failure_code=failure_code,
                        settings=settings,
                    )
                    if _can_retry(step, error, registry):
                        transition_step(
                            db,
                            task=task,
                            step=step,
                            requested_state=AITaskStepState.RETRY_PENDING,
                            actor_type="SYSTEM",
                            reason_code="WORKER_RETRY_SCHEDULED",
                        )
                        transition_task(
                            db,
                            task=task,
                            requested_state=AITaskState.RETRY_PENDING,
                            actor_type="SYSTEM",
                            reason_code="WORKER_RETRY_SCHEDULED",
                            settings=settings,
                        )
                        retry_at = business_now() + timedelta(
                            seconds=5 * step.attempt_count
                        )
                        db.commit()
                        release_task_lease(
                            db,
                            lease=lease,
                            reason_code="WORKER_RETRY_SCHEDULED",
                            next_attempt_at=retry_at,
                        )
                        return AITaskState.RETRY_PENDING.value
                    db.commit()
                    release_task_lease(
                        db,
                        lease=lease,
                        reason_code="WORKER_LEASE_FAILED",
                    )
                    return AITaskState.FAILED.value

            with session_factory() as db:
                task = require_live_task_lease(db, lease=lease)
                step = db.get(AITaskStep, step_id)
                if task.id != task_id or step is None:
                    raise AITaskLeaseError("Task or Step changed during execution")
                if task.state == AITaskState.CANCELLING.value:
                    _cancel_task(db, task, settings)
                    db.commit()
                    release_task_lease(
                        db,
                        lease=lease,
                        reason_code="WORKER_CANCEL_COMPLETE",
                    )
                    return AITaskState.CANCELLED.value
                step.last_attempt_finished_at = _now_text(business_now())
                step.result_hash = result.result_hash
                step.result_metadata_json = json.dumps(
                    result.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.COMPLETED,
                    actor_type="SYSTEM",
                    reason_code="WORKER_COMPLETED_STEP",
                    evidence=result.evidence,
                    artifacts=result.artifacts,
                )
                db.commit()
    finally:
        if owned_provider and active_provider is not None:
            await active_provider.aclose()


def fail_claimed_task(
    *,
    session_factory: Callable[[], Session],
    lease: TaskLease,
    settings: Settings,
    failure_code: str,
) -> str:
    """Close a deterministic preflight failure without leaving a reclaim loop."""
    stable_code = failure_code if failure_code.startswith("TASK_") else "TASK_FAILED"
    with session_factory() as db:
        task = require_live_task_lease(db, lease=lease)
        if task.state == AITaskState.CANCELLING.value:
            _cancel_task(db, task, settings)
            db.commit()
            release_task_lease(
                db,
                lease=lease,
                reason_code="WORKER_CANCEL_COMPLETE",
            )
            return AITaskState.CANCELLED.value
        _ensure_task_running(db, task, settings)
        steps = list(
            db.scalars(select(AITaskStep).where(AITaskStep.task_id == task.id)).all()
        )
        for step in steps:
            if step.state == AITaskStepState.PENDING.value:
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.CANCELLED,
                    actor_type="SYSTEM",
                    reason_code="WORKER_PREFLIGHT_FAILED",
                )
            elif step.state == AITaskStepState.RUNNING.value:
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.FAILED,
                    actor_type="SYSTEM",
                    reason_code="WORKER_PREFLIGHT_FAILED",
                    failure_code=stable_code,
                )
            elif step.state == AITaskStepState.RETRY_PENDING.value:
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.RUNNING,
                    actor_type="SYSTEM",
                    reason_code="WORKER_PREFLIGHT_RECHECK",
                )
                transition_step(
                    db,
                    task=task,
                    step=step,
                    requested_state=AITaskStepState.FAILED,
                    actor_type="SYSTEM",
                    reason_code="WORKER_PREFLIGHT_FAILED",
                    failure_code=stable_code,
                )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.FAILED,
            actor_type="SYSTEM",
            reason_code="WORKER_PREFLIGHT_FAILED",
            failure_code=stable_code,
            settings=settings,
        )
        db.commit()
        release_task_lease(
            db,
            lease=lease,
            reason_code="WORKER_LEASE_FAILED",
        )
        return AITaskState.FAILED.value


async def run_with_heartbeat(
    *,
    session_factory: Callable[[], Session],
    lease: TaskLease,
    settings: Settings,
    registry: ToolRegistry,
    provider: LLMProvider | None = None,
    auth_loader: AuthLoader = _load_current_user,
    skill_registry: SkillRegistry | None = None,
    pilot_guard: AIPilotGuard | None = None,
) -> str:
    from app.services.ai.task_lease import renew_task_lease

    stop = asyncio.Event()

    async def heartbeat() -> None:
        current = lease
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.ai_task_worker_heartbeat_seconds,
                )
            except TimeoutError:
                with session_factory() as db:
                    current = renew_task_lease(
                        db,
                        lease=current,
                        settings=settings,
                    )

    heartbeat_task = asyncio.create_task(
        heartbeat(), name=f"task-heartbeat:{lease.task_id}"
    )
    runner_task = asyncio.create_task(
        run_claimed_task(
            session_factory=session_factory,
            lease=lease,
            settings=settings,
            registry=registry,
            provider=provider,
            auth_loader=auth_loader,
            skill_registry=skill_registry,
            pilot_guard=pilot_guard,
        ),
        name=f"task-runner:{lease.task_id}",
    )
    try:
        done, _pending = await asyncio.wait(
            {runner_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            heartbeat_error = heartbeat_task.exception()
            if heartbeat_error is not None:
                runner_task.cancel()
                with suppress(asyncio.CancelledError):
                    await runner_task
                raise heartbeat_error
        return await runner_task
    finally:
        stop.set()
        if not heartbeat_task.done():
            await heartbeat_task
