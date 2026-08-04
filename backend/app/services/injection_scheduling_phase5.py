from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from statistics import median
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, business_now, parse_business_timestamp
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingOrder,
    InjectionSchedulingShiftReport,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_phase5 import (
    InjectionSchedulingCycleObservation,
    InjectionSchedulingExternalEvent,
    InjectionSchedulingIntegrationCursor,
    InjectionSchedulingSpeedModel,
)
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingShiftReportCreate,
)
from app.schemas.injection_scheduling_phase5 import (
    InjectionSchedulingAnalyticsOverviewOut,
    InjectionSchedulingCalibrationRequest,
    InjectionSchedulingCalibrationResult,
    InjectionSchedulingDeviceBatchResult,
    InjectionSchedulingDeviceEventBatch,
    InjectionSchedulingDeviceEventResult,
    InjectionSchedulingErpOrderItem,
    InjectionSchedulingErpSyncBatch,
    InjectionSchedulingErpSyncResult,
    InjectionSchedulingIntegrationCursorOut,
    InjectionSchedulingMetricOut,
    InjectionSchedulingSpeedModelOut,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import require_injection_scheduling_factory
from app.services.injection_scheduling_execution import (
    create_shift_report,
    order_out,
)


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value))


def _float(value: Decimal | float) -> float:
    return float(value)


def _audit(
    db: Session,
    *,
    factory_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    request_id: str,
    detail: dict[str, Any],
    user: AuthContext,
) -> InjectionSchedulingAuditEvent:
    event = InjectionSchedulingAuditEvent(
        id=f"isaudit-{uuid4().hex}",
        factory_id=factory_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_revision=0,
        request_id=request_id,
        detail_json=_json(detail),
        actor_user_id=user.id,
        actor_name=_actor_name(user),
        created_at=_now(),
    )
    db.add(event)
    db.flush()
    return event


def integration_cursor_out(
    record: InjectionSchedulingIntegrationCursor,
) -> InjectionSchedulingIntegrationCursorOut:
    return InjectionSchedulingIntegrationCursorOut(
        source_type=record.source_type,
        source_key=record.source_key,
        cursor=record.cursor_value,
        status=record.status,
        last_received_at=record.last_received_at,
        last_success_at=record.last_success_at,
        last_error=record.last_error,
        event_count=record.event_count,
        revision=record.revision,
    )


def _upsert_cursor(
    db: Session,
    *,
    factory_id: str,
    source_type: str,
    source_key: str,
    cursor: str,
    event_count: int,
    user: AuthContext,
) -> InjectionSchedulingIntegrationCursor:
    timestamp = _now()
    record = db.scalar(
        select(InjectionSchedulingIntegrationCursor).where(
            InjectionSchedulingIntegrationCursor.factory_id == factory_id,
            InjectionSchedulingIntegrationCursor.source_type == source_type,
            InjectionSchedulingIntegrationCursor.source_key == source_key,
        )
    )
    if record is None:
        record = InjectionSchedulingIntegrationCursor(
            id=f"iscursor-{uuid4().hex}",
            factory_id=factory_id,
            source_type=source_type,
            source_key=source_key,
            cursor_value=cursor,
            status="ACTIVE",
            last_received_at=timestamp,
            last_success_at=timestamp,
            last_error="",
            event_count=event_count,
            revision=1,
            updated_by=user.id,
            updated_by_name=_actor_name(user),
            updated_at=timestamp,
        )
        db.add(record)
    else:
        record.cursor_value = cursor
        record.status = "ACTIVE"
        record.last_received_at = timestamp
        record.last_success_at = timestamp
        record.last_error = ""
        record.event_count += event_count
        record.revision += 1
        record.updated_by = user.id
        record.updated_by_name = _actor_name(user)
        record.updated_at = timestamp
    db.flush()
    return record


