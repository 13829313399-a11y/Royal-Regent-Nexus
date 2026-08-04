from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_scheduler import (
    InjectionSchedulingMachineCalendar,
    InjectionSchedulingRun,
    InjectionSchedulingRunAssignment,
    InjectionSchedulingTransitionRule,
)
from app.schemas.injection_scheduling_scheduler import (
    InjectionSchedulingRunApply,
    InjectionSchedulingRunApplyOut,
    InjectionSchedulingRunAssignmentOut,
    InjectionSchedulingRunCreate,
    InjectionSchedulingRunOut,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import (
    DEFAULT_RULE_CONFIG,
    current_rule_set,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_execution import (
    _audit,
    _delivery_slack_days,
    _record_plan_revision,
    _remaining_shifts,
    _validate_proposed_task_windows,
    plan_out,
)
from app.services.injection_scheduling_scheduler.cp_sat import (
    CpSatUnavailableError,
    solve_cp_sat,
)
from app.services.injection_scheduling_scheduler.duration import default_shift_target
from app.services.injection_scheduling_scheduler.eligibility import (
    evaluate_batch_matches,
)
from app.services.injection_scheduling_scheduler.heuristic import solve_heuristic
from app.services.injection_scheduling_scheduler.normalization import (
    as_business_datetime,
    load_json,
)


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def assignment_out(
    record: InjectionSchedulingRunAssignment,
) -> InjectionSchedulingRunAssignmentOut:
    return InjectionSchedulingRunAssignmentOut(
        id=record.id,
        order_id=record.order_id,
        existing_task_id=record.existing_task_id,
        mold_id=record.mold_id,
        mold_copy_no=record.mold_copy_no,
        machine_id=record.machine_id,
        sequence_no=record.sequence_no,
        planned_start=record.planned_start,
        planned_finish=record.planned_finish,
        setup_minutes=record.setup_minutes,
        production_minutes=record.production_minutes,
        planned_downtime_minutes=record.planned_downtime_minutes,
        changeover_type=record.changeover_type,
        decision=record.decision,
        score=float(record.score) if record.score is not None else None,
        explanation=load_json(record.explanation_json, {}),
        unassigned_reason_code=record.unassigned_reason_code,
    )


def run_out(db: Session, record: InjectionSchedulingRun) -> InjectionSchedulingRunOut:
    assignments = list(
        db.scalars(
            select(InjectionSchedulingRunAssignment)
            .where(
                InjectionSchedulingRunAssignment.factory_id == record.factory_id,
                InjectionSchedulingRunAssignment.run_id == record.id,
            )
            .order_by(
                InjectionSchedulingRunAssignment.decision,
                InjectionSchedulingRunAssignment.machine_id,
                InjectionSchedulingRunAssignment.sequence_no,
                InjectionSchedulingRunAssignment.order_id,
            )
        ).all()
    )
    return InjectionSchedulingRunOut(
        id=record.id,
        factory_id=record.factory_id,
        plan_id=record.plan_id,
        expected_plan_revision=record.expected_plan_revision,
        rule_set_id=record.rule_set_id,
        rule_revision=record.rule_revision,
        mode="PREVIEW",
        solver_type=record.solver_type,
        solver_version=record.solver_version,
        requested_solver=record.requested_solver,
        solver_status=record.solver_status,
        fallback_used=record.fallback_used,
        fallback_reason=record.fallback_reason,
        scenario_group_id=record.scenario_group_id,
        scenario_name=record.scenario_name,
        alternative_no=record.alternative_no,
        replay_of_run_id=record.replay_of_run_id,
        status=record.status,
        horizon_start=record.horizon_start,
        horizon_end=record.horizon_end,
        objective_config=load_json(record.objective_config_json, {}),
        summary=load_json(record.summary_json, {}),
        error_detail=record.error_detail,
        started_at=record.started_at,
        finished_at=record.finished_at,
        applied_at=record.applied_at,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        applied_by=record.applied_by,
        applied_by_name=record.applied_by_name,
        created_at=record.created_at,
        revision=record.revision,
        assignments=[assignment_out(item) for item in assignments],
    )


def _require_plan(
    db: Session, factory_id: str, plan_id: str
) -> InjectionSchedulingPlan:
    record = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.id == plan_id,
            InjectionSchedulingPlan.factory_id == factory_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="计划草案不存在")
    return record


def _require_run(db: Session, factory_id: str, run_id: str) -> InjectionSchedulingRun:
    record = db.scalar(
        select(InjectionSchedulingRun).where(
            InjectionSchedulingRun.id == run_id,
            InjectionSchedulingRun.factory_id == factory_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="自动排期运行不存在")
    return record


def _selected_orders(
    db: Session,
    *,
    factory_id: str,
    plan_tasks: list[InjectionSchedulingTask],
    requested_order_ids: list[str],
) -> list[InjectionSchedulingOrder]:
    if requested_order_ids:
        order_ids = requested_order_ids
    else:
        backlog_ids = list(
            db.scalars(
                select(InjectionSchedulingOrder.id)
                .where(
                    InjectionSchedulingOrder.factory_id == factory_id,
                    InjectionSchedulingOrder.status == "BACKLOG",
                )
                .order_by(
                    InjectionSchedulingOrder.delivery_due_date,
                    InjectionSchedulingOrder.id,
                )
            ).all()
        )
        movable_ids = [
            item.order_id
            for item in plan_tasks
            if not item.locked
            and not item.active_execution
            and item.execution_status not in {"RUNNING", "COMPLETED", "CANCELLED"}
        ]
        order_ids = list(dict.fromkeys((*backlog_ids, *movable_ids)))
    if not order_ids:
        raise HTTPException(status_code=409, detail="当前草案没有可自动安排的订单")
    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.id.in_(order_ids),
            )
        ).all()
    )
    found = {item.id for item in orders}
    if len(found) != len(order_ids):
        raise HTTPException(
            status_code=404,
            detail={
                "message": "部分订单不存在或不属于当前厂区",
                "order_ids": [item for item in order_ids if item not in found],
            },
        )
    invalid = [item.id for item in orders if item.status in {"COMPLETED", "CANCELLED"}]
    if invalid:
        raise HTTPException(
            status_code=409,
            detail={"message": "已完成或已取消订单不可排期", "order_ids": invalid},
        )
    order_by_id = {item.id: item for item in orders}
    return [order_by_id[item] for item in order_ids]


