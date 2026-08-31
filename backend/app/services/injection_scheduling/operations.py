from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import business_now, business_today
from app.models.injection_schedule import (
    InjectionScheduleFactorySettings,
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleMachineUnavailableWindow,
    InjectionScheduleOrderDemand,
    InjectionScheduleShiftOutput,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling.audit import write_audit_event
from app.services.injection_scheduling.calculations import progress
from app.services.injection_scheduling.read_service import FACTORY_NAMES

WINDOW_TYPES = {"MAINTENANCE", "FAULT", "POWER_OUTAGE", "MOLD_REPAIR", "TEMPORARY_STOP"}


def _now_text() -> str:
    return business_now().isoformat(timespec="seconds")


def _parse_time(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} 必须是 ISO 时间") from exc


def ensure_factory_settings(
    db: Session, factory_id: str, actor: AuthContext
) -> InjectionScheduleFactorySettings:
    settings = db.scalar(
        select(InjectionScheduleFactorySettings).where(
            InjectionScheduleFactorySettings.factory_id == factory_id
        )
    )
    if settings is not None:
        return settings
    now = _now_text()
    settings = InjectionScheduleFactorySettings(
        id=f"is-settings-{uuid4().hex}",
        factory_id=factory_id,
        factory_name=FACTORY_NAMES.get(factory_id, factory_id),
        business_date=business_today(),
        created_by=actor.id,
        created_by_name=actor.display_name,
        updated_by=actor.id,
        updated_by_name=actor.display_name,
        created_at=now,
        updated_at=now,
    )
    db.add(settings)
    db.flush()
    return settings


def _line_and_order(
    db: Session, factory_id: str, line_id: str
) -> tuple[InjectionScheduleLine, InjectionScheduleOrderDemand]:
    row = db.execute(
        select(InjectionScheduleLine, InjectionScheduleOrderDemand)
        .join(
            InjectionScheduleOrderDemand,
            InjectionScheduleOrderDemand.id == InjectionScheduleLine.order_demand_id,
        )
        .where(
            InjectionScheduleLine.id == line_id,
            InjectionScheduleLine.factory_id == factory_id,
            InjectionScheduleOrderDemand.factory_id == factory_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="排程行不存在")
    return row[0], row[1]


def _line_snapshot(line: InjectionScheduleLine) -> dict[str, object]:
    return {
        "machine_id": line.machine_id,
        "sequence_no": str(line.sequence_no) if line.sequence_no is not None else None,
        "status": line.status,
        "is_locked": line.is_locked,
        "planned_start_at": line.planned_start_at,
        "planned_finish_at": line.planned_finish_at,
        "version": line.version,
        "schedule_revision": line.schedule_revision,
    }


def _validate_versions(
    line: InjectionScheduleLine,
    settings: InjectionScheduleFactorySettings,
    expected_line_version: int,
    expected_schedule_revision: int,
) -> None:
    if (
        line.version != expected_line_version
        or settings.schedule_revision != expected_schedule_revision
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "排程已被其他用户修改，请刷新后重试",
                "latest_line": _line_snapshot(line),
                "latest_schedule_revision": settings.schedule_revision,
            },
        )


def validate_move(
    db: Session,
    *,
    factory_id: str,
    line_id: str,
    target_machine_id: str,
    planned_start_at: str,
    planned_finish_at: str,
    sequence_no: Decimal | None,
    expected_line_version: int,
    expected_schedule_revision: int,
    actor: AuthContext,
) -> dict[str, object]:
    line, order = _line_and_order(db, factory_id, line_id)
    settings = ensure_factory_settings(db, factory_id, actor)
    _validate_versions(
        line, settings, expected_line_version, expected_schedule_revision
    )
    if line.is_locked:
        raise HTTPException(status_code=409, detail="锁定排程不能移动")
    start = _parse_time(planned_start_at, "planned_start_at")
    finish = _parse_time(planned_finish_at, "planned_finish_at")
    if start >= finish:
        raise HTTPException(status_code=422, detail="计划完成时间必须晚于开始时间")
    machine = db.scalar(
        select(InjectionScheduleMachine).where(
            InjectionScheduleMachine.id == target_machine_id,
            InjectionScheduleMachine.factory_id == factory_id,
        )
    )
    if machine is None:
        raise HTTPException(status_code=404, detail="目标机台不存在")
    conflicts: list[dict[str, object]] = []
    if machine.status != "AVAILABLE":
        conflicts.append(
            {"code": "MACHINE_UNAVAILABLE", "message": "目标机台当前不可用"}
        )
    if (
        order.required_machine_a_value is not None
        and machine.machine_ounce_capacity is not None
        and machine.machine_ounce_capacity < order.required_machine_a_value
    ):
        conflicts.append(
            {
                "code": "MACHINE_A_TOO_SMALL",
                "message": (
                    f"订单要求 {order.required_machine_a_value}A，"
                    f"机台仅 {machine.machine_ounce_capacity}A"
                ),
            }
        )
    windows = db.scalars(
        select(InjectionScheduleMachineUnavailableWindow).where(
            InjectionScheduleMachineUnavailableWindow.factory_id == factory_id,
            InjectionScheduleMachineUnavailableWindow.machine_id == target_machine_id,
            InjectionScheduleMachineUnavailableWindow.start_at < planned_finish_at,
            InjectionScheduleMachineUnavailableWindow.end_at > planned_start_at,
        )
    ).all()
    conflicts.extend(
        {
            "code": "MAINTENANCE_WINDOW",
            "message": item.reason or item.window_type,
            "window_id": item.id,
        }
        for item in windows
    )
    overlapping = db.scalars(
        select(InjectionScheduleLine).where(
            InjectionScheduleLine.factory_id == factory_id,
            InjectionScheduleLine.machine_id == target_machine_id,
            InjectionScheduleLine.id != line_id,
            InjectionScheduleLine.status.notin_(("COMPLETED", "CANCELLED")),
            InjectionScheduleLine.planned_start_at < planned_finish_at,
            InjectionScheduleLine.planned_finish_at > planned_start_at,
        )
    ).all()
    conflicts.extend(
        {"code": "SCHEDULE_OVERLAP", "message": "与已有排程重叠", "line_id": item.id}
        for item in overlapping
    )
    token_payload = {
        "factory_id": factory_id,
        "line_id": line_id,
        "target_machine_id": target_machine_id,
        "planned_start_at": planned_start_at,
        "planned_finish_at": planned_finish_at,
        "sequence_no": str(sequence_no) if sequence_no is not None else "",
        "line_version": line.version,
        "schedule_revision": settings.schedule_revision,
        "conflicts": conflicts,
    }
    token = hashlib.sha256(
        json.dumps(token_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **token_payload,
        "valid": not conflicts,
        "validate_token": token,
        "machine_code": machine.machine_code,
    }


def move_line(
    db: Session,
    *,
    factory_id: str,
    line_id: str,
    target_machine_id: str,
    planned_start_at: str,
    planned_finish_at: str,
    sequence_no: Decimal | None,
    expected_line_version: int,
    expected_schedule_revision: int,
    validate_token: str,
    reason: str,
    actor: AuthContext,
) -> dict[str, object]:
    validation = validate_move(
        db,
        factory_id=factory_id,
        line_id=line_id,
        target_machine_id=target_machine_id,
        planned_start_at=planned_start_at,
        planned_finish_at=planned_finish_at,
        sequence_no=sequence_no,
        expected_line_version=expected_line_version,
        expected_schedule_revision=expected_schedule_revision,
        actor=actor,
    )
    if not validation["valid"]:
        raise HTTPException(
            status_code=409, detail={"message": "移动校验未通过", **validation}
        )
    if validate_token != validation["validate_token"]:
        raise HTTPException(status_code=409, detail="移动校验令牌已失效，请重新校验")
    line, order = _line_and_order(db, factory_id, line_id)
    settings = ensure_factory_settings(db, factory_id, actor)
    before = _line_snapshot(line)
    if sequence_no is None:
        sequence_no = (
            db.scalar(
                select(func.max(InjectionScheduleLine.sequence_no)).where(
                    InjectionScheduleLine.factory_id == factory_id,
                    InjectionScheduleLine.machine_id == target_machine_id,
                )
            )
            or Decimal("0")
        ) + Decimal("10")
    line.machine_id = target_machine_id
    line.sequence_no = sequence_no
    line.status = "SCHEDULED"
    line.planned_start_at = planned_start_at
    line.planned_finish_at = planned_finish_at
    line.manual_adjustment_reason = reason.strip()
    line.schedule_source = "MANUAL"
    line.version += 1
    settings.schedule_revision += 1
    line.schedule_revision = settings.schedule_revision
    line.updated_by = actor.id
    line.updated_by_name = actor.display_name
    line.updated_at = _now_text()
    order.status = "SCHEDULED"
    order.updated_by = actor.id
    order.updated_by_name = actor.display_name
    order.updated_at = line.updated_at
    order.version += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="SCHEDULE_LINE_MOVED",
        entity_type="SCHEDULE_LINE",
        entity_id=line.id,
        entity_version=line.version,
        actor=actor,
        reason=reason,
        before=before,
        after=_line_snapshot(line),
    )
    db.commit()
    return {
        "line": _line_snapshot(line),
        "schedule_revision": settings.schedule_revision,
    }


def set_line_action(
    db: Session,
    *,
    factory_id: str,
    line_id: str,
    action: str,
    expected_line_version: int,
    expected_schedule_revision: int,
    reason: str,
    actor: AuthContext,
) -> dict[str, object]:
    line, order = _line_and_order(db, factory_id, line_id)
    settings = ensure_factory_settings(db, factory_id, actor)
    _validate_versions(
        line, settings, expected_line_version, expected_schedule_revision
    )
    before = _line_snapshot(line)
    if action == "lock":
        line.is_locked = True
    elif action == "unlock":
        line.is_locked = False
    elif action == "pause":
        if line.status != "IN_PRODUCTION":
            raise HTTPException(status_code=409, detail="只有生产中的任务可以暂停")
        line.status = "PAUSED"
    elif action == "resume":
        if line.status != "PAUSED":
            raise HTTPException(status_code=409, detail="只有暂停任务可以恢复")
        line.status = order.status = "IN_PRODUCTION"
    else:
        raise HTTPException(status_code=422, detail="不支持的排程操作")
    line.version += 1
    settings.schedule_revision += 1
    line.schedule_revision = settings.schedule_revision
    line.updated_by = actor.id
    line.updated_by_name = actor.display_name
    line.updated_at = _now_text()
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type=f"SCHEDULE_LINE_{action.upper()}",
        entity_type="SCHEDULE_LINE",
        entity_id=line.id,
        entity_version=line.version,
        actor=actor,
        reason=reason,
        before=before,
        after=_line_snapshot(line),
    )
    db.commit()
    return {
        "line": _line_snapshot(line),
        "schedule_revision": settings.schedule_revision,
    }


