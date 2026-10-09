"""Canonical user API; strict decisions apply in every platform rollout mode."""
from app.services.uv_operations import corrections, execution
from typing import Annotated
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, DataError
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.config import settings
from app.models import uv_operations as m
from app.schemas import uv_operations as s
from app.services.auth import AuthContext, get_current_user
from app.services.permission_codes import UV_OPS_PERMISSION_CODES
from app.services.uv_operations import common as c, authz as a, production as p, planning, inventory, payroll, reports, files, ingest, live, imports, exports, runtime


class UvRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handle(request: Request):
            try:
                return await original(request)
            except c.DomainError as error:
                return JSONResponse(error.body, status_code=error.status)
            except (RequestValidationError, ValidationError) as error:
                # Never echo the rejected input, which can contain a price/token.
                return JSONResponse(dict(code="validation_error", message="请检查输入字段", field_errors={".".join(map(str, x["loc"])): x["msg"] for x in error.errors()}, retryable=False), status_code=422)
            except HTTPException as error:
                return JSONResponse(dict(code="unauthorized" if error.status_code == 401 else "request_failed", message=str(error.detail), retryable=False), status_code=error.status_code)
            except OperationalError:
                return JSONResponse(dict(code="schema_or_database_unavailable", message="UV 数据库暂不可用，请确认迁移和服务状态", retryable=True), status_code=503)
            except (ValueError,DataError):
                return JSONResponse(dict(code='invalid_value',message='日期、数值范围或字段格式不符合约定',retryable=False),status_code=422)
        return handle


router = APIRouter(prefix="/api/uv-operations", tags=["uv-operations"], route_class=UvRoute)
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def gate(db, user, factory, *permissions):
    a.authorize(user, factory, *permissions)
    a.ready(db)


def execute(db, user, body, action, permissions, handler):
    gate(db, user, body.factory_id, *permissions)
    return a.envelope(db, user, c.command(db, user, action, body, permissions, handler))


def register(path, schema, permissions, handler, *, method="POST"):
    if "{entity_id}" in path:
        def endpoint(entity_id: str, body: schema, db: Db, user: User):
            return execute(db, user, body, method+":"+path+":"+entity_id, permissions(body) if callable(permissions) else permissions, lambda: handler(db, user, entity_id, body))
    else:
        def endpoint(body: schema, db: Db, user: User):
            return execute(db, user, body, method+":"+path, permissions, lambda: handler(db, user, body))
    endpoint.__name__ = "uv_"+method.lower()+path.replace("/", "_").replace("{", "").replace("}", "").replace("-", "_")
    router.add_api_route(path, endpoint, methods=[method])


