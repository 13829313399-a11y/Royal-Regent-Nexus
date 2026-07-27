from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
from app.models.injection_schedule import (
    InjectionMachineMaster,
    InjectionMoldMaster,
    InjectionOrderMaster,
    InjectionScheduleActualCorrection,
    InjectionScheduleRuleConfig,
    InjectionScheduleReplanRun,
    InjectionScheduleShiftActual,
    InjectionScheduleTask,
    InjectionScheduleVersion,
)
from app.schemas.injection_schedule import (
    InjectionScheduleAutoDraftRequest,
    InjectionScheduleCommand,
    InjectionScheduleReplanRequest,
    InjectionScheduleShiftActualCorrectionRequest,
    InjectionScheduleShiftActualCreateRequest,
    InjectionScheduleVersionCreateRequest,
)
from app.services.auth import AuthContext
from app.services.injection_schedule import (
    apply_one_command,
    create_version,
    list_tasks,
    load_order_for_version,
    load_task_for_version,
    load_version,
    normalize_lane_sequences,
    prepare_lane_insert,
    serialize_version,
    version_summary,
)
from app.services.injection_schedule_excel import canonical_json, normalize_key
from app.services.injection_schedule_import import (
    add_audit_event,
    json_list,
    json_object,
    now_text,
    revision_conflict,
    serialize_order,
)
from app.services.injection_schedule_phase4_engine import (
    build_projection_rows,
    choose_earliest_eligible_machine,
    plan_lane_locally,
    prioritize_auto_orders,
)
from app.services.injection_schedule_recommendation import (
    AutoRecommendationBatch,
)
from app.services.injection_schedule_rules import (
    calculate_transition_setup,
    canonical_color_key,
)
from app.services.injection_schedule_validation import build_version_data_hash


def generate_auto_draft(
    db: Session,
    factory_id: str,
    source_version_id: str,
    payload: InjectionScheduleAutoDraftRequest,
    actor: AuthContext,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    source = _load_source_with_cas(
        db,
        factory_id,
        source_version_id,
        payload.expected_revision,
    )
    context_hash = _context_hash(
        db,
        source,
        "auto_draft",
        payload.model_dump(
            exclude={"dry_run", "expected_context_hash", "request_id"}
        ),
    )
    request_id = payload.request_id.strip() or f"ISRQ-{uuid4().hex.upper()}"
    replay = _load_replan_replay(
        db,
        factory_id,
        request_id,
        context_hash,
    )
    if replay is not None:
        return replay
    _verify_expected_context(
        payload.expected_context_hash,
        context_hash,
        required=not payload.dry_run,
    )
    horizon = parse_business_timestamp(payload.planning_horizon_end_at)
    plan_base = parse_business_timestamp(source.plan_base_at)
    if (
        horizon is not None
        and plan_base is not None
        and horizon <= plan_base
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_planning_horizon",
                "message": "自动排程截止时间必须晚于版本计划基准时间",
                "plan_base_at": source.plan_base_at,
                "planning_horizon_end_at": payload.planning_horizon_end_at,
            },
        )

    target = _clone_phase4_draft(
        db,
        source,
        actor,
        name=payload.name or f"{source.name}（自动排程）",
        reason=payload.reason,
    )
    before_tasks = list_tasks(db, target)
    allocated = _allocated_qty_by_order(db, target)
    orders = list(
        db.scalars(
            select(InjectionOrderMaster).where(
                InjectionOrderMaster.factory_id == factory_id,
                InjectionOrderMaster.status == "open",
                InjectionOrderMaster.outstanding_qty > 0,
            )
        ).all()
    )
    if payload.order_ids:
        requested = set(payload.order_ids)
        found = {item.id for item in orders if item.id in requested}
        missing = sorted(requested - found)
        if missing:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "auto_order_not_found",
                    "message": "部分自动排程订单不存在、已关闭或不属于该厂区",
                    "order_ids": missing,
                },
            )
        orders = [item for item in orders if item.id in requested]
    pending = [
        item
        for item in orders
        if item.outstanding_qty - allocated.get(item.id, 0.0) > 1e-6
    ]
    ordered = prioritize_auto_orders(
        [
            {
                "id": item.id,
                "priority_flag": item.priority_flag,
                "priority_code": item.priority_code,
                "delivery_due_date": item.delivery_due_date,
                "downstream_urgency": item.downstream_urgency,
                "outstanding_qty": item.outstanding_qty
                - allocated.get(item.id, 0.0),
            }
            for item in pending
        ]
    )
    order_by_id = {item.id: item for item in pending}
    recommendation_batch = AutoRecommendationBatch.load(db, target)
    affected_machine_ids: set[str] = set()
    affected_order_ids: set[str] = set()
    touched_task_ids: set[str] = set()
    manual_review_count = 0
    blocked_count = 0
    unscheduled_order_ids: list[str] = []
    for order_info in ordered:
        order = order_by_id[str(order_info["id"])]
        remaining = order.outstanding_qty - allocated.get(order.id, 0.0)
        result = _auto_assign_order(
            db,
            target,
            order,
            remaining,
            actor,
            recommendation_batch,
            affected_machine_ids,
            touched_task_ids,
            horizon=horizon,
        )
        if result == "scheduled":
            affected_order_ids.add(order.id)
            allocated[order.id] = allocated.get(order.id, 0.0) + remaining
        elif result == "manual_review":
            manual_review_count += 1
            unscheduled_order_ids.append(order.id)
        else:
            blocked_count += 1
            unscheduled_order_ids.append(order.id)

    db.flush()
    after_tasks = list_tasks(db, target)
    scheduled_order_count = len(affected_order_ids)
    (
        affected_machine_ids,
        affected_order_ids,
        affected_task_ids,
    ) = _changed_scope(before_tasks, after_tasks)
    impact = _impact(
        before_tasks,
        after_tasks,
        considered=len(ordered),
        scheduled=scheduled_order_count,
        manual_review=manual_review_count,
        blocked=blocked_count,
        unscheduled=unscheduled_order_ids,
    )
    response = _finish_replan(
        db,
        source,
        target,
        trigger_type="auto_draft",
        context_hash=context_hash,
        request_id=request_id,
        reason=payload.reason,
        affected_machine_ids=affected_machine_ids,
        affected_order_ids=affected_order_ids,
        affected_task_ids=affected_task_ids,
        impact=impact,
        actor=actor,
        ip_address=ip_address,
        dry_run=payload.dry_run,
    )
    return response