def create_run(
    db: Session,
    payload: InjectionSchedulingRunCreate,
    user: AuthContext,
    request_id: str,
) -> InjectionSchedulingRun:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    if payload.plan_id != payload.plan_id.strip():
        raise HTTPException(status_code=422, detail="计划 ID 不合法")
    request_payload = payload.model_dump(mode="json")
    payload_hash = _hash(request_payload)
    replay = db.scalar(
        select(InjectionSchedulingRun).where(
            InjectionSchedulingRun.factory_id == factory_id,
            InjectionSchedulingRun.request_id == request_id,
        )
    )
    if replay is not None:
        if replay.payload_hash != payload_hash:
            raise HTTPException(
                status_code=409, detail="相同 request_id 已用于不同自动排期请求"
            )
        return replay
    plan = _require_plan(db, factory_id, payload.plan_id)
    if plan.status != "DRAFT":
        raise HTTPException(
            status_code=409, detail="自动排期只能基于计划草案预览，不能覆盖已发布计划"
        )
    if plan.revision != payload.expected_plan_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "计划草案已更新，请重新生成预览",
                "expected_revision": payload.expected_plan_revision,
                "current_revision": plan.revision,
            },
        )
    rules = current_rule_set(db, factory_id)
    if rules.revision != payload.rule_revision or plan.rule_revision != rules.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "规则 revision 与计划不一致",
                "expected_rule_revision": payload.rule_revision,
                "current_rule_revision": rules.revision,
                "plan_rule_revision": plan.rule_revision,
            },
        )

    horizon_start = as_business_datetime(payload.horizon_start)
    horizon_end = as_business_datetime(payload.horizon_end)
    timestamp = _now()
    run_id = f"isrun-{uuid4().hex}"
    scenario_group_id = payload.scenario_group_id or f"isscenario-{uuid4().hex}"
    if payload.replay_of_run_id:
        _require_run(db, factory_id, payload.replay_of_run_id)
    record = InjectionSchedulingRun(
        id=run_id,
        factory_id=factory_id,
        plan_id=plan.id,
        expected_plan_revision=plan.revision,
        rule_set_id=rules.id,
        rule_revision=rules.revision,
        mode="PREVIEW",
        solver_type="HEURISTIC",
        solver_version="phase4-cp-sat-v1"
        if payload.solver in {"CP_SAT", "AUTO"}
        else "phase3-v1",
        requested_solver=payload.solver,
        solver_status="NOT_RUN",
        fallback_used=False,
        fallback_reason="",
        scenario_group_id=scenario_group_id,
        scenario_name=payload.scenario_name,
        alternative_no=payload.alternative_no,
        replay_of_run_id=payload.replay_of_run_id,
        status="CREATED",
        horizon_start=horizon_start.isoformat(timespec="seconds"),
        horizon_end=horizon_end.isoformat(timespec="seconds"),
        input_snapshot_json="{}",
        objective_config_json="{}",
        summary_json="{}",
        request_id=request_id,
        payload_hash=payload_hash,
        error_detail="",
        started_at=timestamp,
        finished_at="",
        applied_at="",
        created_by=user.id,
        created_by_name=_actor_name(user),
        applied_by="",
        applied_by_name="",
        created_at=timestamp,
        revision=1,
    )
    db.add(record)
    db.flush()
    db.commit()
    record = _require_run(db, factory_id, record.id)
    try:
        record.status = "VALIDATING"
        plan_tasks = list(
            db.scalars(
                select(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == plan.id,
                    InjectionSchedulingTask.execution_status.notin_(
                        ("COMPLETED", "CANCELLED")
                    ),
                )
                .order_by(
                    InjectionSchedulingTask.machine_id,
                    InjectionSchedulingTask.sequence_no,
                )
            ).all()
        )
        orders = _selected_orders(
            db,
            factory_id=factory_id,
            plan_tasks=plan_tasks,
            requested_order_ids=payload.order_ids,
        )
        machines = list(
            db.scalars(
                select(InjectionSchedulingMachine)
                .where(InjectionSchedulingMachine.factory_id == factory_id)
                .order_by(InjectionSchedulingMachine.machine_code)
            ).all()
        )
        if not machines:
            raise HTTPException(status_code=409, detail="当前厂区没有机台资料")
        all_mold_ids = {item.mold_id for item in orders if item.mold_id} | {
            item.mold_id for item in plan_tasks if item.mold_id
        }
        molds = (
            {
                item.id: item
                for item in db.scalars(
                    select(InjectionSchedulingMold).where(
                        InjectionSchedulingMold.factory_id == factory_id,
                        InjectionSchedulingMold.id.in_(all_mold_ids),
                    )
                ).all()
            }
            if all_mold_ids
            else {}
        )
        calendars = list(
            db.scalars(
                select(InjectionSchedulingMachineCalendar).where(
                    InjectionSchedulingMachineCalendar.factory_id == factory_id,
                    InjectionSchedulingMachineCalendar.window_end
                    > record.horizon_start,
                    InjectionSchedulingMachineCalendar.window_start
                    < record.horizon_end,
                )
            ).all()
        )
        transition_rules = list(
            db.scalars(
                select(InjectionSchedulingTransitionRule)
                .where(
                    InjectionSchedulingTransitionRule.factory_id == factory_id,
                    InjectionSchedulingTransitionRule.active.is_(True),
                )
                .order_by(InjectionSchedulingTransitionRule.revision.desc())
            ).all()
        )
        record.status = "GENERATING_CANDIDATES"
        matches = evaluate_batch_matches(
            db,
            factory_id=factory_id,
            order_ids=[item.id for item in orders],
            machine_ids=[],
            expected_rule_revision=rules.revision,
        )
        rule_config = {**DEFAULT_RULE_CONFIG, **load_json(rules.config_json, {})}
        objective_config = {
            **rule_config,
            "default_units_per_hour": 40,
            "mold_change_minutes": 30,
            "material_change_minutes": 20,
            "color_change_minutes": 10,
            "dark_to_light_minutes": 60,
            **payload.objective_weights.model_dump(mode="json"),
            "transition_rules": [
                {
                    "from_material_group": item.from_material_group,
                    "from_color_rank": item.from_color_rank,
                    "to_material_group": item.to_material_group,
                    "to_color_rank": item.to_color_rank,
                    "mold_change_minutes": item.mold_change_minutes,
                    "color_change_minutes": item.color_change_minutes,
                    "material_change_minutes": item.material_change_minutes,
                    "fixture_change_minutes": item.fixture_change_minutes,
                    "revision": item.revision,
                }
                for item in transition_rules
            ],
        }
        snapshot = {
            "schema_version": "phase4-v1",
            "factory_id": factory_id,
            "plan": {"id": plan.id, "revision": plan.revision, "status": plan.status},
            "rule": {"id": rules.id, "revision": rules.revision},
            "orders": [
                {
                    "id": item.id,
                    "revision": item.revision,
                    "status": item.status,
                    "material_readiness_status": item.material_readiness_status,
                    "mold_id": item.mold_id,
                }
                for item in orders
            ],
            "machines": [
                {"id": item.id, "revision": item.revision, "status": item.status}
                for item in machines
            ],
            "molds": [
                {
                    "id": item.id,
                    "revision": item.revision,
                    "status": item.status,
                    "copy_count": item.copy_count,
                }
                for item in molds.values()
            ],
            "tasks": [
                {
                    "id": item.id,
                    "revision": item.revision,
                    "machine_id": item.machine_id,
                    "mold_id": item.mold_id,
                    "mold_copy_no": item.mold_copy_no,
                    "sequence_no": item.sequence_no,
                    "planned_start": item.planned_start,
                    "planned_finish": item.planned_finish,
                    "locked": item.locked,
                    "active_execution": item.active_execution,
                    "execution_status": item.execution_status,
                }
                for item in plan_tasks
            ],
        }
        record.input_snapshot_json = _json(snapshot)
        record.objective_config_json = _json(objective_config)
        record.status = "SOLVING"
        solver_arguments = {
            "orders": orders,
            "machines": machines,
            "molds": molds,
            "plan_tasks": plan_tasks,
            "matches": matches,
            "calendars": calendars,
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
            "objective_config": objective_config,
            "time_limit_seconds": payload.time_limit_seconds,
        }
        fallback_reason = ""
        if payload.solver == "HEURISTIC":
            result = solve_heuristic(**solver_arguments)
            record.solver_type = "HEURISTIC"
            record.solver_version = "phase3-v1"
            record.solver_status = "HEURISTIC"
        else:
            try:
                result = solve_cp_sat(**solver_arguments)
                record.solver_type = "CP_SAT"
                record.solver_status = str(
                    result.summary.get("solver_status", "FEASIBLE")
                )
                if record.solver_status == "TIME_LIMIT":
                    fallback_reason = "CP-SAT 在时间限制内未找到可行解"
            except CpSatUnavailableError as exc:
                record.solver_status = "UNAVAILABLE"
                fallback_reason = str(exc)
            if fallback_reason:
                result = solve_heuristic(**solver_arguments)
                record.solver_type = "HEURISTIC"
                record.fallback_used = True
                record.fallback_reason = fallback_reason[:2000]
        summary = {
            **result.summary,
            "requested_solver": payload.solver,
            "actual_solver": record.solver_type,
            "solver_status": record.solver_status,
            "fallback_used": record.fallback_used,
            "fallback_reason": record.fallback_reason,
            "scenario_group_id": scenario_group_id,
            "scenario_name": payload.scenario_name,
            "alternative_no": payload.alternative_no,
        }
        for item in result.assignments:
            db.add(
                InjectionSchedulingRunAssignment(
                    id=f"isassignment-{uuid4().hex}",
                    factory_id=factory_id,
                    run_id=record.id,
                    order_id=item["order_id"],
                    existing_task_id=item["existing_task_id"],
                    mold_id=item["mold_id"],
                    mold_copy_no=item["mold_copy_no"],
                    machine_id=item["machine_id"],
                    sequence_no=item["sequence_no"],
                    planned_start=item["planned_start"],
                    planned_finish=item["planned_finish"],
                    setup_minutes=item["setup_minutes"],
                    production_minutes=item["production_minutes"],
                    planned_downtime_minutes=item["planned_downtime_minutes"],
                    changeover_type=item["changeover_type"],
                    decision=item["decision"],
                    score=Decimal(str(item["score"]))
                    if item["score"] is not None
                    else None,
                    explanation_json=_json(item["explanation"]),
                    unassigned_reason_code=item["unassigned_reason_code"],
                    created_at=timestamp,
                )
            )
        record.summary_json = _json(summary)
        record.status = (
            "SUCCEEDED"
            if not result.summary["review_count"]
            and not result.summary["unassigned_count"]
            else "PARTIAL"
        )
        record.finished_at = _now()
        _audit(
            db,
            factory_id=factory_id,
            event_type="auto_schedule_preview_created",
            entity_type="auto_schedule_run",
            entity_id=record.id,
            entity_revision=record.revision,
            request_id=request_id,
            detail={
                "plan_id": plan.id,
                "plan_revision": plan.revision,
                "run_status": record.status,
                "summary": summary,
            },
            user=user,
        )
        db.commit()
    except TimeoutError as exc:
        record.status = "CANCELLED"
        record.error_detail = str(exc)
        record.finished_at = _now()
        db.commit()
    except HTTPException as exc:
        db.rollback()
        failed = _require_run(db, factory_id, record.id)
        failed.status = "FAILED"
        failed.error_detail = str(exc.detail)[:2000]
        failed.finished_at = _now()
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        failed = db.scalar(
            select(InjectionSchedulingRun).where(InjectionSchedulingRun.id == record.id)
        )
        if failed is not None:
            failed.status = "FAILED"
            failed.error_detail = str(exc)[:2000]
            failed.finished_at = _now()
            db.commit()
        raise
    return _require_run(db, factory_id, record.id)


