from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingTask,
)
from app.schemas.injection_scheduling_execution import InjectionSchedulingTaskCreate
from app.schemas.injection_scheduling_matching import (
    InjectionSchedulingMachineMatchOut,
    InjectionSchedulingMatchEvaluationOut,
    InjectionSchedulingMatchReasonOut,
    InjectionSchedulingScoreBreakdownOut,
    InjectionSchedulingSuggestionConfirm,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import (
    DEFAULT_RULE_CONFIG,
    current_rule_set,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_execution import add_task, plan_out
from app.services.injection_scheduling_mold_context import (
    SchedulingMoldContext,
    load_scheduling_molds,
    machine_capabilities_for_mold,
)
from app.services.injection_scheduling_rules import (
    MachineEligibilityProfile,
    MoldEligibilityProfile,
    evaluate_eligibility,
)


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _reason(
    rule_code: str, label: str, detail: str
) -> InjectionSchedulingMatchReasonOut:
    return InjectionSchedulingMatchReasonOut(
        rule_code=rule_code,
        label=label,
        detail=detail,
    )


def _require_order(
    db: Session,
    factory_id: str,
    order_id: str,
    *,
    allow_scheduled: bool = False,
) -> InjectionSchedulingOrder:
    order = db.scalar(
        select(InjectionSchedulingOrder).where(
            InjectionSchedulingOrder.id == order_id,
            InjectionSchedulingOrder.factory_id == factory_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="待排订单不存在")
    allowed_statuses = {"BACKLOG", "SCHEDULED"} if allow_scheduled else {"BACKLOG"}
    if order.status not in allowed_statuses:
        raise HTTPException(
            status_code=409, detail="订单已排产或已结束，不能重复生成候选"
        )
    return order


def _mold_for_order(
    db: Session,
    factory_id: str,
    order: InjectionSchedulingOrder,
) -> SchedulingMoldContext | None:
    return next(
        iter(
            load_scheduling_molds(
                db,
                factory_id=factory_id,
                orders=[order],
            ).values()
        ),
        None,
    )


def _machines(
    db: Session,
    factory_id: str,
    machine_ids: list[str],
) -> list[InjectionSchedulingMachine]:
    statement = select(InjectionSchedulingMachine).where(
        InjectionSchedulingMachine.factory_id == factory_id
    )
    if machine_ids:
        statement = statement.where(InjectionSchedulingMachine.id.in_(machine_ids))
    records = list(
        db.scalars(statement.order_by(InjectionSchedulingMachine.machine_code)).all()
    )
    if machine_ids and len(records) != len(machine_ids):
        raise HTTPException(
            status_code=404, detail="部分候选机台不存在或不属于当前厂区"
        )
    return records


def _queue_context(
    db: Session,
    factory_id: str,
) -> tuple[
    dict[str, list[InjectionSchedulingTask]], dict[str, InjectionSchedulingMold]
]:
    plan = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status.in_(("DRAFT", "PUBLISHED")),
        )
        .order_by(
            (InjectionSchedulingPlan.status == "DRAFT").desc(),
            InjectionSchedulingPlan.updated_at.desc(),
        )
    )
    if plan is None:
        return {}, {}
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.execution_status.notin_(
                    ("COMPLETED", "CANCELLED")
                ),
            )
            .order_by(
                InjectionSchedulingTask.machine_id,
                InjectionSchedulingTask.sequence_no,
            )
        ).all()
    )
    by_machine: dict[str, list[InjectionSchedulingTask]] = {}
    mold_ids = {task.mold_id for task in tasks if task.mold_id}
    for task in tasks:
        by_machine.setdefault(task.machine_id, []).append(task)
    molds = (
        {
            mold.id: mold
            for mold in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == factory_id,
                    InjectionSchedulingMold.id.in_(mold_ids),
                )
            ).all()
        }
        if mold_ids
        else {}
    )
    return by_machine, molds