def _existing_external_event(
    db: Session,
    *,
    factory_id: str,
    source_type: str,
    source_key: str,
    external_event_id: str,
    payload_hash: str,
) -> InjectionSchedulingExternalEvent | None:
    record = db.scalar(
        select(InjectionSchedulingExternalEvent).where(
            InjectionSchedulingExternalEvent.factory_id == factory_id,
            InjectionSchedulingExternalEvent.source_type == source_type,
            InjectionSchedulingExternalEvent.source_key == source_key,
            InjectionSchedulingExternalEvent.external_event_id == external_event_id,
        )
    )
    if record is not None and record.payload_hash != payload_hash:
        raise HTTPException(
            status_code=409,
            detail="相同外部事件 ID 已用于不同内容，请检查上游版本或事件编号",
        )
    return record


def _add_external_event(
    db: Session,
    *,
    factory_id: str,
    source_type: str,
    source_key: str,
    external_event_id: str,
    event_type: str,
    occurred_at: str,
    payload: dict[str, Any],
    payload_hash: str,
    linked_entity_type: str,
    linked_entity_id: str,
    request_id: str,
    user: AuthContext,
    status: str = "APPLIED",
) -> InjectionSchedulingExternalEvent:
    timestamp = _now()
    record = InjectionSchedulingExternalEvent(
        id=f"isext-{uuid4().hex}",
        factory_id=factory_id,
        source_type=source_type,
        source_key=source_key,
        external_event_id=external_event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        payload_hash=payload_hash,
        payload_json=_json(payload),
        status=status,
        linked_entity_type=linked_entity_type,
        linked_entity_id=linked_entity_id,
        request_id=request_id,
        received_by=user.id,
        received_by_name=_actor_name(user),
        received_at=timestamp,
        applied_at=timestamp if status == "APPLIED" else "",
        error_detail="",
    )
    db.add(record)
    db.flush()
    return record


def _require_mold(db: Session, factory_id: str, mold_id: str | None) -> None:
    if mold_id is None:
        return
    if (
        db.scalar(
            select(InjectionSchedulingMold.id).where(
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.id == mold_id,
            )
        )
        is None
    ):
        raise HTTPException(
            status_code=409, detail=f"ERP 订单关联模具不存在：{mold_id}"
        )


def _erp_event_id(item: InjectionSchedulingErpOrderItem) -> str:
    digest = hashlib.sha256(
        f"{item.external_id}\0{item.external_version}".encode()
    ).hexdigest()
    return f"erp-order-{digest}"


def _reported_total(db: Session, factory_id: str, order_id: str) -> Decimal:
    return _decimal(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        InjectionSchedulingShiftReport.normalized_increment_quantity
                    ),
                    0,
                )
            ).where(
                InjectionSchedulingShiftReport.factory_id == factory_id,
                InjectionSchedulingShiftReport.order_id == order_id,
            )
        )
        or 0
    )


