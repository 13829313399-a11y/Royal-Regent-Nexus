from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.models.injection_scheduling import (
    Demand,
    FactorySettings,
    HistoricalOutput,
    ReportAllocation,
    Run,
    RunDemand,
    ShiftReport,
)

from .calculations import TZ, decimal, now, sequential_allocate, timestamp
from .common import record, scoped, touch
from .enrichment import update_quantities


def shift_window(production_date, shift_code, settings):
    day = (
        date.fromisoformat(production_date)
        if isinstance(production_date, str)
        else production_date
    )
    day_start = time.fromisoformat(settings["day_start"])
    night_start = time.fromisoformat(settings["night_start"])
    a = datetime.combine(day, day_start if shift_code == "DAY" else night_start, TZ)
    b = datetime.combine(day, night_start if shift_code == "DAY" else day_start, TZ)
    if b <= a:
        b += timedelta(days=1)
    return a, b


def current_shift(instant, settings):
    instant = timestamp(instant)
    for day in (instant.date(), instant.date() - timedelta(days=1)):
        for code in ("DAY", "NIGHT"):
            start, end = shift_window(day, code, settings)
            if start <= instant < end:
                return day, code
    raise HTTPException(422, "白夜班起始时间配置不正确")


def refresh_quantities(db, factory, demand_ids=None):
    scope = [Demand.factory_id == factory]
    if demand_ids is not None:
        scope.append(Demand.id.in_(demand_ids))
    histories = dict(
        db.execute(
            select(HistoricalOutput.demand_id, func.sum(HistoricalOutput.quantity))
            .join(Demand, Demand.id == HistoricalOutput.demand_id)
            .where(*scope, HistoricalOutput.counts_toward_demand.is_(True))
            .group_by(HistoricalOutput.demand_id)
        ).all()
    )
    values = db.execute(
        select(
            RunDemand.demand_id,
            ReportAllocation.unit,
            func.sum(ReportAllocation.quantity),
        )
        .join(ReportAllocation, ReportAllocation.run_demand_id == RunDemand.id)
        .join(Demand, Demand.id == RunDemand.demand_id)
        .where(*scope)
        .group_by(RunDemand.demand_id, ReportAllocation.unit)
    ).all()
    shots, units = {}, {}
    for demand_id, unit, total in values:
        (shots if unit == "SHOT" else units)[demand_id] = total
    for demand in db.scalars(select(Demand).where(*scope)):
        update_quantities(
            demand,
            decimal(histories.get(demand.id), D(0))
            + decimal(shots.get(demand.id), D(0)),
            decimal(units.get(demand.id), D(0)),
        )
    db.flush()


