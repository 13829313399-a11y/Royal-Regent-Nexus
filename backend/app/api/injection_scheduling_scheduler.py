import re
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_scheduler import (
    InjectionSchedulingRunApply,
    InjectionSchedulingRunApplyOut,
    InjectionSchedulingRunCreate,
    InjectionSchedulingRunListOut,
    InjectionSchedulingRunOut,
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
from app.services.injection_scheduling_scheduler.run_service import (
    apply_run,
    create_run,
    get_run,
    list_runs,
    run_out,
)

router = APIRouter(prefix="/api/injection-scheduling", tags=["injection-scheduling"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied):
        return supplied
    return uuid4().hex


def _ensure_permission(
    db: Session, user: AuthContext, permission: str, factory_id: str
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db, user, permission, factory_id, SCHEDULING_DEPARTMENTS[0]
    )
    return factory_id


@router.post(
    "/auto-schedule/runs", response_model=InjectionSchedulingRunOut, status_code=201
)
def post_auto_schedule_run(
    payload: InjectionSchedulingRunCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return run_out(db, create_run(db, payload, current_user, _request_id(request)))


@router.get("/auto-schedule/runs", response_model=InjectionSchedulingRunListOut)
def get_auto_schedule_runs(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return InjectionSchedulingRunListOut(
        factory_id=factory_id,
        items=[run_out(db, item) for item in list_runs(db, factory_id, limit)],
    )


@router.get("/auto-schedule/runs/{run_id}", response_model=InjectionSchedulingRunOut)
def get_auto_schedule_run(
    run_id: str,
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return run_out(db, get_run(db, factory_id, run_id))


@router.post(
    "/auto-schedule/runs/{run_id}/apply", response_model=InjectionSchedulingRunApplyOut
)
def post_auto_schedule_apply(
    run_id: str,
    payload: InjectionSchedulingRunApply,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    can_override = any(
        has_permission_in_scope(
            current_user, "injection_scheduling:publish", factory_id, department
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    return apply_run(
        db, run_id, payload, current_user, can_override_review=can_override
    )
