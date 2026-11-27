"""Nexus-authenticated gateway for the isolated QC_department service.

Factory identity comes from the authorized route, never from the embedded app.
Sales schedule rows use the explicit QC workflow field mapping; legacy stores remain isolated.
"""
import json
import hashlib
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.auth import AuthUser
from app.services.auth import AuthContext, can, get_current_user, has_permission_in_scope
from app.api.qc_inspection import _ensure_permission
from app.services import qc_workflow, qc_inspection_sheet, qc_inspection_summary, qc_approved_statistics, qc_daily_report, qc_weekly_templates
from starlette.concurrency import run_in_threadpool
from app.services import qc_weekly_excel, qc_monthly_templates, qc_monthly_excel
from app.services.qc_approved_statistics import factory_label
from app.services import qc_report_empty_cols as empty_cols
from urllib.parse import quote

router = APIRouter(prefix="/api/qc-department", tags=["qc-department"])
ASSETS = Path(__file__).resolve().parents[3] / "services" / "qc-department"
COMPANIES = {
    "huakang-a": "hy-huakang-a", "huakang-b": "hy-huakang-b",
    "huakang-c": "hy-huakang-c", "huakang-d": "hy-huakang-d",
    "huadeng": "hy-huadeng", "huaxing": "hy-huaxing",
}
EMPTY_ART_FILES = {
    "empty-art/clerk-reports-middle.webp",
    *(f"empty-art/clerk-{scene}-{pose}.webp"
      for scene in ("schedule", "inspection", "review", "summary", "reports")
      for pose in ("rest", "action")),
}
STATIC_FILES = {
    *EMPTY_ART_FILES,
    "qc-select.js", "qc-select.css",
    "qc-empty-state.js", "qc-empty-state.css", "qc-empty-motion.js",
    "qc-mobile-entry.js", "qc-mobile-entry.css", "qc-photo-shapes.js", "qc-glass-guide.js", "qc-glass-guide.css",
    "qc-export-columns.js", "qc-report-workbook.js", "qc-report-workbook.css", "qc-review-workbook.js",
    "qc-daily-report.js", "qc-daily-report.css",
    "qc-weekly-templates.js", "qc-weekly-templates.css",
    "qc-monthly-templates.js", "qc-monthly-templates.css", "qc-issue-reports.js", "qc-issue-reports.css",
    "qc-approved-statistics.js", "qc-approved-statistics.css",
    "qc-inspection-print.js", "qc-inspection-print.css",
    "index.html", "app.js", "style.css", "mobile.js", "mobile.css",
    "qc-backend.js", "report_export.js", "ai-ocr.js", "nexus-integration.js", "qc-schedule.js", "qc-workflow.js", "qc-workflow.css", "qc-photo-paste.js", "qc-inspection-audit.js", "qc-inspection-sheet.js", "qc-inspection-sheet.css", "qc-inspection-summary.js", "qc-inspection-summary.css",
}
WRITE_PERMISSIONS = {
    "api/records": "qc_inspection:result_write",
    "api/records/delete": "qc_inspection:result_write",
    "api/reference-data/clear": "qc_inspection:result_write",
    "api/records/replace": "qc_inspection:result_write",
    "api/partners": "qc_inspection:customer_manage",
    "api/defects": "qc_inspection:customer_manage",
    "api/ai/ocr-extract": "qc_inspection:result_write",
}
READ_ENDPOINTS = {"api/bootstrap", "api/health", "api/ai/status",
                  "api/export/records.csv", "api/export/factory-excel.xls"}
NO_CACHE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def schedule_source(factory_id: str) -> dict:
    return {
        "contract_version": "1", "factory_id": factory_id,
        "source": "sales.customer-order-ledger.schedule",
        "source_endpoint": "/api/customer-order-ledger/schedule",
        "status": "mapping_required", "mapping_version": None,
        "source_available": None, "items": [], "import_enabled": False,
        "message": "业务部客排期数据待接通；完成字段映射后直接读取，无需 Excel 导入。",
    }


