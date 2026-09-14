"""UV's explicit factory boundary and response permission projection."""
from datetime import date, datetime
import importlib.util
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.core.config import settings
from app.db import get_db
from app.models import uv_printing as m
from app.services import uv_printing as s
from app.services.auth import AuthContext, get_current_user, authorization_decision
from app.services.permission_codes import UV_PRINTING_PERMISSION_CODES
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/uv-printing", tags=["uv-printing"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def allowed(user, code):
    # New UV authority never uses the permissive legacy fallback. Explicit
    # denies and department scope remain authoritative in every authz mode.
    return authorization_decision(user, "uv_printing:" + code, "huakang-a", "production")[0]


def authorize(db, user, factory, code="read"):
    if not factory:
        raise HTTPException(422, "必须提供明确 factory_id")
    if factory != "huakang-a":
        raise HTTPException(403, "UV打印仅适用于华康A生产部")
    if not allowed(user, code):
        raise HTTPException(403, "无华康A生产部相应UV权限")
    if not settings.uv_printing_enabled:
        raise HTTPException(503, "UV打印尚未启用，生产数据不可用")


def response_coverage(data):
    if data is None or data == []:
        return "no_data"
    if isinstance(data, list):
        return "partial" if any(response_coverage(v) == "partial" for v in data) else "complete"
    if not isinstance(data, dict):
        return "complete"
    if data.get("coverage") in ("complete", "partial", "no_data"):
        return data["coverage"]
    if "entity" in data:
        return response_coverage(data["entity"])
    if "items" in data:
        return "no_data" if data.get("total") == 0 else response_coverage(data["items"])
    if "months" in data:
        return "no_data" if not data["months"] else response_coverage(data["months"])
    if data.get("status") == "draft" or data.get("quality_status") in ("pending", "partial") or data.get("pricing_state") == "unpriced" or data.get("reconciliation") in ("unmatched", "needs_unit") or data.get("state") in ("unpriced", "provisional", "pending", "difference") or data.get("cost_coverage") == "partial" or data.get("provisional_reasons"):
        return "partial"
    if any(key in data and data[key] is None for key in ("output_value", "payroll_amount", "operating_result", "batch_total")):
        return "partial"
    if any(data.get(key, 0) for key in ("quality_pending_reports", "unpriced_reports", "unassigned_reports")):
        return "partial"
    if "counts" in data:
        counts = data["counts"]
        if any(counts.get(key, 0) for key in ("unmatched_jobs", "needs_unit_jobs", "reports_needing_quality", "handover_differences")):
            return "partial"
        if not any(counts.values()):
            return "no_data"
    return "partial" if any(response_coverage(data[k]) == "partial" for k in ("commercial", "payroll", "revisions") if k in data) else "complete"


def envelope(data, warnings=None, coverage=None):
    collected = list(warnings or [])
    if isinstance(data, dict):
        collected.extend(data.get("warnings", []))
    resolved = coverage or response_coverage(data)
    if resolved in ("complete", "no_data") and any(w.get("tone") in ("warning", "error") for w in collected):
        resolved = "partial"
    if resolved == "partial" and not collected:
        collected.append(dict(code="incomplete_coverage", message="当前记录仍有来源、质量、计价、人员或成本待核项，不能作为完整核定结果", tone="warning"))
    collected = list({(w.get("code"), w.get("message")): w for w in collected}.values())
    if isinstance(data, dict) and "coverage" in data:
        data = {**data, "coverage": resolved}
    return {"meta": {"factory_id": "huakang-a", "as_of": m.now(), "data_mode": "live", "coverage": resolved, "warnings": collected}, "data": data}


COST_KEYS = {"commercial", "output_value", "area_value", "ink_cost", "expense_amount", "operating_result", "result_ratio", "payroll_ratio", "cost_coverage"}
PAYROLL_KEYS = {"payroll", "worker_shares", "payroll_amount", "payroll_ratio"}