def put_shift_output(
    db: Session,
    *,
    factory_id: str,
    line_id: str,
    production_date: str,
    shift: str,
    reported_shots: Decimal,
    defect_shots: Decimal,
    downtime_minutes: int,
    downtime_reason: str,
    remark: str,
    version: int | None,
    actor: AuthContext,
) -> dict[str, object]:
    if shift not in {"DAY", "NIGHT"}:
        raise HTTPException(status_code=422, detail="shift 仅支持 DAY 或 NIGHT")
    if reported_shots < 0 or defect_shots < 0 or defect_shots > reported_shots:
        raise HTTPException(status_code=422, detail="班次啤数或不良数不合法")
    if downtime_minutes < 0:
        raise HTTPException(status_code=422, detail="停机分钟不能为负数")
    line, order = _line_and_order(db, factory_id, line_id)
    settings = ensure_factory_settings(db, factory_id, actor)
    output = db.scalar(
        select(InjectionScheduleShiftOutput).where(
            InjectionScheduleShiftOutput.factory_id == factory_id,
            InjectionScheduleShiftOutput.schedule_line_id == line_id,
            InjectionScheduleShiftOutput.production_date == production_date,
            InjectionScheduleShiftOutput.shift == shift,
        )
    )
    now = _now_text()
    before: dict[str, object] = {}
    qualified = reported_shots - defect_shots
    if output is None:
        if version not in (None, 0):
            raise HTTPException(status_code=409, detail="班次记录尚不存在，请刷新")
        output = InjectionScheduleShiftOutput(
            id=f"is-output-{uuid4().hex}",
            factory_id=factory_id,
            schedule_line_id=line_id,
            production_date=production_date,
            shift=shift,
            reported_shots=reported_shots,
            defect_shots=defect_shots,
            qualified_shots=qualified,
            downtime_minutes=downtime_minutes,
            downtime_reason=downtime_reason.strip(),
            remark=remark.strip(),
            reported_by=actor.id,
            reported_by_name=actor.display_name,
            reported_at=now,
            updated_at=now,
        )
        db.add(output)
    else:
        if version != output.version:
            raise HTTPException(
                status_code=409,
                detail={"message": "班次记录已更新", "latest_version": output.version},
            )
        before = {
            "reported_shots": str(output.reported_shots),
            "defect_shots": str(output.defect_shots),
            "version": output.version,
        }
        output.reported_shots = reported_shots
        output.defect_shots = defect_shots
        output.qualified_shots = qualified
        output.downtime_minutes = downtime_minutes
        output.downtime_reason = downtime_reason.strip()
        output.remark = remark.strip()
        output.reported_by = actor.id
        output.reported_by_name = actor.display_name
        output.reported_at = now
        output.updated_at = now
        output.version += 1
    db.flush()
    total = db.scalar(
        select(
            func.coalesce(func.sum(InjectionScheduleShiftOutput.qualified_shots), 0)
        ).where(
            InjectionScheduleShiftOutput.factory_id == factory_id,
            InjectionScheduleShiftOutput.schedule_line_id == line_id,
        )
    ) or Decimal("0")
    completed, remaining, percent = progress(order.order_shots, total)
    if completed > 0 and line.status in {"PENDING", "SCHEDULED"}:
        line.status = order.status = "IN_PRODUCTION"
        line.actual_started_at = line.actual_started_at or now
    if remaining <= 0:
        line.status = order.status = "COMPLETED"
        line.actual_finished_at = now
    line.version += 1
    settings.schedule_revision += 1
    line.schedule_revision = settings.schedule_revision
    line.updated_by = actor.id
    line.updated_by_name = actor.display_name
    line.updated_at = now
    order.updated_by = actor.id
    order.updated_by_name = actor.display_name
    order.updated_at = now
    order.version += 1
    after = {
        "reported_shots": str(reported_shots),
        "defect_shots": str(defect_shots),
        "version": output.version,
    }
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="SHIFT_OUTPUT_RECORDED",
        entity_type="SHIFT_OUTPUT",
        entity_id=output.id,
        entity_version=output.version,
        actor=actor,
        before=before,
        after=after,
    )
    db.commit()
    return {
        "id": output.id,
        "version": output.version,
        "qualified_shots": completed,
        "remaining_shots": remaining,
        "completion_percent": percent,
        "line_status": line.status,
        "order_status": order.status,
        "schedule_revision": settings.schedule_revision,
    }