def schedule_example(factory_id: str, *, missing_ok: bool = False) -> dict:
    # User-authorized preview only. Never read/write inspection or Sales databases.
    if factory_id != "huaxing":
        raise HTTPException(404, "当前厂区没有客排期示例")
    try:
        payload = json.loads((ASSETS / "fixtures" / "qc-schedule-example.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        if missing_ok:
            return {"factory_id": factory_id, "example": True, "items": []}
        raise HTTPException(503, "示例数据暂不可用") from None
    except (OSError, ValueError):
        raise HTTPException(503, "示例数据暂不可用") from None
    if payload.get("factory_id") != factory_id or payload.get("example") is not True:
        raise HTTPException(503, "示例数据配置不正确")
    return payload


def inspection_plan_dates(factory_id: str, records: list, eligible_ids=None) -> dict:
    """Read-only provenance join for the explicitly authorized local test import.

    Keep metadata outside records: do not alter incoming/actual dates or the
    signed original snapshots used to authorize linked inspection drafts.
    """
    if factory_id != 'huaxing' or not records:
        return {}
    eligible = set(eligible_ids) if eligible_ids is not None else {
        r['id'] for r in records if qc_workflow.test_entry_allowed(factory_id, r)}
    if not eligible:
        return {}
    source = {r['id']: r for r in schedule_example(factory_id)['items']}
    plans = {}
    for record in records:
        if record.get('id') not in eligible:
            continue
        match = re.search(r'^来源：[^\n]*；(schedule-example-row-\d+)\s*$', record.get('remark') or '', re.M)
        row = source.get(match.group(1)) if match else None
        if not row or any(str(record.get(a) or '').strip() != str(row.get(b) or '').strip()
                          for a,b in [('client','customer'),('orderNo','poNo'),('productNo','productNo')]):
            continue
        start = qc_workflow.source_date(row.get('dateFrom'))
        end = qc_workflow.source_date(row.get('dateTo') or row.get('dateFrom'))
        if start and end and start <= end:
            plans[str(record['id'])] = {'from': start, 'to': end}
    return plans


def ui_context(user: AuthContext, factory_id: str) -> dict:
    allowed = lambda p: can(user, "qc_inspection:" + p, factory_id, "qc")
    write = allowed("result_write") and allowed("order_write")
    manage, export = allowed("customer_manage"), allowed("report_export")
    record_delete = allowed("record_delete")
    menus = ["dashboard", "sales-schedule", "records", "review", "inspection-summary", "analysis", "suppliers",
             "daily", "weekly", "monthly", "yearly", "supplier-report", "defectlib", "import"]
    perms = {key: {"v": 1, "e": 0, "a": 0, "m": 0} for key in menus}
    for key in ("records", "review"):
        perms[key].update(e=int(write), a=int(write), m=int(record_delete))
    for key in ("suppliers", "defectlib"):
        perms[key].update(e=int(manage), a=int(manage), m=int(manage))
    perms["review"]["a"] = int(allowed("review"))
    perms["import"] = dict(v=int(write and manage), e=0, a=0, m=int(record_delete))
    return {"factory": factory_id, "company": COMPANIES[factory_id], "factoryLabel": factory_label(factory_id), "exportAllowed": export, "summaryImportAllowed": allowed("result_write") and manage and export,
            "weeklyTemplatesEditAllowed": allowed("result_write"),
            "deleteAllowed": record_delete,
            "workflow": {"create": allowed("schedule_write") and allowed("order_write"), "edit": allowed("result_write"),
                         "review": allowed("review"),
                         "reviewReads": has_permission_in_scope(user, "qc_inspection:result_write", factory_id, "qc"),
                         "export": export, "manual": write, "delete": record_delete},
            "inspector": {"id": user.id, "name": user.display_name or user.username},
            "user": {"username": "nexus:" + user.id, "name": user.display_name or user.username,
                     "role": "viewer", "enabled": True, "perms": perms}}


async def upstream(method: str, path: str, params: list, body: bytes) -> httpx.Response:
    token = settings.qc_department_gateway_token.get_secret_value()
    if not token:
        raise HTTPException(503, "QC 服务尚未配置，请联系管理员")
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            return await client.request(method, settings.qc_department_url.rstrip("/") + "/" + path,
                params=params, content=body,
                headers={"X-QC-Gateway-Token": token, "Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        raise HTTPException(503, "QC 服务暂时不可用，请稍后重试") from exc


def _legacy_status(record: dict) -> str:
    return str(record.get("status") or "").strip() or "approved"


@router.api_route("/{factory_id}/{asset_path:path}", methods=["GET", "HEAD", "POST"])
async def gateway(factory_id: str, asset_path: str, request: Request,
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "qc_inspection:read", factory_id)
    if factory_id not in COMPANIES:
        raise HTTPException(422, "此厂区尚未配置 QC 对应关系")
    company = COMPANIES[factory_id]
    # Bind every embedded URL to its actor and authorization version. An old tab
    # must not submit its draft with a different account's shared session cookie.
    actor = hashlib.sha256(f"{user.id}:{user.authorization_version}".encode()).hexdigest()[:32]
    actor_prefix = "u-" + actor + "/"
    if asset_path == "api/health" and request.method == "GET":
        result = await upstream("GET", "api/health", [], b"")
        if result.status_code != 200:
            raise HTTPException(503, "QC 服务暂时不可用")
        return JSONResponse({"ok": True, "frame_url": f"/api/qc-department/{factory_id}/{actor_prefix}"}, headers=NO_CACHE)
    if not asset_path.startswith(actor_prefix):
        raise HTTPException(409, "账号或权限已变化，请重新加载 QC 工作台")
    asset_path = asset_path[len(actor_prefix):]
    if any(value != company for value in request.query_params.getlist("company")):
        raise HTTPException(403, "不能访问其他厂区的数据")
    asset_path = asset_path or "index.html"
    if asset_path.startswith('api/inspection-dossier/records/'):
        if request.method != 'GET':
            raise HTTPException(405, '完整资料仅供查询')
        from app.services.qc_dossier_read import detail as dossier_detail
        identity = asset_path.removeprefix('api/inspection-dossier/records/')
        result = await run_in_threadpool(dossier_detail, factory_id, identity,
            full_business=can(user, 'customer_order:read', factory_id, 'sales-business'))
        reports = result['reportSupplements']
        rows = reports['items'] + reports['changes']
        actor_ids = sorted({row['actor']['id'] for row in rows if row['actor']['id']})
        names = {}
        for i in range(0, len(actor_ids), 200):
            for actor_id, name in db.execute(select(AuthUser.id, AuthUser.display_name).where(
                AuthUser.id.in_(actor_ids[i:i+200]))):
                names[actor_id] = name
        for row in rows:
            if name := names.get(row['actor']['id']):
                row['actor']['name'] = name
        return JSONResponse(result, headers=NO_CACHE)
    if asset_path == "api/schedule-source" and request.method == "GET":
        from app.services import qc_schedule_view
        if set(request.query_params) - {'dateFrom', 'dateTo'} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            raise HTTPException(422, '排期日期参数不正确')
        return JSONResponse(qc_schedule_view.listing(db, factory_id,
            date_from=request.query_params.get('dateFrom', ''),
            date_to=request.query_params.get('dateTo', '')), headers=NO_CACHE)
    if request.method == 'GET' and asset_path in {
        'api/daily-report', 'api/weekly-templates', 'api/monthly-templates',
        'api/issue-reports', 'api/approved-statistics/report',
    }:
        from app.services.qc_report_workbook import warm_on_report_visit
        warm_on_report_visit()
    if asset_path == 'api/report-workbook/photo':
        if request.method not in {'GET', 'HEAD'}:
            raise HTTPException(405, '报表照片仅供读取')
        params = request.query_params
        if (set(params) != {'entry', 'revision', 'photo'} or any(len(params.getlist(k)) != 1 for k in params)
                or not re.fullmatch(r'[0-9]{1,18}', params['revision'])):
            raise HTTPException(422, '报表照片参数不正确')
        content, mime = await run_in_threadpool(qc_monthly_excel.approved_photo, factory_id,
            params['entry'], int(params['revision']), params['photo'])
        return Response(content if request.method == 'GET' else b'', media_type=mime,
                        headers={**NO_CACHE, 'Content-Length': str(len(content))})
    if asset_path in {'api/report-workbook', 'api/report-workbook/save'}:
        from app.services import qc_report_workbook
        params = request.query_params
        expected = {'kind', 'day', 'customer'}
        if params.get('kind') == 'annual-stats':
            expected.add('result')
        if set(params) != expected or any(len(params.getlist(k)) != 1 for k in params):
            raise HTTPException(422, '工作簿预览参数不正确')
        scope = (factory_id, params['kind'], params['day'], params['customer'])
        if asset_path == 'api/report-workbook' and request.method in {'GET', 'HEAD'}:
            result = await run_in_threadpool(qc_report_workbook.preview, *scope,
                can(user, 'qc_inspection:result_write', factory_id, 'qc'), params.get('result', 'FAIL'))
            if request.method == 'HEAD':
                return Response(status_code=204, headers=NO_CACHE)
            return await run_in_threadpool(qc_report_workbook.preview_response, result,
                                           request.headers.get('accept-encoding', ''), NO_CACHE)
        if asset_path != 'api/report-workbook/save' or request.method != 'POST':
            raise HTTPException(405, '不支持此操作')
        _ensure_permission(db, user, 'qc_inspection:result_write', factory_id)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, '不接受跨站写入')
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, '请使用 JSON 提交')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 32 * 1024:
                raise HTTPException(413, '提交内容过大')
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise HTTPException(400, '无效 JSON') from None
        result = await run_in_threadpool(qc_report_workbook.save_record, scope[0], {'id': user.id}, *scope[1:],
                                         params.get('result', 'FAIL'), body)
        return JSONResponse(result, headers=NO_CACHE)
    if asset_path in {"api/daily-report", "api/daily-report/export"} and request.method == "GET":
        exporting = asset_path.endswith("/export")
        keys = {"date", "revision"} if exporting else {"date"}
        if exporting and "hideEmptyCols" in request.query_params:
            keys.add("hideEmptyCols")
            if request.query_params["hideEmptyCols"] not in {"0", "1"}:
                raise HTTPException(422, "hideEmptyCols 仅接受 0 或 1")
        if "customer" in request.query_params:
            keys.add("customer")
        if "period" in request.query_params:
            keys.add("period")
        if set(request.query_params) != keys or any(len(request.query_params.getlist(key)) != 1 for key in keys):
            raise HTTPException(422, "日报参数不正确")
        if exporting:
            _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
        report = await run_in_threadpool(qc_daily_report.report, factory_id, request.query_params["date"], request.query_params.get("period", "daily"), request.query_params.get("customer", ""))
        if not exporting:
            return JSONResponse(report, headers=NO_CACHE)
        if request.query_params["revision"] != report["revision"] or not report["total"]:
            raise HTTPException(409, "日报记录已变化或为空，请重新读取后导出")
        columns = empty_cols.hidden('daily', report['rows']) if request.query_params.get("hideEmptyCols") == "1" else []
        content = await run_in_threadpool(qc_daily_report.workbook, report, columns)
        label = {"daily": "每日", "weekly": "每周", "monthly": "每月"}[report["period"]]
        name = quote(f"{label}验货情况统计表_{report['dateFrom']}_{report['dateTo']}.xlsx", safe="")
        return Response(content, media_type=qc_inspection_sheet.MIME, headers={**NO_CACHE,
            "X-QC-Hidden-Columns": quote(json.dumps([report['headers'][i-1] for i in columns], ensure_ascii=False), safe=''),
            "Content-Disposition": "attachment; filename=QC-daily.xlsx; filename*=UTF-8''" + name})
    if asset_path in {"api/issue-reports", "api/issue-reports/excel"}:
        return await issue_reports_request(asset_path, request, db, user, factory_id)
    if asset_path in {"api/monthly-templates", "api/monthly-templates/save", "api/monthly-templates/excel"} or asset_path.startswith('api/monthly-templates/excel/'):
        return await monthly_templates_request(asset_path, request, db, user, factory_id)
    if asset_path in {"api/weekly-templates", "api/weekly-templates/save", "api/weekly-templates/excel"} or asset_path.startswith('api/weekly-templates/excel/'):
        return await weekly_templates_request(asset_path, request, db, user, factory_id)
    if asset_path == "api/approved-statistics/report/excel":
        if request.method != "GET":
            raise HTTPException(405, "年报只支持下载")
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
        args = dict(request.query_params)
        if "hideEmptyCols" in args:
            if len(request.query_params.getlist("hideEmptyCols")) != 1 or args.pop("hideEmptyCols") not in ("0", "1"):
                raise HTTPException(422, "hideEmptyCols 仅接受 0 或 1")
        if (set(args) != {"year", "customer", "result", "revision"} or not args["year"]
                or any(len(request.query_params.getlist(k)) != 1 for k in args)):
            raise HTTPException(422, "年报导出参数不正确")
        revision = args.pop("revision")
        report = await run_in_threadpool(qc_approved_statistics.report, factory_id, args, all_detail_rows=True)
        if report["revision"] != revision or not report["totals"]["total"]:
            raise HTTPException(409, "年报数据已变化或为空，请刷新后导出")
        from app.services.qc_annual_excel import workbook
        content = await run_in_threadpool(workbook, report)
        name = quote(f"{factory_label(factory_id)}{report['filters']['year']}年验货统计表.xlsx", safe="")
        return Response(content, media_type=qc_inspection_sheet.MIME, headers={**NO_CACHE,
            "Content-Disposition": "attachment; filename=QC-annual.xlsx; filename*=UTF-8''" + name})
    stats_handlers = {
        "api/approved-statistics": qc_approved_statistics.query,
        "api/approved-statistics/report": qc_approved_statistics.report,
        "api/approved-statistics/dashboard": qc_approved_statistics.dashboard,
    }
    if asset_path in stats_handlers and request.method == "GET":
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise HTTPException(422, "统计筛选参数不能重复")
        handler = stats_handlers[asset_path]
        return JSONResponse(await run_in_threadpool(handler, factory_id,
            dict(request.query_params)), headers=NO_CACHE)
    if asset_path.startswith("api/workflow/"):
        return await workflow_request(asset_path.removeprefix("api/workflow/"), request, db, user, factory_id)
    if asset_path.startswith("api/inspection-summary/"):
        return await inspection_summary_request(asset_path.removeprefix("api/inspection-summary/"), request, db, user, factory_id)
    if asset_path.startswith("api/inspection-sheet/"):
        return await inspection_sheet_request(asset_path.removeprefix("api/inspection-sheet/"), request, db, user, factory_id)
    if asset_path.startswith("api/schedule-example"):
        raise HTTPException(410,"示例功能已移除")
    if asset_path == "nexus-context.js" and request.method == "GET":
        context = json.dumps(ui_context(user, factory_id), ensure_ascii=True).replace("<", "\\u003c")
        return Response("window.__QC_NEXUS = " + context + ";", media_type="text/javascript", headers=NO_CACHE)
    if not asset_path.startswith("api/"):
        target = (ASSETS / asset_path).resolve()
        vendor = (asset_path.startswith("vendor/") and target.is_relative_to((ASSETS / "vendor").resolve())
                  and target.suffix in {".js", ".wasm", ".gz"})
        if (request.method not in {"GET", "HEAD"} or not target.is_relative_to(ASSETS.resolve())
                or (asset_path not in STATIC_FILES and not vendor) or not target.is_file()):
            raise HTTPException(404, "资源不存在")
        headers = {**NO_CACHE, "X-Frame-Options": "SAMEORIGIN"}
        if asset_path in EMPTY_ART_FILES:
            headers["Cache-Control"] = "private, max-age=86400"
        return FileResponse(target, headers=headers)
    if request.method == "POST":
        permission = WRITE_PERMISSIONS.get(asset_path)
        if not permission:
            raise HTTPException(404, "此操作未开放；账号由 Nexus 统一管理")
        # Browser writes must be JSON; cross-site HTML forms cannot use this gateway.
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "请使用 JSON 提交")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "不接受跨站写入")
        _ensure_permission(db, user, permission, factory_id)
        if asset_path in {"api/records", "api/records/delete", "api/records/replace", "api/reference-data/clear"}:
            # QC_department syncs complete records rather than separate order/event
            # resources. Both operations are required until that contract is split.
            _ensure_permission(db, user, "qc_inspection:order_write", factory_id)
        if asset_path in {"api/records/delete", "api/records/replace", "api/reference-data/clear"}:
            _ensure_permission(db, user, "qc_inspection:customer_manage", factory_id)
            _ensure_permission(db, user, "qc_inspection:record_delete", factory_id)
    elif request.method not in {"GET", "HEAD"} or asset_path not in READ_ENDPOINTS:
        raise HTTPException(404, "接口不存在")
    if asset_path.startswith("api/export/"):
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32 * 1024 * 1024:
            raise HTTPException(413, "提交内容超过 32 MB")
    legacy_write = request.method == "POST" and asset_path in WRITE_PERMISSIONS and asset_path != "api/ai/ocr-extract"
    removed_keys = []
    if legacy_write:
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "无效 JSON")
    if asset_path in {"api/records", "api/records/replace"} and request.method == "POST":
        if payload.get("deletedIds"):
            _ensure_permission(db, user, "qc_inspection:record_delete", factory_id)
            _ensure_permission(db, user, "qc_inspection:customer_manage", factory_id)
        if not isinstance(payload.get("deletedIds", []), list) or any(
            type(val) is not int or not 0 < val <= 9007199254740991 for val in payload.get("deletedIds", [])
        ):
            raise HTTPException(422, "删除编号必须为正整数")
        if not isinstance(payload.get("records", [] if asset_path == "api/records" else None), list):
            raise HTTPException(422, "缺少有效的记录列表")
        if payload.get('records'):
            existing_response = await upstream('GET','api/bootstrap',[('company',company)],b'')
            if existing_response.status_code != 200: raise HTTPException(503,'无法核对历史记录锁定状态')
            existing = {r['id']:r for r in existing_response.json().get('records',[])}
            for r in payload.get('records',[]):
                if not isinstance(r, dict) or type(r.get('id')) is not int or not 0 < r['id'] <= 9007199254740991:
                    raise HTTPException(400, '记录 ID 必须为正整数')
                prev=existing.get(r.get('id'))
                if prev and r.get('qc', '') != prev.get('qc', ''):
                    raise HTTPException(409, '检验员由登录账号绑定，不能手动修改')
                if not prev: r['qc'] = user.display_name or user.username
                if prev and _legacy_status(r) != _legacy_status(prev):
                    raise HTTPException(409,'请通过审核中心或验货表单变更状态')
                if (asset_path == 'api/records' and prev
                        and _legacy_status(prev) in {'pending','approved'} and r != prev):
                    raise HTTPException(409,'已提交记录锁定，请由主管退回后修改')
        links = qc_workflow.legacy_links(factory_id)
        if set(payload.get("deletedIds", [])) & set(links):
            raise HTTPException(409, "记录已进入验货修订流程，不能通过历史同步删除")
        if links:
            payload['records'] = [r for r in payload.get('records', []) if r.get('id') not in links]
    if asset_path in {"api/defects", "api/partners"} and request.method == "POST":
        key = "defectLib" if asset_path == "api/defects" else "partners"
        if "baseRevision" in payload and not (
            type(payload["baseRevision"]) is int and 0 <= payload["baseRevision"] <= 9007199254740991
        ):
            raise HTTPException(422, "名单版本必须为非负整数")
        if not isinstance(payload.get(key), list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip()
            for item in payload[key]
        ):
            raise HTTPException(422, "请提交完整有效的名单")
        existing_response = await upstream("GET", "api/bootstrap", [("company", company)], b"")
        if existing_response.status_code != 200:
            raise HTTPException(503, "无法核对现有配置，请重试")
        existing_data = existing_response.json()
        current_revision = (existing_data.get("catalogVersions") or {}).get(key)
        if "baseRevision" in payload and current_revision is not None and payload["baseRevision"] != current_revision:
            raise HTTPException(409, "名单已在其他窗口更新，请刷新后重试")
        if asset_path == "api/defects" and isinstance(payload.get("defectLib"), list):
            existing_defects = existing_data.get("defectLib") or []
            old_names = {str(d.get("name") or "").strip() for d in existing_defects if isinstance(d, dict) and str(d.get("name") or "").strip()}
            new_names = {str(d.get("name") or "").strip() for d in payload["defectLib"] if isinstance(d, dict) and str(d.get("name") or "").strip()}
            removed_names = old_names - new_names
            if removed_names:
                _ensure_permission(db, user, "qc_inspection:record_delete", factory_id)
                removed_keys = [[name] for name in removed_names]
                referenced = await run_in_threadpool(qc_inspection_sheet.referenced_defect_names, factory_id)
                for rec in existing_data.get("records") or []:
                    if not isinstance(rec, dict):
                        continue
                    for item in rec.get("defects") or []:
                        if isinstance(item, dict):
                            desc = str(item.get("desc") or "").strip()
                            if desc:
                                referenced.add(desc)
                    raw_defect = str(rec.get("defect") or "").strip()
                    if raw_defect:
                        referenced.add(raw_defect)
                        for token in re.split(r"[，,;；、/\n]+", raw_defect):
                            cleaned = token.strip()
                            if cleaned:
                                referenced.add(cleaned)
                blocked = sorted(removed_names & referenced)
                if blocked:
                    raise HTTPException(409, f"不良描述「{'、'.join(blocked[:3])}」已被历史验货记录引用，无法删除；请改用「停用」以保留历史追溯")
        if asset_path == "api/partners" and isinstance(payload.get("partners"), list):
            existing_partners = existing_data.get("partners") or []
            old_pairs = {(str(p.get("type") or "").strip(), str(p.get("name") or "").strip()) for p in existing_partners if isinstance(p, dict) and str(p.get("name") or "").strip()}
            new_pairs = {(str(p.get("type") or "").strip(), str(p.get("name") or "").strip()) for p in payload["partners"] if isinstance(p, dict) and str(p.get("name") or "").strip()}
            if old_pairs - new_pairs:
                _ensure_permission(db, user, "qc_inspection:record_delete", factory_id)
                removed_keys = [list(pair) for pair in old_pairs - new_pairs]
    if asset_path == 'api/records/delete' and request.method == 'POST':
        deleting = payload.get('ids', [])
        if not isinstance(deleting, list) or any(type(i) is not int or not 0 < i <= 9007199254740991 for i in deleting):
            raise HTTPException(422, '删除编号必须为正整数')
        if set(deleting) & set(qc_workflow.legacy_links(factory_id)): raise HTTPException(409,'修订中的历史记录不能删除')
    if asset_path == 'api/records/replace' and request.method == 'POST' and qc_workflow.legacy_links(factory_id):
        raise HTTPException(409, '已有历史记录进入验货修订流程，不能批量清除或替换历史库')
    if legacy_write:
        payload["_qc"] = {"actor": user.id, "removed": removed_keys}
        if asset_path in {"api/defects", "api/partners"} and "baseRevision" in payload:
            payload["_qc"]["baseRevision"] = payload["baseRevision"]
        if asset_path in {"api/records/delete", "api/records/replace", "api/reference-data/clear"} or payload.get("deletedIds"):
            payload["_qc"]["protectedIds"] = await run_in_threadpool(qc_inspection_sheet.submitted_legacy_ids, factory_id)
        body = json.dumps(payload).encode()
    params = [(k, v) for k, v in request.query_params.multi_items() if k != "company"]
    params.append(("company", company))
    export_records = qc_workflow.ledger_records(db, factory_id) if asset_path.startswith('api/export/') else []
    plan_export = asset_path.startswith('api/export/') and request.query_params.get('dateBasis') == 'inspection-plan'
    if export_records or plan_export:
        export_body={'records':export_records,'hiddenIds':list(qc_workflow.legacy_links(factory_id))}
        if plan_export:
            snapshot = await upstream('GET', 'api/bootstrap', [('company',company)], b'')
            if snapshot.status_code != 200:
                raise HTTPException(503, '验货日期来源读取失败，请重试')
            export_body['inspectionPlans'] = inspection_plan_dates(factory_id, snapshot.json().get('records', []))
        result=await upstream('POST',asset_path,params,json.dumps(export_body).encode())
    else:
        result = await upstream(request.method, asset_path, params, bytes(body))
    if asset_path == "api/bootstrap" and result.status_code == 200:
        payload = result.json()
        # An older private service may still return its legacy account data.
        payload.pop("users", None)
        payload["testEntryIds"] = [r["id"] for r in payload.get("records", []) if qc_workflow.test_entry_allowed(factory_id, r)]
        payload["inspectionPlans"] = inspection_plan_dates(factory_id, payload.get("records", []), payload["testEntryIds"])
        return JSONResponse(payload, headers=NO_CACHE)
    if asset_path == "api/ai/status" and result.status_code == 200:
        return JSONResponse({"ready": bool(result.json().get("ready"))}, headers=NO_CACHE)
    headers = {**NO_CACHE, **{k: v for k, v in result.headers.items()
                            if k.lower() in {"content-type", "content-disposition"}}}
    return Response(result.content, status_code=result.status_code, headers=headers)


