import json
from io import BytesIO
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.qc_inspection import (
    QcAuditEventOut,
    QcCustomerConfigCreate,
    QcCustomerConfigOut,
    QcCustomerConfigUpdate,
    QcInspectionEventCreate,
    QcInspectionEventListOut,
    QcInspectionEventOut,
    QcInspectionEventUpdate,
    QcOrderCreate,
    QcOrderListOut,
    QcOrderOut,
    QcOrderReportGenerateRequest,
    QcOrderUpdate,
    QcProblemCreate,
    QcProblemListOut,
    QcProblemOut,
    QcProblemUpdate,
    QcRenameBatchOut,
    QcRenameExecuteRequest,
    QcRenamePreviewMeta,
    QcReportGenerateRequest,
    QcReportListOut,
    QcReportOut,
    QcScheduleBatchOut,
    QcScheduleConfirmRequest,
    QcWorkspaceOut,
)
from app.services.auth import (
    AuthContext,
    can,
    ensure_permission_in_scope,
    get_current_user,
)
from app.services.qc_inspection import (
    MAX_SCHEDULE_IMPORT_BYTES,
    MAX_SCHEDULE_IMPORT_MEGABYTES,
    QC_DEPARTMENTS,
    confirm_schedule_import,
    create_customer_config,
    create_inspection_event,
    create_order,
    create_problem,
    execute_rename_batch,
    generate_report,
    generate_order_report,
    get_rename_archive,
    get_rename_batch,
    get_report_artifact,
    get_schedule_batch,
    list_audit_events,
    list_customer_configs,
    list_inspection_events,
    list_orders,
    list_problems,
    list_reports,
    preview_rename_batch,
    preview_schedule_import,
    require_qc_factory,
    update_customer_config,
    update_inspection_event,
    update_order,
    update_problem,
    workspace,
)
from app.services.qc_report_rename import (
    MAX_BATCH_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_GROUP,
    MAX_GROUPS_PER_BATCH,
)


router = APIRouter(prefix="/api/qc-inspections", tags=["qc-inspections"])
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _ensure_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
    *,
    allow_group: bool = False,
) -> str:
    factory_id = require_qc_factory(factory_id, allow_group=allow_group)
    department = "*" if factory_id == "*" else QC_DEPARTMENTS[0]
    # 集团汇总是独立的显式全局操作授权；即使系统仍处于 legacy/shadow
    # rollout，也必须采纳 canonical 的用户 override，而不能由本厂职位继承。
    if permission == "qc_inspection:group_summary" and can(
        user, permission, factory_id, department
    ):
        return factory_id
    ensure_permission_in_scope(db, user, permission, factory_id, department)
    return factory_id