def replan_locally(
    db: Session,
    factory_id: str,
    source_version_id: str,
    payload: InjectionScheduleReplanRequest,
    actor: AuthContext,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    source = _load_source_with_cas(
        db,
        factory_id,
        source_version_id,
        payload.expected_revision,
    )
    context_hash = _context_hash(
        db,
        source,
        payload.trigger.type,
        payload.model_dump(
            exclude={"dry_run", "expected_context_hash", "request_id"}
        ),
    )
    request_id = payload.request_id.strip() or f"ISRQ-{uuid4().hex.upper()}"
    replay = _load_replan_replay(
        db,
        factory_id,
        request_id,
        context_hash,
    )
    if replay is not None:
        return replay
    _verify_expected_context(
        payload.expected_context_hash,
        context_hash,
        required=not payload.dry_run,
    )
    target = _clone_phase4_draft(
        db,
        source,
        actor,
        name=payload.name
        or (
            f"{source.name}（急单局部重排）"
            if payload.trigger.type == "urgent_order"
            else f"{source.name}（停机局部重排）"
        ),
        reason=payload.reason,
    )
    before_tasks = list_tasks(db, target)
    affected_machine_ids: set[str] = set()
    affected_order_ids: set[str] = set()
    touched_task_ids: set[str] = set()
    if payload.trigger.type == "urgent_order":
        _replan_urgent_order(
            db,
            target,
            payload,
            actor,
            affected_machine_ids,
            affected_order_ids,
            touched_task_ids,
        )
    else:
        _replan_downtime(
            db,
            target,
            payload,
            affected_machine_ids,
            affected_order_ids,
        )
    normalize_lane_sequences(db, target, affected_machine_ids)
    if payload.trigger.type == "urgent_order":
        _refresh_lane_transitions(
            db,
            target,
            affected_machine_ids,
            actor,
            touched_task_ids,
        )
    downtime_start = (
        parse_business_timestamp(payload.trigger.start_at)
        if payload.trigger.type == "machine_downtime"
        else None
    )
    _reflow_machines(
        db,
        target,
        affected_machine_ids,
        actor,
        touched_task_ids,
        freeze_before_at=parse_business_timestamp(
            payload.scope.freeze_before_at
        ),
        preserve_finished_before_at=downtime_start,
    )
    after_tasks = list_tasks(db, target)
    (
        changed_machine_ids,
        affected_order_ids,
        affected_task_ids,
    ) = _changed_scope(before_tasks, after_tasks)
    affected_machine_ids = changed_machine_ids
    if payload.trigger.type == "machine_downtime":
        affected_machine_ids.add(payload.trigger.machine_id)
    if len(affected_machine_ids) > payload.scope.max_affected_machines:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "replan_scope_exceeded",
                "message": "局部重排影响机台数超过请求上限",
                "affected_machine_count": len(affected_machine_ids),
            },
        )
    if len(affected_task_ids) > payload.scope.max_affected_tasks:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "replan_scope_exceeded",
                "message": "局部重排影响任务数超过请求上限",
                "affected_task_count": len(affected_task_ids),
            },
        )
    impact = _impact(
        before_tasks,
        after_tasks,
        considered=1,
        scheduled=len(affected_order_ids),
        manual_review=0,
        blocked=0,
        unscheduled=[],
    )
    return _finish_replan(
        db,
        source,
        target,
        trigger_type=payload.trigger.type,
        context_hash=context_hash,
        request_id=request_id,
        reason=payload.reason,
        affected_machine_ids=affected_machine_ids,
        affected_order_ids=affected_order_ids,
        affected_task_ids=affected_task_ids,
        impact=impact,
        actor=actor,
        ip_address=ip_address,
        dry_run=payload.dry_run,
    )


def create_shift_actual(
    db: Session,
    factory_id: str,
    payload: InjectionScheduleShiftActualCreateRequest,
    actor: AuthContext,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    payload_hash = sha256(
        canonical_json(payload.model_dump()).encode("utf-8")
    ).hexdigest()
    existing = _load_actual_request(db, factory_id, payload.request_id)
    if existing is not None:
        return _actual_create_replay_response(db, existing, payload_hash)

    source_version = load_version(
        db,
        factory_id,
        payload.version_id,
        for_update=True,
    )
    existing = _load_actual_request(db, factory_id, payload.request_id)
    if existing is not None:
        return _actual_create_replay_response(db, existing, payload_hash)
    if source_version.revision != payload.expected_version_revision:
        existing = _load_actual_request(db, factory_id, payload.request_id)
        if existing is not None:
            return _actual_create_replay_response(db, existing, payload_hash)
        raise revision_conflict(
            source_version.id,
            payload.expected_version_revision,
            source_version.revision,
        )
    source_task = load_task_for_version(
        db,
        source_version,
        payload.task_id,
    )
    existing = _load_actual_request(db, factory_id, payload.request_id)
    if existing is not None:
        return _actual_create_replay_response(db, existing, payload_hash)
    if (
        source_task.order_id != payload.order_id
        or source_task.machine_id != payload.machine_id
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actual_task_scope_mismatch",
                "message": "实绩的订单或机台与排程任务不一致",
            },
        )
    if source_task.execution_status in {"completed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "actual_task_closed",
                "message": "已完成或已取消任务不能新增实绩",
                "task_id": source_task.id,
            },
        )
    (
        canonical_source_version_id,
        canonical_source_task_id,
    ) = _canonical_actual_source(
        db,
        source_version,
        source_task,
    )
    duplicate_shift = db.scalar(
        select(InjectionScheduleShiftActual).where(
            InjectionScheduleShiftActual.factory_id == factory_id,
            InjectionScheduleShiftActual.source_task_id
            == canonical_source_task_id,
            InjectionScheduleShiftActual.shift_date == payload.shift_date,
            InjectionScheduleShiftActual.shift == payload.shift,
        )
    )
    if duplicate_shift is not None:
        existing = _load_actual_request(db, factory_id, payload.request_id)
        if existing is not None:
            return _actual_create_replay_response(db, existing, payload_hash)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "actual_shift_already_recorded",
                "message": "该任务在所选日期和班次已有实绩，请使用更正操作",
                "actual_id": duplicate_shift.id,
            },
        )
    lineage_sequence = int(
        db.scalar(
            select(func.coalesce(func.max(
                InjectionScheduleShiftActual.lineage_sequence
            ), 0)).where(
                InjectionScheduleShiftActual.factory_id == factory_id,
                InjectionScheduleShiftActual.source_task_id
                == canonical_source_task_id,
            )
        )
        or 0
    ) + 1
    order = load_order_for_version(
        db,
        source_version,
        payload.order_id,
    )
    existing = _load_actual_request(db, factory_id, payload.request_id)
    if existing is not None:
        return _actual_create_replay_response(db, existing, payload_hash)
    authoritative_outstanding = max(
        float(order.order_qty) - float(order.produced_qty),
        0,
    )
    if order.status in {"completed", "canceled"} or authoritative_outstanding <= 1e-6:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "actual_order_closed",
                "message": "已完成或已取消订单不能新增实绩",
                "order_id": order.id,
            },
        )
    if payload.actual_qty > float(source_task.planned_qty) + 1e-6:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actual_exceeds_task_plan",
                "message": "单笔实绩不能超过当前任务计划数；拆单溢出必须人工分配",
                "task_planned_qty": source_task.planned_qty,
            },
        )
    if payload.actual_qty > authoritative_outstanding + 1e-6:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actual_exceeds_outstanding",
                "message": "实绩数量不能超过当前欠数",
                "outstanding_qty": authoritative_outstanding,
            },
        )
    if source_version.status == "published":
        version = _clone_phase4_draft(
            db,
            source_version,
            actor,
            name=f"{source_version.name}（实绩滚动）",
            reason=payload.reason,
        )
        task = db.scalar(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.parent_task_id == source_task.id,
            )
        )
        if task is None:
            raise RuntimeError("published task was not cloned into rolling draft")
        version_expected_revision = version.revision
    else:
        _ensure_mutable_draft(source_version)
        version = source_version
        task = source_task
        version_expected_revision = payload.expected_version_revision
    timestamp = now_text()
    produced_qty = float(order.produced_qty) + payload.actual_qty
    try:
        _cas_version(
            db,
            version,
            version_expected_revision,
            actor,
            timestamp,
        )
        _cas_order(
            db,
            order,
            payload.expected_order_revision,
            produced_qty=produced_qty,
            outstanding_qty=max(float(order.order_qty) - produced_qty, 0),
            actor=actor,
            timestamp=timestamp,
        )
    except (HTTPException, OperationalError):
        db.rollback()
        existing = _load_actual_request(
            db,
            factory_id,
            payload.request_id,
        )
        if existing is not None:
            return _actual_create_replay_response(
                db,
                existing,
                payload_hash,
            )
        raise
    db.flush()
    db.expire(order)
    db.refresh(order)
    before_tasks = list_tasks(db, version)
    planned_before = float(task.planned_qty)
    shortage = max(planned_before - payload.actual_qty, 0)
    _apply_actual_to_task(
        task,
        order,
        shortage,
        actor,
        timestamp,
    )
    _sync_order_revision_snapshots(
        db,
        version,
        order,
        actor,
        timestamp,
        primary_task_id=task.id,
    )
    db.flush()
    _reflow_machines(
        db,
        version,
        {task.machine_id},
        actor,
        {task.id},
        preserve_before_task_ids={task.machine_id: task.id},
    )
    version.summary_json = canonical_json(version_summary(db, version))
    version.data_hash = build_version_data_hash(db, version)
    version.validation_hash = ""
    after_tasks = list_tasks(db, version)
    projections = build_projection_rows(before_tasks, after_tasks)
    actual = InjectionScheduleShiftActual(
        id=f"ISA-{uuid4().hex.upper()}",
        factory_id=factory_id,
        version_id=version.id,
        task_id=task.id,
        source_version_id=canonical_source_version_id,
        source_task_id=canonical_source_task_id,
        lineage_sequence=lineage_sequence,
        order_id=order.id,
        machine_id=task.machine_id,
        shift_date=payload.shift_date,
        shift=payload.shift,
        legacy_shift_code=payload.legacy_shift_code,
        source=payload.source,
        target_qty=payload.target_qty,
        actual_qty=payload.actual_qty,
        variance_qty=(
            payload.actual_qty - payload.target_qty
            if payload.target_qty is not None
            else None
        ),
        variance_reason=payload.variance_reason.strip(),
        produced_baseline_qty=max(order.produced_qty - payload.actual_qty, 0),
        outstanding_qty_before=order.outstanding_qty + payload.actual_qty,
        outstanding_qty_after=order.outstanding_qty,
        shortage_qty=shortage,
        task_planned_qty_before=planned_before,
        request_id=payload.request_id,
        payload_hash=payload_hash,
        projection_json=canonical_json(projections),
        revision=1,
        correction_count=0,
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
        corrected_by="",
        corrected_by_name="",
        corrected_at="",
        last_correction_request_id="",
        last_correction_payload_hash="",
    )
    db.add(actual)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="shift_actual",
        entity_id=actual.id,
        action="shift_actual_recorded",
        actor=actor,
        request_id=payload.request_id,
        ip_address=ip_address,
        reason=payload.reason,
        new_revision=1,
        after={
            "version_id": version.id,
            "task_id": task.id,
            "source_version_id": canonical_source_version_id,
            "source_task_id": canonical_source_task_id,
            "order_id": order.id,
            "machine_id": task.machine_id,
            "shift_date": payload.shift_date,
            "shift": payload.shift,
            "actual_qty": payload.actual_qty,
            "outstanding_qty_after": order.outstanding_qty,
            "version_revision": version.revision,
            "order_revision": order.revision,
            "projections": projections,
        },
    )
    try:
        db.commit()
    except (IntegrityError, OperationalError):
        db.rollback()
        existing = _load_actual_request(
            db,
            factory_id,
            payload.request_id,
        )
        if existing is not None:
            return _actual_create_replay_response(
                db,
                existing,
                payload_hash,
            )
        raise
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    actual = _load_actual(db, factory_id, actual.id)
    return _actual_response(db, actual, idempotent_replay=False)


