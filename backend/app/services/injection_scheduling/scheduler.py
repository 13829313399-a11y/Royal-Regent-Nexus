"""Deterministic, deadline-first insertion into machine and physical-mold calendars."""

import json
from copy import deepcopy
from decimal import Decimal as D

from .calculations import decimal, delivery, remaining_for_group, timestamp
from .changeover import transition
from .resource_calendar import calendar_blocks, consume, overlaps

ACTIVE = {"PLANNED", "RUNNING", "PAUSED"}


def planned_run_id(demand_id, snapshot):
    active = next(
        (
            run["id"]
            for run in snapshot["runs"]
            if run["demand_ids"]
            and demand_id == run["demand_ids"][0]
            and run.get("status") == "PLANNED"
        ),
        None,
    )
    if active:
        return active
    base = f"run-{demand_id}"
    reserved = set(snapshot.get("reserved_run_ids", []))
    result, number = base, 1
    while result in reserved:
        number += 1
        result = f"{base}-{number}"
    return result


REASONS = {
    "MISSING_REQUIRED_A": "缺少模具机安",
    "MISSING_RATE": "缺少有效日目标或速度",
    "MACHINE_TOO_SMALL": "机器机安小于模具要求",
    "MACHINE_DOWN": "机台停机且未设置恢复时间",
    "MOLD_NOT_AVAILABLE": "本厂没有可用实物模具",
    "UNSUPPORTED_MACHINE_FAMILY": "机型不匹配",
    "ON_HOLD": "需求暂停、待通知或待料",
    "NO_ALLOWED_MACHINE": "没有符合允许上放及工艺要求的机台",
    "MISSING_QUANTITY": "缺少计划数量",
    "UNRESOLVED_OUTPUT": "同啤/双色出件配置尚未明确",
    "RESOURCE_CONFLICT": "固定占用或资源日历冲突",
}
REASONS.update(
    {
        "FORBIDDEN_MACHINE": "该模具明确禁止使用此机号",
        "HIGH_SPEED_REQUIRED": "需求要求高速机",
        "CAPABILITY_REQUIRED": "机器缺少需求要求的能力",
        "MATERIAL_FORBIDDEN": "该机台不允许此树脂",
        "GRADE_FORBIDDEN": "该机台不允许此材料牌号",
        "TRANSPARENT_REQUIRED": "该机台只允许透明产品",
        "MANIPULATOR_REQUIRED": "机械手能力不匹配",
        "FIXTURE_REQUIRED": "缺少所需工装",
        "AUTOMATION_REQUIRED": "该机台不支持所需全自动生产",
        "CALENDAR_UNAVAILABLE": "资源日历在两年内没有可用生产时间",
        "UNKNOWN_RESOURCE_RECOVERY": "机台或实物模具被等待恢复的实际批次占用",
    }
)


class ScheduleConflict(ValueError):
    def __init__(self, reason, run_id):
        super().__init__(reason)
        self.run_id = run_id


def compatible_process(first, second):
    keys = (
        "mold_master_id",
        "material_raw",
        "resin",
        "material_grade",
        "color_name",
        "colorant_code",
        "target_shots_per_day",
        "target_basis_hours",
        "required_machine_a",
        "requirements_snapshot",
        "output_configuration",
        "effective_outputs_per_shot",
        "automation_requirement",
        "manipulator_requirement",
        "fixture_requirement",
    )
    return all(first.get(key) == second.get(key) for key in keys)


def priority(job):
    due = timestamp(job.get("delivery_due_at"))
    return (
        -int(job.get("priority_level") or 0),
        due is None,
        due.timestamp() if due else float("inf"),
        int(job.get("color_depth_rank"))
        if job.get("color_depth_rank") is not None
        else 3,
        int(job.get("stable_sequence") or 0),
        job["id"],
    )


