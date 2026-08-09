from __future__ import annotations

import hashlib
import json
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, parse_business_timestamp
from app.models.injection_scheduling import InjectionSchedulingMold
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingPlanOrderState,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_scheduler import (
    InjectionSchedulingMachineCalendar,
)
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingManualAppendConfirm,
    InjectionSchedulingManualAppendPreview,
    InjectionSchedulingManualAppendPreviewRequest,
    InjectionSchedulingManualAppendResult,
    InjectionSchedulingTaskCreate,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling_execution import (
    add_task,
    plan_tasks,
    task_out,
)
from app.services.injection_scheduling_matching import evaluate_order_matches
from app.services.injection_scheduling_projection import (
    CALCULATION_VERSION,
    load_calculation_context,
    project_task_window,
)
from app.services.injection_scheduling_scheduler.anchor import (
    build_machine_continuation_anchors,
)
from app.services.injection_scheduling_scheduler.duration import default_shift_target


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _require_plan(
    db: Session, factory_id: str, plan_id: str
) -> InjectionSchedulingPlan:
    plan = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == plan_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="计划草案不存在")
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="手工追加只能写入 planning DRAFT")
    return plan


def _require_order(
    db: Session, factory_id: str, order_id: str
) -> InjectionSchedulingOrder:
    order = db.scalar(
        select(InjectionSchedulingOrder).where(
            InjectionSchedulingOrder.factory_id == factory_id,
            InjectionSchedulingOrder.id == order_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="待排订单不存在")
    if order.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="已完成或已取消订单不可追加")
    return order


