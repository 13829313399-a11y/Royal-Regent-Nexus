from __future__ import annotations

import hashlib
import json
from datetime import datetime, time
from decimal import Decimal
from itertools import pairwise
from math import ceil, floor
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, business_now, parse_business_timestamp
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
    InjectionSchedulingRuleSet,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingPlanOrderState,
    InjectionSchedulingPlanRevision,
    InjectionSchedulingProgressAdjustment,
    InjectionSchedulingPublishedSnapshot,
    InjectionSchedulingShiftReport,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_shared import (
    InjectionSchedulingDemandOrderVersion,
    InjectionSchedulingFactoryMoldCapability,
    InjectionSchedulingLegacyMoldCopyBinding,
    InjectionSchedulingMoldReservation,
    InjectionSchedulingPhysicalMoldAsset,
)
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingDraftCreate,
    InjectionSchedulingEventOut,
    InjectionSchedulingOrderCreate,
    InjectionSchedulingOrderOut,
    InjectionSchedulingOrderUpdate,
    InjectionSchedulingPlanOrderStateOut,
    InjectionSchedulingPlanOut,
    InjectionSchedulingProgressAdjustmentOut,
    InjectionSchedulingPublishInput,
    InjectionSchedulingRollbackInput,
    InjectionSchedulingShiftReportBulkCreate,
    InjectionSchedulingShiftReportBulkResult,
    InjectionSchedulingShiftReportCreate,
    InjectionSchedulingShiftReportOut,
    InjectionSchedulingShiftReportResult,
    InjectionSchedulingTaskBulkMove,
    InjectionSchedulingTaskBulkMoveResult,
    InjectionSchedulingTaskCreate,
    InjectionSchedulingTaskMoveResult,
    InjectionSchedulingTaskOut,
    InjectionSchedulingTaskUpdate,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import require_injection_scheduling_factory


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def _decimal(value: float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _float(value: Decimal) -> float:
    return float(value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _payload_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _stable_order_key(order: InjectionSchedulingOrder) -> str:
    lineage = _load_json(order.lineage_json, {})
    value = lineage.get("stable_order_key") if isinstance(lineage, dict) else None
    if isinstance(value, str) and value:
        return value
    return _payload_hash(
        [
            order.factory_id,
            order.order_no,
            order.item_no,
            order.mold_id or "",
            order.product_name,
        ]
    )


def _revision_conflict(
    entity: str,
    expected: int,
    current: int,
    *,
    diff: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": f"{entity}已被其他操作更新",
            "expected_revision": expected,
            "current_revision": current,
            "diff": diff or {},
        },
    )


def _idempotency_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="相同 request_id 已用于不同请求，请更换 request_id",
    )


def _audit(
    db: Session,
    *,
    factory_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    entity_revision: int,
    request_id: str,
    detail: dict[str, Any],
    user: AuthContext,
) -> InjectionSchedulingAuditEvent:
    record = InjectionSchedulingAuditEvent(
        id=f"isaudit-{uuid4().hex}",
        factory_id=factory_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_revision=entity_revision,
        request_id=request_id,
        detail_json=_json(detail),
        actor_user_id=user.id,
        actor_name=_actor_name(user),
        created_at=_now(),
    )
    db.add(record)
    db.flush()
    return record


def order_out(record: InjectionSchedulingOrder) -> InjectionSchedulingOrderOut:
    order_quantity = _float(record.order_quantity)
    completed_quantity = _float(record.completed_quantity)
    outstanding = max(order_quantity - completed_quantity, 0.0)
    return InjectionSchedulingOrderOut(
        id=record.id,
        factory_id=record.factory_id,
        order_no=record.order_no,
        item_no=record.item_no,
        product_name=record.product_name,
        mold_id=record.mold_id,
        order_quantity=order_quantity,
        source_completed_quantity=_float(record.source_completed_quantity),
        completed_quantity=completed_quantity,
        outstanding_quantity=outstanding,
        completion_rate=(
            min(completed_quantity / order_quantity, 1.0) if order_quantity else 0.0
        ),
        estimated_completion_at=record.estimated_completion_at,
        estimated_remaining_shifts=record.estimated_remaining_shifts,
        delivery_slack_days=record.delivery_slack_days,
        delivery_start_date=record.delivery_start_date,
        delivery_due_date=record.delivery_due_date,
        priority_code=record.priority_code,
        material_readiness_status=record.material_readiness_status,
        warehouse_text=record.warehouse_text,
        remark=record.remark,
        source_type=record.source_type,
        source_ref=record.source_ref,
        source_version=record.source_version,
        lineage=_load_json(record.lineage_json, {}),
        status=record.status,
        revision=record.revision,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        updated_by=record.updated_by,
        updated_by_name=record.updated_by_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def task_out(record: InjectionSchedulingTask) -> InjectionSchedulingTaskOut:
    return InjectionSchedulingTaskOut(
        id=record.id,
        factory_id=record.factory_id,
        plan_id=record.plan_id,
        machine_id=record.machine_id,
        order_id=record.order_id,
        mold_id=record.mold_id,
        physical_mold_asset_id=record.physical_mold_asset_id,
        mold_copy_no=record.mold_copy_no,
        sequence_no=record.sequence_no,
        execution_status=record.execution_status,
        planned_start=record.planned_start,
        planned_finish=record.planned_finish,
        shift_target_quantity=_float(record.shift_target_quantity),
        reported_quantity=_float(record.reported_quantity),
        estimated_start=record.estimated_start,
        estimated_finish=record.estimated_finish,
        estimated_remaining_shifts=record.estimated_remaining_shifts,
        delivery_slack_days=record.delivery_slack_days,
        locked=record.locked,
        manual_override_reason=record.manual_override_reason,
        active_execution=record.active_execution,
        import_batch_id=record.import_batch_id,
        source_sheet_name=record.source_sheet_name,
        source_row=record.source_row,
        source_file_hash=record.source_file_hash,
        allocated_quantity=_float(record.allocated_quantity),
        takeover_source_completed_quantity=_float(
            record.takeover_source_completed_quantity
        ),
        origin=record.origin,
        stable_order_key=record.stable_order_key,
        stable_row_key=record.stable_row_key,
        source_task_id=record.source_task_id,
        inherited_report_counter=_float(record.inherited_report_counter),
        completed_at_clone=_float(record.completed_at_clone),
        report_event_watermark=record.report_event_watermark,
        profile_id=record.profile_id,
        profile_revision=record.profile_revision,
        setup_minutes=record.setup_minutes,
        production_minutes=record.production_minutes,
        planned_downtime_minutes=record.planned_downtime_minutes,
        changeover_type=record.changeover_type,
        auto_schedule_run_id=record.auto_schedule_run_id,
        auto_score=(
            _float(record.auto_score) if record.auto_score is not None else None
        ),
        auto_explanation=_load_json(record.auto_explanation_json, {}),
        manual_adjusted=record.manual_adjusted,
        revision=record.revision,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        updated_by=record.updated_by,
        updated_by_name=record.updated_by_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def plan_tasks(
    db: Session,
    factory_id: str,
    plan_id: str,
) -> list[InjectionSchedulingTask]:
    return list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan_id,
            )
            .order_by(
                InjectionSchedulingTask.machine_id,
                InjectionSchedulingTask.sequence_no,
                InjectionSchedulingTask.id,
            )
        ).all()
    )


def plan_orders(
    db: Session,
    factory_id: str,
    plan_id: str,
) -> list[InjectionSchedulingOrder]:
    overlay_order_ids = list(
        db.scalars(
            select(InjectionSchedulingPlanOrderState.order_id).where(
                InjectionSchedulingPlanOrderState.factory_id == factory_id,
                InjectionSchedulingPlanOrderState.plan_id == plan_id,
            )
        ).all()
    )
    if overlay_order_ids:
        return list(
            db.scalars(
                select(InjectionSchedulingOrder)
                .where(
                    InjectionSchedulingOrder.factory_id == factory_id,
                    InjectionSchedulingOrder.id.in_(overlay_order_ids),
                )
                .order_by(
                    InjectionSchedulingOrder.order_no,
                    InjectionSchedulingOrder.item_no,
                    InjectionSchedulingOrder.id,
                )
            ).all()
        )
    return list(
        db.scalars(
            select(InjectionSchedulingOrder)
            .join(
                InjectionSchedulingTask,
                InjectionSchedulingTask.order_id == InjectionSchedulingOrder.id,
            )
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan_id,
                InjectionSchedulingOrder.factory_id == factory_id,
            )
            .distinct()
            .order_by(
                InjectionSchedulingOrder.order_no,
                InjectionSchedulingOrder.item_no,
                InjectionSchedulingOrder.id,
            )
        ).all()
    )


def plan_order_state_out(
    record: InjectionSchedulingPlanOrderState,
) -> InjectionSchedulingPlanOrderStateOut:
    completed = _decimal(record.completed_quantity)
    quantity = _decimal(record.order_quantity)
    return InjectionSchedulingPlanOrderStateOut(
        id=record.id,
        factory_id=record.factory_id,
        plan_id=record.plan_id,
        order_id=record.order_id,
        stable_order_key=record.stable_order_key,
        order_quantity=_float(quantity),
        delivery_start_date=record.delivery_start_date,
        delivery_due_date=record.delivery_due_date,
        takeover_source_completed_quantity=_float(
            record.takeover_source_completed_quantity
        ),
        report_increment_total=_float(record.report_increment_total),
        progress_adjustment_total=_float(record.progress_adjustment_total),
        completed_quantity=_float(completed),
        outstanding_quantity=_float(max(quantity - completed, Decimal(0))),
        status=record.status,
        quantity_scope=record.quantity_scope,
        source_batch_id=record.source_batch_id,
        source_sheet_name=record.source_sheet_name,
        source_row=record.source_row,
        source_profile_id=record.source_profile_id,
        source_profile_revision=record.source_profile_revision,
        source_lineage=_load_json(record.source_lineage_json, {}),
        revision=record.revision,
    )


def plan_out(
    db: Session, record: InjectionSchedulingPlan
) -> InjectionSchedulingPlanOut:
    from app.services.injection_scheduling_takeover import plan_order_states

    states = plan_order_states(db, record.factory_id, record.id)
    states_by_order = {item.order_id: item for item in states}
    projected_orders: list[InjectionSchedulingOrderOut] = []
    for item in plan_orders(db, record.factory_id, record.id):
        projected = order_out(item)
        state = states_by_order.get(item.id)
        if state is not None:
            quantity = _float(state.order_quantity)
            completed = _float(state.completed_quantity)
            projected = projected.model_copy(
                update={
                    "order_quantity": quantity,
                    "completed_quantity": completed,
                    "outstanding_quantity": max(quantity - completed, 0.0),
                    "completion_rate": (
                        min(completed / quantity, 1.0) if quantity else 0.0
                    ),
                    "delivery_start_date": state.delivery_start_date,
                    "delivery_due_date": state.delivery_due_date,
                    "status": state.status,
                }
            )
        projected_orders.append(projected)

    return InjectionSchedulingPlanOut(
        id=record.id,
        factory_id=record.factory_id,
        business_date=record.business_date,
        status=record.status,
        revision=record.revision,
        rule_set_id=record.rule_set_id,
        rule_revision=record.rule_revision,
        based_on_plan_id=record.based_on_plan_id,
        based_on_event_sequence=record.based_on_event_sequence,
        based_on_report_watermark=record.based_on_report_watermark,
        export_profile_id=record.export_profile_id,
        export_profile_revision=record.export_profile_revision,
        export_profile_family=record.export_profile_family,
        export_renderer_code=record.export_renderer_code,
        export_binding_source=record.export_binding_source,
        calculation_version=record.calculation_version,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        updated_by=record.updated_by,
        updated_by_name=record.updated_by_name,
        published_by=record.published_by,
        published_by_name=record.published_by_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        published_at=record.published_at,
        archived_at=record.archived_at,
        orders=projected_orders,
        plan_order_states=[plan_order_state_out(item) for item in states],
        tasks=[task_out(item) for item in plan_tasks(db, record.factory_id, record.id)],
    )


