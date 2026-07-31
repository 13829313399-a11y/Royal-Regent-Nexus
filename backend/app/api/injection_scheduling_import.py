import re
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_import import (
    InjectionSchedulingImportBatchOut,
    InjectionSchedulingImportConfirm,
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
    confirm_import,
    import_batch_out,
    preview_import,
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


@router.post(
    "/preview",
    response_model=InjectionSchedulingImportBatchOut,
    status_code=201,
)
async def post_import_preview(
    request: Request,
    factory_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    expected_revision: Annotated[int, Form()] = 0,
):
    factory_id = _ensure_permission(
        db,
        current_user,
        "injection_scheduling:import",
        factory_id,
    )
    content = await file.read(MAX_SOURCE_BYTES + 1)
    record, replay = preview_import(
        db,
        factory_id=factory_id,
        expected_revision=expected_revision,
        source_file_name=file.filename or "upload.xlsx",
        content=content,
        preview_request_id=_request_id(request),
        user=current_user,
    )
    return import_batch_out(db, record, idempotent_replay=replay)


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
    record, replay = confirm_import(db, batch_id, payload, current_user)
    return import_batch_out(db, record, idempotent_replay=replay)