def _score(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | SchedulingMoldContext | None,
    order: InjectionSchedulingOrder,
    config: dict[str, Any],
    queue: list[InjectionSchedulingTask],
    queue_molds: dict[str, InjectionSchedulingMold],
    max_queue_count: int,
) -> list[InjectionSchedulingScoreBreakdownOut]:
    weights = {
        **DEFAULT_RULE_CONFIG["scoring_weights"],
        **config.get("scoring_weights", {}),
    }
    breakdown: list[InjectionSchedulingScoreBreakdownOut] = []

    slack = order.delivery_slack_days
    if slack is None and order.delivery_due_date:
        try:
            slack = (
                date.fromisoformat(order.delivery_due_date) - business_now().date()
            ).days
        except ValueError:
            slack = None
    urgency_factor = (
        1.0
        if slack is not None and slack < 0
        else 0.8
        if slack is not None and slack <= 3
        else 0.5
        if slack is not None and slack <= 7
        else 0.2
    )
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="delivery_urgency",
            label="货期紧迫度",
            delta=round(float(weights["delivery_urgency"]) * urgency_factor, 2),
            explanation=f"交期差 {slack} 天。"
            if slack is not None
            else "交期未完整，按保守基础分。",
        )
    )

    priority_factor = {"CRITICAL": 1.0, "URGENT": 0.6, "NORMAL": 0.2}.get(
        order.priority_code, 0.2
    )
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="business_priority",
            label="业务优先级",
            delta=round(float(weights["business_priority"]) * priority_factor, 2),
            explanation=f"订单优先级 {order.priority_code}。",
        )
    )

    last_task = queue[-1] if queue else None
    same_mold = bool(last_task and mold and last_task.mold_id == mold.id)
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="same_mold",
            label="同模连续",
            delta=float(weights["same_mold"]) if same_mold else 0,
            explanation="当前队尾为同一模具，减少换模。"
            if same_mold
            else "当前队尾不是同一模具。",
        )
    )

    last_mold = (
        queue_molds.get(last_task.mold_id) if last_task and last_task.mold_id else None
    )
    same_material_color = bool(
        mold
        and last_mold
        and mold.material_code == last_mold.material_code
        and mold.color_profile == last_mold.color_profile
    )
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="same_material_color",
            label="同料同色连续",
            delta=float(weights["same_material_color"]) if same_material_color else 0,
            explanation="队尾同料同色，可减少洗机转色。"
            if same_material_color
            else "未形成同料同色连续。",
        )
    )

    capacity = _float(machine.injection_capacity_g) or 0
    required = _float(mold.whole_shot_net_weight_g) if mold is not None else None
    machine_a_class = _float(machine.machine_a_class)
    mold_a_class = _float(mold.mold_a_class) if mold is not None else None
    utilization = required / capacity if required is not None and capacity else 0
    class_gap = (
        machine_a_class - mold_a_class
        if machine_a_class is not None and mold_a_class is not None
        else None
    )
    fit_factor = (
        max(0.2, 1 - class_gap / machine_a_class)
        if class_gap is not None and machine_a_class
        else 0.3
    )
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="machine_fit",
            label="机台适配度",
            delta=round(float(weights["machine_fit"]) * fit_factor, 2),
            explanation=(
                f"安数余量 {class_gap:g}A；射胶容量利用率约 {utilization * 100:.1f}%。"
                if class_gap is not None
                else f"安数待复核；射胶容量利用率约 {utilization * 100:.1f}%。"
            ),
        )
    )

    balance_factor = 1 - len(queue) / max_queue_count if max_queue_count else 1.0
    breakdown.append(
        InjectionSchedulingScoreBreakdownOut(
            rule_code="queue_balance",
            label="队列负荷",
            delta=round(float(weights["queue_balance"]) * max(0.0, balance_factor), 2),
            explanation=f"当前后续队列 {len(queue)} 条。",
        )
    )
    return breakdown


