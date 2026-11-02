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
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user
from app.api.qc_inspection import _ensure_permission
from app.services.qc_schedule_example_feedback import read_feedback, save_feedback
from app.services import qc_workflow, qc_schedule_downloads, qc_inspection_sheet, qc_cumulative
from starlette.concurrency import run_in_threadpool
from urllib.parse import quote

router = APIRouter(prefix="/api/qc-department", tags=["qc-department"])
ASSETS = Path(__file__).resolve().parents[3] / "services" / "qc-department"
COMPANIES = {
    "huakang-a": "hy-huakang-a", "huakang-b": "hy-huakang-b",
    "huakang-c": "hy-huakang-c", "huakang-d": "hy-huakang-d",
    "huadeng": "hy-huadeng", "huaxing": "hy-huaxing",
}
STATIC_FILES = {
    "index.html", "app.js", "style.css", "mobile.js", "mobile.css",
    "qc-backend.js", "report_export.js", "ai-ocr.js", "nexus-integration.js", "qc-schedule.js", "qc-workflow.js", "qc-workflow.css", "qc-inspection-sheet.js", "qc-inspection-sheet.css",
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


def schedule_example(factory_id: str) -> dict:
    # User-authorized preview only. Never read/write inspection or Sales databases.
    if factory_id != "huaxing":
        raise HTTPException(404, "当前厂区没有客排期示例")
    try:
        payload = json.loads((ASSETS / "fixtures" / "qc-schedule-example.json").read_text(encoding="utf-8"))
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
    menus = ["dashboard", "sales-schedule", "records", "review", "analysis", "suppliers",
             "daily", "weekly", "monthly", "yearly", "supplier-report", "defectlib", "import", "users"]
    perms = {key: {"v": 1, "e": 0, "a": 0, "m": 0} for key in menus}
    for key in ("records", "review"):
        perms[key].update(e=int(write), a=int(write), m=int(write and manage))
    for key in ("suppliers", "defectlib"):
        perms[key].update(e=int(manage), a=int(manage), m=int(manage))
    perms["review"]["a"] = int(allowed("review"))
    perms["import"] = dict(v=int(write and manage), e=0, a=0, m=int(write and manage))
    perms["users"] = dict(v=0, e=0, a=0, m=0)
    return {"factory": factory_id, "company": COMPANIES[factory_id], "exportAllowed": export, "scheduleExampleWriteAllowed": write,
            "workflow": {"create": allowed("schedule_write") and allowed("order_write"), "edit": allowed("result_write"),
                         "review": allowed("review"), "export": export, "manual": write},
            "inspector": {"id": user.id, "name": user.display_name or user.username},
            "user": {"username": "nexus:" + user.id, "name": user.display_name or user.username,
                     "role": "viewer", "enabled": True, "perms": perms, "password": None}}


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
    if asset_path == "api/schedule-export" and request.method == "POST":
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "不接受跨站请求")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != qc_schedule_downloads.MIME:
            raise HTTPException(415, "请提交 Excel 文件")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > qc_schedule_downloads.MAX_BYTES:
                raise HTTPException(413, "导出文件超过 8 MB")
        return JSONResponse(qc_schedule_downloads.prepare(bytes(content), request.query_params.get("mode"), factory_id + ":" + actor), headers=NO_CACHE)
    if asset_path.startswith("api/schedule-export/") and request.method in {"GET", "HEAD"}:
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
        content, filename = qc_schedule_downloads.download(asset_path.removeprefix("api/schedule-export/"), factory_id + ":" + actor)
        return Response(content if request.method == "GET" else b"", media_type=qc_schedule_downloads.MIME,
                        headers={**NO_CACHE, "Content-Disposition": "attachment; filename=QC-schedule.xlsx; filename*=UTF-8''" + quote(filename, safe=""),
                                 "Content-Length": str(len(content)), "Referrer-Policy": "no-referrer"})
    if asset_path == "api/schedule-source" and request.method == "GET":
        return JSONResponse(qc_workflow.sources(db, factory_id), headers=NO_CACHE)
    if asset_path.startswith("api/workflow/"):
        return await workflow_request(asset_path.removeprefix("api/workflow/"), request, db, user, factory_id)
    if asset_path.startswith("api/inspection-sheet/"):
        return await inspection_sheet_request(asset_path.removeprefix("api/inspection-sheet/"), request, db, user, factory_id)
    if asset_path == "api/schedule-example" and request.method == "GET":
        return JSONResponse(read_feedback(schedule_example(factory_id)), headers=NO_CACHE)
    if asset_path == "api/schedule-example/feedback" and request.method == "POST":
        _ensure_permission(db, user, "qc_inspection:result_write", factory_id)
        _ensure_permission(db, user, "qc_inspection:order_write", factory_id)
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "请使用 JSON 提交")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "不接受跨站写入")
        payload = schedule_example(factory_id)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 32 * 1024:
                raise HTTPException(413, "示例回填内容过长")
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "无效 JSON") from None
        return JSONResponse(save_feedback(payload, data, user.id), headers=NO_CACHE)
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
        return FileResponse(target, headers={**NO_CACHE, "X-Frame-Options": "SAMEORIGIN"})
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
    elif request.method not in {"GET", "HEAD"} or asset_path not in READ_ENDPOINTS:
        raise HTTPException(404, "接口不存在")
    if asset_path.startswith("api/export/"):
        _ensure_permission(db, user, "qc_inspection:report_export", factory_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 32 * 1024 * 1024:
            raise HTTPException(413, "提交内容超过 32 MB")
    if asset_path in {"api/records", "api/records/replace"} and request.method == "POST":
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "无效 JSON")
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
                if prev and r.get('status','approved') != prev.get('status','approved'):
                    raise HTTPException(409,'请通过审核中心或验货表单变更状态')
                if prev and prev.get('status','approved') in {'pending','approved'} and r != prev:
                    raise HTTPException(409,'已提交记录锁定，请由主管退回后修改')
        links = qc_workflow.legacy_links(factory_id)
        if set(payload.get("deletedIds", [])) & set(links):
            raise HTTPException(409, "记录已进入验货修订流程，不能通过历史同步删除")
        if links:
            payload['records'] = [r for r in payload.get('records', []) if r.get('id') not in links]
            body = bytearray(json.dumps(payload).encode())
        body = bytearray(json.dumps(payload).encode())
        if payload.get("deletedIds"):
            _ensure_permission(db, user, "qc_inspection:customer_manage", factory_id)
    if asset_path == 'api/records/delete' and request.method == 'POST':
        try: deleting=json.loads(body).get('ids',[])
        except (ValueError,AttributeError): raise HTTPException(400,'无效 JSON')
        if set(deleting) & set(qc_workflow.legacy_links(factory_id)): raise HTTPException(409,'修订中的历史记录不能删除')
    if asset_path == 'api/records/replace' and request.method == 'POST' and qc_workflow.legacy_links(factory_id):
        raise HTTPException(409, '已有历史记录进入验货修订流程，不能批量清除或替换历史库')
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
        payload["users"] = [ui_context(user, factory_id)["user"]]
        payload["testEntryIds"] = [r["id"] for r in payload.get("records", []) if qc_workflow.test_entry_allowed(factory_id, r)]
        payload["inspectionPlans"] = inspection_plan_dates(factory_id, payload.get("records", []), payload["testEntryIds"])
        return JSONResponse(payload, headers=NO_CACHE)
    if asset_path == "api/ai/status" and result.status_code == 200:
        return JSONResponse({"ready": bool(result.json().get("ready"))}, headers=NO_CACHE)
    headers = {**NO_CACHE, **{k: v for k, v in result.headers.items()
                            if k.lower() in {"content-type", "content-disposition"}}}
    return Response(result.content, status_code=result.status_code, headers=headers)


