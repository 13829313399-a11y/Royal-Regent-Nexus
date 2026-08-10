from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from math import ceil
from time import monotonic
from typing import Any

from app.core.time import BUSINESS_TIME_ZONE
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
from app.services.injection_scheduling_scheduler.duration import (
    ProductionEstimate,
    production_estimate,
)
from app.services.injection_scheduling_scheduler.explanation import (
    assignment_explanation,
    unassigned_explanation,
)
from app.services.injection_scheduling_scheduler.heuristic import (
    HeuristicResult,
    QueueSlot,
    _queue_metrics,
)
from app.services.injection_scheduling_scheduler.normalization import (
    as_business_datetime,
    iso_seconds,
)
from app.services.injection_scheduling_scheduler.scoring import placement_score
from app.services.injection_scheduling_scheduler.transition import transition_impact


class CpSatUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class _Option:
    order_id: str
    machine_id: str
    mold_copy_no: int
    presence: Any
    interval: Any


@dataclass(slots=True)
class _MachineNode:
    order_id: str
    mold_id: str | None
    start: Any
    end: Any
    presence: Any | None


def _load_cp_sat():
    try:
        from ortools.sat.python import cp_model
    except (ImportError, OSError) as exc:
        raise CpSatUnavailableError(f"OR-Tools CP-SAT 不可用：{exc}") from exc
    return cp_model


def _minute_offset(value: datetime, origin: datetime) -> int:
    return int((value - origin).total_seconds() // 60)


def _unassigned(
    order: InjectionSchedulingOrder,
    existing_task: InjectionSchedulingTask | None,
    *,
    mold_id: str | None,
    code: str,
    detail: str,
    failures: list[dict[str, Any]] | None = None,
    production: int = 0,
) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "existing_task_id": existing_task.id if existing_task else None,
        "mold_id": mold_id,
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
        "explanation": unassigned_explanation(code, detail, failures),
        "unassigned_reason_code": code,
    }


def _empty_summary(
    *,
    orders: list[InjectionSchedulingOrder],
    assignments: list[dict[str, Any]],
    frozen_task_ids: tuple[str, ...],
    solver_status: str,
    elapsed_ms: float,
    objective_value: float | None = None,
    best_bound: float | None = None,
) -> dict[str, Any]:
    return {
        "input_order_count": len(orders),
        "scheduled_count": 0,
        "review_count": 0,
        "unassigned_count": len(assignments),
        "moved_task_count": 0,
        "local_improvement_move_count": 0,
        "overdue": {"before": 0, "after": 0, "change": 0},
        "mold_changes": {"before": 0, "after": 0, "change": 0},
        "dark_to_light_changes": {"before": 0, "after": 0, "change": 0},
        "machine_loads": [],
        "frozen_task_count": len(frozen_task_ids),
        "solver_elapsed_ms": round(elapsed_ms, 2),
        "solver_status": solver_status,
        "objective_value": objective_value,
        "best_objective_bound": best_bound,
    }


