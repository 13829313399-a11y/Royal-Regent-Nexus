from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable


PROTECTED_EXECUTION_STATUSES = {"running", "completed", "cancelled"}
PRIORITY_CODES = ("P0", "P1", "P2", "P3")


def normalize_priority_code(value: Any) -> str:
    """Map legacy workbook flags into the formal P0-P3 execution priority.

    The original workbook mixes urgency markers with operational notes.  Keep
    that raw text on the order, but derive one deterministic code for the
    scheduler instead of silently sorting every unknown marker together.
    """

    text = str(value or "").strip()
    upper = text.upper()
    if upper in PRIORITY_CODES:
        return upper
    if any(marker in upper for marker in ("特急", "URGENT", "RUSH", "急单")):
        return "P0"
    if "▲" in text or text == "急":
        return "P1"
    return "P3"


def prioritize_auto_orders(
    orders: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a deterministic urgent/due-date priority order.

    This helper intentionally has no database or clock dependency so the same
    source snapshot always produces the same auto-draft input order.
    """

    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        priority = normalize_priority_code(
            item.get("priority_code") or item.get("priority_flag")
        )
        priority_rank = PRIORITY_CODES.index(priority)
        due = str(item.get("delivery_due_date") or "9999-12-31")
        downstream = float(item.get("downstream_urgency") or 0)
        outstanding = float(item.get("outstanding_qty") or 0)
        return (
            priority_rank,
            due,
            -downstream,
            -outstanding,
            str(item.get("id") or ""),
        )

    return sorted((dict(item) for item in orders), key=key)


def choose_earliest_eligible_machine(
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Choose only a PASS/eligible candidate with deterministic tie-breaking."""

    eligible = [
        dict(item)
        for item in candidates
        if item.get("status") == "eligible"
        and item.get("eligible") is True
        and all(
            check.get("status") == "pass"
            for check in item.get("hard_constraints", [])
        )
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda item: (
            int(item.get("rank") or 1_000_000),
            _estimated_start(item),
            str(item.get("machine_id") or ""),
            int(item.get("target_index") or 0),
        ),
    )


def plan_lane_locally(
    tasks: Iterable[dict[str, Any]],
    *,
    plan_base_at: datetime,
    unavailable_windows: Iterable[dict[str, Any]] = (),
    freeze_before_at: datetime | None = None,
    planning_horizon_end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Reflow one lane while preserving every locked/execution barrier.

    `planned_start_at` is the production start (setup has already completed).
    Setup and production are treated as one occupied block for downtime checks.
    """

    plan_base_at = _as_datetime(plan_base_at)
    freeze_before_at = (
        _as_datetime(freeze_before_at)
        if freeze_before_at is not None
        else None
    )
    planning_horizon_end_at = (
        _as_datetime(planning_horizon_end_at)
        if planning_horizon_end_at is not None
        else None
    )
    windows = sorted(
        (
            (_as_datetime(item["start_at"]), _as_datetime(item["end_at"]))
            for item in unavailable_windows
        ),
        key=lambda item: item[0],
    )
    cursor = plan_base_at
    result: list[dict[str, Any]] = []
    for source in tasks:
        item = dict(source)
        existing_start = _optional_datetime(item.get("planned_start_at"))
        existing_finish = _optional_datetime(item.get("planned_finish_at"))
        execution_status = str(item.get("execution_status") or "planned")
        frozen_by_time = (
            freeze_before_at is not None
            and existing_start is not None
            and existing_start < freeze_before_at
        )
        barrier = bool(item.get("locked") or item.get("protected"))
        barrier = barrier or execution_status in PROTECTED_EXECUTION_STATUSES
        barrier = barrier or frozen_by_time

        if barrier:
            item["barrier"] = True
            item["barrier_reason"] = (
                "execution_status"
                if execution_status in PROTECTED_EXECUTION_STATUSES
                else "protected"
                if item.get("protected")
                else "locked"
                if item.get("locked")
                else "freeze_before"
            )
            if existing_start is None or existing_finish is None:
                raise ValueError(
                    f"barrier task {item.get('id', '')} has no valid time window"
                )
            if execution_status not in {"completed", "cancelled"} and cursor > existing_start:
                raise ValueError(
                    f"barrier task {item.get('id', '')} overlaps its fixed predecessor"
                )
            cursor = max(cursor, existing_finish)
            result.append(item)
            continue

        setup_hours = max(float(item.get("setup_hours") or 0), 0)
        duration_hours = max(float(item.get("duration_hours") or 0), 0)
        occupied = timedelta(hours=setup_hours + duration_hours)
        occupied_start = _first_available_start(cursor, occupied, windows)
        production_start = occupied_start + timedelta(hours=setup_hours)
        finish = occupied_start + occupied
        if planning_horizon_end_at is not None and finish > planning_horizon_end_at:
            raise ValueError(
                f"task {item.get('id', '')} exceeds planning horizon"
            )
        item["planned_start_at"] = _format(production_start)
        item["planned_finish_at"] = _format(finish)
        item["barrier"] = False
        item["barrier_reason"] = ""
        cursor = finish
        result.append(item)
    return result


def build_projection_rows(
    before: Iterable[dict[str, Any]],
    after: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_by_id = {str(item["id"]): dict(item) for item in before}
    rows: list[dict[str, Any]] = []
    for current in after:
        previous = before_by_id.get(str(current["id"]))
        if previous is None:
            continue
        before_finish = str(previous.get("planned_finish_at") or "")
        after_finish = str(current.get("planned_finish_at") or "")
        before_qty = float(previous.get("planned_qty") or 0)
        after_qty = float(current.get("planned_qty") or 0)
        if before_finish == after_finish and abs(before_qty - after_qty) < 1e-9:
            continue
        rows.append(
            {
                "task_id": str(current["id"]),
                "order_id": str(current.get("order_id") or ""),
                "machine_id": str(current.get("machine_id") or ""),
                "machine_code": str(current.get("machine_code") or ""),
                "planned_qty_before": before_qty,
                "planned_qty_after": after_qty,
                "planned_finish_at_before": before_finish,
                "planned_finish_at_after": after_finish,
                "eta_shift_minutes": _minutes_between(before_finish, after_finish),
                "shortage_qty": max(after_qty, 0),
            }
        )
    return rows


def _estimated_start(item: dict[str, Any]) -> str:
    score = item.get("score") or {}
    estimated = score.get("estimated") or {}
    return str(estimated.get("slot_start_at") or "9999-12-31 23:59:59")


def _first_available_start(
    start: datetime,
    duration: timedelta,
    windows: list[tuple[datetime, datetime]],
) -> datetime:
    candidate = start
    while True:
        conflict = next(
            (
                (window_start, window_end)
                for window_start, window_end in windows
                if candidate < window_end
                and candidate + duration > window_start
            ),
            None,
        )
        if conflict is None:
            return candidate
        candidate = conflict[1]


def _minutes_between(before: str, after: str) -> float:
    left = _optional_datetime(before)
    right = _optional_datetime(after)
    if left is None or right is None:
        return 0
    return round((right - left).total_seconds() / 60, 3)


def _as_datetime(value: Any) -> datetime:
    parsed = _optional_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid datetime: {value!r}")
    return parsed


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except ValueError:
        return None


def _format(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