async def weekly_templates_request(path, request, db, user, factory_id):
    exporting = path.startswith('api/weekly-templates/excel')
    owner = factory_id + ':' + hashlib.sha256(f'{user.id}:{user.authorization_version}'.encode()).hexdigest()[:32]
    if exporting:
        _ensure_permission(db, user, 'qc_inspection:report_export', factory_id)
    if path.startswith('api/weekly-templates/excel/') and request.method in {'GET', 'HEAD'}:
        content, filename = await run_in_threadpool(qc_weekly_excel.download, owner, path.removeprefix('api/weekly-templates/excel/'))
        return Response(content if request.method == 'GET' else b'', media_type=qc_weekly_excel.MIME, headers={**NO_CACHE,
            'Content-Disposition': 'attachment; filename=QC-weekly.xls; filename*=UTF-8\'\''+quote(filename, safe=''),
            'Content-Length': str(len(content)), 'Referrer-Policy': 'no-referrer'})
    if path == 'api/weekly-templates' and request.method == 'GET':
        keys = set(request.query_params)
        if 'date' not in keys or keys - {'date', 'customer'} or any(len(request.query_params.getlist(k)) != 1 for k in keys):
            raise HTTPException(422, '周报模板查询参数不正确')
        data = await run_in_threadpool(qc_weekly_templates.query, factory_id,
            request.query_params['date'], request.query_params.get('customer', ''))
        data['canEdit'] = can(user, 'qc_inspection:result_write', factory_id, 'qc')
        data['canExport'] = can(user, 'qc_inspection:report_export', factory_id, 'qc')
        return JSONResponse(data, headers=NO_CACHE)
    if path not in {'api/weekly-templates/save', 'api/weekly-templates/excel'} or request.method != 'POST':
        raise HTTPException(405, '不支持此操作')
    if not exporting:
        _ensure_permission(db, user, 'qc_inspection:result_write', factory_id)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '不接受跨站写入')
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, '请使用 JSON 提交')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > (2 * 1024 * 1024 if exporting else 32 * 1024):
            raise HTTPException(413, '提交内容过大')
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, '无效 JSON') from None
    if exporting:
        result = await run_in_threadpool(qc_weekly_excel.prepare, factory_id, owner, body)
    else:
        result = await run_in_threadpool(qc_weekly_templates.save, factory_id,
            {'id': user.id, 'name': user.display_name or user.username}, body)
    return JSONResponse(result, headers=NO_CACHE)