def reallocate_run(db, run, *, refresh=True):
    links = list(
        db.scalars(
            select(RunDemand)
            .where(RunDemand.run_id == run.id)
            .order_by(RunDemand.sequence, RunDemand.id)
        )
    )
    reports = list(
        db.scalars(
            select(ShiftReport)
            .where(ShiftReport.run_id == run.id)
            .order_by(
                ShiftReport.production_date,
                ShiftReport.shift_code,
                ShiftReport.segment_key,
            )
        )
    )
    report_ids = [r.id for r in reports]
    if report_ids:
        db.execute(
            delete(ReportAllocation).where(ReportAllocation.report_id.in_(report_ids))
        )
    # Use the current demand totals; saved plan quotas must not truncate corrected production.
    # Existing earlier-run history remains in its original execution segment.
    remaining = []
    for link in links:
        demand = db.get(Demand, link.demand_id)
        history = db.scalar(
            select(func.sum(HistoricalOutput.quantity)).where(
                HistoricalOutput.demand_id == demand.id,
                HistoricalOutput.counts_toward_demand.is_(True),
            )
        ) or D(0)
        other = db.scalar(
            select(func.sum(ReportAllocation.quantity))
            .join(RunDemand, RunDemand.id == ReportAllocation.run_demand_id)
            .where(RunDemand.demand_id == demand.id, RunDemand.run_id != run.id)
        ) or D(0)
        total = (
            demand.required_units
            if link.allocation_mode == "CO_OUTPUT_UNITS"
            else decimal(demand.planned_shots, D(0))
            + demand.adjustment_shots
            - demand.opening_shots
            - history
        )
        remaining.append(max(D(0), decimal(total, D(0)) - other))
    totals = [D(0) for _ in links]
    physical = D(0)
    surplus = D(0)
    mode = links[0].allocation_mode if links else "SEQUENTIAL_SHOTS"
    if not links:
        raise HTTPException(409, "批次未关联任何需求")
    for report in reports:
        physical += report.physical_shots
        if mode == "CO_OUTPUT_UNITS":
            allocations = [D(0) for _ in links]
            products = {link.product_code for link in links}
            if set(report.good_units) - products or set(report.scrap_units) - products:
                raise HTTPException(422, "报工包含该批次出件配置之外的产物")
            for product in products:
                indexes = [
                    i for i, link in enumerate(links) if link.product_code == product
                ]
                outputs = {links[i].outputs_per_shot for i in indexes}
                if len(outputs) != 1:
                    raise HTTPException(409, "同一产物的每啤出件配置不一致")
                theoretical = report.physical_shots * next(iter(outputs))
                scrap = decimal(report.scrap_units.get(product), D(0))
                good = decimal(report.good_units.get(product), theoretical - scrap)
                if good < 0 or scrap < 0 or good + scrap > theoretical:
                    raise HTTPException(422, "良品与不良件数不能超过该产物的理论出件数")
                portions, _ = (
                    ([good], D(0))
                    if len(indexes) == 1
                    else sequential_allocate(good, [remaining[i] for i in indexes])
                )
                for index, portion in zip(indexes, portions, strict=True):
                    allocations[index] = portion
        else:
            allocations, left = (
                ([report.physical_shots], D(0))
                if len(links) == 1
                else sequential_allocate(report.physical_shots, remaining)
            )
            surplus += left
        for i, (link, quantity) in enumerate(zip(links, allocations, strict=True)):
            remaining[i] = max(D(0), remaining[i] - quantity)
            totals[i] += quantity
            db.add(
                ReportAllocation(
                    report_id=report.id,
                    run_demand_id=link.id,
                    quantity=quantity,
                    unit="UNIT" if mode == "CO_OUTPUT_UNITS" else "SHOT",
                )
            )
    run.physical_shots = physical
    run.explanation = {
        **run.explanation,
        "overproduced_physical_shots": float(surplus),
        "allocation_mode": mode,
    }
    db.flush()
    if refresh:
        refresh_quantities(db, run.factory_id, [link.demand_id for link in links])


def reallocate_factory(db, factory, *, run_id=None, demand_ids=None):
    links = list(db.scalars(select(RunDemand).where(RunDemand.factory_id == factory)))
    affected = set(demand_ids or [])
    selected_runs = {run_id} if run_id else set()
    if run_id is not None or demand_ids is not None:
        # Follow only connected execution segments/order groups; unrelated machines retain allocations.
        while True:
            prior = (len(affected), len(selected_runs))
            affected.update(
                link.demand_id for link in links if link.run_id in selected_runs
            )
            selected_runs.update(
                link.run_id for link in links if link.demand_id in affected
            )
            if prior == (len(affected), len(selected_runs)):
                break
        owned = select(RunDemand.id).where(
            RunDemand.factory_id == factory, RunDemand.run_id.in_(selected_runs)
        )
    else:
        owned = select(RunDemand.id).where(RunDemand.factory_id == factory)
    db.execute(
        delete(ReportAllocation).where(ReportAllocation.run_demand_id.in_(owned))
    )
    query = select(Run).where(
        Run.factory_id == factory, Run.actual_start_at.is_not(None)
    )
    if run_id is not None or demand_ids is not None:
        query = query.where(Run.id.in_(selected_runs))
    runs = list(db.scalars(query.order_by(Run.actual_start_at, Run.id)))
    for run in runs:
        reallocate_run(db, run, refresh=False)
    refresh_quantities(
        db, factory, affected if run_id is not None or demand_ids is not None else None
    )