def solve_cp_sat(
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
    cp_model = _load_cp_sat()
    started = monotonic()
    horizon_minutes = max(1, ceil((horizon_end - horizon_start).total_seconds() / 60))
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
    machine_by_id = {item.id: item for item in machines}
    evaluation_by_order = {item.order_id: item for item in matches.evaluations}

    assignments: list[dict[str, Any]] = []
    candidate_orders: list[InjectionSchedulingOrder] = []
    eligible_by_order: dict[str, list[InjectionSchedulingMachineMatchOut]] = {}
    estimates_by_order: dict[str, ProductionEstimate] = {}
    frozen_order_ids = {
        item.order_id
        for item in plan_tasks
        if item.locked or item.active_execution or item.execution_status == "RUNNING"
    }
    for order in orders:
        existing_task = task_by_order.get(order.id)
        if order.id in frozen_order_ids and order.id not in partial_order_ids:
            continue
        if order.material_readiness_status == "blocked":
            assignments.append(
                _unassigned(
                    order,
                    existing_task,
                    mold_id=order.mold_id,
                    code="MATERIAL_BLOCKED",
                    detail="物料状态为 blocked，CP-SAT 禁止安排。",
                )
            )
            continue
        mold = molds.get(order_mold_key(order))
        if mold is None:
            assignments.append(
                _unassigned(
                    order,
                    existing_task,
                    mold_id=order.mold_id,
                    code="MOLD_MISSING",
                    detail="订单没有可用的关联模具资料。",
                )
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
                _unassigned(
                    order,
                    existing_task,
                    mold_id=mold.id,
                    code="NO_ELIGIBLE_MACHINE",
                    detail="所有候选机台均有硬约束失败。",
                    failures=failures,
                )
            )
            continue
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
        if estimate.production_minutes <= 0 or estimate.planned_quantity <= 0:
            detail = "当前草案已覆盖订单全部未完成数量，无需重复排期。"
            unassigned = _unassigned(
                order,
                existing_task,
                mold_id=mold.id,
                code="ALREADY_FULLY_ALLOCATED",
                detail=detail,
            )
            unassigned["explanation"]["production"] = estimate.explanation()
            assignments.append(unassigned)
            continue
        candidate_orders.append(order)
        eligible_by_order[order.id] = eligible
        estimates_by_order[order.id] = estimate

    schedulable_ids = {item.id for item in candidate_orders}
    fixed_tasks = [
        item
        for item in plan_tasks
        if item.order_id not in schedulable_ids
        or item.order_id not in order_ids
        or item.order_id in partial_order_ids
        or item.locked
        or item.active_execution
        or item.execution_status == "RUNNING"
    ]
    frozen_task_ids = tuple(sorted(item.id for item in fixed_tasks))
    machine_release_minutes: dict[str, int] = {
        machine_id: max(0, _minute_offset(anchor, horizon_start))
        for machine_id, anchor in (machine_anchors or {}).items()
    }
    for task in fixed_tasks:
        if not task.planned_finish:
            continue
        release = _minute_offset(
            as_business_datetime(task.planned_finish), horizon_start
        )
        machine_release_minutes[task.machine_id] = max(
            machine_release_minutes.get(task.machine_id, 0), release
        )
    if not candidate_orders:
        summary = _empty_summary(
            orders=orders,
            assignments=assignments,
            frozen_task_ids=frozen_task_ids,
            solver_status="OPTIMAL",
            elapsed_ms=(monotonic() - started) * 1000,
            objective_value=0,
            best_bound=0,
        )
        return HeuristicResult(tuple(assignments), summary, frozen_task_ids)

    model = cp_model.CpModel()
    start_vars: dict[str, Any] = {}
    end_vars: dict[str, Any] = {}
    durations: dict[str, int] = {}
    options_by_order: dict[str, list[_Option]] = {}
    machine_intervals: dict[str, list[Any]] = {item.id: [] for item in machines}
    mold_intervals: dict[tuple[str, int], list[Any]] = {}
    machine_nodes: dict[str, list[_MachineNode]] = {item.id: [] for item in machines}
    objective_terms: list[Any] = []

    for order in candidate_orders:
        estimate = estimates_by_order[order.id]
        duration = estimate.production_minutes
        durations[order.id] = duration
        start_var = model.NewIntVar(0, horizon_minutes - 1, f"start_{order.id}")
        end_var = model.NewIntVar(1, horizon_minutes, f"end_{order.id}")
        model.Add(end_var == start_var + duration)
        start_vars[order.id] = start_var
        end_vars[order.id] = end_var
        mold = molds[order_mold_key(order)]
        options: list[_Option] = []
        by_machine: dict[str, list[Any]] = {}
        for match in eligible_by_order[order.id]:
            for copy_no in range(1, mold.copy_count + 1):
                presence = model.NewBoolVar(
                    f"assign_{order.id}_{match.machine_id}_{copy_no}"
                )
                interval = model.NewOptionalIntervalVar(
                    start_var,
                    duration,
                    end_var,
                    presence,
                    f"interval_{order.id}_{match.machine_id}_{copy_no}",
                )
                option = _Option(
                    order.id, match.machine_id, copy_no, presence, interval
                )
                model.Add(
                    start_var
                    >= max(0, machine_release_minutes.get(match.machine_id, 0))
                ).OnlyEnforceIf(presence)
                options.append(option)
                by_machine.setdefault(match.machine_id, []).append(presence)
                machine_intervals[match.machine_id].append(interval)
                mold_intervals.setdefault((mold.id, copy_no), []).append(interval)
                machine = machine_by_id[match.machine_id]
                class_gap = max(
                    float(machine.machine_a_class or 0) - float(mold.mold_a_class or 0),
                    0,
                )
                option_cost = round(
                    class_gap * float(objective_config.get("class_gap_weight", 1.5))
                )
                existing_task = task_by_order.get(order.id)
                if existing_task and existing_task.machine_id != machine.id:
                    option_cost += int(
                        objective_config.get("existing_task_move_cost", 40)
                    )
                if option_cost:
                    objective_terms.append(option_cost * presence)
        model.AddExactlyOne([item.presence for item in options])
        options_by_order[order.id] = options
        for machine_id, presences in by_machine.items():
            machine_presence = model.NewBoolVar(f"on_machine_{order.id}_{machine_id}")
            model.Add(sum(presences) == machine_presence)
            machine_nodes[machine_id].append(
                _MachineNode(
                    order.id,
                    mold.id,
                    start_var,
                    end_var,
                    machine_presence,
                )
            )

        due_minute = horizon_minutes
        if order.delivery_due_date:
            try:
                due_at = datetime.combine(
                    datetime.fromisoformat(order.delivery_due_date).date(),
                    time.max,
                    tzinfo=BUSINESS_TIME_ZONE,
                )
                due_minute = _minute_offset(due_at, horizon_start)
            except ValueError:
                due_minute = horizon_minutes
        tardiness = model.NewIntVar(0, horizon_minutes * 2, f"tardy_{order.id}")
        model.Add(tardiness >= end_var - due_minute)
        priority = {"CRITICAL": 4, "URGENT": 2, "NORMAL": 1}.get(order.priority_code, 1)
        tardiness_cost = priority * int(objective_config.get("tardiness_weight", 100))
        if tardiness_cost:
            objective_terms.append(tardiness_cost * tardiness)

    for task in fixed_tasks:
        if (
            task.machine_id not in machine_intervals
            or not task.planned_start
            or not task.planned_finish
        ):
            continue
        fixed_start = max(
            0, _minute_offset(as_business_datetime(task.planned_start), horizon_start)
        )
        fixed_end = min(
            horizon_minutes,
            _minute_offset(as_business_datetime(task.planned_finish), horizon_start),
        )
        if fixed_end <= fixed_start:
            continue
        interval = model.NewFixedSizeIntervalVar(
            fixed_start, fixed_end - fixed_start, f"fixed_task_{task.id}"
        )
        machine_intervals[task.machine_id].append(interval)
        task_key = task_mold_key(task, order_by_id)
        machine_nodes[task.machine_id].append(
            _MachineNode(task.order_id, task_key or None, fixed_start, fixed_end, None)
        )
        if task_key:
            mold_intervals.setdefault((task_key, task.mold_copy_no), []).append(
                interval
            )

    for calendar in calendars:
        if calendar.available or calendar.machine_id not in machine_intervals:
            continue
        blocked_start = max(
            0,
            _minute_offset(as_business_datetime(calendar.window_start), horizon_start),
        )
        blocked_end = min(
            horizon_minutes,
            _minute_offset(as_business_datetime(calendar.window_end), horizon_start),
        )
        if blocked_end > blocked_start:
            machine_intervals[calendar.machine_id].append(
                model.NewFixedSizeIntervalVar(
                    blocked_start,
                    blocked_end - blocked_start,
                    f"calendar_{calendar.id}",
                )
            )

    for intervals in machine_intervals.values():
        if intervals:
            model.AddNoOverlap(intervals)
    for intervals in mold_intervals.values():
        if intervals:
            model.AddNoOverlap(intervals)

    transition_weight = int(objective_config.get("transition_weight", 2))
    for machine_id, nodes in machine_nodes.items():
        if not nodes:
            continue
        arcs: list[tuple[int, int, Any]] = []
        variable_presences = [
            item.presence for item in nodes if item.presence is not None
        ]
        fixed_count = sum(item.presence is None for item in nodes)
        if not fixed_count:
            empty = model.NewBoolVar(f"empty_{machine_id}")
            model.Add(sum(variable_presences) == 0).OnlyEnforceIf(empty)
            model.Add(sum(variable_presences) >= 1).OnlyEnforceIf(empty.Not())
            arcs.append((0, 0, empty))
        for index, node in enumerate(nodes, start=1):
            if node.presence is not None:
                arcs.append((index, index, node.presence.Not()))
            first = model.NewBoolVar(f"first_{machine_id}_{index}")
            last = model.NewBoolVar(f"last_{machine_id}_{index}")
            if node.presence is not None:
                model.AddImplication(first, node.presence)
                model.AddImplication(last, node.presence)
            arcs.extend(((0, index, first), (index, 0, last)))
        for left_index, left in enumerate(nodes, start=1):
            for right_index, right in enumerate(nodes, start=1):
                if left_index == right_index:
                    continue
                arc = model.NewBoolVar(f"arc_{machine_id}_{left_index}_{right_index}")
                if left.presence is not None:
                    model.AddImplication(arc, left.presence)
                if right.presence is not None:
                    model.AddImplication(arc, right.presence)
                previous_mold = molds.get(left.mold_id or "")
                current_mold = molds.get(right.mold_id or "")
                setup = (
                    transition_impact(previous_mold, current_mold, objective_config)
                    if current_mold is not None
                    else None
                )
                setup_minutes = setup.setup_minutes if setup is not None else 0
                model.Add(right.start >= left.end + setup_minutes).OnlyEnforceIf(arc)
                if setup_minutes and transition_weight:
                    objective_terms.append(setup_minutes * transition_weight * arc)
                arcs.append((left_index, right_index, arc))
        model.AddCircuit(arcs)

    loads: list[Any] = []
    for machine in machines:
        terms: list[Any] = []
        fixed_minutes = 0
        for node in machine_nodes[machine.id]:
            if node.presence is None:
                fixed_minutes += int(node.end) - int(node.start)
            else:
                terms.append(durations[node.order_id] * node.presence)
        load = model.NewIntVar(0, horizon_minutes * 2, f"load_{machine.id}")
        model.Add(load == fixed_minutes + sum(terms))
        loads.append(load)
    if loads:
        max_load = model.NewIntVar(0, horizon_minutes * 2, "max_load")
        min_load = model.NewIntVar(0, horizon_minutes * 2, "min_load")
        model.AddMaxEquality(max_load, loads)
        model.AddMinEquality(min_load, loads)
        load_weight = int(objective_config.get("load_balance_weight", 25))
        if load_weight:
            objective_terms.append(load_weight * (max_load - min_load))

    model.Minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.Solve(model)
    elapsed_ms = (monotonic() - started) * 1000
    if status == cp_model.INFEASIBLE:
        for order in candidate_orders:
            assignments.append(
                _unassigned(
                    order,
                    task_by_order.get(order.id),
                    mold_id=order.mold_id,
                    code="CP_SAT_INFEASIBLE",
                    detail="CP-SAT 在当前范围和锁定约束下没有可行解。",
                    production=durations[order.id],
                )
            )
        summary = _empty_summary(
            orders=orders,
            assignments=assignments,
            frozen_task_ids=frozen_task_ids,
            solver_status="INFEASIBLE",
            elapsed_ms=elapsed_ms,
        )
        return HeuristicResult(tuple(assignments), summary, frozen_task_ids)
    if status == cp_model.MODEL_INVALID:
        raise CpSatUnavailableError("CP-SAT 模型校验失败，已阻止使用该结果")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        summary = _empty_summary(
            orders=orders,
            assignments=assignments,
            frozen_task_ids=frozen_task_ids,
            solver_status="TIME_LIMIT",
            elapsed_ms=elapsed_ms,
        )
        return HeuristicResult(tuple(assignments), summary, frozen_task_ids)

    solver_status = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
    selected: dict[str, _Option] = {}
    for order in candidate_orders:
        selected[order.id] = next(
            item for item in options_by_order[order.id] if solver.Value(item.presence)
        )

    before_slots: dict[str, list[QueueSlot]] = {item.id: [] for item in machines}
    after_slots: dict[str, list[QueueSlot]] = {item.id: [] for item in machines}
    for task in plan_tasks:
        if (
            task.machine_id not in before_slots
            or not task.planned_start
            or not task.planned_finish
        ):
            continue
        slot = QueueSlot(
            task.machine_id,
            task.order_id,
            task_mold_key(task, order_by_id),
            task.mold_copy_no,
            task.sequence_no,
            as_business_datetime(task.planned_start),
            as_business_datetime(task.planned_finish),
        )
        before_slots[task.machine_id].append(slot)
        if task in fixed_tasks:
            after_slots[task.machine_id].append(slot)

    solved_by_machine: dict[str, list[tuple[InjectionSchedulingOrder, _Option]]] = {}
    for order in candidate_orders:
        option = selected[order.id]
        solved_by_machine.setdefault(option.machine_id, []).append((order, option))
    for items in solved_by_machine.values():
        items.sort(key=lambda item: (solver.Value(start_vars[item[0].id]), item[0].id))

    for machine in machines:
        existing_sequences = [item.sequence_no for item in after_slots[machine.id]]
        next_sequence = max(existing_sequences, default=-1) + 1
        scheduled_minutes = sum(
            max(0, int((item.finish - item.start).total_seconds() / 60))
            for item in after_slots[machine.id]
        )
        for order, option in solved_by_machine.get(machine.id, []):
            mold = molds[order_mold_key(order)]
            start = horizon_start + timedelta(
                minutes=solver.Value(start_vars[order.id])
            )
            finish = horizon_start + timedelta(minutes=solver.Value(end_vars[order.id]))
            previous_slot = max(
                (item for item in after_slots[machine.id] if item.finish <= start),
                key=lambda item: (item.finish, item.sequence_no),
                default=None,
            )
            previous_mold = (
                molds.get(previous_slot.mold_id or "") if previous_slot else None
            )
            transition = transition_impact(previous_mold, mold, objective_config)
            match = next(
                item
                for item in eligible_by_order[order.id]
                if item.machine_id == machine.id
            )
            score = placement_score(
                order=order,
                machine=machine,
                mold=mold,
                finish=finish,
                transition=transition,
                machine_load_minutes=scheduled_minutes,
                horizon_minutes=horizon_minutes,
                existing_task=task_by_order.get(order.id),
                planned_start=iso_seconds(start),
                config=objective_config,
            )
            explanation = assignment_explanation(
                match, score, transition, machine, mold
            )
            estimate = estimates_by_order[order.id]
            explanation["production"] = estimate.explanation()
            if estimate.split_required:
                explanation["summary"] = (
                    f"当前窗口安排 {float(estimate.planned_quantity):g}，"
                    f"剩余 {float(estimate.remaining_quantity):g} 继续留在待排订单。"
                )
            explanation["solver"] = {
                "type": "CP_SAT",
                "status": solver_status,
                "optional_interval": True,
                "machine_no_overlap": True,
                "mold_copy_no_overlap": True,
                "sequence_dependent_setup": True,
            }
            slot = QueueSlot(
                machine.id,
                order.id,
                mold.id,
                option.mold_copy_no,
                next_sequence,
                start,
                finish,
            )
            after_slots[machine.id].append(slot)
            scheduled_minutes += durations[order.id]
            assignments.append(
                {
                    "order_id": order.id,
                    "existing_task_id": task_by_order.get(order.id).id
                    if task_by_order.get(order.id)
                    else None,
                    "mold_id": order.mold_id,
                    "mold_copy_no": option.mold_copy_no,
                    "machine_id": machine.id,
                    "sequence_no": next_sequence,
                    "planned_start": iso_seconds(start),
                    "planned_finish": iso_seconds(finish),
                    "setup_minutes": transition.setup_minutes,
                    "production_minutes": durations[order.id],
                    "planned_downtime_minutes": 0,
                    "changeover_type": transition.changeover_type,
                    "decision": match.decision,
                    "score": score.total,
                    "explanation": explanation,
                    "unassigned_reason_code": "",
                }
            )
            next_sequence += 1

    before_metrics = _queue_metrics(before_slots, molds)
    after_metrics = _queue_metrics(after_slots, molds)

    def overdue_count(slots_by_machine: dict[str, list[QueueSlot]]) -> int:
        return sum(
            1
            for slots in slots_by_machine.values()
            for slot in slots
            if order_by_id.get(slot.order_id)
            and order_by_id[slot.order_id].delivery_due_date
            and slot.finish.date().isoformat()
            > order_by_id[slot.order_id].delivery_due_date
        )

    overdue_before = overdue_count(before_slots)
    overdue_after = overdue_count(after_slots)
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
    machine_loads = [
        {
            "machine_id": machine.id,
            "machine_code": machine.machine_code,
            "scheduled_minutes": sum(
                max(0, int((slot.finish - slot.start).total_seconds() / 60))
                for slot in after_slots[machine.id]
            ),
            "load_ratio": round(
                sum(
                    max(0, int((slot.finish - slot.start).total_seconds() / 60))
                    for slot in after_slots[machine.id]
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
        "local_improvement_move_count": 0,
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
        "solver_elapsed_ms": round(elapsed_ms, 2),
        "solver_status": solver_status,
        "objective_value": round(solver.ObjectiveValue(), 3),
        "best_objective_bound": round(solver.BestObjectiveBound(), 3),
    }
    return HeuristicResult(tuple(assignments), summary, frozen_task_ids)
