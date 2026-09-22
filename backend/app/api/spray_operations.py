"""Strict authority and projection for the rebuilt four-factory spray domain."""
from datetime import datetime, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.config import settings
from app.db import get_db
from app.models import spray_ops as m
from app.services.auth import AuthContext, get_current_user, authorization_decision
from app.services.spray_ops import common as c, schemas as s, production as p, scheduling
from app.services.spray_ops import handover, materials, finance, history
from app.services.spray_ops import imports as ingest
from app.services.spray_ops import exports
from app.services.spray_ops.query_filters import related_order
from app.services.spray_ops.source_reader import PROFILES, read_source, MAX_FILE


class SprayRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except c.DomainError as error:
                return JSONResponse(error.body, status_code=error.status)
            except (RequestValidationError, ValidationError) as error:
                fields = {".".join(str(x) for x in item["loc"]): item["msg"] for item in error.errors()}
                return JSONResponse(dict(code="validation_error", message="请检查输入字段", field_errors=fields, conflicts=[], retryable=False), status_code=422)
            except HTTPException as error:
                return JSONResponse(dict(code="unauthorized" if error.status_code == 401 else "request_failed", message=str(error.detail), field_errors={}, conflicts=[], retryable=False), status_code=error.status_code)
        return handler


router = APIRouter(prefix="/api/spray-operations", tags=["spray-operations"], route_class=SprayRoute)
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def allowed(user, factory, action):
    return authorization_decision(user, "spray_ops:" + action, factory, "production")[0]


def authorize(user, factory, *actions):
    c.require(factory in m.FACTORIES, "factory_required", "请选择华兴、华登、华康A或华康B的明确工厂", 422)
    for action in {"read", *actions}:
        c.require(allowed(user, factory, action), "permission_denied", "没有当前工厂喷油模块的相应权限", 403)
    c.require(settings.spray_ops_enabled, "module_disabled", "喷油部生产管理尚未启用", 503)


def envelope(db, user, f, data, *, pagination=None, warnings=None, coverage=None):
    gate = db.get(m.SprayOpsFactory, f)
    c.require(gate is not None, "schema_not_ready", "喷油模块尚未迁移", 503)
    meta = dict(factory_id=f, as_of=datetime.now(UTC).isoformat(), factory_revision=gate.revision, data_mode="live", warnings=warnings or [])
    if coverage:
        meta["coverage"] = coverage
    result = dict(meta=meta, data=c.project(c.json_value(data), cost=allowed(user, f, "cost_read"), payroll=allowed(user, f, "payroll_read")))
    if pagination:
        result["pagination"] = pagination
    return result


def execute(db, user, body, action, permissions, handler, *, changes_revision=True, check_month=True):
    authorize(user, body.factory_id, *permissions)
    result = c.command(db, user, action, body, ("read", *permissions), handler, changes_revision=changes_revision, check_month=check_month)
    return envelope(db, user, body.factory_id, result)


@router.get("/access")
def access(db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id)
    from app.services.permission_codes import SPRAY_OPS_PERMISSION_CODES
    return envelope(db, user, factory_id, dict(permissions=[code.split(":")[1] for code in SPRAY_OPS_PERMISSION_CODES if allowed(user, factory_id, code.split(":")[1])], authorization_version=user.authorization_version))


@router.get("/commands/{operation_id}")
def receipt(operation_id: str, db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id)
    item = db.scalar(c.scoped(db, m.SprayOpsReceipt, factory_id).where(m.SprayOpsReceipt.operation_id == operation_id, m.SprayOpsReceipt.actor_id == user.id))
    c.require(item is not None, "not_found", "尚未找到本人的操作回执", 404)
    authorize(user, factory_id, *item.required_permissions)
    return envelope(db, user, factory_id, item.result)