def shift_report_out(
    record: InjectionSchedulingShiftReport,
) -> InjectionSchedulingShiftReportOut:
    return InjectionSchedulingShiftReportOut(
        id=record.id,
        factory_id=record.factory_id,
        task_id=record.task_id,
        order_id=record.order_id,
        business_date=record.business_date,
        shift_code=record.shift_code,
        quantity_mode=record.quantity_mode,
        reported_quantity=_float(record.reported_quantity),
        normalized_increment_quantity=_float(record.normalized_increment_quantity),
        shift_target_quantity=_float(record.shift_target_quantity),
        downtime_minutes=record.downtime_minutes,
        exception_code=record.exception_code,
        exception_detail=record.exception_detail,
        reported_status=record.reported_status,
        request_id=record.request_id,
        reported_by=record.reported_by,
        reported_by_name=record.reported_by_name,
        created_at=record.created_at,
    )


def event_out(record: InjectionSchedulingAuditEvent) -> InjectionSchedulingEventOut:
    return InjectionSchedulingEventOut(
        sequence=record.sequence,
        id=record.id,
        factory_id=record.factory_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        entity_revision=record.entity_revision,
        request_id=record.request_id,
        detail=_load_json(record.detail_json, {}),
        actor_user_id=record.actor_user_id,
        actor_name=record.actor_name,
        created_at=record.created_at,
    )


def create_order(
    db: Session,
    payload: InjectionSchedulingOrderCreate,
    user: AuthContext,
    request_id: str,
) -> tuple[InjectionSchedulingOrder, int]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    if payload.mold_id is not None:
        _require_mold(db, factory_id, payload.mold_id)
    timestamp = _now()
    completed = _decimal(payload.source_completed_quantity)
    quantity = _decimal(payload.order_quantity)
    status = "COMPLETED" if completed >= quantity else "BACKLOG"
    record = InjectionSchedulingOrder(
        id=f"isorder-{uuid4().hex}",
        factory_id=factory_id,
        order_no=payload.order_no,
        item_no=payload.item_no,
        product_name=payload.product_name,
        mold_id=payload.mold_id,
        order_quantity=quantity,
        source_completed_quantity=completed,
        completed_quantity=completed,
        estimated_completion_at="",
        estimated_remaining_shifts=0,
        delivery_slack_days=None,
        delivery_start_date=(
            payload.delivery_start_date.isoformat()
            if payload.delivery_start_date is not None
            else ""
        ),
        delivery_due_date=(
            payload.delivery_due_date.isoformat()
            if payload.delivery_due_date is not None
            else ""
        ),
        priority_code=payload.priority_code,
        material_readiness_status=payload.material_readiness_status,
        warehouse_text=payload.warehouse_text,
        remark=payload.remark,
        source_type="manual",
        source_ref=payload.source_ref,
        source_version=payload.source_version,
        lineage_json=_json(payload.lineage),
        status=status,
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        updated_by=user.id,
        updated_by_name=_actor_name(user),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(record)
    audit = _audit(
        db,
        factory_id=factory_id,
        event_type="order_created",
        entity_type="order",
        entity_id=record.id,
        entity_revision=1,
        request_id=request_id,
        detail={
            "order_no": record.order_no,
            "item_no": record.item_no,
            "order": order_out(record).model_dump(mode="json"),
        },
        user=user,
    )
    db.commit()
    return record, audit.sequence


def update_order(
    db: Session,
    order_id: str,
    payload: InjectionSchedulingOrderUpdate,
    user: AuthContext,
    request_id: str,
) -> tuple[InjectionSchedulingOrder, int]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    record = _require_order(db, factory_id, order_id)
    if record.revision != payload.expected_revision:
        raise _revision_conflict(
            "排产订单",
            payload.expected_revision,
            record.revision,
            diff={
                "warehouse_text": record.warehouse_text,
                "remark": record.remark,
            },
        )
    changes = payload.model_dump(
        exclude_none=True,
        exclude={"factory_id", "expected_revision"},
    )
    timestamp = _now()
    result = db.execute(
        update(InjectionSchedulingOrder)
        .where(
            InjectionSchedulingOrder.id == record.id,
            InjectionSchedulingOrder.factory_id == factory_id,
            InjectionSchedulingOrder.revision == payload.expected_revision,
        )
        .values(
            **changes,
            revision=payload.expected_revision + 1,
            updated_by=user.id,
            updated_by_name=_actor_name(user),
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        latest = _require_order(db, factory_id, order_id)
        raise _revision_conflict(
            "排产订单",
            payload.expected_revision,
            latest.revision,
            diff={
                "warehouse_text": latest.warehouse_text,
                "remark": latest.remark,
            },
        )
    db.flush()
    refreshed = _require_order(db, factory_id, order_id)
    audit = _audit(
        db,
        factory_id=factory_id,
        event_type="order_updated",
        entity_type="order",
        entity_id=record.id,
        entity_revision=payload.expected_revision + 1,
        request_id=request_id,
        detail={
            "changes": changes,
            "order": order_out(refreshed).model_dump(mode="json"),
        },
        user=user,
    )
    db.commit()
    return refreshed, audit.sequence


def progress_adjustment_out(
    record: InjectionSchedulingProgressAdjustment,
) -> InjectionSchedulingProgressAdjustmentOut:
    return InjectionSchedulingProgressAdjustmentOut(
        id=record.id,
        factory_id=record.factory_id,
        plan_id=record.plan_id,
        order_id=record.order_id,
        task_id=record.task_id,
        signed_quantity=_float(record.signed_quantity),
        before_quantity=_float(record.before_quantity),
        after_quantity=_float(record.after_quantity),
        reason=record.reason,
        source_kind=record.source_kind,
        source_batch_id=record.source_batch_id,
        source_sheet_name=record.source_sheet_name,
        source_row=record.source_row,
        request_id=record.request_id,
        adjusted_by=record.adjusted_by,
        adjusted_by_name=record.adjusted_by_name,
        created_at=record.created_at,
    )


def list_backlog_orders(
    db: Session,
    factory_id: str,
) -> list[InjectionSchedulingOrder]:
    factory_id = require_injection_scheduling_factory(factory_id)
    draft_plan_id = db.scalar(
        select(InjectionSchedulingPlan.id).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if draft_plan_id is not None:
        return list(
            db.scalars(
                select(InjectionSchedulingOrder)
                .join(
                    InjectionSchedulingPlanOrderState,
                    InjectionSchedulingPlanOrderState.order_id
                    == InjectionSchedulingOrder.id,
                )
                .where(
                    InjectionSchedulingOrder.factory_id == factory_id,
                    InjectionSchedulingPlanOrderState.factory_id == factory_id,
                    InjectionSchedulingPlanOrderState.plan_id == draft_plan_id,
                    InjectionSchedulingPlanOrderState.status == "BACKLOG",
                )
                .order_by(
                    InjectionSchedulingPlanOrderState.delivery_due_date,
                    InjectionSchedulingOrder.priority_code.desc(),
                    InjectionSchedulingOrder.order_no,
                )
            ).all()
        )
    return list(
        db.scalars(
            select(InjectionSchedulingOrder)
            .where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.status == "BACKLOG",
            )
            .order_by(
                InjectionSchedulingOrder.delivery_due_date,
                InjectionSchedulingOrder.priority_code.desc(),
                InjectionSchedulingOrder.order_no,
            )
        ).all()
    )


def create_draft_plan(
    db: Session,
    payload: InjectionSchedulingDraftCreate,
    user: AuthContext,
    request_id: str,
) -> tuple[InjectionSchedulingPlan, int]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    existing = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="当前厂区已存在计划草案")
    rules = db.scalar(
        select(InjectionSchedulingRuleSet)
        .where(
            InjectionSchedulingRuleSet.factory_id == factory_id,
            InjectionSchedulingRuleSet.status == "active",
        )
        .order_by(InjectionSchedulingRuleSet.revision.desc())
    )
    if rules is None:
        raise HTTPException(status_code=409, detail="当前厂区尚未配置有效排产规则")
    timestamp = _now()
    record = InjectionSchedulingPlan(
        id=f"isplan-{uuid4().hex}",
        factory_id=factory_id,
        business_date=payload.business_date.isoformat(),
        status="DRAFT",
        revision=1,
        rule_set_id=rules.id,
        rule_revision=rules.revision,
        based_on_plan_id="",
        export_profile_id="isprofile-system-standard-v1",
        export_profile_revision=1,
        export_profile_family="system_standard",
        export_renderer_code="system_standard_v1",
        export_binding_source="SYSTEM_STANDARD",
        calculation_version="injection-scheduling-calculation-v2",
        rollback_request_id=None,
        created_by=user.id,
        created_by_name=_actor_name(user),
        updated_by=user.id,
        updated_by_name=_actor_name(user),
        published_by="",
        published_by_name="",
        created_at=timestamp,
        updated_at=timestamp,
        published_at="",
        archived_at="",
    )
    db.add(record)
    try:
        db.flush()
        _record_plan_revision(
            db,
            plan=record,
            user=user,
            timestamp=timestamp,
        )
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_draft_created",
            entity_type="plan",
            entity_id=record.id,
            entity_revision=1,
            request_id=request_id,
            detail={"business_date": record.business_date},
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在计划草案") from exc
    return record, audit.sequence


def current_plan(
    db: Session,
    factory_id: str,
) -> InjectionSchedulingPlan | None:
    factory_id = require_injection_scheduling_factory(factory_id)
    draft = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if draft is not None:
        return draft
    return db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
        .order_by(InjectionSchedulingPlan.published_at.desc())
    )


def latest_event_sequence(db: Session, factory_id: str) -> int:
    factory_id = require_injection_scheduling_factory(factory_id)
    return int(
        db.scalar(
            select(func.max(InjectionSchedulingAuditEvent.sequence)).where(
                InjectionSchedulingAuditEvent.factory_id == factory_id
            )
        )
        or 0
    )


def _remaining_shifts(
    order: InjectionSchedulingOrder,
    shift_target_quantity: Decimal,
) -> int:
    outstanding = max(order.order_quantity - order.completed_quantity, Decimal(0))
    if outstanding <= 0 or shift_target_quantity <= 0:
        return 0
    return ceil(outstanding / shift_target_quantity)


def _delivery_slack_days(
    delivery_due_date: str,
    estimated_finish: str,
) -> int | None:
    if not delivery_due_date or not estimated_finish:
        return None
    try:
        due_date = datetime.fromisoformat(delivery_due_date).date()
    except ValueError:
        return None
    finish = parse_business_timestamp(estimated_finish)
    if finish is None:
        return None
    due_at = datetime.combine(due_date, time.max, tzinfo=BUSINESS_TIME_ZONE)
    return floor((due_at - finish).total_seconds() / 86400)


def _iso_seconds(value: datetime) -> str:
    return value.astimezone(BUSINESS_TIME_ZONE).isoformat(timespec="seconds")


def _ensure_physical_reservation_window_available(
    db: Session,
    *,
    physical_asset_id: str,
    planned_start: str,
    planned_finish: str,
    exclude_task_ids: set[str] | None = None,
    exclude_reservation_ids: set[str] | None = None,
) -> None:
    timestamp = _now()
    db.execute(
        update(InjectionSchedulingMoldReservation)
        .where(
            InjectionSchedulingMoldReservation.status == "TENTATIVE",
            InjectionSchedulingMoldReservation.expires_at != "",
            InjectionSchedulingMoldReservation.expires_at <= timestamp,
        )
        .values(
            status="EXPIRED",
            revision=InjectionSchedulingMoldReservation.revision + 1,
            released_at=timestamp,
        )
    )
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:asset_id))"),
            {"asset_id": physical_asset_id},
        )
    statement = select(InjectionSchedulingMoldReservation.id).where(
        InjectionSchedulingMoldReservation.physical_asset_id == physical_asset_id,
        InjectionSchedulingMoldReservation.status.in_({"TENTATIVE", "ACTIVE"}),
        InjectionSchedulingMoldReservation.window_start < planned_finish,
        InjectionSchedulingMoldReservation.window_end > planned_start,
    )
    if exclude_task_ids:
        statement = statement.where(
            InjectionSchedulingMoldReservation.task_id.notin_(exclude_task_ids)
        )
    if exclude_reservation_ids:
        statement = statement.where(
            InjectionSchedulingMoldReservation.id.notin_(exclude_reservation_ids)
        )
    conflict = db.scalar(statement)
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PHYSICAL_MOLD_ASSET_RESERVED",
                "message": "该副实物模具在目标时间窗已被占用",
                "reservation_id": conflict,
            },
        )


