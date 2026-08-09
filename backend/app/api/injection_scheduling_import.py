import re
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_import import (
    InjectionSchedulingImportBatchOut,
    InjectionSchedulingImportConfirm,
    InjectionSchedulingImportRetry,
    InjectionSchedulingMappingDraftUpdate,
    InjectionSchedulingMasterApproval,
    InjectionSchedulingProfileProposalCreate,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_excel import MAX_SOURCE_BYTES
from app.services.injection_scheduling_import import (
    approve_master_differences,
    confirm_import,
    get_import_batch,
    import_batch_out,
    list_import_batches,
    master_import_required_permissions,
    preview_import,
    propose_import_profile_from_batch,
    retry_import_batch,
    update_import_mapping_draft,
)

router = APIRouter(
    prefix="/api/injection-scheduling/imports",
    tags=["injection-scheduling"],
)


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied):
        return supplied
    return uuid4().hex


def _ensure_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        permission,
        factory_id,
        SCHEDULING_DEPARTMENTS[0],
    )
    return factory_id


@router.get("", response_model=list[InjectionSchedulingImportBatchOut])
def get_import_batches(
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return [
        import_batch_out(db, item)
        for item in list_import_batches(db, factory_id=factory_id, limit=limit)
    ]


@router.get("/{batch_id}", response_model=InjectionSchedulingImportBatchOut)
def get_import_batch_by_id(
    batch_id: str,
    factory_id: Annotated[str, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return import_batch_out(
        db,
        get_import_batch(db, factory_id=factory_id, batch_id=batch_id),
    )


@router.post(
    "/preview",
    response_model=InjectionSchedulingImportBatchOut,
    status_code=201,
)
def post_import_preview(
    request: Request,
    factory_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    expected_revision: Annotated[int, Form()] = 0,
    document_kind: Annotated[str | None, Form()] = None,
):
    factory_id = _ensure_permission(
        db,
        current_user,
        "injection_scheduling:import",
        factory_id,
    )
    content = file.file.read(MAX_SOURCE_BYTES + 1)
    record, replay = preview_import(
        db,
        factory_id=factory_id,
        expected_revision=expected_revision,
        source_file_name=file.filename or "upload.xlsx",
        content=content,
        preview_request_id=_request_id(request),
        user=current_user,
        document_kind=document_kind,
    )
    return import_batch_out(db, record, idempotent_replay=replay)


@router.patch(
    "/{batch_id}/mapping-draft",
    response_model=InjectionSchedulingImportBatchOut,
)
def patch_import_mapping_draft(
    batch_id: str,
    payload: InjectionSchedulingMappingDraftUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:import", payload.factory_id
    )
    record = update_import_mapping_draft(
        db,
        batch_id=batch_id,
        factory_id=factory_id,
        expected_revision=payload.expected_revision,
        request_id=payload.request_id,
        mappings=payload.mappings,
        user=current_user,
    )
    return import_batch_out(db, record)


@router.post(
    "/{batch_id}/profile-proposal",
    response_model=InjectionSchedulingImportBatchOut,
)
def post_import_profile_proposal(
    batch_id: str,
    payload: InjectionSchedulingProfileProposalCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:import", payload.factory_id
    )
    _ensure_permission(
        db,
        current_user,
        "injection_scheduling:propose_import_profiles",
        factory_id,
    )
    record = propose_import_profile_from_batch(
        db,
        batch_id=batch_id,
        factory_id=factory_id,
        expected_revision=payload.expected_revision,
        request_id=payload.request_id,
        name=payload.name,
        reason=payload.reason,
        user=current_user,
    )
    return import_batch_out(db, record)


@router.post(
    "/{batch_id}/confirm",
    response_model=InjectionSchedulingImportBatchOut,
)
def post_import_confirm(
    batch_id: str,
    payload: InjectionSchedulingImportConfirm,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    _ensure_permission(
        db,
        current_user,
        "injection_scheduling:import",
        payload.factory_id,
    )
    batch = get_import_batch(
        db,
        factory_id=payload.factory_id,
        batch_id=batch_id,
    )
    if batch.document_kind == "DEMAND_ORDER":
        _ensure_permission(
            db,
            current_user,
            "injection_scheduling:edit",
            payload.factory_id,
        )
    elif batch.document_kind == "MASTER_DATA":
        for permission in master_import_required_permissions(
            batch,
            payload.selected_row_ids if payload.confirm_scope == "SELECTED" else None,
        ):
            _ensure_permission(db, current_user, permission, payload.factory_id)
    can_publish = any(
        has_permission_in_scope(
            current_user,
            "injection_scheduling:publish",
            payload.factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    record, replay = confirm_import(
        db,
        batch_id,
        payload,
        current_user,
        can_publish=can_publish,
    )
    return import_batch_out(db, record, idempotent_replay=replay)


@router.post(
    "/{batch_id}/retry",
    response_model=InjectionSchedulingImportBatchOut,
)
def post_import_retry(
    batch_id: str,
    payload: InjectionSchedulingImportRetry,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    _ensure_permission(
        db,
        current_user,
        "injection_scheduling:import",
        payload.factory_id,
    )
    record, replay = retry_import_batch(
        db,
        batch_id=batch_id,
        payload=payload,
        user=current_user,
    )
    return import_batch_out(db, record, idempotent_replay=replay)


@router.post(
    "/{batch_id}/master-differences/approve",
    response_model=InjectionSchedulingImportBatchOut,
)
def post_master_difference_approval(
    batch_id: str,
    payload: InjectionSchedulingMasterApproval,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    _ensure_permission(
        db,
        current_user,
        "injection_scheduling:manage_master",
        payload.factory_id,
    )
    record, replay = approve_master_differences(
        db,
        batch_id=batch_id,
        payload=payload,
        user=current_user,
    )
    return import_batch_out(db, record, idempotent_replay=replay)
