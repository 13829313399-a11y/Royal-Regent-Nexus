"""Explicit factory plan reset; persistent resources are outside the deletion set."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    HistoricalOutput,
    ImportBatch,
    ImportRow,
    Machine,
    MoldAsset,
    MoldMaster,
    ReportAllocation,
    Run,
    RunDemand,
    SavedView,
    SharedRevision,
    ShiftReport,
)

from .common import record, touch
from .queries import revision

FACTORY_NAMES = {
    "huaxing": "华兴",
    "huadeng": "华登",
    "huakang-a": "华康 A",
    "huakang-b": "华康 B",
}


def confirmation_text(factory):
    return f"清空{FACTORY_NAMES[factory]}计划数据"


def selections(factory):
    demands = select(Demand.id).where(Demand.factory_id == factory)
    batches = select(ImportBatch.id).where(ImportBatch.factory_id == factory)
    reports = select(ShiftReport.id).where(ShiftReport.factory_id == factory)
    # Child-first order also works with non-deferred SQLite/PostgreSQL FKs.
    return [
        (ReportAllocation, ReportAllocation.report_id.in_(reports)),
        (ShiftReport, ShiftReport.factory_id == factory),
        (RunDemand, RunDemand.factory_id == factory),
        (Run, Run.factory_id == factory),
        (HistoricalOutput, HistoricalOutput.demand_id.in_(demands)),
        (ImportRow, ImportRow.batch_id.in_(batches)),
        (Demand, Demand.factory_id == factory),
        (ImportBatch, ImportBatch.factory_id == factory),
    ]


def snapshot(db, factory):
    data = {
        model.__tablename__: [
            record(row)
            for row in db.scalars(select(model).where(where).order_by(model.id))
        ]
        for model, where in selections(factory)
    }
    machine_ids = {r["machine_id"] for r in data[Run.__tablename__]}
    # Resource specifications, calendar, maintenance/fault state and mold assets
    # survive. Only erased jobs' runtime setup/occupancy is reset.
    machines = list(
        db.scalars(
            select(Machine).where(Machine.factory_id == factory).order_by(Machine.id)
        )
    )
    changes = [
        m
        for m in machines
        if m.operating_status == "RUNNING" or (m.id in machine_ids and m.current_setup)
    ]
    data["machine_runtime_before"] = [record(m) for m in changes]
    return data, changes


def token(factory, base_revision, data):
    return hashlib.sha256(
        json.dumps(
            {"factory_id": factory, "revision": base_revision, "data": data},
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def counts(data):
    demands = data[Demand.__tablename__]
    runs = data[Run.__tablename__]
    return {
        "demands": len(demands),
        "manual_demands": sum(not d["import_batch_id"] for d in demands),
        "runs": len(runs),
        "active_runs": sum(r["status"] in {"RUNNING", "PAUSED"} for r in runs),
        "executed_runs": sum(
            r["status"] in {"RUNNING", "PAUSED", "FINISHED", "TRANSFERRED"}
            or r["actual_start_at"] is not None
            or r["actual_end_at"] is not None
            or bool(r["execution_events"])
            or r["physical_shots"] > 0
            for r in runs
        ),
        "shift_reports": len(data[ShiftReport.__tablename__]),
        "report_allocations": len(data[ReportAllocation.__tablename__]),
        "historical_outputs": len(data[HistoricalOutput.__tablename__]),
        "import_batches": len(data[ImportBatch.__tablename__]),
        "import_rows": len(data[ImportRow.__tablename__]),
        "machine_runtime_resets": len(data["machine_runtime_before"]),
    }


def preview(db, factory):
    versions = revision(db, factory)
    data, _ = snapshot(db, factory)
    impact = counts(data)
    preserved = {}
    for name, model, where in [
        ("machines", Machine, Machine.factory_id == factory),
        ("mold_masters", MoldMaster, True),
        ("mold_assets", MoldAsset, MoldAsset.current_factory_id == factory),
        ("calendar_events", CalendarEvent, CalendarEvent.factory_id == factory),
        ("saved_views", SavedView, SavedView.factory_id == factory),
    ]:
        preserved[name] = db.scalar(
            select(func.count()).select_from(model).where(where)
        )
    return {
        "factory_id": factory,
        **versions,
        "counts": impact,
        "preserved": preserved,
        "requires_execution_confirmation": bool(
            impact["executed_runs"] or impact["shift_reports"]
        ),
        "can_clear": any(impact.values()),
        "confirmation_text": confirmation_text(factory),
        "preview_token": token(factory, versions["revision"], data),
        "imports": [
            {k: b[k] for k in ("id", "file_name", "sheet_name", "status")}
            for b in data[ImportBatch.__tablename__]
        ],
    }


def clear(db, payload, actor):
    factory = payload.factory_id
    if payload.confirmation != confirmation_text(factory):
        raise HTTPException(422, "请完整输入当前厂区的清空确认文字")
    reason = payload.reason.strip()
    if len(reason) < 2:
        raise HTTPException(422, "请填写至少两个字的清空原因")
    # write() has already locked shared/factory revisions before this callback.
    if payload.expected_revision != payload.base_revision:
        raise HTTPException(409, "预览后资料已更新，请重新预览清空范围")
    before, machines = snapshot(db, factory)
    if token(factory, payload.base_revision, before) != payload.preview_token:
        raise HTTPException(409, "预览后资料已更新，请重新预览清空范围")
    impact = counts(before)
    if (
        impact["executed_runs"] or impact["shift_reports"]
    ) and not payload.include_execution:
        raise HTTPException(409, "包含开工或报工记录，请额外确认删除这些生产记录")
    if not any(impact.values()):
        raise HTTPException(409, "本厂没有可清空的计划数据")
    # The complete before image is committed with the deletion by finish_write.
    # No mutation reaches machines' specifications or the shared master catalogs.
    for model, where in selections(factory):
        db.execute(
            delete(model).where(where).execution_options(synchronize_session=False)
        )
    for machine in machines:
        if machine.operating_status == "RUNNING":
            machine.operating_status = "IDLE"
        machine.current_setup = {}
        touch(machine, actor)
    db.flush()
    return {
        "cleared": True,
        "factory_id": factory,
        "counts": impact,
        "reason": reason,
        "source_preview_token": payload.preview_token,
        "audit_operation_id": payload.client_operation_id,
        "before": before,
        "shared_revision": db.get(SharedRevision, "shared").revision,
    }