def fit(job, machine, settings, *, manual_oversize=False):
    req = job.get("requirements_snapshot") or {}
    if machine["factory_id"] != job["factory_id"]:
        return "FACTORY_MISMATCH"
    if machine.get("operating_status") in {
        "MAINTENANCE",
        "FAULT",
        "DISABLED",
        "PAUSED",
    } and not machine.get("recovery_at"):
        return "MACHINE_DOWN"
    family = req.get("machine_family", "HORIZONTAL")
    if family != machine.get("machine_family", "HORIZONTAL"):
        return "UNSUPPORTED_MACHINE_FAMILY"
    a, actual = (
        decimal(job.get("required_machine_a")),
        decimal(machine.get("machine_a")),
    )
    if family != "TWO_COLOR":
        if a is None:
            return "MISSING_REQUIRED_A"
        if actual is None or actual < a:
            return "MACHINE_TOO_SMALL"
        allowed = settings.get("allowed_upsize", {}).get(
            format(a.normalize(), "f"), [float(a)]
        )
        if actual != a and float(actual) not in allowed and not manual_oversize:
            return "NO_ALLOWED_MACHINE"
    elif not job.get("output_configuration"):
        return "UNRESOLVED_OUTPUT"
    if machine["code"] in req.get("forbidden_machine_codes", []):
        return "FORBIDDEN_MACHINE"
    if req.get("speed_class") and req["speed_class"] != machine.get("speed_class"):
        return "HIGH_SPEED_REQUIRED"
    capabilities = machine.get("capabilities") or {}
    if any(not capabilities.get(c) for c in req.get("required_capabilities", [])):
        return "CAPABILITY_REQUIRED"
    manipulator = job.get("manipulator_requirement") or req.get(
        "manipulator_requirement"
    )
    if manipulator and manipulator not in (machine.get("manipulator") or ""):
        return "MANIPULATOR_REQUIRED"
    fixture = job.get("fixture_requirement") or req.get("fixture_requirement")
    if fixture and fixture not in capabilities.get("fixtures", []):
        return "FIXTURE_REQUIRED"
    restrictions = machine.get("restrictions") or {}
    resin = str(job.get("resin") or "").upper()
    if resin in restrictions.get("forbidden_resins", []):
        return "MATERIAL_FORBIDDEN"
    if restrictions.get("only_resin") and resin != restrictions["only_resin"]:
        return "MATERIAL_FORBIDDEN"
    if (
        restrictions.get("only_grade")
        and job.get("material_grade") != restrictions["only_grade"]
    ):
        return "GRADE_FORBIDDEN"
    if restrictions.get("transparent_only") and "透明" not in str(
        job.get("color_name") or ""
    ):
        return "TRANSPARENT_REQUIRED"
    if job.get("automation_requirement") in {"全自动", "是"} and not capabilities.get(
        "AUTOMATIC"
    ):
        return "AUTOMATION_REQUIRED"
    return None


def ready_reason(job):
    if job.get("dispatch_state") != "READY":
        return "ON_HOLD"
    if job.get("remaining_shots") is None:
        return "MISSING_QUANTITY"
    if job.get("allocation_mode") == "LEGACY_UNRESOLVED":
        return "UNRESOLVED_OUTPUT"
    if job.get("allocation_mode") == "CO_OUTPUT_UNITS" and (
        job.get("required_units") is None or not job.get("output_configuration")
    ):
        return "UNRESOLVED_OUTPUT"
    if decimal(job.get("target_shots_per_day"), D(0)) <= 0:
        return "MISSING_RATE"
    if (
        job.get("required_machine_a") is None
        and (job.get("requirements_snapshot") or {}).get("machine_family")
        != "TWO_COLOR"
    ):
        return "MISSING_REQUIRED_A"
    return None


