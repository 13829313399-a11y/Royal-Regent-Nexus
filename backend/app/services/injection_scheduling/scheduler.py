from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
from app.models.injection_schedule import (
    InjectionScheduleAutoProposal,
    InjectionScheduleFactorySettings,
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleMachineUnavailableWindow,
    InjectionScheduleMold,
    InjectionScheduleOrderDemand,
    InjectionScheduleShiftOutput,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling.audit import write_audit_event
from app.services.injection_scheduling.operations import ensure_factory_settings

ALGORITHM_VERSION = "deterministic-heuristic-v1"
PRIORITY_RANK = {"EXPEDITE": 0, "URGENT": 1, "NORMAL": 2}
MATERIAL_READY = {"READY", "PREPARED", "SUFFICIENT"}


def _json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _digest(rows: list[object]) -> str:
    return hashlib.sha256(_json(rows).encode()).hexdigest()


def _parse_time(value: str, field: str) -> datetime:
    parsed = parse_business_timestamp(value)
    if parsed is None:
        raise HTTPException(status_code=422, detail=f"{field} 必须是 ISO 时间")
    return parsed


def _json_string_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def current_input_digest(db: Session, factory_id: str) -> str:
    settings = db.scalar(
        select(InjectionScheduleFactorySettings).where(
            InjectionScheduleFactorySettings.factory_id == factory_id
        )
    )
    orders = db.execute(
        select(
            InjectionScheduleOrderDemand.id,
            InjectionScheduleOrderDemand.version,
            InjectionScheduleOrderDemand.status,
        )
        .where(InjectionScheduleOrderDemand.factory_id == factory_id)
        .order_by(InjectionScheduleOrderDemand.id)
    ).all()
    lines = db.execute(
        select(
            InjectionScheduleLine.id,
            InjectionScheduleLine.version,
            InjectionScheduleLine.status,
            InjectionScheduleLine.is_locked,
        )
        .where(InjectionScheduleLine.factory_id == factory_id)
        .order_by(InjectionScheduleLine.id)
    ).all()
    machines = db.execute(
        select(
            InjectionScheduleMachine.id,
            InjectionScheduleMachine.version,
            InjectionScheduleMachine.status,
        )
        .where(InjectionScheduleMachine.factory_id == factory_id)
        .order_by(InjectionScheduleMachine.id)
    ).all()
    windows = db.execute(
        select(
            InjectionScheduleMachineUnavailableWindow.id,
            InjectionScheduleMachineUnavailableWindow.version,
        )
        .where(InjectionScheduleMachineUnavailableWindow.factory_id == factory_id)
        .order_by(InjectionScheduleMachineUnavailableWindow.id)
    ).all()
    outputs = db.execute(
        select(InjectionScheduleShiftOutput.id, InjectionScheduleShiftOutput.version)
        .where(InjectionScheduleShiftOutput.factory_id == factory_id)
        .order_by(InjectionScheduleShiftOutput.id)
    ).all()
    return _digest(
        [
            ["revision", settings.schedule_revision if settings else 1],
            ["orders", [list(row) for row in orders]],
            ["lines", [list(row) for row in lines]],
            ["machines", [list(row) for row in machines]],
            ["windows", [list(row) for row in windows]],
            ["outputs", [list(row) for row in outputs]],
        ]
    )


def _proposal_out(item: InjectionScheduleAutoProposal) -> dict[str, object]:
    return {
        "proposal_id": item.id,
        "factory_id": item.factory_id,
        "status": item.status,
        "algorithm_version": item.algorithm_version,
        "input_version_digest": item.input_version_digest,
        "summary": json.loads(item.summary_json),
        "changes": json.loads(item.changes_json),
        "unscheduled": json.loads(item.unscheduled_json),
        "expires_at": item.expires_at,
        "version": item.version,
    }


def _duration_hours(order: InjectionScheduleOrderDemand) -> Decimal:
    target = order.daily_target or Decimal("0")
    if target <= 0:
        return Decimal("0")
    hours = order.order_shots / target * Decimal("24")
    return max(hours, Decimal("0.25")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _changeover(
    previous: InjectionScheduleOrderDemand | None, current: InjectionScheduleOrderDemand
) -> tuple[Decimal, list[str]]:
    if previous is None:
        return Decimal("0"), ["机台首单"]
    hours = Decimal("0")
    reasons: list[str] = []
    if previous.mold_code != current.mold_code:
        hours += Decimal("1.5")
        reasons.append("换模")
    if previous.material_name != current.material_name:
        hours += Decimal("0.5")
        reasons.append("换料")
    if previous.color != current.color:
        previous_rank = previous.color_lightness_rank
        current_rank = current.color_lightness_rank
        if (
            previous_rank is not None
            and current_rank is not None
            and current_rank < previous_rank
        ):
            hours += Decimal("1")
            reasons.append("深转浅")
        else:
            hours += Decimal("0.5")
            reasons.append("换色")
    return hours, reasons or ["同模同料同色"]


def build_proposal(
    db: Session,
    *,
    factory_id: str,
    request_id: str,
    start_at: str,
    end_at: str,
    mode: str,
    selected_order_ids: list[str],
    affected_machine_ids: list[str],
    expected_schedule_revision: int,
    actor: AuthContext,
) -> dict[str, object]:
    if mode not in {"INCREMENTAL", "FULL"}:
        raise HTTPException(status_code=422, detail="mode 仅支持 INCREMENTAL 或 FULL")
    start = _parse_time(start_at, "start_at")
    end = _parse_time(end_at, "end_at")
    if start >= end or end - start > timedelta(days=90):
        raise HTTPException(
            status_code=422, detail="自动排程区间必须为 90 天以内的有效范围"
        )
    settings = ensure_factory_settings(db, factory_id, actor)
    if settings.schedule_revision != expected_schedule_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "排程版本已变化",
                "latest_schedule_revision": settings.schedule_revision,
            },
        )
    request_payload = {
        "factory_id": factory_id,
        "start_at": start_at,
        "end_at": end_at,
        "mode": mode,
        "selected_order_ids": sorted(selected_order_ids),
        "affected_machine_ids": sorted(affected_machine_ids),
        "expected_schedule_revision": expected_schedule_revision,
    }
    request_hash = _digest([request_payload])
    existing = db.scalar(
        select(InjectionScheduleAutoProposal).where(
            InjectionScheduleAutoProposal.factory_id == factory_id,
            InjectionScheduleAutoProposal.request_id == request_id,
        )
    )
    if existing is not None:
        if existing.request_payload_sha256 != request_hash:
            raise HTTPException(
                status_code=409, detail="request_id 已用于不同的排程请求"
            )
        return _proposal_out(existing)

    machines = db.scalars(
        select(InjectionScheduleMachine)
        .where(
            InjectionScheduleMachine.factory_id == factory_id,
            InjectionScheduleMachine.status == "AVAILABLE",
        )
        .order_by(
            InjectionScheduleMachine.display_order,
            InjectionScheduleMachine.machine_code,
        )
    ).all()
    if affected_machine_ids:
        allowed = set(affected_machine_ids)
        machines = [item for item in machines if item.id in allowed]
    molds = db.scalars(
        select(InjectionScheduleMold).where(
            InjectionScheduleMold.factory_id == factory_id,
            InjectionScheduleMold.status == "ACTIVE",
        )
    ).all()
    molds_by_key = {(item.mold_code, item.product_code): item for item in molds}
    windows_by_machine: dict[str, list[InjectionScheduleMachineUnavailableWindow]] = {
        machine.id: [] for machine in machines
    }
    for window in db.scalars(
        select(InjectionScheduleMachineUnavailableWindow).where(
            InjectionScheduleMachineUnavailableWindow.factory_id == factory_id,
            InjectionScheduleMachineUnavailableWindow.start_at < end_at,
            InjectionScheduleMachineUnavailableWindow.end_at > start_at,
        )
    ).all():
        if window.machine_id in windows_by_machine:
            windows_by_machine[window.machine_id].append(window)
    line_rows = db.execute(
        select(InjectionScheduleLine, InjectionScheduleOrderDemand)
        .join(
            InjectionScheduleOrderDemand,
            InjectionScheduleOrderDemand.id == InjectionScheduleLine.order_demand_id,
        )
        .where(
            InjectionScheduleLine.factory_id == factory_id,
            InjectionScheduleLine.status.notin_(("COMPLETED", "CANCELLED")),
        )
    ).all()
    selected = set(selected_order_ids)
    freeze_cutoff = business_now() + timedelta(hours=settings.freeze_hours)
    candidates: list[tuple[InjectionScheduleLine, InjectionScheduleOrderDemand]] = []
    unscheduled: list[dict[str, object]] = []
    for line, order in line_rows:
        if selected and order.id not in selected:
            continue
        if line.is_locked:
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "LOCKED",
                    "message": "任务已锁定，自动排程不会移动",
                }
            )
            continue
        if line.machine_id and line.planned_start_at:
            if _parse_time(line.planned_start_at, "planned_start_at") < freeze_cutoff:
                unscheduled.append(
                    {
                        "order_id": order.id,
                        "line_id": line.id,
                        "reason_code": "FROZEN_WINDOW",
                        "message": "任务位于冻结区，自动排程不会移动",
                    }
                )
                continue
        if line.machine_id and mode == "INCREMENTAL":
            continue
        if (
            order.data_completeness_status != "COMPLETE"
            or order.required_machine_a_value is None
        ):
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "MASTER_DATA_INCOMPLETE",
                    "message": "订单或模具主数据不完整",
                }
            )
            continue
        if order.material_status not in MATERIAL_READY:
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "MATERIAL_NOT_READY",
                    "message": "材料未齐套",
                }
            )
            continue
        if _duration_hours(order) <= 0:
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "DAILY_TARGET_MISSING",
                    "message": "缺少有效日产量",
                }
            )
            continue
        candidates.append((line, order))
    candidates.sort(
        key=lambda item: (
            PRIORITY_RANK.get(item[1].priority, 9),
            item[1].delivery_due_date or "9999-12-31",
            -item[1].order_shots,
            item[1].id,
        )
    )

    existing_by_machine: dict[
        str, list[tuple[InjectionScheduleLine, InjectionScheduleOrderDemand]]
    ] = {machine.id: [] for machine in machines}
    for line, order in line_rows:
        if line.machine_id in existing_by_machine and (
            line.is_locked
            or (line.machine_id and line not in [item[0] for item in candidates])
        ):
            existing_by_machine[line.machine_id].append((line, order))
    cursors: dict[str, datetime] = {}
    previous_orders: dict[str, InjectionScheduleOrderDemand | None] = {}
    load_hours = {machine.id: Decimal("0") for machine in machines}
    next_sequence: dict[str, Decimal] = {}
    for machine in machines:
        existing_lines = existing_by_machine[machine.id]
        finishes = [
            _parse_time(line.planned_finish_at, "planned_finish_at")
            for line, _ in existing_lines
            if line.planned_finish_at
        ]
        cursors[machine.id] = max([start, *finishes])
        previous_orders[machine.id] = max(
            existing_lines,
            key=lambda item: item[0].planned_finish_at or "",
            default=(None, None),
        )[1]
        next_sequence[machine.id] = max(
            [
                line.sequence_no or Decimal("0")
                for line, _ in existing_lines
                if line.sequence_no is not None
            ],
            default=Decimal("0"),
        )

    changes: list[dict[str, object]] = []
    for line, order in candidates:
        mold = molds_by_key.get((order.mold_code, order.product_code))
        compatible = [
            machine
            for machine in machines
            if machine.machine_ounce_capacity is not None
            and machine.machine_ounce_capacity >= order.required_machine_a_value
            and (
                mold is None
                or mold.min_machine_ounce is None
                or machine.machine_ounce_capacity >= mold.min_machine_ounce
            )
            and (
                mold is None
                or mold.max_machine_ounce is None
                or machine.machine_ounce_capacity <= mold.max_machine_ounce
            )
            and (
                mold is None
                or not mold.requires_core_pull
                or machine.supports_core_pull
            )
            and (
                mold is None
                or mold.required_robot_arm in {"", "UNKNOWN"}
                or machine.robot_arm_type == mold.required_robot_arm
            )
            and machine.machine_code
            not in (
                _json_string_list(mold.forbidden_machine_codes_json)
                if mold is not None
                else []
            )
        ]
        if not compatible:
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "NO_COMPATIBLE_MACHINE",
                    "message": (
                        f"没有同时满足 {order.required_machine_a_value}A、"
                        "模具和机械手约束的可用机台"
                    ),
                }
            )
            continue
        scored: list[
            tuple[tuple[object, ...], InjectionScheduleMachine, Decimal, list[str]]
        ] = []
        for machine in compatible:
            previous = previous_orders[machine.id]
            changeover, change_reasons = _changeover(previous, order)
            exact_gap = machine.machine_ounce_capacity - order.required_machine_a_value
            same_mold = 0 if previous and previous.mold_code == order.mold_code else 1
            same_material = (
                0 if previous and previous.material_name == order.material_name else 1
            )
            same_color = 0 if previous and previous.color == order.color else 1
            high_speed_penalty = (
                0
                if machine.is_high_speed and order.order_shots >= Decimal("10000")
                else 1
            )
            score = (
                exact_gap,
                same_mold,
                same_material,
                same_color,
                high_speed_penalty,
                load_hours[machine.id],
                machine.machine_code,
            )
            scored.append((score, machine, changeover, change_reasons))
        score, machine, changeover, change_reasons = min(
            scored, key=lambda item: item[0]
        )
        planned_start = cursors[machine.id] + timedelta(hours=float(changeover))
        duration = _duration_hours(order)
        planned_finish = planned_start + timedelta(hours=float(duration))
        for window in sorted(
            windows_by_machine[machine.id], key=lambda item: item.start_at
        ):
            window_start = _parse_time(window.start_at, "window.start_at")
            window_end = _parse_time(window.end_at, "window.end_at")
            if planned_start < window_end and planned_finish > window_start:
                planned_start = window_end + timedelta(hours=float(changeover))
                planned_finish = planned_start + timedelta(hours=float(duration))
        if planned_finish > end:
            unscheduled.append(
                {
                    "order_id": order.id,
                    "line_id": line.id,
                    "reason_code": "OUTSIDE_HORIZON",
                    "message": "预计完成时间超出本次排程区间",
                }
            )
            continue
        next_sequence[machine.id] += Decimal("10")
        sequence = next_sequence[machine.id]
        reasons = [f"机安差 {score[0]}A", *change_reasons]
        changes.append(
            {
                "line_id": line.id,
                "line_version": line.version,
                "order_id": order.id,
                "machine_id": machine.id,
                "machine_code": machine.machine_code,
                "sequence_no": str(sequence),
                "planned_start_at": planned_start.isoformat(timespec="seconds"),
                "planned_finish_at": planned_finish.isoformat(timespec="seconds"),
                "changeover_hours": str(changeover),
                "duration_hours": str(duration),
                "reason_codes": reasons,
            }
        )
        cursors[machine.id] = planned_finish
        previous_orders[machine.id] = order
        load_hours[machine.id] += duration + changeover

    digest = current_input_digest(db, factory_id)
    now = business_now()
    summary = {
        "scheduled_count": len(changes),
        "unscheduled_count": len(unscheduled),
        "machine_count": len({item["machine_id"] for item in changes}),
        "deterministic": True,
    }
    proposal = InjectionScheduleAutoProposal(
        id=f"is-proposal-{uuid4().hex}",
        factory_id=factory_id,
        request_id=request_id,
        request_payload_sha256=request_hash,
        input_version_digest=digest,
        algorithm_version=ALGORITHM_VERSION,
        status="PREVIEW",
        summary_json=_json(summary),
        changes_json=_json(changes),
        unscheduled_json=_json(unscheduled),
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=now.isoformat(timespec="seconds"),
        expires_at=(now + timedelta(minutes=30)).isoformat(timespec="seconds"),
    )
    db.add(proposal)
    db.commit()
    return _proposal_out(proposal)


