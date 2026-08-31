from datetime import date
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_schedule import (
    InjectionScheduleAiAdjustmentRequest,
    InjectionScheduleAiExplainRequest,
    InjectionScheduleAiFilterRequest,
    InjectionScheduleAiRemarkRequest,
    InjectionScheduleAutoPreviewRequest,
    InjectionScheduleBoardOut,
    InjectionScheduleBootstrapOut,
    InjectionScheduleImportCommitOut,
    InjectionScheduleImportCommitRequest,
    InjectionScheduleImportIssueOut,
    InjectionScheduleImportPreviewOut,
    InjectionScheduleImportRejectRequest,
    InjectionScheduleLineActionRequest,
    InjectionScheduleMachineCreateRequest,
    InjectionScheduleMachineListOut,
    InjectionScheduleMachinePatchRequest,
    InjectionScheduleMoldCreateRequest,
    InjectionScheduleMoldListOut,
    InjectionScheduleMoldPatchRequest,
    InjectionScheduleMoveRequest,
    InjectionScheduleOrderListOut,
    InjectionScheduleOrderPatchRequest,
    InjectionScheduleProposalActionRequest,
    InjectionScheduleSavedViewCreateRequest,
    InjectionScheduleSavedViewPatchRequest,
    InjectionScheduleShiftMatrixExportRequest,
    InjectionScheduleShiftOutputRequest,
    InjectionScheduleTableExportRequest,
    InjectionScheduleVersionRequest,
    InjectionScheduleWindowCreateRequest,
    InjectionScheduleWindowPatchRequest,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling.ai_service import (
    explain_schedule,
    interpret_filter,
    parse_adjustment,
    parse_remark,
)
from app.services.injection_scheduling.exporter import export_shift_matrix, export_table
from app.services.injection_scheduling.import_service import (
    commit_import,
    get_import_batch,
    preview_import,
    reject_import,
)
from app.services.injection_scheduling.importer import MAX_IMPORT_BYTES
from app.services.injection_scheduling.master_data import (
    create_machine,
    create_mold,
    patch_machine,
    patch_mold,
    patch_order,
)
from app.services.injection_scheduling.operations import (
    create_window,
    delete_window,
    list_shift_outputs,
    move_line,
    patch_window,
    put_shift_output,
    set_line_action,
    validate_move,
)
from app.services.injection_scheduling.read_service import (
    INJECTION_SCHEDULING_DEPARTMENTS,
    SUPPORTED_IMPORT_PROFILES,
    board_lines,
    default_board_range,
    get_settings,
    kpis,
    list_machines,
    list_molds,
    list_orders,
    require_factory,
)
from app.services.injection_scheduling.saved_views import (
    archive_saved_view,
    create_saved_view,
    list_saved_views,
    patch_saved_view,
)
from app.services.injection_scheduling.scheduler import (
    apply_proposal,
    build_proposal,
    reject_proposal,
)

router = APIRouter(
    prefix="/api/production/injection-scheduling",
    tags=["injection-scheduling"],
)
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _has_permission(user: AuthContext, permission: str, factory_id: str) -> bool:
    return any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in INJECTION_SCHEDULING_DEPARTMENTS
    )


def _ensure_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> str:
    factory_id = require_factory(factory_id)
    if _has_permission(user, permission, factory_id):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        permission,
        factory_id,
        INJECTION_SCHEDULING_DEPARTMENTS[0],
    )
    return factory_id