def redact(value, user):
    if isinstance(value, list):
        return [redact(v, user) for v in value]
    if not isinstance(value, dict):
        return value
    denied = (set() if allowed(user, "cost_read") else COST_KEYS) | (set() if allowed(user, "payroll_read") else PAYROLL_KEYS)
    if "rate_kind" in value and not allowed(user, "payroll_read" if value["rate_kind"] == "piece_wage" else "cost_read"):
        denied |= {"unit_price", "currency"}
    return {k: redact(v, user) for k, v in value.items() if k not in denied}


def scope_query(factory_id: str = Query(...), business_date: date | None = None, date_from: date | None = None, date_to: date | None = None,
                shift: str | None = Query(None, pattern="^(day|night)$"), machine_id: str | None = None, product_id: str | None = None,
                status: str | None = None, q: str = Query("", max_length=128), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "开始日期晚于结束日期")
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in locals().items() if v is not None}


Scope = Annotated[dict, Depends(scope_query)]
COLLECTIONS = {"machines": m.UvMachine, "products": m.UvProduct, "rate-versions": m.UvRateVersion, "workers": m.UvWorker,
    "shift-templates": m.UvShiftTemplate, "shift-assignments": m.UvAssignment, "jobs": m.UvJob, "production-reports": m.UvReport}


def collection_endpoint(kind):
    def endpoint(db: Db, user: User, scope: Scope):
        authorize(db, user, scope["factory_id"])
        rows = s.query_rows(db, COLLECTIONS[kind], scope["factory_id"], scope)
        warnings = []
        if kind == "jobs":
            warnings.extend(s.job_scope_warnings(db, scope["factory_id"], scope))
        if kind == "rate-versions":
            rows = [r for r in rows if allowed(user, "payroll_read" if r.rate_kind == "piece_wage" else "cost_read")]
            if not allowed(user, "payroll_read") or not allowed(user, "cost_read"):
                warnings.append(dict(code="restricted_rates", message="仅返回当前授权价规", tone="info"))
        return envelope(redact(s.page([s.entity_output(db, row) for row in rows], scope), user), warnings)
    return endpoint


for kind in COLLECTIONS:
    router.add_api_route("/" + kind, collection_endpoint(kind), methods=["GET"], name="uv_" + kind)