def _preview(
    db: Session,
    *,
    plan_id: str,
    payload: InjectionSchedulingManualAppendPreviewRequest,
) -> InjectionSchedulingManualAppendPreview:
    plan = _require_plan(db, payload.factory_id, plan_id)
    order = _require_order(db, payload.factory_id, payload.order_id)
    if order.source_type == "DEMAND_ORDER_VERSION" and order.mold_id is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMAND_MOLD_ENRICHMENT_PENDING",
                "message": "订单已进入待排池，但模具资料尚未补齐，暂不能追加到机台",
            },
        )
    if plan.revision != payload.expected_plan_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PLAN_REVISION_STALE",
                "message": "计划草案版本已变化，请重新预览",
                "expected_revision": payload.expected_plan_revision,
                "current_revision": plan.revision,
            },
        )
    if order.revision != payload.expected_order_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ORDER_REVISION_STALE",
                "message": "订单版本已变化，请重新预览",
                "expected_revision": payload.expected_order_revision,
                "current_revision": order.revision,
            },
        )
    state = db.scalar(
        select(InjectionSchedulingPlanOrderState).where(
            InjectionSchedulingPlanOrderState.factory_id == payload.factory_id,
            InjectionSchedulingPlanOrderState.plan_id == plan.id,
            InjectionSchedulingPlanOrderState.order_id == order.id,
        )
    )
    if state is not None and state.status != "BACKLOG":
        raise HTTPException(status_code=409, detail="该订单在当前草案中已不是 BACKLOG")
    existing = db.scalar(
        select(InjectionSchedulingTask.id).where(
            InjectionSchedulingTask.factory_id == payload.factory_id,
            InjectionSchedulingTask.plan_id == plan.id,
            InjectionSchedulingTask.order_id == order.id,
            InjectionSchedulingTask.execution_status.notin_(("COMPLETED", "CANCELLED")),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该订单已有未完成 DRAFT Task")
    matches = evaluate_order_matches(
        db,
        factory_id=payload.factory_id,
        order_id=order.id,
        machine_ids=[payload.machine_id],
        allow_scheduled=True,
    )
    match = matches.results[0]
    if matches.rule_set_revision != payload.expected_rule_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RULE_REVISION_STALE",
                "message": "匹配规则版本已变化，请重新预览",
                "expected_revision": payload.expected_rule_revision,
                "current_revision": matches.rule_set_revision,
            },
        )
    tasks = plan_tasks(db, payload.factory_id, plan.id)
    machine_tasks = [
        item
        for item in tasks
        if item.machine_id == payload.machine_id
        and item.execution_status not in {"COMPLETED", "CANCELLED"}
    ]
    calendar_rows = list(
        db.scalars(
            select(InjectionSchedulingMachineCalendar)
            .where(
                InjectionSchedulingMachineCalendar.factory_id == payload.factory_id,
                InjectionSchedulingMachineCalendar.machine_id == payload.machine_id,
            )
            .order_by(
                InjectionSchedulingMachineCalendar.window_start,
                InjectionSchedulingMachineCalendar.id,
            )
        ).all()
    )
    try:
        business_day = datetime.fromisoformat(plan.business_date).date()
    except ValueError:
        raise HTTPException(status_code=409, detail="计划业务日期无效") from None
    horizon_start = datetime.combine(
        business_day, time.min, tzinfo=BUSINESS_TIME_ZONE
    )
    anchors = build_machine_continuation_anchors(
        db,
        factory_id=payload.factory_id,
        target_plan=plan,
        target_tasks=tasks,
        calendars=calendar_rows,
        horizon_start=horizon_start,
    )
    anchor = anchors.get(payload.machine_id)
    baseline_floor = anchor.starts_at if anchor is not None else horizon_start
    queue_finishes = [
        value
        for item in machine_tasks
        if (value := parse_business_timestamp(item.estimated_finish or item.planned_finish))
        is not None
    ]
    queue_tail = max([baseline_floor, *queue_finishes])
    state_order_quantity = state.order_quantity if state is not None else order.order_quantity
    completed_quantity = (
        state.completed_quantity if state is not None else order.completed_quantity
    )
    planned_quantity = max(
        Decimal(state_order_quantity) - Decimal(completed_quantity), Decimal(0)
    )
    if planned_quantity <= 0:
        raise HTTPException(status_code=409, detail="订单已无可排欠数")
    shift_target = min(planned_quantity, default_shift_target(order))
    mold_ids = {item for item in (order.mold_id,) if item}
    context = load_calculation_context(
        db, factory_id=payload.factory_id, mold_ids=mold_ids
    )
    mold_rows = (
        {
            item.id: item
            for item in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == payload.factory_id,
                    InjectionSchedulingMold.id.in_(mold_ids),
                )
            ).all()
        }
        if mold_ids
        else {}
    )
    previous_task = max(
        machine_tasks,
        key=lambda item: (item.sequence_no, item.id),
        default=None,
    )
    previous_mold = None
    if previous_task is not None and previous_task.mold_id:
        previous_mold = db.scalar(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == payload.factory_id,
                InjectionSchedulingMold.id == previous_task.mold_id,
            )
        )
    anchor_detail = {
        "machine_id": payload.machine_id,
        "baseline_floor": baseline_floor.isoformat(timespec="seconds"),
        "queue_tail": queue_tail.isoformat(timespec="seconds"),
        "sources": list(anchor.sources) if anchor is not None else [],
    }
    calculation = project_task_window(
        order=order,
        planned_quantity=planned_quantity,
        completed_quantity=0,
        shift_target_quantity=shift_target,
        previous_mold=previous_mold,
        current_mold=mold_rows.get(order.mold_id or ""),
        earliest_start=queue_tail,
        calendars=calendar_rows,
        context=context,
        continuation_anchor=anchor_detail,
    )
    maximum_sequence = db.scalar(
        select(func.max(InjectionSchedulingTask.sequence_no)).where(
            InjectionSchedulingTask.factory_id == payload.factory_id,
            InjectionSchedulingTask.plan_id == plan.id,
            InjectionSchedulingTask.machine_id == payload.machine_id,
        )
    )
    sequence_no = int(maximum_sequence if maximum_sequence is not None else -1) + 1
    fingerprint_payload = {
        "calculation_version": CALCULATION_VERSION,
        "plan": [plan.id, plan.revision],
        "order": [order.id, order.revision],
        "state": [state.id, state.revision] if state is not None else None,
        "machine_id": payload.machine_id,
        "rule_revision": matches.rule_set_revision,
        "task_revisions": sorted((item.id, item.revision) for item in machine_tasks),
        "calendar_revisions": sorted((item.id, item.revision) for item in calendar_rows),
        "planned_quantity": float(planned_quantity),
        "sequence_no": sequence_no,
        "calculation_input_fingerprint": calculation["input_fingerprint"],
    }
    return InjectionSchedulingManualAppendPreview(
        factory_id=payload.factory_id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        order_id=order.id,
        order_revision=order.revision,
        machine_id=payload.machine_id,
        sequence_no=sequence_no,
        decision=match.decision,
        hard_failures=[item.model_dump(mode="json") for item in match.hard_failures],
        warnings=[
            item.model_dump(mode="json") for item in match.warnings
        ]
        + calculation["warnings"],
        advisories=[item.model_dump(mode="json") for item in match.advisories],
        planned_quantity=float(planned_quantity),
        shift_target_quantity=float(shift_target),
        planned_start=calculation["estimated_start"],
        planned_finish=calculation["estimated_finish"],
        continuation_anchor=anchor_detail,
        calculation=calculation,
        rule_set_id=matches.rule_set_id,
        rule_revision=matches.rule_set_revision,
        input_fingerprint=_fingerprint(fingerprint_payload),
    )