def _sync_task_reservation_window(
    db: Session,
    *,
    task_id: str,
    plan_id: str,
    planned_start: str,
    planned_finish: str,
) -> None:
    reservation = db.scalar(
        select(InjectionSchedulingMoldReservation)
        .where(
            InjectionSchedulingMoldReservation.task_id == task_id,
            InjectionSchedulingMoldReservation.status.in_({"TENTATIVE", "ACTIVE"}),
        )
        .with_for_update()
    )
    if reservation is None:
        return
    reservation.plan_id = plan_id
    reservation.window_start = planned_start
    reservation.window_end = planned_finish
    reservation.status = "ACTIVE"
    reservation.expires_at = ""
    reservation.revision += 1
    reservation.released_at = ""


def _release_task_reservation(db: Session, *, task_id: str, timestamp: str) -> None:
    reservations = list(
        db.scalars(
            select(InjectionSchedulingMoldReservation)
            .where(
                InjectionSchedulingMoldReservation.task_id == task_id,
                InjectionSchedulingMoldReservation.status.in_({"TENTATIVE", "ACTIVE"}),
            )
            .with_for_update()
        ).all()
    )
    for reservation in reservations:
        reservation.status = "RELEASED"
        reservation.revision += 1
        reservation.released_at = timestamp


def _physical_asset_for_new_task(
    db: Session,
    *,
    order: InjectionSchedulingOrder,
    factory_id: str,
    requested_asset_id: str | None,
    mold_copy_no: int,
    planned_start: str,
    planned_finish: str,
) -> InjectionSchedulingPhysicalMoldAsset | None:
    if order.source_type != "DEMAND_ORDER_VERSION":
        binding = db.scalar(
            select(InjectionSchedulingLegacyMoldCopyBinding).where(
                InjectionSchedulingLegacyMoldCopyBinding.factory_id == factory_id,
                InjectionSchedulingLegacyMoldCopyBinding.mold_id == order.mold_id,
                InjectionSchedulingLegacyMoldCopyBinding.mold_copy_no == mold_copy_no,
                InjectionSchedulingLegacyMoldCopyBinding.status == "ACTIVE",
            )
        )
        if binding is None:
            if requested_asset_id:
                raise HTTPException(
                    status_code=422,
                    detail="旧订单不能直接绑定共享实物；请先完成 LegacyMoldCopyBinding 激活",
                )
            return None
        asset = db.get(InjectionSchedulingPhysicalMoldAsset, binding.physical_asset_id)
        if (
            asset is None
            or asset.current_factory_id != factory_id
            or asset.status != "AVAILABLE"
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "LEGACY_MOLD_ASSET_NOT_AVAILABLE",
                    "message": "旧副模具绑定的实物资产当前不可用",
                },
            )
        if requested_asset_id and requested_asset_id != asset.id:
            raise HTTPException(
                status_code=409,
                detail="请求的实物模具与已激活 LegacyMoldCopyBinding 不一致",
            )
        _ensure_physical_reservation_window_available(
            db,
            physical_asset_id=asset.id,
            planned_start=planned_start,
            planned_finish=planned_finish,
        )
        return asset
    version = db.get(InjectionSchedulingDemandOrderVersion, order.source_ref)
    if version is None:
        raise HTTPException(status_code=409, detail="需求订单冻结版本不存在")
    if version.readiness_status != "FACTORY_READY":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMAND_ORDER_NOT_FACTORY_READY",
                "message": "订单可留在 BACKLOG，但本厂实物或已验证能力不足，不能生成 Task",
                "order_revision_id": version.id,
            },
        )
    assets = list(
        db.scalars(
            select(InjectionSchedulingPhysicalMoldAsset).where(
                InjectionSchedulingPhysicalMoldAsset.mold_definition_id
                == version.mold_definition_id,
                InjectionSchedulingPhysicalMoldAsset.current_factory_id == factory_id,
                InjectionSchedulingPhysicalMoldAsset.status == "AVAILABLE",
            )
        ).all()
    )
    capabilities = list(
        db.scalars(
            select(InjectionSchedulingFactoryMoldCapability).where(
                InjectionSchedulingFactoryMoldCapability.factory_id == factory_id,
                InjectionSchedulingFactoryMoldCapability.mold_definition_id
                == version.mold_definition_id,
                InjectionSchedulingFactoryMoldCapability.status == "ACTIVE",
            )
        ).all()
    )
    eligible_asset_ids = {
        asset.id
        for asset in assets
        if any(
            capability.physical_asset_id in {None, asset.id}
            and capability.mold_output_spec_id in {None, version.mold_output_spec_id}
            for capability in capabilities
        )
    }
    if requested_asset_id:
        eligible_asset_ids &= {requested_asset_id}
    if len(eligible_asset_ids) != 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PHYSICAL_MOLD_ASSET_SELECTION_REQUIRED",
                "message": "可用实物模具不是唯一结果，请核验资产或明确选择",
                "candidate_asset_ids": sorted(eligible_asset_ids),
            },
        )
    asset_id = next(iter(eligible_asset_ids))
    _ensure_physical_reservation_window_available(
        db,
        physical_asset_id=asset_id,
        planned_start=planned_start,
        planned_finish=planned_finish,
    )
    return next(item for item in assets if item.id == asset_id)


