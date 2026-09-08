# FastAPI dependency factories are intentional argument defaults.
# ruff: noqa: B008
import hashlib
import json
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    HistoricalOutput,
    ImportBatch,
    ImportRow,
    Machine,
    MoldAsset,
    MoldMaster,
    Operation,
    Run,
    RunDemand,
    SavedView,
    ShiftReport,
)
from app.schemas.injection_scheduling import (
    BulkStart,
    BulkWrite,
    ExportQuery,
    FactoryId,
    GroupWrite,
    ImportApply,
    MoveWrite,
    PlanClearPreview,
    PlanClearWrite,
    Query,
    RecordWrite,
    RelocateWrite,
    ReportWrite,
    RunAction,
    ScheduleWrite,
    StartPreview,
    Write,
)
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import ensure_permission_for_departments
from app.services.injection_scheduling import (
    bulk_start,
    import_service,
    master_data,
    plan_clear,
    planning,
    production,
    queries,
    reports,
)
from app.services.injection_scheduling.calculations import now, timestamp
from app.services.injection_scheduling.common import (
    begin_write,
    check_revision,
    finish_write,
    jsonable,
    record,
    scoped,
    touch,
)
from app.services.injection_scheduling.enrichment import apply_demand_fields, enrich
from app.services.injection_scheduling.field_registry import FIELDS

router = APIRouter(prefix="/api/injection-scheduling", tags=["注塑排产"])


def authorize(db, user, factory, action="read"):
    ensure_permission_for_departments(
        db,
        user,
        f"injection_scheduling:{action}",
        factory,
        ("production", "molding", "management"),
    )


def write(db, user, payload, kind, callback, permission="plan"):
    authorize(db, user, payload.factory_id, permission)
    try:
        prior, context = begin_write(db, payload, user.id, kind)
        if prior is not None:
            return prior
        result = callback()
        before = result.pop("before", {})
        return finish_write(db, context, result, before)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "记录或操作发生冲突，已保留输入，请刷新后重新应用"
        ) from None
    except Exception:
        db.rollback()
        raise


@router.post("/execution/start-preview")
def preview_bulk_start(
    payload: StartPreview,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id, "report")
    return bulk_start.preview(db, payload.factory_id, payload.items)


@router.post("/execution/bulk-start")
def commit_bulk_start(
    payload: BulkStart,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db,
        user,
        payload,
        "bulk_start",
        lambda: bulk_start.start(db, payload, user.id),
        permission="report",
    )