def list_shift_outputs(
    db: Session, factory_id: str, line_id: str
) -> list[dict[str, object]]:
    _line_and_order(db, factory_id, line_id)
    return [
        {
            "id": item.id,
            "production_date": item.production_date,
            "shift": item.shift,
            "reported_shots": item.reported_shots,
            "defect_shots": item.defect_shots,
            "qualified_shots": item.qualified_shots,
            "downtime_minutes": item.downtime_minutes,
            "downtime_reason": item.downtime_reason,
            "remark": item.remark,
            "version": item.version,
        }
        for item in db.scalars(
            select(InjectionScheduleShiftOutput)
            .where(
                InjectionScheduleShiftOutput.factory_id == factory_id,
                InjectionScheduleShiftOutput.schedule_line_id == line_id,
            )
            .order_by(
                InjectionScheduleShiftOutput.production_date,
                InjectionScheduleShiftOutput.shift,
            )
        ).all()
    ]


def create_window(
    db: Session,
    *,
    factory_id: str,
    machine_id: str,
    start_at: str,
    end_at: str,
    window_type: str,
    reason: str,
    is_locked: bool,
    actor: AuthContext,
) -> dict[str, object]:
    if window_type not in WINDOW_TYPES:
        raise HTTPException(status_code=422, detail="不支持的停机窗口类型")
    if _parse_time(start_at, "start_at") >= _parse_time(end_at, "end_at"):
        raise HTTPException(status_code=422, detail="停机结束时间必须晚于开始时间")
    machine = db.scalar(
        select(InjectionScheduleMachine).where(
            InjectionScheduleMachine.id == machine_id,
            InjectionScheduleMachine.factory_id == factory_id,
        )
    )
    if machine is None:
        raise HTTPException(status_code=404, detail="机台不存在")
    now = _now_text()
    item = InjectionScheduleMachineUnavailableWindow(
        id=f"is-window-{uuid4().hex}",
        factory_id=factory_id,
        machine_id=machine_id,
        start_at=start_at,
        end_at=end_at,
        window_type=window_type,
        reason=reason.strip(),
        is_locked=is_locked,
        created_by=actor.id,
        created_by_name=actor.display_name,
        updated_by=actor.id,
        updated_by_name=actor.display_name,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="MACHINE_WINDOW_CREATED",
        entity_type="MACHINE_WINDOW",
        entity_id=item.id,
        entity_version=1,
        actor=actor,
        reason=reason,
        after={
            "machine_id": machine_id,
            "start_at": start_at,
            "end_at": end_at,
            "window_type": window_type,
        },
    )
    db.commit()
    return {
        "id": item.id,
        "version": item.version,
        "schedule_revision": settings.schedule_revision,
    }