def apply_proposal(
    db: Session,
    *,
    factory_id: str,
    proposal_id: str,
    expected_schedule_revision: int,
    reason: str,
    actor: AuthContext,
) -> dict[str, object]:
    proposal = db.scalar(
        select(InjectionScheduleAutoProposal).where(
            InjectionScheduleAutoProposal.id == proposal_id,
            InjectionScheduleAutoProposal.factory_id == factory_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="排程 proposal 不存在")
    if proposal.status == "APPLIED":
        return _proposal_out(proposal)
    if proposal.status != "PREVIEW":
        raise HTTPException(status_code=409, detail="当前 proposal 不能应用")
    if _parse_time(proposal.expires_at, "expires_at") <= business_now():
        proposal.status = "EXPIRED"
        proposal.version += 1
        db.commit()
        raise HTTPException(status_code=409, detail="排程 proposal 已过期")
    settings = ensure_factory_settings(db, factory_id, actor)
    if settings.schedule_revision != expected_schedule_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "排程版本已变化",
                "latest_schedule_revision": settings.schedule_revision,
            },
        )
    if current_input_digest(db, factory_id) != proposal.input_version_digest:
        raise HTTPException(status_code=409, detail="排程输入已变化，请重新生成预览")
    changes = json.loads(proposal.changes_json)
    now = business_now().isoformat(timespec="seconds")
    resolved: list[
        tuple[
            dict[str, object],
            InjectionScheduleLine,
            InjectionScheduleOrderDemand,
        ]
    ] = []
    for change in changes:
        line, order = db.execute(
            select(InjectionScheduleLine, InjectionScheduleOrderDemand)
            .join(
                InjectionScheduleOrderDemand,
                InjectionScheduleOrderDemand.id
                == InjectionScheduleLine.order_demand_id,
            )
            .where(
                InjectionScheduleLine.id == change["line_id"],
                InjectionScheduleLine.factory_id == factory_id,
            )
        ).one()
        if line.is_locked or line.version != change["line_version"]:
            raise HTTPException(
                status_code=409, detail="排程行已锁定或版本变化，请重新预览"
            )
        resolved.append((change, line, order))
    for _, line, _ in resolved:
        line.machine_id = None
        line.sequence_no = None
    db.flush()
    for change, line, order in resolved:
        line.machine_id = change["machine_id"]
        line.sequence_no = Decimal(change["sequence_no"])
        line.status = "SCHEDULED"
        line.planned_start_at = change["planned_start_at"]
        line.planned_finish_at = change["planned_finish_at"]
        line.suggested_changeover_hours = Decimal(change["changeover_hours"])
        line.final_changeover_hours = Decimal(change["changeover_hours"])
        line.assignment_reason_json = _json(change["reason_codes"])
        line.schedule_source = "AUTO"
        line.version += 1
        line.updated_by, line.updated_by_name, line.updated_at = (
            actor.id,
            actor.display_name,
            now,
        )
        order.status = "SCHEDULED"
        order.version += 1
        order.updated_by, order.updated_by_name, order.updated_at = (
            actor.id,
            actor.display_name,
            now,
        )
    settings.schedule_revision += 1
    for change in changes:
        line = db.get(InjectionScheduleLine, change["line_id"])
        if line:
            line.schedule_revision = settings.schedule_revision
    proposal.status = "APPLIED"
    proposal.applied_by = actor.id
    proposal.applied_at = now
    proposal.version += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="AUTO_PROPOSAL_APPLIED",
        entity_type="AUTO_PROPOSAL",
        entity_id=proposal.id,
        entity_version=proposal.version,
        actor=actor,
        reason=reason,
        after={
            "schedule_revision": settings.schedule_revision,
            "changes": len(changes),
        },
    )
    db.commit()
    return _proposal_out(proposal)


def reject_proposal(
    db: Session, *, factory_id: str, proposal_id: str, reason: str, actor: AuthContext
) -> dict[str, object]:
    proposal = db.scalar(
        select(InjectionScheduleAutoProposal).where(
            InjectionScheduleAutoProposal.id == proposal_id,
            InjectionScheduleAutoProposal.factory_id == factory_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="排程 proposal 不存在")
    if proposal.status == "APPLIED":
        raise HTTPException(status_code=409, detail="已应用的 proposal 不能拒绝")
    proposal.status = "REJECTED"
    proposal.version += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="AUTO_PROPOSAL_REJECTED",
        entity_type="AUTO_PROPOSAL",
        entity_id=proposal.id,
        entity_version=proposal.version,
        actor=actor,
        reason=reason,
    )
    db.commit()
    return _proposal_out(proposal)