@router.get("/overview")
def overview(db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id)
    counts = {}
    for name, model, predicate in [
        ("demands", m.SprayOpsDemand, m.SprayOpsDemand.status.in_(["confirmed", "in_progress"])),
        ("planned", m.SprayOpsTask, m.SprayOpsTask.status == "planned"),
        ("started", m.SprayOpsTask, m.SprayOpsTask.status == "started"),
        ("quality_batches", m.SprayOpsStock, (m.SprayOpsStock.state == "hold") & (m.SprayOpsStock.quantity > 0)),
        ("unmatched_batches", m.SprayOpsBatch, m.SprayOpsBatch.line_id.is_(None)),
    ]:
        counts[name] = db.scalar(select(func.count()).select_from(model).where(model.factory_id == factory_id, predicate))
    balances = db.execute(select(m.SprayOpsStock.state, m.SprayOpsStock.unit, func.sum(m.SprayOpsStock.quantity)).where(m.SprayOpsStock.factory_id == factory_id).group_by(m.SprayOpsStock.state, m.SprayOpsStock.unit)).all()
    return envelope(db, user, factory_id, dict(counts=counts, stock=[dict(state=state, unit=unit, quantity=str(qty)) for state, unit, qty in balances]))


@router.get("/schedule/window")
def timeline(db: Db, user: User, start_at: s.Instant, end_at: s.Instant, factory_id: str = "", page: int = Query(1, ge=1), page_size: int = Query(200, ge=1, le=200), demand_id: str = ""):
    authorize(user, factory_id)
    c.require(end_at > start_at and (end_at - start_at).days <= 31, "planning_window", "请查询最多 31 天的有效排期窗口", 422)
    stmt = c.scoped(db, m.SprayOpsTask, factory_id).where(m.SprayOpsTask.start_at < c.timestamp(end_at), m.SprayOpsTask.end_at > c.timestamp(start_at), m.SprayOpsTask.status != "cancelled")
    stmt = related_order(db, factory_id, demand_id, "tasks", stmt)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    tasks = list(db.scalars(stmt.order_by(m.SprayOpsTask.start_at, m.SprayOpsTask.id).offset((page - 1) * page_size).limit(page_size)))
    return envelope(db, user, factory_id, [p.task_detail(db, factory_id, task) for task in tasks], pagination=dict(page=page, page_size=page_size, total=total))


@router.post("/resources")
def resource_create(body: s.ResourceCreate, db: Db, user: User):
    return execute(db, user, body, "resource.create", ("master_write",), lambda _: p.create_resource(db, body.factory_id, body))


@router.post("/resources/{entity_id}/calendar")
def resource_calendar(entity_id: str, body: s.CalendarSet, db: Db, user: User):
    return execute(db, user, body, "resource.calendar:" + entity_id, ("master_write",), lambda _: p.set_calendar(db, body.factory_id, entity_id, body))


@router.post("/routes")
def route_create(body: s.RouteCreate, db: Db, user: User):
    return execute(db, user, body, "route.create", ("master_write",), lambda _: p.create_route(db, body.factory_id, body))


@router.post("/employees")
def employee_create(body: s.EmployeeCreate, db: Db, user: User):
    def create(_):
        c.require(body.expected_version == 0, "version_conflict", "新员工版本应为 0")
        return c.serialize(c.add(db, m.SprayOpsEmployee, body.factory_id, code=body.code, name=body.name))
    return execute(db, user, body, "employee.create", ("master_write",), create)


@router.post("/demands")
def demand_create(body: s.DemandCreate, db: Db, user: User):
    permissions = ("plan", "cost_write") if any(line.commercial_price is not None for line in body.lines) else ("plan",)
    return execute(db, user, body, "demand.create", permissions, lambda _: p.create_demand(db, body.factory_id, body))


@router.post("/demands/{entity_id}/amend")
def demand_amend(entity_id: str, body: s.DemandAmend, db: Db, user: User):
    return execute(db, user, body, "demand.amend:" + entity_id, ("plan",), lambda _: p.amend_demand(db, body.factory_id, entity_id, body))


@router.post("/batches")
def batch_create(body: s.BatchCreate, db: Db, user: User):
    return execute(db, user, body, "batch.create", ("stock_write",), lambda _: p.create_batch(db, body.factory_id, body))


@router.post("/batches/{entity_id}/match")
def batch_match(entity_id: str, body: s.BatchMatch, db: Db, user: User):
    return execute(db, user, body, "batch.match:" + entity_id, ("stock_write",), lambda _: p.match_batch(db, body.factory_id, entity_id, body))


