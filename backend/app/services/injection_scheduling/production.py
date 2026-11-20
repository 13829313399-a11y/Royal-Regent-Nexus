from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    Machine,
    MoldAsset,
    Run,
    RunDemand,
)

from .calculations import decimal, now, timestamp
from .common import check_revision, record, scoped, touch
from .planning import public_run, recalculate
from .resource_calendar import calendar_blocks
from .scheduler import REASONS, fit, ready_reason


def validate_execution(db, factory, run, machine, instant):
    """Validate current physical facts again at start/resume, under the write lock."""
    settings = db.get(FactorySettings, factory).parameters
    asset = scoped(db, MoldAsset, run.mold_asset_id, factory)
    if (
        asset.status != "AVAILABLE"
        or asset.available_at
        and timestamp(asset.available_at) > instant
    ):
        raise HTTPException(409, "实物模具当前不可用")
    if machine.operating_status in {"MAINTENANCE", "FAULT", "DISABLED"}:
        raise HTTPException(409, "机台当前不可生产，请先解除设备停机状态")
    links = list(db.scalars(select(RunDemand).where(RunDemand.run_id == run.id)))
    if not links:
        raise HTTPException(409, "批次未关联需求")
    for link in links:
        demand = scoped(db, Demand, link.demand_id, factory)
        data = {**record(demand), **(run.snapshot if run.status == "PAUSED" else {})}
        why = ready_reason(data) or fit(
            data,
            record(machine),
            settings,
            manual_oversize=bool(run.snapshot.get("manual_oversize")),
        )
        if why:
            raise HTTPException(422, REASONS.get(why, why))
        if demand.mold_master_id != asset.master_id:
            raise HTTPException(409, "实物模具与需求模具不匹配")
        if (
            demand.earliest_available_at
            and timestamp(demand.earliest_available_at) > instant
        ):
            raise HTTPException(409, "需求尚未到可生产时间")
    if not any(
        decimal(db.get(Demand, link.demand_id).remaining_shots, 0) > 0 for link in links
    ):
        raise HTTPException(409, "该批次已无剩余生产数量")
    events = [
        record(e)
        for e in db.scalars(
            select(CalendarEvent).where(CalendarEvent.factory_id == factory)
        )
    ]
    if any(
        start <= instant < end
        for start, end in calendar_blocks(
            instant, settings, events, machine.id, asset.id
        )
    ):
        raise HTTPException(409, "当前处于厂区、机台或模具的停机日历内")
    clash = db.scalar(
        select(Run.id)
        .where(
            Run.id != run.id,
            Run.status.in_(["RUNNING", "PAUSED"]),
            (Run.machine_id == run.machine_id)
            | (Run.mold_asset_id == run.mold_asset_id),
        )
        .limit(1)
    )
    if clash:
        raise HTTPException(409, "该机台或实物模具已有执行中的批次")


def action(
    db,
    factory,
    run_id,
    verb,
    actor,
    reason="",
    target_machine_id=None,
    *,
    instant=None,
    recalculate_after=True,
):
    run = scoped(db, Run, run_id, factory)
    machine = scoped(db, Machine, run.machine_id, factory)
    instant = instant or now()
    was_unknown = bool(run.explanation.get("forecast_unknown")) or (
        run.status == "PAUSED" and not machine.recovery_at
    )
    before = record(run)
    if verb == "start":
        if run.status != "PLANNED":
            raise HTTPException(409, "只有未开工计划可以开工")
        validate_execution(db, factory, run, machine, instant)
        run.status = "RUNNING"
        run.actual_start_at = instant
        run.setup_start_at = run.planned_start_at = instant
        machine.operating_status = "RUNNING"
        machine.current_setup = {**run.snapshot, "mold_asset_id": run.mold_asset_id}
    elif verb == "pause":
        if run.status != "RUNNING":
            raise HTTPException(409, "只有在产批次可以暂停")
        run.status = "PAUSED"
        machine.operating_status = "IDLE"
    elif verb == "resume":
        if run.status != "PAUSED":
            raise HTTPException(409, "只有已暂停批次可以恢复")
        validate_execution(db, factory, run, machine, instant)
        run.status = "RUNNING"
        machine.operating_status = "RUNNING"
    elif verb == "finish":
        if run.status not in {"RUNNING", "PAUSED"}:
            raise HTTPException(409, "该批次尚未开工或已经结束")
        run.status = "FINISHED"
        run.actual_end_at = instant
        machine.operating_status = "IDLE"
    elif verb == "transfer":
        if run.status != "PAUSED" or not target_machine_id:
            raise HTTPException(409, "请先暂停，并选择剩余量的目标机台")
        target = scoped(db, Machine, target_machine_id, factory)
        if target.id == machine.id:
            raise HTTPException(422, "转机请选择另一台机台；原机继续生产请使用恢复")
        why = fit(
            {**run.snapshot, "factory_id": factory},
            record(target),
            db.get(FactorySettings, factory).parameters,
            manual_oversize=True,
        )
        if why:
            raise HTTPException(422, f"目标机台不可行：{why}")
        run.status = "TRANSFERRED"
        run.actual_end_at = instant
        machine.operating_status = "IDLE"
        successor = Run(
            id=uuid4().hex,
            factory_id=factory,
            machine_id=target.id,
            mold_asset_id=run.mold_asset_id,
            parent_run_id=run.id,
            status="PLANNED",
            sequence=100000,
            snapshot=run.snapshot,
            setup_start_at=instant,
            planned_start_at=instant,
            planned_end_at=instant,
            physical_shots=0,
            planned_physical_shots=0,
            explanation={"transfer_from": run.id},
        )
        touch(successor, actor)
        db.add(successor)
        db.flush()
        for old in db.scalars(select(RunDemand).where(RunDemand.run_id == run.id)):
            d = db.get(Demand, old.demand_id)
            db.add(
                RunDemand(
                    factory_id=factory,
                    run_id=successor.id,
                    demand_id=d.id,
                    allocation_mode=old.allocation_mode,
                    sequence=old.sequence,
                    planned_quantity=d.remaining_units
                    if old.allocation_mode == "CO_OUTPUT_UNITS"
                    else d.remaining_shots or 0,
                    outputs_per_shot=old.outputs_per_shot,
                    product_code=old.product_code,
                )
            )
    else:
        raise HTTPException(422, "不支持的开停工动作")
    run.execution_events = [
        *run.execution_events,
        {
            "action": verb,
            "at": instant.isoformat(),
            "actor_id": actor,
            "reason": reason,
            "physical_shots": float(run.physical_shots),
        },
    ]
    if run.status in {"FINISHED", "TRANSFERRED"} and was_unknown:
        run.planned_end_at = instant
        run.explanation = {**run.explanation, "forecast_unknown": False}
    touch(run, actor)
    touch(machine, actor)
    db.flush()
    result = recalculate(db, factory, actor, instant) if recalculate_after else {}
    return {**result, "run": public_run(record(run)), "before": before}


