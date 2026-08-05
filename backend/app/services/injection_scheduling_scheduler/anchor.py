from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling_execution import (
    InjectionSchedulingPlan,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_scheduler import (
    InjectionSchedulingMachineCalendar,
)
from app.services.injection_scheduling_scheduler.normalization import (
    as_business_datetime,
    iso_seconds,
)


@dataclass(frozen=True, slots=True)
class MachineContinuationAnchor:
    machine_id: str
    starts_at: datetime
    sources: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "machine_id": self.machine_id,
            "starts_at": iso_seconds(self.starts_at),
            "sources": list(self.sources),
        }


def next_feasible_start(
    candidate: datetime,
    duration: timedelta,
    calendars: list[InjectionSchedulingMachineCalendar],
) -> datetime:
    """Advance through unavailable windows instead of using a blind max()."""
    current = candidate
    blocked = sorted(
        (item for item in calendars if not item.available),
        key=lambda item: (item.window_start, item.window_end, item.id),
    )
    while True:
        finish = current + duration
        conflict = next(
            (
                item
                for item in blocked
                if current < as_business_datetime(item.window_end)
                and finish > as_business_datetime(item.window_start)
            ),
            None,
        )
        if conflict is None:
            return current
        current = as_business_datetime(conflict.window_end)


def build_machine_continuation_anchors(
    db: Session,
    *,
    factory_id: str,
    target_plan: InjectionSchedulingPlan,
    target_tasks: list[InjectionSchedulingTask],
    calendars: list[InjectionSchedulingMachineCalendar],
    horizon_start: datetime,
) -> dict[str, MachineContinuationAnchor]:
    published = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
    )
    reference_tasks = (
        list(
            db.scalars(
                select(InjectionSchedulingTask).where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == published.id,
                    InjectionSchedulingTask.execution_status.notin_(
                        ("COMPLETED", "CANCELLED")
                    ),
                )
            ).all()
        )
        if published is not None and published.id != target_plan.id
        else []
    )
    cloned_source_ids = {
        item.source_task_id for item in target_tasks if item.source_task_id
    }
    candidates: dict[str, list[tuple[datetime, dict[str, str]]]] = {}

    def add(task: InjectionSchedulingTask, value: str, source_kind: str) -> None:
        if not value:
            return
        candidates.setdefault(task.machine_id, []).append(
            (
                as_business_datetime(value),
                {
                    "source_kind": source_kind,
                    "plan_id": task.plan_id,
                    "task_id": task.id,
                    "timestamp": value,
                },
            )
        )

    for task in target_tasks:
        if task.locked and task.execution_status not in {"COMPLETED", "CANCELLED"}:
            add(task, task.planned_finish, "TARGET_LOCKED_BASELINE")
    for task in reference_tasks:
        if task.id not in cloned_source_ids:
            add(
                task,
                task.estimated_finish or task.planned_finish,
                "REFERENCE_PUBLISHED_QUEUE",
            )
        if task.execution_status == "RUNNING":
            add(
                task,
                task.estimated_finish or task.planned_finish,
                "RUNNING_ESTIMATED_FINISH",
            )

    calendar_by_machine: dict[str, list[InjectionSchedulingMachineCalendar]] = {}
    for item in calendars:
        calendar_by_machine.setdefault(item.machine_id, []).append(item)
    machine_ids = {
        item.machine_id for item in target_tasks
    } | {item.machine_id for item in reference_tasks}
    anchors: dict[str, MachineContinuationAnchor] = {}
    for machine_id in sorted(machine_ids):
        items = candidates.get(machine_id, [])
        candidate = max(
            [horizon_start, *(value for value, _ in items)],
        )
        feasible = next_feasible_start(
            candidate,
            timedelta(microseconds=1),
            calendar_by_machine.get(machine_id, []),
        )
        sources = tuple(
            detail
            for _, detail in sorted(
                items,
                key=lambda item: (
                    item[0],
                    item[1]["source_kind"],
                    item[1]["task_id"],
                ),
            )
        )
        anchors[machine_id] = MachineContinuationAnchor(
            machine_id=machine_id,
            starts_at=feasible,
            sources=sources,
        )
    return anchors