def correct_shift_actual(
    db: Session,
    factory_id: str,
    actual_id: str,
    payload: InjectionScheduleShiftActualCorrectionRequest,
    actor: AuthContext,
    *,
    ip_address: str = "",
) -> dict[str, Any]:
    correction_payload_hash = sha256(
        canonical_json(payload.model_dump()).encode("utf-8")
    ).hexdigest()
    correction_replay = _load_correction_request(
        db,
        factory_id,
        payload.request_id,
    )
    if correction_replay is not None:
        return _correction_replay_response(
            correction_replay,
            actual_id,
            correction_payload_hash,
        )
    actual = _load_actual(db, factory_id, actual_id, for_update=True)
    # PostgreSQL may have waited on another correction of this same actual.
    # Re-read the immutable key after acquiring the row lock so the loser of
    # a same-request race replays the winner instead of reporting stale CAS.
    correction_replay = _load_correction_request(
        db,
        factory_id,
        payload.request_id,
    )
    if correction_replay is not None:
        return _correction_replay_response(
            correction_replay,
            actual_id,
            correction_payload_hash,
        )
    if actual.revision != payload.expected_revision:
        correction_replay = _load_correction_request(
            db,
            factory_id,
            payload.request_id,
        )
        if correction_replay is not None:
            return _correction_replay_response(
                correction_replay,
                actual_id,
                correction_payload_hash,
            )
        raise revision_conflict(
            actual.id,
            payload.expected_revision,
            actual.revision,
        )
    version = load_version(db, factory_id, actual.version_id)
    _ensure_mutable_draft(version)
    order = db.scalar(
        select(InjectionOrderMaster).where(
            InjectionOrderMaster.factory_id == factory_id,
            InjectionOrderMaster.id == actual.order_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的订单")
    latest = db.scalar(
        select(InjectionScheduleShiftActual)
        .where(
            InjectionScheduleShiftActual.factory_id == factory_id,
            InjectionScheduleShiftActual.source_task_id
            == actual.source_task_id,
        )
        .order_by(
            InjectionScheduleShiftActual.lineage_sequence.desc(),
            InjectionScheduleShiftActual.id.desc(),
        )
    )
    if latest is None or latest.id != actual.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "actual_correction_not_latest",
                "message": "只能更正该任务最新一笔实绩",
            },
        )
    if payload.actual_qty > actual.task_planned_qty_before + 1e-6:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actual_exceeds_task_plan",
                "message": "更正后的单笔实绩不能超过原任务计划数",
                "task_planned_qty": actual.task_planned_qty_before,
            },
        )
    restored_outstanding = max(
        float(order.order_qty)
        - (float(order.produced_qty) - float(actual.actual_qty)),
        0,
    )
    if payload.actual_qty > restored_outstanding + 1e-6:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "actual_exceeds_outstanding",
                "message": "更正后的实绩数量不能超过还原后的欠数",
                "outstanding_qty": restored_outstanding,
            },
        )
    timestamp = now_text()
    corrected_produced = max(
        order.produced_qty - actual.actual_qty + payload.actual_qty,
        0,
    )
    corrected_outstanding = max(
        float(order.order_qty) - corrected_produced,
        0,
    )
    try:
        _cas_version(
            db,
            version,
            payload.expected_version_revision,
            actor,
            timestamp,
        )
        _cas_order(
            db,
            order,
            payload.expected_order_revision,
            produced_qty=corrected_produced,
            outstanding_qty=corrected_outstanding,
            actor=actor,
            timestamp=timestamp,
        )
    except (HTTPException, OperationalError):
        db.rollback()
        correction_replay = _load_correction_request(
            db,
            factory_id,
            payload.request_id,
        )
        if correction_replay is not None:
            return _correction_replay_response(
                correction_replay,
                actual_id,
                correction_payload_hash,
            )
        raise
    db.flush()
    db.expire(order)
    db.refresh(order)
    task = load_task_for_version(db, version, actual.task_id)
    before_tasks = list_tasks(db, version)
    shortage = max(actual.task_planned_qty_before - payload.actual_qty, 0)
    _apply_actual_to_task(task, order, shortage, actor, timestamp)
    _sync_order_revision_snapshots(
        db,
        version,
        order,
        actor,
        timestamp,
        primary_task_id=task.id,
    )
    db.flush()
    _reflow_machines(
        db,
        version,
        {task.machine_id},
        actor,
        {task.id},
        preserve_before_task_ids={task.machine_id: task.id},
    )
    version.summary_json = canonical_json(version_summary(db, version))
    version.data_hash = build_version_data_hash(db, version)
    version.validation_hash = ""
    after_tasks = list_tasks(db, version)
    projections = build_projection_rows(before_tasks, after_tasks)
    before_actual = _serialize_actual(actual)
    previous_actual_qty = float(actual.actual_qty)
    previous_actual_revision = int(actual.revision)
    actual.actual_qty = payload.actual_qty
    actual.outstanding_qty_after = corrected_outstanding
    actual.shortage_qty = shortage
    actual.variance_qty = (
        payload.actual_qty - actual.target_qty
        if actual.target_qty is not None
        else None
    )
    actual.projection_json = canonical_json(projections)
    actual.revision += 1
    actual.correction_count += 1
    actual.corrected_by = actor.id
    actual.corrected_by_name = actor.display_name
    actual.corrected_at = timestamp
    actual.last_correction_request_id = payload.request_id
    actual.last_correction_payload_hash = correction_payload_hash
    correction = InjectionScheduleActualCorrection(
        id=f"IAC-{uuid4().hex.upper()}",
        factory_id=factory_id,
        actual_id=actual.id,
        request_id=payload.request_id,
        payload_hash=correction_payload_hash,
        previous_actual_qty=previous_actual_qty,
        corrected_actual_qty=payload.actual_qty,
        previous_actual_revision=previous_actual_revision,
        result_actual_revision=actual.revision,
        reason=payload.reason,
        response_json="{}",
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
    )
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="shift_actual",
        entity_id=actual.id,
        action="shift_actual_corrected",
        actor=actor,
        request_id=payload.request_id,
        ip_address=ip_address,
        reason=payload.reason,
        old_revision=payload.expected_revision,
        new_revision=payload.expected_revision + 1,
        before=before_actual,
        after={
            **_serialize_actual(actual),
            "version_revision": version.revision,
            "order_revision": payload.expected_order_revision + 1,
            "projections": projections,
        },
    )
    try:
        db.flush()
        response = _actual_response(
            db,
            actual,
            idempotent_replay=False,
        )
        correction.response_json = canonical_json(response)
        db.add(correction)
        db.flush()
        db.commit()
    except (IntegrityError, OperationalError):
        db.rollback()
        concurrent_replay = _load_correction_request(
            db,
            factory_id,
            payload.request_id,
        )
        if concurrent_replay is None:
            raise
        return _correction_replay_response(
            concurrent_replay,
            actual_id,
            correction_payload_hash,
        )
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return response