@router.get("/workspace", response_model=QcWorkspaceOut)
def get_workspace(
    factory_id: str,
    week: str = Query(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$"),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    return workspace(db, factory_id, week)


@router.get("/orders", response_model=QcOrderListOut)
def get_orders(
    factory_id: str,
    week: str = Query(default="", max_length=10),
    search: str = Query(default="", max_length=128),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    items = list_orders(db, factory_id, week=week, search=search)
    return QcOrderListOut(factory_id=factory_id, week=week, total=len(items), items=items)


@router.post("/orders", response_model=QcOrderOut, status_code=201)
def post_order(
    payload: QcOrderCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:order_write", payload.factory_id)
    return create_order(db, payload, current_user)


@router.get("/orders/{order_id}", response_model=QcOrderOut)
def get_order(
    order_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    items = list_orders(db, factory_id)
    for item in items:
        if item["id"] == order_id:
            return item
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="验货主单不存在")


@router.patch("/orders/{order_id}", response_model=QcOrderOut)
def patch_order(
    order_id: str,
    payload: QcOrderUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    changed_fields = payload.model_fields_set - {
        "factory_id",
        "expected_revision",
        "request_id",
        "reason",
    }
    result_fields = {
        "actual_inspection_date",
        "inspection_result",
        "inspection_agency",
        "manual_has_problem",
        "packing",
        "carton_count",
        "report_status",
        "production_department",
    }
    permission = (
        "qc_inspection:result_write"
        if changed_fields and changed_fields <= result_fields
        else "qc_inspection:order_write"
    )
    _ensure_permission(db, current_user, permission, payload.factory_id)
    return update_order(db, order_id, payload, current_user)


@router.get("/orders/{order_id}/events", response_model=QcInspectionEventListOut)
def get_order_events(
    order_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    items = list_inspection_events(db, factory_id, order_id)
    return QcInspectionEventListOut(
        factory_id=factory_id,
        inspection_order_id=order_id,
        total=len(items),
        items=items,
    )


@router.post("/orders/{order_id}/events", response_model=QcInspectionEventOut, status_code=201)
def post_order_event(
    order_id: str,
    payload: QcInspectionEventCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if payload.inspection_order_id != order_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="路径主单与请求主单不一致")
    _ensure_permission(db, current_user, "qc_inspection:result_write", payload.factory_id)
    return create_inspection_event(db, payload, current_user)


@router.patch("/orders/{order_id}/events/{event_id}", response_model=QcInspectionEventOut)
def patch_order_event(
    order_id: str,
    event_id: str,
    payload: QcInspectionEventUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if payload.inspection_order_id != order_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="路径主单与请求主单不一致")
    _ensure_permission(db, current_user, "qc_inspection:result_write", payload.factory_id)
    return update_inspection_event(db, event_id, payload, current_user)


@router.post(
    "/orders/{order_id}/reports/generate",
    response_model=QcReportOut,
    status_code=201,
)
def post_order_report_generate(
    order_id: str,
    payload: QcOrderReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:report_export", payload.factory_id)
    return generate_order_report(db, order_id, payload, current_user)


@router.get("/problems", response_model=QcProblemListOut)
def get_problems(
    factory_id: str,
    week: str = Query(default="", max_length=10),
    status: str = Query(default="", max_length=32),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    items = list_problems(db, factory_id, week=week, status=status)
    return QcProblemListOut(factory_id=factory_id, week=week, total=len(items), items=items)


@router.post("/problems", response_model=QcProblemOut, status_code=201)
def post_problem(
    payload: QcProblemCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:problem_write", payload.factory_id)
    return create_problem(db, payload, current_user)


@router.patch("/problems/{problem_id}", response_model=QcProblemOut)
def patch_problem(
    problem_id: str,
    payload: QcProblemUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:problem_write", payload.factory_id)
    return update_problem(db, problem_id, payload, current_user)


@router.post("/schedule-imports/preview", response_model=QcScheduleBatchOut, status_code=201)
def post_schedule_preview(
    factory_id: str = Form(...),
    week_key: str = Form(...),
    request_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    import re
    from fastapi import HTTPException

    if not re.fullmatch(r"\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])", week_key.strip()):
        raise HTTPException(status_code=422, detail="week_key 必须使用 YYYY-Www 格式")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id.strip()):
        raise HTTPException(status_code=422, detail="request_id 格式无效")
    factory_id = _ensure_permission(
        db, current_user, "qc_inspection:schedule_write", factory_id
    )
    content_buffer = bytearray()
    try:
        while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
            content_buffer.extend(chunk)
            if len(content_buffer) > MAX_SCHEDULE_IMPORT_BYTES:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=413,
                    detail=f"排期文件不能超过 {MAX_SCHEDULE_IMPORT_MEGABYTES} MB",
                )
    finally:
        file.file.close()
    content = bytes(content_buffer)
    return preview_schedule_import(
        db,
        factory_id=factory_id,
        week_key=week_key.strip(),
        request_id=request_id.strip(),
        file_name=file.filename or "schedule.xlsx",
        content=content,
        user=current_user,
    )


@router.get("/schedule-imports/{batch_id}", response_model=QcScheduleBatchOut)
def get_schedule_import(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    return get_schedule_batch(db, factory_id, batch_id)


@router.post("/schedule-imports/{batch_id}/confirm", response_model=QcScheduleBatchOut)
def post_schedule_confirm(
    batch_id: str,
    payload: QcScheduleConfirmRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "qc_inspection:schedule_write", payload.factory_id
    )
    return confirm_schedule_import(db, batch_id, payload, current_user)


@router.get("/reports", response_model=QcReportListOut)
def get_reports(
    factory_id: str,
    week: str = Query(default="", max_length=10),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    permission = (
        "qc_inspection:group_summary"
        if factory_id.strip() == "*"
        else "qc_inspection:read"
    )
    factory_id = _ensure_permission(
        db,
        current_user,
        permission,
        factory_id,
        allow_group=permission == "qc_inspection:group_summary",
    )
    items = list_reports(db, factory_id, week=week)
    return QcReportListOut(factory_id=factory_id, week=week, total=len(items), items=items)


@router.post("/reports/generate", response_model=QcReportOut, status_code=201)
def post_report_generate(
    payload: QcReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if payload.report_type == "GROUP_SUMMARY":
        _ensure_permission(
            db,
            current_user,
            "qc_inspection:group_summary",
            payload.factory_id,
            allow_group=True,
        )
    else:
        _ensure_permission(
            db, current_user, "qc_inspection:report_export", payload.factory_id
        )
        if payload.is_formal_snapshot:
            _ensure_permission(
                db, current_user, "qc_inspection:factory_summary", payload.factory_id
            )
    return generate_report(db, payload, current_user)


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    permission = (
        "qc_inspection:group_summary"
        if factory_id.strip() == "*"
        else "qc_inspection:report_export"
    )
    factory_id = _ensure_permission(
        db,
        current_user,
        permission,
        factory_id,
        allow_group=factory_id.strip() == "*",
    )
    file_name, media_type, content = get_report_artifact(db, factory_id, report_id)
    encoded = url_quote(file_name)
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.get("/customers", response_model=list[QcCustomerConfigOut])
def get_customers(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "qc_inspection:read", factory_id)
    return list_customer_configs(db, factory_id)


@router.post("/customers", response_model=QcCustomerConfigOut, status_code=201)
def post_customer(
    payload: QcCustomerConfigCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:customer_manage", payload.factory_id)
    return create_customer_config(db, payload, current_user)


@router.patch("/customers/{customer_id}", response_model=QcCustomerConfigOut)
def patch_customer(
    customer_id: str,
    payload: QcCustomerConfigUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "qc_inspection:customer_manage", payload.factory_id)
    return update_customer_config(db, customer_id, payload, current_user)


@router.get("/audit-events", response_model=list[QcAuditEventOut])
def get_audit_events(
    factory_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "qc_inspection:audit_read", factory_id
    )
    return list_audit_events(db, factory_id, limit=limit)


@router.post("/rename-batches/preview", response_model=QcRenameBatchOut, status_code=201)
def post_rename_preview(
    metadata_json: str = Form(...),
    files: list[UploadFile] = File(...),
    file_ids: list[str] = Form(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    try:
        metadata = QcRenamePreviewMeta.model_validate(json.loads(metadata_json))
    except (json.JSONDecodeError, ValueError) as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="改名预览 metadata_json 无效") from exc
    _ensure_permission(
        db,
        current_user,
        "qc_inspection:report_rename_preview",
        metadata.factory_id,
    )
    if (
        len(files) != len(file_ids)
        or len(file_ids) != len(set(file_ids))
        or len(files) > MAX_GROUPS_PER_BATCH * MAX_FILES_PER_GROUP
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="files 与 file_ids 必须一一对应且不重复")
    upload_files: dict[str, tuple[str, bytes]] = {}
    total_size = 0
    try:
        for file_id, upload in zip(file_ids, files, strict=True):
            content = bytearray()
            while chunk := upload.file.read(UPLOAD_CHUNK_SIZE):
                content.extend(chunk)
                total_size += len(chunk)
                if len(content) > MAX_FILE_SIZE_BYTES:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=413, detail="单个报告文件不能超过 25 MB")
                if total_size > MAX_BATCH_SIZE_BYTES:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=413, detail="改名批次总文件不能超过 250 MB")
            upload_files[file_id] = (upload.filename or "", bytes(content))
    finally:
        for upload in files:
            upload.file.close()
    return preview_rename_batch(
        db,
        metadata=metadata,
        upload_files=upload_files,
        user=current_user,
    )


@router.get("/rename-batches/{batch_id}", response_model=QcRenameBatchOut)
def get_rename_preview(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "qc_inspection:report_rename_preview", factory_id
    )
    return get_rename_batch(db, factory_id, batch_id)


@router.post("/rename-batches/{batch_id}/execute")
def post_rename_execute(
    batch_id: str,
    payload: QcRenameExecuteRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db,
        current_user,
        "qc_inspection:report_rename_execute",
        payload.factory_id,
    )
    result, archive = execute_rename_batch(db, batch_id, payload, current_user)
    encoded = url_quote(str(result["archive_file_name"]))
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "X-QC-Rename-Batch-ID": batch_id,
            "X-QC-Rename-Revision": str(result["revision"]),
            "X-QC-Rename-Archive-SHA256": str(result["archive_sha256"]),
        },
    )


@router.get("/rename-batches/{batch_id}/download")
def download_rename_archive(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "qc_inspection:report_rename_execute", factory_id
    )
    file_name, archive = get_rename_archive(db, factory_id, batch_id)
    encoded = url_quote(file_name)
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
