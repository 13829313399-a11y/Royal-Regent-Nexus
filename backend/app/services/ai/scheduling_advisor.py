from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import BUSINESS_TIME_ZONE, business_now
from app.models.injection_scheduling_execution import InjectionSchedulingPlan
from app.models.injection_scheduling_scheduler import InjectionSchedulingRun
from app.schemas.ai.scheduling import AIEntityLink
from app.schemas.ai.scheduling_advisor import (
    AIInjectionSchedulingComparisonData,
    AIInjectionSchedulingPreviewData,
    AISchedulingMetricDelta,
    AISchedulingPreviewMetrics,
    AISchedulingPreviewRunSummary,
    InjectionSchedulingPreviewComparisonInput,
    InjectionSchedulingPreviewIntentInput,
)
from app.schemas.injection_scheduling_scheduler import (
    InjectionSchedulingObjectiveWeights,
    InjectionSchedulingRunCreate,
)
from app.services.ai.previews.scheduling_adapter import (
    build_scheduling_preview_manifest,
    build_scheduling_scenario_compare,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import current_rule_set
from app.services.injection_scheduling_scheduler.normalization import load_json
from app.services.injection_scheduling_scheduler.run_service import create_run

if TYPE_CHECKING:
    from app.services.ai.tool_executor import ToolExecutionContext

_OBJECTIVE_WEIGHTS = {
    "BALANCED": InjectionSchedulingObjectiveWeights(),
    "DELIVERY_PRIORITY": InjectionSchedulingObjectiveWeights(
        tardiness_weight=300,
    ),
    "MINIMIZE_CHANGEOVER": InjectionSchedulingObjectiveWeights(
        transition_weight=8,
    ),
    "LOAD_BALANCE": InjectionSchedulingObjectiveWeights(
        load_balance_weight=100,
    ),
}


def _draft_plan(db: Session, factory_id: str) -> InjectionSchedulingPlan:
    plan = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if plan is None:
        raise HTTPException(status_code=409, detail="当前厂区没有可供预览的计划草案")
    return plan


def _business_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="计划业务日期无效") from exc


def _iso_at(value: date, hour: int) -> str:
    return datetime.combine(value, time(hour=hour), tzinfo=BUSINESS_TIME_ZONE).isoformat(
        timespec="seconds"
    )


def _request_id(context: ToolExecutionContext, arguments: object) -> str:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{context.request_id}:{context.tool_call_id}:{normalized}".encode()
    ).hexdigest()[:40]
    return f"ai-preview-{digest}"


def _number(value: object, *, integer: bool = False) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(value) if integer else float(value)


def _delta(value: object) -> AISchedulingMetricDelta:
    source = value if isinstance(value, dict) else {}
    before = _number(source.get("before"), integer=True)
    after = _number(source.get("after"), integer=True)
    change = source.get("change")
    safe_change = int(change) if isinstance(change, (int, float)) and not isinstance(change, bool) else None
    return AISchedulingMetricDelta(
        before=before if isinstance(before, int) else None,
        after=after if isinstance(after, int) else None,
        change=safe_change,
    )


def _metrics(summary: dict[str, Any]) -> AISchedulingPreviewMetrics:
    ratios = [
        float(item["load_ratio"])
        for item in summary.get("machine_loads", [])
        if isinstance(item, dict)
        and isinstance(item.get("load_ratio"), (int, float))
        and not isinstance(item.get("load_ratio"), bool)
        and item["load_ratio"] >= 0
    ]

    def count(key: str) -> int | None:
        value = _number(summary.get(key), integer=True)
        return value if isinstance(value, int) else None

    elapsed = _number(summary.get("solver_elapsed_ms"))
    return AISchedulingPreviewMetrics(
        input_order_count=count("input_order_count"),
        scheduled_count=count("scheduled_count"),
        review_count=count("review_count"),
        unassigned_count=count("unassigned_count"),
        moved_task_count=count("moved_task_count"),
        overdue=_delta(summary.get("overdue")),
        mold_changes=_delta(summary.get("mold_changes")),
        dark_to_light_changes=_delta(summary.get("dark_to_light_changes")),
        load_ratio_min=min(ratios) if ratios else None,
        load_ratio_max=max(ratios) if ratios else None,
        load_ratio_average=round(sum(ratios) / len(ratios), 4) if ratios else None,
        solver_elapsed_ms=float(elapsed) if elapsed is not None else None,
    )


