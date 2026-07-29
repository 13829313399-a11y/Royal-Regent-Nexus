import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling import (
    InjectionSchedulingDraftSaveOut,
    InjectionSchedulingDraftSaveRequest,
    InjectionSchedulingImportConfirmOut,
    InjectionSchedulingImportConfirmRequest,
    InjectionSchedulingImportIssueOut,
    InjectionSchedulingImportPreviewOut,
    InjectionSchedulingMoveValidationOut,
    InjectionSchedulingMoveValidationRequest,
    InjectionSchedulingPlanEnvelope,
    InjectionSchedulingPublishOut,
    InjectionSchedulingPublishRequest,
    InjectionSchedulingPublishedEnvelope,
    InjectionSchedulingRollbackOut,
    InjectionSchedulingRollbackRequest,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    confirm_import,
    create_import_preview,
    current_plan_snapshot,
    current_published_snapshot,
    list_import_issues,
    publish_plan,
    rollback_plan,
    save_draft,
    validate_move,
)
from app.services.injection_scheduling_import import parse_injection_schedule_workbook


router = APIRouter(prefix="/api/injection-scheduling", tags=["injection-scheduling"])
MAX_IMPORT_BYTES = 25 * 1024 * 1024


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "").strip()


def _ensure_scheduling_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> None:
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return
    ensure_permission_in_scope(
        db,
        user,
        permission,
        factory_id,
        SCHEDULING_DEPARTMENTS[0],
    )


def _preview_out(db: Session, batch) -> InjectionSchedulingImportPreviewOut:
    issues = list_import_issues(db, batch.id, batch.factory_id)
    return InjectionSchedulingImportPreviewOut(
        batch_id=batch.id,
        factory_id=batch.factory_id,
        source_file_name=batch.source_file_name,
        source_sha256=batch.source_sha256,
        business_date=batch.business_date,
        parser_version=batch.parser_version,
        preview_revision=batch.preview_revision,
        status=batch.status,
        summary=json.loads(batch.summary_json),
        issues=[
            InjectionSchedulingImportIssueOut(
                id=issue.id,
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                sheet_name=issue.sheet_name,
                source_row=issue.source_row,
                field=issue.field,
                source_value=issue.source_value,
            )
            for issue in issues
        ],
        created_at=batch.created_at,
    )


