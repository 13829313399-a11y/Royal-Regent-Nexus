from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_schedule import (
    InjectionImportBatchOut,
    InjectionImportConfirmRequest,
    InjectionImportRejectRequest,
    InjectionMachineCreateRequest,
    InjectionMachineOut,
    InjectionMachineUpdateRequest,
    InjectionMoldCreateRequest,
    InjectionMoldOut,
    InjectionMoldUpdateRequest,
    InjectionOrderCreateRequest,
    InjectionOrderOut,
    InjectionOrderRecommendationsOut,
    InjectionOrderUpdateRequest,
    InjectionScheduleAutoDraftRequest,
    InjectionScheduleAuditEventOut,
    InjectionScheduleCloneRequest,
    InjectionScheduleCommandRequest,
    InjectionScheduleCommandResponse,
    InjectionScheduleDiffOut,
    InjectionSchedulePublishRequest,
    InjectionScheduleReplanRequest,
    InjectionScheduleReplanResponse,
    InjectionScheduleRuleConfigOut,
    InjectionScheduleRuleConfigUpdateRequest,
    InjectionScheduleValidateRequest,
    InjectionScheduleValidationOut,
    InjectionScheduleVersionCreateRequest,
    InjectionScheduleVersionDetailOut,
    InjectionScheduleVersionOut,
    InjectionScheduleWorkspaceOut,
    InjectionScheduleShiftActualCorrectionRequest,
    InjectionScheduleShiftActualCreateRequest,
    InjectionScheduleShiftActualOut,
    InjectionScheduleShiftActualResponse,
)
from app.services.auth import AuthContext, get_current_user
from app.services.injection_schedule import (
    apply_schedule_commands,
    clone_version_as_draft,
    create_version,
    diff_version,
    get_workspace,
    list_audit_events,
    list_versions,
    publish_version,
    validate_schedule_version,
    version_detail,
)
from app.services.injection_schedule_authz import (
    INJECTION_CONFIG_PERMISSION,
    INJECTION_EDIT_PERMISSION,
    INJECTION_PUBLISH_PERMISSION,
    ensure_injection_read,
    ensure_injection_write,
)
from app.services.injection_schedule_excel import MAX_COMPRESSED_BYTES
from app.services.injection_schedule_import import (
    confirm_import_batch,
    create_import_preview,
    create_machine_master,
    create_mold_master,
    create_order_master,
    list_import_batches,
    list_machine_masters,
    list_mold_masters,
    list_order_masters,
    load_import_batch,
    reject_import_batch,
    serialize_import_batch,
    update_machine_master,
    update_mold_master,
    update_order_master,
)
from app.services.injection_schedule_recommendation import (
    get_rule_config,
    recommend_order_machines,
    update_rule_config,
)
from app.services.injection_schedule_phase4 import (
    correct_shift_actual,
    create_shift_actual,
    generate_auto_draft,
    list_shift_actuals,
    replan_locally,
)


router = APIRouter(
    prefix="/api/factories/{factory_id}/injection-schedule",
    tags=["injection-schedule"],
)


def request_metadata(request: Request) -> tuple[str, str]:
    request_id = request.headers.get("x-request-id", "").strip()[:128]
    ip_address = request.client.host if request.client is not None else ""
    return request_id, ip_address