def list_shift_actuals(
    db: Session,
    factory_id: str,
    *,
    version_id: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, Any]]:
    statement = select(InjectionScheduleShiftActual).where(
        InjectionScheduleShiftActual.factory_id == factory_id
    )
    if version_id:
        statement = statement.where(
            or_(
                InjectionScheduleShiftActual.version_id == version_id,
                InjectionScheduleShiftActual.source_version_id
                == version_id,
            )
        )
    if date_from:
        statement = statement.where(
            InjectionScheduleShiftActual.shift_date >= date_from
        )
    if date_to:
        statement = statement.where(
            InjectionScheduleShiftActual.shift_date <= date_to
        )
    rows = db.scalars(
        statement.order_by(
            InjectionScheduleShiftActual.shift_date.desc(),
            InjectionScheduleShiftActual.created_at.desc(),
            InjectionScheduleShiftActual.id.desc(),
        )
    ).all()
    return [_serialize_actual(item) for item in rows]


def _canonical_actual_source(
    db: Session,
    version: InjectionScheduleVersion,
    task: InjectionScheduleTask,
) -> tuple[str, str]:
    """Return the immutable root schedule lineage for an execution actual.

    The first actual against a published version creates a rolling draft.  All
    later day/night writes against that draft (or a clone of it) must remain
    discoverable from the published schedule, so their source ids point to the
    same root instead of drifting to each rolling task id.
    """

    prior = db.scalar(
        select(InjectionScheduleShiftActual)
        .where(
            InjectionScheduleShiftActual.factory_id == version.factory_id,
            or_(
                InjectionScheduleShiftActual.task_id == task.id,
                InjectionScheduleShiftActual.source_task_id == task.id,
            ),
        )
        .order_by(
            InjectionScheduleShiftActual.created_at.desc(),
            InjectionScheduleShiftActual.id.desc(),
        )
    )
    if prior is not None:
        return prior.source_version_id, prior.source_task_id

    current_version = version
    current_task = task
    visited: set[tuple[str, str]] = set()
    while (
        current_version.base_version_id
        and current_task.parent_task_id
        and (current_version.id, current_task.id) not in visited
    ):
        visited.add((current_version.id, current_task.id))
        parent_version = db.scalar(
            select(InjectionScheduleVersion).where(
                InjectionScheduleVersion.factory_id == version.factory_id,
                InjectionScheduleVersion.id
                == current_version.base_version_id,
            )
        )
        if parent_version is None:
            break
        parent_task = db.scalar(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == parent_version.id,
                InjectionScheduleTask.id == current_task.parent_task_id,
            )
        )
        if parent_task is None:
            break
        current_version = parent_version
        current_task = parent_task
        if current_version.status == "published":
            break
    return current_version.id, current_task.id


def _load_source_with_cas(
    db: Session,
    factory_id: str,
    version_id: str,
    expected_revision: int,
) -> InjectionScheduleVersion:
    source = load_version(db, factory_id, version_id, for_update=True)
    if source.revision != expected_revision:
        raise revision_conflict(
            source.id,
            expected_revision,
            source.revision,
        )
    return source


def _clone_phase4_draft(
    db: Session,
    source: InjectionScheduleVersion,
    actor: AuthContext,
    *,
    name: str,
    reason: str,
) -> InjectionScheduleVersion:
    created = create_version(
        db,
        source.factory_id,
        InjectionScheduleVersionCreateRequest(
            name=name,
            business_date=source.business_date,
            plan_base_at=source.plan_base_at,
            base_version_id=source.id,
        ),
        actor,
        clone_reason=reason,
        commit=False,
        exact_clone=True,
    )
    return load_version(db, source.factory_id, created["id"])


def _auto_assign_order(
    db: Session,
    version: InjectionScheduleVersion,
    order: InjectionOrderMaster,
    planned_qty: float,
    actor: AuthContext,
    recommendation_batch: AutoRecommendationBatch,
    affected_machine_ids: set[str],
    touched_task_ids: set[str],
    *,
    horizon: datetime | None,
) -> str:
    recommendations = recommendation_batch.select_append_candidate(
        order,
        planned_qty,
    )
    candidate = recommendations["candidate"]
    if candidate is None:
        return (
            "manual_review"
            if recommendations["manual_review_count"] > 0
            else "blocked"
        )
    estimated, _ = _validated_candidate_timing(candidate)
    finish = parse_business_timestamp(str(estimated.get("finish_at") or ""))
    if horizon is not None and finish is not None and finish > horizon:
        return "blocked"
    target_index = int(candidate["target_index"])
    machine = next(
        item
        for item in recommendation_batch.machines
        if item.id == candidate["machine_id"]
    )
    mold = recommendation_batch.mold_by_code.get(
        normalize_key(order.mold_code)
    )
    timestamp = now_text()
    task = _candidate_task(
        version,
        order,
        machine,
        mold,
        candidate,
        planned_qty=planned_qty,
        sequence_no=target_index,
        actor=actor,
        timestamp=timestamp,
    )
    db.add(task)
    recommendation_batch.register_task(task)
    affected_machine_ids.add(machine.id)
    touched_task_ids.add(task.id)
    return "scheduled"


def _candidate_task(
    version: InjectionScheduleVersion,
    order: InjectionOrderMaster,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster | None,
    candidate: dict[str, Any],
    *,
    planned_qty: float,
    sequence_no: int,
    actor: AuthContext,
    timestamp: str,
) -> InjectionScheduleTask:
    score = candidate.get("score") or {}
    estimated, transition = _validated_candidate_timing(candidate)
    return InjectionScheduleTask(
        id=f"IST-{uuid4().hex.upper()}",
        factory_id=version.factory_id,
        version_id=version.id,
        order_id=order.id,
        machine_id=machine.id,
        mold_id=mold.id if mold is not None else None,
        sequence_no=sequence_no,
        planned_qty=planned_qty,
        planned_start_at=str(estimated["production_start_at"]),
        planned_finish_at=str(estimated["finish_at"]),
        setup_hours=float(transition["setup_minutes_before"]) / 60,
        duration_hours=float(estimated["duration_hours"]),
        locked=False,
        split_group_id="",
        parent_task_id="",
        order_no_snapshot=order.order_no,
        product_code_snapshot=order.product_code,
        product_name_snapshot=order.product_name,
        delivery_due_date_snapshot=order.delivery_due_date,
        mold_code_snapshot=(
            mold.mold_code if mold is not None else order.mold_code
        ),
        color_snapshot=canonical_color_key(order.pigment, order.color),
        color_rank_snapshot=order.color_rank,
        material_snapshot=order.material,
        machine_code_snapshot=machine.machine_code,
        source="auto",
        execution_status="planned",
        protected=False,
        recommendation_score=float(score["total"]),
        score_breakdown_json=canonical_json(score.get("breakdown") or []),
        constraint_snapshot_json=canonical_json(
            candidate.get("hard_constraints") or []
        ),
        recommendation_context_hash=str(
            candidate.get("recommendation_context_hash") or ""
        ),
        risk_level="normal",
        risk_reasons_json="[]",
        order_revision_snapshot=order.revision,
        machine_revision_snapshot=machine.revision,
        mold_revision_snapshot=mold.revision if mold is not None else 0,
        revision=1,
        created_by=actor.id,
        created_at=timestamp,
        updated_by=actor.id,
        updated_at=timestamp,
    )


