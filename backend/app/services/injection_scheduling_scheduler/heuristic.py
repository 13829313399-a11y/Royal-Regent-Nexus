from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from time import monotonic
from typing import Any

from app.models.injection_scheduling import InjectionSchedulingMachine
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_scheduler import InjectionSchedulingMachineCalendar
from app.schemas.injection_scheduling_matching import (
    InjectionSchedulingMachineMatchOut,
    InjectionSchedulingMatchBatchOut,
)
from app.services.injection_scheduling_mold_context import (
    SchedulingMoldContext,
    order_mold_key,
    task_mold_key,
)
from app.services.injection_scheduling_scheduler.anchor import next_feasible_start
from app.services.injection_scheduling_scheduler.duration import production_estimate
from app.services.injection_scheduling_scheduler.explanation import (
    assignment_explanation,
    unassigned_explanation,
)
from app.services.injection_scheduling_scheduler.normalization import (
    as_business_datetime,
    color_rank,
    iso_seconds,
)
from app.services.injection_scheduling_scheduler.scoring import placement_score
from app.services.injection_scheduling_scheduler.transition import transition_impact


@dataclass(slots=True)
class QueueSlot:
    machine_id: str
    order_id: str
    mold_id: str | None
    mold_copy_no: int
    sequence_no: int
    start: datetime
    finish: datetime


@dataclass(frozen=True, slots=True)
class HeuristicResult:
    assignments: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    frozen_task_ids: tuple[str, ...]


def _order_sort_key(order: InjectionSchedulingOrder) -> tuple[Any, ...]:
    due = order.delivery_due_date or "9999-12-31"
    overdue_rank = (
        0
        if order.delivery_slack_days is not None and order.delivery_slack_days < 0
        else 1
    )
    priority_rank = {"CRITICAL": 0, "URGENT": 1, "NORMAL": 2}.get(
        order.priority_code, 3
    )
    return (
        overdue_rank,
        due,
        priority_rank,
        order.order_no,
        order.id,
    )


def _priority_bucket(order: InjectionSchedulingOrder) -> tuple[Any, ...]:
    """Keep local moves inside the same delivery/priority boundary."""
    key = _order_sort_key(order)
    return key[:3]


def _locally_batch_orders(
    orders: list[InjectionSchedulingOrder],
    molds: dict[str, SchedulingMoldContext],
) -> tuple[list[InjectionSchedulingOrder], int]:
    """Deterministically batch compatible molds without weakening due-date order."""
    baseline = sorted(orders, key=_order_sort_key)
    improved: list[InjectionSchedulingOrder] = []
    cursor = 0
    while cursor < len(baseline):
        bucket = _priority_bucket(baseline[cursor])
        end = cursor + 1
        while end < len(baseline) and _priority_bucket(baseline[end]) == bucket:
            end += 1
        pending = list(baseline[cursor:end])
        while pending:
            previous_mold_id = order_mold_key(improved[-1]) if improved else None
            same_mold = next(
                (
                    item
                    for item in pending
                    if previous_mold_id and order_mold_key(item) == previous_mold_id
                ),
                None,
            )
            selected = same_mold or min(
                pending,
                key=lambda item: (
                    molds[order_mold_key(item)].mold_no
                    if order_mold_key(item) in molds
                    else "~",
                    item.order_no,
                    item.id,
                ),
            )
            improved.append(selected)
            pending.remove(selected)
        cursor = end
    move_count = sum(
        1 for index, order in enumerate(improved) if baseline[index].id != order.id
    )
    return improved, move_count


def _queue_metrics(
    slots_by_machine: dict[str, list[QueueSlot]],
    molds: dict[str, SchedulingMoldContext],
) -> dict[str, int]:
    mold_changes = 0
    dark_to_light = 0
    for slots in slots_by_machine.values():
        ordered = sorted(
            slots, key=lambda item: (item.start, item.sequence_no, item.order_id)
        )
        for previous, current in pairwise(ordered):
            previous_mold = molds.get(previous.mold_id or "")
            current_mold = molds.get(current.mold_id or "")
            if previous.mold_id != current.mold_id:
                mold_changes += 1
            if (
                previous_mold
                and current_mold
                and color_rank(previous_mold.color_profile)
                > color_rank(current_mold.color_profile)
            ):
                dark_to_light += 1
    return {"mold_changes": mold_changes, "dark_to_light_changes": dark_to_light}


