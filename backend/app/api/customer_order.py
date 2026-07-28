from hashlib import sha256
import json
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.customer_order import CustomerOrderImportPreviewOut
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import ensure_permission_for_departments
from app.services.customer_order_buzzbee import (
    CustomerOrderWorkbookError,
    XLSX_CONTENT_TYPE,
    MAX_BATCH_PO_BYTES,
    MAX_BATCH_PO_FILES,
    MAX_PO_BYTES,
    create_buzzbee_batch_preview,
    create_buzzbee_preview,
    export_buzzbee_batch_schedule,
    export_buzzbee_schedule,
)


router = APIRouter(prefix="/api/customer-orders", tags=["customer-orders"])
SALES_DEPARTMENTS = ("sales-business",)


def _ensure_customer_order_permission(
    db: Session,
    current_user: AuthContext,
    permission: str,
    factory_id: str,
) -> None:
    ensure_permission_for_departments(
        db,
        current_user,
        permission,
        factory_id,
        SALES_DEPARTMENTS,
    )


def _validate_upload(file: UploadFile, *, kind: str) -> None:
    file_name = file.filename or ""
    supported = (".xls", ".xlsx") if kind == "PO" else (".xlsx",)
    if not file_name.lower().endswith(supported):
        suffixes = " / ".join(supported)
        raise HTTPException(status_code=400, detail=f"{kind} 文件只支持 {suffixes}")


def _parse_skipped_issue_keys(raw: str) -> set[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="跳过项参数格式无效") from exc
    if (
        not isinstance(value, list)
        or len(value) > 100
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise HTTPException(status_code=400, detail="跳过项参数必须是字符串数组")
    return {item.strip() for item in value}


async def _read_po_uploads(po_files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not po_files:
        raise HTTPException(status_code=400, detail="请至少上传一份 PO 文件")
    if len(po_files) > MAX_BATCH_PO_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"单批最多上传 {MAX_BATCH_PO_FILES} 份 PO 文件",
        )
    uploaded: list[tuple[str, bytes]] = []
    total_size = 0
    for po_file in po_files:
        _validate_upload(po_file, kind="PO")
        content = await po_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="PO 文件不能为空")
        if len(content) > MAX_PO_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"PO 文件超过 12MB 限制：{po_file.filename or '未命名文件'}",
            )
        total_size += len(content)
        if total_size > MAX_BATCH_PO_BYTES:
            raise HTTPException(status_code=400, detail="本批 PO 文件合计超过 80MB 限制")
        uploaded.append((po_file.filename or "", content))
    return uploaded


@router.post(
    "/buzzbee/preview",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_buzzbee_customer_order(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_file: UploadFile = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(po_file, kind="PO")
    _validate_upload(schedule_file, kind="客户排期")
    po_content = await po_file.read()
    schedule_content = await schedule_file.read()
    if not po_content or not schedule_content:
        raise HTTPException(status_code=400, detail="PO 和客户排期文件都不能为空")
    try:
        return create_buzzbee_preview(
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_file_name=po_file.filename or "",
            po_content=po_content,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/buzzbee/preview-batch",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_buzzbee_customer_order_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files)
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        return create_buzzbee_batch_preview(
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/buzzbee/export")
async def export_buzzbee_customer_schedule(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    po_file: UploadFile = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    _validate_upload(po_file, kind="PO")
    _validate_upload(schedule_file, kind="客户排期")
    po_content = await po_file.read()
    schedule_content = await schedule_file.read()
    if not po_content or not schedule_content:
        raise HTTPException(status_code=400, detail="PO 和客户排期文件都不能为空")
    try:
        output, file_name, preview = export_buzzbee_schedule(
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_file_name=po_file.filename or "",
            po_content=po_content,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_skipped_issue_keys,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": "true",
            "X-Skipped-Issue-Count": str(len(normalized_skipped_issue_keys)),
            "X-Content-SHA256": sha256(output).hexdigest(),
        },
    )


@router.post("/buzzbee/export-batch")
async def export_buzzbee_customer_schedule_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files)
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        output, file_name, preview = export_buzzbee_batch_schedule(
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_skipped_issue_keys,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": "true",
            "X-PO-File-Count": str(preview["po_file_count"]),
            "X-Skipped-Issue-Count": str(len(normalized_skipped_issue_keys)),
            "X-Content-SHA256": sha256(output).hexdigest(),
        },
    )