def _validated_candidate_timing(
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    score = candidate.get("score") or {}
    estimated = score.get("estimated") or {}
    transition = score.get("transition") or {}
    production_start = parse_business_timestamp(
        str(estimated.get("production_start_at") or "")
    )
    finish = parse_business_timestamp(
        str(estimated.get("finish_at") or "")
    )
    duration_hours = float(estimated.get("duration_hours") or 0)
    setup_minutes = float(transition.get("setup_minutes_before") or 0)
    if (
        production_start is None
        or finish is None
        or finish <= production_start
        or duration_hours <= 0
        or setup_minutes < 0
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "auto_planned_time_invalid",
                "message": "候选机台的自动计划时间无效，已阻止写入草稿",
                "machine_id": str(candidate.get("machine_id") or ""),
                "production_start_at": str(
                    estimated.get("production_start_at") or ""
                ),
                "finish_at": str(estimated.get("finish_at") or ""),
                "duration_hours": duration_hours,
                "setup_minutes_before": setup_minutes,
            },
        )
    return estimated, transition


def _replan_urgent_order(
    db: Session,
    version: InjectionScheduleVersion,
    payload: InjectionScheduleReplanRequest,
    actor: AuthContext,
    affected_machine_ids: set[str],
    affected_order_ids: set[str],
    touched_task_ids: set[str],
) -> None:
    order = load_order_for_version(db, version, payload.trigger.order_id)
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.order_id == order.id,
            )
            .order_by(
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    if not tasks:
        recommendation_batch = AutoRecommendationBatch.load(db, version)
        recommendations = recommendation_batch.recommend_movable_suffix(
            order,
            order.outstanding_qty,
        )
        candidate = choose_earliest_eligible_machine(
            recommendations["candidates"]
        )
        if candidate is None:
            status = (
                "manual_review"
                if recommendations["manual_review_count"] > 0
                else "blocked"
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "urgent_order_not_auto_eligible",
                    "message": "急单没有全部硬约束通过的自动排程机台",
                    "status": status,
                },
            )
        _validated_candidate_timing(candidate)
        machine = next(
            item
            for item in recommendation_batch.machines
            if item.id == candidate["machine_id"]
        )
        mold = recommendation_batch.mold_by_code.get(
            normalize_key(order.mold_code)
        )
        target_index = int(candidate["target_index"])
        target_sequence = prepare_lane_insert(
            db,
            version,
            machine.id,
            target_index,
        )
        timestamp = now_text()
        task = _candidate_task(
            version,
            order,
            machine,
            mold,
            candidate,
            planned_qty=order.outstanding_qty,
            sequence_no=target_sequence,
            actor=actor,
            timestamp=timestamp,
        )
        db.add(task)
        affected_machine_ids.add(machine.id)
        touched_task_ids.add(task.id)
        db.flush()
    else:
        task = tasks[0]
        _ensure_task_movable(task)
        target_index = _last_barrier_index(db, version, task.machine_id) + 1
        apply_one_command(
            db,
            version,
            InjectionScheduleCommand(
                type="reorder",
                task_id=task.id,
                target_index=target_index,
            ),
            actor,
            now_text(),
            affected_machine_ids,
            touched_task_ids,
        )
    affected_order_ids.add(order.id)


def _replan_downtime(
    db: Session,
    version: InjectionScheduleVersion,
    payload: InjectionScheduleReplanRequest,
    affected_machine_ids: set[str],
    affected_order_ids: set[str],
) -> None:
    machine = db.scalar(
        select(InjectionMachineMaster).where(
            InjectionMachineMaster.factory_id == version.factory_id,
            InjectionMachineMaster.id == payload.trigger.machine_id,
        )
    )
    if machine is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的机台")
    start = parse_business_timestamp(payload.trigger.start_at)
    end = parse_business_timestamp(payload.trigger.end_at)
    assert start is not None and end is not None
    rules = json_object(version.rules_snapshot_json)
    windows = list(rules.get("unavailable_windows") or [])
    windows.append(
        {
            "scope": "machine",
            "machine_id": machine.id,
            "start_at": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_at": end.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": payload.trigger.reason
            or payload.reason,
        }
    )
    rules["unavailable_windows"] = windows
    version.rules_snapshot_json = canonical_json(rules)
    lane = db.scalars(
        select(InjectionScheduleTask)
        .where(
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
            InjectionScheduleTask.machine_id == machine.id,
        )
        .order_by(InjectionScheduleTask.sequence_no, InjectionScheduleTask.id)
    ).all()
    barriers: list[str] = []
    for task in lane:
        occupied_start = parse_business_timestamp(task.planned_start_at)
        finish = parse_business_timestamp(task.planned_finish_at)
        if occupied_start is not None:
            occupied_start -= timedelta(hours=float(task.setup_hours or 0))
        if (
            occupied_start is not None
            and finish is not None
            and occupied_start < end
            and finish > start
        ):
            affected_order_ids.add(task.order_id)
            if _is_task_barrier(task):
                barriers.append(task.id)
    if barriers:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "downtime_hits_protected_tasks",
                "message": "停机窗口占用已锁定、已开机、已完成或受保护任务",
                "task_ids": barriers,
            },
        )
    affected_machine_ids.add(machine.id)


def _refresh_lane_transitions(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
    actor: AuthContext,
    touched_task_ids: set[str],
) -> None:
    """Recompute setup at the final sequence after an urgent insertion.

    Only the movable suffix after the last execution barrier is eligible for
    changes. The calculation uses the same directed mold/color/material rule
    engine as Phase 3 recommendations.
    """

    if not machine_ids:
        return
    rules = json_object(version.rules_snapshot_json)
    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(sorted(machine_ids)),
            )
        ).all()
    }
    timestamp = now_text()
    for machine_id in sorted(machine_ids):
        machine = machines.get(machine_id)
        if machine is None:
            raise HTTPException(status_code=404, detail="未找到该厂区的机台")
        lane = list(
            db.scalars(
                select(InjectionScheduleTask)
                .where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                    InjectionScheduleTask.machine_id == machine_id,
                )
                .order_by(
                    InjectionScheduleTask.sequence_no,
                    InjectionScheduleTask.id,
                )
            ).all()
        )
        last_barrier = max(
            (
                index
                for index, task in enumerate(lane)
                if _is_task_barrier(task)
            ),
            default=-1,
        )
        previous: InjectionScheduleTask | None = None
        for index, task in enumerate(lane):
            if index <= last_barrier:
                previous = task
                continue
            transition = calculate_transition_setup(
                from_mold_code=(
                    previous.mold_code_snapshot
                    if previous is not None
                    else ""
                ),
                from_color=(
                    previous.color_snapshot
                    if previous is not None
                    else ""
                ),
                from_color_rank=(
                    previous.color_rank_snapshot
                    if previous is not None
                    else None
                ),
                from_material=(
                    previous.material_snapshot
                    if previous is not None
                    else ""
                ),
                to_mold_code=task.mold_code_snapshot,
                to_color=task.color_snapshot,
                to_color_rank=task.color_rank_snapshot,
                to_material=task.material_snapshot,
                machine_class=machine.machine_class,
                rules=rules,
            )
            setup_hours = float(transition["setup_minutes"]) / 60
            if abs(float(task.setup_hours) - setup_hours) > 1e-9:
                task.setup_hours = setup_hours
                if task.id not in touched_task_ids:
                    task.revision += 1
                    touched_task_ids.add(task.id)
                task.updated_by = actor.id
                task.updated_at = timestamp
            previous = task
    db.flush()