def solve_heuristic(
    *,
    orders: list[InjectionSchedulingOrder],
    machines: list[InjectionSchedulingMachine],
    molds: dict[str, SchedulingMoldContext],
    plan_tasks: list[InjectionSchedulingTask],
    matches: InjectionSchedulingMatchBatchOut,
    calendars: list[InjectionSchedulingMachineCalendar],
    horizon_start: datetime,
    horizon_end: datetime,
    objective_config: dict[str, Any],
    time_limit_seconds: int,
    machine_anchors: dict[str, datetime] | None = None,
) -> HeuristicResult:
    started = monotonic()
    order_ids = {item.id for item in orders}
    order_by_id = {item.id: item for item in orders}
    tasks_by_order: dict[str, list[InjectionSchedulingTask]] = {}
    for item in plan_tasks:
        if item.order_id in order_ids and item.execution_status != "CANCELLED":
            tasks_by_order.setdefault(item.order_id, []).append(item)
    allocated_by_order = {
        order_id: sum(
            (Decimal(item.allocated_quantity or 0) for item in items), Decimal(0)
        )
        for order_id, items in tasks_by_order.items()
    }
    partial_order_ids = {
        item.id
        for item in orders
        if item.status == "BACKLOG" and allocated_by_order.get(item.id, Decimal(0)) > 0
    }
    task_by_order: dict[str, InjectionSchedulingTask] = {}
    for item in sorted(plan_tasks, key=lambda task: task.id):
        if item.order_id in order_ids and item.order_id not in partial_order_ids:
            task_by_order.setdefault(item.order_id, item)
    evaluation_by_order = {item.order_id: item for item in matches.evaluations}
    machine_by_id = {item.id: item for item in machines}
    calendar_by_machine: dict[str, list[InjectionSchedulingMachineCalendar]] = {}
    for item in calendars:
        calendar_by_machine.setdefault(item.machine_id, []).append(item)

    schedulable_order_ids: set[str] = set()
    for order in orders:
        evaluation = evaluation_by_order[order.id]
        has_candidate = any(item.decision != "FAIL" for item in evaluation.results)
        if (
            has_candidate
            and order.material_readiness_status != "blocked"
            and order_mold_key(order) in molds
        ):
            schedulable_order_ids.add(order.id)

    fixed_tasks = [
        item
        for item in plan_tasks
        if item.order_id not in schedulable_order_ids
        or item.order_id not in order_ids
        or item.order_id in partial_order_ids
        or item.locked
        or item.active_execution
        or item.execution_status == "RUNNING"
    ]
    frozen_task_ids = tuple(sorted(item.id for item in fixed_tasks))
    frozen_order_ids = {
        item.order_id
        for item in fixed_tasks
        if item.order_id not in partial_order_ids
    }
    slots_by_machine: dict[str, list[QueueSlot]] = {item.id: [] for item in machines}
    mold_available: dict[tuple[str, int], datetime] = {}
    for task in fixed_tasks:
        if (
            task.machine_id not in slots_by_machine
            or not task.planned_start
            or not task.planned_finish
        ):
            continue
        slot = QueueSlot(
            machine_id=task.machine_id,
            order_id=task.order_id,
            mold_id=task_mold_key(task, order_by_id),
            mold_copy_no=task.mold_copy_no,
            sequence_no=task.sequence_no,
            start=as_business_datetime(task.planned_start),
            finish=as_business_datetime(task.planned_finish),
        )
        slots_by_machine[task.machine_id].append(slot)
        task_key = task_mold_key(task, order_by_id)
        if task_key:
            key = (task_key, task.mold_copy_no)
            mold_available[key] = max(
                mold_available.get(key, horizon_start), slot.finish
            )

    before_slots: dict[str, list[QueueSlot]] = {item.id: [] for item in machines}
    for task in plan_tasks:
        if (
            task.machine_id in before_slots
            and task.planned_start
            and task.planned_finish
        ):
            before_slots[task.machine_id].append(
                QueueSlot(
                    task.machine_id,
                    task.order_id,
                    task_mold_key(task, order_by_id),
                    task.mold_copy_no,
                    task.sequence_no,
                    as_business_datetime(task.planned_start),
                    as_business_datetime(task.planned_finish),
                )
            )

    ordered_orders, local_improvement_moves = _locally_batch_orders(orders, molds)
    assignments: list[dict[str, Any]] = []
    for order in ordered_orders:
        if monotonic() - started > time_limit_seconds:
            raise TimeoutError("启发式排期超过时间上限")
        existing_task = task_by_order.get(order.id)
        if order.id in frozen_order_ids:
            continue
        if order.material_readiness_status == "blocked":
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": existing_task.id if existing_task else None,
                    "mold_id": order.mold_id,
                    "mold_copy_no": existing_task.mold_copy_no if existing_task else 1,
                    "machine_id": None,
                    "sequence_no": None,
                    "planned_start": "",
                    "planned_finish": "",
                    "setup_minutes": 0,
                    "production_minutes": 0,
                    "planned_downtime_minutes": 0,
                    "changeover_type": "",
                    "decision": "UNASSIGNED",
                    "score": None,
                    "explanation": unassigned_explanation(
                        "MATERIAL_BLOCKED", "物料状态为 blocked，自动排期禁止安排。"
                    ),
                    "unassigned_reason_code": "MATERIAL_BLOCKED",
                }
            )
            continue
        mold = molds.get(order_mold_key(order))
        if mold is None:
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": existing_task.id if existing_task else None,
                    "mold_id": order.mold_id,
                    "mold_copy_no": 1,
                    "machine_id": None,
                    "sequence_no": None,
                    "planned_start": "",
                    "planned_finish": "",
                    "setup_minutes": 0,
                    "production_minutes": 0,
                    "planned_downtime_minutes": 0,
                    "changeover_type": "",
                    "decision": "UNASSIGNED",
                    "score": None,
                    "explanation": unassigned_explanation(
                        "MOLD_MISSING", "订单没有可用的关联模具资料。"
                    ),
                    "unassigned_reason_code": "MOLD_MISSING",
                }
            )
            continue
        evaluation = evaluation_by_order[order.id]
        eligible = [
            item
            for item in evaluation.results
            if item.decision != "FAIL" and item.machine_id in machine_by_id
        ]
        if any(item.decision == "PASS" for item in eligible):
            eligible = [item for item in eligible if item.decision == "PASS"]
        if not eligible:
            failures = [
                reason.model_dump(mode="json")
                for result in evaluation.results
                for reason in result.hard_failures
            ]
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": existing_task.id if existing_task else None,
                    "mold_id": order.mold_id,
                    "mold_copy_no": existing_task.mold_copy_no if existing_task else 1,
                    "machine_id": None,
                    "sequence_no": None,
                    "planned_start": "",
                    "planned_finish": "",
                    "setup_minutes": 0,
                    "production_minutes": 0,
                    "planned_downtime_minutes": 0,
                    "changeover_type": "",
                    "decision": "UNASSIGNED",
                    "score": None,
                    "explanation": unassigned_explanation(
                        "NO_ELIGIBLE_MACHINE", "所有候选机台均有硬约束失败。", failures
                    ),
                    "unassigned_reason_code": "NO_ELIGIBLE_MACHINE",
                }
            )
            continue

        horizon_minutes = max(
            1, int((horizon_end - horizon_start).total_seconds() / 60)
        )
        setup_buffer = max(
            int(objective_config.get("dark_to_light_minutes", 60)),
            int(objective_config.get("mold_change_minutes", 30))
            + int(objective_config.get("material_change_minutes", 20))
            + int(objective_config.get("color_change_minutes", 10)),
        )
        estimate = production_estimate(
            order,
            objective_config,
            already_allocated_quantity=allocated_by_order.get(
                order.id, Decimal(0)
            )
            if order.id in partial_order_ids
            else Decimal(0),
            max_production_minutes=max(1, horizon_minutes - setup_buffer),
        )
        production = estimate.production_minutes
        if production <= 0 or estimate.planned_quantity <= 0:
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": existing_task.id if existing_task else None,
                    "mold_id": mold.id,
                    "mold_copy_no": existing_task.mold_copy_no
                    if existing_task
                    else 1,
                    "machine_id": None,
                    "sequence_no": None,
                    "planned_start": "",
                    "planned_finish": "",
                    "setup_minutes": 0,
                    "production_minutes": 0,
                    "planned_downtime_minutes": 0,
                    "changeover_type": "",
                    "decision": "UNASSIGNED",
                    "score": None,
                    "explanation": {
                        **unassigned_explanation(
                            "ALREADY_FULLY_ALLOCATED",
                            "当前草案已覆盖订单全部未完成数量，无需重复排期。",
                        ),
                        "production": estimate.explanation(),
                    },
                    "unassigned_reason_code": "ALREADY_FULLY_ALLOCATED",
                }
            )
            continue
        candidates: list[
            tuple[
                float,
                str,
                int,
                datetime,
                datetime,
                InjectionSchedulingMachineMatchOut,
                Any,
                Any,
            ]
        ] = []
        for match in eligible:
            machine = machine_by_id[match.machine_id]
            queue = slots_by_machine[machine.id]
            last_slot = max(
                queue, key=lambda item: (item.finish, item.sequence_no), default=None
            )
            previous_mold = molds.get(last_slot.mold_id or "") if last_slot else None
            transition = transition_impact(previous_mold, mold, objective_config)
            duration = timedelta(minutes=transition.setup_minutes + production)
            machine_start = max(
                horizon_start,
                (machine_anchors or {}).get(machine.id, horizon_start),
                last_slot.finish if last_slot else horizon_start,
            )
            best_copy: tuple[datetime, int] | None = None
            for copy_no in range(1, mold.copy_count + 1):
                copy_start = max(
                    machine_start, mold_available.get((mold.id, copy_no), horizon_start)
                )
                copy_start = next_feasible_start(
                    copy_start, duration, calendar_by_machine.get(machine.id, [])
                )
                if best_copy is None or (copy_start, copy_no) < best_copy:
                    best_copy = (copy_start, copy_no)
            assert best_copy is not None
            start, copy_no = best_copy
            finish = start + duration
            if finish > horizon_end:
                continue
            machine_load = sum(
                max(0, int((item.finish - item.start).total_seconds() / 60))
                for item in queue
            )
            score = placement_score(
                order=order,
                machine=machine,
                mold=mold,
                finish=finish,
                transition=transition,
                machine_load_minutes=machine_load,
                horizon_minutes=horizon_minutes,
                existing_task=existing_task,
                planned_start=iso_seconds(start),
                config=objective_config,
            )
            candidates.append(
                (
                    score.total,
                    machine.machine_code,
                    copy_no,
                    start,
                    finish,
                    match,
                    transition,
                    score,
                )
            )
        if not candidates:
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": existing_task.id if existing_task else None,
                    "mold_id": mold.id,
                    "mold_copy_no": existing_task.mold_copy_no if existing_task else 1,
                    "machine_id": None,
                    "sequence_no": None,
                    "planned_start": "",
                    "planned_finish": "",
                    "setup_minutes": 0,
                    "production_minutes": production,
                    "planned_downtime_minutes": 0,
                    "changeover_type": "",
                    "decision": "UNASSIGNED",
                    "score": None,
                    "explanation": {
                        **unassigned_explanation(
                            "HORIZON_EXCEEDED",
                            "该订单当前分段仍无法放入排期范围，其他订单不受影响。",
                        ),
                        "production": estimate.explanation(),
                    },
                    "unassigned_reason_code": "HORIZON_EXCEEDED",
                }
            )
            continue
        total, _, copy_no, start, finish, match, transition, score = min(
            candidates, key=lambda item: (item[0], item[1], item[2], item[3])
        )
        queue = slots_by_machine[match.machine_id]
        sequence_no = max((item.sequence_no for item in queue), default=-1) + 1
        slot = QueueSlot(
            match.machine_id, order.id, mold.id, copy_no, sequence_no, start, finish
        )
        queue.append(slot)
        mold_available[(mold.id, copy_no)] = finish
        explanation = assignment_explanation(
            match, score, transition, machine_by_id[match.machine_id], mold
        )
        explanation["production"] = estimate.explanation()
        if estimate.split_required:
            explanation["summary"] = (
                f"当前窗口安排 {float(estimate.planned_quantity):g}，"
                f"剩余 {float(estimate.remaining_quantity):g} 继续留在待排订单。"
            )
        assignments.append(
            {
                "order_id": order.id,
                "existing_task_id": existing_task.id if existing_task else None,
                "mold_id": order.mold_id,
                "mold_copy_no": copy_no,
                "machine_id": match.machine_id,
                "sequence_no": sequence_no,
                "planned_start": iso_seconds(start),
                "planned_finish": iso_seconds(finish),
                "setup_minutes": transition.setup_minutes,
                "production_minutes": production,
                "planned_downtime_minutes": 0,
                "changeover_type": transition.changeover_type,
                "decision": match.decision,
                "score": total,
                "explanation": explanation,
                "unassigned_reason_code": "",
            }
        )

    before_metrics = _queue_metrics(before_slots, molds)
    after_metrics = _queue_metrics(slots_by_machine, molds)
    overdue_before = sum(
        1
        for slots in before_slots.values()
        for slot in slots
        if order_by_id.get(slot.order_id)
        and order_by_id[slot.order_id].delivery_due_date
        and slot.finish.date().isoformat()
        > order_by_id[slot.order_id].delivery_due_date
    )
    overdue_after = sum(
        1
        for slots in slots_by_machine.values()
        for slot in slots
        if order_by_id.get(slot.order_id)
        and order_by_id[slot.order_id].delivery_due_date
        and slot.finish.date().isoformat()
        > order_by_id[slot.order_id].delivery_due_date
    )
    scheduled = [item for item in assignments if item["decision"] == "PASS"]
    reviews = [item for item in assignments if item["decision"] == "REVIEW_REQUIRED"]
    unassigned = [item for item in assignments if item["decision"] == "UNASSIGNED"]
    moved = sum(
        1
        for item in scheduled + reviews
        if item["existing_task_id"]
        and (
            task_by_order[item["order_id"]].machine_id != item["machine_id"]
            or task_by_order[item["order_id"]].planned_start != item["planned_start"]
            or task_by_order[item["order_id"]].planned_finish != item["planned_finish"]
        )
    )
    horizon_minutes = max(1, int((horizon_end - horizon_start).total_seconds() / 60))
    machine_loads = [
        {
            "machine_id": machine.id,
            "machine_code": machine.machine_code,
            "scheduled_minutes": sum(
                max(0, int((slot.finish - slot.start).total_seconds() / 60))
                for slot in slots_by_machine[machine.id]
            ),
            "load_ratio": round(
                sum(
                    max(0, int((slot.finish - slot.start).total_seconds() / 60))
                    for slot in slots_by_machine[machine.id]
                )
                / horizon_minutes,
                4,
            ),
        }
        for machine in machines
    ]
    summary = {
        "input_order_count": len(orders),
        "scheduled_count": len(scheduled),
        "review_count": len(reviews),
        "unassigned_count": len(unassigned),
        "moved_task_count": moved,
        "local_improvement_move_count": local_improvement_moves,
        "overdue": {
            "before": overdue_before,
            "after": overdue_after,
            "change": overdue_after - overdue_before,
        },
        "mold_changes": {
            "before": before_metrics["mold_changes"],
            "after": after_metrics["mold_changes"],
            "change": after_metrics["mold_changes"] - before_metrics["mold_changes"],
        },
        "dark_to_light_changes": {
            "before": before_metrics["dark_to_light_changes"],
            "after": after_metrics["dark_to_light_changes"],
            "change": after_metrics["dark_to_light_changes"]
            - before_metrics["dark_to_light_changes"],
        },
        "machine_loads": machine_loads,
        "frozen_task_count": len(frozen_task_ids),
        "solver_elapsed_ms": round((monotonic() - started) * 1000, 2),
    }
    return HeuristicResult(tuple(assignments), summary, frozen_task_ids)