def get_run(db: Session, factory_id: str, run_id: str) -> InjectionSchedulingRun:
    return _require_run(db, require_injection_scheduling_factory(factory_id), run_id)


def list_runs(
    db: Session, factory_id: str, limit: int = 50
) -> list[InjectionSchedulingRun]:
    factory_id = require_injection_scheduling_factory(factory_id)
    return list(
        db.scalars(
            select(InjectionSchedulingRun)
            .where(InjectionSchedulingRun.factory_id == factory_id)
            .order_by(
                InjectionSchedulingRun.created_at.desc(),
                InjectionSchedulingRun.id.desc(),
            )
            .limit(limit)
        ).all()
    )


def _validate_snapshot(db: Session, run: InjectionSchedulingRun) -> None:
    snapshot = load_json(run.input_snapshot_json, {})
    conflicts: list[dict[str, Any]] = []
    for model, key, fields in (
        (InjectionSchedulingMachine, "machines", ("revision", "status")),
        (InjectionSchedulingMold, "molds", ("revision", "status", "copy_count")),
        (
            InjectionSchedulingTask,
            "tasks",
            (
                "revision",
                "machine_id",
                "mold_id",
                "mold_copy_no",
                "sequence_no",
                "planned_start",
                "planned_finish",
                "locked",
                "active_execution",
                "execution_status",
            ),
        ),
    ):
        for expected in snapshot.get(key, []):
            current = db.get(model, expected["id"])
            if current is None or current.factory_id != run.factory_id:
                conflicts.append(
                    {"entity": key, "id": expected["id"], "reason": "missing"}
                )
                continue
            changed = {
                field: {
                    "expected": expected.get(field),
                    "current": getattr(current, field),
                }
                for field in fields
                if expected.get(field) != getattr(current, field)
            }
            if changed:
                conflicts.append(
                    {"entity": key, "id": expected["id"], "changes": changed}
                )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "预览输入已变化，请重新生成自动排期",
                "conflicts": conflicts[:50],
            },
        )