async def inspection_sheet_request(path, request, db, user, factory_id):
    service = qc_inspection_sheet
    parts = path.split('/')
    actor = {'id': user.id, 'name': user.display_name or user.username}
    async def current_entries(copy_photos=True):
        response=await upstream('GET','api/bootstrap',[('company',COMPANIES[factory_id])],b'')
        if response.status_code!=200:raise HTTPException(503,'验货基础数据读取失败，请重试')
        data=response.json();examples=schedule_example(factory_id)['items'] if factory_id=='huaxing' else []
        rows=service.candidates(factory_id,data.get('records',[]),qc_workflow.list_tasks(db,factory_id)['items'],
            qc_workflow.sources(db,factory_id)['items'],examples,data.get('referenceData',{}).get('ids',[]))
        return await run_in_threadpool(service.sync,factory_id,rows,copy_photos)
    if request.method in {'GET','HEAD'}:
        if path == 'entries' and request.method == 'GET':
            return JSONResponse(await current_entries(),headers=NO_CACHE)
        if parts[0]=='workbook':
            _ensure_permission(db,user,'qc_inspection:report_export',factory_id)
            if path=='workbook/status':
                items=(await current_entries(False))['items']
                return JSONResponse(await run_in_threadpool(qc_cumulative.state,factory_id,items,dict(request.query_params)),headers=NO_CACHE)
            if path=='workbook/archives':
                return JSONResponse(await run_in_threadpool(qc_cumulative.archives,factory_id),headers=NO_CACHE)
            if len(parts)==3 and parts[1]=='archives' and parts[2].isdigit():
                content,name=await run_in_threadpool(qc_cumulative.archive_download,factory_id,int(parts[2]))
                return Response(content if request.method=='GET' else b'',media_type=service.MIME,headers={**NO_CACHE,'Content-Disposition':"attachment; filename=QC-archive.xlsx; filename*=UTF-8''"+quote(name),'Content-Length':str(len(content))})
            if path=='workbook/download':
                content,_=await run_in_threadpool(qc_cumulative.download,factory_id)
                return Response(content if request.method=='GET' else b'',media_type=service.MIME,
                    headers={**NO_CACHE,'Content-Disposition':"attachment; filename=QC-cumulative.xlsx; filename*=UTF-8''"+quote('QC累计验货.xlsx'),
                        'Content-Length':str(len(content))})
            if len(parts)==3 and parts[1]=='jobs':
                return JSONResponse(await run_in_threadpool(qc_cumulative.job,factory_id,str(user.id),parts[2]),headers=NO_CACHE)
            raise HTTPException(404,'接口不存在')
        if len(parts)==4 and parts[0]=='entries' and parts[2]=='photos':
            content=service.read_photo(factory_id,parts[1],parts[3])
            return Response(content if request.method=='GET' else b'',media_type='image/jpeg',headers=NO_CACHE)
        if len(parts)==2 and parts[0]=='exports':
            _ensure_permission(db,user,'qc_inspection:report_export',factory_id)
            content=service.download_export(factory_id,user.id,parts[1])
            return Response(content if request.method=='GET' else b'',media_type=service.MIME,
                headers={**NO_CACHE,'Content-Disposition':"attachment; filename=QC-inspection.xlsx; filename*=UTF-8''"+quote('QC验货明细.xlsx'),
                         'Content-Length':str(len(content))})
        raise HTTPException(404,'接口不存在')
    if request.method != 'POST':raise HTTPException(405,'不支持此方法')
    _ensure_permission(db,user,'qc_inspection:'+('report_export' if path=='export' else 'result_write'),factory_id)
    if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'不接受跨站写入')
    if request.headers.get('content-type','').split(';')[0].lower()!='application/json':raise HTTPException(415,'请使用 JSON 提交')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>(44*1024*1024 if path=='workbook/replace' else 15*1024*1024 if path.endswith('/photos') else 1024*1024):raise HTTPException(413,'提交内容过大')
    try:
        body=json.loads(raw)
        if not isinstance(body,dict):raise ValueError()
    except (ValueError,UnicodeError):raise HTTPException(400,'无效 JSON') from None
    if path in {'workbook/import','workbook/undo','workbook/replace'}:
        _ensure_permission(db,user,'qc_inspection:report_export',factory_id)
        items=(await current_entries(False))['items'] if path.endswith('/import') else []
        result=await run_in_threadpool(qc_cumulative.operate,factory_id,str(user.id),body,items,path.split('/')[1])
    elif len(parts)==4 and parts[:2]==['workbook','entries'] and parts[3]=='save':
        _ensure_permission(db,user,'qc_inspection:report_export',factory_id)
        result=service.save(factory_id,parts[2],body,actor,True)
    elif path=='export':result=service.prepare_export(factory_id,body,user.id)
    elif len(parts)==3 and parts[0]=='entries' and parts[2] in {'save','photos','remove-photo'}:
        method={'save':service.save,'photos':service.add_photo,'remove-photo':service.remove_photo}[parts[2]]
        result=method(factory_id,parts[1],body,actor)
    else:raise HTTPException(404,'接口不存在')
    return JSONResponse(result,headers=NO_CACHE)


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
    if path == "tasks":
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
    if path == "tasks":
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
        if record.get('updatedAt','') != body['updatedAt']: raise HTTPException(409,'记录已变化，请刷新核对')
        action=body['action'];reason=qc_workflow.text(body['reason']);stamp=qc_workflow.now()
        if action=='approve' and record.get('status','approved')!='pending': raise HTTPException(409,'只有已提交的记录可审批')
        if action=='return' and (not reason or record.get('status','approved') not in {'pending','approved'}): raise HTTPException(409,'请检查记录状态并填写退回原因')
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
    return JSONResponse(result, headers=NO_CACHE)