def evaluate_order_matches(
    db: Session,
    *,
    factory_id: str,
    order_id: str,
    machine_ids: list[str] | None = None,
    allow_scheduled: bool = False,
) -> InjectionSchedulingMatchEvaluationOut:
    factory_id = require_injection_scheduling_factory(factory_id)
    order = _require_order(
        db,
        factory_id,
        order_id,
        allow_scheduled=allow_scheduled,
    )
    mold = _mold_for_order(db, factory_id, order)
    rules = current_rule_set(db, factory_id)
    config = {**DEFAULT_RULE_CONFIG, **_json(rules.config_json, {})}
    records = _machines(db, factory_id, machine_ids or [])
    queues, queue_molds = _queue_context(db, factory_id)
    max_queue_count = max((len(items) for items in queues.values()), default=0)
    results: list[InjectionSchedulingMachineMatchOut] = []
    for machine in records:
        if mold is None:
            failures: list[InjectionSchedulingMatchReasonOut] = []
            warnings = [
                _reason(
                    "MOLD_MISSING",
                    "模具资料",
                    "订单未关联模具，只能由有权限人员人工复核。",
                )
            ]
            advisories: list[InjectionSchedulingMatchReasonOut] = []
            decision = "REVIEW_REQUIRED"
        else:
            arm_capabilities, fixture_capabilities = machine_capabilities_for_mold(
                mold,
                tuple(_json(machine.robot_capabilities_json, [])),
                tuple(_json(machine.fixture_capabilities_json, [])),
            )
            eligibility = evaluate_eligibility(
                MachineEligibilityProfile(
                    a_class=machine.machine_a_class,
                    injection_capacity_g=machine.injection_capacity_g,
                    arm_capabilities=arm_capabilities,
                    fixture_capabilities=fixture_capabilities,
                    process_capabilities=tuple(_json(machine.process_tags_json, [])),
                    process_restrictions=tuple(
                        _json(machine.process_restrictions_json, [])
                    ),
                    status=machine.status,
                    normalization_status=machine.normalization_status,
                    special_machine_type=machine.special_machine_type,
                ),
                MoldEligibilityProfile(
                    a_class=mold.mold_a_class,
                    whole_shot_net_weight_g=mold.whole_shot_net_weight_g,
                    required_arm_type=mold.required_arm_type,
                    required_fixture_type=mold.required_fixture_type,
                    process_requirements=tuple(
                        dict.fromkeys(
                            (
                                *_json(mold.process_requirements_json, []),
                                *_json(mold.process_tags_json, []),
                            )
                        )
                    ),
                    status=mold.status,
                    normalization_status=mold.normalization_status,
                    special_machine_type=mold.special_machine_type,
                ),
            )
            failures = [
                _reason(reason.rule_code, reason.label, reason.detail)
                for reason in eligibility.hard_failures
            ]
            warnings = [
                _reason(reason.rule_code, reason.label, reason.detail)
                for reason in eligibility.review_reasons
            ]
            advisories = [
                _reason(reason.rule_code, reason.label, reason.detail)
                for reason in eligibility.advisories
            ]
            decision = eligibility.decision
        breakdown = (
            []
            if failures
            else _score(
                machine,
                mold,
                order,
                config,
                queues.get(machine.id, []),
                queue_molds,
                max_queue_count,
            )
        )
        score = None if failures else round(sum(item.delta for item in breakdown), 1)
        result_label = (
            "硬约束失败" if failures else "资料待复核" if warnings else "硬约束通过"
        )
        results.append(
            InjectionSchedulingMachineMatchOut(
                machine_id=machine.id,
                machine_code=machine.machine_code,
                decision=decision,
                score=score,
                hard_failures=failures,
                warnings=warnings,
                advisories=advisories,
                score_breakdown=breakdown,
                explanation=f"{machine.machine_code}：{result_label}；规则 revision {rules.revision}。",
                rule_set_id=rules.id,
                rule_set_revision=rules.revision,
            )
        )
    decision_rank = {"PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}
    results.sort(
        key=lambda item: (
            decision_rank[item.decision],
            -(item.score or -1),
            item.machine_code,
        )
    )
    return InjectionSchedulingMatchEvaluationOut(
        factory_id=factory_id,
        order_id=order.id,
        mold_id=mold.id if mold is not None else "",
        rule_set_id=rules.id,
        rule_set_revision=rules.revision,
        results=results,
    )


def confirm_suggestion(
    db: Session,
    *,
    plan_id: str,
    payload: InjectionSchedulingSuggestionConfirm,
    match: InjectionSchedulingMachineMatchOut,
    user: AuthContext,
) -> tuple[Any, int]:
    plan = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.id == plan_id,
            InjectionSchedulingPlan.factory_id == payload.factory_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="计划草案不存在")
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="只有草案可以确认候选机台")
    if plan.revision != payload.expected_plan_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "计划草案已被其他操作更新",
                "expected_revision": payload.expected_plan_revision,
                "current_revision": plan.revision,
            },
        )
    if (
        match.rule_set_revision != payload.expected_rule_revision
        or plan.rule_revision != match.rule_set_revision
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "匹配规则版本已变化，请重新获取候选机台",
                "current_rule_revision": match.rule_set_revision,
                "plan_rule_revision": plan.rule_revision,
            },
        )
    if match.decision == "FAIL":
        raise HTTPException(status_code=409, detail="硬约束失败的机台禁止排入草案")
    if match.decision == "REVIEW_REQUIRED" and not payload.override_reason:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "资料待复核的候选必须填写人工覆盖原因",
                "override_reason_required": True,
            },
        )
    order = _require_order(db, payload.factory_id, payload.order_id)
    machine_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == payload.factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.machine_id == payload.machine_id,
            )
            .order_by(InjectionSchedulingTask.sequence_no)
        ).all()
    )
    base_start = datetime.fromisoformat(f"{plan.business_date}T08:00:00")
    if machine_tasks:
        base_start = max(
            base_start, datetime.fromisoformat(machine_tasks[-1].planned_finish)
        )
    outstanding = max(float(order.order_quantity - order.completed_quantity), 0.0)
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="订单已无欠数")
    previous_target = (
        float(machine_tasks[-1].shift_target_quantity) if machine_tasks else 0.0
    )
    shift_target = previous_target if previous_target > 0 else min(outstanding, 1400.0)
    shift_count = max(1, math.ceil(outstanding / shift_target))
    planned_finish = base_start + timedelta(hours=12 * shift_count)
    task_payload = InjectionSchedulingTaskCreate(
        factory_id=payload.factory_id,
        expected_revision=payload.expected_plan_revision,
        machine_id=payload.machine_id,
        order_id=order.id,
        mold_id=order.mold_id or order.mold_definition_id or "",
        mold_copy_no=1,
        sequence_no=(machine_tasks[-1].sequence_no + 1) if machine_tasks else 0,
        execution_status="QUEUED",
        planned_start=base_start.isoformat(timespec="seconds"),
        planned_finish=planned_finish.isoformat(timespec="seconds"),
        shift_target_quantity=shift_target,
        locked=False,
        manual_override_reason=payload.override_reason
        if match.decision == "REVIEW_REQUIRED"
        else "",
    )
    updated_plan, _, audit_sequence = add_task(
        db,
        plan.id,
        task_payload,
        user,
        payload.request_id,
        audit_detail={"match_result": match.model_dump(mode="json")},
    )
    return plan_out(db, updated_plan), audit_sequence
