from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D

from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    Machine,
    MoldAsset,
    Run,
    RunDemand,
)

from .calculations import decimal, delivery, now, remaining_for_group, timestamp
from .common import jsonable, record, touch
from .resource_calendar import calendar_blocks, consume
from .scheduler import (
    ACTIVE,
    REASONS,
    ScheduleConflict,
    compatible_process,
    fit,
    planned_run_id,
    priority,
    ready_reason,
    schedule_factory,
    simulate,
)


def snapshot(db, factory, as_of=None):
    as_of = as_of or now()
    demands = [
        record(d)
        for d in db.scalars(select(Demand).where(Demand.factory_id == factory))
    ]
    by_demand = {d["id"]: d for d in demands}
    machines = [
        record(m)
        for m in db.scalars(select(Machine).where(Machine.factory_id == factory))
    ]
    by_machine = {m["id"]: m for m in machines}
    assets = [record(a) for a in db.scalars(select(MoldAsset))]
    events = [
        record(e)
        for e in db.scalars(
            select(CalendarEvent).where(CalendarEvent.factory_id == factory)
        )
    ]
    settings = db.get(FactorySettings, factory).parameters
    all_links = list(
        db.scalars(select(RunDemand).where(RunDemand.factory_id == factory))
    )
    reserved_run_ids = list(db.scalars(select(Run.id).where(Run.factory_id == factory)))
    links = {}
    for link in all_links:
        links.setdefault(link.run_id, []).append(link)
    runs = []
    for obj in db.scalars(
        select(Run).where(Run.factory_id == factory, Run.status.in_(ACTIVE))
    ):
        run_links = sorted(links.get(obj.id, []), key=lambda r: (r.sequence, r.id))
        if not run_links:
            continue
        first = by_demand[run_links[0].demand_id]

        def comparable(demand, first=first):
            return (
                {
                    **demand,
                    "effective_outputs_per_shot": first.get(
                        "effective_outputs_per_shot"
                    ),
                }
                if first.get("allocation_mode") == "CO_OUTPUT_UNITS"
                else demand
            )

        if (
            obj.status == "PLANNED"
            and len(run_links) > 1
            and any(
                by_demand[link.demand_id]["allocation_mode"] != first["allocation_mode"]
                or not compatible_process(first, comparable(by_demand[link.demand_id]))
                for link in run_links[1:]
            )
        ):
            # A changed child process cannot silently inherit the first child's old recipe.
            # Split only unstarted groups; preserved demand IDs keep edits/report lineage precise.
            for index, link in enumerate(run_links):
                child = by_demand[link.demand_id]
                asset = next(
                    (
                        a
                        for a in assets
                        if a["master_id"] == child["mold_master_id"]
                        and a["current_factory_id"] == factory
                        and a["status"] == "AVAILABLE"
                    ),
                    None,
                )
                identity = (
                    obj.id
                    if index == 0
                    else planned_run_id(
                        child["id"], {"runs": [], "reserved_run_ids": reserved_run_ids}
                    )
                )
                reserved_run_ids.append(identity)
                runs.append(
                    {
                        **child,
                        **record(obj),
                        "id": identity,
                        "demand_ids": [child["id"]],
                        "sequence": obj.sequence + index / 1000,
                        "remaining_shots": child["remaining_shots"],
                        "mold_asset_id": asset["id"] if asset else obj.mold_asset_id,
                        "explanation": {
                            "reason_text": "本单工艺参数已改变，原未开工订单组拆为独立批次。"
                        },
                    }
                )
            continue
        data = {
            **first,
            **(obj.snapshot if obj.status in {"RUNNING", "PAUSED"} else {}),
            **record(obj),
        }
        # record(run) contains physical identity, but rate/process fields live in its snapshot.
        data["demand_ids"] = [r.demand_id for r in run_links]
        data["remaining_shots"] = remaining_for_group(
            [by_demand[r.demand_id] for r in run_links]
        )
        data["delivery_due_at"] = min(
            (
                by_demand[r.demand_id]["delivery_due_at"]
                for r in run_links
                if by_demand[r.demand_id].get("delivery_due_at")
            ),
            default=None,
        )
        data["output_configuration"] = first.get("output_configuration")
        # The process identity stays fixed after opening; explicit rate edits remain live.
        data["target_shots_per_day"] = first.get("target_shots_per_day")
        data["target_basis_hours"] = first.get("target_basis_hours")
        data["requirements_snapshot"] = (
            obj.snapshot.get("requirements_snapshot")
            if obj.status in {"RUNNING", "PAUSED"}
            else first.get("requirements_snapshot")
        ) or {}
        if obj.status in {"RUNNING", "PAUSED"}:
            data["forecast_unknown"] = False
            rate = decimal(data.get("target_shots_per_day"), D(0)) / decimal(
                data.get("target_basis_hours"), D(24)
            )
            cursor = max(
                timestamp(as_of), timestamp(obj.actual_start_at) or timestamp(as_of)
            )
            machine = by_machine[obj.machine_id]
            if machine.get("recovery_at"):
                cursor = max(cursor, timestamp(machine["recovery_at"]))
            if obj.status == "PAUSED" and not machine.get("recovery_at"):
                # Unknown pause duration blocks future capacity without claiming a forecast.
                end = timestamp(as_of) + timedelta(days=730)
                data["forecast_unknown"] = True
                segments = []
                machine["operating_status"] = "PAUSED"
            elif rate > 0:
                try:
                    end, parts = consume(
                        cursor,
                        data["remaining_shots"] / rate * 60,
                        calendar_blocks(
                            as_of, settings, events, obj.machine_id, obj.mold_asset_id
                        ),
                    )
                except ValueError:
                    # An indefinite future stop cannot manufacture a recovery date.
                    end, parts = timestamp(as_of) + timedelta(days=730), []
                    data["forecast_unknown"] = True
                segments = [
                    {"kind": "PRODUCTION", "start": a.isoformat(), "end": b.isoformat()}
                    for a, b in parts
                ]
            else:
                raise HTTPException(409, "在产批次缺少速度，请补齐日目标")
            data["planned_end_at"] = end.isoformat()
            data["segments"] = segments
        runs.append(data)
    external = [
        record(r)
        for r in db.scalars(
            select(Run).where(Run.factory_id != factory, Run.status.in_(ACTIVE))
        )
    ]
    return {
        "demands": demands,
        "machines": machines,
        "assets": assets,
        "events": events,
        "settings": settings,
        "runs": runs,
        "external_runs": external,
        "reserved_run_ids": reserved_run_ids,
    }