async def issue_reports_request(path, request, db, user, factory_id):
    from app.services import qc_issue_reports
    if path=='api/issue-reports' and request.method=='GET':
        keys=set(request.query_params)
        if not {'date','period'}<=keys or keys-{'date','period','customer'} or any(len(request.query_params.getlist(k))!=1 for k in keys):
            raise HTTPException(422,'图文报表查询参数不正确')
        data=await run_in_threadpool(qc_issue_reports.query,factory_id,request.query_params['date'],request.query_params['period'],request.query_params.get('customer',''))
        data['canExport']=can(user,'qc_inspection:report_export',factory_id,'qc')
        return JSONResponse(data,headers=NO_CACHE)
    if path!='api/issue-reports/excel' or request.method!='POST':raise HTTPException(405,'不支持此操作')
    _ensure_permission(db,user,'qc_inspection:report_export',factory_id)
    if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'不接受跨站写入')
    if request.headers.get('content-type','').split(';')[0].lower()!='application/json':raise HTTPException(415,'请使用 JSON 提交')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>32768:raise HTTPException(413,'请求过大')
    try:body=json.loads(raw)
    except (ValueError,UnicodeError):raise HTTPException(400,'无效 JSON') from None
    owner=factory_id+':'+hashlib.sha256(f'{user.id}:{user.authorization_version}'.encode()).hexdigest()[:32]
    result=await run_in_threadpool(qc_issue_reports.prepare,factory_id,owner,body)
    return JSONResponse(result,headers=NO_CACHE)