def _reflow_machines(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
    actor: AuthContext,
    touched_task_ids: set[str],
    *,
    freeze_before_at: datetime | None = None,
    preserve_finished_before_at: datetime | None = None,
    preserve_before_task_ids: dict[str, str] | None = None,
    planning_horizon_end_at: datetime | None = None,
) -> None:
    if not machine_ids:
        return
    rules = json_object(version.rules_snapshot_json)
    all_windows = list(rules.get("unavailable_windows") or [])
    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(sorted(machine_ids)),
            )
        ).all()
    }
    timestamp = now_text()
    for machine_id in sorted(machine_ids):
        machine = machines.get(machine_id)
        if machine is None:
            raise HTTPException(status_code=404, detail="未找到该厂区的机台")
        lane = list(
            db.scalars(
                select(InjectionScheduleTask)
                .where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                    InjectionScheduleTask.machine_id == machine_id,
                )
                .order_by(
                    InjectionScheduleTask.sequence_no,
                    InjectionScheduleTask.created_at,
                    InjectionScheduleTask.id,
                )
            ).all()
        )
        plan_base = parse_business_timestamp(version.plan_base_at) or business_now()
        available_at = parse_business_timestamp(machine.available_at)
        if available_at is not None:
            plan_base = max(plan_base, available_at)
        inputs: list[dict[str, Any]] = []
        suffix_task_id = (preserve_before_task_ids or {}).get(machine_id, "")
        reached_suffix = not bool(suffix_task_id)
        for task in lane:
            if task.id == suffix_task_id:
                reached_suffix = True
            preserve = False
            finish = parse_business_timestamp(task.planned_finish_at)
            if (
                preserve_finished_before_at is not None
                and finish is not None
                and finish <= preserve_finished_before_at
            ):
                preserve = True
            if not reached_suffix:
                preserve = True
            inputs.append(
                {
                    "id": task.id,
                    "order_id": task.order_id,
                    "machine_id": task.machine_id,
                    "machine_code": task.machine_code_snapshot,
                    "planned_qty": task.planned_qty,
                    "planned_start_at": task.planned_start_at,
                    "planned_finish_at": task.planned_finish_at,
                    "setup_hours": task.setup_hours,
                    "duration_hours": task.duration_hours,
                    "locked": bool(task.locked or preserve),
                    "protected": bool(task.protected),
                    "execution_status": task.execution_status,
                }
            )
        windows = [
            item
            for item in all_windows
            if item.get("scope") == "factory"
            or (
                item.get("scope") == "machine"
                and item.get("machine_id") == machine_id
            )
        ]
        try:
            planned = plan_lane_locally(
                inputs,
                plan_base_at=plan_base,
                unavailable_windows=windows,
                freeze_before_at=freeze_before_at,
                planning_horizon_end_at=planning_horizon_end_at,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "protected_task_barrier",
                    "message": "局部重排被已锁定、已开机、已完成或受保护任务阻挡",
                    "reason": str(exc),
                },
            ) from exc
        planned_by_id = {str(item["id"]): item for item in planned}
        for task in lane:
            item = planned_by_id[task.id]
            before = (task.planned_start_at, task.planned_finish_at)
            after = (
                str(item["planned_start_at"]),
                str(item["planned_finish_at"]),
            )
            if before == after:
                continue
            task.planned_start_at, task.planned_finish_at = after
            if task.id not in touched_task_ids:
                task.revision += 1
                touched_task_ids.add(task.id)
            task.updated_by = actor.id
            task.updated_at = timestamp
    db.flush()


def _finish_replan(
    db: Session,
    source: InjectionScheduleVersion,
    target: InjectionScheduleVersion,
    *,
    trigger_type: str,
    context_hash: str,
    request_id: str,
    reason: str,
    affected_machine_ids: set[str],
    affected_order_ids: set[str],
    affected_task_ids: set[str],
    impact: dict[str, Any],
    actor: AuthContext,
    ip_address: str,
    dry_run: bool,
) -> dict[str, Any]:
    target.summary_json = canonical_json(version_summary(db, target))
    target.data_hash = build_version_data_hash(db, target)
    target.validation_hash = ""
    timestamp = now_text()
    run = InjectionScheduleReplanRun(
        id=f"ISR-{uuid4().hex.upper()}",
        factory_id=source.factory_id,
        source_version_id=source.id,
        result_version_id=target.id,
        trigger_type=trigger_type,
        status="previewed" if dry_run else "applied",
        source_revision=source.revision,
        result_revision=target.revision,
        context_hash=context_hash,
        reason=reason,
        request_id=request_id,
        affected_machine_ids_json=canonical_json(sorted(affected_machine_ids)),
        affected_order_ids_json=canonical_json(sorted(affected_order_ids)),
        affected_task_ids_json=canonical_json(sorted(affected_task_ids)),
        impact_json=canonical_json(impact),
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
    )
    db.add(run)
    add_audit_event(
        db,
        factory_id=source.factory_id,
        entity_type="schedule_version",
        entity_id=target.id,
        action=(
            "auto_draft_previewed"
            if dry_run and trigger_type == "auto_draft"
            else "local_replan_previewed"
            if dry_run
            else "auto_draft_generated"
            if trigger_type == "auto_draft"
            else "local_replan_applied"
        ),
        actor=actor,
        request_id=request_id,
        ip_address=ip_address,
        reason=reason,
        old_revision=source.revision,
        new_revision=target.revision,
        before={"source_version_id": source.id},
        after={
            "result_version_id": target.id,
            "trigger_type": trigger_type,
            "context_hash": context_hash,
            "affected_machine_ids": sorted(affected_machine_ids),
            "affected_order_ids": sorted(affected_order_ids),
            "affected_task_ids": sorted(affected_task_ids),
            "impact": impact,
        },
    )
    try:
        db.flush()
        response = _replan_response(db, run)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    except (IntegrityError, OperationalError):
        db.rollback()
        replay = _load_replan_replay(
            db,
            source.factory_id,
            request_id,
            context_hash,
        )
        if replay is not None:
            return replay
        raise
    except Exception:
        db.rollback()
        raise
    return response


def _replan_response(
    db: Session,
    run: InjectionScheduleReplanRun,
) -> dict[str, Any]:
    version = load_version(db, run.factory_id, run.result_version_id)
    return {
        "version": serialize_version(version),
        "tasks": list_tasks(db, version),
        "conflicts": [],
        "affected_machine_ids": json_list(run.affected_machine_ids_json),
        "affected_order_ids": json_list(run.affected_order_ids_json),
        "affected_task_ids": json_list(run.affected_task_ids_json),
        "run": _serialize_run(run),
    }


def _load_replan_replay(
    db: Session,
    factory_id: str,
    request_id: str,
    context_hash: str,
) -> dict[str, Any] | None:
    existing = db.scalar(
        select(InjectionScheduleReplanRun).where(
            InjectionScheduleReplanRun.factory_id == factory_id,
            InjectionScheduleReplanRun.request_id == request_id,
        )
    )
    if existing is None:
        return None
    if existing.context_hash != context_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_key_conflict",
                "message": "request_id 已用于另一笔自动/局部重排",
            },
        )
    return _replan_response(db, existing)


def _impact(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    considered: int,
    scheduled: int,
    manual_review: int,
    blocked: int,
    unscheduled: list[str],
) -> dict[str, Any]:
    rows = _task_impact_rows(before, after)
    moved = 0
    eta_delayed = 0
    total_eta_shift_minutes = 0.0
    for row in rows:
        if (
            row["machine_id_before"] != row["machine_id_after"]
            or row["sequence_no_before"] != row["sequence_no_after"]
        ):
            moved += 1
        shift = float(row["eta_shift_minutes"])
        total_eta_shift_minutes += shift
        if shift > 1e-6:
            eta_delayed += 1
    return {
        "considered_order_count": considered,
        "scheduled_order_count": scheduled,
        "manual_review_order_count": manual_review,
        "blocked_order_count": blocked,
        "unscheduled_order_ids": sorted(unscheduled),
        "moved_task_count": moved,
        "eta_delayed_task_count": eta_delayed,
        "total_eta_shift_minutes": round(total_eta_shift_minutes, 3),
        "before_task_count": len(before),
        "after_task_count": len(after),
        "rows": rows,
    }


