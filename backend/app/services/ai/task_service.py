from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_conversation import AIMessage
from app.models.ai_task import AITask, AITaskStep
from app.models.auth import AuthAuditLog
from app.schemas.ai.context import AIServerPageContext
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.task import (
    AIArtifactReference,
    AITaskCreate,
    AITaskData,
    AITaskEventType,
    AITaskListPage,
    AITaskRuntimePlanData,
    AITaskState,
    AITaskStepData,
    AITaskStepState,
    AITaskSummaryData,
    AITaskType,
    AITaskWorkerStatus,
)
from app.schemas.ai.tool import AIToolRiskLevel
from app.services.ai.conversation_service import (
    ConversationError,
    get_owned_conversation,
)
from app.services.ai.runtime.plan import RuntimePlan, RuntimePlanBuilder
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_events import append_task_event
from app.services.ai.task_state_machine import (
    TERMINAL_TASK_STATES,
    AITaskTransitionError,
    require_step_transition,
    require_task_transition,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import (
    ToolIdempotency,
    ToolRegistry,
    ToolSideEffectClass,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext, authorization_decision

_REASON_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,95}")
_TASK_TYPE_ORDER = {
    AITaskType.READ: 0,
    AITaskType.COMPUTE: 1,
    AITaskType.SIMULATE: 2,
    AITaskType.PREVIEW: 3,
}
_RISK_ORDER = {
    AIToolRiskLevel.READ_ONLY: 0,
    AIToolRiskLevel.PREVIEW_WITH_AUDIT: 1,
    AIToolRiskLevel.CONSEQUENTIAL_WRITE: 2,
    AIToolRiskLevel.HIGH_RISK_WRITE: 3,
}


class AITaskError(ValueError):
    code = "AI_TASK_INVALID"
    status_code = 422
    public_message = "AI 任务请求无效。"


class AITaskNotFoundError(AITaskError):
    code = "AI_TASK_NOT_FOUND"
    status_code = 404
    public_message = "AI 任务不存在。"


class AITaskConflictError(AITaskError):
    code = "AI_TASK_CONFLICT"
    status_code = 409
    public_message = "AI 任务状态已变化，请刷新后重试。"


class AITaskTransitionConflictError(AITaskConflictError):
    code = "AI_TASK_INVALID_TRANSITION"
    public_message = "当前 AI 任务状态不允许此操作。"


class AITaskResumeError(AITaskConflictError):
    code = "AI_TASK_RESUME_REVALIDATION_FAILED"
    public_message = "AI 任务当前无法恢复；权限、版本或输入校验已变化。"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_text(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def _optional_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _worker_status(
    record: AITask, *, now: datetime | None = None
) -> AITaskWorkerStatus:
    current = now or business_now()
    lease_expires_at = _optional_datetime(record.lease_expires_at)
    next_attempt_at = _optional_datetime(record.next_attempt_at)
    if (
        record.lease_token
        and lease_expires_at is not None
        and lease_expires_at > current
    ):
        return AITaskWorkerStatus.LEASED
    if next_attempt_at is not None and next_attempt_at > current:
        return AITaskWorkerStatus.WAITING_RETRY
    if record.state in {
        AITaskState.CREATED.value,
        AITaskState.UNDERSTOOD.value,
        AITaskState.PLANNED.value,
        AITaskState.RUNNING.value,
        AITaskState.RETRY_PENDING.value,
    }:
        return AITaskWorkerStatus.QUEUED
    return AITaskWorkerStatus.IDLE


def _task_id() -> str:
    return f"aitask-{uuid4().hex}"


def _step_id() -> str:
    return f"aistp-{uuid4().hex}"


def _runtime_plan_json(plan: RuntimePlan) -> str:
    return _canonical_json(plan.model_dump(mode="json"))


def _server_context_json(context: AIServerPageContext | None) -> str:
    return (
        "null" if context is None else _canonical_json(context.model_dump(mode="json"))
    )


def _parse_server_context(value: str) -> AIServerPageContext | None:
    try:
        payload = json.loads(value)
        return None if payload is None else AIServerPageContext.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AITaskResumeError("stored Task page context is corrupt") from exc


def _parse_plan(value: str) -> RuntimePlan:
    try:
        return RuntimePlan.model_validate_json(value)
    except ValidationError as exc:
        raise AITaskResumeError("stored Runtime Plan is corrupt") from exc


def _required_access(
    plan: RuntimePlan, registry: ToolRegistry
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in plan.allowed_tool_names:
        spec = registry.resolve(name)
        if spec is None:
            raise AITaskError("Runtime Plan references an unknown Tool")
        if spec.required_permission is None:
            continue
        result.append(
            {
                "tool_name": spec.name,
                "permission": spec.required_permission,
                "departments": sorted(spec.allowed_departments),
            }
        )
    return result


def _tool_versions(plan: RuntimePlan, registry: ToolRegistry) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in plan.allowed_tool_names:
        spec = registry.resolve(name)
        if spec is None:
            raise AITaskError("Runtime Plan references an unknown Tool")
        versions[name] = spec.version
    return versions


def _step_contract(
    *,
    task_type: AITaskType,
    step,
    plan: RuntimePlan,
    registry: ToolRegistry,
) -> tuple[str, str, bool]:
    if _TASK_TYPE_ORDER[step.kind] > _TASK_TYPE_ORDER[task_type]:
        raise AITaskError("Task step exceeds its declared Task type")
    if step.tool_name is None:
        if step.kind in {AITaskType.READ, AITaskType.PREVIEW}:
            raise AITaskError("READ and PREVIEW steps require a registered Tool")
        return "", ToolSideEffectClass.NONE.value, True
    if step.tool_name not in plan.allowed_tool_names:
        raise AITaskError("Task step Tool is outside the Runtime Plan")
    spec = registry.resolve(step.tool_name)
    if spec is None:
        raise AITaskError("Task step Tool is unknown")
    if spec.side_effect_class not in {
        ToolSideEffectClass.NONE,
        ToolSideEffectClass.PREVIEW_STATE,
    }:
        raise AITaskError("Task step Tool has a prohibited side effect")
    if step.kind == AITaskType.PREVIEW:
        if spec.risk_level != AIToolRiskLevel.PREVIEW_WITH_AUDIT:
            raise AITaskError("PREVIEW step requires a Preview Tool")
    elif spec.risk_level != AIToolRiskLevel.READ_ONLY:
        raise AITaskError("Non-Preview step cannot use a stateful Tool")
    idempotent = spec.idempotency in {
        ToolIdempotency.IDEMPOTENT,
        ToolIdempotency.IDEMPOTENT_WITH_KEY,
    }
    return spec.version, spec.side_effect_class.value, idempotent


def _access_is_current(record: AITask, user: AuthContext) -> bool:
    if user.id != record.owner_user_id:
        return False
    if (
        "*" not in user.factory_scopes
        and record.factory_scope not in user.factory_scopes
    ):
        return False
    try:
        required = json.loads(record.required_access_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(required, list):
        return False
    for item in required:
        if not isinstance(item, dict):
            return False
        permission = item.get("permission")
        departments = item.get("departments")
        if not isinstance(permission, str) or not isinstance(departments, list):
            return False
        if not departments or not all(isinstance(value, str) for value in departments):
            return False
        if not any(
            authorization_decision(
                user,
                permission,
                record.factory_scope,
                department,
            )[0]
            for department in departments
        ):
            return False
    return True


def get_owned_task(
    db: Session,
    *,
    task_id: str,
    user: AuthContext,
    allowed_factory_scopes: frozenset[str],
) -> AITask:
    record = db.scalar(
        select(AITask).where(
            AITask.id == task_id,
            AITask.owner_user_id == user.id,
        )
    )
    if (
        record is None
        or record.factory_scope not in allowed_factory_scopes
        or not _access_is_current(record, user)
    ):
        raise AITaskNotFoundError("Task not found")
    return record


def _step_data(record: AITaskStep) -> AITaskStepData:
    try:
        result_metadata = json.loads(record.result_metadata_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AITaskError("stored Task step result metadata is corrupt") from exc
    if not isinstance(result_metadata, dict):
        raise AITaskError("stored Task step result metadata is corrupt")
    return AITaskStepData(
        id=record.id,
        task_id=record.task_id,
        ordinal=record.ordinal,
        key=record.step_key,
        kind=AITaskType(record.kind),
        label=record.label,
        state=AITaskStepState(record.state),
        tool_name=record.tool_name or None,
        tool_version=record.tool_version or None,
        arguments_hash=record.arguments_hash,
        side_effect_class=record.side_effect_class,
        idempotent=bool(record.idempotent),
        revision=record.revision,
        attempt_count=record.attempt_count,
        max_attempts=record.max_attempts,
        result_hash=record.result_hash,
        result_metadata=result_metadata,
        created_at=datetime.fromisoformat(record.created_at),
        updated_at=datetime.fromisoformat(record.updated_at),
        started_at=_optional_datetime(record.started_at),
        completed_at=_optional_datetime(record.completed_at),
        failure_code=record.failure_code,
    )


def task_data(db: Session, record: AITask) -> AITaskData:
    try:
        plan = AITaskRuntimePlanData.model_validate_json(record.runtime_plan_json)
    except ValidationError as exc:
        raise AITaskError("stored Runtime Plan is corrupt") from exc
    steps = tuple(
        _step_data(item)
        for item in db.scalars(
            select(AITaskStep)
            .where(AITaskStep.task_id == record.id)
            .order_by(AITaskStep.ordinal.asc())
        ).all()
    )
    if len(steps) != record.step_count:
        raise AITaskError("Task step count is corrupt")
    return AITaskData(
        id=record.id,
        owner_user_id=record.owner_user_id,
        conversation_id=record.conversation_id,
        input_message_id=record.input_message_id,
        factory_scope=record.factory_scope,
        task_type=AITaskType(record.task_type),
        state=AITaskState(record.state),
        maximum_risk=AIToolRiskLevel(record.maximum_risk),
        primary_skill_id=record.primary_skill_id,
        primary_skill_version=record.primary_skill_version,
        primary_skill_hash=record.primary_skill_hash,
        prompt_version=record.prompt_version,
        prompt_hash=record.prompt_hash,
        runtime_plan=plan,
        runtime_plan_hash=record.runtime_plan_hash,
        input_hash=record.input_hash,
        revision=record.revision,
        step_count=record.step_count,
        created_at=datetime.fromisoformat(record.created_at),
        updated_at=datetime.fromisoformat(record.updated_at),
        terminal_at=_optional_datetime(record.terminal_at),
        retention_expires_at=_optional_datetime(record.retention_expires_at),
        backup_delete_by=_optional_datetime(record.backup_delete_by),
        cancellation_requested_at=_optional_datetime(record.cancellation_requested_at),
        resume_requested_at=_optional_datetime(record.resume_requested_at),
        failure_code=record.failure_code,
        worker_status=_worker_status(record),
        lease_expires_at=_optional_datetime(record.lease_expires_at),
        last_heartbeat_at=_optional_datetime(record.last_heartbeat_at),
        next_attempt_at=_optional_datetime(record.next_attempt_at),
        claim_count=record.claim_count,
        steps=steps,
    )


def _summary_data(record: AITask) -> AITaskSummaryData:
    return AITaskSummaryData(
        id=record.id,
        conversation_id=record.conversation_id,
        factory_scope=record.factory_scope,
        task_type=AITaskType(record.task_type),
        state=AITaskState(record.state),
        maximum_risk=AIToolRiskLevel(record.maximum_risk),
        primary_skill_id=record.primary_skill_id,
        revision=record.revision,
        step_count=record.step_count,
        worker_status=_worker_status(record),
        created_at=datetime.fromisoformat(record.created_at),
        updated_at=datetime.fromisoformat(record.updated_at),
        terminal_at=_optional_datetime(record.terminal_at),
    )


def list_owned_tasks(
    db: Session,
    *,
    user: AuthContext,
    allowed_factory_scopes: frozenset[str],
    conversation_id: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> AITaskListPage:
    if not 1 <= limit <= 100:
        raise AITaskError("Task list limit is invalid")
    query = select(AITask).where(
        AITask.owner_user_id == user.id,
        AITask.factory_scope.in_(tuple(allowed_factory_scopes)),
    )
    if conversation_id is not None:
        query = query.where(AITask.conversation_id == conversation_id)
    if cursor:
        try:
            cursor_updated_at, cursor_id = cursor.split("|", 1)
            if not cursor_updated_at or not cursor_id:
                raise ValueError
        except ValueError as exc:
            raise AITaskError("Task list cursor is invalid") from exc
        query = query.where(
            (AITask.updated_at < cursor_updated_at)
            | ((AITask.updated_at == cursor_updated_at) & (AITask.id < cursor_id))
        )
    rows = list(
        db.scalars(
            query.order_by(AITask.updated_at.desc(), AITask.id.desc()).limit(limit + 1)
        ).all()
    )
    visible = [record for record in rows if _access_is_current(record, user)]
    selected = visible[:limit]
    next_cursor = None
    if len(visible) > limit and selected:
        last = selected[-1]
        next_cursor = f"{last.updated_at}|{last.id}"
    return AITaskListPage(
        items=tuple(_summary_data(record) for record in selected),
        next_cursor=next_cursor,
    )


def create_task(
    db: Session,
    *,
    payload: AITaskCreate,
    user: AuthContext,
    settings: Settings,
    registry: ToolRegistry,
    skill_registry: SkillRegistry,
    server_page_context: AIServerPageContext | None,
    allowed_factory_scopes: frozenset[str],
    request_id: str,
    now: datetime | None = None,
) -> AITask:
    if (
        payload.factory_scope not in ALLOWED_FACTORY_IDS
        or payload.factory_scope not in allowed_factory_scopes
        or (
            "*" not in user.factory_scopes
            and payload.factory_scope not in user.factory_scopes
        )
    ):
        raise AITaskNotFoundError("Task factory is unavailable")
    if server_page_context is not None and (
        server_page_context.verified_factory_id != payload.factory_scope
    ):
        raise AITaskError("Task page context factory is invalid")
    if payload.conversation_id is not None:
        try:
            conversation = get_owned_conversation(
                db,
                conversation_id=payload.conversation_id,
                user=user,
            )
        except ConversationError as exc:
            raise AITaskNotFoundError("Task conversation is unavailable") from exc
        if (
            conversation.factory_scope != payload.factory_scope
            or conversation.status != "ACTIVE"
        ):
            raise AITaskNotFoundError("Task conversation is unavailable")
        if payload.input_message_id is not None:
            input_message = db.scalar(
                select(AIMessage).where(
                    AIMessage.id == payload.input_message_id,
                    AIMessage.conversation_id == conversation.id,
                    AIMessage.role == "USER",
                )
            )
            if input_message is None:
                raise AITaskNotFoundError("Task input message is unavailable")

    context = ToolExecutionContext(
        db=None,
        user=user,
        request_id=request_id,
        page_context=server_page_context,
    )
    try:
        plan = RuntimePlanBuilder(skill_registry).build(
            primary_skill_id=payload.primary_skill_id,
            primary_skill_version=payload.primary_skill_version,
            supporting_skill_ids=payload.supporting_skill_ids,
            proposed_tool_names=payload.proposed_tool_names,
            proposed_max_steps=payload.proposed_max_steps,
            proposed_maximum_risk=payload.proposed_maximum_risk,
            proposed_token_budget=payload.proposed_token_budget,
            context=context,
        )
    except SkillRegistryError as exc:
        raise AITaskError("Task Runtime Plan is invalid or unauthorized") from exc
    if _RISK_ORDER[plan.maximum_risk] > _RISK_ORDER[AIToolRiskLevel.PREVIEW_WITH_AUDIT]:
        raise AITaskError("Task Runtime Plan exceeds the Preview boundary")
    if len(payload.steps) > plan.max_steps:
        raise AITaskError("Task steps exceed the Runtime Plan")

    primary = skill_registry.resolve(plan.primary_skill_id, plan.primary_skill_version)
    plan_json = _runtime_plan_json(plan)
    plan_hash = _sha256(plan_json)
    tool_versions = _tool_versions(plan, registry)
    access = _required_access(plan, registry)
    step_contracts = [
        _step_contract(
            task_type=payload.task_type,
            step=step,
            plan=plan,
            registry=registry,
        )
        for step in payload.steps
    ]
    request_payload = {
        "task_type": payload.task_type.value,
        "factory_scope": payload.factory_scope,
        "conversation_id": payload.conversation_id,
        "input_message_id": payload.input_message_id,
        "runtime_plan_hash": plan_hash,
        "input_hash": payload.input_hash,
        "page_context": (
            server_page_context.model_dump(mode="json")
            if server_page_context is not None
            else None
        ),
        "steps": [item.model_dump(mode="json") for item in payload.steps],
    }
    request_hash = _sha256(_canonical_json(request_payload))
    existing = db.scalar(
        select(AITask).where(
            AITask.owner_user_id == user.id,
            AITask.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AITaskConflictError("Task idempotency key was reused")
        return existing

    current = now or business_now()
    current_text = _now_text(current)
    record = AITask(
        id=_task_id(),
        owner_user_id=user.id,
        conversation_id=payload.conversation_id,
        input_message_id=payload.input_message_id,
        factory_scope=payload.factory_scope,
        task_type=payload.task_type.value,
        state=AITaskState.CREATED.value,
        maximum_risk=plan.maximum_risk.value,
        primary_skill_id=primary.manifest.id,
        primary_skill_version=primary.manifest.version,
        primary_skill_hash=primary.content_hash,
        prompt_version=primary.manifest.prompt_version,
        prompt_hash=primary.prompt_hash,
        runtime_plan_json=plan_json,
        runtime_plan_hash=plan_hash,
        server_page_context_json=_server_context_json(server_page_context),
        tool_versions_json=_canonical_json(tool_versions),
        required_access_json=_canonical_json(access),
        input_hash=payload.input_hash,
        idempotency_key=payload.idempotency_key,
        request_hash=request_hash,
        revision=1,
        next_event_sequence=1,
        step_count=len(payload.steps),
        created_at=current_text,
        updated_at=current_text,
        terminal_at="",
        retention_expires_at="",
        backup_delete_by="",
        cancellation_requested_at="",
        resume_requested_at="",
        failure_code="",
        lease_owner_instance="",
        lease_token="",
        lease_expires_at="",
        last_heartbeat_at="",
        next_attempt_at=current_text,
        claim_count=0,
    )
    db.add(record)
    for ordinal, (step, contract) in enumerate(
        zip(payload.steps, step_contracts, strict=True),
        start=1,
    ):
        tool_version, side_effect_class, idempotent = contract
        arguments_json = _canonical_json(step.arguments)
        db.add(
            AITaskStep(
                id=_step_id(),
                task_id=record.id,
                ordinal=ordinal,
                step_key=step.key,
                kind=step.kind.value,
                label=step.label,
                state=AITaskStepState.PENDING.value,
                tool_name=step.tool_name or "",
                tool_version=tool_version,
                arguments_json=arguments_json,
                arguments_hash=_sha256(arguments_json),
                side_effect_class=side_effect_class,
                idempotent=int(idempotent),
                revision=1,
                attempt_count=0,
                max_attempts=(1 + settings.ai_task_worker_max_recovery_retries),
                last_attempt_id="",
                last_attempt_started_at="",
                last_attempt_finished_at="",
                result_hash="",
                result_metadata_json="{}",
                created_at=current_text,
                updated_at=current_text,
                started_at="",
                completed_at="",
                failure_code="",
            )
        )
    try:
        db.flush()
        append_task_event(
            db,
            task=record,
            event_type=AITaskEventType.TASK_CREATED,
            actor_type="USER",
            actor_user_id=user.id,
            transition_to=AITaskState.CREATED.value,
            reason_code="TASK_CREATED",
            now=current,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(AITask).where(
                AITask.owner_user_id == user.id,
                AITask.idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None and replay.request_hash == request_hash:
            return replay
        raise AITaskConflictError("Task creation conflicted") from exc
    return record


def transition_task(
    db: Session,
    *,
    task: AITask,
    requested_state: AITaskState,
    actor_type: str,
    actor_user_id: str = "",
    reason_code: str,
    event_type: AITaskEventType = AITaskEventType.STATE_TRANSITION,
    expected_revision: int | None = None,
    failure_code: str = "",
    evidence: tuple[AIEvidenceReferenceV1, ...] = (),
    settings: Settings,
    now: datetime | None = None,
) -> AITask:
    if expected_revision is not None and task.revision != expected_revision:
        raise AITaskConflictError("Task revision changed")
    if not _REASON_CODE.fullmatch(reason_code):
        raise AITaskError("Task transition reason code is invalid")
    try:
        next_state = require_task_transition(task.state, requested_state.value)
    except AITaskTransitionError as exc:
        raise AITaskTransitionConflictError(str(exc)) from exc
    if next_state == AITaskState.FAILED and (
        not failure_code or not _REASON_CODE.fullmatch(failure_code)
    ):
        raise AITaskError("Failed Task requires a stable failure code")
    current = now or business_now()
    current_text = _now_text(current)
    previous = task.state
    task.state = next_state.value
    task.revision += 1
    task.updated_at = current_text
    if next_state == AITaskState.CANCELLING:
        task.cancellation_requested_at = current_text
    if next_state in TERMINAL_TASK_STATES:
        task.terminal_at = current_text
        task.retention_expires_at = _now_text(
            current + timedelta(days=settings.ai_task_retention_days)
        )
        task.backup_delete_by = _now_text(
            current
            + timedelta(
                days=(
                    settings.ai_task_retention_days
                    + settings.ai_task_backup_delete_sla_days
                )
            )
        )
    elif AITaskState(previous) in TERMINAL_TASK_STATES:
        task.terminal_at = ""
        task.retention_expires_at = ""
        task.backup_delete_by = ""
    if next_state == AITaskState.FAILED:
        task.failure_code = failure_code
    append_task_event(
        db,
        task=task,
        event_type=event_type,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        transition_from=previous,
        transition_to=next_state.value,
        reason_code=reason_code,
        evidence=evidence,
        now=current,
    )
    return task


def transition_step(
    db: Session,
    *,
    task: AITask,
    step: AITaskStep,
    requested_state: AITaskStepState,
    actor_type: str,
    actor_user_id: str = "",
    reason_code: str,
    expected_revision: int | None = None,
    failure_code: str = "",
    evidence: tuple[AIEvidenceReferenceV1, ...] = (),
    artifacts: tuple[AIArtifactReference, ...] = (),
    now: datetime | None = None,
) -> AITaskStep:
    if step.task_id != task.id:
        raise AITaskNotFoundError("Task step is unavailable")
    if expected_revision is not None and step.revision != expected_revision:
        raise AITaskConflictError("Task step revision changed")
    if not _REASON_CODE.fullmatch(reason_code):
        raise AITaskError("Task step reason code is invalid")
    try:
        next_state = require_step_transition(step.state, requested_state.value)
    except AITaskTransitionError as exc:
        raise AITaskTransitionConflictError(str(exc)) from exc
    if next_state == AITaskStepState.FAILED and (
        not failure_code or not _REASON_CODE.fullmatch(failure_code)
    ):
        raise AITaskError("Failed Task step requires a stable failure code")
    current = now or business_now()
    current_text = _now_text(current)
    previous = step.state
    step.state = next_state.value
    step.revision += 1
    step.updated_at = current_text
    if next_state == AITaskStepState.RUNNING and not step.started_at:
        step.started_at = current_text
    if next_state in {
        AITaskStepState.COMPLETED,
        AITaskStepState.CANCELLED,
        AITaskStepState.FAILED,
    }:
        step.completed_at = current_text
    elif previous == AITaskStepState.FAILED.value:
        step.completed_at = ""
    if next_state == AITaskStepState.FAILED:
        step.failure_code = failure_code
    append_task_event(
        db,
        task=task,
        event_type=AITaskEventType.STEP_STATE_TRANSITION,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        step_id=step.id,
        transition_from=previous,
        transition_to=next_state.value,
        reason_code=reason_code,
        evidence=evidence,
        artifacts=artifacts,
        now=current,
    )
    return step


def request_task_cancellation(
    db: Session,
    *,
    task: AITask,
    user: AuthContext,
    expected_revision: int,
    reason_code: str,
    settings: Settings,
    now: datetime | None = None,
) -> AITask:
    if task.state in {AITaskState.CANCELLING.value, AITaskState.CANCELLED.value}:
        return task
    return transition_task(
        db,
        task=task,
        requested_state=AITaskState.CANCELLING,
        actor_type="USER",
        actor_user_id=user.id,
        reason_code=reason_code,
        event_type=AITaskEventType.CANCEL_REQUESTED,
        expected_revision=expected_revision,
        settings=settings,
        now=now,
    )


def _revalidate_plan(
    *,
    task: AITask,
    user: AuthContext,
    registry: ToolRegistry,
    skill_registry: SkillRegistry,
) -> None:
    stored = _parse_plan(task.runtime_plan_json)
    context = ToolExecutionContext(
        db=None,
        user=user,
        request_id=f"resume:{task.id}",
        page_context=_parse_server_context(task.server_page_context_json),
    )
    try:
        primary = skill_registry.resolve(
            stored.primary_skill_id,
            stored.primary_skill_version,
        )
        rebuilt = RuntimePlanBuilder(skill_registry).build(
            primary_skill_id=stored.primary_skill_id,
            primary_skill_version=stored.primary_skill_version,
            supporting_skill_ids=stored.supporting_skill_ids,
            proposed_tool_names=stored.allowed_tool_names,
            proposed_max_steps=stored.max_steps,
            proposed_maximum_risk=stored.maximum_risk,
            proposed_token_budget=stored.token_budget,
            context=context,
        )
    except SkillRegistryError as exc:
        raise AITaskResumeError("Task Skill is no longer available") from exc
    if (
        primary.content_hash != task.primary_skill_hash
        or primary.prompt_hash != task.prompt_hash
    ):
        raise AITaskResumeError("Task Skill or Prompt version changed")
    rebuilt_json = _runtime_plan_json(rebuilt)
    if (
        _sha256(rebuilt_json) != task.runtime_plan_hash
        or rebuilt_json != task.runtime_plan_json
    ):
        raise AITaskResumeError("Task Runtime Plan changed")
    try:
        stored_versions = json.loads(task.tool_versions_json)
    except json.JSONDecodeError as exc:
        raise AITaskResumeError("Task Tool versions are corrupt") from exc
    if not isinstance(stored_versions, dict):
        raise AITaskResumeError("Task Tool versions are corrupt")
    current_versions = _tool_versions(stored, registry)
    if current_versions != stored_versions:
        raise AITaskResumeError("Task Tool versions changed")


def request_task_resume(
    db: Session,
    *,
    task: AITask,
    user: AuthContext,
    expected_revision: int,
    expected_input_hash: str,
    expected_runtime_plan_hash: str,
    registry: ToolRegistry,
    skill_registry: SkillRegistry,
    settings: Settings,
    now: datetime | None = None,
) -> AITask:
    if task.revision != expected_revision:
        raise AITaskConflictError("Task revision changed")
    if (
        task.input_hash != expected_input_hash
        or task.runtime_plan_hash != expected_runtime_plan_hash
    ):
        raise AITaskResumeError("Task freshness binding changed")
    if not _access_is_current(task, user):
        raise AITaskNotFoundError("Task access changed")
    _revalidate_plan(
        task=task,
        user=user,
        registry=registry,
        skill_registry=skill_registry,
    )
    current = now or business_now()
    if task.state == AITaskState.FAILED.value:
        failed_steps = list(
            db.scalars(
                select(AITaskStep).where(
                    AITaskStep.task_id == task.id,
                    AITaskStep.state == AITaskStepState.FAILED.value,
                )
            ).all()
        )
        if not failed_steps or any(not item.idempotent for item in failed_steps):
            raise AITaskResumeError("Failed Task has no retry-safe step")
        for step in failed_steps:
            transition_step(
                db,
                task=task,
                step=step,
                requested_state=AITaskStepState.RETRY_PENDING,
                actor_type="USER",
                actor_user_id=user.id,
                reason_code="USER_RESUME_REQUESTED",
                now=current,
            )
        next_state = AITaskState.RETRY_PENDING
    elif task.state == AITaskState.WAITING_INPUT.value:
        waiting_steps = list(
            db.scalars(
                select(AITaskStep).where(
                    AITaskStep.task_id == task.id,
                    AITaskStep.state == AITaskStepState.WAITING_INPUT.value,
                )
            ).all()
        )
        for step in waiting_steps:
            transition_step(
                db,
                task=task,
                step=step,
                requested_state=AITaskStepState.RUNNING,
                actor_type="USER",
                actor_user_id=user.id,
                reason_code="USER_RESUME_REQUESTED",
                now=current,
            )
        next_state = AITaskState.RUNNING
    else:
        raise AITaskTransitionConflictError("Task is not resumable")
    task.resume_requested_at = _now_text(current)
    return transition_task(
        db,
        task=task,
        requested_state=next_state,
        actor_type="USER",
        actor_user_id=user.id,
        reason_code="USER_RESUME_REQUESTED",
        event_type=AITaskEventType.RESUME_REQUESTED,
        expected_revision=expected_revision,
        settings=settings,
        now=current,
    )


def enforce_task_retention(
    db: Session,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[int, int]:
    current = now or business_now()
    current_text = _now_text(current)
    audit_cutoff = (
        current - timedelta(days=settings.ai_task_security_audit_retention_days)
    ).strftime("%Y-%m-%d %H:%M:%S")
    task_result = db.execute(
        delete(AITask).where(
            AITask.state.in_(tuple(item.value for item in TERMINAL_TASK_STATES)),
            AITask.retention_expires_at != "",
            AITask.retention_expires_at <= current_text,
        )
    )
    audit_result = db.execute(
        delete(AuthAuditLog).where(
            AuthAuditLog.action == "ai_task_access_denied",
            AuthAuditLog.created_at <= audit_cutoff,
        )
    )
    db.commit()
    return max(task_result.rowcount or 0, 0), max(audit_result.rowcount or 0, 0)