@router.post("/preparations")
def preparation(body: s.PreparationSet, db: Db, user: User):
    return execute(db, user, body, "preparation.set", ("plan",), lambda _: p.prepare(db, body.factory_id, body))


@router.post("/scenarios/preview")
def plan_preview(body: s.PlanPreview, db: Db, user: User):
    return execute(db, user, body, "scenario.preview", ("plan",), lambda gate: scheduling.preview(db, body.factory_id, body, gate), changes_revision=False)


@router.post("/scenarios/{entity_id}/publish")
def plan_publish(entity_id: str, body: s.PlanPublish, db: Db, user: User):
    return execute(db, user, body, "scenario.publish:" + entity_id, ("plan",), lambda gate: scheduling.publish(db, body.factory_id, entity_id, body, gate))


@router.post("/tasks/{entity_id}/start")
def task_start(entity_id: str, body: s.TaskStart, db: Db, user: User):
    return execute(db, user, body, "task.start:" + entity_id, ("report",), lambda _: p.start_task(db, body.factory_id, entity_id, body))


@router.post("/reports")
def report_create(body: s.ReportCreate, db: Db, user: User):
    return execute(db, user, body, "report.create", ("report",), lambda _: p.create_report(db, body.factory_id, body))


@router.post("/reports/{entity_id}/confirm")
def report_confirm(entity_id: str, body: s.Command, db: Db, user: User):
    return execute(db, user, body, "report.confirm:" + entity_id, ("report",), lambda _: p.confirm_report(db, body.factory_id, entity_id, body.expected_version))


@router.post("/reports/{entity_id}/reverse")
def report_reverse(entity_id: str, body: s.ReasonCommand, db: Db, user: User):
    return execute(db, user, body, "report.reverse:" + entity_id, ("report",), lambda _: p.reverse_report(db, body.factory_id, entity_id, body))


@router.post("/stock/{entity_id}/quality")
def quality_disposition(entity_id: str, body: s.QualityDisposition, db: Db, user: User):
    return execute(db, user, body, "quality.disposition:" + entity_id, ("quality",), lambda _: p.quality(db, body.factory_id, entity_id, body))


def register_command(path, schema, action, permissions, handler, *, changes_revision=True, check_month=True):
    """Register an explicit typed endpoint; action names are never client-selected."""
    def endpoint(body, db: Db, user: User, entity_id: str = ""):
        required = permissions(body, db, user, entity_id) if callable(permissions) else permissions
        return execute(db, user, body, action + (":" + entity_id if entity_id else ""), required,
                       lambda gate: handler(db, body.factory_id, body, entity_id, user, gate),
                       changes_revision=changes_revision, check_month=check_month)
    endpoint.__annotations__["body"] = schema
    endpoint.__name__ = action.replace(".", "_")
    router.add_api_route(path, endpoint, methods=["POST"])