def _run_summary(
    record: InjectionSchedulingRun,
    *,
    preview_manifest=None,
) -> AISchedulingPreviewRunSummary:
    if record.status not in {"SUCCEEDED", "PARTIAL"}:
        raise HTTPException(status_code=409, detail="该候选方案尚未成功生成")
    summary = load_json(record.summary_json, {})
    if not isinstance(summary, dict):
        raise HTTPException(status_code=409, detail="候选方案指标无效")
    return AISchedulingPreviewRunSummary(
        run_id=record.id,
        plan_id=record.plan_id,
        plan_revision=record.expected_plan_revision,
        rule_revision=record.rule_revision,
        status=record.status,
        requested_solver=record.requested_solver,
        actual_solver=record.solver_type,
        solver_status=record.solver_status,
        fallback_used=record.fallback_used,
        scenario_group_id=record.scenario_group_id,
        scenario_name=record.scenario_name,
        alternative_no=record.alternative_no,
        horizon_start=record.horizon_start,
        horizon_end=record.horizon_end,
        metrics=_metrics(summary),
        preview_manifest=preview_manifest,
    )


def _scheduling_link(factory_id: str, run_id: str = "") -> AIEntityLink:
    query = {"factory": factory_id}
    if run_id:
        query["autoScheduleRun"] = run_id
    return AIEntityLink(
        label="在正式排产页面查看候选方案",
        route="/modules/production/injection-scheduling",
        query=query,
    )