def add_task(
    db: Session,
    plan_id: str,
    payload: InjectionSchedulingTaskCreate,
    user: AuthContext,
    request_id: str,
    audit_detail: dict[str, Any] | None = None,
    calculation: dict[str, Any] | None = None,
    allocated_quantity: Decimal | None = None,
    origin: str = "manual",
) -> tuple[InjectionSchedulingPlan, InjectionSchedulingTask, int]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    plan = _require_plan(db, factory_id, plan_id)
    _require_draft(plan)
    if plan.revision != payload.expected_revision:
        raise _revision_conflict("计划草案", payload.expected_revision, plan.revision)
    _require_machine(db, factory_id, payload.machine_id)
    order = _require_order(db, factory_id, payload.order_id)
    if order.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="已完成或已取消订单不可排程")
    mold_id = payload.mold_id or order.mold_id
    if mold_id is not None:
        _require_mold(db, factory_id, mold_id)
    physical_asset = _physical_asset_for_new_task(
        db,
        order=order,
        factory_id=factory_id,
        requested_asset_id=payload.physical_mold_asset_id,
        mold_copy_no=payload.mold_copy_no,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
    )
    _validate_schedule_conflicts(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        machine_id=payload.machine_id,
        mold_id=mold_id,
        physical_mold_asset_id=physical_asset.id if physical_asset else None,
        mold_copy_no=payload.mold_copy_no,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
    )
    from app.models.injection_scheduling_scheduler import (
        InjectionSchedulingMachineCalendar,
    )
    from app.services.injection_scheduling_scheduler.anchor import (
        build_machine_continuation_anchors,
    )

    requested_start = parse_business_timestamp(payload.planned_start)
    if requested_start is None:
        raise HTTPException(status_code=422, detail="计划开始时间无效")
    calendars = list(
        db.scalars(
            select(InjectionSchedulingMachineCalendar).where(
                InjectionSchedulingMachineCalendar.factory_id == factory_id,
                InjectionSchedulingMachineCalendar.window_end > payload.planned_start,
            )
        ).all()
    )
    continuation = build_machine_continuation_anchors(
        db,
        factory_id=factory_id,
        target_plan=plan,
        target_tasks=plan_tasks(db, factory_id, plan.id),
        calendars=calendars,
        horizon_start=requested_start,
    ).get(payload.machine_id)
    if continuation is not None and requested_start < continuation.starts_at:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTINUATION_ANCHOR_VIOLATION",
                "message": "手工追加任务必须从机台接续点之后开始",
                "machine_id": payload.machine_id,
                "requested_start": payload.planned_start,
                "continuation_anchor": continuation.as_dict(),
            },
        )
    timestamp = _now()
    target_quantity = _decimal(payload.shift_target_quantity)
    estimated_remaining_shifts = _remaining_shifts(order, target_quantity)
    calculation_detail = calculation or {}
    record = InjectionSchedulingTask(
        id=f"istask-{uuid4().hex}",
        factory_id=factory_id,
        plan_id=plan.id,
        machine_id=payload.machine_id,
        order_id=order.id,
        mold_id=mold_id,
        physical_mold_asset_id=physical_asset.id if physical_asset else None,
        mold_copy_no=payload.mold_copy_no,
        sequence_no=payload.sequence_no,
        execution_status=payload.execution_status,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
        shift_target_quantity=target_quantity,
        reported_quantity=Decimal(0),
        estimated_start=payload.planned_start,
        estimated_finish=payload.planned_finish,
        estimated_remaining_shifts=estimated_remaining_shifts,
        delivery_slack_days=_delivery_slack_days(
            order.delivery_due_date,
            payload.planned_finish,
        ),
        locked=payload.locked,
        manual_override_reason=payload.manual_override_reason,
        active_execution=False,
        allocated_quantity=allocated_quantity or Decimal(0),
        origin=origin,
        setup_minutes=int(calculation_detail.get("setup_minutes", 0)),
        production_minutes=int(calculation_detail.get("production_minutes", 0)),
        planned_downtime_minutes=int(
            calculation_detail.get("calendar_delay_minutes", 0)
        ),
        changeover_type=str(calculation_detail.get("changeover_type", "")),
        auto_explanation_json=_json(
            {"calculation": calculation_detail} if calculation_detail else {}
        ),
        manual_adjusted=origin == "manual_append",
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        updated_by=user.id,
        updated_by_name=_actor_name(user),
        created_at=timestamp,
        updated_at=timestamp,
    )
    if physical_asset is not None:
        db.add(
            InjectionSchedulingMoldReservation(
                id=f"ismoldreservation-{uuid4().hex}",
                physical_asset_id=physical_asset.id,
                factory_id=factory_id,
                plan_id=plan.id,
                task_id=record.id,
                window_start=payload.planned_start,
                window_end=payload.planned_finish,
                status="ACTIVE",
                revision=1,
                expires_at="",
                idempotency_key=f"task:{record.id}",
                source_kind=origin.upper(),
                created_by=user.id,
                created_at=timestamp,
                released_at="",
            )
        )
    db.add(record)
    state = db.scalar(
        select(InjectionSchedulingPlanOrderState).where(
            InjectionSchedulingPlanOrderState.factory_id == factory_id,
            InjectionSchedulingPlanOrderState.plan_id == plan.id,
            InjectionSchedulingPlanOrderState.order_id == order.id,
        )
    )
    if state is None:
        state = InjectionSchedulingPlanOrderState(
            id=f"ispostate-{uuid4().hex}",
            factory_id=factory_id,
            plan_id=plan.id,
            order_id=order.id,
            stable_order_key=_stable_order_key(order),
            order_quantity=order.order_quantity,
            delivery_start_date=order.delivery_start_date,
            delivery_due_date=order.delivery_due_date,
            takeover_source_completed_quantity=order.source_completed_quantity,
            report_increment_total=Decimal(0),
            progress_adjustment_total=Decimal(0),
            completed_quantity=order.source_completed_quantity,
            status="SCHEDULED",
            quantity_scope="ORDER_CUMULATIVE",
            source_batch_id=None,
            source_sheet_name="",
            source_row=None,
            source_profile_id=None,
            source_profile_revision=None,
            source_lineage_json=_json({"origin": origin}),
            revision=1,
            created_by=user.id,
            created_by_name=_actor_name(user),
            updated_by=user.id,
            updated_by_name=_actor_name(user),
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(state)
    elif state.status == "BACKLOG":
        state.status = "SCHEDULED"
        state.revision += 1
        state.updated_by = user.id
        state.updated_by_name = _actor_name(user)
        state.updated_at = timestamp
    try:
        db.flush()
        result = db.execute(
            update(InjectionSchedulingPlan)
            .where(
                InjectionSchedulingPlan.id == plan.id,
                InjectionSchedulingPlan.factory_id == factory_id,
                InjectionSchedulingPlan.status == "DRAFT",
                InjectionSchedulingPlan.revision == payload.expected_revision,
            )
            .values(
                revision=payload.expected_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
        )
        if result.rowcount != 1:
            db.rollback()
            latest = _require_plan(db, factory_id, plan.id)
            raise _revision_conflict(
                "计划草案", payload.expected_revision, latest.revision
            )
        order.status = "SCHEDULED"
        order.revision += 1
        order.updated_by = user.id
        order.updated_by_name = _actor_name(user)
        order.updated_at = timestamp
        db.flush()
        _record_plan_revision(
            db,
            plan=plan,
            user=user,
            timestamp=timestamp,
        )
        event_detail: dict[str, Any] = {
            "plan_id": plan.id,
            "plan_revision": payload.expected_revision + 1,
            "task": task_out(record).model_dump(mode="json"),
            "order": order_out(order).model_dump(mode="json"),
        }
        if audit_detail:
            event_detail.update(audit_detail)
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_task_created",
            entity_type="task",
            entity_id=record.id,
            entity_revision=1,
            request_id=request_id,
            detail=event_detail,
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="同一计划的机台序号已存在",
        ) from exc
    refreshed_plan = _require_plan(db, factory_id, plan.id)
    refreshed_task = _require_task(db, factory_id, plan.id, record.id)
    return refreshed_plan, refreshed_task, audit.sequence


def update_task(
    db: Session,
    plan_id: str,
    task_id: str,
    payload: InjectionSchedulingTaskUpdate,
    user: AuthContext,
    request_id: str,
    *,
    can_override_baseline: bool = False,
) -> tuple[InjectionSchedulingPlan, InjectionSchedulingTask, int]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    plan = _require_plan(db, factory_id, plan_id)
    _require_draft(plan)
    task = _require_task(db, factory_id, plan_id, task_id)
    previous_order_id = task.order_id
    if plan.revision != payload.expected_plan_revision:
        raise _revision_conflict(
            "计划草案", payload.expected_plan_revision, plan.revision
        )
    if task.revision != payload.expected_revision:
        raise _revision_conflict(
            "排产任务",
            payload.expected_revision,
            task.revision,
            diff={"updated_at": task.updated_at},
        )
    requested = payload.model_dump(exclude_none=True)
    protected_fields = {
        "machine_id",
        "order_id",
        "mold_id",
        "mold_copy_no",
        "sequence_no",
        "planned_start",
        "planned_finish",
        "shift_target_quantity",
    }
    protected_change = any(
        field in requested and requested[field] != getattr(task, field)
        for field in protected_fields
    )
    unlocking = task.locked and payload.locked is False
    if task.locked and (protected_change or unlocking):
        if not can_override_baseline:
            raise HTTPException(
                status_code=403,
                detail="修改或解除锁定基线需要发布权限",
            )
        reason = (payload.manual_override_reason or "").strip()
        if not 4 <= len(reason) <= 500:
            raise HTTPException(
                status_code=422,
                detail="修改或解除锁定基线必须填写 4-500 字的逐条原因",
            )
    values = _task_update_values(task, payload)
    order = _validate_task_references(db, factory_id, values)
    values["estimated_start"] = values["planned_start"]
    values["estimated_finish"] = values["planned_finish"]
    values["estimated_remaining_shifts"] = _remaining_shifts(
        order,
        values["shift_target_quantity"],
    )
    values["delivery_slack_days"] = _delivery_slack_days(
        order.delivery_due_date,
        values["estimated_finish"],
    )
    _validate_schedule_conflicts(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        machine_id=values["machine_id"],
        mold_id=values["mold_id"],
        physical_mold_asset_id=task.physical_mold_asset_id,
        mold_copy_no=values["mold_copy_no"],
        planned_start=values["planned_start"],
        planned_finish=values["planned_finish"],
        exclude_task_id=task.id,
    )
    if task.physical_mold_asset_id:
        _ensure_physical_reservation_window_available(
            db,
            physical_asset_id=task.physical_mold_asset_id,
            planned_start=values["planned_start"],
            planned_finish=values["planned_finish"],
            exclude_task_ids={task.id},
        )
    timestamp = _now()
    try:
        task_result = db.execute(
            update(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.id == task.id,
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.revision == payload.expected_revision,
            )
            .values(
                **values,
                manual_adjusted=(
                    task.manual_adjusted or bool(task.auto_schedule_run_id)
                ),
                revision=payload.expected_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
        )
        plan_result = db.execute(
            update(InjectionSchedulingPlan)
            .where(
                InjectionSchedulingPlan.id == plan.id,
                InjectionSchedulingPlan.factory_id == factory_id,
                InjectionSchedulingPlan.status == "DRAFT",
                InjectionSchedulingPlan.revision == payload.expected_plan_revision,
            )
            .values(
                revision=payload.expected_plan_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
        )
        if task_result.rowcount != 1 or plan_result.rowcount != 1:
            db.rollback()
            latest_plan = _require_plan(db, factory_id, plan.id)
            latest_task = _require_task(db, factory_id, plan.id, task.id)
            if latest_plan.revision != payload.expected_plan_revision:
                raise _revision_conflict(
                    "计划草案",
                    payload.expected_plan_revision,
                    latest_plan.revision,
                )
            raise _revision_conflict(
                "排产任务", payload.expected_revision, latest_task.revision
            )
        if values["execution_status"] in {"COMPLETED", "CANCELLED"}:
            _release_task_reservation(db, task_id=task.id, timestamp=timestamp)
        else:
            _sync_task_reservation_window(
                db,
                task_id=task.id,
                plan_id=plan.id,
                planned_start=values["planned_start"],
                planned_finish=values["planned_finish"],
            )
        db.flush()
        for order_id in {previous_order_id, values["order_id"]}:
            _synchronize_order_schedule_status(
                db,
                factory_id=factory_id,
                order_id=order_id,
                user=user,
                timestamp=timestamp,
            )
        _record_plan_revision(
            db,
            plan=plan,
            user=user,
            timestamp=timestamp,
        )
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_task_updated",
            entity_type="task",
            entity_id=task.id,
            entity_revision=payload.expected_revision + 1,
            request_id=request_id,
            detail={
                "plan_id": plan.id,
                "plan_revision": payload.expected_plan_revision + 1,
                "changes": payload.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude={
                        "factory_id",
                        "expected_revision",
                        "expected_plan_revision",
                    },
                ),
                "task": task_out(
                    _require_task(db, factory_id, plan.id, task.id)
                ).model_dump(mode="json"),
                "order": order_out(
                    _require_order(db, factory_id, values["order_id"])
                ).model_dump(mode="json"),
            },
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="任务更新违反机台序号或执行状态约束",
        ) from exc
    return (
        _require_plan(db, factory_id, plan.id),
        _require_task(db, factory_id, plan.id, task.id),
        audit.sequence,
    )


def _validate_proposed_task_windows(
    placements: list[dict[str, Any]],
) -> None:
    by_machine: dict[str, list[dict[str, Any]]] = {}
    by_mold_copy: dict[tuple[str, int], list[dict[str, Any]]] = {}
    by_physical_asset: dict[str, list[dict[str, Any]]] = {}
    for placement in placements:
        placement["_start"] = datetime.fromisoformat(placement["planned_start"])
        placement["_finish"] = datetime.fromisoformat(placement["planned_finish"])
        by_machine.setdefault(placement["machine_id"], []).append(placement)
        if placement["mold_id"]:
            key = (placement["mold_id"], placement["mold_copy_no"])
            by_mold_copy.setdefault(key, []).append(placement)
        if placement.get("physical_mold_asset_id"):
            by_physical_asset.setdefault(
                placement["physical_mold_asset_id"], []
            ).append(placement)

    def ensure_no_overlap(
        groups: dict[Any, list[dict[str, Any]]],
        message: str,
    ) -> None:
        for items in groups.values():
            ordered = sorted(items, key=lambda item: (item["_start"], item["id"]))
            for previous, current in pairwise(ordered):
                if current["_start"] < previous["_finish"]:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": message,
                            "task_ids": [previous["id"], current["id"]],
                        },
                    )

    ensure_no_overlap(by_machine, "移动后的同一机台任务时间发生重叠")
    ensure_no_overlap(by_mold_copy, "移动后的同一实体模具时间发生重叠")
    ensure_no_overlap(by_physical_asset, "移动后的同一实物模具时间发生重叠")