def save_runs(db, factory, result, actor):
    desired = {r["id"] for r in result["changed_runs"]}
    current = list(
        db.scalars(select(Run).where(Run.factory_id == factory, Run.status.in_(ACTIVE)))
    )
    demands = {
        d.id: d for d in db.scalars(select(Demand).where(Demand.factory_id == factory))
    }
    for demand in demands.values():
        demand.planned_start_at = demand.planned_end_at = (
            demand.expected_stock_ready_at
        ) = None
        demand.delivery_slack_hours = None
        demand.machine_code = None
        demand.extras = {
            **demand.extras,
            "active_run_id": None,
            "forecast_unknown": False,
        }
    for obj in current:
        if obj.id not in desired:
            if obj.status in {"RUNNING", "PAUSED"}:
                raise HTTPException(409, "不能移除已开工批次")
            obj.status = "CANCELLED"
            touch(obj, actor)
    for row in result["changed_runs"]:
        if row.get("status", "PLANNED") == "PLANNED":
            row["demand_ids"] = sorted(
                row["demand_ids"],
                key=lambda identity: priority(record(demands[identity])),
            )
        obj = db.get(Run, row["id"])
        if obj is None:
            obj = Run(id=row["id"], factory_id=factory)
            db.add(obj)
        elif obj.factory_id != factory:
            raise HTTPException(404, "批次不属于当前厂区")
        elif (
            obj.status in {"FINISHED", "TRANSFERRED"}
            and row.get("status", "PLANNED") == "PLANNED"
        ):
            raise HTTPException(409, "已结束的执行段不能覆盖为新计划")
        obj.machine_id = row["machine_id"]
        obj.mold_asset_id = row["mold_asset_id"]
        obj.status = row.get("status", "PLANNED")
        obj.sequence = row["sequence"]
        obj.pinned = row.get("pinned", False)
        obj.setup_start_at = timestamp(row["setup_start_at"])
        obj.planned_start_at = timestamp(row["planned_start_at"])
        obj.planned_end_at = timestamp(row["planned_end_at"])
        obj.segments = jsonable(row.get("segments", []))
        obj.explanation = jsonable(
            {
                **row.get("explanation", {}),
                "forecast_unknown": bool(row.get("forecast_unknown")),
            }
        )
        if obj.status not in {"RUNNING", "PAUSED"}:
            obj.snapshot = jsonable(
                {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {"snapshot", "segments", "execution_events", "explanation"}
                }
            )
        obj.planned_physical_shots = decimal(row["remaining_shots"], D(0)) + decimal(
            obj.physical_shots, D(0)
        )
        touch(obj, actor)
        db.flush()
        old = {
            r.demand_id: r
            for r in db.scalars(select(RunDemand).where(RunDemand.run_id == obj.id))
        }
        if obj.status == "PLANNED":
            for stale_id, stale_link in old.items():
                if stale_id not in row["demand_ids"]:
                    db.delete(stale_link)
        cumulative = D(0)
        for sequence, demand_id in enumerate(row["demand_ids"]):
            demand = demands.get(demand_id)
            if demand is None:
                raise HTTPException(404, "排程包含异厂需求")
            link = old.get(demand_id)
            if link is None:
                link = RunDemand(
                    factory_id=factory,
                    run_id=obj.id,
                    demand_id=demand_id,
                    sequence=sequence,
                    allocation_mode=demand.allocation_mode,
                    outputs_per_shot=demand.effective_outputs_per_shot,
                    planned_quantity=demand.remaining_units
                    if demand.allocation_mode == "CO_OUTPUT_UNITS"
                    else demand.remaining_shots or 0,
                    product_code=demand.item_no or demand.mold_code,
                )
                db.add(link)
            if obj.status == "PLANNED":
                link.sequence = sequence
                link.allocation_mode = demand.allocation_mode
                link.planned_quantity = (
                    demand.remaining_units
                    if demand.allocation_mode == "CO_OUTPUT_UNITS"
                    else demand.remaining_shots or 0
                )
                link.outputs_per_shot = demand.effective_outputs_per_shot
                link.product_code = demand.item_no or demand.mold_code
            demand.machine_code = row["machine_code"]
            demand.planned_start_at = obj.planned_start_at
            demand.planned_end_at = obj.planned_end_at
            if (
                demand.allocation_mode == "SEQUENTIAL_SHOTS"
                and len(row["demand_ids"]) > 1
                and not row.get("forecast_unknown")
            ):
                rate = decimal(row["target_shots_per_day"]) / decimal(
                    row.get("target_basis_hours"), D(24)
                )
                previous_quantity = cumulative
                cumulative += decimal(demand.remaining_shots, D(0))
                demand.planned_start_at = production_point(
                    row, previous_quantity / rate * 3600
                )
                demand.planned_end_at = production_point(row, cumulative / rate * 3600)
            demand.expected_stock_ready_at, demand.delivery_slack_hours = delivery(
                demand.planned_end_at,
                demand.delivery_due_at or demand.delivery_window_start,
                demand.downstream_lead_days,
            )
            if row.get("forecast_unknown"):
                demand.planned_end_at = demand.expected_stock_ready_at = (
                    demand.delivery_slack_hours
                ) = None
            demand.unplaced_reason = None
            demand.extras = jsonable(
                {
                    **demand.extras,
                    "active_run_id": obj.id,
                    "forecast_unknown": bool(row.get("forecast_unknown")),
                    "mold_change_minutes": obj.explanation.get("mold_change_minutes"),
                    "color_change_minutes": obj.explanation.get("color_change_minutes"),
                    "changeover_minutes": obj.explanation.get("changeover_minutes"),
                    "planned_completion_month": demand.planned_end_at.strftime("%Y-%m")
                    if demand.planned_end_at
                    else None,
                }
            )
        db.flush()
    for item in result.get("unplaced", []):
        demands[item["demand_id"]].unplaced_reason = item["reason_text"]
    db.flush()