@router.get("/bootstrap", response_model=InjectionScheduleBootstrapOut)
def bootstrap(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return {
        "factory_id": factory_id,
        "settings": get_settings(db, factory_id),
        "capabilities": {
            "can_read": True,
            "can_edit": _has_permission(
                current_user, "injection_scheduling:edit", factory_id
            ),
            "can_schedule": _has_permission(
                current_user, "injection_scheduling:schedule", factory_id
            ),
            "can_admin": _has_permission(
                current_user, "injection_scheduling:admin", factory_id
            ),
        },
        "supported_import_profiles": list(SUPPORTED_IMPORT_PROFILES),
    }


@router.get("/board", response_model=InjectionScheduleBoardOut)
def board(
    factory_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    settings = get_settings(db, factory_id)
    default_start, default_end = default_board_range(settings)
    normalized_start = (start_date or date.fromisoformat(default_start)).isoformat()
    normalized_end = (end_date or date.fromisoformat(default_end)).isoformat()
    if normalized_end < normalized_start:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="结束日期不得早于开始日期")
    if (
        date.fromisoformat(normalized_end) - date.fromisoformat(normalized_start)
    ).days > 30:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="看板时间范围最多 31 天")
    revision = getattr(settings, "schedule_revision", None)
    if revision is None:
        revision = settings["schedule_revision"]
    return {
        "factory_id": factory_id,
        "start_date": normalized_start,
        "end_date": normalized_end,
        "schedule_revision": revision,
        "kpis": kpis(db, factory_id),
        "lines": board_lines(db, factory_id, normalized_start, normalized_end),
    }