def save_report(db, payload, actor):
    run = scoped(db, Run, payload.run_id, payload.factory_id)
    if not run.actual_start_at or run.status not in {
        "RUNNING",
        "PAUSED",
        "FINISHED",
        "TRANSFERRED",
    }:
        raise HTTPException(409, "请先对该批次执行开工，再填写实际报数")
    try:
        day = date.fromisoformat(payload.production_date)
    except ValueError:
        raise HTTPException(422, "生产日期格式不正确") from None
    parameters = db.get(FactorySettings, payload.factory_id).parameters
    start, end = shift_window(day, payload.shift_code, parameters)
    if (
        start > now()
        or end <= timestamp(run.actual_start_at)
        or run.actual_end_at
        and start >= timestamp(run.actual_end_at)
    ):
        raise HTTPException(422, "该班次不在本批次的实际执行期间内")
    if any(
        type(n) is not int or n < 0
        for n in [*payload.good_units.values(), *payload.scrap_units.values()]
    ):
        raise HTTPException(422, "良品、不良必须为非负整数件数")
    links = list(db.scalars(select(RunDemand).where(RunDemand.run_id == run.id)))
    for link in links:
        demand = db.get(Demand, link.demand_id)
        if demand.opening_cutoff_at and end <= timestamp(demand.opening_cutoff_at):
            raise HTTPException(409, "该班次已包含在导入历史中，不能重复累计")
    report = db.scalar(
        select(ShiftReport).where(
            ShiftReport.run_id == run.id,
            ShiftReport.production_date == day,
            ShiftReport.shift_code == payload.shift_code,
            ShiftReport.segment_key == payload.segment_key,
        )
    )
    if (report.revision if report else 0) != payload.report_revision:
        raise HTTPException(409, "这项班次数量已被修改，请刷新后重新保存")
    before = record(report) if report else {}
    if report is None:
        report = ShiftReport(
            factory_id=payload.factory_id,
            run_id=run.id,
            production_date=day,
            shift_code=payload.shift_code,
            segment_key=payload.segment_key,
        )
        db.add(report)
    report.physical_shots = payload.physical_shots
    report.good_units = payload.good_units
    report.scrap_units = payload.scrap_units
    report.client_operation_id = payload.client_operation_id
    touch(report, actor)
    db.flush()
    reallocate_factory(db, run.factory_id, run_id=run.id)
    touch(run, actor)
    return {
        "report": record(report),
        "physical_delta": payload.physical_shots - before.get("physical_shots", 0),
        "before": before,
    }


def list_reports(
    db, factory, run_id=None, demand_id=None, from_date=None, to_date=None
):
    query = select(ShiftReport).where(ShiftReport.factory_id == factory)
    if run_id:
        scoped(db, Run, run_id, factory)
        query = query.where(ShiftReport.run_id == run_id)
    if demand_id:
        scoped(db, Demand, demand_id, factory)
        query = query.where(
            ShiftReport.run_id.in_(
                select(RunDemand.run_id).where(
                    RunDemand.demand_id == demand_id, RunDemand.factory_id == factory
                )
            )
        )
    if from_date:
        query = query.where(
            ShiftReport.production_date >= date.fromisoformat(from_date)
        )
    if to_date:
        query = query.where(ShiftReport.production_date <= date.fromisoformat(to_date))
    return [
        record(r)
        for r in db.scalars(
            query.order_by(ShiftReport.production_date, ShiftReport.shift_code)
        )
    ]