def production_point(row, seconds):
    remaining = float(seconds)
    parts = [part for part in row.get("segments", []) if part["kind"] == "PRODUCTION"]
    for part in parts:
        start, end = timestamp(part["start"]), timestamp(part["end"])
        length = (end - start).total_seconds()
        if remaining <= length:
            return start + timedelta(seconds=max(0, remaining))
        remaining -= length
    return (
        timestamp(row["planned_end_at"])
        if seconds
        else timestamp(row["planned_start_at"])
    )


def public_run(row, *, forecast_unknown=None):
    """Hide internal occupancy sentinels without releasing machine/mold reservations."""
    unknown = (
        bool(
            row.get(
                "forecast_unknown",
                (row.get("explanation") or {}).get("forecast_unknown"),
            )
        )
        if forecast_unknown is None
        else forecast_unknown
    )
    if row.get("status") not in {"RUNNING", "PAUSED"}:
        unknown = False
    result = {**row, "forecast_unknown": unknown}
    if unknown:
        hidden = {
            "planned_end_at": None,
            "expected_stock_ready_at": None,
            "delivery_slack_hours": None,
            "planned_completion_month": None,
        }
        result.update(hidden, forecast_status="WAITING_FOR_RECOVERY")
        result["explanation"] = {
            **(row.get("explanation") or {}),
            "forecast_unknown": True,
            "reason_text": "等待资源恢复，预计结束时间未知；机台和实物模具仍保留占用。",
        }
        if isinstance(row.get("snapshot"), dict):
            result["snapshot"] = {**row["snapshot"], **hidden, "forecast_unknown": True}
    return result


