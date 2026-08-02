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
    InjectionSchedulingRuleSet,
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


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _reason(rule_code: str, label: str, detail: str) -> InjectionSchedulingMatchReasonOut:
    return InjectionSchedulingMatchReasonOut(
        rule_code=rule_code,
        label=label,
        detail=detail,
    )


def _normalize_arm(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"", "none", "半自动", "无", "manual"}:
        return "none"
    if "multi" in normalized or "多" in normalized:
        return "multi"
    if "dual" in normalized or "双" in normalized:
        return "dual"
    if "single" in normalized or "单" in normalized:
        return "single"
    return normalized


def _require_order(
    db: Session,
    factory_id: str,
    order_id: str,
) -> InjectionSchedulingOrder:
    order = db.scalar(
        select(InjectionSchedulingOrder).where(
            InjectionSchedulingOrder.id == order_id,
            InjectionSchedulingOrder.factory_id == factory_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="待排订单不存在")
    if order.status != "BACKLOG":
        raise HTTPException(status_code=409, detail="订单已排产或已结束，不能重复生成候选")
    return order


def _mold_for_order(
    db: Session,
    factory_id: str,
    order: InjectionSchedulingOrder,
) -> InjectionSchedulingMold | None:
    if not order.mold_id:
        return None
    return db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.id == order.mold_id,
            InjectionSchedulingMold.factory_id == factory_id,
        )
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
    records = list(db.scalars(statement.order_by(InjectionSchedulingMachine.machine_code)).all())
    if machine_ids and len(records) != len(machine_ids):
        raise HTTPException(status_code=404, detail="部分候选机台不存在或不属于当前厂区")
    return records


def _queue_context(
    db: Session,
    factory_id: str,
) -> tuple[dict[str, list[InjectionSchedulingTask]], dict[str, InjectionSchedulingMold]]:
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
                InjectionSchedulingTask.execution_status.notin_(("COMPLETED", "CANCELLED")),
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
    molds = {
        mold.id: mold
        for mold in db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.id.in_(mold_ids),
            )
        ).all()
    } if mold_ids else {}
    return by_machine, molds


def _dimension_checks(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | None,
    rules: InjectionSchedulingRuleSet,
    failures: list[InjectionSchedulingMatchReasonOut],
    warnings: list[InjectionSchedulingMatchReasonOut],
) -> None:
    if mold is None:
        warnings.append(_reason("MOLD_MISSING", "模具资料", "订单未关联模具，只能由有权限人员人工复核。"))
        return
    mold_l, mold_w = _float(mold.length_mm), _float(mold.width_mm)
    machine_x = _float(machine.tie_bar_x_mm) or _float(machine.platen_x_mm)
    machine_y = _float(machine.tie_bar_y_mm) or _float(machine.platen_y_mm)
    if None in (mold_l, mold_w, machine_x, machine_y):
        warnings.append(_reason("INSTALLATION_DIMENSIONS_MISSING", "模具安装面", "模具 L×W 或机台安装空间资料不完整，不能自动判为适配。"))
    else:
        direct = mold_l <= machine_x and mold_w <= machine_y
        rotated = rules.allow_mold_rotation_90 and mold_l <= machine_y and mold_w <= machine_x
        if not direct and not rotated:
            failures.append(_reason("INSTALLATION_DIMENSIONS_EXCEEDED", "模具安装面", f"模具 {mold_l:g}×{mold_w:g}mm 超出机台 {machine_x:g}×{machine_y:g}mm 安装空间。"))

    mold_thickness = _float(mold.height_mm)
    min_thickness = _float(machine.min_mold_thickness_mm)
    max_thickness = _float(machine.max_mold_thickness_mm)
    if mold_thickness is None or min_thickness is None or max_thickness is None:
        warnings.append(_reason("MOLD_THICKNESS_UNCONFIRMED", "模厚范围", "模具 H 或机台最小/最大模厚资料不完整，必须现场复核。"))
    elif not min_thickness <= mold_thickness <= max_thickness:
        failures.append(_reason("MOLD_THICKNESS_OUT_OF_RANGE", "模厚范围", f"模具 H={mold_thickness:g}mm 不在机台 {min_thickness:g}–{max_thickness:g}mm 范围内。"))


