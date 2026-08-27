from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_workbench import (
    InjectionSchedulingWorkbenchBulkUpdate,
    InjectionSchedulingWorkbenchOut,
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
from app.services.injection_scheduling_workbench import (
    get_injection_scheduling_workbench,
    update_injection_scheduling_workbench_jobs,
)

router = APIRouter(
    prefix="/api/injection-scheduling/workbench",
    tags=["injection-scheduling"],
)
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _ensure_read_permission(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(
            user,
            "injection_scheduling:read",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        "injection_scheduling:read",
        factory_id,
        SCHEDULING_DEPARTMENTS[0],
    )
    return factory_id


def _ensure_edit_permission(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> tuple[str, bool]:
    factory_id = require_injection_scheduling_factory(factory_id)
    if not any(
        has_permission_in_scope(
            user,
            "injection_scheduling:edit",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    ):
        ensure_permission_in_scope(
            db,
            user,
            "injection_scheduling:edit",
            factory_id,
            SCHEDULING_DEPARTMENTS[0],
        )
    can_override = any(
        has_permission_in_scope(
            user,
            "injection_scheduling:publish",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    return factory_id, can_override


@router.get("", response_model=InjectionSchedulingWorkbenchOut)
def get_workbench(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
    search: Annotated[str, Query(max_length=128)] = "",
    status: Annotated[str, Query(max_length=32)] = "",
    machine_id: Annotated[str, Query(max_length=96)] = "",
):
    factory_id = _ensure_read_permission(db, current_user, factory_id)
    return get_injection_scheduling_workbench(
        db,
        factory_id=factory_id,
        search=search,
        status=status,
        machine_id=machine_id,
    )


@router.post("/jobs/bulk-update", response_model=InjectionSchedulingWorkbenchOut)
def post_bulk_update(
    payload: InjectionSchedulingWorkbenchBulkUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    _, can_override = _ensure_edit_permission(
        db,
        current_user,
        payload.factory_id,
    )
    return update_injection_scheduling_workbench_jobs(
        db,
        payload=payload,
        user=current_user,
        can_override_baseline=can_override,
    )