async def monthly_templates_request(path, request, db, user, factory_id):
    exporting = path.startswith('api/monthly-templates/excel')
    owner = factory_id + ':' + hashlib.sha256(f'{user.id}:{user.authorization_version}'.encode()).hexdigest()[:32]
    if exporting:
        _ensure_permission(db, user, 'qc_inspection:report_export', factory_id)
    if path.startswith('api/monthly-templates/excel/') and request.method in {'GET', 'HEAD'}:
        content, filename = await run_in_threadpool(qc_monthly_excel.download, owner, path.removeprefix('api/monthly-templates/excel/'))
        return Response(content if request.method == 'GET' else b'', media_type=('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if filename.endswith('.xlsx') else 'application/vnd.ms-excel'), headers={**NO_CACHE,
            'Content-Disposition': 'attachment; filename=QC-monthly.xls; filename*=UTF-8\'\''+quote(filename, safe=''),
            'Content-Length': str(len(content)), 'Referrer-Policy': 'no-referrer'})
    if path == 'api/monthly-templates' and request.method == 'GET':
        keys = set(request.query_params)
        if 'date' not in keys or keys - {'date', 'customer','template'} or request.query_params.get('template') not in (None,'overview',*qc_monthly_templates.design.NAMES) or any(len(request.query_params.getlist(k)) != 1 for k in keys):
            raise HTTPException(422, '月报模板查询参数不正确')
        data = await run_in_threadpool(qc_monthly_templates.query, factory_id,
            request.query_params['date'], request.query_params.get('customer', ''),request.query_params.get('template')=='overview',
            request.query_params.get('template') if request.query_params.get('template') in qc_monthly_templates.design.NAMES else None)
        data['canEdit'] = can(user, 'qc_inspection:result_write', factory_id, 'qc')
        data['canExport'] = can(user, 'qc_inspection:report_export', factory_id, 'qc')
        return JSONResponse(data, headers=NO_CACHE)
    if path not in {'api/monthly-templates/save', 'api/monthly-templates/excel'} or request.method != 'POST':
        raise HTTPException(405, '不支持此操作')
    if not exporting:
        _ensure_permission(db, user, 'qc_inspection:result_write', factory_id)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '不接受跨站写入')
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, '请使用 JSON 提交')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > (2 * 1024 * 1024 if exporting else 32 * 1024):
            raise HTTPException(413, '提交内容过大')
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, '无效 JSON') from None
    if exporting:
        result = await run_in_threadpool(qc_monthly_excel.prepare, factory_id, owner, body)
    else:
        result = await run_in_threadpool(qc_monthly_templates.save, factory_id,
            {'id': user.id, 'name': user.display_name or user.username}, body)
    return JSONResponse(result, headers=NO_CACHE)


