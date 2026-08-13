from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import ceil
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_action import AIActionConfirmation
from app.models.ai_observability import AIEvalRun, AIFeedback, AIMetricEvent
from app.models.ai_task import AITask
from app.schemas.ai.feedback import (
    AIEvalRunData,
    AIMetricEventData,
    AIMetricLatency,
    AIMetricRates,
    AIMetricSummary,
)

metric_logger = logging.getLogger("app.ai.observability")


@dataclass(frozen=True, slots=True)
class AIObservabilityEvent:
    request_id: str
    event_type: Literal["MODEL_RUN", "TOOL_CALL"]
    event_key: str
    owner_user_id: str
    status: Literal["SUCCESS", "FAILURE", "DENIED", "CANCELLED"]
    factory_id: str = ""
    conversation_id: str = ""
    task_id: str = ""
    action_id: str = ""
    skill_id: str = ""
    skill_version: str = ""
    skill_hash: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    provider: str = ""
    model: str = ""
    tool_name: str = ""
    tool_version: str = ""
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retry_count: int = 0
    error_code: str = ""
    evidence_count: int = 0
    truncated: bool = False
    unauthorized_action: bool = False
    cross_factory_leakage: bool = False
    preview_executed_mislabel: bool = False


def _estimated_cost(event: AIObservabilityEvent, settings: Settings) -> tuple[int, str]:
    input_rate = settings.ai_input_token_cost_usd_per_million
    output_rate = settings.ai_output_token_cost_usd_per_million
    if input_rate <= 0 and output_rate <= 0:
        return 0, "UNAVAILABLE"
    # USD / million tokens converts directly to micro-USD per token.
    value = round(event.input_tokens * input_rate + event.output_tokens * output_rate)
    return max(value, 0), "CONFIGURED_ESTIMATE"


def record_metric_event(
    db: Session,
    event: AIObservabilityEvent,
    *,
    settings: Settings,
) -> AIMetricEvent:
    replay = db.scalar(
        select(AIMetricEvent).where(
            AIMetricEvent.request_id == event.request_id,
            AIMetricEvent.event_type == event.event_type,
            AIMetricEvent.event_key == event.event_key,
        )
    )
    if replay is not None:
        return replay
    estimated_cost, cost_basis = _estimated_cost(event, settings)
    record = AIMetricEvent(
        id=f"aimet-{uuid4().hex}",
        request_id=event.request_id[:128],
        event_type=event.event_type,
        event_key=event.event_key[:160],
        owner_user_id=event.owner_user_id,
        factory_id=event.factory_id[:64],
        conversation_id=event.conversation_id[:64],
        task_id=event.task_id[:64],
        action_id=event.action_id[:96],
        skill_id=event.skill_id[:160],
        skill_version=event.skill_version[:32],
        skill_hash=event.skill_hash[:64],
        prompt_version=event.prompt_version[:32],
        prompt_hash=event.prompt_hash[:64],
        provider=event.provider[:64],
        model=event.model[:128],
        tool_name=event.tool_name[:160],
        tool_version=event.tool_version[:32],
        status=event.status,
        duration_ms=max(int(event.duration_ms), 0),
        input_tokens=max(event.input_tokens, 0),
        output_tokens=max(event.output_tokens, 0),
        total_tokens=max(event.input_tokens, 0) + max(event.output_tokens, 0),
        estimated_cost_microusd=estimated_cost,
        cost_basis=cost_basis,
        retry_count=max(event.retry_count, 0),
        error_code=event.error_code[:96],
        evidence_count=max(event.evidence_count, 0),
        truncated=int(event.truncated),
        unauthorized_action=int(event.unauthorized_action),
        cross_factory_leakage=int(event.cross_factory_leakage),
        preview_executed_mislabel=int(event.preview_executed_mislabel),
        created_at=business_now().isoformat(timespec="seconds"),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(AIMetricEvent).where(
                AIMetricEvent.request_id == event.request_id,
                AIMetricEvent.event_type == event.event_type,
                AIMetricEvent.event_key == event.event_key,
            )
        )
        if replay is not None:
            return replay
        raise
    return record


def safe_record_metric_event(
    session_factory: sessionmaker[Session],
    event: AIObservabilityEvent,
    *,
    settings: Settings,
) -> None:
    if not (settings.ai_observability_enabled or settings.ai_feedback_enabled):
        return
    try:
        with session_factory() as db:
            record_metric_event(db, event, settings=settings)
    except Exception:
        metric_logger.exception(
            "ai_metric_write_failed request_id=%s event_type=%s event_key=%s",
            event.request_id,
            event.event_type,
            event.event_key,
        )


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(ceil(len(ordered) * percentile) - 1, 0)
    return ordered[index]