def sync_erp_orders(
    db: Session,
    payload: InjectionSchedulingErpSyncBatch,
    user: AuthContext,
    request_id: str,
) -> InjectionSchedulingErpSyncResult:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    created_count = 0
    updated_count = 0
    skipped_count = 0
    changed_order_ids: list[str] = []
    timestamp = _now()
    try:
        for item in payload.orders:
            item_payload = item.model_dump(mode="json")
            event_hash = _hash(item_payload)
            event_id = _erp_event_id(item)
            replay = _existing_external_event(
                db,
                factory_id=factory_id,
                source_type="ERP",
                source_key=payload.source_key,
                external_event_id=event_id,
                payload_hash=event_hash,
            )
            if replay is not None:
                skipped_count += 1
                if replay.linked_entity_id:
                    changed_order_ids.append(replay.linked_entity_id)
                continue
            _require_mold(db, factory_id, item.mold_id)
            order = db.scalar(
                select(InjectionSchedulingOrder)
                .where(
                    InjectionSchedulingOrder.factory_id == factory_id,
                    InjectionSchedulingOrder.source_type == "erp",
                    InjectionSchedulingOrder.source_ref == item.external_id,
                )
                .order_by(InjectionSchedulingOrder.created_at.desc())
                .limit(1)
            )
            if order is None:
                completed = _decimal(item.source_completed_quantity)
                quantity = _decimal(item.order_quantity)
                order = InjectionSchedulingOrder(
                    id=f"isorder-{uuid4().hex}",
                    factory_id=factory_id,
                    order_no=item.order_no,
                    item_no=item.item_no,
                    product_name=item.product_name,
                    mold_id=item.mold_id,
                    order_quantity=quantity,
                    source_completed_quantity=completed,
                    completed_quantity=completed,
                    estimated_completion_at="",
                    estimated_remaining_shifts=0,
                    delivery_slack_days=None,
                    delivery_start_date=(
                        item.delivery_start_date.isoformat()
                        if item.delivery_start_date
                        else ""
                    ),
                    delivery_due_date=(
                        item.delivery_due_date.isoformat()
                        if item.delivery_due_date
                        else ""
                    ),
                    priority_code=item.priority_code,
                    material_readiness_status=item.material_readiness_status,
                    warehouse_text=item.warehouse_text,
                    remark=item.remark,
                    source_type="erp",
                    source_ref=item.external_id,
                    source_version=item.external_version,
                    lineage_json=_json(
                        item.lineage | {"erp_source": payload.source_key}
                    ),
                    status="COMPLETED" if completed >= quantity else "BACKLOG",
                    revision=1,
                    created_by=user.id,
                    created_by_name=_actor_name(user),
                    updated_by=user.id,
                    updated_by_name=_actor_name(user),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(order)
                db.flush()
                created_count += 1
            else:
                report_total = _reported_total(db, factory_id, order.id)
                source_completed = _decimal(item.source_completed_quantity)
                completed = source_completed + report_total
                quantity = _decimal(item.order_quantity)
                if quantity < completed:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"ERP 订单 {item.order_no} 数量 {quantity} 小于系统累计完成数 "
                            f"{completed}，必须先核对来源数据"
                        ),
                    )
                order.order_no = item.order_no
                order.item_no = item.item_no
                order.product_name = item.product_name
                order.mold_id = item.mold_id
                order.order_quantity = quantity
                order.source_completed_quantity = source_completed
                order.completed_quantity = completed
                order.delivery_start_date = (
                    item.delivery_start_date.isoformat()
                    if item.delivery_start_date
                    else ""
                )
                order.delivery_due_date = (
                    item.delivery_due_date.isoformat() if item.delivery_due_date else ""
                )
                order.priority_code = item.priority_code
                order.material_readiness_status = item.material_readiness_status
                order.warehouse_text = item.warehouse_text
                order.remark = item.remark
                order.source_version = item.external_version
                order.lineage_json = _json(
                    item.lineage | {"erp_source": payload.source_key}
                )
                order.status = (
                    "COMPLETED"
                    if completed >= quantity
                    else ("SCHEDULED" if order.status == "SCHEDULED" else "BACKLOG")
                )
                order.revision += 1
                order.updated_by = user.id
                order.updated_by_name = _actor_name(user)
                order.updated_at = timestamp
                updated_count += 1
            _add_external_event(
                db,
                factory_id=factory_id,
                source_type="ERP",
                source_key=payload.source_key,
                external_event_id=event_id,
                event_type="ORDER_UPSERT",
                occurred_at=item.occurred_at.astimezone(BUSINESS_TIME_ZONE).isoformat(
                    timespec="seconds"
                ),
                payload=item_payload,
                payload_hash=event_hash,
                linked_entity_type="order",
                linked_entity_id=order.id,
                request_id=request_id,
                user=user,
            )
            changed_order_ids.append(order.id)
        cursor = _upsert_cursor(
            db,
            factory_id=factory_id,
            source_type="ERP",
            source_key=payload.source_key,
            cursor=payload.cursor,
            event_count=created_count + updated_count,
            user=user,
        )
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="erp_orders_incrementally_synced",
            entity_type="integration",
            entity_id=cursor.id,
            request_id=request_id,
            detail={
                "source_key": payload.source_key,
                "cursor": payload.cursor,
                "created_count": created_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "order_ids": changed_order_ids,
                "orders": [
                    order_out(record).model_dump(mode="json")
                    for record in db.scalars(
                        select(InjectionSchedulingOrder).where(
                            InjectionSchedulingOrder.factory_id == factory_id,
                            InjectionSchedulingOrder.id.in_(set(changed_order_ids)),
                        )
                    ).all()
                ]
                if changed_order_ids
                else [],
            },
            user=user,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="ERP 增量批次写入冲突") from exc
    return InjectionSchedulingErpSyncResult(
        factory_id=factory_id,
        source_key=payload.source_key,
        cursor=payload.cursor,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        order_ids=list(dict.fromkeys(changed_order_ids)),
        audit_sequence=audit.sequence,
        integration=integration_cursor_out(cursor),
    )