async def inspection_sheet_request(path, request, db, user, factory_id):
    service = qc_inspection_sheet
    parts = path.split('/')
    actor = {'id': user.id, 'name': user.display_name or user.username}
    notification_actions = {'review/notifications': 'revoke', 'entries/notifications': 'return-to-inspection'}
    async def current_entries(copy_photos=True, view="workbench"):
        response=await upstream('GET','api/bootstrap',[('company',COMPANIES[factory_id])],b'')
        if response.status_code!=200:raise HTTPException(503,'验货基础数据读取失败，请重试')
        data=response.json()
        examples=schedule_example(factory_id, missing_ok=True)['items'] if factory_id=='huaxing' else []
        source_rows=qc_workflow.sources(db,factory_id)['items']
        tasks=qc_workflow.list_tasks(db,factory_id)['items']
        rows=service.candidates(factory_id,data.get('records',[]),tasks,
            source_rows,examples,data.get('referenceData',{}).get('ids',[]))
        result=await run_in_threadpool(service.sync,factory_id,rows,copy_photos)
        cancelled={r['id'] for r in source_rows if r.get('sourceStatus')=='cancelled'}
        all_items=result['items']
        task_methods={task['id']:task['method'] for task in tasks if task.get('methodConfirmed') is not False}
        for item in all_items:item['inspectionMethod']=task_methods.get(item.get('workflowId'),'')
        for item in all_items:item['sourceCancelled']=item.get('sourceId') in cancelled or (item.get('sourceRecord') or {}).get('sourceStatus')=='cancelled'
        if view=='review':
            result['items']=[r for r in all_items if r.get('reviewState') in {'pending','approved'} or r.get('legacyCompleted')]
            # The inspection sheet supports self-review under result_write.
            # The separate supervisor workflow keeps its own review permission.
            if has_permission_in_scope(user, 'qc_inspection:result_write', factory_id, 'qc'):
                reads = await run_in_threadpool(service.review_read_versions, factory_id, user.id)
                for item in result['items']:
                    if item.get('reviewState') == 'pending':
                        item['reviewRead'] = reads.get(item['id']) == item['revision']
        else:
            result['items']=service.workbench_items(all_items)
        return result
    if request.method in {'GET','HEAD'}:
        if path == 'options' and request.method == 'GET':
            from app.services import qc_options
            return JSONResponse(qc_options.choices(factory_id, actor), headers=NO_CACHE)
        if path == 'entries' and request.method == 'GET':
            return JSONResponse(await current_entries(),headers=NO_CACHE)
        if path in notification_actions and request.method=='GET':
            result = await run_in_threadpool(service.review_notifications, factory_id, actor, action=notification_actions[path])
            return JSONResponse(result, headers=NO_CACHE)
        if path=='review/entries' and request.method=='GET':
            return JSONResponse(await current_entries(view='review'),headers=NO_CACHE)
        if len(parts)==3 and parts[0]=='entries' and parts[2]=='audit':
            return JSONResponse(service.audit(factory_id,parts[1]),headers=NO_CACHE)
        if len(parts)==3 and parts[0]=='entries' and parts[2]=='photo-info' and request.method=='GET':
            result = await run_in_threadpool(service.photo_info, factory_id, parts[1])
            return JSONResponse(result, headers=NO_CACHE)
        if len(parts)==4 and parts[0]=='entries' and parts[2]=='photos':
            if set(request.query_params)-{'variant'} or len(request.query_params.getlist('variant'))>1:raise HTTPException(422,'照片参数不正确')
            content,mime=await run_in_threadpool(service.read_photo_version,factory_id,parts[1],parts[3],request.query_params.get('variant','preview'))
            # Revalidate authentication, factory, active photo and bytes before 304.
            # Private cache avoids downloading unchanged originals again.
            etag='"'+hashlib.sha256(content).hexdigest()+'"'
            headers={'Cache-Control':'private, no-cache','ETag':etag,'X-Content-Type-Options':'nosniff','Vary':'Cookie, Authorization'}
            if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers=headers)
            return Response(content if request.method=='GET' else b'',media_type=mime,headers=headers)
        raise HTTPException(404,'接口不存在')
    if request.method != 'POST':raise HTTPException(405,'不支持此方法')
    if path in {'intake/preview', 'intake/import', 'intake/manual'}:
        return await inspection_intake_request(path, request, db, user, factory_id, actor)
    exporting = path in {'print-preview', 'schedule-excel'}
    deleting = path in {'entries/delete', 'review/delete'}
    if deleting:
        _ensure_permission(db, user, 'qc_inspection:record_delete', factory_id)
    else:
        _ensure_permission(db, user, 'qc_inspection:report_export' if exporting else 'qc_inspection:result_write', factory_id)
    if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'不接受跨站写入')
    if request.headers.get('content-type','').split(';')[0].lower()!='application/json':raise HTTPException(415,'请使用 JSON 提交')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>(15*1024*1024 if path.endswith('/photos') else 1024*1024):raise HTTPException(413,'提交内容过大')
    try:
        body=json.loads(raw)
        if not isinstance(body,dict):raise ValueError()
    except (ValueError,UnicodeError):raise HTTPException(400,'无效 JSON') from None
    if path == 'schedule-excel':
        from app.services import qc_inspection_schedule_excel
        content = await run_in_threadpool(qc_inspection_schedule_excel.export, factory_id, body)
        return Response(content, media_type=service.MIME, headers={**NO_CACHE,
            'Content-Disposition': "attachment; filename=QC-schedule.xlsx; filename*=UTF-8''" + quote('客户验货排期表.xlsx')})
    if path == 'print-preview':
        from app.services import qc_inspection_print
        result = await run_in_threadpool(qc_inspection_print.preview, factory_id, body)
        return JSONResponse(result, headers=NO_CACHE)
    notification_action = notification_actions.get(path.removesuffix('/shown')) if path.endswith('/shown') else None
    if notification_action:
        result = await run_in_threadpool(service.review_notifications, factory_id, actor, body, action=notification_action)
    elif path == 'review/mark-read':
        result = await run_in_threadpool(service.mark_review_read, factory_id, user.id, body)
    elif path in {'review/confirm','review/revoke'}:
        result=await run_in_threadpool(service.review_batch,factory_id,parts[1],body,actor)
    elif path in {'entries/delete','review/delete'}:
        scope = 'workbench' if path == 'entries/delete' else 'pending'
        result = await run_in_threadpool(service.delete_batch, factory_id, scope, body, actor)
        legacy_ids = []
        for item in result['results']:
            if not item.get('ok'):
                continue
            if isinstance(item.get('legacyId'), int):
                legacy_ids.append(item['legacyId'])
        if legacy_ids:
            cleanup = await upstream(
                'POST', 'api/records/delete', [('company', COMPANIES[factory_id])],
                json.dumps({'ids': legacy_ids, '_qc': {'actor': user.id, 'sheetReceipt': True}}).encode(),
            )
            if not cleanup.is_success:
                raise HTTPException(503, '历史库归档尚未确认，请重试同一删除请求')
    elif (len(parts)==3 and parts[0]=='entries' or len(parts)==4 and parts[:2]==['review','entries']) and parts[-1]=='photo-annotations':
        result=await run_in_threadpool(service.save_photo_annotations,factory_id,parts[-2],body,actor,review=len(parts)==4)
    elif len(parts)==4 and parts[:2]==['review','entries'] and parts[3] in {'save','photos','remove-photo'}:
        method={'save':service.save,'photos':service.add_photo,'remove-photo':service.remove_photo}[parts[3]]
        result=await run_in_threadpool(method,factory_id,parts[2],body,actor,review=True)
    elif len(parts)==4 and parts[:2]==['review','entries'] and parts[3]=='return-to-inspection':
        source_rows=qc_workflow.sources(db,factory_id)['items']
        result=await run_in_threadpool(service.return_to_inspection,factory_id,parts[2],body,actor,source_rows)
    elif len(parts)==3 and parts[0]=='entries' and parts[2] in {'save','photos','remove-photo','submit'}:
        method={'save':service.save,'photos':service.add_photo,'remove-photo':service.remove_photo,'submit':service.submit}[parts[2]]
        if parts[2]=='photos':
            result=await run_in_threadpool(method,factory_id,parts[1],body,actor,include_upload_id=True)
        else:
            result=method(factory_id,parts[1],body,actor)
    else:raise HTTPException(404,'接口不存在')
    return JSONResponse(result,headers=NO_CACHE)