@router.get("/orders", response_model=InjectionScheduleOrderListOut)
def orders(
    factory_id: str,
    search: str = Query(default="", max_length=128),
    status: str = Query(default="", max_length=20),
    priority: str = Query(default="", max_length=16),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    items = list_orders(
        db,
        factory_id,
        search=search,
        status=status,
        priority=priority,
    )
    return {"factory_id": factory_id, "total": len(items), "items": items}


@router.get("/machines", response_model=InjectionScheduleMachineListOut)
def machines(
    factory_id: str,
    include_disabled: bool = False,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    items = list_machines(db, factory_id, include_disabled=include_disabled)
    return {"factory_id": factory_id, "total": len(items), "items": items}


@router.get("/molds", response_model=InjectionScheduleMoldListOut)
def molds(
    factory_id: str,
    include_disabled: bool = False,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    items = list_molds(db, factory_id, include_disabled=include_disabled)
    return {"factory_id": factory_id, "total": len(items), "items": items}


@router.patch("/orders/{order_id}")
def update_order(
    order_id: str,
    payload: InjectionScheduleOrderPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return patch_order(
        db,
        factory_id=factory_id,
        order_id=order_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.post("/machines")
def add_machine(
    payload: InjectionScheduleMachineCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:admin", payload.factory_id
    )
    return create_machine(
        db,
        factory_id=factory_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.patch("/machines/{machine_id}")
def update_machine(
    machine_id: str,
    payload: InjectionScheduleMachinePatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:admin", payload.factory_id
    )
    values = payload.model_dump(exclude={"factory_id", "version", "reason"})
    return patch_machine(
        db,
        factory_id=factory_id,
        machine_id=machine_id,
        version=payload.version,
        reason=payload.reason,
        actor=current_user,
        **values,
    )


@router.post("/molds")
def add_mold(
    payload: InjectionScheduleMoldCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:admin", payload.factory_id
    )
    return create_mold(
        db,
        factory_id=factory_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.patch("/molds/{mold_id}")
def update_mold(
    mold_id: str,
    payload: InjectionScheduleMoldPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:admin", payload.factory_id
    )
    values = payload.model_dump(exclude={"factory_id", "version", "reason"})
    return patch_mold(
        db,
        factory_id=factory_id,
        mold_id=mold_id,
        version=payload.version,
        reason=payload.reason,
        actor=current_user,
        **values,
    )


@router.post("/imports/preview", response_model=InjectionScheduleImportPreviewOut)
def preview_excel_import(
    factory_id: str = Form(...),
    request_id: str = Form(...),
    profile_override: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", factory_id
    )
    content = bytearray()
    while chunk := file.file.read(UPLOAD_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > MAX_IMPORT_BYTES:
            from fastapi import HTTPException

            raise HTTPException(status_code=413, detail="排产导入文件不能超过 35 MB")
    return preview_import(
        db,
        factory_id=factory_id,
        content=bytes(content),
        file_name=file.filename or "import.xlsx",
        request_id=request_id,
        profile_override=profile_override,
        actor=current_user,
    )


@router.get("/imports/{batch_id}", response_model=InjectionScheduleImportPreviewOut)
def import_batch(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return get_import_batch(db, factory_id, batch_id)


@router.get(
    "/imports/{batch_id}/issues",
    response_model=list[InjectionScheduleImportIssueOut],
)
def import_issues(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return get_import_batch(db, factory_id, batch_id)["issues"]


@router.post(
    "/imports/{batch_id}/commit",
    response_model=InjectionScheduleImportCommitOut,
)
def commit_excel_import(
    batch_id: str,
    payload: InjectionScheduleImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return commit_import(
        db,
        factory_id=factory_id,
        batch_id=batch_id,
        request_id=payload.request_id,
        actor=current_user,
    )


@router.post(
    "/imports/{batch_id}/reject",
    response_model=InjectionScheduleImportPreviewOut,
)
def reject_excel_import(
    batch_id: str,
    payload: InjectionScheduleImportRejectRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return reject_import(
        db,
        factory_id=factory_id,
        batch_id=batch_id,
        reason=payload.reason,
        actor=current_user,
    )


@router.post("/schedule-lines/{line_id}/validate-move")
def validate_schedule_line_move(
    line_id: str,
    payload: InjectionScheduleMoveRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return validate_move(
        db,
        factory_id=factory_id,
        line_id=line_id,
        target_machine_id=payload.target_machine_id,
        planned_start_at=payload.planned_start_at,
        planned_finish_at=payload.planned_finish_at,
        sequence_no=payload.sequence_no,
        expected_line_version=payload.expected_line_version,
        expected_schedule_revision=payload.expected_schedule_revision,
        actor=current_user,
    )


@router.post("/schedule-lines/{line_id}/move")
def move_schedule_line(
    line_id: str,
    payload: InjectionScheduleMoveRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return move_line(
        db,
        factory_id=factory_id,
        line_id=line_id,
        target_machine_id=payload.target_machine_id,
        planned_start_at=payload.planned_start_at,
        planned_finish_at=payload.planned_finish_at,
        sequence_no=payload.sequence_no,
        expected_line_version=payload.expected_line_version,
        expected_schedule_revision=payload.expected_schedule_revision,
        validate_token=payload.validate_token,
        reason=payload.reason,
        actor=current_user,
    )


@router.post("/schedule-lines/{line_id}/{action}")
def mutate_schedule_line(
    line_id: str,
    action: str,
    payload: InjectionScheduleLineActionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return set_line_action(
        db,
        factory_id=factory_id,
        line_id=line_id,
        action=action,
        expected_line_version=payload.expected_line_version,
        expected_schedule_revision=payload.expected_schedule_revision,
        reason=payload.reason,
        actor=current_user,
    )


@router.put("/schedule-lines/{line_id}/shift-outputs/{production_date}/{shift}")
def record_shift_output(
    line_id: str,
    production_date: date,
    shift: str,
    payload: InjectionScheduleShiftOutputRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return put_shift_output(
        db,
        factory_id=factory_id,
        line_id=line_id,
        production_date=production_date.isoformat(),
        shift=shift.upper(),
        reported_shots=payload.reported_shots,
        defect_shots=payload.defect_shots,
        downtime_minutes=payload.downtime_minutes,
        downtime_reason=payload.downtime_reason,
        remark=payload.remark,
        version=payload.version,
        actor=current_user,
    )


@router.get("/schedule-lines/{line_id}/shift-outputs")
def shift_outputs(
    line_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return list_shift_outputs(db, factory_id, line_id)


@router.post("/machine-unavailable-windows")
def add_machine_window(
    payload: InjectionScheduleWindowCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return create_window(
        db,
        factory_id=factory_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.patch("/machine-unavailable-windows/{window_id}")
def update_machine_window(
    window_id: str,
    payload: InjectionScheduleWindowPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return patch_window(
        db,
        factory_id=factory_id,
        window_id=window_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.delete("/machine-unavailable-windows/{window_id}")
def remove_machine_window(
    window_id: str,
    payload: InjectionScheduleVersionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return delete_window(
        db,
        factory_id=factory_id,
        window_id=window_id,
        version=payload.version,
        reason=payload.reason,
        actor=current_user,
    )


@router.post("/auto-schedule/preview")
def preview_auto_schedule(
    payload: InjectionScheduleAutoPreviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:schedule", payload.factory_id
    )
    return build_proposal(
        db,
        factory_id=factory_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.post("/auto-schedule/proposals/{proposal_id}/apply")
def apply_auto_schedule(
    proposal_id: str,
    payload: InjectionScheduleProposalActionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:schedule", payload.factory_id
    )
    return apply_proposal(
        db,
        factory_id=factory_id,
        proposal_id=proposal_id,
        expected_schedule_revision=payload.expected_schedule_revision,
        reason=payload.reason,
        actor=current_user,
    )


@router.post("/auto-schedule/proposals/{proposal_id}/reject")
def reject_auto_schedule(
    proposal_id: str,
    payload: InjectionScheduleProposalActionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:schedule", payload.factory_id
    )
    return reject_proposal(
        db,
        factory_id=factory_id,
        proposal_id=proposal_id,
        reason=payload.reason,
        actor=current_user,
    )


@router.get("/saved-views")
def saved_views(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return list_saved_views(db, factory_id, current_user)


@router.post("/saved-views")
def add_saved_view(
    payload: InjectionScheduleSavedViewCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    permission = (
        "injection_scheduling:admin"
        if payload.scope == "FACTORY_SHARED"
        else "injection_scheduling:read"
    )
    factory_id = _ensure_permission(db, current_user, permission, payload.factory_id)
    return create_saved_view(
        db,
        factory_id=factory_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.patch("/saved-views/{view_id}")
def update_saved_view(
    view_id: str,
    payload: InjectionScheduleSavedViewPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    return patch_saved_view(
        db,
        factory_id=factory_id,
        view_id=view_id,
        actor=current_user,
        **payload.model_dump(exclude={"factory_id"}),
    )


@router.delete("/saved-views/{view_id}")
def delete_saved_view(
    view_id: str,
    payload: InjectionScheduleVersionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    return archive_saved_view(
        db,
        factory_id=factory_id,
        view_id=view_id,
        version=payload.version,
        actor=current_user,
    )


def _excel_response(content: bytes, filename: str) -> StreamingResponse:
    encoded = quote(filename)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/exports/table")
def export_current_table(
    payload: InjectionScheduleTableExportRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    content = export_table(
        db, factory_id=factory_id, **payload.model_dump(exclude={"factory_id"})
    )
    return _excel_response(content, f"注塑排产台账-{factory_id}.xlsx")


@router.post("/exports/shift-matrix")
def export_current_shift_matrix(
    payload: InjectionScheduleShiftMatrixExportRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    content = export_shift_matrix(
        db,
        factory_id=factory_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return _excel_response(
        content,
        f"注塑白夜班矩阵-{factory_id}-{payload.start_date}-{payload.end_date}.xlsx",
    )


@router.post("/ai/parse-remark")
def ai_parse_remark(
    payload: InjectionScheduleAiRemarkRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return parse_remark(payload.remark)


@router.post("/ai/interpret-filter")
def ai_interpret_filter(
    payload: InjectionScheduleAiFilterRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    return interpret_filter(payload.text)


@router.post("/ai/explain-schedule")
def ai_explain_schedule(
    payload: InjectionScheduleAiExplainRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", payload.factory_id
    )
    return explain_schedule(db, factory_id, payload.line_id)


@router.post("/ai/parse-adjustment")
def ai_parse_adjustment(
    payload: InjectionScheduleAiAdjustmentRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:schedule", payload.factory_id
    )
    return parse_adjustment(db, factory_id, payload.text, current_user)