register_command("/deliveries", s.DeliveryCreate, "delivery.create", ("stock_write",), lambda db, f, b, *_: handover.create_delivery(db, f, b))
register_command("/demands/{entity_id}/confirm", s.Command, "demand.confirm", ("plan",), lambda db, f, b, eid, *_: p.confirm_demand(db, f, eid, b))
register_command("/forecasts", s.ForecastCreate, "forecast.create", ("plan",), lambda db, f, b, *_: scheduling.create_forecast(db, f, b))
register_command("/history-policy", s.HistoryPolicy, "history.policy", ("import", "stock_write"), lambda db,f,b,*_: history.create_policy(db,f,b))
register_command("/openings", s.OpeningCreate, "opening.create", ("import", "stock_write"), lambda db,f,b,*_: history.create_opening(db,f,b))
register_command("/forecasts/{entity_id}/convert", s.ForecastConvert, "forecast.convert", ("plan",), lambda db, f, b, eid, user, gate: scheduling.convert_forecast(db, f, eid, b, gate))
register_command("/forecasts/{entity_id}/cancel", s.ReasonCommand, "forecast.cancel", ("plan",), lambda db, f, b, eid, *_: scheduling.cancel_forecast(db, f, eid, b))
register_command("/tasks/{entity_id}/pause", s.ReasonCommand, "task.pause", ("report",), lambda db, f, b, eid, *_: p.task_pause(db, f, eid, b))
register_command("/tasks/{entity_id}/resume", s.ReasonCommand, "task.resume", ("report",), lambda db, f, b, eid, *_: p.task_pause(db, f, eid, b, resume=True))
register_command("/reports/{entity_id}/labor", s.ReportLabor, "report.labor", ("report",), lambda db, f, b, eid, *_: p.set_report_labor(db, f, eid, b))
register_command("/reports/{entity_id}/amend", s.ReportAmend, "report.amend", ("report",), lambda db, f, b, eid, *_: p.amend_report(db, f, eid, b))
register_command("/imports/{entity_id}/cancel", s.ReasonCommand, "import.cancel", lambda b, db, user, eid: ingest.source_permissions(c.get(db, m.SprayOpsSource, b.factory_id, c.get(db, m.SprayOpsImport, b.factory_id, eid).source_id)), lambda db, f, b, eid, *_: ingest.cancel(db, f, eid, b), changes_revision=False)
register_command("/deliveries/{entity_id}/dispatch", s.Command, "delivery.dispatch", ("stock_write",), lambda db, f, b, eid, *_: handover.dispatch(db, f, eid, b.expected_version))
register_command("/deliveries/{entity_id}/accept", s.DeliveryAccept, "delivery.accept", ("stock_write",), lambda db, f, b, eid, *_: handover.accept(db, f, eid, b))
register_command("/returns", s.ReturnCreate, "return.create", ("stock_write",), lambda db, f, b, *_: handover.return_goods(db, f, b))
register_command("/containers", s.ContainerCreate, "container.create", ("stock_write",), lambda db, f, b, *_: handover.container(db, f, b))
register_command("/materials", s.MaterialCreate, "material.create", ("master_write",), lambda db, f, b, *_: c.serialize(c.add(db, m.SprayOpsMaterial, f, code=b.code, name=b.name, unit=b.unit)))
register_command("/purchases", s.PurchaseCreate, "purchase.create", ("procure", "cost_write"), lambda db, f, b, *_: materials.create_purchase(db, f, b))
register_command("/purchases/{entity_id}/cancel", s.PurchaseCancel, "purchase.cancel", ("procure",), lambda db, f, b, eid, *_: materials.cancel_purchase(db, f, eid, b))
register_command("/material-receipts", s.MaterialReceiptCreate, "material.receive", ("procure", "stock_write"), lambda db, f, b, *_: materials.receipt(db, f, b))
register_command("/material-lots/{entity_id}/move", s.MaterialMove, "material.move", ("stock_write",), lambda db, f, b, eid, *_: materials.move(db, f, eid, b))
register_command("/savings", s.SavingCreate, "saving.create", ("cost_write",), lambda db, f, b, *_: materials.saving(db, f, b))


def rule_permissions(body, db, user, entity_id):
    # Authorize the factory before looking up a rule's domain-specific permission.
    authorize(user, body.factory_id)
    kind = body.kind if isinstance(body, s.RuleCreate) else c.get(db, m.SprayOpsRule, body.factory_id, entity_id).kind
    return ("payroll_write",) if kind == "wage" else ("cost_write",)


