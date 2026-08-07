import re
from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingBacklogOut,
    InjectionSchedulingCurrentPlanOut,
    InjectionSchedulingDraftCreate,
    InjectionSchedulingEventsOut,
    InjectionSchedulingManualAppendConfirm,
    InjectionSchedulingManualAppendPreview,
    InjectionSchedulingManualAppendPreviewRequest,
    InjectionSchedulingManualAppendResult,
    InjectionSchedulingOrderCreate,
    InjectionSchedulingOrderOut,
    InjectionSchedulingOrderUpdate,
    InjectionSchedulingPlanContextOut,
    InjectionSchedulingPlanOperationOut,
    InjectionSchedulingPlanOut,
    InjectionSchedulingProgressAdjustmentCreate,
    InjectionSchedulingProgressAdjustmentResult,
    InjectionSchedulingPublishInput,
    InjectionSchedulingRollbackInput,
    InjectionSchedulingShiftReportBulkCreate,
    InjectionSchedulingShiftReportBulkResult,
    InjectionSchedulingShiftReportCreate,
    InjectionSchedulingShiftReportResult,
    InjectionSchedulingTaskBulkMove,
    InjectionSchedulingTaskBulkMoveResult,
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
    create_shift_reports_bulk,
    current_plan,
    event_out,
    latest_event_sequence,
    list_backlog_orders,
    list_events,
    move_tasks_bulk,
    order_out,
    plan_order_state_out,
    plan_out,
    progress_adjustment_out,
    publish_plan,
    rollback_plan,
    shift_report_out,
    task_out,
    update_order,
    update_task,
)
from app.services.injection_scheduling_manual_append import (
    confirm_manual_append,
    preview_manual_append,
)
from app.services.injection_scheduling_takeover import (
    explicit_plan_context,
    manual_progress_adjustment,
)

router = APIRouter(
    prefix="/api/injection-scheduling",
    tags=["injection-scheduling"],
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


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
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    record, _ = create_order(db, payload, current_user, _request_id(request))
    return order_out(record)


@router.patch("/orders/{order_id}", response_model=InjectionSchedulingOrderOut)
def patch_order(
    order_id: str,
    payload: InjectionSchedulingOrderUpdate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    record, _ = update_order(
        db,
        order_id,
        payload,
        current_user,
        _request_id(request),
    )
    return order_out(record)


@router.get("/backlog", response_model=InjectionSchedulingBacklogOut)
def get_backlog(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
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
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    record, _ = create_draft_plan(db, payload, current_user, _request_id(request))
    return plan_out(db, record)


@router.get("/plans/current", response_model=InjectionSchedulingCurrentPlanOut)
def get_current_plan(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
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
    db: DbSession,
    current_user: CurrentUser,
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
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    can_override_baseline = any(
        has_permission_in_scope(
            current_user,
            "injection_scheduling:publish",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
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
        can_override_baseline=can_override_baseline,
    )
    return plan_out(db, plan)


@router.post(
    "/plans/{plan_id}/tasks/bulk-move",
    response_model=InjectionSchedulingTaskBulkMoveResult,
)
def post_task_bulk_move(
    plan_id: str,
    payload: InjectionSchedulingTaskBulkMove,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    can_override_review = any(
        has_permission_in_scope(
            current_user,
            "injection_scheduling:publish",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    return move_tasks_bulk(
        db,
        plan_id,
        payload,
        current_user,
        can_override_review=can_override_review,
    )


@router.get("/plans/context", response_model=InjectionSchedulingPlanContextOut)
def get_plan_context(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    published, draft = explicit_plan_context(db, factory_id)
    return InjectionSchedulingPlanContextOut(
        factory_id=factory_id,
        execution_published_plan=(plan_out(db, published) if published else None),
        planning_draft_plan=(plan_out(db, draft) if draft else None),
        polling_revision=latest_event_sequence(db, factory_id),
    )


@router.post(
    "/plans/{plan_id}/manual-append/preview",
    response_model=InjectionSchedulingManualAppendPreview,
)
def post_manual_append_preview(
    plan_id: str,
    payload: InjectionSchedulingManualAppendPreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    return preview_manual_append(db, plan_id=plan_id, payload=payload)


@router.post(
    "/plans/{plan_id}/manual-append/confirm",
    response_model=InjectionSchedulingManualAppendResult,
)
def post_manual_append_confirm(
    plan_id: str,
    payload: InjectionSchedulingManualAppendConfirm,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:edit", payload.factory_id
    )
    can_override_review = any(
        has_permission_in_scope(
            current_user,
            "injection_scheduling:publish",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    )
    return confirm_manual_append(
        db,
        plan_id=plan_id,
        payload=payload,
        user=current_user,
        can_override_review=can_override_review,
    )


@router.post(
    "/plans/{plan_id}/publish",
    response_model=InjectionSchedulingPlanOperationOut,
)
def post_publish(
    plan_id: str,
    payload: InjectionSchedulingPublishInput,
    db: DbSession,
    current_user: CurrentUser,
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
    db: DbSession,
    current_user: CurrentUser,
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
    db: DbSession,
    current_user: CurrentUser,
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


@router.post(
    "/tasks/shift-reports/bulk",
    response_model=InjectionSchedulingShiftReportBulkResult,
)
def post_shift_reports_bulk(
    payload: InjectionSchedulingShiftReportBulkCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:report", payload.factory_id
    )
    return create_shift_reports_bulk(db, payload, current_user)


@router.post(
    "/progress-adjustments",
    response_model=InjectionSchedulingProgressAdjustmentResult,
)
def post_progress_adjustment(
    payload: InjectionSchedulingProgressAdjustmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:publish", payload.factory_id
    )
    adjustment, state, sequence, replay = manual_progress_adjustment(
        db,
        factory_id=factory_id,
        plan_id=payload.plan_id,
        order_id=payload.order_id,
        task_id=payload.task_id,
        expected_state_revision=payload.expected_state_revision,
        signed_quantity=Decimal(str(payload.signed_quantity)),
        reason=payload.reason,
        request_id=payload.request_id,
        user=current_user,
    )
    return InjectionSchedulingProgressAdjustmentResult(
        adjustment=progress_adjustment_out(adjustment),
        state=plan_order_state_out(state),
        audit_sequence=sequence,
        idempotent_replay=replay,
    )


@router.get("/events", response_model=InjectionSchedulingEventsOut)
def get_events(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
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