def patch_window(
    db: Session,
    *,
    factory_id: str,
    window_id: str,
    version: int,
    start_at: str,
    end_at: str,
    window_type: str,
    reason: str,
    is_locked: bool,
    actor: AuthContext,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleMachineUnavailableWindow).where(
            InjectionScheduleMachineUnavailableWindow.id == window_id,
            InjectionScheduleMachineUnavailableWindow.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="停机窗口不存在")
    if item.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "停机窗口已更新", "latest_version": item.version},
        )
    if window_type not in WINDOW_TYPES or _parse_time(
        start_at, "start_at"
    ) >= _parse_time(end_at, "end_at"):
        raise HTTPException(status_code=422, detail="停机窗口参数不合法")
    before = {
        "start_at": item.start_at,
        "end_at": item.end_at,
        "window_type": item.window_type,
        "version": item.version,
    }
    item.start_at, item.end_at, item.window_type = start_at, end_at, window_type
    item.reason, item.is_locked = reason.strip(), is_locked
    item.version += 1
    item.updated_by, item.updated_by_name, item.updated_at = (
        actor.id,
        actor.display_name,
        _now_text(),
    )
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="MACHINE_WINDOW_UPDATED",
        entity_type="MACHINE_WINDOW",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        reason=reason,
        before=before,
        after={
            "start_at": start_at,
            "end_at": end_at,
            "window_type": window_type,
            "version": item.version,
        },
    )
    db.commit()
    return {
        "id": item.id,
        "version": item.version,
        "schedule_revision": settings.schedule_revision,
    }


def delete_window(
    db: Session,
    *,
    factory_id: str,
    window_id: str,
    version: int,
    reason: str,
    actor: AuthContext,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleMachineUnavailableWindow).where(
            InjectionScheduleMachineUnavailableWindow.id == window_id,
            InjectionScheduleMachineUnavailableWindow.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="停机窗口不存在")
    if item.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "停机窗口已更新", "latest_version": item.version},
        )
    before = {
        "machine_id": item.machine_id,
        "start_at": item.start_at,
        "end_at": item.end_at,
        "window_type": item.window_type,
        "version": item.version,
    }
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="MACHINE_WINDOW_DELETED",
        entity_type="MACHINE_WINDOW",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        reason=reason,
        before=before,
    )
    db.delete(item)
    db.commit()
    return {
        "deleted": True,
        "id": window_id,
        "schedule_revision": settings.schedule_revision,
    }