def _task_impact_rows(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_by_id = {str(item["id"]): item for item in before}
    rows: list[dict[str, Any]] = []
    for item in after:
        previous = before_by_id.get(str(item["id"]))
        if previous is not None and not _task_changed(previous, item):
            continue
        old_finish = parse_business_timestamp(
            str((previous or {}).get("planned_finish_at") or "")
        )
        new_finish = parse_business_timestamp(
            str(item.get("planned_finish_at") or "")
        )
        eta_shift_minutes = (
            round((new_finish - old_finish).total_seconds() / 60, 3)
            if old_finish is not None and new_finish is not None
            else 0.0
        )
        rows.append(
            {
                "task_id": str(item["id"]),
                "source_task_id": str(
                    item.get("parent_task_id")
                    or (previous or {}).get("parent_task_id")
                    or item["id"]
                ),
                "order_id": str(item["order_id"]),
                "machine_id_before": str(
                    (previous or {}).get("machine_id") or ""
                ),
                "machine_id_after": str(item["machine_id"]),
                "sequence_no_before": (
                    (previous or {}).get("sequence_no")
                ),
                "sequence_no_after": item.get("sequence_no"),
                "planned_qty_before": (
                    float(previous["planned_qty"])
                    if previous is not None
                    else 0.0
                ),
                "planned_qty_after": float(item["planned_qty"]),
                "planned_start_at_before": str(
                    (previous or {}).get("planned_start_at") or ""
                ),
                "planned_start_at_after": str(
                    item.get("planned_start_at") or ""
                ),
                "planned_finish_at_before": str(
                    (previous or {}).get("planned_finish_at") or ""
                ),
                "planned_finish_at_after": str(
                    item.get("planned_finish_at") or ""
                ),
                "setup_hours_before": (
                    float(previous["setup_hours"])
                    if previous is not None
                    else 0.0
                ),
                "setup_hours_after": float(item.get("setup_hours") or 0),
                "eta_shift_minutes": eta_shift_minutes,
                "execution_status_before": str(
                    (previous or {}).get("execution_status") or ""
                ),
                "execution_status_after": str(
                    item.get("execution_status") or ""
                ),
            }
        )
    return rows


def _task_changed(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    return any(
        previous.get(field_name) != current.get(field_name)
        for field_name in (
            "machine_id",
            "sequence_no",
            "planned_qty",
            "planned_start_at",
            "planned_finish_at",
            "setup_hours",
            "duration_hours",
            "locked",
            "execution_status",
            "protected",
        )
    )


def _changed_scope(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> tuple[set[str], set[str], set[str]]:
    before_by_id = {str(item["id"]): item for item in before}
    affected_machine_ids: set[str] = set()
    affected_order_ids: set[str] = set()
    affected_task_ids: set[str] = set()
    for item in after:
        previous = before_by_id.get(str(item["id"]))
        changed = previous is None or _task_changed(
            previous,
            item,
        )
        if not changed:
            continue
        affected_task_ids.add(str(item["id"]))
        affected_machine_ids.add(str(item["machine_id"]))
        affected_order_ids.add(str(item["order_id"]))
        if previous is not None:
            affected_machine_ids.add(str(previous["machine_id"]))
    return affected_machine_ids, affected_order_ids, affected_task_ids


def _context_hash(
    db: Session,
    source: InjectionScheduleVersion,
    trigger_type: str,
    payload: dict[str, Any],
) -> str:
    current_rules = db.get(InjectionScheduleRuleConfig, source.factory_id)
    source_rules = json_object(source.rules_snapshot_json)
    master_revisions = {
        "orders": [
            [item_id, revision]
            for item_id, revision in db.execute(
                select(
                    InjectionOrderMaster.id,
                    InjectionOrderMaster.revision,
                )
                .where(
                    InjectionOrderMaster.factory_id == source.factory_id
                )
                .order_by(InjectionOrderMaster.id)
            ).all()
        ],
        "machines": [
            [item_id, revision]
            for item_id, revision in db.execute(
                select(
                    InjectionMachineMaster.id,
                    InjectionMachineMaster.revision,
                )
                .where(
                    InjectionMachineMaster.factory_id == source.factory_id
                )
                .order_by(InjectionMachineMaster.id)
            ).all()
        ],
        "molds": [
            [item_id, revision]
            for item_id, revision in db.execute(
                select(
                    InjectionMoldMaster.id,
                    InjectionMoldMaster.revision,
                )
                .where(
                    InjectionMoldMaster.factory_id == source.factory_id
                )
                .order_by(InjectionMoldMaster.id)
            ).all()
        ],
    }
    return sha256(
        canonical_json(
            {
                "factory_id": source.factory_id,
                "source_version_id": source.id,
                "source_revision": source.revision,
                "source_data_hash": source.data_hash,
                "source_rule_config_revision": (
                    source.rule_config_revision
                ),
                "source_rule_snapshot_hash": sha256(
                    canonical_json(source_rules).encode("utf-8")
                ).hexdigest(),
                "calendar": {
                    "availability_calendar_verified_through": (
                        source_rules.get(
                            "availability_calendar_verified_through",
                            "",
                        )
                    ),
                    "unavailable_windows": source_rules.get(
                        "unavailable_windows",
                        [],
                    ),
                },
                "current_rule_config": {
                    "revision": (
                        current_rules.revision
                        if current_rules is not None
                        else 0
                    ),
                    "hash": sha256(
                        (
                            current_rules.config_json
                            if current_rules is not None
                            else "{}"
                        ).encode("utf-8")
                    ).hexdigest(),
                },
                "master_revisions": master_revisions,
                "trigger_type": trigger_type,
                "payload": payload,
            }
        ).encode("utf-8")
    ).hexdigest()


def _verify_expected_context(
    expected: str,
    actual: str,
    *,
    required: bool,
) -> None:
    if required and not expected:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "expected_context_hash_required",
                "message": "正式执行前必须先预览并提交 expected_context_hash",
            },
        )
    if expected and expected != actual:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "replan_context_changed",
                "message": "重排预览上下文已变化，请重新预览",
                "expected_context_hash": expected,
                "current_context_hash": actual,
            },
        )


def _allocated_qty_by_order(
    db: Session,
    version: InjectionScheduleVersion,
) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    tasks = db.scalars(
        select(InjectionScheduleTask).where(
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
            InjectionScheduleTask.execution_status.not_in(
                ("completed", "cancelled")
            ),
        )
    ).all()
    for task in tasks:
        totals[task.order_id] += float(task.planned_qty)
    return totals


def _last_barrier_index(
    db: Session,
    version: InjectionScheduleVersion,
    machine_id: str,
) -> int:
    lane = db.scalars(
        select(InjectionScheduleTask)
        .where(
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
            InjectionScheduleTask.machine_id == machine_id,
        )
        .order_by(InjectionScheduleTask.sequence_no, InjectionScheduleTask.id)
    ).all()
    return max(
        (
            index
            for index, task in enumerate(lane)
            if _is_task_barrier(task)
        ),
        default=-1,
    )


def _is_task_barrier(task: InjectionScheduleTask) -> bool:
    return bool(
        task.locked
        or task.protected
        or task.execution_status in {"running", "completed", "cancelled"}
    )


def _ensure_task_movable(task: InjectionScheduleTask) -> None:
    if _is_task_barrier(task):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_protected",
                "message": "已锁定、已开机、已完成或受保护任务不能重排",
                "task_id": task.id,
            },
        )


def _ensure_mutable_draft(version: InjectionScheduleVersion) -> None:
    if version.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="已发布版本不可修改，请复制为新草稿",
        )