def _resolve_device_task(
    db: Session,
    *,
    factory_id: str,
    machine_code: str,
    task_id: str | None,
) -> tuple[InjectionSchedulingMachine, InjectionSchedulingTask]:
    machine = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.factory_id == factory_id,
            InjectionSchedulingMachine.machine_code == machine_code,
        )
    )
    if machine is None:
        raise HTTPException(
            status_code=409, detail=f"设备事件机台不存在：{machine_code}"
        )
    query = select(InjectionSchedulingTask).where(
        InjectionSchedulingTask.factory_id == factory_id,
        InjectionSchedulingTask.machine_id == machine.id,
        InjectionSchedulingTask.active_execution.is_(True),
    )
    if task_id:
        query = query.where(InjectionSchedulingTask.id == task_id)
    else:
        query = query.where(InjectionSchedulingTask.execution_status == "RUNNING")
    tasks = list(db.scalars(query.order_by(InjectionSchedulingTask.sequence_no)).all())
    if not tasks:
        raise HTTPException(
            status_code=409,
            detail=f"机台 {machine_code} 没有可接收设备数据的当前已发布任务",
        )
    if len(tasks) > 1:
        raise HTTPException(
            status_code=409,
            detail=f"机台 {machine_code} 匹配到多个任务，设备事件必须提供 task_id",
        )
    return machine, tasks[0]


def _shift_code(value: datetime) -> str:
    local = value.astimezone(BUSINESS_TIME_ZONE).time()
    return "DAY" if time(8, 0) <= local < time(20, 0) else "NIGHT"


def speed_model_out(
    record: InjectionSchedulingSpeedModel,
    mold_no: str,
) -> InjectionSchedulingSpeedModelOut:
    return InjectionSchedulingSpeedModelOut(
        id=record.id,
        factory_id=record.factory_id,
        mold_id=record.mold_id,
        mold_no=mold_no,
        sample_count=record.sample_count,
        calibrated_cycle_seconds=_float(record.calibrated_cycle_seconds),
        units_per_cycle=_float(record.units_per_cycle),
        calibrated_units_per_hour=_float(record.calibrated_units_per_hour),
        confidence=_float(record.confidence),
        status=record.status,
        source_window_start=record.source_window_start,
        source_window_end=record.source_window_end,
        last_observed_at=record.last_observed_at,
        revision=record.revision,
        updated_at=record.updated_at,
    )