@router.get("/summary")
def summary(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    reports = [s.report_output(db, r) for r in s.query_rows(db, m.UvReport, scope["factory_id"], scope, True)]
    machines = [s.entity_output(db, r) for r in s.query_rows(db, m.UvMachine, scope["factory_id"], scope)]
    jobs = [s.job_output(db, r) for r in s.query_rows(db, m.UvJob, scope["factory_id"], scope)]
    data = dict(business_date=scope.get("business_date") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(), shift=scope.get("shift", "all"),
        counts=dict(enabled_machines=sum(r["enabled"] and r["admin_status"] != "disabled" for r in machines), fresh_connected_machines=sum(r["freshness"] == "fresh" for r in machines), good_qty=sum(r["good_qty"] for r in reports), pending_qty=sum(r["pending_qty"] for r in reports), unmatched_jobs=sum(r["reconciliation"] == "unmatched" for r in jobs), needs_unit_jobs=sum(r["reconciliation"] == "needs_unit" for r in jobs), reports_needing_quality=sum(r["quality_status"] != "complete" for r in reports), low_stock_skus=0, handover_differences=0),
        permissions=[p for p in UV_PRINTING_PERMISSION_CODES if allowed(user, p.split(":")[1])],
        commercial=dict(output_value=s.sum_money(r["commercial"]["output_value"] for r in reports), unpriced_report_count=sum(r["commercial"]["pricing_state"] == "unpriced" for r in reports), pricing_complete=bool(reports) and all(r["commercial"]["pricing_state"] == "priced" for r in reports)))
    warnings = s.job_scope_warnings(db, scope["factory_id"], scope)
    if importlib.util.find_spec("app.services.uv_finance"):
        from app.services.uv_finance import summary_counts
        data["counts"].update(summary_counts(db, scope["factory_id"], scope))
    else:
        warnings.append(dict(code="ink_summary_unavailable", message="墨水库存摘要能力尚未启用", tone="warning"))
    if importlib.util.find_spec("app.services.uv_handover"):
        from app.services.uv_handover import summary_counts
        data["counts"].update(summary_counts(db, scope["factory_id"], scope))
    else:
        warnings.append(dict(code="handover_summary_unavailable", message="入库核数摘要能力尚未启用", tone="warning"))
    if reports and data["commercial"]["output_value"] is None:
        data["commercial"]["pricing_complete"] = False
    return envelope(redact(data, user), warnings)


@router.get("/products/{product_id}")
def product_detail(product_id: str, db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(s.entity_output(db, s.find(db, m.UvProduct, scope["factory_id"], product_id)))


@router.get("/machines/{machine_id}")
def machine_detail(machine_id: str, db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    row = s.find(db, m.UvMachine, scope["factory_id"], machine_id)
    scope["machine_id"] = machine_id
    windows, warnings = s.runtime_windows(db, scope["factory_id"], machine_id, scope)
    warnings.extend(s.job_scope_warnings(db, scope["factory_id"], scope))
    data = dict(machine=s.entity_output(db, row), jobs=[s.job_output(db, r) for r in s.query_rows(db, m.UvJob, scope["factory_id"], scope)], reports=[s.report_output(db, r) for r in s.query_rows(db, m.UvReport, scope["factory_id"], scope)], assignments=[s.entity_output(db, r) for r in s.query_rows(db, m.UvAssignment, scope["factory_id"], scope)], runtime_windows=windows)
    if allowed(user, "cost_read"):
        expenses, expense_warnings = s.machine_expenses(db, scope["factory_id"], machine_id, scope)
        data["expenses"] = expenses
        warnings.extend(expense_warnings)
    return envelope(redact(data, user), warnings)


@router.get("/production-reports/{report_id}")
def report_detail(report_id: str, db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(redact(s.report_output(db, s.find(db, m.UvReport, scope["factory_id"], report_id)), user))


@router.get("/production-reports/{report_id}/trace")
def report_trace(report_id: str, db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(redact(s.report_trace(db, scope["factory_id"], report_id), user))


@router.get("/payroll/preview")
def payroll_preview(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"], "payroll_read")
    return envelope(s.payroll_preview(db, scope["factory_id"], scope))


@router.get("/reports/daily-projection")
def daily_projection(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(redact(s.page(s.daily_projection(db, scope["factory_id"], scope), scope), user))


@router.get("/reports/daily")
def daily_report(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    days = s.daily_projection(db, scope["factory_id"], scope)
    rows = [dict(key=key, label=label, value=str(sum(d[key] for d in days)), unit="件", drill_kind="reports", drill_ref=None, provisional=False)
            for key, label in (("reported_qty", "报工数量"), ("good_qty", "合格数量"), ("defective_qty", "不良数量"))]
    for key, label, permission, drill in (("output_value", "商业产值", "cost_read", "reports"), ("payroll_amount", "班组工资", "payroll_read", "payroll"), ("operating_result", "经营结余", "cost_read", "expenses")):
        if allowed(user, permission):
            value = s.sum_money(d[key] for d in days)
            rows.append(dict(key=key, label=label, value=value["amount"] if value else None, unit=value["currency"] if value else "", drill_kind=drill, drill_ref=None, provisional=value is None))
    metrics = [{**{k: r[k] for k in ("key", "label", "value", "unit", "provisional")}, "formula": "全量有效记录按相同筛选汇总", "sources": ["production-reports"], "note": "缺价及不同币种不能合并" if r["provisional"] else "", "unpriced": r["value"] is None} for r in rows]
    return envelope(dict(business_date=scope.get("business_date", ""), shift=scope.get("shift", "all"), headline="有效报工与质量口径", metrics=metrics, rows=rows, coverage="partial" if any(r["provisional"] for r in rows) else "complete" if days else "no_data"))


@router.get("/reports/monthly")
def monthly_projection(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(redact(s.monthly_projection(db, scope["factory_id"], scope), user))


@router.get("/operations/{operation_id}")
def operation_result(operation_id: str, db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    row = db.scalar(select(m.UvOperation).where(m.UvOperation.factory_id == scope["factory_id"], m.UvOperation.actor_id == user.id, m.UvOperation.operation_id == operation_id))
    entity = row.result["entity"] if row else None
    return envelope(None if row is None else dict(operation_id=row.operation_id, command=row.command, result_kind=row.command, result_id=entity.get("id") if isinstance(entity, dict) else None, accepted_at=row.created_at, summary="请求已提交并持久化"))


def command_endpoint(action, permission):
    def endpoint(request: Request, db: Db, user: User, payload: Annotated[dict[str, Any], Body()]):
        factory = payload.get("factory_id")
        authorize(db, user, factory)
        authorize(db, user, factory, permission)
        for key, value in request.path_params.items():
            body_key = key if key in ("report_id", "job_id", "product_id") else "id"
            if action == "product":
                body_key = "id"
            if payload.get(body_key) != value:
                raise HTTPException(422, "路径与请求对象不一致")
        if action == "rate":
            authorize(db, user, factory, "payroll_write" if payload.get("rate_kind") == "piece_wage" else "cost_write")
        if action == "report":
            quality = payload
            if any(quality.get(k, 0) for k in ("good_qty", "defective_qty", "semi_finished_qty")):
                authorize(db, user, factory, "quality")
        try:
            if action in ("correction", "void"):
                s.lock(db, factory)
                original = s.find(db, m.UvReport, factory, payload.get("report_id"))
                corrected = payload.get("correction", {})
                if action == "correction" and not isinstance(corrected, dict):
                    raise HTTPException(422, "更正明细必须是对象")
                changes_quality = any(getattr(original, key) != (corrected.get(key) if action == "correction" else 0) for key in s.QUALITY)
                if changes_quality:
                    authorize(db, user, factory, "quality")
            result = s.execute(db, factory, user.id, action, payload)
            db.commit()
            return envelope(redact(result, user))
        except (IntegrityError, OperationalError):
            db.rollback()
            raise HTTPException(409, "唯一约束或并发状态冲突，请刷新核对")
        except Exception:
            db.rollback()
            raise
    return endpoint


for path, action, permission in (
    ("/products", "product", "master_write"), ("/products/{product_id}", "product", "master_write"),
    ("/products/{product_id}/process-versions", "process", "master_write"),
    ("/rate-versions", "rate", "read"), ("/rate-versions/{rate_id}", "rate", "read"),
    ("/machines", "machine", "master_write"), ("/machines/{machine_id}", "machine", "master_write"),
    ("/workers", "worker", "shift_write"), ("/workers/{worker_id}", "worker", "shift_write"),
    ("/shift-templates", "shift-template", "shift_write"), ("/shift-templates/{template_id}", "shift-template", "shift_write"),
    ("/shift-assignments", "assignment", "shift_write"), ("/jobs/{job_id}/reconcile", "reconcile", "report"),
    ("/production-reports", "report", "report"), ("/production-reports/{report_id}/confirm", "confirm", "report"),
    ("/production-reports/{report_id}/quality", "quality", "quality"), ("/production-reports/{report_id}/corrections", "correction", "report"),
    ("/production-reports/{report_id}/void", "void", "report")):
    router.add_api_route(path, command_endpoint(action, permission), methods=["POST"], name="uv_" + action)