def simulate(
    queues, machines, assets, settings, events, as_of, *, external=(), cache=None
):
    """Recalculate all successor conversions once; fixed/running resources stay fixed.

    Ready queue heads are chosen deterministically. Reservations include setup and
    production through end, conservatively retaining molds across calendar gaps.
    """
    as_of = timestamp(as_of)
    # Cache only inside one immutable planning snapshot, never across writes/factories.
    cache = cache if cache is not None else {}
    priorities = cache.setdefault("priorities", {})
    calendars = cache.setdefault("calendars", {})
    conversions = cache.setdefault("conversions", {})

    def order(job):
        identity = job["id"]
        if identity not in priorities:
            priorities[identity] = priority(job)
        return priorities[identity]

    states = {
        m: {
            "cursor": as_of,
            "previous": machines[m].get("current_setup") or None,
            "index": 0,
        }
        for m in queues
    }
    occupied = {a: [] for a in assets}
    fixed_machine = {m: [] for m in machines}
    unknown_assets, unknown_machines = set(), set()
    for run in [
        *external,
        *(
            r
            for q in queues.values()
            for r in q
            if r.get("status") in {"RUNNING", "PAUSED"}
        ),
    ]:
        interval = (timestamp(run["setup_start_at"]), timestamp(run["planned_end_at"]))
        occupied.setdefault(run["mold_asset_id"], []).append((interval, run["id"]))
        fixed_machine.setdefault(run["machine_id"], []).append((interval, run["id"]))
        if run.get(
            "forecast_unknown", (run.get("explanation") or {}).get("forecast_unknown")
        ):
            unknown_assets.add(run["mold_asset_id"])
            unknown_machines.add(run["machine_id"])
    results = []
    while True:
        heads = [
            (q[s["index"]], m)
            for m, s in states.items()
            if s["index"] < len(q := queues[m])
        ]
        if not heads:
            break
        job, mid = min(heads, key=lambda pair: (order(pair[0]), pair[1]))
        state, machine = states[mid], machines[mid]
        asset = assets[job["mold_asset_id"]]
        if job.get("status") == "PLANNED" and (
            asset["id"] in unknown_assets or mid in unknown_machines
        ):
            raise ScheduleConflict("UNKNOWN_RESOURCE_RECOVERY", job["id"])
        if job.get("status") == "PLANNED" and (
            asset.get("status") != "AVAILABLE"
            or asset.get("current_factory_id") != job["factory_id"]
            or asset.get("master_id") != job.get("mold_master_id")
        ):
            raise ScheduleConflict("MOLD_NOT_AVAILABLE", job["id"])
        previous = state["previous"]
        rate = decimal(job.get("target_shots_per_day"), D(0)) / decimal(
            job.get("target_basis_hours"), D(24)
        )
        if rate <= 0:
            raise ValueError("MISSING_RATE")
        conversion_key = (
            mid,
            (previous or {}).get("id"),
            (previous or {}).get("mold_asset_id"),
            job["id"],
            asset["id"],
        )
        if conversion_key not in conversions:
            conversions[conversion_key] = transition(previous, job, settings)
        change = conversions[conversion_key]
        candidate = max(
            state["cursor"],
            timestamp(job.get("earliest_available_at")) or as_of,
            timestamp(asset.get("available_at")) or as_of,
            timestamp(machine.get("recovery_at")) or as_of,
        )
        calendar_key = (mid, asset["id"])
        if calendar_key not in calendars:
            calendars[calendar_key] = calendar_blocks(
                as_of, settings, events, mid, asset["id"]
            )
        blocks = calendars[calendar_key]
        reservations = [
            (a, b)
            for (a, b), identity in [
                *occupied.get(asset["id"], []),
                *fixed_machine.get(mid, []),
            ]
            if identity != job["id"]
        ]
        # A user pin preserves machine/queue position, not an obsolete clock time.
        # Actual execution alone has an immutable physical start.
        pinned = job.get("status") in {"RUNNING", "PAUSED"}
        if pinned:
            start, prod, end = map(
                timestamp,
                (job["setup_start_at"], job["planned_start_at"], job["planned_end_at"]),
            )
            if state["cursor"] > start and job.get("status") not in {
                "RUNNING",
                "PAUSED",
            }:
                raise ValueError("RESOURCE_CONFLICT")
            segments = job.get("segments", [])
            if any(overlaps((start, end), r) for r in reservations):
                raise ValueError("RESOURCE_CONFLICT")
            result = dict(job)
        else:
            # Advance until the entire resource occupancy avoids all fixed/asset runs.
            for _ in range(len(reservations) + 2):
                try:
                    prod, setup_segments = consume(
                        candidate,
                        change["changeover_minutes"],
                        blocks,
                        continuous=not settings.get("setup_interruptible", False),
                    )
                    start = setup_segments[0][0] if setup_segments else prod
                    end, production_segments = consume(
                        prod, decimal(job["remaining_shots"]) / rate * 60, blocks
                    )
                except ValueError:
                    raise ScheduleConflict("CALENDAR_UNAVAILABLE", job["id"]) from None
                conflict = next(
                    (r for r in sorted(reservations) if overlaps((start, end), r)), None
                )
                if conflict:
                    candidate = conflict[1]
                    continue
                break
            else:
                raise ValueError("RESOURCE_CONFLICT")
            segments = [
                {"kind": "SETUP", "start": a.isoformat(), "end": b.isoformat()}
                for a, b in setup_segments
            ] + [
                {"kind": "PRODUCTION", "start": a.isoformat(), "end": b.isoformat()}
                for a, b in production_segments
            ]
            actual = decimal(machine.get("machine_a"), D(0))
            required = decimal(job.get("required_machine_a"), D(0))
            fit_class = "EXACT" if actual == required else "ALLOWED_UPSIZE"
            result = {
                **job,
                "setup_start_at": start.isoformat(),
                "planned_start_at": prod.isoformat(),
                "planned_end_at": end.isoformat(),
                "segments": segments,
                "explanation": {
                    **change,
                    "fit_class": fit_class,
                    "required_a": required,
                    "actual_a": actual,
                    "reason_codes": ["DUE_DATE_PRIORITY", fit_class]
                    + (
                        ["SAME_MOLD_NEXT"]
                        if previous and previous.get("mold_asset_id") == asset["id"]
                        else []
                    ),
                    "reason_text": f"交期优先；{required}A 模具安排至 {machine['code']}（{actual}A），转换 {change['changeover_minutes']} 分钟。",
                },
            }
        ready, slack = delivery(
            end, job.get("delivery_due_at"), job.get("downstream_lead_days", 3)
        )
        result.update(
            machine_id=mid,
            machine_code=machine["code"],
            sequence=state["index"],
            expected_stock_ready_at=None
            if job.get("forecast_unknown")
            else ready.isoformat(),
            delivery_slack_hours=None if job.get("forecast_unknown") else slack,
        )
        results.append(result)
        occupied.setdefault(asset["id"], []).append(((start, end), job["id"]))
        state.update(
            cursor=max(state["cursor"], end), previous=job, index=state["index"] + 1
        )
    return results