async def inspection_intake_request(path, request, db, user, factory_id, actor):
    from app.services import qc_inspection_intake as intake

    for permission in ('order_write', 'result_write'):
        _ensure_permission(db, user, 'qc_inspection:' + permission, factory_id)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '不接受跨站写入')
    manual = path == 'intake/manual'
    expected_type = 'application/json' if manual else 'application/octet-stream'
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != expected_type:
        raise HTTPException(415, '请使用验货台新增窗口上传')
    limit = 128 * 1024 if manual else intake.MAX_BYTES
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(413, '提交内容过大')
    if manual:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise HTTPException(400, '无效 JSON') from None
        result = await run_in_threadpool(intake.manual, factory_id, actor, body)
    else:
        digest = request.headers.get('x-qc-preview-digest', '') if path == 'intake/import' else None
        result = await run_in_threadpool(intake.workbook, factory_id, actor, bytes(raw), digest)
    return JSONResponse(result, headers=NO_CACHE)


async def workflow_request(path, request, db, user, factory_id):
    """The actor-bound gateway has already checked the authenticated factory."""
    actor = {"id": user.id, "name": user.display_name or user.username}
    parts = path.split("/")
    if request.method == "GET":
        if len(parts) == 2 and parts[0] == "exports":
            _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
            return Response(qc_workflow.download_export(factory_id, user.id, parts[1]), media_type="application/zip",
                headers={**NO_CACHE, "Content-Disposition": "attachment; filename=QC-inspection-package.zip"})
        if path == "tasks":
            return JSONResponse(qc_workflow.list_tasks(db, factory_id), headers=NO_CACHE)
        if path == "projections":
            return JSONResponse({"items": qc_workflow.projections(db, factory_id)}, headers=NO_CACHE)
        if len(parts) == 2 and parts[0] == "tasks":
            return JSONResponse(qc_workflow.detail(db, factory_id, parts[1]), headers=NO_CACHE)
        if len(parts) == 4 and parts[0] == "tasks" and parts[2] == "files":
            f = qc_workflow.read_file(factory_id, parts[1], parts[3])
            disposition = "attachment" if request.query_params.get("download") == "1" else "inline"
            return Response(f["content"], media_type=f["mime"], headers={**NO_CACHE,
                "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(f["name"], safe=""),
                "Content-Security-Policy": "sandbox; default-src 'none'"})
        raise HTTPException(404, "接口不存在")
    if request.method != "POST":
        raise HTTPException(405, "不支持此方法")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise HTTPException(415, "请使用 JSON 提交")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "不接受跨站写入")
    if path in {"tasks", "schedules"}:
        _ensure_permission(db, user, "qc_inspection:schedule_write", factory_id)
        _ensure_permission(db, user, "qc_inspection:order_write", factory_id)
    elif path == "legacy-review":
        _ensure_permission(db, user, "qc_inspection:review", factory_id)
    elif path in {"manual", "legacy"}:
        _ensure_permission(db, user, "qc_inspection:result_write", factory_id)
        _ensure_permission(db, user, "qc_inspection:order_write", factory_id)
    elif path in {"export", "export-prepare"}:
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
    elif len(parts) == 3 and parts[0] == "tasks":
        permission = "review" if parts[2] in {"approve", "return", "reopen"} else "result_write"
        _ensure_permission(db, user, "qc_inspection:" + permission, factory_id)
    else:
        raise HTTPException(404, "接口不存在")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > (15 * 1024 * 1024 if path.endswith("/attach") else 512 * 1024):
            raise HTTPException(413, "提交内容过大")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(400, "无效 JSON") from None
    if path == "schedules":
        result = qc_workflow.create_schedule(factory_id,body,actor)
    elif path == "tasks":
        result = qc_workflow.create_tasks(db, factory_id, body, actor)
    elif path == "legacy-review":
        if set(body) != {'recordId','updatedAt','action','reason'} or body['action'] not in {'approve','return'}:
            raise HTTPException(422, '审核字段不正确')
        if body['recordId'] in qc_workflow.legacy_links(factory_id):
            raise HTTPException(409, '该记录已接入验货修订，请刷新后在新表单审核')
        response = await upstream('GET','api/bootstrap',[('company',COMPANIES[factory_id])],b'')
        if response.status_code != 200: raise HTTPException(503, '历史记录读取失败')
        record = next((r for r in response.json().get('records',[]) if type(body['recordId']) is int and r['id']==body['recordId']), None)
        if not record: raise HTTPException(404,'历史记录不存在')
        if (record.get('updatedAt') or '') != body['updatedAt']: raise HTTPException(409,'记录已变化，请刷新核对')
        action=body['action'];reason=qc_workflow.text(body['reason']);stamp=qc_workflow.now()
        status = _legacy_status(record)
        if action=='approve' and status!='pending': raise HTTPException(409,'只有已提交的记录可审批')
        if action=='return' and (not reason or status not in {'pending','approved'}): raise HTTPException(409,'请检查记录状态并填写退回原因')
        record.update(status='approved' if action=='approve' else 'rejected',updatedAt=stamp,
            reviewBy=actor['name'] if action=='approve' else '',reviewAt=stamp if action=='approve' else '',
            rejectReason=reason if action=='return' else '',rejectBy=actor['name'] if action=='return' else '',rejectAt=stamp if action=='return' else '')
        saved=await upstream('POST','api/records',[('company',COMPANIES[factory_id])],json.dumps({'records':[record]}).encode())
        if saved.status_code!=200: raise HTTPException(503,'审核保存未确认，请刷新核对')
        result=record
    elif path == "manual":
        result = qc_workflow.create_entry(factory_id, body, actor)
    elif path == "legacy":
        response = await upstream("GET", "api/bootstrap", [("company", COMPANIES[factory_id])], b"")
        if response.status_code != 200:
            raise HTTPException(503, "历史记录读取失败，请重试")
        data = response.json()
        record = next((r for r in data.get("records", []) if type(body.get("recordId")) is int and r["id"] == body["recordId"]), None)
        if record is None: raise HTTPException(404, "历史记录不存在")
        result = qc_workflow.create_entry(factory_id, body, actor, record,
            record['id'] in data.get('referenceData', {}).get('ids', []))
    elif path == "export-prepare":
        result = qc_workflow.prepare_export(db, factory_id, body, user.id)
    elif path == "export":
        return Response(qc_workflow.export_packet(db, factory_id, body), media_type="application/zip",
            headers={**NO_CACHE, "Content-Disposition": "attachment; filename=QC-inspection-package.zip"})
    elif parts[2] == "attach":
        result = qc_workflow.add_file(factory_id, parts[1], body, actor)
    elif parts[2] == "remove-attachment":
        file_id = body.get("fileId")
        if not isinstance(file_id, str):
            raise HTTPException(422, "缺少附件编号")
        result = qc_workflow.remove_file(factory_id, parts[1], file_id, {k:v for k,v in body.items() if k != "fileId"}, actor)
    else:
        result = qc_workflow.act(db, factory_id, parts[1], parts[2], body, actor)
        result["summarySync"] = await run_in_threadpool(qc_inspection_summary.after_change, factory_id)
    return JSONResponse(result, headers=NO_CACHE)