def _capacity_check(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | None,
    rules: InjectionSchedulingRuleSet,
    failures: list[InjectionSchedulingMatchReasonOut],
    warnings: list[InjectionSchedulingMatchReasonOut],
) -> None:
    required = _float(mold.whole_shot_net_weight_g) if mold is not None else None
    capacity = _float(machine.injection_capacity_g)
    if required is None or capacity is None:
        warnings.append(_reason("SHOT_CAPACITY_MISSING", "射胶容量", "整啤净重或机台射胶量缺失，不能自动判定。"))
        return
    allowed = capacity * float(rules.configured_max_utilization)
    if required > allowed:
        failures.append(_reason("SHOT_CAPACITY_EXCEEDED", "射胶容量", f"整啤净重 {required:g}g 超过机台允许值 {allowed:g}g。"))


def _arm_and_fixture_checks(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | None,
    config: dict[str, Any],
    failures: list[InjectionSchedulingMatchReasonOut],
    warnings: list[InjectionSchedulingMatchReasonOut],
) -> None:
    if mold is None:
        return
    requirement = _normalize_arm(mold.required_arm_type)
    capabilities = [_normalize_arm(value) for value in _json(machine.robot_capabilities_json, [])]
    coverage_config = config.get("arm_coverage", DEFAULT_RULE_CONFIG["arm_coverage"])
    covered: set[str] = set()
    for capability in capabilities:
        covered.update(_normalize_arm(value) for value in coverage_config.get(capability, [capability]))
    if requirement not in covered:
        if capabilities:
            failures.append(_reason("ROBOT_ARM_UNSUPPORTED", "机械手能力", f"模具要求 {mold.required_arm_type or 'none'}，机台能力为 {', '.join(capabilities)}。"))
        else:
            warnings.append(_reason("ROBOT_ARM_DATA_MISSING", "机械手能力", "机台机械手能力未维护，必须人工复核。"))

    fixture_requirement = mold.required_fixture_type.strip().lower()
    fixtures = {value.strip().lower() for value in _json(machine.fixture_capabilities_json, []) if value.strip()}
    if fixture_requirement and fixture_requirement not in fixtures:
        if fixtures:
            failures.append(_reason("FIXTURE_UNSUPPORTED", "夹具能力", f"模具要求 {mold.required_fixture_type}，机台未配置该夹具。"))
        else:
            warnings.append(_reason("FIXTURE_DATA_MISSING", "夹具能力", "机台夹具能力未维护，必须人工复核。"))


def _process_checks(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | None,
    failures: list[InjectionSchedulingMatchReasonOut],
    warnings: list[InjectionSchedulingMatchReasonOut],
) -> None:
    if machine.status in {"maintenance", "offline"}:
        failures.append(_reason("MACHINE_UNAVAILABLE", "机台状态", f"机台当前状态为 {machine.status}。"))
    if mold is None:
        return
    if mold.status in {"maintenance", "not_arrived", "retired"}:
        failures.append(_reason("MOLD_UNAVAILABLE", "模具状态", f"模具当前状态为 {mold.status}。"))
    elif mold.status == "occupied":
        warnings.append(_reason("MOLD_OCCUPIED", "模具状态", "模具当前被占用，排入草案时必须重新校验实体副本和时间重叠。"))
    requirements = {value.strip().lower() for value in _json(mold.process_requirements_json, []) if value.strip()}
    restrictions = {value.strip().lower() for value in _json(machine.process_restrictions_json, []) if value.strip()}
    conflicts = {
        "core_pull": "no_core_pull",
        "pvc": "no_pvc",
        "high_pressure": "high_pressure_limit",
    }
    for requirement in requirements:
        blocked_by = conflicts.get(requirement, requirement)
        if blocked_by in restrictions:
            failures.append(_reason("PROCESS_RESTRICTION", "工艺限制", f"模具要求 {requirement}，机台限制为 {blocked_by}。"))