@router.post("/imports/preview", response_model=InjectionSchedulingImportPreviewOut)
async def preview_import(
    request: Request,
    factory_id: str = Form(...),
    business_date: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:import",
        factory_id,
    )
    file_name = (file.filename or "").strip()
    if not file_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="仅支持 .xlsx 工作簿")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="工作簿超过 25MB 限制")
    try:
        parsed = parse_injection_schedule_workbook(
            content,
            factory_id=factory_id,
            source_file_name=file_name,
            business_date=business_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    batch = create_import_preview(
        db,
        parsed=parsed,
        user=current_user,
        request_id=_request_id(request),
    )
    return _preview_out(db, batch)


@router.post(
    "/imports/{batch_id}/confirm",
    response_model=InjectionSchedulingImportConfirmOut,
)
def confirm_import_preview(
    batch_id: str,
    payload: InjectionSchedulingImportConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:import",
        payload.factory_id,
    )
    plan, batch, snapshot = confirm_import(
        db,
        batch_id=batch_id,
        factory_id=payload.factory_id,
        preview_revision=payload.preview_revision,
        reason=payload.reason,
        user=current_user,
        request_id=_request_id(request),
    )
    return InjectionSchedulingImportConfirmOut(
        batch_id=batch.id,
        factory_id=batch.factory_id,
        plan_id=plan.id,
        revision=plan.revision,
        confirmed_at=batch.confirmed_at,
        summary=json.loads(batch.summary_json),
        snapshot=snapshot,
    )


@router.get("/snapshots/current", response_model=InjectionSchedulingPlanEnvelope)
def get_current_snapshot(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:read",
        factory_id,
    )
    plan, snapshot = current_plan_snapshot(db, factory_id=factory_id)
    return InjectionSchedulingPlanEnvelope(
        plan_id=plan.id,
        factory_id=plan.factory_id,
        revision=plan.revision,
        snapshot=snapshot,
    )


@router.get("/machines")
def get_machines(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:read",
        factory_id,
    )
    _, snapshot = current_plan_snapshot(db, factory_id=factory_id)
    return {"factory_id": factory_id, "machines": snapshot.get("machines", [])}


@router.get("/backlog")
def get_backlog(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:read",
        factory_id,
    )
    _, snapshot = current_plan_snapshot(db, factory_id=factory_id)
    return {"factory_id": factory_id, "backlog": snapshot.get("backlog", [])}


@router.post("/moves/validate", response_model=InjectionSchedulingMoveValidationOut)
def validate_plan_move(
    payload: InjectionSchedulingMoveValidationRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:edit",
        payload.factory_id,
    )
    result = validate_move(
        db,
        factory_id=payload.factory_id,
        revision=payload.revision,
        task_id=payload.task_id,
        backlog_id=payload.backlog_id,
        target_machine_id=payload.target_machine_id,
    )
    return InjectionSchedulingMoveValidationOut(
        allowed=result["allowed"],
        eligibility=result["eligibility"],
        reasons=result["reasons"],
        affected_task_count=result["affected_task_count"],
    )


@router.post("/plans/draft", response_model=InjectionSchedulingDraftSaveOut)
def save_plan_draft(
    payload: InjectionSchedulingDraftSaveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:edit",
        payload.factory_id,
    )
    plan, saved_at, digest = save_draft(
        db,
        factory_id=payload.factory_id,
        revision=payload.revision,
        snapshot=payload.snapshot,
        reason=payload.reason,
        user=current_user,
        request_id=_request_id(request),
    )
    return InjectionSchedulingDraftSaveOut(
        plan_id=plan.id,
        revision=plan.revision,
        saved_at=saved_at,
        snapshot_sha256=digest,
    )


@router.post("/plans/publish", response_model=InjectionSchedulingPublishOut)
def publish_plan_version(
    payload: InjectionSchedulingPublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:publish",
        payload.factory_id,
    )
    published = publish_plan(
        db,
        factory_id=payload.factory_id,
        revision=payload.revision,
        reason=payload.reason,
        user=current_user,
        request_id=_request_id(request),
    )
    return InjectionSchedulingPublishOut(
        plan_id=published.plan_id,
        version=published.version,
        plan_revision=published.plan_revision,
        published_at=published.published_at,
        snapshot_sha256=published.snapshot_sha256,
    )


@router.get("/published/current", response_model=InjectionSchedulingPublishedEnvelope)
def get_current_published_snapshot(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:read",
        factory_id,
    )
    published, snapshot = current_published_snapshot(db, factory_id=factory_id)
    return InjectionSchedulingPublishedEnvelope(
        snapshot_id=published.id,
        plan_id=published.plan_id,
        factory_id=published.factory_id,
        version=published.version,
        plan_revision=published.plan_revision,
        published_at=published.published_at,
        snapshot=snapshot,
    )


@router.post("/plans/rollback", response_model=InjectionSchedulingRollbackOut)
def rollback_plan_version(
    payload: InjectionSchedulingRollbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:rollback",
        payload.factory_id,
    )
    plan, snapshot, saved_at = rollback_plan(
        db,
        factory_id=payload.factory_id,
        version=payload.version,
        revision=payload.revision,
        reason=payload.reason,
        user=current_user,
        request_id=_request_id(request),
    )
    return InjectionSchedulingRollbackOut(
        plan_id=plan.id,
        revision=plan.revision,
        rolled_back_from_version=payload.version,
        saved_at=saved_at,
        snapshot=snapshot,
    )