def public_result(result):
    return jsonable(
        {**result, "changed_runs": [public_run(row) for row in result["changed_runs"]]}
    )


def auto_schedule(db, factory, scope, actor, as_of=None, save=True, snapshot_data=None):
    as_of = as_of or now()
    snap = snapshot_data if snapshot_data is not None else snapshot(db, factory, as_of)
    ids = set(scope.get("demand_ids", []))
    machine_ids = set(scope.get("machine_ids", []))
    if ids - {d["id"] for d in snap["demands"]} or machine_ids - {
        m["id"] for m in snap["machines"]
    }:
        raise HTTPException(404, "选择范围包含异厂或不存在的记录")
    try:
        result = schedule_factory(snap, scope, as_of)
    except ValueError as exc:
        raise HTTPException(409, REASONS.get(str(exc), str(exc))) from None
    if save:
        save_runs(db, factory, result, actor)
    return public_result(result)


def recalculate(db, factory, actor, as_of=None):
    as_of = as_of or now()
    snap = snapshot(db, factory, as_of)
    machines = {m["id"]: m for m in snap["machines"]}
    queues = {m: [] for m in machines}
    unplaced = []
    for run in sorted(snap["runs"], key=lambda r: (r["sequence"], r["id"])):
        reason = ready_reason(run) if run.get("status") == "PLANNED" else None
        if not reason and run.get("status") == "PLANNED":
            reason = fit(
                run,
                machines[run["machine_id"]],
                snap["settings"],
                manual_oversize=bool(run.get("manual_oversize")),
            )
        if reason:
            unplaced.extend(
                {
                    "demand_id": d,
                    "reason_code": reason,
                    "reason_text": REASONS.get(reason, reason),
                }
                for d in run["demand_ids"]
            )
        else:
            queues[run["machine_id"]].append(run)
    while True:
        try:
            rows = simulate(
                queues,
                machines,
                {a["id"]: a for a in snap["assets"]},
                snap["settings"],
                snap["events"],
                as_of,
                external=snap["external_runs"],
            )
            break
        except ScheduleConflict as exc:
            affected = next(
                (
                    r
                    for queue in queues.values()
                    for r in queue
                    if r["id"] == exc.run_id
                ),
                None,
            )
            if not affected or affected.get("status") != "PLANNED":
                raise HTTPException(409, REASONS.get(str(exc), str(exc))) from None
            queues[affected["machine_id"]].remove(affected)
            unplaced.extend(
                {
                    "demand_id": identity,
                    "reason_code": str(exc),
                    "reason_text": REASONS.get(str(exc), str(exc)),
                }
                for identity in affected["demand_ids"]
            )
        except ValueError as exc:
            raise HTTPException(409, REASONS.get(str(exc), str(exc))) from None
    result = {
        "changed_runs": rows,
        "unplaced": unplaced,
        "as_of": timestamp(as_of).isoformat(),
    }
    save_runs(db, factory, result, actor)
    return public_result(result)