@router.get("/access")
def access(db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    return a.envelope(db, user, dict(permissions=[code.split(":")[1] for code in UV_OPS_PERMISSION_CODES if a.allowed(user, code.split(":")[1])], dispatch_supported=False))


@router.get("/workspace")
def workspace(db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    return live.response(db,user)


@router.get("/live")
async def stream(request: Request, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    db.rollback()
    return StreamingResponse(live.events(request, factory_id), media_type="text/event-stream", headers={"Cache-Control":"no-cache, no-store", "X-Accel-Buffering":"no"})


@router.get("/receipts/{operation_id}")
def receipt(operation_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    row = db.scalar(c.query(m.UvOpsReceipt).where(m.UvOpsReceipt.actor_id == user.id, m.UvOpsReceipt.operation_id == operation_id))
    c.require(row is not None, "not_found", "尚未找到本人的操作回执", 404)
    a.authorize(user, factory_id, *row.permissions)
    return a.envelope(db, user, row.result)


@router.get("/reports")
def report(db: Db, user: User, start_date: str, end_date: str, factory_id: str = ""):
    gate(db, user, factory_id)
    value = reports.report(db, start_date, end_date)
    return a.envelope(db, user, value, coverage=value["coverage"], warnings=value["warnings"])


@router.post("/quotes/calculate")
def quote(body: s.QuoteCalculate, db: Db, user: User):
    gate(db, user, body.factory_id, "cost_read")
    return a.envelope(db, user, reports.quote(body))


@router.get('/machine-time')
def machine_time(db: Db,user: User,start_date:str,end_date:str,factory_id:str=''):
    gate(db,user,factory_id)
    return a.envelope(db,user,runtime.report(db,start_date,end_date))


@router.post("/schedule/preview")
def preview(body: s.SchedulePreview, db: Db, user: User):
    gate(db, user, body.factory_id, "plan_write")
    return a.envelope(db, user, planning.preview(db, body))


@router.post('/schedule/recommendations')
def recommend(body: s.ScheduleRecommend, db: Db, user: User):
    gate(db,user,body.factory_id,'plan_write')
    task=c.get(db,m.UvOpsTask,body.task_id)
    return a.envelope(db,user,planning.recommendations(db,task,batch_id=body.batch_id,earliest_at=body.earliest_at,manual_seconds=body.manual_estimated_seconds))


@router.get('/schedule/window')
def schedule_window(db:Db,user:User,start_at:datetime,end_at:datetime,factory_id:str='',cursor:str='',limit:int=Query(200,ge=1,le=500)):
    gate(db,user,factory_id)
    start,end=c.ts(start_at),c.ts(end_at)
    c.require(0<(end_at-start_at).total_seconds()<=31*86400,'schedule_window','请选择不超过31天的排程窗口',422)
    query=c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.status!='cancelled',m.UvOpsScheduleBlock.start_at<end,m.UvOpsScheduleBlock.end_at>start)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    if cursor: query=query.where(m.UvOpsScheduleBlock.id>cursor)
    rows=list(db.scalars(query.order_by(m.UvOpsScheduleBlock.id).limit(limit+1)))
    data=[c.record(row) for row in rows[:limit]]
    tasks={row.id:row for row in db.scalars(c.query(m.UvOpsTask).where(m.UvOpsTask.id.in_({row.task_id for row in rows[:limit]})))}
    started_pairs=set()
    for model in (m.UvOpsProductionEntry,m.UvOpsRunAllocation,m.UvOpsExecution):
        started_pairs.update(db.execute(select(model.task_id,model.batch_id).where(model.factory_id==m.FACTORY,model.task_id.in_(tasks)).distinct()).all())
    for row in data:
        row['task_code']=tasks[row['task_id']].code
        row['task_status']=tasks[row['task_id']].status
        row['started']=(row['task_id'],row['batch_id']) in started_pairs or tasks[row['task_id']].status in {'completed','cancelled'} or (row['batch_id'] is None and any(task_id==row['task_id'] for task_id,_ in started_pairs))
    return a.envelope(db,user,data,pagination=dict(total=total,has_more=len(rows)>limit,next_cursor=rows[limit-1].id if len(rows)>limit else None))


@router.get("/tasks/{entity_id}")
def task(entity_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    item = c.get(db, m.UvOpsTask, entity_id)
    detail = p.task_detail(db, item)
    lineage_ids = select(m.UvOpsBatch.id).where(m.UvOpsBatch.factory_id == m.FACTORY, m.UvOpsBatch.task_id == (item.parent_task_id or item.id))
    detail['batch_relations'] = [c.record(x) for x in db.scalars(c.query(m.UvOpsBatchRelation).where(m.UvOpsBatchRelation.source_id.in_(lineage_ids)).order_by(m.UvOpsBatchRelation.created_at, m.UvOpsBatchRelation.id))]
    detail['demand_code'] = c.get(db, m.UvOpsDemand, item.demand_id).code
    preview = db.scalar(c.query(m.UvOpsFileVersion).where(m.UvOpsFileVersion.process_version_id == item.process_version_id, m.UvOpsFileVersion.role == 'preview', m.UvOpsFileVersion.mime.in_(['image/png', 'image/jpeg', 'image/webp'])).order_by(m.UvOpsFileVersion.created_at.desc()).limit(1))
    detail['preview_file_id'] = preview.id if preview else None
    detail["recommendations"] = planning.recommendations(db, item)
    for name, model in (("production", m.UvOpsProductionEntry), ("participations", m.UvOpsParticipation), ("run_allocations", m.UvOpsRunAllocation)):
        detail[name] = [c.record(x) for x in db.scalars(c.query(model).where(model.task_id == item.id))]
    return a.envelope(db, user, detail)


@router.get("/shifts/{entity_id}/gaps")
def gaps(entity_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    return a.envelope(db, user, p.shift_gaps(db, c.get(db, m.UvOpsShift, entity_id)))


@router.post("/files")
async def upload(db: Db, user: User, factory_id: str = Form(...), operation_id: str = Form(...), process_version_id: str = Form(...), role: str = Form(...), file: UploadFile = File(...)):
    gate(db, user, factory_id, "master_write")
    content = await file.read(files.MAX_FILE_BYTES+1)
    digest = files.validate(file.filename, content, file.content_type, role)
    body = s.FileUpload(factory_id=factory_id, operation_id=operation_id, process_version_id=process_version_id, role=role, name=file.filename, sha256=digest, mime=file.content_type, size_bytes=len(content))
    return execute(db, user, body, "file.upload", ("master_write",), lambda: files.create(db, user, body, content))


@router.get("/files/{entity_id}/download")
def download(entity_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id)
    row = c.get(db, m.UvOpsFileVersion, entity_id)
    disposition = "inline" if row.role == "preview" and row.mime.startswith("image/") else "attachment"
    return Response(row.content, media_type=row.mime, headers={"Content-Disposition": disposition, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; sandbox"})


for path, schema, model, permissions in (
    ("/machines", s.MachineCreate, m.UvOpsMachine, ("master_write",)),
    ("/fixtures", s.FixtureCreate, m.UvOpsFixture, ("master_write",)),
    ("/products", s.ProductCreate, m.UvOpsProduct, ("master_write",)),
    ("/process-versions", s.ProcessCreate, m.UvOpsProcessVersion, ("master_write",)),
    ("/pricing-policies", s.PriceCreate, m.UvOpsPricePolicy, ("cost_read", "cost_write")),
    ("/wage-policies", s.WagePolicyCreate, m.UvOpsWagePolicy, ("payroll_read", "payroll_write")),
    ("/ink/skus", s.InkSkuCreate, m.UvOpsInkSku, ("inventory_write",)),
):
    register(path, schema, permissions, lambda db, user, body, model=model: p.create_master(db, user, body, model))

register("/demands", s.DemandCreate, ("plan_write",), p.create_demand)
register("/agents", s.AgentCreate, ("agent_manage",), ingest.create_agent)
register("/sources", s.SourceBind, ("agent_manage",), ingest.bind_source)
register('/sources/{entity_id}/unbind', s.Command, ('agent_manage',), ingest.unbind_source)
register("/agents/{entity_id}/revoke", s.Command, ("agent_manage",), ingest.revoke)
register("/runs/{entity_id}/match", s.RunMatch, ("production_write",), ingest.match_run)
register("/tasks", s.TaskCreate, ("plan_write",), p.create_task)
register('/tasks/{entity_id}/cancel',s.Command,('plan_write',),p.cancel_task)
register('/tasks/{entity_id}/complete-accounting',s.CompleteAccounting,lambda body:('plan_write',*(('cost_read','cost_write') if body.price_policy_id else ()),*(('payroll_read','payroll_write') if body.wage_policy_id else ())),p.complete_accounting)
register('/run-costs',s.RunCost,('cost_read','cost_write'),reports.run_cost)
register("/schedule/commit", s.SchedulePreview, ("plan_write",), planning.commit)
register('/schedule/{entity_id}/cancel',s.Command,('plan_write',),lambda db,user,entity_id,body:planning.change_plan(db,user,entity_id,body,cancel=True))
register('/schedule/{entity_id}/unlock',s.Command,('plan_write',),planning.change_plan)
register("/shifts", s.ShiftCreate, ("shift_write",), p.create_shift)
register("/participations", s.ParticipationCreate, ("shift_write",), p.participate)
register("/production/confirm", s.ProductionConfirm, ("production_write",), p.confirm)
register("/production/{entity_id}/reverse", s.Command, ("production_write",), p.reverse)
register("/batches/{entity_id}/advance-pass", s.Command, ("production_write",), p.advance_pass)
register('/batches/{entity_id}/split',s.BatchSplit,('plan_write',),p.reshape_batch)
register('/batches/{entity_id}/merge',s.BatchMerge,('plan_write',),lambda db,user,entity_id,body:p.reshape_batch(db,user,entity_id,body,merge=True))
register("/quality/resolve", s.QualityResolve, ("quality_write",), p.quality)
register('/schedule/{entity_id}/start',s.ExecutionStart,('production_write',),execution.start)
register('/executions/{entity_id}/finish',s.ExecutionFinish,('production_write',),execution.finish)
for route,kind,permissions in [('quality','quality',('quality_write',)),('participations','participation',('shift_write',)),('wages','wage',('payroll_read','payroll_write')),('expenses','expense',('cost_read','cost_write')),('run-costs','run_cost',('cost_read','cost_write'))]:
    register('/'+route+'/{entity_id}/reverse',s.Command,permissions,lambda db,user,entity_id,body,kind=kind:corrections.reverse(db,user,entity_id,body,kind))

register("/rework-tasks", s.ReworkCreate, ("quality_write", "plan_write"), p.rework_task)
register("/handovers", s.HandoverCreate, ("handover_write",), p.handover_create)
register('/handovers/{entity_id}/cancel',s.HandoverCancel,('handover_write',),p.cancel_handover)
register('/rework-tasks/{entity_id}/cancel',s.Command,('quality_write','plan_write'),p.cancel_rework)
for kind in ("receive", "reject", "return"):
    register("/handovers/{entity_id}/"+kind, s.HandoverAction, ("handover_write",), lambda db, user, entity_id, body, kind=kind: p.handover_action(db, user, entity_id, body, kind))
register("/shifts/{entity_id}/close", s.ShiftClose, ("shift_write",), p.close_shift)
register("/file-versions/{entity_id}/confirm", s.FileConfirm, ("master_write",), files.confirm)
register("/ink/movements", s.InkMovement, ("inventory_write", "cost_read", "cost_write"), inventory.movement)
register("/expenses", s.ExpenseCreate, ("cost_read", "cost_write"), reports.expense)
register("/wages/confirm", s.WageConfirm, ("payroll_read", "payroll_write"), payroll.confirm)
register("/imports/{entity_id}/commit", s.ImportCommit, ("import",), imports.commit)
register('/imports/{entity_id}/revalidate',s.Command,('import',),imports.revalidate)
register("/exports", s.ExportCreate, ("export",), exports.create)
register("/periods/{entity_id}/close", s.Command, ("close_period", "cost_read", "payroll_read"), reports.close)
register("/periods/{entity_id}/reopen", s.Command, ("close_period", "cost_read", "payroll_read"), reports.reopen)


def amend_machine(db, user, entity_id, body):
    machine = c.get(db, m.UvOpsMachine, entity_id, lock=True, version=body.expected_version)
    for key, value in c.values(body).items():
        setattr(machine, key, value)
    c.touch(machine)
    return c.record(machine)


def cancel_demand(db, user, entity_id, body):
    row = c.get(db, m.UvOpsDemand, entity_id, lock=True, version=body.expected_version)
    c.require(row.allocated + row.cancelled + body.quantity <= row.quantity, "cancel_allocated", "仅能取消尚未分配的需求数量")
    row.cancelled += body.quantity
    c.touch(row)
    return c.record(row)


def reopen_shift(db, user, entity_id, body):
    row = c.get(db, m.UvOpsShift, entity_id)
    c.lock_period(db, row.business_date)
    row = c.get(db, m.UvOpsShift, entity_id, lock=True, version=body.expected_version)
    c.require(row.status == "closed" and len(body.reason.strip()) >= 5, "reopen_reason", "请为已关闭班次填写具体重开理由", 422)
    row.status = "open"
    c.touch(row)
    return c.record(row)


register("/machines/{entity_id}", s.MachineCreate, ("master_write",), amend_machine, method="PATCH")
register("/demands/{entity_id}/cancel", s.QuantityAction, ("plan_write",), cancel_demand)
register("/shifts/{entity_id}/reopen", s.Command, ("shift_write",), reopen_shift)

COLLECTIONS = {
    'executions':(m.UvOpsExecution,()), 'reversals':(m.UvOpsReversal,('audit_read',)),
    "machines": (m.UvOpsMachine, ()), "fixtures": (m.UvOpsFixture, ()), "products": (m.UvOpsProduct, ()),
    "process-versions": (m.UvOpsProcessVersion, ()), "file-versions": (m.UvOpsFileVersion, ()),
    "demands": (m.UvOpsDemand, ()), "tasks": (m.UvOpsTask, ()), "schedule": (m.UvOpsScheduleBlock, ()),
    "shifts": (m.UvOpsShift, ()), "participations": (m.UvOpsParticipation, ()), "batches": (m.UvOpsBatch, ()),
    'batch-relations': (m.UvOpsBatchRelation, ()),
    "production": (m.UvOpsProductionEntry, ()), "quality": (m.UvOpsQualityEntry, ()), "handovers": (m.UvOpsHandover, ()),
    "ink/skus": (m.UvOpsInkSku, ()), "ink/balances": (m.UvOpsInkBalance, ()), "ink/movements": (m.UvOpsInkMovement, ()),
    "pricing-policies": (m.UvOpsPricePolicy, ("cost_read",)), "wage-policies": (m.UvOpsWagePolicy, ("payroll_read",)),
    "wages": (m.UvOpsWageAccrual, ("payroll_read",)), "wage-allocations": (m.UvOpsWageAllocation, ("payroll_read",)),
    "expenses": (m.UvOpsExpense, ("cost_read",)), "periods": (m.UvOpsPeriod, ("cost_read", "payroll_read")),
    "report-snapshots": (m.UvOpsReportSnapshot, ("cost_read", "payroll_read")),
    "runs": (m.UvOpsRun, ()), "run-allocations": (m.UvOpsRunAllocation, ()),
    "agents": (m.UvOpsAgent, ("agent_manage",)), "sources": (m.UvOpsSourceBinding, ("agent_manage",)),
    "audit": (m.UvOpsAudit, ("audit_read",)),
    'reference-efficiency':(m.UvOpsReferenceEfficiency,('cost_read',)),
    'run-costs':(m.UvOpsRunCost,('cost_read',)),
}


def register_collection(name, model, permissions):
    def listing(db: Db, user: User, factory_id: str = "", cursor: str = "", limit: int = Query(100, ge=1, le=200), history: bool = False):
        gate(db, user, factory_id, *permissions)
        statement = c.query(model, history=history).order_by(model.id)
        if model == m.UvOpsBatch:
            statement = statement.where(model.active.is_(True))
        total = db.scalar(select(func.count()).select_from(statement.subquery()))
        if cursor:
            statement = statement.where(model.id > cursor)
        rows = list(db.scalars(statement.limit(limit+1)))
        has_more = len(rows) > limit
        data = [p.task_detail(db, x) if model == m.UvOpsTask else c.record(x) for x in rows[:limit]]
        return a.envelope(db, user, data, pagination=dict(total=total, next_cursor=rows[limit-1].id if has_more else None, has_more=has_more))
    listing.__name__ = "uv_list_"+name.replace("/", "_").replace("-", "_")
    router.add_api_route("/"+name, listing, methods=["GET"])


for name, (model, permissions) in COLLECTIONS.items():
    register_collection(name, model, permissions)


@router.get('/exports')
def export_jobs(db: Db, user: User, factory_id: str = ''):
    gate(db, user, factory_id, 'export')
    rows = list(db.scalars(c.query(m.UvOpsExportJob).where(m.UvOpsExportJob.actor_id == user.id).order_by(m.UvOpsExportJob.created_at.desc()).limit(100)))
    return a.envelope(db, user, [c.record(row) for row in rows if all(a.allowed(user, permission) for permission in row.permissions)])


def retry_export(db, user, entity_id, body):
    row = c.get(db, m.UvOpsExportJob, entity_id, lock=True, version=body.expected_version)
    c.require(row.actor_id == user.id, 'export_owner', '只能重试本人的导出任务', 403)
    a.authorize(user, m.FACTORY, *row.permissions)
    c.require(row.status == 'failed', 'export_state', '只有失败任务可以重试')
    row.status, row.error = 'queued', None
    c.touch(row)
    return c.record(row)


register('/exports/{entity_id}/retry', s.Command, ('export',), retry_export)


@router.get('/late-events')
def late_events(db: Db, user: User, factory_id: str = '',cursor:str='',limit:int=Query(100,ge=1,le=200)):
    gate(db, user, factory_id, 'audit_read')
    statement=c.query(m.UvOpsAgentEventInbox).where(m.UvOpsAgentEventInbox.late_closed_period.is_(True)).order_by(m.UvOpsAgentEventInbox.id)
    total=db.scalar(select(func.count()).select_from(statement.subquery()))
    if cursor: statement=statement.where(m.UvOpsAgentEventInbox.id>cursor)
    rows=list(db.scalars(statement.limit(limit+1)))
    return a.envelope(db,user,[c.record(row, exclude=('evidence', 'payload_hash')) for row in rows[:limit]],pagination=dict(total=total,has_more=len(rows)>limit,next_cursor=rows[limit-1].id if len(rows)>limit else None))


def acknowledge_late(db,user,entity_id,body):
    row=c.get(db,m.UvOpsAgentEventInbox,entity_id,lock=True,version=body.expected_version)
    c.require(row.late_closed_period and row.resolved_by is None,'late_state','该证据已处理或不属于封账后差异')
    c.require(len(body.reason.strip())>=5,'reason_required','请记录核对结论及是否需要重开账期',422)
    row.resolved_by=user.id
    c.touch(row)
    return c.record(row,exclude=('evidence','payload_hash'))


register('/late-events/{entity_id}/acknowledge',s.Command,('audit_read','close_period'),acknowledge_late)


@router.get("/imports/templates")
def import_templates(db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id, "import")
    return a.envelope(db, user, {key: dict(fields=[name for name in schema.model_fields if name not in {"operation_id", "factory_id", "reason"}], permissions=list(permissions)) for key, (schema, permissions, _) in imports.TEMPLATES.items() if all(a.allowed(user, permission) for permission in permissions)})


@router.post("/imports/preview")
async def import_preview(db: Db, user: User, factory_id: str = Form(...), template: str = Form(...), file: UploadFile = File(...), field_mapping: str = Form('{}'), units_confirmed: bool = Form(False)):
    gate(db, user, factory_id, "import")
    content = await file.read(imports.MAX_BYTES+1)
    import json
    return a.envelope(db, user, imports.preview(db, user, template, file.filename, content, json.loads(field_mapping), units_confirmed))


@router.get("/exports/{entity_id}")
def export_status(entity_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id, "export")
    row = c.get(db, m.UvOpsExportJob, entity_id)
    c.require(row.actor_id == user.id, "export_owner", "只能读取本人的导出任务", 403)
    a.authorize(user, factory_id, *row.permissions)
    return a.envelope(db, user, c.record(row))


@router.get('/imports/{entity_id}')
def import_status(entity_id:str,db:Db,user:User,factory_id:str=''):
    gate(db,user,factory_id,'import')
    row=c.get(db,m.UvOpsImportJob,entity_id)
    c.require(row.actor_id==user.id,'import_owner','只能读取本人导入作业',403)
    a.authorize(user,factory_id,*imports.TEMPLATES[row.template][1])
    return a.envelope(db,user,imports.summary(row))


@router.get("/exports/{entity_id}/download")
def export_download(entity_id: str, db: Db, user: User, factory_id: str = ""):
    gate(db, user, factory_id, "export")
    row = c.get(db, m.UvOpsExportJob, entity_id)
    c.require(row.actor_id == user.id, "export_owner", "只能下载本人的导出结果", 403)
    a.authorize(user, factory_id, *row.permissions)
    c.require(row.status == "ready", "export_not_ready", "导出尚未完成，请等待任务状态更新")
    a.authorize(user,factory_id,*row.filters.get('_built_read_permissions',[]))
    content = row.artifact
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":'attachment; filename="uv-'+row.kind+'.xlsx"', "Cache-Control":"no-store"})