def affected_machines(queues, changed_machine):
    """Return the transitive queue component linked by shared physical molds."""
    asset_machines = {}
    for mid, queue in queues.items():
        for row in queue:
            asset_machines.setdefault(row["mold_asset_id"], set()).add(mid)
    affected = {changed_machine}
    pending = [changed_machine]
    while pending:
        mid = pending.pop()
        for row in queues[mid]:
            for linked in asset_machines[row["mold_asset_id"]] - affected:
                affected.add(linked)
                pending.append(linked)
    return affected


def schedule_factory(snapshot, scope, as_of):
    machines = {m["id"]: m for m in snapshot["machines"]}
    assets = {a["id"]: a for a in snapshot["assets"]}
    settings, events = snapshot["settings"], snapshot["events"]
    mode = scope.get("mode", "UNSCHEDULED")
    selected_demands, selected_machines = (
        set(scope.get("demand_ids", [])),
        set(scope.get("machine_ids", [])),
    )
    selected_demands.update(
        d
        for r in snapshot["runs"]
        if r["machine_id"] in selected_machines
        for d in r["demand_ids"]
    )
    # A selected child represents its whole unstarted physical batch.
    for run in snapshot["runs"]:
        if selected_demands.intersection(run["demand_ids"]):
            selected_demands.update(run["demand_ids"])
    if mode not in {"UNSCHEDULED", "SELECTED", "ALL_UNSTARTED"}:
        raise ValueError("排程范围不正确")
    queues = {m: [] for m in machines}
    retained_ids = set()
    for run in sorted(snapshot["runs"], key=lambda r: (r["sequence"], r["id"])):
        fixed = run.get("pinned") or run.get("status") in {"RUNNING", "PAUSED"}
        keep = (
            mode == "UNSCHEDULED"
            or fixed
            or mode == "SELECTED"
            and not (
                set(run["demand_ids"]) & selected_demands
                or run["machine_id"] in selected_machines
            )
        )
        if keep:
            queues[run["machine_id"]].append(deepcopy(run))
            retained_ids.update(run["demand_ids"])
    demands = [
        d
        for d in snapshot["demands"]
        if d["id"] not in retained_ids
        and (mode != "SELECTED" or d["id"] in selected_demands)
    ]
    demands = form_jobs(demands)
    unplaced = []

    cache = {}
    priorities = cache.setdefault("priorities", {})

    def order(job):
        if job["id"] not in priorities:
            priorities[job["id"]] = priority(job)
        return priorities[job["id"]]

    def simulate_current(q, changed_machine=None):
        affected = set(q)
        if changed_machine is not None:
            # Only queues sharing a physical mold can propagate a changed end time.
            # Include the transitive component so moved molds still constrain successors.
            affected = affected_machines(q, changed_machine)
        result = simulate(
            {mid: queue for mid, queue in q.items() if mid in affected},
            machines,
            assets,
            settings,
            events,
            as_of,
            external=snapshot.get("external_runs", []),
            cache=cache,
        )
        return (
            result
            if changed_machine is None
            else [r for r in current if r["machine_id"] not in affected] + result
        )

    current = simulate_current(queues)
    for demand in sorted(demands, key=priority):
        if demand.get("remaining_shots") == 0:
            continue
        reason = ready_reason(demand)
        available_assets = [
            a
            for a in assets.values()
            if a["master_id"] == demand.get("mold_master_id")
            and a["current_factory_id"] == demand["factory_id"]
            and a["status"] == "AVAILABLE"
        ]
        if not reason and not available_assets:
            reason = "MOLD_NOT_AVAILABLE"
        if reason:
            unplaced.append(
                {
                    "demand_id": demand["id"],
                    "reason_code": reason,
                    "reason_text": REASONS.get(reason, reason),
                }
            )
            continue
        best, best_queues, best_result = None, None, None
        failures = []
        prior_late = {
            r["id"]: max(0, -(r.get("delivery_slack_hours") or 0)) for r in current
        }
        for mid, machine in sorted(machines.items(), key=lambda x: x[1]["code"]):
            failed = fit(demand, machine, settings)
            if failed:
                failures.append(failed)
                continue
            for asset in available_assets:
                job = {
                    **demand,
                    "id": planned_run_id(demand["id"], snapshot),
                    "demand_ids": demand.get("demand_ids", [demand["id"]]),
                    "mold_asset_id": asset["id"],
                    "machine_id": mid,
                    "status": "PLANNED",
                    "pinned": False,
                }
                # Bounded candidates: tail, front, and each same-mold/gap boundary.
                positions = {len(queues[mid]), 0}
                for i, r in enumerate(queues[mid]):
                    if (
                        r["mold_asset_id"] == asset["id"]
                        or i == 0
                        or timestamp(r["setup_start_at"])
                        > timestamp(queues[mid][i - 1]["planned_end_at"])
                    ):
                        positions.update([i, i + 1])
                for pos in sorted(positions):
                    candidate = {m: list(q) for m, q in queues.items()}
                    candidate[mid].insert(pos, job)
                    try:
                        result = simulate_current(candidate, mid)
                    except ValueError:
                        continue
                    new = next(r for r in result if r["id"] == job["id"])
                    if any(
                        max(0, -(r.get("delivery_slack_hours") or 0))
                        > prior_late.get(r["id"], float("inf")) + 1e-8
                        for r in result
                        if r["id"] != job["id"] and order(r) < order(job)
                    ):
                        continue
                    late = max(0, -(new.get("delivery_slack_hours") or 0))
                    waste = float(
                        decimal(machine.get("machine_a"), D(0))
                        - decimal(demand.get("required_machine_a"), D(0))
                    )
                    priority_inversions = sum(
                        order(earlier) > order(later)
                        for q in candidate.values()
                        for index, earlier in enumerate(q)
                        for later in q[index + 1 :]
                    )
                    score = (
                        late,
                        waste,
                        sum(
                            float(r.get("explanation", {}).get("changeover_minutes", 0))
                            for r in result
                        ),
                        priority_inversions,
                        timestamp(new["planned_end_at"]),
                        machine["code"],
                        pos,
                        asset["id"],
                    )
                    if best is None or score < best:
                        best, best_queues, best_result = score, candidate, result
        if best_result is None:
            reason = (
                failures[0]
                if failures and len(set(failures)) == 1
                else "NO_ALLOWED_MACHINE"
            )
            unplaced.append(
                {
                    "demand_id": demand["id"],
                    "reason_code": reason,
                    "reason_text": REASONS.get(reason, reason),
                }
            )
        else:
            current = best_result
            by_id = {r["id"]: r for r in current}
            queues = {m: [by_id[r["id"]] for r in q] for m, q in best_queues.items()}
    expanded = []
    grouped = {d["id"]: d.get("demand_ids", [d["id"]]) for d in demands}
    for item in unplaced:
        expanded.extend(
            {**item, "demand_id": identity}
            for identity in grouped.get(item["demand_id"], [item["demand_id"]])
        )
    current = merge_adjacent_runs(current)
    return {
        "as_of": timestamp(as_of).isoformat(),
        "changed_runs": current,
        "unplaced": expanded,
        "scheduled_count": sum(len(r["demand_ids"]) for r in current),
        "impact": {
            "late_orders_before": sum(
                (r.get("delivery_slack_hours") or 0) < 0 for r in snapshot["runs"]
            ),
            "late_orders_after": sum(
                (r.get("delivery_slack_hours") or 0) < 0 for r in current
            ),
            "changeover_minutes_after": sum(
                float(r.get("explanation", {}).get("changeover_minutes", 0))
                for r in current
            ),
        },
    }