def move_tasks_bulk(
    db: Session,
    plan_id: str,
    payload: InjectionSchedulingTaskBulkMove,
    user: AuthContext,
    *,
    can_override_review: bool,
) -> InjectionSchedulingTaskBulkMoveResult:
    from app.services.injection_scheduling_matching import evaluate_order_matches

    factory_id = require_injection_scheduling_factory(payload.factory_id)
    request_payload = payload.model_dump(mode="json") | {"plan_id": plan_id}
    request_hash = _payload_hash(request_payload)
    replay = db.scalar(
        select(InjectionSchedulingAuditEvent)
        .where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.event_type == "plan_tasks_bulk_moved",
            InjectionSchedulingAuditEvent.request_id == payload.request_id,
        )
        .order_by(InjectionSchedulingAuditEvent.sequence.desc())
    )
    if replay is not None:
        detail = _load_json(replay.detail_json, {})
        if detail.get("payload_hash") != request_hash:
            raise _idempotency_conflict()
        plan = _require_plan(db, factory_id, plan_id)
        return InjectionSchedulingTaskBulkMoveResult(
            plan=plan_out(db, plan),
            moves=[
                InjectionSchedulingTaskMoveResult.model_validate(item)
                for item in detail.get("moves", [])
            ],
            audit_sequence=replay.sequence,
            idempotent_replay=True,
        )

    plan = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == plan_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="排产计划不存在")
    _require_draft(plan)
    if plan.revision != payload.expected_plan_revision:
        raise _revision_conflict(
            "计划草案",
            payload.expected_plan_revision,
            plan.revision,
        )
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
            .order_by(
                InjectionSchedulingTask.machine_id,
                InjectionSchedulingTask.sequence_no,
            )
            .with_for_update()
        ).all()
    )
    task_by_id = {task.id: task for task in tasks}
    move_by_task_id = {move.task_id: move for move in payload.moves}
    missing = [task_id for task_id in move_by_task_id if task_id not in task_by_id]
    if missing:
        raise HTTPException(
            status_code=404, detail={"message": "排产任务不存在", "task_ids": missing}
        )

    match_by_task_id: dict[str, dict[str, Any]] = {}
    move_results: list[InjectionSchedulingTaskMoveResult] = []
    for move in payload.moves:
        task = task_by_id[move.task_id]
        if task.revision != move.expected_revision:
            raise _revision_conflict(
                "排产任务",
                move.expected_revision,
                task.revision,
                diff={
                    "machine_id": task.machine_id,
                    "sequence_no": task.sequence_no,
                    "planned_start": task.planned_start,
                    "planned_finish": task.planned_finish,
                },
            )
        if task.locked or task.active_execution or task.execution_status == "RUNNING":
            raise HTTPException(status_code=409, detail="运行中或已锁定任务不能移动")
        evaluation = evaluate_order_matches(
            db,
            factory_id=factory_id,
            order_id=task.order_id,
            machine_ids=[move.machine_id],
            allow_scheduled=True,
        )
        match = evaluation.results[0]
        if (
            match.rule_set_revision != payload.expected_rule_revision
            or plan.rule_revision != match.rule_set_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "排产规则版本已变化，请重新评估资格",
                    "expected_rule_revision": payload.expected_rule_revision,
                    "current_rule_revision": match.rule_set_revision,
                    "plan_rule_revision": plan.rule_revision,
                },
            )
        match_payload = match.model_dump(mode="json")
        match_payload["placement_change"] = {
            "machine_changed": task.machine_id != move.machine_id,
            "sequence_changed": task.sequence_no != move.sequence_no,
            "time_changed": (
                task.planned_start != move.planned_start
                or task.planned_finish != move.planned_finish
            ),
            "setup_review": (
                "跨机移动，需复核前后任务的换模与转色影响"
                if task.machine_id != move.machine_id
                else "同机重排，需复核相邻任务的换模与转色影响"
            ),
        }
        if match.decision == "FAIL":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "目标机台资格硬失败，禁止移动",
                    "task_id": task.id,
                    "match": match_payload,
                },
            )
        if match.decision == "REVIEW_REQUIRED":
            if not can_override_review:
                raise HTTPException(
                    status_code=403, detail="待复核移动需要发布/覆盖权限"
                )
            if not move.override_reason:
                raise HTTPException(
                    status_code=409, detail="待复核移动必须填写人工覆盖原因"
                )
        match_by_task_id[task.id] = match_payload
        move_results.append(
            InjectionSchedulingTaskMoveResult(
                task_id=task.id,
                from_machine_id=task.machine_id,
                to_machine_id=move.machine_id,
                from_sequence_no=task.sequence_no,
                to_sequence_no=move.sequence_no,
                previous_start=task.planned_start,
                previous_finish=task.planned_finish,
                planned_start=move.planned_start,
                planned_finish=move.planned_finish,
                match=match_payload,
            )
        )

    moving_task_ids = set(move_by_task_id)
    affected_machine_ids = {
        task_by_id[task_id].machine_id for task_id in moving_task_ids
    } | {move.machine_id for move in payload.moves}
    queues: dict[str, list[InjectionSchedulingTask]] = {
        machine_id: sorted(
            [
                task
                for task in tasks
                if task.machine_id == machine_id and task.id not in moving_task_ids
            ],
            key=lambda task: (task.sequence_no, task.id),
        )
        for machine_id in affected_machine_ids
    }
    for move in payload.moves:
        queue = queues.setdefault(move.machine_id, [])
        queue.insert(min(move.sequence_no, len(queue)), task_by_id[move.task_id])

    proposed_by_id: dict[str, dict[str, Any]] = {
        task.id: {
            "id": task.id,
            "machine_id": task.machine_id,
            "sequence_no": task.sequence_no,
            "planned_start": task.planned_start,
            "planned_finish": task.planned_finish,
            "mold_id": task.mold_id,
            "physical_mold_asset_id": task.physical_mold_asset_id,
            "mold_copy_no": task.mold_copy_no,
        }
        for task in tasks
    }
    for machine_id, queue in queues.items():
        for sequence_no, task in enumerate(queue):
            proposed_by_id[task.id]["machine_id"] = machine_id
            proposed_by_id[task.id]["sequence_no"] = sequence_no
    for move in payload.moves:
        proposed_by_id[move.task_id]["planned_start"] = move.planned_start
        proposed_by_id[move.task_id]["planned_finish"] = move.planned_finish

    _validate_proposed_task_windows(list(proposed_by_id.values()))
    changed_tasks = [
        task
        for task in tasks
        if any(
            (
                task.machine_id != proposed_by_id[task.id]["machine_id"],
                task.sequence_no != proposed_by_id[task.id]["sequence_no"],
                task.planned_start != proposed_by_id[task.id]["planned_start"],
                task.planned_finish != proposed_by_id[task.id]["planned_finish"],
            )
        )
    ]
    if not changed_tasks:
        raise HTTPException(status_code=409, detail="任务位置和计划时间没有变化")

    changed_task_ids = {item.id for item in changed_tasks}
    for task in changed_tasks:
        proposed = proposed_by_id[task.id]
        if task.physical_mold_asset_id:
            _ensure_physical_reservation_window_available(
                db,
                physical_asset_id=task.physical_mold_asset_id,
                planned_start=proposed["planned_start"],
                planned_finish=proposed["planned_finish"],
                exclude_task_ids=changed_task_ids,
            )

    timestamp = _now()
    temp_base = max((task.sequence_no for task in tasks), default=0) + len(tasks) + 1000
    try:
        for index, task in enumerate(changed_tasks):
            result = db.execute(
                update(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.id == task.id,
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == plan.id,
                    InjectionSchedulingTask.revision == task.revision,
                )
                .values(sequence_no=temp_base + index)
            )
            if result.rowcount != 1:
                raise _revision_conflict("排产任务", task.revision, task.revision + 1)
            _sync_task_reservation_window(
                db,
                task_id=task.id,
                plan_id=plan.id,
                planned_start=proposed["planned_start"],
                planned_finish=proposed["planned_finish"],
            )
        db.flush()
        for task in changed_tasks:
            proposed = proposed_by_id[task.id]
            move = move_by_task_id.get(task.id)
            values: dict[str, Any] = {
                "machine_id": proposed["machine_id"],
                "sequence_no": proposed["sequence_no"],
                "planned_start": proposed["planned_start"],
                "planned_finish": proposed["planned_finish"],
                "revision": task.revision + 1,
                "updated_by": user.id,
                "updated_by_name": _actor_name(user),
                "updated_at": timestamp,
                "manual_adjusted": (
                    task.manual_adjusted or bool(task.auto_schedule_run_id)
                ),
            }
            if move is not None:
                values.update(
                    estimated_start=move.planned_start,
                    estimated_finish=move.planned_finish,
                    manual_override_reason=(
                        move.override_reason
                        if match_by_task_id[task.id]["decision"] == "REVIEW_REQUIRED"
                        else task.manual_override_reason
                    ),
                )
            result = db.execute(
                update(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.id == task.id,
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == plan.id,
                    InjectionSchedulingTask.revision == task.revision,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                raise _revision_conflict("排产任务", task.revision, task.revision + 1)
        plan_result = db.execute(
            update(InjectionSchedulingPlan)
            .where(
                InjectionSchedulingPlan.id == plan.id,
                InjectionSchedulingPlan.factory_id == factory_id,
                InjectionSchedulingPlan.status == "DRAFT",
                InjectionSchedulingPlan.revision == payload.expected_plan_revision,
            )
            .values(
                revision=payload.expected_plan_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
        )
        if plan_result.rowcount != 1:
            db.rollback()
            latest = _require_plan(db, factory_id, plan.id)
            raise _revision_conflict(
                "计划草案",
                payload.expected_plan_revision,
                latest.revision,
            )
        db.flush()
        refreshed_plan = _require_plan(db, factory_id, plan.id)
        _record_plan_revision(
            db,
            plan=refreshed_plan,
            user=user,
            timestamp=timestamp,
        )
        refreshed_tasks = [
            task_out(_require_task(db, factory_id, plan.id, task.id)).model_dump(
                mode="json"
            )
            for task in changed_tasks
        ]
        serialized_moves = [item.model_dump(mode="json") for item in move_results]
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_tasks_bulk_moved",
            entity_type="plan",
            entity_id=plan.id,
            entity_revision=payload.expected_plan_revision + 1,
            request_id=payload.request_id,
            detail={
                "payload_hash": request_hash,
                "plan_revision": payload.expected_plan_revision + 1,
                "moves": serialized_moves,
                "tasks": refreshed_tasks,
            },
            user=user,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="批量移动违反队列或时间约束"
        ) from exc
    return InjectionSchedulingTaskBulkMoveResult(
        plan=plan_out(db, _require_plan(db, factory_id, plan.id)),
        moves=move_results,
        audit_sequence=audit.sequence,
    )


def publish_plan(
    db: Session,
    plan_id: str,
    payload: InjectionSchedulingPublishInput,
    user: AuthContext,
) -> tuple[InjectionSchedulingPlan, str, int, bool]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    request_hash = _payload_hash(
        {
            "operation": "publish",
            "factory_id": factory_id,
            "plan_id": plan_id,
            "expected_revision": payload.expected_revision,
        }
    )
    replay = db.scalar(
        select(InjectionSchedulingPublishedSnapshot).where(
            InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
            InjectionSchedulingPublishedSnapshot.request_id == payload.request_id,
        )
    )
    if replay is not None:
        if replay.payload_hash != request_hash or replay.plan_id != plan_id:
            raise _idempotency_conflict()
        audit = _event_for_request(db, factory_id, payload.request_id, "plan_published")
        return (
            _require_plan(db, factory_id, replay.plan_id),
            replay.id,
            audit.sequence,
            True,
        )

    plan = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == plan_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="排产计划不存在")
    _require_draft(plan)
    if plan.revision != payload.expected_revision:
        raise _revision_conflict("计划草案", payload.expected_revision, plan.revision)
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
            .order_by(
                InjectionSchedulingTask.machine_id,
                InjectionSchedulingTask.sequence_no,
            )
            .with_for_update()
        ).all()
    )
    if not tasks:
        raise HTTPException(status_code=409, detail="空计划不能发布")
    timestamp = _now()
    previous = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
            InjectionSchedulingPlan.id != plan.id,
        )
        .with_for_update()
    )
    previous_order_ids = (
        {task.order_id for task in plan_tasks(db, factory_id, previous.id)}
        if previous is not None
        else set()
    )
    rebase_detail: dict[str, Any] = {}
    try:
        if plan.based_on_plan_id:
            if previous is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "SUCCESSOR_BASE_PLAN_MISSING",
                        "message": "接班草稿的来源执行计划已不存在",
                    },
                )
            from app.services.injection_scheduling_takeover import (
                rebase_successor_draft,
            )

            rebase_detail = rebase_successor_draft(
                db,
                draft=plan,
                source=previous,
                user=user,
                timestamp=timestamp,
            )
        tasks = plan_tasks(db, factory_id, plan.id)
        reservation_ids_in_published_plan: set[str] = set()
        for task in tasks:
            if not task.physical_mold_asset_id:
                continue
            lineage_task_ids = {task.id}
            if task.source_task_id:
                lineage_task_ids.add(task.source_task_id)
            _ensure_physical_reservation_window_available(
                db,
                physical_asset_id=task.physical_mold_asset_id,
                planned_start=task.planned_start,
                planned_finish=task.planned_finish,
                exclude_task_ids=lineage_task_ids,
            )
            reservation = db.scalar(
                select(InjectionSchedulingMoldReservation)
                .where(
                    InjectionSchedulingMoldReservation.task_id.in_(lineage_task_ids),
                    InjectionSchedulingMoldReservation.status.in_(
                        {"TENTATIVE", "ACTIVE"}
                    ),
                )
                .order_by(InjectionSchedulingMoldReservation.revision.desc())
                .with_for_update()
            )
            if reservation is None:
                reservation = InjectionSchedulingMoldReservation(
                    id=f"ismoldreservation-{uuid4().hex}",
                    physical_asset_id=task.physical_mold_asset_id,
                    factory_id=factory_id,
                    plan_id=plan.id,
                    task_id=task.id,
                    window_start=task.planned_start,
                    window_end=task.planned_finish,
                    status="ACTIVE",
                    revision=1,
                    expires_at="",
                    idempotency_key=f"publish:{plan.id}:{task.id}",
                    source_kind="PLAN_PUBLISH",
                    created_by=user.id,
                    created_at=timestamp,
                    released_at="",
                )
                db.add(reservation)
            else:
                reservation.plan_id = plan.id
                reservation.task_id = task.id
                reservation.window_start = task.planned_start
                reservation.window_end = task.planned_finish
                reservation.status = "ACTIVE"
                reservation.expires_at = ""
                reservation.revision += 1
                reservation.released_at = ""
            reservation_ids_in_published_plan.add(reservation.id)
        if previous is not None:
            stale_reservations = list(
                db.scalars(
                    select(InjectionSchedulingMoldReservation)
                    .where(
                        InjectionSchedulingMoldReservation.plan_id == previous.id,
                        InjectionSchedulingMoldReservation.status.in_(
                            {"TENTATIVE", "ACTIVE"}
                        ),
                    )
                    .with_for_update()
                ).all()
            )
            for reservation in stale_reservations:
                if reservation.id in reservation_ids_in_published_plan:
                    continue
                reservation.status = "RELEASED"
                reservation.revision += 1
                reservation.released_at = timestamp
        if previous is not None:
            db.execute(
                update(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == previous.id,
                )
                .values(active_execution=False)
            )
            previous.status = "ARCHIVED"
            previous.archived_at = timestamp
            previous.updated_at = timestamp
            db.flush()
        db.execute(
            update(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
            .values(active_execution=True)
        )
        published_revision = payload.expected_revision + 1
        plan.status = "PUBLISHED"
        plan.revision = published_revision
        plan.updated_by = user.id
        plan.updated_by_name = _actor_name(user)
        plan.updated_at = timestamp
        plan.published_by = user.id
        plan.published_by_name = _actor_name(user)
        plan.published_at = timestamp
        db.flush()
        _recalculate_plan_queues(
            db,
            plan=plan,
            user=user,
            timestamp=timestamp,
        )
        for order_id in previous_order_ids | {task.order_id for task in tasks}:
            _synchronize_order_schedule_status(
                db,
                factory_id=factory_id,
                order_id=order_id,
                user=user,
                timestamp=timestamp,
            )
        db.flush()
        snapshot_json, snapshot_sha256 = _record_plan_revision(
            db,
            plan=plan,
            user=user,
            timestamp=timestamp,
        )
        snapshot = InjectionSchedulingPublishedSnapshot(
            id=f"issnapshot-{uuid4().hex}",
            factory_id=factory_id,
            plan_id=plan.id,
            plan_revision=published_revision,
            request_id=payload.request_id,
            payload_hash=request_hash,
            snapshot_json=snapshot_json,
            snapshot_sha256=snapshot_sha256,
            published_by=user.id,
            published_by_name=_actor_name(user),
            created_at=timestamp,
        )
        db.add(snapshot)
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_published",
            entity_type="plan",
            entity_id=plan.id,
            entity_revision=published_revision,
            request_id=payload.request_id,
            detail={
                "snapshot_id": snapshot.id,
                "snapshot_sha256": snapshot_sha256,
                "task_count": len(tasks),
                "rebase": rebase_detail,
            },
            user=user,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(InjectionSchedulingPublishedSnapshot).where(
                InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
                InjectionSchedulingPublishedSnapshot.request_id == payload.request_id,
            )
        )
        if replay is not None and replay.payload_hash == request_hash:
            audit = _event_for_request(
                db, factory_id, payload.request_id, "plan_published"
            )
            return (
                _require_plan(db, factory_id, replay.plan_id),
                replay.id,
                audit.sequence,
                True,
            )
        raise HTTPException(status_code=409, detail="计划发布冲突") from exc
    return plan, snapshot.id, audit.sequence, False