register_command("/rules", s.RuleCreate, "rule.create", rule_permissions, lambda db, f, b, *_: finance.create_rule(db, f, b))
register_command("/rules/{entity_id}/confirm", s.ReasonCommand, "rule.confirm", rule_permissions, lambda db, f, b, eid, user, _: finance.confirm_rule(db, f, eid, b, user.id))
register_command("/payroll/trial", s.PayrollTrial, "payroll.trial", ("payroll_write", "payroll_read"), lambda db, f, b, *_: finance.payroll_trial(db, f, b))
register_command("/payroll/{entity_id}/confirm", s.Command, "payroll.confirm", ("payroll_write", "payroll_read"), lambda db, f, b, eid, *_: finance.confirm_payroll(db, f, eid, b.expected_version))
register_command("/expenses", s.ExpenseCreate, "expense.create", ("cost_write",), lambda db, f, b, *_: finance.expense(db, f, b))
register_command("/expenses/{entity_id}/confirm", s.ExpenseConfirm, "expense.confirm", ("cost_write",), lambda db, f, b, eid, *_: finance.confirm_expense(db, f, eid, b))
register_command("/material-lots/{entity_id}/cost", s.MaterialCostConfirm, "material.cost", ("cost_write", "cost_read"), lambda db, f, b, eid, *_: materials.confirm_original_cost(db, f, eid, b))
register_command("/valuations", s.ValueReport, "valuation.create", ("cost_write",), lambda db, f, b, *_: finance.value_report(db, f, b))
register_command("/settlements", s.SettlementCreate, "settlement.create", ("settle", "cost_read"), lambda db, f, b, *_: finance.create_settlement(db, f, b))
register_command("/credits", s.CreditCreate, "credit.create", ("settle", "cost_read"), lambda db, f, b, *_: finance.credit(db, f, b))
register_command("/delivery-lines/{entity_id}/price", s.PriceSet, "delivery.price", ("cost_write",), lambda db, f, b, eid, *_: finance.set_price(db, f, eid, b))
register_command("/periods/close", s.PeriodChange, "period.close", ("settle", "cost_read", "payroll_read"), lambda db, f, b, *_: finance.close_period(db, f, b))
register_command("/periods/{entity_id}/reopen", s.ReasonCommand, "period.reopen", ("settle", "cost_read", "payroll_read"), lambda db, f, b, eid, *_: finance.reopen_period(db, f, eid, b), check_month=False)


@router.get("/finance/economics")
def economics(db: Db, user: User, month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), currency: str = Query("CNY", pattern="^(CNY|HKD|USD)$"), factory_id: str = ""):
    authorize(user, factory_id, "cost_read")
    result = finance.economics(db, factory_id, month, currency)
    if not allowed(user, factory_id, "payroll_read"):
        result["surplus"] = None
        result["is_partial"] = True
    return envelope(db, user, factory_id, result, coverage=result["coverage"])


@router.get("/periods/preview")
def period_preview(db: Db, user: User, month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), factory_id: str = ""):
    authorize(user, factory_id, "settle", "cost_read", "payroll_read")
    result = finance.close_preview(db, factory_id, month)
    result.pop("snapshot")
    return envelope(db, user, factory_id, result)


@router.post("/exports")
def export_create(body: s.ExportCreate, db: Db, user: User):
    permissions = exports.permissions(body.kind)
    authorize(user, body.factory_id, *permissions)
    snapshot = exports.prepare(db, body.factory_id, body, cost=allowed(user, body.factory_id, "cost_read"), payroll=allowed(user, body.factory_id, "payroll_read"))
    payload = exports.render(snapshot)
    return execute(db, user, body, "export.create", permissions, lambda gate: exports.freeze(db, body.factory_id, body, snapshot, payload, gate), changes_revision=False)