def _cas_version(
    db: Session,
    version: InjectionScheduleVersion,
    expected_revision: int,
    actor: AuthContext,
    timestamp: str,
) -> None:
    result = db.execute(
        update(InjectionScheduleVersion)
        .where(
            InjectionScheduleVersion.id == version.id,
            InjectionScheduleVersion.factory_id == version.factory_id,
            InjectionScheduleVersion.status == "draft",
            InjectionScheduleVersion.revision == expected_revision,
        )
        .values(
            revision=InjectionScheduleVersion.revision + 1,
            validation_hash="",
            data_hash="",
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = load_version(db, version.factory_id, version.id)
        raise revision_conflict(
            version.id,
            expected_revision,
            current.revision,
        )
    db.flush()
    db.expire(version)
    db.refresh(version)


def _cas_order(
    db: Session,
    order: InjectionOrderMaster,
    expected_revision: int,
    *,
    produced_qty: float,
    outstanding_qty: float,
    actor: AuthContext,
    timestamp: str,
) -> None:
    result = db.execute(
        update(InjectionOrderMaster)
        .where(
            InjectionOrderMaster.id == order.id,
            InjectionOrderMaster.factory_id == order.factory_id,
            InjectionOrderMaster.revision == expected_revision,
        )
        .values(
            produced_qty=max(produced_qty, 0),
            outstanding_qty=max(outstanding_qty, 0),
            status="completed" if outstanding_qty <= 1e-6 else "open",
            revision=InjectionOrderMaster.revision + 1,
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.scalar(
            select(InjectionOrderMaster).where(
                InjectionOrderMaster.id == order.id,
                InjectionOrderMaster.factory_id == order.factory_id,
            )
        )
        raise revision_conflict(
            order.id,
            expected_revision,
            current.revision if current is not None else None,
        )


def _apply_actual_to_task(
    task: InjectionScheduleTask,
    order: InjectionOrderMaster,
    shortage: float,
    actor: AuthContext,
    timestamp: str,
) -> None:
    task.locked = True
    task.protected = True
    task.order_revision_snapshot = order.revision
    task.revision += 1
    task.updated_by = actor.id
    task.updated_at = timestamp
    now = business_now().replace(second=0, microsecond=0)
    existing_start = parse_business_timestamp(task.planned_start_at)
    if shortage <= 1e-6:
        task.execution_status = "completed"
        if existing_start is None or existing_start >= now:
            existing_start = now - timedelta(minutes=1)
            task.planned_start_at = existing_start.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        task.planned_finish_at = now.strftime("%Y-%m-%d %H:%M:%S")
        task.duration_hours = max(
            (now - existing_start).total_seconds() / 3600,
            1 / 60,
        )
        return
    task.execution_status = "running"
    task.planned_qty = shortage
    task.duration_hours = max(
        shortage / order.daily_target_qty * 24
        if order.daily_target_qty
        else 24.0,
        0.25,
    )
    task.planned_finish_at = (
        now + timedelta(hours=task.duration_hours)
    ).strftime("%Y-%m-%d %H:%M:%S")
    if existing_start is None or existing_start > now:
        task.planned_start_at = now.strftime("%Y-%m-%d %H:%M:%S")


def _sync_order_revision_snapshots(
    db: Session,
    version: InjectionScheduleVersion,
    order: InjectionOrderMaster,
    actor: AuthContext,
    timestamp: str,
    *,
    primary_task_id: str,
) -> None:
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.order_id == order.id,
            )
        ).all()
    )
    for sibling in tasks:
        if sibling.order_revision_snapshot == order.revision:
            continue
        sibling.order_revision_snapshot = order.revision
        if sibling.id != primary_task_id:
            sibling.revision += 1
            sibling.updated_by = actor.id
            sibling.updated_at = timestamp


def _load_actual(
    db: Session,
    factory_id: str,
    actual_id: str,
    *,
    for_update: bool = False,
) -> InjectionScheduleShiftActual:
    statement = select(InjectionScheduleShiftActual).where(
        InjectionScheduleShiftActual.factory_id == factory_id,
        InjectionScheduleShiftActual.id == actual_id,
    )
    if for_update:
        statement = statement.with_for_update()
    actual = db.scalar(statement)
    if actual is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的班次实绩")
    return actual


def _load_actual_request(
    db: Session,
    factory_id: str,
    request_id: str,
) -> InjectionScheduleShiftActual | None:
    return db.scalar(
        select(InjectionScheduleShiftActual).where(
            InjectionScheduleShiftActual.factory_id == factory_id,
            InjectionScheduleShiftActual.request_id == request_id,
        )
    )


def _actual_create_replay_response(
    db: Session,
    actual: InjectionScheduleShiftActual,
    payload_hash: str,
) -> dict[str, Any]:
    if actual.payload_hash != payload_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_key_conflict",
                "message": "request_id 已用于另一笔实绩回写",
            },
        )
    return _actual_response(db, actual, idempotent_replay=True)


def _load_correction_request(
    db: Session,
    factory_id: str,
    request_id: str,
) -> InjectionScheduleActualCorrection | None:
    return db.scalar(
        select(InjectionScheduleActualCorrection).where(
            InjectionScheduleActualCorrection.factory_id == factory_id,
            InjectionScheduleActualCorrection.request_id == request_id,
        )
    )


def _correction_replay_response(
    correction: InjectionScheduleActualCorrection,
    actual_id: str,
    payload_hash: str,
) -> dict[str, Any]:
    if (
        correction.actual_id != actual_id
        or correction.payload_hash != payload_hash
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_key_conflict",
                "message": "request_id 已用于另一笔实绩更正",
            },
        )
    response = json_object(correction.response_json)
    if not response:
        raise RuntimeError("实绩更正幂等台账缺少响应快照")
    response["idempotent_replay"] = True
    return response


def _actual_response(
    db: Session,
    actual: InjectionScheduleShiftActual,
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    version = load_version(db, actual.factory_id, actual.version_id)
    order = db.scalar(
        select(InjectionOrderMaster).where(
            InjectionOrderMaster.factory_id == actual.factory_id,
            InjectionOrderMaster.id == actual.order_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的订单")
    return {
        "actual": _serialize_actual(actual),
        "updated_order": serialize_order(order),
        "version": serialize_version(version),
        "tasks": list_tasks(db, version),
        "projections": json_list(actual.projection_json),
        "affected_machine_ids": [actual.machine_id],
        "idempotent_replay": idempotent_replay,
    }


def _serialize_run(run: InjectionScheduleReplanRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "factory_id": run.factory_id,
        "source_version_id": run.source_version_id,
        "result_version_id": run.result_version_id,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "source_revision": run.source_revision,
        "result_revision": run.result_revision,
        "context_hash": run.context_hash,
        "reason": run.reason,
        "request_id": run.request_id,
        "affected_machine_ids": json_list(run.affected_machine_ids_json),
        "affected_order_ids": json_list(run.affected_order_ids_json),
        "affected_task_ids": json_list(run.affected_task_ids_json),
        "impact": json_object(run.impact_json),
        "created_by": run.created_by,
        "created_by_name": run.created_by_name,
        "created_at": run.created_at,
    }


def _serialize_actual(
    actual: InjectionScheduleShiftActual,
) -> dict[str, Any]:
    return {
        "id": actual.id,
        "factory_id": actual.factory_id,
        "version_id": actual.version_id,
        "task_id": actual.task_id,
        "source_version_id": actual.source_version_id,
        "source_task_id": actual.source_task_id,
        "lineage_sequence": actual.lineage_sequence,
        "order_id": actual.order_id,
        "machine_id": actual.machine_id,
        "shift_date": actual.shift_date,
        "shift": actual.shift,
        "source": actual.source,
        "legacy_shift_code": actual.legacy_shift_code,
        "target_qty": actual.target_qty,
        "actual_qty": actual.actual_qty,
        "variance_qty": actual.variance_qty,
        "variance_reason": actual.variance_reason,
        "produced_baseline_qty": actual.produced_baseline_qty,
        "outstanding_qty_before": actual.outstanding_qty_before,
        "outstanding_qty_after": actual.outstanding_qty_after,
        "shortage_qty": actual.shortage_qty,
        "request_id": actual.request_id,
        "revision": actual.revision,
        "correction_count": actual.correction_count,
        "created_by": actual.created_by,
        "created_by_name": actual.created_by_name,
        "created_at": actual.created_at,
        "corrected_by": actual.corrected_by,
        "corrected_by_name": actual.corrected_by_name,
        "corrected_at": actual.corrected_at,
    }
