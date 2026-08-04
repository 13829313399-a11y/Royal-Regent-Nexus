from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from app.core.time import BUSINESS_TIME_ZONE
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingTask,
)
from app.services.injection_scheduling_scheduler.transition import TransitionImpact


@dataclass(frozen=True, slots=True)
class PlacementScore:
    total: float
    breakdown: tuple[dict[str, Any], ...]


def placement_score(
    *,
    order: InjectionSchedulingOrder,
    machine: InjectionSchedulingMachine,
    mold: InjectionSchedulingMold,
    finish: datetime,
    transition: TransitionImpact,
    machine_load_minutes: int,
    horizon_minutes: int,
    existing_task: InjectionSchedulingTask | None,
    planned_start: str,
    config: dict[str, Any],
) -> PlacementScore:
    priority_weight = {"CRITICAL": 4.0, "URGENT": 2.0, "NORMAL": 1.0}.get(
        order.priority_code, 1.0
    )
    tardy_hours = 0.0
    if order.delivery_due_date:
        try:
            due = datetime.combine(
                datetime.fromisoformat(order.delivery_due_date).date(),
                time.max,
                tzinfo=BUSINESS_TIME_ZONE,
            )
            tardy_hours = max(0.0, (finish - due).total_seconds() / 3600)
        except ValueError:
            tardy_hours = 0.0
    tardiness_cost = (
        tardy_hours * priority_weight * float(config.get("tardiness_weight", 100))
    )
    transition_cost = transition.setup_minutes * float(
        config.get("transition_weight", 2)
    )
    class_gap = max(
        float(machine.machine_a_class or 0) - float(mold.mold_a_class or 0), 0.0
    )
    class_cost = class_gap * float(config.get("class_gap_weight", 1.5))
    load_ratio = machine_load_minutes / max(horizon_minutes, 1)
    load_cost = load_ratio * float(config.get("load_balance_weight", 25))
    disruption = 0.0
    if existing_task is not None and (
        existing_task.machine_id != machine.id
        or existing_task.planned_start != planned_start
    ):
        disruption = float(config.get("existing_task_move_cost", 40))
    total = round(
        tardiness_cost + transition_cost + class_cost + load_cost + disruption, 3
    )
    return PlacementScore(
        total=total,
        breakdown=(
            {
                "code": "weighted_tardiness",
                "cost": round(tardiness_cost, 3),
                "detail": f"预计拖期 {tardy_hours:.1f} 小时，优先权重 {priority_weight:g}",
            },
            {
                "code": "transition",
                "cost": round(transition_cost, 3),
                "detail": f"换模/转料/转色共 {transition.setup_minutes} 分钟",
            },
            {
                "code": "minimum_a_class",
                "cost": round(class_cost, 3),
                "detail": f"机台比模具高 {class_gap:g}A",
            },
            {
                "code": "load_balance",
                "cost": round(load_cost, 3),
                "detail": f"候选前负荷 {load_ratio:.1%}",
            },
            {
                "code": "plan_disruption",
                "cost": round(disruption, 3),
                "detail": "保持原位置" if not disruption else "移动现有未锁定任务",
            },
        ),
    )