def form_jobs(demands):
    groups = {}
    members = {}
    result = []
    for demand in sorted(demands, key=priority):
        group = demand.get("co_output_group")
        if (
            demand.get("allocation_mode") != "CO_OUTPUT_UNITS"
            or not group
            or not demand.get("output_configuration")
            or ready_reason(demand)
        ):
            result.append(demand)
            continue
        key = (
            group,
            demand.get("mold_master_id"),
            demand.get("material_raw"),
            demand.get("resin"),
            demand.get("material_grade"),
            demand.get("color_name"),
            demand.get("colorant_code"),
            json.dumps(demand["output_configuration"], sort_keys=True),
            demand.get("target_shots_per_day"),
            demand.get("target_basis_hours"),
            json.dumps(demand.get("requirements_snapshot") or {}, sort_keys=True),
            demand.get("required_machine_a"),
        )
        if key not in groups:
            job = deepcopy(demand)
            job["demand_ids"] = [demand["id"]]
            groups[key] = job
            members[key] = [demand]
            result.append(job)
        else:
            job = groups[key]
            members[key].append(demand)
            job["demand_ids"].append(demand["id"])
            job["remaining_shots"] = remaining_for_group(members[key])
            job["earliest_available_at"] = max(
                (
                    x
                    for x in [
                        job.get("earliest_available_at"),
                        demand.get("earliest_available_at"),
                    ]
                    if x
                ),
                default=None,
            )
    return result