def rebuild_speed_models(
    db: Session,
    payload: InjectionSchedulingCalibrationRequest,
    user: AuthContext,
    request_id: str,
    *,
    commit: bool = True,
) -> InjectionSchedulingCalibrationResult:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    mold_ids = payload.mold_ids or list(
        db.scalars(
            select(InjectionSchedulingCycleObservation.mold_id)
            .where(InjectionSchedulingCycleObservation.factory_id == factory_id)
            .distinct()
        ).all()
    )
    if mold_ids:
        existing_molds = {
            item.id: item
            for item in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == factory_id,
                    InjectionSchedulingMold.id.in_(mold_ids),
                )
            ).all()
        }
        missing = sorted(set(mold_ids) - set(existing_molds))
        if missing:
            raise HTTPException(
                status_code=409,
                detail={"message": "校准模具不存在", "mold_ids": missing},
            )
    else:
        existing_molds = {}
    timestamp = _now()
    outputs: list[InjectionSchedulingSpeedModelOut] = []
    calibrated_count = 0
    insufficient_count = 0
    for mold_id in mold_ids:
        observations = list(
            db.scalars(
                select(InjectionSchedulingCycleObservation)
                .where(
                    InjectionSchedulingCycleObservation.factory_id == factory_id,
                    InjectionSchedulingCycleObservation.mold_id == mold_id,
                )
                .order_by(InjectionSchedulingCycleObservation.observed_at.desc())
                .limit(200)
            ).all()
        )
        if not observations:
            continue
        cycles = [float(item.cycle_seconds) for item in observations]
        units = [float(item.units_per_cycle) for item in observations]
        rates = [3600 * unit / cycle for unit, cycle in zip(units, cycles, strict=True)]
        calibrated_cycle = median(cycles)
        calibrated_units = median(units)
        calibrated_rate = median(rates)
        sample_count = len(observations)
        status = (
            "ACTIVE"
            if sample_count >= payload.minimum_sample_count
            else "INSUFFICIENT_DATA"
        )
        confidence = min(1.0, sample_count / 10)
        model = db.scalar(
            select(InjectionSchedulingSpeedModel).where(
                InjectionSchedulingSpeedModel.factory_id == factory_id,
                InjectionSchedulingSpeedModel.mold_id == mold_id,
            )
        )
        if model is None:
            model = InjectionSchedulingSpeedModel(
                id=f"isspeed-{uuid4().hex}",
                factory_id=factory_id,
                mold_id=mold_id,
                sample_count=sample_count,
                calibrated_cycle_seconds=_decimal(calibrated_cycle),
                units_per_cycle=_decimal(calibrated_units),
                calibrated_units_per_hour=_decimal(calibrated_rate),
                confidence=_decimal(confidence),
                status=status,
                source_window_start=min(item.observed_at for item in observations),
                source_window_end=max(item.observed_at for item in observations),
                last_observed_at=max(item.observed_at for item in observations),
                revision=1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=timestamp,
            )
            db.add(model)
        else:
            model.sample_count = sample_count
            model.calibrated_cycle_seconds = _decimal(calibrated_cycle)
            model.units_per_cycle = _decimal(calibrated_units)
            model.calibrated_units_per_hour = _decimal(calibrated_rate)
            model.confidence = _decimal(confidence)
            model.status = status
            model.source_window_start = min(item.observed_at for item in observations)
            model.source_window_end = max(item.observed_at for item in observations)
            model.last_observed_at = max(item.observed_at for item in observations)
            model.revision += 1
            model.updated_by = user.id
            model.updated_by_name = _actor_name(user)
            model.updated_at = timestamp
        db.flush()
        outputs.append(speed_model_out(model, existing_molds[mold_id].mold_no))
        if status == "ACTIVE":
            calibrated_count += 1
        else:
            insufficient_count += 1
    audit = _audit(
        db,
        factory_id=factory_id,
        event_type="speed_models_calibrated",
        entity_type="speed_model",
        entity_id=factory_id,
        request_id=request_id,
        detail={
            "minimum_sample_count": payload.minimum_sample_count,
            "calibrated_count": calibrated_count,
            "insufficient_count": insufficient_count,
            "mold_ids": mold_ids,
        },
        user=user,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return InjectionSchedulingCalibrationResult(
        factory_id=factory_id,
        calibrated_count=calibrated_count,
        insufficient_count=insufficient_count,
        models=outputs,
        audit_sequence=audit.sequence,
    )


def ingest_device_events(
    db: Session,
    payload: InjectionSchedulingDeviceEventBatch,
    user: AuthContext,
    request_id: str,
) -> InjectionSchedulingDeviceBatchResult:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    results: list[InjectionSchedulingDeviceEventResult] = []
    applied_count = 0
    skipped_count = 0
    affected_molds: set[str] = set()
    try:
        for item in payload.events:
            item_payload = item.model_dump(mode="json")
            event_hash = _hash(item_payload)
            replay = _existing_external_event(
                db,
                factory_id=factory_id,
                source_type="DEVICE",
                source_key=payload.source_key,
                external_event_id=item.external_event_id,
                payload_hash=event_hash,
            )
            if replay is not None:
                skipped_count += 1
                results.append(
                    InjectionSchedulingDeviceEventResult(
                        external_event_id=item.external_event_id,
                        task_id=replay.linked_entity_id,
                        order_id="",
                        machine_id="",
                        normalized_increment_quantity=0,
                        observation_created=False,
                        replayed=True,
                    )
                )
                continue
            machine, task = _resolve_device_task(
                db,
                factory_id=factory_id,
                machine_code=item.machine_code,
                task_id=item.task_id,
            )
            local_time = item.occurred_at.astimezone(BUSINESS_TIME_ZONE)
            report_request_id = (
                "device-"
                + hashlib.sha256(
                    f"{factory_id}\0{payload.source_key}\0{item.external_event_id}".encode()
                ).hexdigest()
            )
            report, refreshed_task, order, _, _ = create_shift_report(
                db,
                task.id,
                InjectionSchedulingShiftReportCreate(
                    factory_id=factory_id,
                    expected_revision=task.revision,
                    request_id=report_request_id,
                    business_date=local_time.date(),
                    shift_code=_shift_code(item.occurred_at),
                    quantity_mode="CUMULATIVE",
                    reported_quantity=item.cumulative_quantity,
                    shift_target_quantity=float(task.shift_target_quantity),
                    downtime_minutes=item.downtime_minutes,
                    exception_code=item.exception_code,
                    exception_detail=item.exception_detail,
                    reported_status=item.status,
                ),
                user,
                commit=False,
            )
            external = _add_external_event(
                db,
                factory_id=factory_id,
                source_type="DEVICE",
                source_key=payload.source_key,
                external_event_id=item.external_event_id,
                event_type="PRODUCTION_READING",
                occurred_at=local_time.isoformat(timespec="seconds"),
                payload=item_payload,
                payload_hash=event_hash,
                linked_entity_type="task",
                linked_entity_id=task.id,
                request_id=request_id,
                user=user,
            )
            observation_created = False
            increment = _float(report.normalized_increment_quantity)
            if item.cycle_seconds is not None and task.mold_id:
                runtime_minutes = (
                    _decimal(item.cycle_seconds)
                    * _decimal(increment)
                    / _decimal(item.units_per_cycle)
                    / Decimal(60)
                )
                db.add(
                    InjectionSchedulingCycleObservation(
                        id=f"iscycle-{uuid4().hex}",
                        factory_id=factory_id,
                        external_event_id=external.id,
                        task_id=task.id,
                        order_id=order.id,
                        machine_id=machine.id,
                        mold_id=task.mold_id,
                        observed_at=local_time.isoformat(timespec="seconds"),
                        cycle_seconds=_decimal(item.cycle_seconds),
                        units_per_cycle=_decimal(item.units_per_cycle),
                        produced_quantity=_decimal(increment),
                        runtime_minutes=runtime_minutes,
                        source_key=payload.source_key,
                        created_at=_now(),
                    )
                )
                affected_molds.add(task.mold_id)
                observation_created = True
            results.append(
                InjectionSchedulingDeviceEventResult(
                    external_event_id=item.external_event_id,
                    task_id=refreshed_task.id,
                    order_id=order.id,
                    machine_id=machine.id,
                    normalized_increment_quantity=increment,
                    observation_created=observation_created,
                    replayed=False,
                )
            )
            applied_count += 1
        if affected_molds:
            db.flush()
        calibration = (
            rebuild_speed_models(
                db,
                InjectionSchedulingCalibrationRequest(
                    factory_id=factory_id,
                    mold_ids=sorted(affected_molds),
                    minimum_sample_count=3,
                ),
                user,
                f"{request_id}-calibration"[:128],
                commit=False,
            )
            if affected_molds
            else None
        )
        cursor = _upsert_cursor(
            db,
            factory_id=factory_id,
            source_type="DEVICE",
            source_key=payload.source_key,
            cursor=payload.cursor,
            event_count=applied_count,
            user=user,
        )
        _audit(
            db,
            factory_id=factory_id,
            event_type="device_production_events_ingested",
            entity_type="integration",
            entity_id=cursor.id,
            request_id=request_id,
            detail={
                "source_key": payload.source_key,
                "cursor": payload.cursor,
                "applied_count": applied_count,
                "skipped_count": skipped_count,
                "affected_mold_ids": sorted(affected_molds),
            },
            user=user,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="设备生产事件批次写入冲突") from exc
    return InjectionSchedulingDeviceBatchResult(
        factory_id=factory_id,
        source_key=payload.source_key,
        cursor=payload.cursor,
        applied_count=applied_count,
        skipped_count=skipped_count,
        calibrated_mold_count=calibration.calibrated_count if calibration else 0,
        events=results,
        integration=integration_cursor_out(cursor),
    )


def _empty_cursor(source_type: str) -> InjectionSchedulingIntegrationCursorOut:
    return InjectionSchedulingIntegrationCursorOut(
        source_type=source_type,
        source_key="未配置",
        cursor="",
        status="NOT_CONFIGURED",
        last_received_at="",
        last_success_at="",
        last_error="",
        event_count=0,
        revision=1,
    )


def analytics_overview(
    db: Session,
    factory_id: str,
    date_from: date,
    date_to: date,
) -> InjectionSchedulingAnalyticsOverviewOut:
    factory_id = require_injection_scheduling_factory(factory_id)
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from 不能晚于 date_to")
    start = datetime.combine(date_from, time.min, tzinfo=BUSINESS_TIME_ZONE)
    end = datetime.combine(
        date_to + timedelta(days=1), time.min, tzinfo=BUSINESS_TIME_ZONE
    )
    start_text = start.isoformat(timespec="seconds")
    end_text = end.isoformat(timespec="seconds")
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id
            )
        ).all()
    )
    reports = list(
        db.scalars(
            select(InjectionSchedulingShiftReport).where(
                InjectionSchedulingShiftReport.factory_id == factory_id,
                InjectionSchedulingShiftReport.created_at >= start_text,
                InjectionSchedulingShiftReport.created_at < end_text,
            )
        ).all()
    )
    completion_by_task: dict[str, datetime] = {}
    for report in reports:
        if report.reported_status != "COMPLETED":
            continue
        observed = parse_business_timestamp(report.created_at)
        if observed is not None and (
            report.task_id not in completion_by_task
            or observed > completion_by_task[report.task_id]
        ):
            completion_by_task[report.task_id] = observed
    completed_with_plan = 0
    completed_on_plan = 0
    for task in tasks:
        actual = completion_by_task.get(task.id)
        planned = parse_business_timestamp(task.planned_finish)
        if actual is None or planned is None:
            continue
        completed_with_plan += 1
        if actual <= planned:
            completed_on_plan += 1

    scheduled_tasks = [
        item
        for item in tasks
        if item.planned_start and start_text <= item.planned_start < end_text
    ]
    mold_changes = 0
    queues: dict[tuple[str, str], list[InjectionSchedulingTask]] = {}
    for task in scheduled_tasks:
        queues.setdefault((task.plan_id, task.machine_id), []).append(task)
    for queue in queues.values():
        ordered = sorted(queue, key=lambda item: item.sequence_no)
        mold_changes += sum(
            1
            for previous, current in pairwise(ordered)
            if previous.mold_id
            and current.mold_id
            and previous.mold_id != current.mold_id
        )

    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.delivery_due_date >= date_from.isoformat(),
                InjectionSchedulingOrder.delivery_due_date <= date_to.isoformat(),
            )
        ).all()
    )
    tasks_by_order: dict[str, list[InjectionSchedulingTask]] = {}
    for task in tasks:
        tasks_by_order.setdefault(task.order_id, []).append(task)
    overdue_count = 0
    reference_time = min(business_now(), end)
    for order in orders:
        due = datetime.combine(
            date.fromisoformat(order.delivery_due_date),
            time.max,
            tzinfo=BUSINESS_TIME_ZONE,
        )
        completions = [
            completion_by_task[item.id]
            for item in tasks_by_order.get(order.id, [])
            if item.id in completion_by_task
        ]
        actual = max(completions) if completions else None
        if (actual is not None and actual > due) or (
            actual is None and order.status != "COMPLETED" and reference_time > due
        ):
            overdue_count += 1

    observations = list(
        db.scalars(
            select(InjectionSchedulingCycleObservation).where(
                InjectionSchedulingCycleObservation.factory_id == factory_id,
                InjectionSchedulingCycleObservation.observed_at >= start_text,
                InjectionSchedulingCycleObservation.observed_at < end_text,
            )
        ).all()
    )
    runtime_minutes = sum(float(item.runtime_minutes) for item in observations)
    machine_count = int(
        db.scalar(
            select(func.count(InjectionSchedulingMachine.id)).where(
                InjectionSchedulingMachine.factory_id == factory_id,
                InjectionSchedulingMachine.status.notin_(("offline", "maintenance")),
            )
        )
        or 0
    )
    available_minutes = machine_count * (end - start).total_seconds() / 60

    cursor_records = list(
        db.scalars(
            select(InjectionSchedulingIntegrationCursor)
            .where(InjectionSchedulingIntegrationCursor.factory_id == factory_id)
            .order_by(
                InjectionSchedulingIntegrationCursor.source_type,
                InjectionSchedulingIntegrationCursor.source_key,
            )
        ).all()
    )
    statuses = [integration_cursor_out(item) for item in cursor_records]
    present_types = {item.source_type for item in statuses}
    statuses.extend(
        _empty_cursor(source_type)
        for source_type in ("ERP", "DEVICE")
        if source_type not in present_types
    )
    model_rows = list(
        db.execute(
            select(InjectionSchedulingSpeedModel, InjectionSchedulingMold.mold_no)
            .join(
                InjectionSchedulingMold,
                (InjectionSchedulingMold.id == InjectionSchedulingSpeedModel.mold_id)
                & (
                    InjectionSchedulingMold.factory_id
                    == InjectionSchedulingSpeedModel.factory_id
                ),
            )
            .where(InjectionSchedulingSpeedModel.factory_id == factory_id)
            .order_by(
                InjectionSchedulingSpeedModel.status,
                InjectionSchedulingSpeedModel.updated_at.desc(),
            )
            .limit(100)
        ).all()
    )
    speed_models = [speed_model_out(model, mold_no) for model, mold_no in model_rows]
    plan_accuracy_value = (
        completed_on_plan / completed_with_plan * 100 if completed_with_plan else 0
    )
    overdue_value = overdue_count / len(orders) * 100 if orders else 0
    utilization_value = (
        runtime_minutes / available_minutes * 100 if available_minutes else 0
    )
    notes = [
        "计划准确率按所选期间内有完成回报且实际完成时间不晚于计划完成时间的任务计算。",
        "超期率按交货完成期落在所选期间内的订单计算；未完成且已过交期也计入超期。",
        "机台利用率仅使用设备周期事件换算的实际运行分钟；没有设备数据时显示 0，并保留样本数。",
        "速度模型使用最近 200 条周期观察的中位数，至少 3 条样本才进入 ACTIVE。",
    ]
    if utilization_value > 100:
        notes.append(
            "设备事件换算利用率超过 100%，请检查重复累计量、周期或每啤产出配置。"
        )
    return InjectionSchedulingAnalyticsOverviewOut(
        factory_id=factory_id,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        generated_at=_now(),
        plan_accuracy=InjectionSchedulingMetricOut(
            value=round(plan_accuracy_value, 2),
            numerator=completed_on_plan,
            denominator=completed_with_plan,
            unit="%",
            sample_count=completed_with_plan,
            formula="按计划完成任务 / 有计划完成时间的已完成任务",
        ),
        mold_change_count=InjectionSchedulingMetricOut(
            value=float(mold_changes),
            numerator=float(mold_changes),
            denominator=float(len(scheduled_tasks)),
            unit="次",
            sample_count=len(scheduled_tasks),
            formula="同计划同机台相邻任务的模具编号变化次数",
        ),
        overdue_rate=InjectionSchedulingMetricOut(
            value=round(overdue_value, 2),
            numerator=overdue_count,
            denominator=len(orders),
            unit="%",
            sample_count=len(orders),
            formula="超期订单 / 期间内有交期订单",
        ),
        machine_utilization=InjectionSchedulingMetricOut(
            value=round(utilization_value, 2),
            numerator=round(runtime_minutes, 2),
            denominator=round(available_minutes, 2),
            unit="%",
            sample_count=len(observations),
            formula="设备周期事件实际运行分钟 / 可用机台期间分钟",
        ),
        integration_statuses=statuses,
        speed_models=speed_models,
        device_interface_configured=any(
            item.source_type == "DEVICE" and item.status == "ACTIVE"
            for item in statuses
        ),
        notes=notes,
    )