def _score(
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold | None,
    order: InjectionSchedulingOrder,
    config: dict[str, Any],
    queue: list[InjectionSchedulingTask],
    queue_molds: dict[str, InjectionSchedulingMold],
    max_queue_count: int,
) -> list[InjectionSchedulingScoreBreakdownOut]:
    weights = {**DEFAULT_RULE_CONFIG["scoring_weights"], **config.get("scoring_weights", {})}
    breakdown: list[InjectionSchedulingScoreBreakdownOut] = []

    slack = order.delivery_slack_days
    if slack is None and order.delivery_due_date:
        try:
            slack = (date.fromisoformat(order.delivery_due_date) - business_now().date()).days
        except ValueError:
            slack = None
    urgency_factor = 1.0 if slack is not None and slack < 0 else 0.8 if slack is not None and slack <= 3 else 0.5 if slack is not None and slack <= 7 else 0.2
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="delivery_urgency", label="货期紧迫度",
        delta=round(float(weights["delivery_urgency"]) * urgency_factor, 2),
        explanation=f"交期差 {slack} 天。" if slack is not None else "交期未完整，按保守基础分。",
    ))

    priority_factor = {"CRITICAL": 1.0, "URGENT": 0.6, "NORMAL": 0.2}.get(order.priority_code, 0.2)
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="business_priority", label="业务优先级",
        delta=round(float(weights["business_priority"]) * priority_factor, 2),
        explanation=f"订单优先级 {order.priority_code}。",
    ))

    last_task = queue[-1] if queue else None
    same_mold = bool(last_task and mold and last_task.mold_id == mold.id)
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="same_mold", label="同模连续",
        delta=float(weights["same_mold"]) if same_mold else 0,
        explanation="当前队尾为同一模具，减少换模。" if same_mold else "当前队尾不是同一模具。",
    ))

    last_mold = queue_molds.get(last_task.mold_id) if last_task and last_task.mold_id else None
    same_material_color = bool(
        mold and last_mold
        and mold.material_code == last_mold.material_code
        and mold.color_profile == last_mold.color_profile
    )
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="same_material_color", label="同料同色连续",
        delta=float(weights["same_material_color"]) if same_material_color else 0,
        explanation="队尾同料同色，可减少洗机转色。" if same_material_color else "未形成同料同色连续。",
    ))

    capacity = _float(machine.injection_capacity_g) or 0
    required = _float(mold.whole_shot_net_weight_g) if mold is not None else None
    exact_class = bool(mold and mold.recommended_machine_class and mold.recommended_machine_class == machine.machine_class)
    utilization = required / capacity if required is not None and capacity else 0
    fit_factor = 1.0 if exact_class else 0.7 if 0.45 <= utilization <= 0.9 else 0.3
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="machine_fit", label="机台适配度",
        delta=round(float(weights["machine_fit"]) * fit_factor, 2),
        explanation="建议机型一致。" if exact_class else f"射胶容量利用率约 {utilization * 100:.1f}%。",
    ))

    balance_factor = 1 - len(queue) / max_queue_count if max_queue_count else 1.0
    breakdown.append(InjectionSchedulingScoreBreakdownOut(
        rule_code="queue_balance", label="队列负荷",
        delta=round(float(weights["queue_balance"]) * max(0.0, balance_factor), 2),
        explanation=f"当前后续队列 {len(queue)} 条。",
    ))
    return breakdown