def machine_status(db, factory, machine_id, data, actor):
    machine = scoped(db, Machine, machine_id, factory)
    status = data.get("operating_status")
    if status not in {"IDLE", "MAINTENANCE", "FAULT", "DISABLED"}:
        raise HTTPException(422, "设备状态不正确；运行中来自批次开工")
    instant = now()
    recovery = timestamp(data.get("recovery_at"))
    if recovery and recovery <= instant and status != "IDLE":
        raise HTTPException(422, "预计恢复时间必须晚于当前时间")
    machine.operating_status = status
    machine.recovery_at = recovery if status != "IDLE" else None
    machine.notes = str(data.get("notes", machine.notes))
    for event in db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.factory_id == factory,
            CalendarEvent.resource_type == "MACHINE",
            CalendarEvent.resource_id == machine.id,
            CalendarEvent.kind == "STATUS_STOP",
            CalendarEvent.start_at <= instant,
            or_(CalendarEvent.end_at.is_(None), CalendarEvent.end_at > instant),
        )
    ):
        event.end_at = instant
    if status != "IDLE":
        db.add(
            CalendarEvent(
                factory_id=factory,
                resource_type="MACHINE",
                resource_id=machine.id,
                start_at=instant,
                end_at=recovery,
                kind="STATUS_STOP",
                notes=machine.notes,
            )
        )
        for run in db.scalars(
            select(Run).where(
                Run.machine_id == machine.id,
                Run.factory_id == factory,
                Run.status == "RUNNING",
            )
        ):
            run.status = "PAUSED"
            run.execution_events = [
                *run.execution_events,
                {
                    "action": "pause_for_machine",
                    "at": instant.isoformat(),
                    "actor_id": actor,
                    "reason": machine.notes,
                },
            ]
            touch(run, actor)
    touch(machine, actor)
    db.flush()
    result = recalculate(db, factory, actor, instant)
    return {**result, "machine": record(machine)}


def relocate_asset(
    db, factory, identity, destination, data, actor, record_revision=None
):
    asset = scoped(db, MoldAsset, identity, factory)
    check_revision(asset, record_revision)
    if destination == factory:
        raise HTTPException(422, "请选择另一厂区")
    if db.scalar(
        select(Run.id)
        .where(Run.mold_asset_id == identity, Run.status.in_(["RUNNING", "PAUSED"]))
        .limit(1)
    ):
        raise HTTPException(409, "模具仍在执行批次中，请先结束实际占用")
    before = record(asset)
    asset.current_factory_id = destination
    asset.available_at = timestamp(data.get("available_at"))
    asset.location_source = f"人工调厂：{factory} → {destination}"
    if "notes" in data:
        asset.notes = str(data["notes"])[:2000]
    touch(asset, actor)
    # Source plans lose this physical asset; identity and historical production stay intact.
    db.execute(
        update(FactorySettings)
        .where(FactorySettings.factory_id == destination)
        .values(revision=FactorySettings.revision + 1)
    )
    db.flush()
    source = recalculate(db, factory, actor)
    target = recalculate(db, destination, actor)
    return {
        "record": record(asset),
        "source_impact": source,
        "destination_impact": target,
        "destination_revision": db.get(FactorySettings, destination).revision,
        "before": before,
    }