def rollback_plan(
    db: Session,
    plan_id: str,
    payload: InjectionSchedulingRollbackInput,
    user: AuthContext,
) -> tuple[InjectionSchedulingPlan, str, int, bool]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    business_date = payload.business_date.isoformat() if payload.business_date else ""
    request_detail = {
        "operation": "rollback",
        "factory_id": factory_id,
        "source_plan_id": plan_id,
        "expected_revision": payload.expected_revision,
        "business_date": business_date,
    }
    request_hash = _payload_hash(request_detail)
    replay = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.rollback_request_id == payload.request_id,
        )
    )
    if replay is not None:
        audit = _event_for_request(
            db, factory_id, payload.request_id, "plan_rolled_back"
        )
        detail = _load_json(audit.detail_json, {})
        if detail.get("payload_hash") != request_hash:
            raise _idempotency_conflict()
        return replay, "", audit.sequence, True
    existing_draft = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if existing_draft is not None:
        raise HTTPException(
            status_code=409, detail="当前厂区已有草案，不能创建回滚草案"
        )
    source = _require_plan(db, factory_id, plan_id)
    if source.status not in {"PUBLISHED", "ARCHIVED"}:
        raise HTTPException(status_code=409, detail="只能从已发布计划创建回滚草案")
    if source.revision != payload.expected_revision:
        raise _revision_conflict(
            "已发布计划", payload.expected_revision, source.revision
        )
    timestamp = _now()
    from app.services.injection_scheduling_takeover import clone_successor_draft

    draft = clone_successor_draft(
        db,
        source=source,
        business_date=business_date or source.business_date,
        user=user,
        timestamp=timestamp,
        rollback_request_id=payload.request_id,
    )
    source_tasks = plan_tasks(db, factory_id, source.id)
    try:
        db.flush()
        _record_plan_revision(
            db,
            plan=draft,
            user=user,
            timestamp=timestamp,
        )
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="plan_rolled_back",
            entity_type="plan",
            entity_id=draft.id,
            entity_revision=1,
            request_id=payload.request_id,
            detail={
                "source_plan_id": source.id,
                "source_revision": source.revision,
                "payload_hash": request_hash,
                "task_count": len(source_tasks),
            },
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(InjectionSchedulingPlan).where(
                InjectionSchedulingPlan.factory_id == factory_id,
                InjectionSchedulingPlan.rollback_request_id == payload.request_id,
            )
        )
        if replay is not None:
            audit = _event_for_request(
                db, factory_id, payload.request_id, "plan_rolled_back"
            )
            if _load_json(audit.detail_json, {}).get("payload_hash") == request_hash:
                return replay, "", audit.sequence, True
        raise HTTPException(status_code=409, detail="回滚草案创建冲突") from exc
    return draft, "", audit.sequence, False


def _recalculate_order_projection(
    db: Session,
    *,
    factory_id: str,
    order_id: str,
    user: AuthContext,
    timestamp: str,
    increment_revision: bool,
) -> None:
    order = _require_order(db, factory_id, order_id)
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.order_id == order_id,
                InjectionSchedulingTask.active_execution.is_(True),
            )
        ).all()
    )
    finish_values = [item.estimated_finish for item in tasks if item.estimated_finish]
    estimated_finish = max(
        finish_values,
        key=lambda value: parse_business_timestamp(value) or business_now(),
        default="",
    )
    estimated_shifts = max(
        (item.estimated_remaining_shifts for item in tasks),
        default=0,
    )
    slack_days = _delivery_slack_days(order.delivery_due_date, estimated_finish)
    if (
        order.estimated_completion_at == estimated_finish
        and order.estimated_remaining_shifts == estimated_shifts
        and order.delivery_slack_days == slack_days
    ):
        return
    order.estimated_completion_at = estimated_finish
    order.estimated_remaining_shifts = estimated_shifts
    order.delivery_slack_days = slack_days
    if increment_revision:
        order.revision += 1
        order.updated_by = user.id
        order.updated_by_name = _actor_name(user)
        order.updated_at = timestamp


def _recalculate_machine_queue(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    machine_id: str,
    user: AuthContext,
    timestamp: str,
    anchor: datetime | None = None,
    reported_task_id: str = "",
    reported_order_id: str = "",
    reported_downtime_minutes: int = 0,
    increment_task_revisions: bool,
    increment_order_revisions: bool,
) -> list[str]:
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == plan.factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.machine_id == machine_id,
                InjectionSchedulingTask.active_execution.is_(True),
            )
            .order_by(
                InjectionSchedulingTask.sequence_no,
                InjectionSchedulingTask.id,
            )
        ).all()
    )
    from app.models.injection_scheduling_scheduler import (
        InjectionSchedulingMachineCalendar,
    )
    from app.services.injection_scheduling_projection import (
        load_calculation_context,
        project_task_window,
    )

    mold_ids = {item.mold_id for item in tasks if item.mold_id}
    molds = (
        {
            item.id: item
            for item in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == plan.factory_id,
                    InjectionSchedulingMold.id.in_(mold_ids),
                )
            ).all()
        }
        if mold_ids
        else {}
    )
    calendars = list(
        db.scalars(
            select(InjectionSchedulingMachineCalendar)
            .where(
                InjectionSchedulingMachineCalendar.factory_id == plan.factory_id,
                InjectionSchedulingMachineCalendar.machine_id == machine_id,
            )
            .order_by(
                InjectionSchedulingMachineCalendar.window_start,
                InjectionSchedulingMachineCalendar.id,
            )
        ).all()
    )
    calculation_context = load_calculation_context(
        db,
        factory_id=plan.factory_id,
        mold_ids=mold_ids,
    )
    cursor: datetime | None = None
    affected_order_ids: set[str] = set()
    changed_task_ids: list[str] = []
    reported_index = next(
        (index for index, item in enumerate(tasks) if item.id == reported_task_id),
        0,
    )
    for index, task in enumerate(tasks):
        if reported_task_id and anchor is not None and index < reported_index:
            cursor = (
                parse_business_timestamp(task.estimated_finish)
                or parse_business_timestamp(task.planned_finish)
                or cursor
            )
            continue
        order = _require_order(db, plan.factory_id, task.order_id)
        planned_start = parse_business_timestamp(task.planned_start)
        planned_finish = parse_business_timestamp(task.planned_finish)
        if planned_start is None or planned_finish is None:
            raise HTTPException(status_code=409, detail="排产任务计划时间无效")
        earliest_start = max(
            value for value in (planned_start, cursor) if value is not None
        )
        if task.id == reported_task_id and anchor is not None:
            earliest_start = max(earliest_start, anchor)
        planned_quantity = (
            _decimal(task.allocated_quantity)
            if _decimal(task.allocated_quantity) > 0
            else _decimal(order.order_quantity)
        )
        completed_quantity = (
            min(
                planned_quantity,
                _decimal(task.takeover_source_completed_quantity)
                + max(
                    _decimal(task.reported_quantity)
                    - _decimal(task.inherited_report_counter),
                    Decimal(0),
                ),
            )
            if _decimal(task.allocated_quantity) > 0
            else _decimal(order.completed_quantity)
        )
        previous_task = tasks[index - 1] if index > 0 else None
        calculation = project_task_window(
            order=order,
            planned_quantity=planned_quantity,
            completed_quantity=completed_quantity,
            shift_target_quantity=task.shift_target_quantity,
            previous_mold=(
                molds.get(previous_task.mold_id or "")
                if previous_task is not None
                else None
            ),
            current_mold=molds.get(task.mold_id or ""),
            earliest_start=earliest_start,
            calendars=calendars,
            context=calculation_context,
            continuation_anchor={
                "reported_task_id": reported_task_id,
                "queue_predecessor_task_id": previous_task.id
                if previous_task is not None
                else "",
                "earliest_start": _iso_seconds(earliest_start),
            },
            extra_downtime_minutes=(
                reported_downtime_minutes if task.id == reported_task_id else 0
            ),
        )
        if task.execution_status in {"COMPLETED", "CANCELLED"}:
            projected_start = (
                anchor
                if task.id == reported_task_id and anchor is not None
                else earliest_start
            )
            projected_finish = projected_start
            calculation["estimated_start"] = _iso_seconds(projected_start)
            calculation["estimated_finish"] = _iso_seconds(projected_finish)
            calculation["estimated_remaining_shifts"] = 0
            calculation["production_minutes"] = 0
            calculation["setup_minutes"] = 0
            calculation["changeover_type"] = "COMPLETED"
        else:
            projected_start = parse_business_timestamp(calculation["estimated_start"])
            projected_finish = parse_business_timestamp(calculation["estimated_finish"])
            if projected_start is None or projected_finish is None:
                raise HTTPException(status_code=409, detail="统一计算结果时间无效")
        estimated_start = str(calculation["estimated_start"])
        estimated_finish = str(calculation["estimated_finish"])
        remaining_shifts = int(calculation["estimated_remaining_shifts"])
        slack_days = calculation["delivery_slack_days"]
        changed = (
            task.estimated_start != estimated_start
            or task.estimated_finish != estimated_finish
            or task.estimated_remaining_shifts != remaining_shifts
            or task.delivery_slack_days != slack_days
            or task.setup_minutes != int(calculation["setup_minutes"])
            or task.production_minutes != int(calculation["production_minutes"])
            or task.planned_downtime_minutes
            != int(calculation["calendar_delay_minutes"])
            + (reported_downtime_minutes if task.id == reported_task_id else 0)
            or task.changeover_type != str(calculation["changeover_type"])
        )
        task.estimated_start = estimated_start
        task.estimated_finish = estimated_finish
        task.estimated_remaining_shifts = remaining_shifts
        task.delivery_slack_days = slack_days
        task.setup_minutes = int(calculation["setup_minutes"])
        task.production_minutes = int(calculation["production_minutes"])
        task.planned_downtime_minutes = int(calculation["calendar_delay_minutes"]) + (
            reported_downtime_minutes if task.id == reported_task_id else 0
        )
        task.changeover_type = str(calculation["changeover_type"])
        task.auto_explanation_json = _json({"calculation": calculation})
        if changed:
            changed_task_ids.append(task.id)
            if increment_task_revisions and task.id != reported_task_id:
                task.revision += 1
                task.updated_by = user.id
                task.updated_by_name = _actor_name(user)
                task.updated_at = timestamp
        affected_order_ids.add(order.id)
        cursor = projected_finish
    db.flush()
    for order_id in affected_order_ids:
        _recalculate_order_projection(
            db,
            factory_id=plan.factory_id,
            order_id=order_id,
            user=user,
            timestamp=timestamp,
            increment_revision=(
                increment_order_revisions and order_id != reported_order_id
            ),
        )
    return changed_task_ids