def _comparison_base(
    db: Session,
    factory_id: str,
    run_id: str,
    plan: InjectionSchedulingPlan,
    rule_revision: int,
) -> InjectionSchedulingRun:
    record = db.scalar(
        select(InjectionSchedulingRun).where(
            InjectionSchedulingRun.id == run_id,
            InjectionSchedulingRun.factory_id == factory_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="对比基准候选方案不存在")
    if record.status not in {"SUCCEEDED", "PARTIAL"}:
        raise HTTPException(status_code=409, detail="对比基准不是可用候选方案")
    if (
        record.plan_id != plan.id
        or record.expected_plan_revision != plan.revision
        or record.rule_revision != rule_revision
    ):
        raise HTTPException(status_code=409, detail="对比基准已过期，请重新生成候选方案")
    if record.alternative_no >= 9:
        raise HTTPException(status_code=409, detail="当前方案组已达到候选数量上限")
    return record


def intent_to_run_create(
    *,
    plan: InjectionSchedulingPlan,
    rule_revision: int,
    intent: InjectionSchedulingPreviewIntentInput,
    comparison_base: InjectionSchedulingRun | None = None,
) -> InjectionSchedulingRunCreate:
    if comparison_base is not None:
        snapshot = load_json(comparison_base.input_snapshot_json, {})
        source_orders = snapshot.get("orders", []) if isinstance(snapshot, dict) else []
        order_ids = [
            item["id"]
            for item in source_orders
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        horizon_start = comparison_base.horizon_start
        horizon_end = comparison_base.horizon_end
        scenario_group_id = comparison_base.scenario_group_id
        alternative_no = comparison_base.alternative_no + 1
    else:
        start_date = _business_date(plan.business_date)
        order_ids = intent.order_ids if intent.order_scope == "SELECTED" else []
        horizon_start = _iso_at(start_date, 8)
        horizon_end = _iso_at(start_date + timedelta(days=intent.horizon_days), 20)
        scenario_group_id = ""
        alternative_no = 1
    return InjectionSchedulingRunCreate(
        factory_id=intent.factory_id,
        plan_id=plan.id,
        expected_plan_revision=plan.revision,
        rule_revision=rule_revision,
        mode="PREVIEW",
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        order_ids=order_ids,
        respect_locked_tasks=True,
        solver=intent.solver,
        time_limit_seconds=intent.time_limit_seconds,
        objective_weights=_OBJECTIVE_WEIGHTS[intent.objective],
        scenario_group_id=scenario_group_id,
        scenario_name=intent.scenario_name,
        alternative_no=alternative_no,
        replay_of_run_id=None,
    )


def generate_preview(
    db: Session,
    intent: InjectionSchedulingPreviewIntentInput,
    user: AuthContext,
    context: ToolExecutionContext,
) -> AIInjectionSchedulingPreviewData:
    plan = _draft_plan(db, intent.factory_id)
    rules = current_rule_set(db, intent.factory_id)
    comparison_base = (
        _comparison_base(
            db,
            intent.factory_id,
            intent.compare_with_run_id,
            plan,
            rules.revision,
        )
        if intent.compare_with_run_id
        else None
    )
    payload = intent_to_run_create(
        plan=plan,
        rule_revision=rules.revision,
        intent=intent,
        comparison_base=comparison_base,
    )
    record = create_run(
        db,
        payload,
        user,
        _request_id(context, intent.model_dump(mode="json")),
    )
    created_at = datetime.fromisoformat(record.created_at)
    manifest = build_scheduling_preview_manifest(
        record,
        user=user,
        current_plan=plan,
        current_rule_revision=rules.revision,
        ttl_minutes=settings.ai_preview_ttl_minutes,
        now=created_at,
    )
    return AIInjectionSchedulingPreviewData(
        factory_id=intent.factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        intent_objective=intent.objective,
        run=_run_summary(record, preview_manifest=manifest),
        entity_links=[_scheduling_link(intent.factory_id, record.id)],
    )


def compare_previews(
    db: Session,
    arguments: InjectionSchedulingPreviewComparisonInput,
    user: AuthContext,
) -> AIInjectionSchedulingComparisonData:
    records = list(
        db.scalars(
            select(InjectionSchedulingRun).where(
                InjectionSchedulingRun.factory_id == arguments.factory_id,
                InjectionSchedulingRun.id.in_(arguments.run_ids),
            )
        ).all()
    )
    by_id = {record.id: record for record in records}
    if len(by_id) != len(arguments.run_ids):
        raise HTTPException(status_code=404, detail="部分候选方案不存在或不属于当前厂区")
    ordered = [by_id[run_id] for run_id in arguments.run_ids]
    snapshot_keys = {
        (
            record.plan_id,
            record.expected_plan_revision,
            record.rule_revision,
            record.horizon_start,
            record.horizon_end,
        )
        for record in ordered
    }
    comparable = len(snapshot_keys) == 1
    current_plan = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == arguments.factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    current_rules = (
        current_rule_set(db, arguments.factory_id) if current_plan is not None else None
    )
    now = business_now()
    manifests = tuple(
        build_scheduling_preview_manifest(
            record,
            user=user,
            current_plan=current_plan,
            current_rule_revision=(
                current_rules.revision if current_rules is not None else None
            ),
            ttl_minutes=settings.ai_preview_ttl_minutes,
            now=now,
        )
        for record in ordered
    )
    warning = (
        "候选方案基于同一计划、规则与时间范围，可直接比较。"
        if comparable
        else "候选方案的计划、规则或时间范围不同，指标不可直接横向比较。"
    )
    return AIInjectionSchedulingComparisonData(
        factory_id=arguments.factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        comparable_snapshot=comparable,
        comparison_warning=warning,
        runs=[
            _run_summary(record, preview_manifest=manifest)
            for record, manifest in zip(ordered, manifests, strict=True)
        ],
        scenario_compare=build_scheduling_scenario_compare(
            manifests,
            warning=warning,
        ),
        entity_links=[_scheduling_link(arguments.factory_id)],
    )