def _average_metric(eval_runs: list[AIEvalRun], key: str) -> float | None:
    values: list[float] = []
    for run in eval_runs:
        try:
            value = json.loads(run.metrics_json).get(key)
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(value, (int, float)):
            values.append(float(value))
    return round(sum(values) / len(values), 6) if values else None


def _between(column, from_time: str, to_time: str):
    return column >= from_time, column <= to_time


def build_metric_summary(
    db: Session,
    *,
    from_time: str,
    to_time: str,
) -> AIMetricSummary:
    events = list(
        db.scalars(
            select(AIMetricEvent).where(
                *_between(AIMetricEvent.created_at, from_time, to_time)
            )
        ).all()
    )
    tasks = list(
        db.scalars(
            select(AITask).where(*_between(AITask.created_at, from_time, to_time))
        ).all()
    )
    actions = list(
        db.scalars(
            select(AIActionConfirmation).where(
                *_between(AIActionConfirmation.created_at, from_time, to_time)
            )
        ).all()
    )
    feedback = list(
        db.scalars(
            select(AIFeedback).where(
                *_between(AIFeedback.created_at, from_time, to_time)
            )
        ).all()
    )
    eval_runs = list(
        db.scalars(
            select(AIEvalRun).where(*_between(AIEvalRun.created_at, from_time, to_time))
        ).all()
    )
    model_runs = [item for item in events if item.event_type == "MODEL_RUN"]
    tool_calls = [item for item in events if item.event_type == "TOOL_CALL"]
    terminal_tasks = [
        item for item in tasks if item.state in {"COMPLETED", "FAILED", "CANCELLED"}
    ]
    successful_tasks = [item for item in terminal_tasks if item.state == "COMPLETED"]
    successful_task_ids = {item.id for item in successful_tasks}
    task_model_runs = [
        event
        for event in model_runs
        if event.task_id and event.task_id in successful_task_ids
    ]
    task_cost = sum(event.estimated_cost_microusd for event in task_model_runs)
    correction_rate = (
        sum(item.rating == "NOT_HELPFUL" for item in feedback) / len(feedback)
        if feedback
        else None
    )
    security_denominator = max(len(model_runs), 1)
    production_unauthorized_rate = (
        sum(item.unauthorized_action for item in model_runs) / security_denominator
    )
    production_cross_factory_rate = (
        sum(item.cross_factory_leakage for item in model_runs) / security_denominator
    )
    production_preview_mislabel_rate = (
        sum(item.preview_executed_mislabel for item in model_runs)
        / security_denominator
    )
    eval_unauthorized_rate = _average_metric(eval_runs, "unauthorized_action_rate")
    eval_cross_factory_rate = _average_metric(eval_runs, "cross_factory_leakage_rate")
    eval_preview_mislabel_rate = _average_metric(
        eval_runs, "preview_executed_mislabel_rate"
    )
    cost_bases = {item.cost_basis for item in model_runs}
    if not model_runs or cost_bases == {"UNAVAILABLE"}:
        cost_basis = "UNAVAILABLE"
    elif cost_bases == {"CONFIGURED_ESTIMATE"}:
        cost_basis = "CONFIGURED_ESTIMATE"
    else:
        cost_basis = "MIXED"
    return AIMetricSummary(
        from_time=from_time,
        to_time=to_time,
        model_runs=len(model_runs),
        tool_calls=len(tool_calls),
        tasks=len(tasks),
        actions=len(actions),
        feedback_items=len(feedback),
        eval_runs=len(eval_runs),
        total_tokens=sum(item.total_tokens for item in model_runs),
        estimated_cost_microusd=sum(
            item.estimated_cost_microusd for item in model_runs
        ),
        cost_per_successful_task_microusd=(
            round(task_cost / len({event.task_id for event in task_model_runs}))
            if task_model_runs
            else None
        ),
        cost_basis=cost_basis,
        rates=AIMetricRates(
            task_success_rate=(
                len(successful_tasks) / len(terminal_tasks) if terminal_tasks else None
            ),
            grounded_claim_rate=_average_metric(eval_runs, "grounded_claim_rate"),
            citation_accuracy=_average_metric(eval_runs, "citation_accuracy"),
            tool_selection_precision=_average_metric(
                eval_runs, "tool_selection_precision"
            ),
            tool_argument_accuracy=_average_metric(eval_runs, "tool_argument_accuracy"),
            user_correction_rate=correction_rate,
            provider_retry_rate=(
                sum(item.retry_count > 0 for item in model_runs) / len(model_runs)
                if model_runs
                else None
            ),
            model_failure_rate=(
                sum(item.status == "FAILURE" for item in model_runs) / len(model_runs)
                if model_runs
                else None
            ),
            tool_failure_rate=(
                sum(item.status == "FAILURE" for item in tool_calls) / len(tool_calls)
                if tool_calls
                else None
            ),
            worker_retry_rate=(
                sum(item.claim_count > 1 for item in tasks) / len(tasks)
                if tasks
                else None
            ),
            unauthorized_action_rate=max(
                production_unauthorized_rate, eval_unauthorized_rate or 0.0
            ),
            cross_factory_leakage_rate=max(
                production_cross_factory_rate, eval_cross_factory_rate or 0.0
            ),
            preview_executed_mislabel_rate=max(
                production_preview_mislabel_rate, eval_preview_mislabel_rate or 0.0
            ),
        ),
        latency=AIMetricLatency(
            model_run_p50_ms=_percentile(
                [item.duration_ms for item in model_runs], 0.5
            ),
            model_run_p95_ms=_percentile(
                [item.duration_ms for item in model_runs], 0.95
            ),
            tool_call_p50_ms=_percentile(
                [item.duration_ms for item in tool_calls], 0.5
            ),
            tool_call_p95_ms=_percentile(
                [item.duration_ms for item in tool_calls], 0.95
            ),
        ),
        failures={
            "provider": sum(item.status == "FAILURE" for item in model_runs),
            "tool": sum(item.status == "FAILURE" for item in tool_calls),
            "worker": sum(item.state == "FAILED" for item in tasks),
            "action": sum(item.status in {"FAILED", "STALE"} for item in actions),
        },
    )