def evaluate_order_matches(
    db: Session,
    *,
    factory_id: str,
    order_id: str,
    machine_ids: list[str] | None = None,
) -> InjectionSchedulingMatchEvaluationOut:
    factory_id = require_injection_scheduling_factory(factory_id)
    order = _require_order(db, factory_id, order_id)
    mold = _mold_for_order(db, factory_id, order)
    rules = current_rule_set(db, factory_id)
    config = {**DEFAULT_RULE_CONFIG, **_json(rules.config_json, {})}
    records = _machines(db, factory_id, machine_ids or [])
    queues, queue_molds = _queue_context(db, factory_id)
    max_queue_count = max((len(items) for items in queues.values()), default=0)
    results: list[InjectionSchedulingMachineMatchOut] = []
    for machine in records:
        failures: list[InjectionSchedulingMatchReasonOut] = []
        warnings: list[InjectionSchedulingMatchReasonOut] = []
        _dimension_checks(machine, mold, rules, failures, warnings)
        _capacity_check(machine, mold, rules, failures, warnings)
        _arm_and_fixture_checks(machine, mold, config, failures, warnings)
        _process_checks(machine, mold, failures, warnings)
        if mold and mold.color_profile and not config.get("color_scale"):
            warnings.append(_reason("COLOR_SCALE_UNCONFIGURED", "颜色顺序", "颜色色阶尚未配置，本轮不使用中文颜色名称猜测深浅。"))
        breakdown = [] if failures else _score(
            machine,
            mold,
            order,
            config,
            queues.get(machine.id, []),
            queue_molds,
            max_queue_count,
        )
        decision = "FAIL" if failures else "REVIEW_REQUIRED" if warnings else "PASS"
        score = None if failures else round(sum(item.delta for item in breakdown), 1)
        result_label = "硬约束失败" if failures else "资料待复核" if warnings else "硬约束通过"
        results.append(InjectionSchedulingMachineMatchOut(
            machine_id=machine.id,
            machine_code=machine.machine_code,
            decision=decision,
            score=score,
            hard_failures=failures,
            warnings=warnings,
            score_breakdown=breakdown,
            explanation=f"{machine.machine_code}：{result_label}；规则 revision {rules.revision}。",
            rule_set_id=rules.id,
            rule_set_revision=rules.revision,
        ))
    decision_rank = {"PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}
    results.sort(key=lambda item: (decision_rank[item.decision], -(item.score or -1), item.machine_code))
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
        raise HTTPException(status_code=409, detail={
            "message": "计划草案已被其他操作更新",
            "expected_revision": payload.expected_plan_revision,
            "current_revision": plan.revision,
        })
    if match.rule_set_revision != payload.expected_rule_revision or plan.rule_revision != match.rule_set_revision:
        raise HTTPException(status_code=409, detail={
            "message": "匹配规则版本已变化，请重新获取候选机台",
            "current_rule_revision": match.rule_set_revision,
            "plan_rule_revision": plan.rule_revision,
        })
    if match.decision == "FAIL":
        raise HTTPException(status_code=409, detail="硬约束失败的机台禁止排入草案")
    if match.decision == "REVIEW_REQUIRED" and not payload.override_reason:
        raise HTTPException(status_code=409, detail={
            "message": "资料待复核的候选必须填写人工覆盖原因",
            "override_reason_required": True,
        })
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
        base_start = max(base_start, datetime.fromisoformat(machine_tasks[-1].planned_finish))
    outstanding = max(float(order.order_quantity - order.completed_quantity), 0.0)
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="订单已无欠数")
    previous_target = float(machine_tasks[-1].shift_target_quantity) if machine_tasks else 0.0
    shift_target = previous_target if previous_target > 0 else min(outstanding, 1400.0)
    shift_count = max(1, math.ceil(outstanding / shift_target))
    planned_finish = base_start + timedelta(hours=12 * shift_count)
    task_payload = InjectionSchedulingTaskCreate(
        factory_id=payload.factory_id,
        expected_revision=payload.expected_plan_revision,
        machine_id=payload.machine_id,
        order_id=order.id,
        mold_id=order.mold_id,
        mold_copy_no=1,
        sequence_no=(machine_tasks[-1].sequence_no + 1) if machine_tasks else 0,
        execution_status="QUEUED",
        planned_start=base_start.isoformat(timespec="seconds"),
        planned_finish=planned_finish.isoformat(timespec="seconds"),
        shift_target_quantity=shift_target,
        locked=False,
        manual_override_reason=payload.override_reason if match.decision == "REVIEW_REQUIRED" else "",
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