@router.get("/field-registry")
def fields(
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return {
        "schema_version": "injection-v3-1",
        "fields": [s.public() for s in FIELDS.values()],
    }


@router.get("/summary")
def summary(
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return queries.summary(db, Query(factory_id=factory_id))


@router.post("/demands/query")
def query_demands(
    payload: Query,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id)
    instant = now()
    total = queries.summary(db, payload, instant)
    rows = [
        record(d)
        for d in db.scalars(
            queries.ordered_query(payload, instant)
            .offset(payload.cursor or 0)
            .limit(payload.page_size)
        )
    ]
    if any(k not in FIELDS for k in payload.columns):
        raise HTTPException(422, "未知列")
    next_offset = (payload.cursor or 0) + len(rows)
    return {
        "total_count": total["total_count"],
        "filtered_summary": total,
        "rows": rows,
        "next_cursor": next_offset if next_offset < total["total_count"] else None,
        **queries.revision(db, payload.factory_id),
    }


@router.post("/demands/locate")
def locate(
    payload: Query,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id)
    from sqlalchemy import func

    base = queries.ordered_query(payload).subquery()
    total = db.scalar(select(func.count()).select_from(base)) or 0
    index = (payload.cursor or 0) % total if total else 0
    row = db.scalar(queries.ordered_query(payload).offset(index).limit(1))
    return {
        "total_count": total,
        "position": index,
        "page_cursor": index // payload.page_size * payload.page_size,
        "demand_id": row.id if row else None,
        "matching_field": (payload.search or {}).get("field", "mold_code"),
        "row": record(row) if row else None,
    }


@router.get("/demands/{demand_id}")
def detail(
    demand_id: str,
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    demand = scoped(db, Demand, demand_id, factory_id)
    history = [
        record(h)
        for h in db.scalars(
            select(HistoricalOutput)
            .where(HistoricalOutput.demand_id == demand_id)
            .order_by(HistoricalOutput.production_date)
        )
    ]
    source = [
        record(r)
        for r in db.scalars(select(ImportRow).where(ImportRow.demand_id == demand_id))
    ]
    run_id = demand.extras.get("active_run_id")
    return {
        "demand": record(demand),
        "run": record(db.get(Run, run_id)) if run_id and db.get(Run, run_id) else None,
        "history": history,
        "reports": reports.list_reports(db, factory_id, demand_id=demand_id),
        "source_rows": source,
    }


def update_one(db, payload, actor, identity=None):
    obj = (
        scoped(db, Demand, identity, payload.factory_id)
        if identity
        else Demand(factory_id=payload.factory_id, mold_code="")
    )
    if identity:
        check_revision(obj, payload.record_revision)
        rid = obj.extras.get("active_run_id")
        run = db.get(Run, rid) if rid else None
        if (
            run
            and run.status in {"RUNNING", "PAUSED"}
            and set(payload.data)
            - {
                "order_note",
                "production_note",
                "delivery_due_at",
                "priority_level",
                "planned_shots",
                "adjustment_shots",
                "target_shots_per_day",
            }
        ):
            raise HTTPException(409, "在产工艺快照已固定；请先暂停转机或结束批次后修改")
    apply_demand_fields(db, obj, payload.data, actor, new=identity is None)
    if (
        identity
        and "target_shots_per_day" in payload.data
        and run
        and run.status in {"RUNNING", "PAUSED"}
    ):
        for link in db.scalars(
            select(RunDemand).where(
                RunDemand.run_id == run.id, RunDemand.demand_id != obj.id
            )
        ):
            sibling = db.get(Demand, link.demand_id)
            apply_demand_fields(
                db,
                sibling,
                {"target_shots_per_day": payload.data["target_shots_per_day"]},
                actor,
            )
    db.add(obj)
    db.flush()
    reports.reallocate_factory(db, payload.factory_id, demand_ids=[obj.id])
    impact = planning.recalculate(db, payload.factory_id, actor)
    return {"demand": record(obj), **impact}


@router.post("/demands")
def create_demand(
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db, user, payload, "demand.create", lambda: update_one(db, payload, user.id)
    )


@router.patch("/demands/{demand_id}")
def update_demand(
    demand_id: str,
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db,
        user,
        payload,
        "demand.update:" + demand_id,
        lambda: update_one(db, payload, user.id, demand_id),
    )


@router.post("/demands/bulk-update")
def bulk_demands(
    payload: BulkWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        selected = []
        for entry in payload.rows:
            obj = scoped(db, Demand, entry.get("id"), payload.factory_id)
            check_revision(obj, entry.get("revision"))
            rid = obj.extras.get("active_run_id")
            run = db.get(Run, rid) if rid else None
            if run and run.status in {"RUNNING", "PAUSED"}:
                raise HTTPException(409, "批量参数修改包含在产批次，请在详情中调整")
            apply_demand_fields(db, obj, entry.get("data", {}), user.id)
            selected.append(obj)
        db.flush()
        reports.reallocate_factory(
            db, payload.factory_id, demand_ids=[obj.id for obj in selected]
        )
        result = planning.recalculate(db, payload.factory_id, user.id)
        return {**result, "rows": [record(d) for d in selected]}

    return write(db, user, payload, "demand.bulk", apply)


@router.post("/demands/enrich")
def enrich_demands(
    payload: BulkWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        for entry in payload.rows:
            obj = scoped(db, Demand, entry.get("id"), payload.factory_id)
            if obj.extras.get("active_run_id"):
                run = db.get(Run, obj.extras["active_run_id"])
                if run and run.status in {"RUNNING", "PAUSED"}:
                    raise HTTPException(409, "不能对在产任务应用最新公共资料")
            enrich(db, obj, apply_latest=True)
            touch(obj, user.id)
        db.flush()
        reports.refresh_quantities(db, payload.factory_id)
        return planning.recalculate(db, payload.factory_id, user.id)

    return write(db, user, payload, "demand.enrich", apply)


@router.get("/settings")
def settings(
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    item = db.get(FactorySettings, factory_id)
    return {"parameters": item.parameters, **queries.revision(db, factory_id)}


@router.patch("/settings")
def patch_settings(
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        params = master_data.update_settings(db, payload.factory_id, payload.data)
        return {
            "parameters": params,
            **planning.recalculate(db, payload.factory_id, user.id),
        }

    return write(db, user, payload, "settings.update", apply, "master_write")


@router.get("/timeline")
def timeline(
    factory_id: FactoryId,
    from_at: str | None = None,
    to_at: str | None = None,
    include_finished: bool = False,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    query = select(Run).where(
        Run.factory_id == factory_id,
        Run.status.in_(
            ["PLANNED", "RUNNING", "PAUSED", "FINISHED", "TRANSFERRED"]
            if include_finished
            else ["PLANNED", "RUNNING", "PAUSED"]
        ),
    )
    if from_at:
        query = query.where(
            func.coalesce(Run.actual_end_at, Run.planned_end_at) > timestamp(from_at)
        )
    if to_at:
        query = query.where(
            func.coalesce(Run.actual_start_at, Run.setup_start_at) < timestamp(to_at)
        )
    rows = list(db.scalars(query.order_by(Run.sequence, Run.id)))
    machine_rows = list(
        db.scalars(
            select(Machine)
            .where(Machine.factory_id == factory_id)
            .order_by(Machine.workshop, Machine.code)
        )
    )
    machines_by_id = {machine.id: machine for machine in machine_rows}
    links = list(
        db.scalars(
            select(RunDemand)
            .where(
                RunDemand.factory_id == factory_id,
                RunDemand.run_id.in_([r.id for r in rows]),
            )
            .order_by(RunDemand.sequence)
        )
    )
    by_run = {}
    products = {}
    for link in links:
        by_run.setdefault(link.run_id, []).append(link.demand_id)
        products.setdefault(link.run_id, []).append(
            {
                "demand_id": link.demand_id,
                "product_code": link.product_code,
                "outputs_per_shot": jsonable(link.outputs_per_shot),
                "allocation_mode": link.allocation_mode,
            }
        )
    production_date, shift_code = reports.current_shift(
        now(), db.get(FactorySettings, factory_id).parameters
    )
    shift_totals = (
        dict(
            db.execute(
                select(ShiftReport.run_id, func.sum(ShiftReport.physical_shots))
                .where(
                    ShiftReport.factory_id == factory_id,
                    ShiftReport.production_date == production_date,
                    ShiftReport.shift_code == shift_code,
                    ShiftReport.run_id.in_([row.id for row in rows]),
                )
                .group_by(ShiftReport.run_id)
            ).all()
        )
        if rows
        else {}
    )
    return {
        "current_production_date": production_date.isoformat(),
        "current_shift_code": shift_code,
        "runs": [
            planning.public_run(
                {
                    **r.snapshot,
                    **record(r),
                    "demand_ids": by_run.get(r.id, []),
                    "products": products.get(r.id, []),
                    "current_shift_shots": jsonable(shift_totals.get(r.id)),
                    "remaining_shots": jsonable(
                        max(0, r.planned_physical_shots - r.physical_shots)
                    ),
                },
                forecast_unknown=bool(r.explanation.get("forecast_unknown"))
                or (
                    r.status == "PAUSED"
                    and not machines_by_id[r.machine_id].recovery_at
                ),
            )
            for r in rows
        ],
        "machines": [record(m) for m in machine_rows],
        "events": [
            record(e)
            for e in db.scalars(
                select(CalendarEvent).where(CalendarEvent.factory_id == factory_id)
            )
        ],
        **queries.revision(db, factory_id),
    }


@router.post("/schedule/auto")
def auto(
    payload: ScheduleWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    if not payload.save:
        authorize(db, user, payload.factory_id, "plan")
        return {
            **planning.auto_schedule(
                db, payload.factory_id, payload.scope.model_dump(), user.id, save=False
            ),
            **queries.revision(db, payload.factory_id),
        }

    def apply():
        as_of = now()
        snap = planning.snapshot(db, payload.factory_id, as_of)
        before = {
            "changed_runs": snap["runs"],
            "unplaced": [],
        }
        return {
            **planning.auto_schedule(
                db,
                payload.factory_id,
                payload.scope.model_dump(),
                user.id,
                as_of=as_of,
                snapshot_data=snap,
            ),
            "before": before,
        }

    return write(db, user, payload, "schedule.auto", apply)


@router.post("/schedule/move")
def move(
    payload: MoveWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        before = {
            "changed_runs": planning.snapshot(db, payload.factory_id)["runs"],
            "unplaced": [],
        }
        return {**planning.move(db, payload, user.id), "before": before}

    return write(db, user, payload, "schedule.move", apply)


@router.post("/schedule/recalculate")
def recalculate(
    payload: Write,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db,
        user,
        payload,
        "schedule.recalculate",
        lambda: planning.recalculate(db, payload.factory_id, user.id),
    )


@router.post("/schedule/group")
def group_runs(
    payload: GroupWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        before = {
            "changed_runs": planning.snapshot(db, payload.factory_id)["runs"],
            "unplaced": [],
        }
        return {**planning.group(db, payload, user.id), "before": before}

    return write(db, user, payload, "schedule.group", apply)


@router.post("/schedule/undo")
def undo(
    payload: Write,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        op = db.scalar(
            select(Operation).where(
                Operation.factory_id == payload.factory_id,
                Operation.revision == payload.base_revision,
            )
        )
        if (
            not op
            or op.kind not in {"schedule.auto", "schedule.move", "schedule.group"}
            or not op.before
        ):
            raise HTTPException(409, "最近变更包含报工或其他业务修改，不能撤销实际事实")
        planning.save_runs(db, payload.factory_id, op.before, user.id)
        return {**op.before, "undone_operation_id": op.id}

    return write(db, user, payload, "schedule.undo", apply)


@router.post("/runs/{run_id}/{verb}")
def run_action(
    run_id: str,
    verb: str,
    payload: RunAction,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db,
        user,
        payload,
        f"run.{verb}:{run_id}",
        lambda: production.action(
            db,
            payload.factory_id,
            run_id,
            verb,
            user.id,
            payload.reason,
            payload.target_machine_id,
        ),
        "report",
    )


@router.put("/shift-reports/{key}")
def save_report(
    key: str,
    payload: ReportWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        result = reports.save_report(db, payload, user.id)
        return {**result, **planning.recalculate(db, payload.factory_id, user.id)}

    return write(db, user, payload, "report.save", apply, "report")


@router.post("/shift-reports/bulk")
def bulk_reports(
    payload: BulkWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        results = []
        for index, row in enumerate(payload.rows):
            try:
                with db.begin_nested():
                    item = ReportWrite(
                        **{
                            **row,
                            "factory_id": payload.factory_id,
                            "base_revision": payload.base_revision,
                            "client_operation_id": f"{hashlib.sha256(payload.client_operation_id.encode()).hexdigest()}:{index}",
                        }
                    )
                    result = reports.save_report(db, item, user.id)
                    results.append({"index": index, "ok": True, **result})
            except (HTTPException, ValueError) as exc:
                results.append(
                    {
                        "index": index,
                        "ok": False,
                        "error": getattr(exc, "detail", str(exc)),
                    }
                )
        return {
            "results": results,
            **planning.recalculate(db, payload.factory_id, user.id),
        }

    return write(db, user, payload, "report.bulk", apply, "report")


@router.get("/shift-reports")
def get_reports(
    factory_id: FactoryId,
    run_id: str | None = None,
    demand_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return {
        "rows": reports.list_reports(
            db, factory_id, run_id, demand_id, from_date, to_date
        ),
        **queries.revision(db, factory_id),
    }


@router.post("/imports")
async def upload_plan(
    factory_id: FactoryId = Form(...),
    base_revision: int = Form(...),
    client_operation_id: str = Form(...),
    sheet_name: str = Form("计划表"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id, "plan")
    content = await file.read(40 * 1024 * 1024 + 1)
    if len(content) > 40 * 1024 * 1024:
        raise HTTPException(413, "工作簿超过 40 MB")
    payload = RecordWrite(
        factory_id=factory_id,
        base_revision=base_revision,
        client_operation_id=client_operation_id,
        data={"sha256": hashlib.sha256(content).hexdigest(), "sheet_name": sheet_name},
    )

    def apply():
        try:
            obj = import_service.preview(
                db,
                factory_id,
                content,
                Path(file.filename or "计划表.xlsx").name,
                sheet_name,
                user.id,
            )
        except (ValueError, KeyError, BadZipFile, ParseError) as exc:
            raise HTTPException(422, str(exc)) from None
        return {
            "batch_id": obj.id,
            "status": obj.status,
            "summary": obj.summary,
            "rows": [
                {
                    "source_row": r["source_row"],
                    "fields": r["fields"],
                    "issues": r["issues"],
                    "row_role": r["row_role"],
                }
                for r in obj.evidence["demands"]
            ],
        }

    return write(db, user, payload, "import.preview", apply)


@router.get("/imports/{batch_id}")
def get_import(
    batch_id: str,
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return record(scoped(db, ImportBatch, batch_id, factory_id))


@router.post("/imports/{batch_id}/apply")
def apply_import(
    batch_id: str,
    payload: ImportApply,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id, "plan")
    batch = scoped(db, ImportBatch, batch_id, payload.factory_id)
    if batch.evidence.get("exchange") and any(
        value != row.get("baseline", {}).get("shift_values", {}).get(key)
        for row in batch.evidence["demands"]
        for key, value in row["fields"].items()
        if "|" in key
    ):
        # Authorization happens before the transaction: denied access must not commit partial import work.
        authorize(db, user, payload.factory_id, "report")

    def apply():
        batch = scoped(db, ImportBatch, batch_id, payload.factory_id)
        result = import_service.apply_batch(
            db, batch, user.id, payload.matches, payload.skip_rows
        )
        if result.get("recalculate_required") and not result.get("already_applied"):
            result.update(
                planning.import_original_assignments(
                    db,
                    payload.factory_id,
                    batch.summary.get("original_assignments", []),
                    user.id,
                )
            )
        return result

    return write(db, user, payload, "import.apply:" + batch_id, apply)


@router.get("/changes")
def changes(
    factory_id: FactoryId,
    since_revision: int = 0,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    rev = queries.revision(db, factory_id)
    return {
        **rev,
        "changed": rev["revision"] != since_revision,
        "synced_at": now().isoformat(),
    }


@router.post("/plan-data/clear-preview")
def preview_plan_clear(
    payload: PlanClearPreview,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id, "plan")
    return plan_clear.preview(db, payload.factory_id)


@router.post("/plan-data/clear")
def clear_plan_data(
    payload: PlanClearWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    if payload.include_execution:
        authorize(db, user, payload.factory_id, "report")
    return write(
        db, user, payload, "plan.clear", lambda: plan_clear.clear(db, payload, user.id)
    )


@router.get("/views")
def views(
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return [
        record(v)
        for v in db.scalars(
            select(SavedView).where(
                SavedView.factory_id == factory_id, SavedView.user_id == user.id
            )
        )
    ]


@router.post("/views")
def save_view(
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        name = str(payload.data.get("name", "")).strip()
        if not name or len(name) > 100:
            raise HTTPException(422, "视图名称不能为空且不超过 100 字")
        validate_view(payload.data)
        obj = SavedView(
            factory_id=payload.factory_id,
            user_id=user.id,
            name=name,
            view_type=str(payload.data.get("view_type", "table")),
            config=payload.data.get("config", {}),
        )
        touch(obj, user.id)
        db.add(obj)
        db.flush()
        return {"view": record(obj)}

    return write(db, user, payload, "view.save", apply, "read")


def validate_view(data):
    if set(data) - {"name", "view_type", "config"}:
        raise HTTPException(422, "视图包含不支持的字段")
    if (
        not isinstance(data.get("config", {}), dict)
        or len(json.dumps(data.get("config", {}))) > 100000
    ):
        raise HTTPException(422, "视图配置必须为有限的对象")
    if data.get("view_type", "table") not in {
        "table",
        "timeline",
        "machines",
        "reports",
        "master",
    }:
        raise HTTPException(422, "视图类型不正确")


@router.patch("/views/{identity}")
def update_view(
    identity: str,
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    def apply():
        obj = scoped(db, SavedView, identity, payload.factory_id)
        if obj.user_id != user.id:
            raise HTTPException(404, "视图不存在")
        check_revision(obj, payload.record_revision)
        validate_view(payload.data)
        if "name" in payload.data:
            name = str(payload.data["name"]).strip()
            if not name or len(name) > 100:
                raise HTTPException(422, "视图名称不能为空且不超过100字")
            obj.name = name
        if "view_type" in payload.data:
            obj.view_type = payload.data["view_type"]
        if "config" in payload.data:
            obj.config = payload.data["config"]
        touch(obj, user.id)
        db.flush()
        return {"view": record(obj)}

    return write(db, user, payload, "view.update:" + identity, apply, "read")


@router.get("/operations")
def operations(
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    return [
        {
            "id": o.id,
            "kind": o.kind,
            "actor_id": o.actor_id,
            "at": jsonable(o.occurred_at),
            "revision": o.revision,
        }
        for o in db.scalars(
            select(Operation)
            .where(Operation.factory_id == factory_id)
            .order_by(Operation.revision.desc())
            .limit(100)
        )
    ]


@router.post("/exports/plan")
def export(
    payload: ExportQuery,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id)
    from urllib.parse import quote

    from app.services.injection_scheduling.export_plan import export_plan

    try:
        content, name = export_plan(db, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.post("/machines/{machine_id}/status")
def status(
    machine_id: str,
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    return write(
        db,
        user,
        payload,
        "machine.status:" + machine_id,
        lambda: production.machine_status(
            db, payload.factory_id, machine_id, payload.data, user.id
        ),
        "master_write",
    )


@router.post("/mold-assets/{identity}/relocate")
def relocate_asset(
    identity: str,
    payload: RelocateWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, payload.factory_id, "master_write")
    authorize(db, user, payload.destination_factory_id, "master_write")
    return write(
        db,
        user,
        payload,
        "asset.relocate:" + identity,
        lambda: production.relocate_asset(
            db,
            payload.factory_id,
            identity,
            payload.destination_factory_id,
            payload.model_dump(),
            user.id,
            payload.record_revision,
        ),
        "master_write",
    )


# Literal routes above intentionally precede these four whitelisted resources.
RESOURCE_MODELS = {
    "molds": MoldMaster,
    "machines": Machine,
    "mold-assets": MoldAsset,
    "calendar-events": CalendarEvent,
}


@router.get("/{resource}")
def get_resources(
    resource: str,
    factory_id: FactoryId,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    authorize(db, user, factory_id)
    model = RESOURCE_MODELS.get(resource)
    if model is None:
        raise HTTPException(404, "资源不存在")
    query = select(model)
    if model is MoldAsset:
        query = query.where(MoldAsset.current_factory_id == factory_id)
    elif model is not MoldMaster:
        query = query.where(model.factory_id == factory_id)
    return {
        "rows": [record(o) for o in db.scalars(query)],
        **queries.revision(db, factory_id),
    }


@router.post("/{resource}")
def create_resource(
    resource: str,
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    if resource not in RESOURCE_MODELS:
        raise HTTPException(404, "资源不存在")

    def apply():
        obj = master_data.write_master(
            db, resource, payload.factory_id, payload.data, user.id
        )
        return {
            "record": record(obj),
            **planning.recalculate(db, payload.factory_id, user.id),
        }

    return write(db, user, payload, resource + ".create", apply, "master_write")


@router.patch("/{resource}/{identity}")
def patch_resource(
    resource: str,
    identity: str,
    payload: RecordWrite,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    if resource not in RESOURCE_MODELS:
        raise HTTPException(404, "资源不存在")

    def apply():
        obj = master_data.write_master(
            db,
            resource,
            payload.factory_id,
            payload.data,
            user.id,
            identity,
            payload.record_revision,
        )
        return {
            "record": record(obj),
            **planning.recalculate(db, payload.factory_id, user.id),
        }

    return write(
        db, user, payload, resource + ".update:" + identity, apply, "master_write"
    )