def apply_run(
    db: Session,
    run_id: str,
    payload: InjectionSchedulingRunApply,
    user: AuthContext,
    *,
    can_override_review: bool,
) -> InjectionSchedulingRunApplyOut:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    request_hash = _hash(payload.model_dump(mode="json") | {"run_id": run_id})
    replay = db.scalar(
        select(InjectionSchedulingAuditEvent).where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.event_type == "auto_schedule_run_applied",
            InjectionSchedulingAuditEvent.request_id == payload.request_id,
        )
    )
    if replay is not None:
        detail = load_json(replay.detail_json, {})
        if detail.get("payload_hash") != request_hash or replay.entity_id != run_id:
            raise HTTPException(
                status_code=409, detail="相同 request_id 已用于不同应用请求"
            )
        run = _require_run(db, factory_id, run_id)
        plan = _require_plan(db, factory_id, run.plan_id)
        return InjectionSchedulingRunApplyOut(
            run=run_out(db, run),
            plan=plan_out(db, plan),
            audit_sequence=replay.sequence,
            idempotent_replay=True,
        )

    run = _require_run(db, factory_id, run_id)
    if run.status not in {"SUCCEEDED", "PARTIAL"}:
        raise HTTPException(status_code=409, detail=f"状态 {run.status} 的运行不可应用")
    plan = _require_plan(db, factory_id, run.plan_id)
    if plan.status != "DRAFT":
        raise HTTPException(status_code=409, detail="自动方案不能覆盖已发布计划")
    if (
        plan.revision != payload.expected_plan_revision
        or plan.revision != run.expected_plan_revision
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "计划 revision 已变化，请重新生成预览",
                "expected_revision": run.expected_plan_revision,
                "current_revision": plan.revision,
            },
        )
    rules = current_rule_set(db, factory_id)
    if (
        rules.revision != payload.expected_rule_revision
        or rules.revision != run.rule_revision
        or plan.rule_revision != rules.revision
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "规则 revision 已变化，请重新生成预览",
                "expected_rule_revision": run.rule_revision,
                "current_rule_revision": rules.revision,
            },
        )
    _validate_snapshot(db, run)
    assignments = list(
        db.scalars(
            select(InjectionSchedulingRunAssignment).where(
                InjectionSchedulingRunAssignment.factory_id == factory_id,
                InjectionSchedulingRunAssignment.run_id == run.id,
                InjectionSchedulingRunAssignment.decision.in_(
                    ("PASS", "REVIEW_REQUIRED")
                ),
            )
        ).all()
    )
    review_assignments = [
        item for item in assignments if item.decision == "REVIEW_REQUIRED"
    ]
    if review_assignments and not can_override_review:
        raise HTTPException(
            status_code=403, detail="方案含待复核安排，需要发布/覆盖权限"
        )
    if review_assignments and not payload.review_override_reason:
        raise HTTPException(
            status_code=409, detail="方案含待复核安排，应用时必须填写人工覆盖原因"
        )
    if not assignments:
        raise HTTPException(status_code=409, detail="当前预览没有可应用的安排")
    reevaluated = evaluate_batch_matches(
        db,
        factory_id=factory_id,
        order_ids=[item.order_id for item in assignments],
        machine_ids=[],
        expected_rule_revision=run.rule_revision,
    )
    decisions = {
        (item.order_id, result.machine_id): result.decision
        for item in reevaluated.evaluations
        for result in item.results
    }
    failures = [
        item.id
        for item in assignments
        if decisions.get((item.order_id, item.machine_id)) == "FAIL"
    ]
    if failures:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "应用前硬约束复核失败，请重新生成预览",
                "assignment_ids": failures,
            },
        )

    current_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
        ).all()
    )
    task_by_id = {item.id: item for item in current_tasks}
    placements = [
        {
            "id": item.id,
            "machine_id": item.machine_id,
            "sequence_no": item.sequence_no,
            "planned_start": item.planned_start,
            "planned_finish": item.planned_finish,
            "mold_id": item.mold_id,
            "mold_copy_no": item.mold_copy_no,
        }
        for item in current_tasks
        if item.id
        not in {
            assignment.existing_task_id
            for assignment in assignments
            if assignment.existing_task_id
        }
    ]
    placements.extend(
        {
            "id": item.existing_task_id or item.id,
            "machine_id": item.machine_id,
            "sequence_no": item.sequence_no,
            "planned_start": item.planned_start,
            "planned_finish": item.planned_finish,
            "mold_id": item.mold_id,
            "mold_copy_no": item.mold_copy_no,
        }
        for item in assignments
    )
    _validate_proposed_task_windows(placements)
    timestamp = _now()
    try:
        existing_targets = [
            task_by_id[item.existing_task_id]
            for item in assignments
            if item.existing_task_id
        ]
        temp_base = (
            max((item.sequence_no for item in current_tasks), default=0)
            + len(current_tasks)
            + 1000
        )
        for index, task in enumerate(existing_targets):
            if (
                task.locked
                or task.active_execution
                or task.execution_status == "RUNNING"
            ):
                raise HTTPException(
                    status_code=409, detail="运行中或已锁定任务不能由自动方案移动"
                )
            temp_result = db.execute(
                update(InjectionSchedulingTask)
                .where(
                    InjectionSchedulingTask.id == task.id,
                    InjectionSchedulingTask.revision == task.revision,
                )
                .values(sequence_no=temp_base + index)
            )
            if temp_result.rowcount != 1:
                raise HTTPException(status_code=409, detail="排产任务 revision 已变化")
        db.flush()
        affected_order_ids: set[str] = set()
        for assignment in assignments:
            affected_order_ids.add(assignment.order_id)
            explanation = assignment.explanation_json
            if assignment.existing_task_id:
                task = task_by_id[assignment.existing_task_id]
                values = {
                    "machine_id": assignment.machine_id,
                    "mold_id": assignment.mold_id,
                    "mold_copy_no": assignment.mold_copy_no,
                    "sequence_no": assignment.sequence_no,
                    "planned_start": assignment.planned_start,
                    "planned_finish": assignment.planned_finish,
                    "estimated_start": assignment.planned_start,
                    "estimated_finish": assignment.planned_finish,
                    "setup_minutes": assignment.setup_minutes,
                    "production_minutes": assignment.production_minutes,
                    "planned_downtime_minutes": assignment.planned_downtime_minutes,
                    "changeover_type": assignment.changeover_type,
                    "auto_schedule_run_id": run.id,
                    "auto_score": assignment.score,
                    "auto_explanation_json": explanation,
                    "manual_adjusted": False,
                    "manual_override_reason": payload.review_override_reason
                    if assignment.decision == "REVIEW_REQUIRED"
                    else "",
                    "delivery_slack_days": _delivery_slack_days(
                        db.get(
                            InjectionSchedulingOrder, assignment.order_id
                        ).delivery_due_date,
                        assignment.planned_finish,
                    ),
                    "revision": task.revision + 1,
                    "updated_by": user.id,
                    "updated_by_name": _actor_name(user),
                    "updated_at": timestamp,
                }
                result = db.execute(
                    update(InjectionSchedulingTask)
                    .where(
                        InjectionSchedulingTask.id == task.id,
                        InjectionSchedulingTask.revision == task.revision,
                    )
                    .values(**values)
                )
                if result.rowcount != 1:
                    raise HTTPException(
                        status_code=409, detail="排产任务 revision 已变化"
                    )
            else:
                order = db.get(InjectionSchedulingOrder, assignment.order_id)
                task = InjectionSchedulingTask(
                    id=f"istask-{uuid4().hex}",
                    factory_id=factory_id,
                    plan_id=plan.id,
                    machine_id=assignment.machine_id or "",
                    order_id=assignment.order_id,
                    mold_id=assignment.mold_id,
                    mold_copy_no=assignment.mold_copy_no,
                    sequence_no=assignment.sequence_no or 0,
                    execution_status="QUEUED",
                    planned_start=assignment.planned_start,
                    planned_finish=assignment.planned_finish,
                    shift_target_quantity=default_shift_target(order),
                    reported_quantity=Decimal(0),
                    estimated_start=assignment.planned_start,
                    estimated_finish=assignment.planned_finish,
                    estimated_remaining_shifts=_remaining_shifts(
                        order, default_shift_target(order)
                    ),
                    delivery_slack_days=_delivery_slack_days(
                        order.delivery_due_date, assignment.planned_finish
                    ),
                    locked=False,
                    manual_override_reason=payload.review_override_reason
                    if assignment.decision == "REVIEW_REQUIRED"
                    else "",
                    active_execution=False,
                    import_batch_id=None,
                    source_sheet_name="",
                    source_row=None,
                    source_file_hash="",
                    setup_minutes=assignment.setup_minutes,
                    production_minutes=assignment.production_minutes,
                    planned_downtime_minutes=assignment.planned_downtime_minutes,
                    changeover_type=assignment.changeover_type,
                    auto_schedule_run_id=run.id,
                    auto_score=assignment.score,
                    auto_explanation_json=explanation,
                    manual_adjusted=False,
                    revision=1,
                    created_by=user.id,
                    created_by_name=_actor_name(user),
                    updated_by=user.id,
                    updated_by_name=_actor_name(user),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(task)
        for order_id in affected_order_ids:
            order = db.get(InjectionSchedulingOrder, order_id)
            if order.status == "BACKLOG":
                order.status = "SCHEDULED"
                order.revision += 1
                order.updated_by = user.id
                order.updated_by_name = _actor_name(user)
                order.updated_at = timestamp
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
            raise HTTPException(status_code=409, detail="计划 revision 已变化")
        run.status = "APPLIED"
        run.applied_at = timestamp
        run.applied_by = user.id
        run.applied_by_name = _actor_name(user)
        run.revision += 1
        db.flush()
        refreshed_plan = _require_plan(db, factory_id, plan.id)
        _record_plan_revision(db, plan=refreshed_plan, user=user, timestamp=timestamp)
        audit = _audit(
            db,
            factory_id=factory_id,
            event_type="auto_schedule_run_applied",
            entity_type="auto_schedule_run",
            entity_id=run.id,
            entity_revision=run.revision,
            request_id=payload.request_id,
            detail={
                "payload_hash": request_hash,
                "plan_id": plan.id,
                "plan_revision": payload.expected_plan_revision + 1,
                "assignment_count": len(assignments),
                "task_ids": [item.existing_task_id or item.id for item in assignments],
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
            status_code=409, detail="应用自动方案违反机台序号或时间约束"
        ) from exc
    return InjectionSchedulingRunApplyOut(
        run=run_out(db, _require_run(db, factory_id, run.id)),
        plan=plan_out(db, _require_plan(db, factory_id, plan.id)),
        audit_sequence=audit.sequence,
    )