def group(db, payload, actor):
    factory, as_of = payload.factory_id, now()
    snap = snapshot(db, factory, as_of)
    machines = {machine["id"]: machine for machine in snap["machines"]}
    if payload.machine_id not in machines:
        raise HTTPException(404, "机台不存在或不属于本厂")
    identities = set(payload.demand_ids)
    demands = sorted(
        (d for d in snap["demands"] if d["id"] in identities), key=priority
    )
    if len(demands) != len(identities):
        raise HTTPException(404, "所选需求不存在或不属于本厂")
    first = demands[0]
    mode = first["allocation_mode"]
    for demand in demands:
        reason = ready_reason(demand) or fit(
            demand,
            machines[payload.machine_id],
            snap["settings"],
            manual_oversize=payload.allow_oversized,
        )
        if reason or decimal(demand.get("remaining_shots"), D(0)) <= 0:
            raise HTTPException(
                422, REASONS.get(reason, reason) if reason else "完成需求不能加入生产组"
            )
        # Co-output products may have different outputs per shot, but share one confirmed vector.
        comparable = (
            {
                **demand,
                "effective_outputs_per_shot": first.get("effective_outputs_per_shot"),
            }
            if mode == "CO_OUTPUT_UNITS"
            else demand
        )
        if mode != demand["allocation_mode"] or not compatible_process(
            first, comparable
        ):
            raise HTTPException(
                422,
                "连续组需使用相同模具、出件配置、材料牌号、颜色色粉、速度和工艺要求",
            )
    queues = {machine: [] for machine in machines}
    selected_runs = []
    for run in snap["runs"]:
        if identities.intersection(run["demand_ids"]):
            if run["status"] != "PLANNED" or set(run["demand_ids"]) - identities:
                raise HTTPException(
                    409, "已开工批次不能重组；已有订单组请选择其全部需求"
                )
            selected_runs.append(run)
        else:
            queues[run["machine_id"]].append(run)
    asset = next(
        (
            a
            for a in snap["assets"]
            if a["master_id"] == first["mold_master_id"]
            and a["status"] == "AVAILABLE"
            and a["current_factory_id"] == factory
        ),
        None,
    )
    if asset is None:
        raise HTTPException(422, "本厂没有可用实物模具")
    job = {
        **deepcopy(first),
        "id": selected_runs[0]["id"]
        if selected_runs
        else planned_run_id(first["id"], snap),
        "demand_ids": [d["id"] for d in demands],
        "mold_asset_id": asset["id"],
        "machine_id": payload.machine_id,
        "remaining_shots": remaining_for_group(demands),
        "earliest_available_at": max(
            (
                d["earliest_available_at"]
                for d in demands
                if d.get("earliest_available_at")
            ),
            default=None,
        ),
        "status": "PLANNED",
        "pinned": True,
        "manual_oversize": payload.allow_oversized,
    }
    queue = queues[payload.machine_id]
    # Preserve an existing source position; otherwise append at the machine tail.
    place = min(
        (r["sequence"] for r in selected_runs if r["machine_id"] == payload.machine_id),
        default=len(queue),
    )
    queue.insert(min(place, len(queue)), job)
    try:
        rows = simulate(
            queues,
            machines,
            {a["id"]: a for a in snap["assets"]},
            snap["settings"],
            snap["events"],
            as_of,
            external=snap["external_runs"],
        )
    except ValueError as exc:
        raise HTTPException(422, REASONS.get(str(exc), str(exc))) from None
    result = {"changed_runs": rows, "unplaced": [], "grouped_run_id": job["id"]}
    save_runs(db, factory, result, actor)
    return public_result(result)