def _event_data(record: AIMetricEvent) -> AIMetricEventData:
    return AIMetricEventData(
        id=record.id,
        request_id=record.request_id,
        event_type=record.event_type,
        factory_id=record.factory_id,
        conversation_id=record.conversation_id,
        task_id=record.task_id,
        action_id=record.action_id,
        skill_id=record.skill_id,
        skill_version=record.skill_version,
        skill_hash=record.skill_hash,
        prompt_version=record.prompt_version,
        prompt_hash=record.prompt_hash,
        provider=record.provider,
        model=record.model,
        tool_name=record.tool_name,
        tool_version=record.tool_version,
        status=record.status,
        duration_ms=record.duration_ms,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        total_tokens=record.total_tokens,
        estimated_cost_microusd=record.estimated_cost_microusd,
        cost_basis=record.cost_basis,
        retry_count=record.retry_count,
        error_code=record.error_code,
        evidence_count=record.evidence_count,
        truncated=bool(record.truncated),
        unauthorized_action=bool(record.unauthorized_action),
        cross_factory_leakage=bool(record.cross_factory_leakage),
        preview_executed_mislabel=bool(record.preview_executed_mislabel),
        created_at=record.created_at,
    )


def list_metric_events(
    db: Session,
    *,
    from_time: str,
    to_time: str,
    limit: int,
    offset: int,
) -> list[AIMetricEventData]:
    records = db.scalars(
        select(AIMetricEvent)
        .where(*_between(AIMetricEvent.created_at, from_time, to_time))
        .order_by(AIMetricEvent.created_at.desc(), AIMetricEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_event_data(item) for item in records]


def list_eval_runs(
    db: Session,
    *,
    from_time: str,
    to_time: str,
    limit: int,
    offset: int,
) -> list[AIEvalRunData]:
    records = db.scalars(
        select(AIEvalRun)
        .where(*_between(AIEvalRun.created_at, from_time, to_time))
        .order_by(AIEvalRun.created_at.desc(), AIEvalRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    output: list[AIEvalRunData] = []
    for record in records:
        try:
            metrics = json.loads(record.metrics_json)
        except (json.JSONDecodeError, TypeError):
            metrics = {}
        output.append(
            AIEvalRunData(
                id=record.id,
                suite_id=record.suite_id,
                dataset_version=record.dataset_version,
                dataset_hash=record.dataset_hash,
                runner_version=record.runner_version,
                mode=record.mode,
                skill_id=record.skill_id,
                skill_version=record.skill_version,
                skill_hash=record.skill_hash,
                prompt_version=record.prompt_version,
                prompt_hash=record.prompt_hash,
                provider=record.provider,
                model=record.model,
                status=record.status,
                case_count=record.case_count,
                passed_count=record.passed_count,
                failed_count=record.failed_count,
                metrics=metrics,
                created_by=record.created_by,
                created_at=record.created_at,
                completed_at=record.completed_at,
            )
        )
    return output