@router.get("/rule-config", response_model=InjectionScheduleRuleConfigOut)
def get_injection_schedule_rule_config(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return get_rule_config(db, factory_id)


@router.patch("/rule-config", response_model=InjectionScheduleRuleConfigOut)
def patch_injection_schedule_rule_config(
    factory_id: str,
    payload: InjectionScheduleRuleConfigUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    request_id, ip_address = request_metadata(request)
    return update_rule_config(
        db,
        factory_id,
        payload,
        current_user,
        request_id=request_id,
        ip_address=ip_address,
    )


@router.get("/workspace", response_model=InjectionScheduleWorkspaceOut)
def get_injection_schedule_workspace(
    factory_id: str,
    version_id: str | None = Query(default=None, max_length=96),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return get_workspace(db, factory_id, version_id)


@router.post(
    "/imports",
    response_model=InjectionImportBatchOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_import(
    factory_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    content = file.file.read(MAX_COMPRESSED_BYTES + 1)
    request_id, ip_address = request_metadata(request)
    return create_import_preview(
        db,
        factory_id=factory_id,
        source_file_name=file.filename or "upload.xlsx",
        source_content_type=file.content_type or "",
        content=content,
        actor=current_user,
        request_id=request_id,
        ip_address=ip_address,
    )


@router.get("/imports", response_model=list[InjectionImportBatchOut])
def get_injection_schedule_imports(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_import_batches(db, factory_id)


@router.get("/imports/{batch_id}", response_model=InjectionImportBatchOut)
def get_injection_schedule_import(
    factory_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return serialize_import_batch(
        db,
        load_import_batch(db, factory_id, batch_id),
    )


@router.post(
    "/imports/{batch_id}/confirm",
    response_model=InjectionImportBatchOut,
)
def post_injection_schedule_import_confirm(
    factory_id: str,
    batch_id: str,
    payload: InjectionImportConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    request_id, ip_address = request_metadata(request)
    return confirm_import_batch(
        db,
        factory_id=factory_id,
        batch_id=batch_id,
        expected_revision=payload.expected_revision,
        business_date=payload.business_date,
        reason=payload.reason,
        resolutions=payload.resolutions,
        actor=current_user,
        request_id=request_id,
        ip_address=ip_address,
    )


@router.post(
    "/imports/{batch_id}/reject",
    response_model=InjectionImportBatchOut,
)
def post_injection_schedule_import_reject(
    factory_id: str,
    batch_id: str,
    payload: InjectionImportRejectRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return reject_import_batch(
        db,
        factory_id=factory_id,
        batch_id=batch_id,
        expected_revision=payload.expected_revision,
        reason=payload.reason,
        actor=current_user,
    )


@router.get("/machines", response_model=list[InjectionMachineOut])
def get_injection_schedule_machines(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_machine_masters(db, factory_id)


@router.post(
    "/machines",
    response_model=InjectionMachineOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_machine(
    factory_id: str,
    payload: InjectionMachineCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return create_machine_master(db, factory_id, payload, current_user)


@router.patch("/machines/{machine_id}", response_model=InjectionMachineOut)
def patch_injection_schedule_machine(
    factory_id: str,
    machine_id: str,
    payload: InjectionMachineUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return update_machine_master(db, factory_id, machine_id, payload, current_user)


@router.get("/molds", response_model=list[InjectionMoldOut])
def get_injection_schedule_molds(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_mold_masters(db, factory_id)


@router.post(
    "/molds",
    response_model=InjectionMoldOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_mold(
    factory_id: str,
    payload: InjectionMoldCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return create_mold_master(db, factory_id, payload, current_user)


@router.patch("/molds/{mold_id}", response_model=InjectionMoldOut)
def patch_injection_schedule_mold(
    factory_id: str,
    mold_id: str,
    payload: InjectionMoldUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return update_mold_master(db, factory_id, mold_id, payload, current_user)


@router.get("/orders", response_model=list[InjectionOrderOut])
def get_injection_schedule_orders(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_order_masters(db, factory_id)


@router.post(
    "/orders",
    response_model=InjectionOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_order(
    factory_id: str,
    payload: InjectionOrderCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return create_order_master(db, factory_id, payload, current_user)


@router.patch("/orders/{order_id}", response_model=InjectionOrderOut)
def patch_injection_schedule_order(
    factory_id: str,
    order_id: str,
    payload: InjectionOrderUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return update_order_master(db, factory_id, order_id, payload, current_user)


@router.get("/versions", response_model=list[InjectionScheduleVersionOut])
def get_injection_schedule_versions(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_versions(db, factory_id)


@router.post(
    "/versions",
    response_model=InjectionScheduleVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_version(
    factory_id: str,
    payload: InjectionScheduleVersionCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    return create_version(db, factory_id, payload, current_user)


@router.get(
    "/versions/{version_id}",
    response_model=InjectionScheduleVersionDetailOut,
)
def get_injection_schedule_version(
    factory_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return version_detail(db, factory_id, version_id)


@router.get(
    "/versions/{version_id}/orders/{order_id}/recommendations",
    response_model=InjectionOrderRecommendationsOut,
)
def get_injection_schedule_order_recommendations(
    factory_id: str,
    version_id: str,
    order_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    planned_qty: float | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return recommend_order_machines(
        db,
        factory_id,
        version_id,
        order_id,
        limit=limit,
        planned_qty=planned_qty,
    )


@router.post(
    "/versions/{version_id}/auto-draft",
    response_model=InjectionScheduleReplanResponse,
)
def post_injection_schedule_auto_draft(
    factory_id: str,
    version_id: str,
    payload: InjectionScheduleAutoDraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    _, ip_address = request_metadata(request)
    return generate_auto_draft(
        db,
        factory_id,
        version_id,
        payload,
        current_user,
        ip_address=ip_address,
    )


@router.post(
    "/versions/{version_id}/replan",
    response_model=InjectionScheduleReplanResponse,
)
def post_injection_schedule_replan(
    factory_id: str,
    version_id: str,
    payload: InjectionScheduleReplanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    _, ip_address = request_metadata(request)
    return replan_locally(
        db,
        factory_id,
        version_id,
        payload,
        current_user,
        ip_address=ip_address,
    )


@router.post(
    "/versions/{version_id}/commands",
    response_model=InjectionScheduleCommandResponse,
)
def post_injection_schedule_commands(
    factory_id: str,
    version_id: str,
    payload: InjectionScheduleCommandRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    request_id, ip_address = request_metadata(request)
    return apply_schedule_commands(
        db,
        factory_id,
        version_id,
        expected_revision=payload.expected_revision,
        reason=payload.reason,
        request_id=payload.request_id or request_id,
        commands=payload.commands,
        actor=current_user,
        ip_address=ip_address,
    )


@router.post(
    "/versions/{version_id}/validate",
    response_model=InjectionScheduleValidationOut,
)
def post_injection_schedule_validate(
    factory_id: str,
    version_id: str,
    payload: InjectionScheduleValidateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    return validate_schedule_version(
        db,
        factory_id,
        version_id,
        payload.expected_revision,
        current_user,
    )


@router.get(
    "/versions/{version_id}/diff",
    response_model=InjectionScheduleDiffOut,
)
def get_injection_schedule_version_diff(
    factory_id: str,
    version_id: str,
    against_version_id: str | None = Query(default=None, max_length=96),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return diff_version(db, factory_id, version_id, against_version_id)


@router.post(
    "/versions/{version_id}/publish",
    response_model=InjectionScheduleVersionOut,
)
def post_injection_schedule_publish(
    factory_id: str,
    version_id: str,
    payload: InjectionSchedulePublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_PUBLISH_PERMISSION)
    request_id, ip_address = request_metadata(request)
    return publish_version(
        db,
        factory_id,
        version_id,
        expected_revision=payload.expected_revision,
        validation_run_id=payload.validation_run_id,
        reason=payload.reason,
        actor=current_user,
        request_id=request_id,
        ip_address=ip_address,
    )


@router.post(
    "/versions/{version_id}/clone",
    response_model=InjectionScheduleVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_clone(
    factory_id: str,
    version_id: str,
    payload: InjectionScheduleCloneRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    return clone_version_as_draft(
        db,
        factory_id,
        version_id,
        name=payload.name,
        reason=payload.reason,
        actor=current_user,
    )


@router.get(
    "/actuals",
    response_model=list[InjectionScheduleShiftActualOut],
)
def get_injection_schedule_shift_actuals(
    factory_id: str,
    version_id: str = Query(default="", max_length=96),
    date_from: str = Query(default="", max_length=10),
    date_to: str = Query(default="", max_length=10),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_read(db, current_user, factory_id)
    return list_shift_actuals(
        db,
        factory_id,
        version_id=version_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.post(
    "/actuals",
    response_model=InjectionScheduleShiftActualResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_injection_schedule_shift_actual(
    factory_id: str,
    payload: InjectionScheduleShiftActualCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    _, ip_address = request_metadata(request)
    return create_shift_actual(
        db,
        factory_id,
        payload,
        current_user,
        ip_address=ip_address,
    )


@router.patch(
    "/actuals/{actual_id}",
    response_model=InjectionScheduleShiftActualResponse,
)
def patch_injection_schedule_shift_actual(
    factory_id: str,
    actual_id: str,
    payload: InjectionScheduleShiftActualCorrectionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_EDIT_PERMISSION)
    _, ip_address = request_metadata(request)
    return correct_shift_actual(
        db,
        factory_id,
        actual_id,
        payload,
        current_user,
        ip_address=ip_address,
    )


@router.get("/audit", response_model=list[InjectionScheduleAuditEventOut])
def get_injection_schedule_audit(
    factory_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_injection_write(db, current_user, factory_id, INJECTION_CONFIG_PERMISSION)
    return list_audit_events(db, factory_id, limit)