def move(db, payload, actor, as_of=None):
    as_of = as_of or now()
    factory = payload.factory_id
    snap = snapshot(db, factory, as_of)
    machines = {m["id"]: m for m in snap["machines"]}
    machine = machines.get(payload.machine_id)
    if not machine:
        raise HTTPException(404, "机台不存在或不属于本厂")
    queues = {m: [] for m in machines}
    moving = None
    for r in sorted(snap["runs"], key=lambda r: (r["sequence"], r["id"])):
        if r["id"] == payload.run_id:
            moving = r
        else:
            queues[r["machine_id"]].append(r)
    if moving is None and payload.demand_id:
        demand = next(
            (d for d in snap["demands"] if d["id"] == payload.demand_id), None
        )
        if not demand:
            raise HTTPException(404, "需求不存在或不属于本厂")
        if any(demand["id"] in r["demand_ids"] for r in snap["runs"]):
            raise HTTPException(409, "需求已经排程，请移动现有批次")
        reason = ready_reason(demand)
        if reason:
            raise HTTPException(422, REASONS.get(reason, reason))
        asset = next(
            (
                a
                for a in snap["assets"]
                if a["master_id"] == demand["mold_master_id"]
                and a["current_factory_id"] == factory
                and a["status"] == "AVAILABLE"
            ),
            None,
        )
        if not asset:
            raise HTTPException(422, "本厂没有可用实物模具")
        moving = {
            **deepcopy(demand),
            "id": planned_run_id(demand["id"], snap),
            "demand_ids": [demand["id"]],
            "mold_asset_id": asset["id"],
            "status": "PLANNED",
        }
    if moving is None:
        raise HTTPException(404, "批次不存在")
    if moving.get("status") in {"RUNNING", "PAUSED"}:
        raise HTTPException(409, "已开工批次需先记录暂停转机，历史不能拖走")
    reason = fit(
        moving, machine, snap["settings"], manual_oversize=payload.allow_oversized
    )
    if reason:
        text = (
            f"{moving.get('required_machine_a')}A 模不能放 {machine.get('machine_a')}A 机"
            if reason == "MACHINE_TOO_SMALL"
            else REASONS.get(reason, reason)
        )
        raise HTTPException(422, text)
    original_machine_id = moving.get("machine_id")
    moving["machine_id"] = machine["id"]
    moving["manual_oversize"] = payload.allow_oversized
    moving["pinned"] = False
    q = queues[machine["id"]]
    if payload.before_run_id:
        pos = next(
            (i for i, r in enumerate(q) if r["id"] == payload.before_run_id), None
        )
        if pos is None:
            raise HTTPException(422, "目标相邻批次不属于该机台")
    elif payload.pinned is not None and original_machine_id == payload.machine_id:
        pos = min(int(moving.get("sequence", len(q))), len(q))
    else:
        pos = len(q)
    q.insert(pos, moving)
    try:
        rows = simulate(
            queues,
            machines,
            {a["id"]: a for a in snap["assets"]},
            snap["settings"],
            snap["events"],
            as_of,
            external=snap["external_runs"],
        )
    except ValueError as exc:
        raise HTTPException(409, REASONS.get(str(exc), str(exc))) from None
    target = next(r for r in rows if r["id"] == moving["id"])
    target["pinned"] = payload.pinned if payload.pinned is not None else False
    result = {"changed_runs": rows, "unplaced": [], "moved_run_id": target["id"]}
    save_runs(db, factory, result, actor)
    return public_result(result)