def merge_adjacent_runs(rows):
    """Combine only already-adjacent compatible plans without moving any other job."""
    result = []
    for row in sorted(rows, key=lambda r: (r["machine_id"], r["sequence"], r["id"])):
        prior = result[-1] if result else None
        available = timestamp(row.get("earliest_available_at"))
        if (
            prior
            and prior["machine_id"] == row["machine_id"]
            and prior.get("status") == row.get("status") == "PLANNED"
            and not prior.get("pinned")
            and not row.get("pinned")
            and prior.get("allocation_mode")
            == row.get("allocation_mode")
            == "SEQUENTIAL_SHOTS"
            and prior["mold_asset_id"] == row["mold_asset_id"]
            and compatible_process(prior, row)
            and (not available or available <= timestamp(prior["planned_start_at"]))
            and float(row.get("explanation", {}).get("changeover_minutes", 0)) == 0
        ):
            prior["demand_ids"] = [*prior["demand_ids"], *row["demand_ids"]]
            prior["remaining_shots"] = decimal(prior["remaining_shots"]) + decimal(
                row["remaining_shots"]
            )
            prior["planned_end_at"] = row["planned_end_at"]
            prior["segments"] = [*prior.get("segments", []), *row.get("segments", [])]
            prior["explanation"] = {
                **prior.get("explanation", {}),
                "continuous_group": True,
                "reason_text": prior.get("explanation", {}).get("reason_text", "")
                + " 同模同配方连续订单合并报工，分别保留数量及交期。",
            }
        else:
            result.append(deepcopy(row))
    return result