def _recalculate_plan_queues(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    user: AuthContext,
    timestamp: str,
) -> None:
    machine_ids = sorted(
        {task.machine_id for task in plan_tasks(db, plan.factory_id, plan.id)}
    )
    for machine_id in machine_ids:
        _recalculate_machine_queue(
            db,
            plan=plan,
            machine_id=machine_id,
            user=user,
            timestamp=timestamp,
            increment_task_revisions=False,
            increment_order_revisions=True,
        )


def _published_successor_task_id(
    db: Session,
    *,
    factory_id: str,
    stale_task: InjectionSchedulingTask,
) -> str | None:
    current = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
    )
    if current is None or current.id == stale_task.plan_id:
        return None
    candidates = list(
        db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == current.id,
                InjectionSchedulingTask.order_id == stale_task.order_id,
            )
        ).all()
    )
    task_cache: dict[str, InjectionSchedulingTask | None] = {}
    for candidate in candidates:
        source_id = candidate.source_task_id
        visited: set[str] = set()
        while source_id and source_id not in visited:
            if source_id == stale_task.id:
                return candidate.id
            visited.add(source_id)
            if source_id not in task_cache:
                task_cache[source_id] = db.scalar(
                    select(InjectionSchedulingTask).where(
                        InjectionSchedulingTask.factory_id == factory_id,
                        InjectionSchedulingTask.id == source_id,
                    )
                )
            source = task_cache[source_id]
            source_id = source.source_task_id if source is not None else None
    return None


def _require_or_create_plan_order_state(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    task: InjectionSchedulingTask,
    order: InjectionSchedulingOrder,
    user: AuthContext,
    timestamp: str,
) -> InjectionSchedulingPlanOrderState:
    state = db.scalar(
        select(InjectionSchedulingPlanOrderState)
        .where(
            InjectionSchedulingPlanOrderState.factory_id == plan.factory_id,
            InjectionSchedulingPlanOrderState.plan_id == plan.id,
            InjectionSchedulingPlanOrderState.order_id == order.id,
        )
        .with_for_update()
    )
    if state is not None:
        return state
    state = InjectionSchedulingPlanOrderState(
        id=f"ispostate-{uuid4().hex}",
        factory_id=plan.factory_id,
        plan_id=plan.id,
        order_id=order.id,
        stable_order_key=task.stable_order_key or _stable_order_key(order),
        order_quantity=order.order_quantity,
        delivery_start_date=order.delivery_start_date,
        delivery_due_date=order.delivery_due_date,
        takeover_source_completed_quantity=order.source_completed_quantity,
        report_increment_total=Decimal(0),
        progress_adjustment_total=Decimal(0),
        completed_quantity=order.source_completed_quantity,
        status="SCHEDULED",
        quantity_scope="ORDER_CUMULATIVE",
        source_batch_id=task.import_batch_id,
        source_sheet_name=task.source_sheet_name,
        source_row=task.source_row,
        source_profile_id=task.profile_id,
        source_profile_revision=task.profile_revision,
        source_lineage_json=_json({"legacy_backfill": True}),
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        updated_by=user.id,
        updated_by_name=_actor_name(user),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(state)
    db.flush()
    return state


def create_shift_report(
    db: Session,
    task_id: str,
    payload: InjectionSchedulingShiftReportCreate,
    user: AuthContext,
    *,
    commit: bool = True,
) -> tuple[
    InjectionSchedulingShiftReport,
    InjectionSchedulingTask,
    InjectionSchedulingOrder,
    int,
    bool,
]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    request_payload = payload.model_dump(mode="json") | {"task_id": task_id}
    request_hash = _payload_hash(request_payload)
    replay = db.scalar(
        select(InjectionSchedulingShiftReport).where(
            InjectionSchedulingShiftReport.factory_id == factory_id,
            InjectionSchedulingShiftReport.request_id == payload.request_id,
        )
    )
    if replay is not None:
        if replay.payload_hash != request_hash or replay.task_id != task_id:
            raise _idempotency_conflict()
        audit = _event_for_request(
            db, factory_id, payload.request_id, "shift_report_recorded"
        )
        return (
            replay,
            _require_task_by_id(db, factory_id, replay.task_id),
            _require_order(db, factory_id, replay.order_id),
            audit.sequence,
            True,
        )
    task_locator = db.scalar(
        select(InjectionSchedulingTask).where(
            InjectionSchedulingTask.factory_id == factory_id,
            InjectionSchedulingTask.id == task_id,
        )
    )
    if task_locator is None:
        raise HTTPException(status_code=404, detail="排产任务不存在")
    plan = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == task_locator.plan_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise HTTPException(status_code=409, detail="任务关联计划不存在")
    task = db.scalar(
        select(InjectionSchedulingTask)
        .where(
            InjectionSchedulingTask.factory_id == factory_id,
            InjectionSchedulingTask.id == task_id,
            InjectionSchedulingTask.plan_id == plan.id,
        )
        .with_for_update()
    )
    if task is None:
        raise HTTPException(status_code=409, detail="排产任务已变化，请刷新后重试")
    if plan.status != "PUBLISHED" or not task.active_execution:
        successor_task_id = _published_successor_task_id(
            db,
            factory_id=factory_id,
            stale_task=task,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_EXECUTION_TASK",
                "message": "只能对当前已发布计划回报生产数据",
                "stale_task_id": task.id,
                "successor_task_id": successor_task_id,
            },
        )
    if task.revision != payload.expected_revision:
        raise _revision_conflict("排产任务", payload.expected_revision, task.revision)
    order = db.scalar(
        select(InjectionSchedulingOrder)
        .where(
            InjectionSchedulingOrder.factory_id == factory_id,
            InjectionSchedulingOrder.id == task.order_id,
        )
        .with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=409, detail="任务关联订单不存在")
    reported = _decimal(payload.reported_quantity)
    if payload.quantity_mode == "CUMULATIVE":
        if reported < task.reported_quantity:
            raise HTTPException(
                status_code=409, detail="累计完成数不能小于当前已回报数"
            )
        increment = reported - task.reported_quantity
    else:
        increment = reported
    if payload.reported_status == "RUNNING":
        running = db.scalar(
            select(InjectionSchedulingTask.id).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.machine_id == task.machine_id,
                InjectionSchedulingTask.active_execution.is_(True),
                InjectionSchedulingTask.execution_status == "RUNNING",
                InjectionSchedulingTask.id != task.id,
            )
        )
        if running is not None:
            raise HTTPException(status_code=409, detail="同一机台已有正在生产任务")
    timestamp = _now()
    state = _require_or_create_plan_order_state(
        db,
        plan=plan,
        task=task,
        order=order,
        user=user,
        timestamp=timestamp,
    )
    report = InjectionSchedulingShiftReport(
        id=f"isreport-{uuid4().hex}",
        factory_id=factory_id,
        task_id=task.id,
        order_id=order.id,
        business_date=payload.business_date.isoformat(),
        shift_code=payload.shift_code,
        quantity_mode=payload.quantity_mode,
        reported_quantity=reported,
        normalized_increment_quantity=increment,
        shift_target_quantity=_decimal(payload.shift_target_quantity),
        downtime_minutes=payload.downtime_minutes,
        exception_code=payload.exception_code,
        exception_detail=payload.exception_detail,
        reported_status=payload.reported_status,
        request_id=payload.request_id,
        payload_hash=request_hash,
        reported_by=user.id,
        reported_by_name=_actor_name(user),
        created_at=timestamp,
    )
    db.add(report)
    try:
        db.flush()
        task_result = db.execute(
            update(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.id == task.id,
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.revision == payload.expected_revision,
            )
            .values(
                reported_quantity=task.reported_quantity + increment,
                execution_status=payload.reported_status,
                revision=payload.expected_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
        )
        if task_result.rowcount != 1:
            db.rollback()
            latest = _require_task_by_id(db, factory_id, task.id)
            raise _revision_conflict(
                "排产任务", payload.expected_revision, latest.revision
            )
        state.report_increment_total = (
            _decimal(state.report_increment_total) + increment
        )
        completed = max(
            _decimal(state.takeover_source_completed_quantity)
            + _decimal(state.report_increment_total)
            + _decimal(state.progress_adjustment_total),
            Decimal(0),
        )
        state.completed_quantity = completed
        state.status = "COMPLETED" if completed >= state.order_quantity else "SCHEDULED"
        state.revision += 1
        state.updated_by = user.id
        state.updated_by_name = _actor_name(user)
        state.updated_at = timestamp
        order.completed_quantity = completed
        order.status = "COMPLETED" if completed >= order.order_quantity else "SCHEDULED"
        order.revision += 1
        order.updated_by = user.id
        order.updated_by_name = _actor_name(user)
        order.updated_at = timestamp
        if order.status == "COMPLETED":
            db.execute(
                update(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.id == task.id,
                    InjectionSchedulingTask.factory_id == factory_id,
                )
                .values(execution_status="COMPLETED")
            )
            report.reported_status = "COMPLETED"
        if payload.reported_status == "COMPLETED" or order.status == "COMPLETED":
            _release_task_reservation(db, task_id=task.id, timestamp=timestamp)
        db.flush()
        changed_projection_task_ids = _recalculate_machine_queue(
            db,
            plan=plan,
            machine_id=task.machine_id,
            user=user,
            timestamp=timestamp,
            anchor=parse_business_timestamp(timestamp),
            reported_task_id=task.id,
            reported_order_id=order.id,
            reported_downtime_minutes=payload.downtime_minutes,
            increment_task_revisions=True,
            increment_order_revisions=True,
        )
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="shift_report_recorded",
            entity_type="task",
            entity_id=task.id,
            entity_revision=payload.expected_revision + 1,
            request_id=payload.request_id,
            detail={
                "report_id": report.id,
                "order_id": order.id,
                "increment_quantity": float(increment),
                "order_completed_quantity": float(completed),
                "estimated_completion_at": order.estimated_completion_at,
                "estimated_remaining_shifts": order.estimated_remaining_shifts,
                "delivery_slack_days": order.delivery_slack_days,
                "recalculated_task_ids": changed_projection_task_ids,
                "task": task_out(
                    _require_task_by_id(db, factory_id, task.id)
                ).model_dump(mode="json"),
                "order": order_out(_require_order(db, factory_id, order.id)).model_dump(
                    mode="json"
                ),
                "tasks": [
                    task_out(
                        _require_task_by_id(db, factory_id, changed_task_id)
                    ).model_dump(mode="json")
                    for changed_task_id in changed_projection_task_ids
                ],
            },
            user=user,
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(InjectionSchedulingShiftReport).where(
                InjectionSchedulingShiftReport.factory_id == factory_id,
                InjectionSchedulingShiftReport.request_id == payload.request_id,
            )
        )
        if replay is not None and replay.payload_hash == request_hash:
            audit = _event_for_request(
                db, factory_id, payload.request_id, "shift_report_recorded"
            )
            return (
                replay,
                _require_task_by_id(db, factory_id, replay.task_id),
                _require_order(db, factory_id, replay.order_id),
                audit.sequence,
                True,
            )
        raise HTTPException(status_code=409, detail="班次回报写入冲突") from exc
    return (
        report,
        _require_task_by_id(db, factory_id, task.id),
        _require_order(db, factory_id, order.id),
        audit.sequence,
        False,
    )