def import_original_assignments(
    db, factory, assignments, actor, *, replace_demand_ids=(), strict=False, as_of=None
):
    snap = snapshot(db, factory)
    machines = {m["id"]: m for m in snap["machines"]}
    demands = {d["id"]: d for d in snap["demands"]}
    queues = {m: [] for m in machines}
    replacements = set(replace_demand_ids)
    for run in sorted(snap["runs"], key=lambda r: (r["sequence"], r["id"])):
        if replacements.intersection(run["demand_ids"]):
            if run["status"] != "PLANNED" or not set(run["demand_ids"]) <= replacements:
                raise HTTPException(
                    409, "导入涉及已开工或合并了其他需求的批次，请先在系统核对"
                )
            continue
        queues[run["machine_id"]].append(run)
    issues = []
    for item in assignments:
        d = demands[item["demand_id"]]
        if d.get("remaining_shots") == 0:
            continue
        reason = ready_reason(d) or fit(
            d, machines[item["machine_id"]], snap["settings"], manual_oversize=True
        )
        asset = next(
            (
                a
                for a in snap["assets"]
                if a["master_id"] == d["mold_master_id"]
                and a["current_factory_id"] == factory
                and a["status"] == "AVAILABLE"
                and (not item.get("mold_asset_id") or a["id"] == item["mold_asset_id"])
            ),
            None,
        )
        if not reason and not asset:
            reason = "MOLD_NOT_AVAILABLE"
        if reason:
            issues.append(
                {
                    "demand_id": d["id"],
                    "reason_code": reason,
                    "reason_text": REASONS.get(reason, reason),
                    "source_row": item["source_row"],
                }
            )
            continue
        queues[item["machine_id"]].append(
            {
                **d,
                "id": planned_run_id(d["id"], snap),
                "demand_ids": [d["id"]],
                "mold_asset_id": asset["id"],
                "machine_id": item["machine_id"],
                "status": "PLANNED",
                "pinned": False,
                "manual_oversize": True,
            }
        )
    if strict and issues:
        raise HTTPException(
            422,
            "；".join(
                f"第 {i['source_row']} 行原排机未保存：{i['reason_text']}"
                for i in issues
            ),
        )
    as_of = as_of or (
        min(
            (
                timestamp(a["legacy_start"])
                for a in assignments
                if a.get("legacy_start")
            ),
            default=now(),
        )
        if not snap["runs"]
        else now()
    )
    try:
        rows = simulate(
            queues,
            machines,
            {a["id"]: a for a in snap["assets"]},
            snap["settings"],
            snap["events"],
            as_of,
            external=snap["external_runs"],
        )
    except ValueError as exc:
        raise HTTPException(409, f"原计划资源冲突：{exc}") from None
    result = {"changed_runs": rows, "unplaced": issues}
    save_runs(db, factory, result, actor)
    return public_result(result)