def preview_manual_append(
    db: Session,
    *,
    plan_id: str,
    payload: InjectionSchedulingManualAppendPreviewRequest,
) -> InjectionSchedulingManualAppendPreview:
    return _preview(db, plan_id=plan_id, payload=payload)


def confirm_manual_append(
    db: Session,
    *,
    plan_id: str,
    payload: InjectionSchedulingManualAppendConfirm,
    user: AuthContext,
    can_override_review: bool,
) -> InjectionSchedulingManualAppendResult:
    preview_payload = InjectionSchedulingManualAppendPreviewRequest(
        factory_id=payload.factory_id,
        order_id=payload.order_id,
        machine_id=payload.machine_id,
        expected_plan_revision=payload.expected_plan_revision,
        expected_order_revision=payload.expected_order_revision,
        expected_rule_revision=payload.expected_rule_revision,
    )
    preview = _preview(db, plan_id=plan_id, payload=preview_payload)
    if preview.input_fingerprint != payload.expected_input_fingerprint:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MANUAL_APPEND_PREVIEW_STALE",
                "message": "机台队列、日历或计算输入已变化，请重新预览",
                "current_input_fingerprint": preview.input_fingerprint,
            },
        )
    if preview.decision == "FAIL":
        raise HTTPException(status_code=409, detail="FAIL 候选不可确认")
    reason = payload.override_reason.strip()
    if preview.decision == "REVIEW_REQUIRED" and (
        not can_override_review or not reason
    ):
        raise HTTPException(
            status_code=403,
            detail="REVIEW_REQUIRED 需要 publish 权限和非空覆盖原因",
        )
    order = _require_order(db, payload.factory_id, payload.order_id)
    plan, task, audit_sequence = add_task(
        db,
        plan_id,
        InjectionSchedulingTaskCreate(
            factory_id=payload.factory_id,
            expected_revision=payload.expected_plan_revision,
            machine_id=payload.machine_id,
            order_id=payload.order_id,
            mold_id=order.mold_id,
            mold_copy_no=1,
            sequence_no=preview.sequence_no,
            execution_status="QUEUED",
            planned_start=preview.planned_start,
            planned_finish=preview.planned_finish,
            shift_target_quantity=preview.shift_target_quantity,
            locked=False,
            manual_override_reason=reason,
        ),
        user,
        payload.request_id,
        audit_detail={
            "manual_append": True,
            "input_fingerprint": preview.input_fingerprint,
            "decision": preview.decision,
            "calculation": preview.calculation,
        },
        calculation=preview.calculation,
        allocated_quantity=Decimal(str(preview.planned_quantity)),
        origin="manual_append",
    )
    return InjectionSchedulingManualAppendResult(
        plan_id=plan.id,
        plan_revision=plan.revision,
        task=task_out(task),
        decision=preview.decision,
        calculation=preview.calculation,
        audit_sequence=audit_sequence,
        input_fingerprint=preview.input_fingerprint,
    )