@router.get("/exports/{entity_id}/download")
def export_download(entity_id: str, db: Db, user: User, factory_id: str = ""):
    from urllib.parse import quote
    authorize(user, factory_id, "export")
    artifact = c.get(db, m.SprayOpsExport, factory_id, entity_id)
    authorize(user, factory_id, *artifact.required_permissions)
    return Response(artifact.payload, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(artifact.name), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/import-profiles")
def import_profiles(db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id, "import")
    return envelope(db, user, factory_id, [dict(id=key, **value) for key, value in PROFILES.items()])


@router.post("/imports/upload")
async def import_upload(db: Db, user: User, file: Annotated[UploadFile, File()], options: Annotated[str, Form(max_length=10000)]):
    from pathlib import PureWindowsPath
    body = s.ImportUpload.model_validate_json(options)
    authorize(user, body.factory_id, "import", "cost_read")
    c.require(body.profile in PROFILES, "import_profile", "请选择支持的导入配置", 422)
    if PROFILES[body.profile]["payroll"]:
        authorize(user, body.factory_id, "payroll_read")
    raw = await file.read(MAX_FILE + 1)
    parsed = read_source(raw)
    name = PureWindowsPath(file.filename or "source").name[:200]
    body = body.model_copy(update={"source_sha256": parsed["sha256"], "filename": name})
    permissions = ("import", "cost_read") + (("payroll_read",) if PROFILES[body.profile]["payroll"] else ())
    return execute(db, user, body, "import.upload", permissions, lambda _: ingest.upload(db, body.factory_id, body, name, raw, parsed), changes_revision=False)


@router.get("/sources/{entity_id}")
def source_read(entity_id: str, db: Db, user: User, factory_id: str = "", sheet: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    authorize(user, factory_id, "import")
    source = c.get(db, m.SprayOpsSource, factory_id, entity_id)
    authorize(user, factory_id, *ingest.source_permissions(source))
    parsed = read_source(source.payload)
    data = ingest.source_view(source, parsed, sheet, page, page_size)
    return envelope(db, user, factory_id, data, pagination=dict(page=page, page_size=page_size, total=data["total"]))


@router.get("/sources/{entity_id}/download")
def source_download(entity_id: str, db: Db, user: User, factory_id: str = ""):
    from urllib.parse import quote
    authorize(user, factory_id, "import")
    source = c.get(db, m.SprayOpsSource, factory_id, entity_id)
    authorize(user, factory_id, *ingest.source_permissions(source))
    return Response(source.payload, media_type="application/pdf" if source.format == "PDF" else "application/octet-stream", headers={"Content-Disposition": "inline; filename*=UTF-8''" + quote(source.name), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/imports/preview")
def import_preview(body: s.ImportPreview, db: Db, user: User):
    authorize(user, body.factory_id, "import")
    source = c.get(db, m.SprayOpsSource, body.factory_id, body.source_id)
    permissions = ingest.source_permissions(source)
    authorize(user, body.factory_id, *permissions)
    parsed = read_source(source.payload)  # parsing finishes before obtaining a write lock
    return execute(db, user, body, "import.preview", permissions, lambda _: ingest.preview(db, body.factory_id, body, parsed), changes_revision=False)


@router.post("/imports/{entity_id}/confirm")
def import_confirm(entity_id: str, body: s.ImportConfirm, db: Db, user: User):
    authorize(user, body.factory_id, "import")
    permissions = ingest.confirmation_permissions(db, body.factory_id, entity_id, body)
    return execute(db, user, body, "import.confirm:" + entity_id, permissions, lambda _: ingest.confirm(db, body.factory_id, entity_id, body))


@router.get("/imports")
def import_list(db: Db, user: User, factory_id: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    authorize(user, factory_id, "import", "cost_read")
    stmt = c.scoped(db, m.SprayOpsImport, factory_id).join(m.SprayOpsSource, (m.SprayOpsSource.id == m.SprayOpsImport.source_id) & (m.SprayOpsSource.factory_id == m.SprayOpsImport.factory_id))
    if not allowed(user, factory_id, "payroll_read"):
        stmt = stmt.where(m.SprayOpsSource.payroll_sensitive.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(m.SprayOpsImport.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    # List metadata only; raw evidence is guarded by the detail endpoint below.
    return envelope(db, user, factory_id, [{k: v for k, v in c.serialize(item).items() if k != "snapshot"} for item in items], pagination=dict(page=page, page_size=page_size, total=total))


@router.get("/imports/{entity_id}")
def import_detail(entity_id: str, db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id, "import")
    job = c.get(db, m.SprayOpsImport, factory_id, entity_id)
    source = c.get(db, m.SprayOpsSource, factory_id, job.source_id)
    authorize(user, factory_id, *ingest.source_permissions(source))
    return envelope(db, user, factory_id, ingest.detail(db, factory_id, job))


COLLECTION_PERMISSIONS = {
    "payroll": ("payroll_read",), "expenses": ("cost_read",), "valuations": ("cost_read",),
    "settlements": ("settle", "cost_read"), "settlement-lines": ("settle", "cost_read"),
    "credits": ("settle", "cost_read"), "periods": ("settle", "cost_read", "payroll_read"),
    "savings": ("cost_read",),
}


COLLECTIONS = {
    "history-policy": (m.SprayOpsHistoryPolicy, None), "openings": (m.SprayOpsOpening, None),
    "forecasts": (m.SprayOpsForecast, None),
    "resources": (m.SprayOpsResource, p.resource_detail), "routes": (m.SprayOpsRoute, p.route_detail),
    "demands": (m.SprayOpsDemand, p.demand_detail), "demand-lines": (m.SprayOpsDemandLine, None),
    "batches": (m.SprayOpsBatch, None), "stock": (m.SprayOpsStock, None),
    "preparations": (m.SprayOpsPreparation, None), "tasks": (m.SprayOpsTask, p.task_detail),
    "reports": (m.SprayOpsReport, p.report_detail), "scenarios": (m.SprayOpsScenario, None),
    "employees": (m.SprayOpsEmployee, None), "activity": (m.SprayOpsAudit, None),
    "movements": (m.SprayOpsMovement, None),
    "deliveries": (m.SprayOpsDelivery, handover.delivery_detail), "delivery-lines": (m.SprayOpsDeliveryLine, None),
    "returns": (m.SprayOpsReturn, None), "containers": (m.SprayOpsContainer, None),
    "materials": (m.SprayOpsMaterial, None), "purchases": (m.SprayOpsPurchase, materials.purchase_detail),
    "purchase-lines": (m.SprayOpsPurchaseLine, None), "material-receipts": (m.SprayOpsMaterialReceipt, None),
    "material-lots": (m.SprayOpsMaterialLot, None), "material-movements": (m.SprayOpsMaterialMovement, None),
    "savings": (m.SprayOpsSaving, None), "rules": (m.SprayOpsRule, None),
    "payroll": (m.SprayOpsPayroll, finance.payroll_detail), "expenses": (m.SprayOpsExpense, None),
    "valuations": (m.SprayOpsValuation, None), "settlements": (m.SprayOpsSettlement, finance.settlement_detail),
    "settlement-lines": (m.SprayOpsSettlementLine, None), "credits": (m.SprayOpsCredit, None),
    "periods": (m.SprayOpsPeriod, None),
}


@router.get("/{collection}")
def list_collection(collection: str, db: Db, user: User, factory_id: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), search: str = Query("", max_length=128), status: str = "", from_date: str = "", to_date: str = "", demand_id: str = ""):
    authorize(user, factory_id, *COLLECTION_PERMISSIONS.get(collection, ()))
    c.require(collection in COLLECTIONS, "not_found", "工作区不存在", 404)
    model, detail = COLLECTIONS[collection]
    stmt = c.scoped(db, model, factory_id)
    stmt = related_order(db, factory_id, demand_id, collection, stmt)
    if search:
        fields = [getattr(model, key) for key in ("document_no", "code", "item_no", "name", "label") if hasattr(model, key)]
        if fields:
            from sqlalchemy import or_
            stmt = stmt.where(or_(*(field.contains(search, autoescape=True) for field in fields)))
    if status and hasattr(model, "status"):
        stmt = stmt.where(model.status == status)
    if hasattr(model, "business_date"):
        if from_date:
            stmt = stmt.where(model.business_date >= from_date)
        if to_date:
            stmt = stmt.where(model.business_date <= to_date)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = list(db.scalars(stmt.order_by(model.created_at.desc(), model.id).offset((page - 1) * page_size).limit(page_size)))
    data = [detail(db, factory_id, item) if detail else c.serialize(item) for item in items]
    return envelope(db, user, factory_id, data, pagination=dict(page=page, page_size=page_size, total=total))


@router.get("/{collection}/{entity_id}")
def get_entity(collection: str, entity_id: str, db: Db, user: User, factory_id: str = ""):
    authorize(user, factory_id, *COLLECTION_PERMISSIONS.get(collection, ()))
    c.require(collection in COLLECTIONS, "not_found", "工作区不存在", 404)
    model, detail = COLLECTIONS[collection]
    item = c.get(db, model, factory_id, entity_id)
    result = detail(db, factory_id, item) if detail else c.serialize(item)
    if collection == "demands":
        result['journey'] = p.demand_journey(db, factory_id, item.id)
    return envelope(db, user, factory_id, result)