async def inspection_summary_request(path, request, db, user, factory_id):
    service = qc_inspection_summary
    parts = path.split('/')
    actor = str(user.id)
    actor_obj = {'id': user.id, 'name': user.display_name or user.username}
    if request.method == 'GET':
        if path == 'records':
            result = await run_in_threadpool(service.listing, factory_id, dict(request.query_params))
        elif path == 'history/batches':
            _ensure_permission(db, user, 'qc_inspection:record_delete', factory_id)
            result = await run_in_threadpool(service.list_history_batches, factory_id)
        elif len(parts) == 2 and parts[0] == 'records':
            result = await run_in_threadpool(service.detail, factory_id, parts[1])
        elif len(parts) == 2 and parts[0] == 'history':
            result = await run_in_threadpool(service.batch_detail, factory_id, parts[1], actor)
        else:
            raise HTTPException(404, '接口不存在')
        return JSONResponse(result, headers=NO_CACHE)
    if request.method != 'POST':
        raise HTTPException(405, '不支持的操作')
    deleting_record = len(parts) == 3 and parts[0] == 'records' and parts[2] == 'delete'
    rolling_back = len(parts) == 3 and parts[0] == 'history' and parts[2] == 'rollback'
    if deleting_record or rolling_back:
        _ensure_permission(db, user, 'qc_inspection:record_delete', factory_id)
    else:
        for permission in ('result_write', 'customer_manage', 'report_export'):
            _ensure_permission(db, user, 'qc_inspection:' + permission, factory_id)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '不接受跨站写入')
    if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
        raise HTTPException(415, '请使用 JSON 提交')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > (44 * 1024 * 1024 if path == 'history/preview' else 16384):
            raise HTTPException(413, '提交内容过大')
    try:
        body = json.loads(raw)
        if not isinstance(body, dict): raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(400, '无效 JSON') from None
    if path == 'history/preview':
        result = await run_in_threadpool(service.preview, factory_id, actor, body)
    elif len(parts) == 3 and parts[0] == 'history' and parts[2] == 'commit' and not body:
        result = await run_in_threadpool(service.commit_history, factory_id, actor, parts[1])
    elif deleting_record:
        result = await run_in_threadpool(service.delete_history_record, factory_id, parts[1], body, actor_obj)
    elif rolling_back:
        result = await run_in_threadpool(service.rollback_history_batch, factory_id, parts[1], body, actor_obj)
    else:
        raise HTTPException(404, '接口不存在')
    return JSONResponse(result, headers=NO_CACHE)