def create_shift_reports_bulk(
    db: Session,
    payload: InjectionSchedulingShiftReportBulkCreate,
    user: AuthContext,
) -> InjectionSchedulingShiftReportBulkResult:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    results: list[InjectionSchedulingShiftReportResult] = []
    try:
        for item in payload.reports:
            item_payload = item.model_dump(exclude={"task_id"})
            report, task, order, audit_sequence, replay = create_shift_report(
                db,
                item.task_id,
                InjectionSchedulingShiftReportCreate(
                    factory_id=factory_id,
                    **item_payload,
                ),
                user,
                commit=False,
            )
            results.append(
                InjectionSchedulingShiftReportResult(
                    report=shift_report_out(report),
                    task=task_out(task),
                    order=order_out(order),
                    audit_sequence=audit_sequence,
                    idempotent_replay=replay,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return InjectionSchedulingShiftReportBulkResult(
        results=results,
        latest_sequence=latest_event_sequence(db, factory_id),
    )


def list_events(
    db: Session,
    factory_id: str,
    *,
    after_sequence: int,
    limit: int,
) -> list[InjectionSchedulingAuditEvent]:
    factory_id = require_injection_scheduling_factory(factory_id)
    return list(
        db.scalars(
            select(InjectionSchedulingAuditEvent)
            .where(
                InjectionSchedulingAuditEvent.factory_id == factory_id,
                InjectionSchedulingAuditEvent.sequence > after_sequence,
            )
            .order_by(InjectionSchedulingAuditEvent.sequence)
            .limit(limit)
        ).all()
    )


def _require_machine(
    db: Session,
    factory_id: str,
    machine_id: str,
) -> InjectionSchedulingMachine:
    record = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.factory_id == factory_id,
            InjectionSchedulingMachine.id == machine_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="机台不存在")
    return record


def _require_mold(
    db: Session,
    factory_id: str,
    mold_id: str,
) -> InjectionSchedulingMold:
    record = db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.factory_id == factory_id,
            InjectionSchedulingMold.id == mold_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="模具不存在")
    return record


def _require_order(
    db: Session,
    factory_id: str,
    order_id: str,
) -> InjectionSchedulingOrder:
    record = db.scalar(
        select(InjectionSchedulingOrder).where(
            InjectionSchedulingOrder.factory_id == factory_id,
            InjectionSchedulingOrder.id == order_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return record


def _require_plan(
    db: Session,
    factory_id: str,
    plan_id: str,
) -> InjectionSchedulingPlan:
    record = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.id == plan_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="排产计划不存在")
    return record


def _require_task(
    db: Session,
    factory_id: str,
    plan_id: str,
    task_id: str,
) -> InjectionSchedulingTask:
    record = db.scalar(
        select(InjectionSchedulingTask).where(
            InjectionSchedulingTask.factory_id == factory_id,
            InjectionSchedulingTask.plan_id == plan_id,
            InjectionSchedulingTask.id == task_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="排产任务不存在")
    return record


def _require_task_by_id(
    db: Session,
    factory_id: str,
    task_id: str,
) -> InjectionSchedulingTask:
    record = db.scalar(
        select(InjectionSchedulingTask).where(
            InjectionSchedulingTask.factory_id == factory_id,
            InjectionSchedulingTask.id == task_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="排产任务不存在")
    return record


def _require_draft(plan: InjectionSchedulingPlan) -> None:
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已发布计划不可修改")


def _task_update_values(
    task: InjectionSchedulingTask,
    payload: InjectionSchedulingTaskUpdate,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "machine_id": payload.machine_id or task.machine_id,
        "order_id": payload.order_id or task.order_id,
        "mold_id": payload.mold_id if payload.mold_id is not None else task.mold_id,
        "mold_copy_no": (
            payload.mold_copy_no
            if payload.mold_copy_no is not None
            else task.mold_copy_no
        ),
        "sequence_no": (
            payload.sequence_no if payload.sequence_no is not None else task.sequence_no
        ),
        "execution_status": payload.execution_status or task.execution_status,
        "planned_start": payload.planned_start or task.planned_start,
        "planned_finish": payload.planned_finish or task.planned_finish,
        "shift_target_quantity": (
            _decimal(payload.shift_target_quantity)
            if payload.shift_target_quantity is not None
            else task.shift_target_quantity
        ),
        "locked": payload.locked if payload.locked is not None else task.locked,
        "manual_override_reason": (
            payload.manual_override_reason
            if payload.manual_override_reason is not None
            else task.manual_override_reason
        ),
    }
    try:
        planned_start = datetime.fromisoformat(values["planned_start"])
        planned_finish = datetime.fromisoformat(values["planned_finish"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="计划时间格式无效") from exc
    if planned_start >= planned_finish:
        raise HTTPException(status_code=422, detail="计划开始时间必须早于计划完成时间")
    if values["locked"] and not values["manual_override_reason"]:
        raise HTTPException(status_code=422, detail="锁定任务必须填写人工覆盖原因")
    return values


def _validate_task_references(
    db: Session,
    factory_id: str,
    values: dict[str, Any],
) -> InjectionSchedulingOrder:
    _require_machine(db, factory_id, values["machine_id"])
    order = _require_order(db, factory_id, values["order_id"])
    if order.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="已完成或已取消订单不可排程")
    if values["mold_id"] is not None:
        _require_mold(db, factory_id, values["mold_id"])
    return order


def _validate_schedule_conflicts(
    db: Session,
    *,
    factory_id: str,
    plan_id: str,
    machine_id: str,
    mold_id: str | None,
    mold_copy_no: int,
    planned_start: str,
    planned_finish: str,
    physical_mold_asset_id: str | None = None,
    exclude_task_id: str = "",
) -> None:
    start = datetime.fromisoformat(planned_start)
    finish = datetime.fromisoformat(planned_finish)
    if mold_id is not None:
        mold = _require_mold(db, factory_id, mold_id)
        if mold_copy_no > mold.copy_count:
            raise HTTPException(status_code=409, detail="模具副本号超过可用副本数量")
    existing_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan_id,
                InjectionSchedulingTask.id != exclude_task_id,
            )
        ).all()
    )
    for existing in existing_tasks:
        existing_start = datetime.fromisoformat(existing.planned_start)
        existing_finish = datetime.fromisoformat(existing.planned_finish)
        if start >= existing_finish or finish <= existing_start:
            continue
        if existing.machine_id == machine_id:
            raise HTTPException(status_code=409, detail="同一机台的排产时间不可重叠")
        if (
            physical_mold_asset_id is not None
            and existing.physical_mold_asset_id == physical_mold_asset_id
        ):
            raise HTTPException(status_code=409, detail="同一实物模具不可重叠排产")
        if (
            mold_id is not None
            and existing.mold_id == mold_id
            and existing.mold_copy_no == mold_copy_no
        ):
            raise HTTPException(status_code=409, detail="同一实体模具副本不可重叠排产")


def _synchronize_order_schedule_status(
    db: Session,
    *,
    factory_id: str,
    order_id: str,
    user: AuthContext,
    timestamp: str,
) -> None:
    order = _require_order(db, factory_id, order_id)
    if order.status in {"COMPLETED", "CANCELLED"}:
        return
    scheduled_task_id = db.scalar(
        select(InjectionSchedulingTask.id).where(
            InjectionSchedulingTask.factory_id == factory_id,
            InjectionSchedulingTask.order_id == order_id,
            InjectionSchedulingTask.plan_id.in_(
                select(InjectionSchedulingPlan.id).where(
                    InjectionSchedulingPlan.factory_id == factory_id,
                    InjectionSchedulingPlan.status.in_(("DRAFT", "PUBLISHED")),
                )
            ),
        )
    )
    status = "SCHEDULED" if scheduled_task_id is not None else "BACKLOG"
    if order.status == status:
        return
    order.status = status
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = _actor_name(user)
    order.updated_at = timestamp


def _record_plan_revision(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    user: AuthContext,
    timestamp: str,
) -> tuple[str, str]:
    snapshot_payload = _plan_snapshot(db, plan)
    snapshot_json = _json(snapshot_payload)
    snapshot_sha256 = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    db.add(
        InjectionSchedulingPlanRevision(
            id=f"isrevision-{uuid4().hex}",
            factory_id=plan.factory_id,
            plan_id=plan.id,
            plan_revision=plan.revision,
            snapshot_json=snapshot_json,
            snapshot_sha256=snapshot_sha256,
            created_by=user.id,
            created_by_name=_actor_name(user),
            created_at=timestamp,
        )
    )
    db.flush()
    return snapshot_json, snapshot_sha256


def _plan_snapshot(
    db: Session,
    plan: InjectionSchedulingPlan,
) -> dict[str, Any]:
    tasks = plan_tasks(db, plan.factory_id, plan.id)
    order_ids = sorted({task.order_id for task in tasks})
    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder)
            .where(
                InjectionSchedulingOrder.factory_id == plan.factory_id,
                InjectionSchedulingOrder.id.in_(order_ids),
            )
            .order_by(InjectionSchedulingOrder.id)
        ).all()
    )
    return {
        "schema_version": "phase3-v1",
        "factory_id": plan.factory_id,
        "plan_id": plan.id,
        "plan_revision": plan.revision,
        "business_date": plan.business_date,
        "rule_set_id": plan.rule_set_id,
        "rule_revision": plan.rule_revision,
        "export_profile_id": plan.export_profile_id,
        "export_profile_revision": plan.export_profile_revision,
        "export_profile_family": plan.export_profile_family,
        "export_renderer_code": plan.export_renderer_code,
        "export_binding_source": plan.export_binding_source,
        "calculation_version": plan.calculation_version,
        "tasks": [task_out(item).model_dump(mode="json") for item in tasks],
        "orders": [order_out(item).model_dump(mode="json") for item in orders],
    }


def _event_for_request(
    db: Session,
    factory_id: str,
    request_id: str,
    event_type: str,
) -> InjectionSchedulingAuditEvent:
    record = db.scalar(
        select(InjectionSchedulingAuditEvent).where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.request_id == request_id,
            InjectionSchedulingAuditEvent.event_type == event_type,
        )
    )
    if record is None:
        raise HTTPException(status_code=409, detail="幂等请求缺少对应审计事件")
    return record
