import re
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingBacklogOut,
    InjectionSchedulingCurrentPlanOut,
    InjectionSchedulingDraftCreate,
    InjectionSchedulingEventsOut,
    InjectionSchedulingOrderCreate,
    InjectionSchedulingOrderOut,
    InjectionSchedulingPlanOperationOut,
    InjectionSchedulingPlanOut,
    InjectionSchedulingPublishInput,
    InjectionSchedulingRollbackInput,
    InjectionSchedulingShiftReportCreate,
    InjectionSchedulingShiftReportResult,
    InjectionSchedulingTaskCreate,
    InjectionSchedulingTaskUpdate,
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
from app.services.injection_scheduling_execution import (
    add_task,
    create_draft_plan,
    create_order,
    create_shift_report,
    current_plan,
    event_out,
    latest_event_sequence,
    list_backlog_orders,
    list_events,
    order_out,
    plan_out,
    publish_plan,
    rollback_plan,
    shift_report_out,
    task_out,
    update_task,
)

router = APIRouter(
    prefix="/api/injection-scheduling",
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


@router.post("/orders", response_model=InjectionSchedulingOrderOut, status_code=201)
def post_order(
    payload: InjectionSchedulingOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    record, _ = create_order(db, payload, current_user, _request_id(request))
    return order_out(record)


@router.get("/backlog", response_model=InjectionSchedulingBacklogOut)
def get_backlog(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return InjectionSchedulingBacklogOut(
        factory_id=factory_id,
        items=[order_out(item) for item in list_backlog_orders(db, factory_id)],
    )


@router.post(
    "/plans/drafts",
    response_model=InjectionSchedulingPlanOut,
    status_code=201,
)
def post_draft(
    payload: InjectionSchedulingDraftCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    record, _ = create_draft_plan(db, payload, current_user, _request_id(request))
    return plan_out(db, record)


@router.get("/plans/current", response_model=InjectionSchedulingCurrentPlanOut)
def get_current_plan(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    record = current_plan(db, factory_id)
    return InjectionSchedulingCurrentPlanOut(
        factory_id=factory_id,
        plan=plan_out(db, record) if record is not None else None,
        polling_revision=latest_event_sequence(db, factory_id),
    )


@router.post(
    "/plans/{plan_id}/tasks",
    response_model=InjectionSchedulingPlanOut,
    status_code=201,
)
def post_task(
    plan_id: str,
    payload: InjectionSchedulingTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    if payload.locked or payload.manual_override_reason:
        _ensure_permission(
            db,
            current_user,
            "injection_scheduling:publish",
            payload.factory_id,
        )
    plan, _, _ = add_task(
        db,
        plan_id,
        payload,
        current_user,
        _request_id(request),
    )
    return plan_out(db, plan)


@router.patch(
    "/plans/{plan_id}/tasks/{task_id}",
    response_model=InjectionSchedulingPlanOut,
)
def patch_task(
    plan_id: str,
    task_id: str,
    payload: InjectionSchedulingTaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    if payload.locked is not None or payload.manual_override_reason is not None:
        _ensure_permission(
            db,
            current_user,
            "injection_scheduling:publish",
            payload.factory_id,
        )
    plan, _, _ = update_task(
        db,
        plan_id,
        task_id,
        payload,
        current_user,
        _request_id(request),
    )
    return plan_out(db, plan)


@router.post(
    "/plans/{plan_id}/publish",
    response_model=InjectionSchedulingPlanOperationOut,
)
def post_publish(
    plan_id: str,
    payload: InjectionSchedulingPublishInput,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:publish", payload.factory_id
    )
    plan, snapshot_id, audit_sequence, replay = publish_plan(
        db, plan_id, payload, current_user
    )
    return InjectionSchedulingPlanOperationOut(
        plan=plan_out(db, plan),
        snapshot_id=snapshot_id,
        audit_sequence=audit_sequence,
        idempotent_replay=replay,
    )


@router.post(
    "/plans/{plan_id}/rollback",
    response_model=InjectionSchedulingPlanOperationOut,
)
def post_rollback(
    plan_id: str,
    payload: InjectionSchedulingRollbackInput,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:rollback", payload.factory_id
    )
    plan, snapshot_id, audit_sequence, replay = rollback_plan(
        db, plan_id, payload, current_user
    )
    return InjectionSchedulingPlanOperationOut(
        plan=plan_out(db, plan),
        snapshot_id=snapshot_id,
        audit_sequence=audit_sequence,
        idempotent_replay=replay,
    )


@router.post(
    "/tasks/{task_id}/shift-reports",
    response_model=InjectionSchedulingShiftReportResult,
)
def post_shift_report(
    task_id: str,
    payload: InjectionSchedulingShiftReportCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(
        db, current_user, "injection_scheduling:report", payload.factory_id
    )
    report, task, order, audit_sequence, replay = create_shift_report(
        db, task_id, payload, current_user
    )
    return InjectionSchedulingShiftReportResult(
        report=shift_report_out(report),
        task=task_out(task),
        order=order_out(order),
        audit_sequence=audit_sequence,
        idempotent_replay=replay,
    )


@router.get("/events", response_model=InjectionSchedulingEventsOut)
def get_events(
    factory_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    records = list_events(
        db,
        factory_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return InjectionSchedulingEventsOut(
        factory_id=factory_id,
        after_sequence=after_sequence,
        latest_sequence=latest_event_sequence(db, factory_id),
        events=[event_out(item) for item in records],
    )
