from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_profile import (
    InjectionSchedulingImportProfileCreate,
    InjectionSchedulingImportProfileListOut,
    InjectionSchedulingImportProfileOut,
    InjectionSchedulingImportProfileTransition,
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
from app.services.injection_scheduling_profile_registry import (
    create_profile_revision,
    list_profile_records,
    profile_record_out,
    transition_profile,
)

router = APIRouter(
    prefix="/api/injection-scheduling/import-profiles",
    tags=["injection-scheduling"],
)


def _ensure_profile_permission(db: Session, user: AuthContext, factory_id: str) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    permission = "injection_scheduling:manage_import_profiles"
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


def _ensure_profile_proposal_permission(
    db: Session, user: AuthContext, factory_id: str
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    for permission in (
        "injection_scheduling:import",
        "injection_scheduling:propose_import_profiles",
    ):
        if any(
            has_permission_in_scope(user, permission, factory_id, department)
            for department in SCHEDULING_DEPARTMENTS
        ):
            continue
        ensure_permission_in_scope(
            db,
            user,
            permission,
            factory_id,
            SCHEDULING_DEPARTMENTS[0],
        )
    return factory_id


@router.get("", response_model=InjectionSchedulingImportProfileListOut)
def get_import_profiles(
    factory_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_profile_permission(db, current_user, factory_id)
    return InjectionSchedulingImportProfileListOut(
        factory_id=factory_id,
        items=[
            InjectionSchedulingImportProfileOut(**profile_record_out(db, record))
            for record in list_profile_records(db, factory_id)
        ],
    )


@router.post(
    "",
    response_model=InjectionSchedulingImportProfileOut,
    status_code=201,
)
def post_import_profile_revision(
    payload: InjectionSchedulingImportProfileCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_profile_proposal_permission(
        db, current_user, payload.factory_id
    )
    record = create_profile_revision(
        db,
        factory_id=factory_id,
        profile_family=payload.profile_family,
        profile_code=payload.profile_code,
        name=payload.name,
        description=payload.description,
        expected_family_revision=payload.expected_family_revision,
        request_id=payload.request_id,
        config=payload.config,
        user=current_user,
    )
    return InjectionSchedulingImportProfileOut(**profile_record_out(db, record))


@router.post(
    "/{profile_id}/activate",
    response_model=InjectionSchedulingImportProfileOut,
)
def post_activate_import_profile(
    profile_id: str,
    payload: InjectionSchedulingImportProfileTransition,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_profile_permission(db, current_user, payload.factory_id)
    record = transition_profile(
        db,
        profile_id=profile_id,
        factory_id=factory_id,
        expected_lifecycle_revision=payload.expected_lifecycle_revision,
        target_status="ACTIVE",
        request_id=payload.request_id,
        reason=payload.reason,
        user=current_user,
    )
    return InjectionSchedulingImportProfileOut(**profile_record_out(db, record))


@router.post(
    "/{profile_id}/retire",
    response_model=InjectionSchedulingImportProfileOut,
)
def post_retire_import_profile(
    profile_id: str,
    payload: InjectionSchedulingImportProfileTransition,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    factory_id = _ensure_profile_permission(db, current_user, payload.factory_id)
    record = transition_profile(
        db,
        profile_id=profile_id,
        factory_id=factory_id,
        expected_lifecycle_revision=payload.expected_lifecycle_revision,
        target_status="RETIRED",
        request_id=payload.request_id,
        reason=payload.reason,
        user=current_user,
    )
    return InjectionSchedulingImportProfileOut(**profile_record_out(db, record))
