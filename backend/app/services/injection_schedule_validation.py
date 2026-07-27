from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import parse_business_timestamp
from app.models.injection_schedule import (
    InjectionMachineMaster,
    InjectionMoldMaster,
    InjectionOrderMaster,
    InjectionScheduleRuleConfig,
    InjectionScheduleTask,
    InjectionScheduleValidationItem,
    InjectionScheduleValidationRun,
    InjectionScheduleVersion,
)
from app.services.auth import AuthContext
from app.services.injection_schedule_excel import canonical_json, normalize_key
from app.services.injection_schedule_import import (
    add_audit_event,
    json_list,
    json_object,
    now_text,
)
from app.services.injection_schedule_rules import (
    calculate_transition_setup,
    normalize_rule_config,
)


TONNAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:T|吨)", re.IGNORECASE)


def build_version_data_hash(
    db: Session,
    version: InjectionScheduleVersion,
) -> str:
    tasks = db.scalars(
        select(InjectionScheduleTask)
        .where(
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
        )
        .order_by(
            InjectionScheduleTask.machine_id,
            InjectionScheduleTask.sequence_no,
            InjectionScheduleTask.id,
        )
    ).all()
    payload = {
        "version": {
            "id": version.id,
            "plan_base_at": version.plan_base_at,
            "rules_snapshot": json_object(version.rules_snapshot_json),
            "rule_config_revision": version.rule_config_revision,
        },
        "tasks": [
            {
                "id": item.id,
                "order_id": item.order_id,
                "machine_id": item.machine_id,
                "mold_id": item.mold_id,
                "sequence_no": item.sequence_no,
                "planned_qty": item.planned_qty,
                "planned_start_at": item.planned_start_at,
                "planned_finish_at": item.planned_finish_at,
                "setup_hours": item.setup_hours,
                "duration_hours": item.duration_hours,
                "locked": bool(item.locked),
                "revision": item.revision,
                "order_revision_snapshot": item.order_revision_snapshot,
                "machine_revision_snapshot": item.machine_revision_snapshot,
                "mold_revision_snapshot": item.mold_revision_snapshot,
                "order_no_snapshot": item.order_no_snapshot,
                "product_code_snapshot": item.product_code_snapshot,
                "product_name_snapshot": item.product_name_snapshot,
                "delivery_due_date_snapshot": item.delivery_due_date_snapshot,
                "mold_code_snapshot": item.mold_code_snapshot,
                "color_snapshot": item.color_snapshot,
                "color_rank_snapshot": item.color_rank_snapshot,
                "material_snapshot": item.material_snapshot,
                "machine_code_snapshot": item.machine_code_snapshot,
                "source": item.source,
                "recommendation_score": item.recommendation_score,
                "score_breakdown": json_list(item.score_breakdown_json),
                "constraint_snapshot": json_list(
                    item.constraint_snapshot_json
                ),
                "recommendation_context_hash": (
                    item.recommendation_context_hash
                ),
                "risk_level": item.risk_level,
                "risk_reasons": json_list(item.risk_reasons_json),
            }
            for item in tasks
        ],
    }
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def validate_version(
    db: Session,
    version: InjectionScheduleVersion,
    actor: AuthContext,
    *,
    persist: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
            .order_by(
                InjectionScheduleTask.machine_id,
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    order_ids = {task.order_id for task in tasks}
    machine_ids = {task.machine_id for task in tasks}
    mold_ids = {task.mold_id for task in tasks if task.mold_id}
    orders = {
        item.id: item
        for item in db.scalars(
            select(InjectionOrderMaster).where(
                InjectionOrderMaster.factory_id == version.factory_id,
                InjectionOrderMaster.id.in_(order_ids),
            )
        ).all()
    } if order_ids else {}
    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(machine_ids),
            )
        ).all()
    } if machine_ids else {}
    molds = {
        item.id: item
        for item in db.scalars(
            select(InjectionMoldMaster).where(
                InjectionMoldMaster.factory_id == version.factory_id,
                InjectionMoldMaster.id.in_(mold_ids),
            )
        ).all()
    } if mold_ids else {}
    config = normalize_rule_config(json_object(version.rules_snapshot_json))
    safety_factor = float(config.get("shot_safety_factor") or 0.85)
    planned_by_order: Counter[str] = Counter()
    for task in tasks:
        if task.execution_status not in {"completed", "cancelled"}:
            planned_by_order[task.order_id] += task.planned_qty

    results: list[dict[str, Any]] = []
    if not tasks:
        results.append(
            validation_result(
                "",
                "schedule_has_tasks",
                "fail",
                "草稿没有排程任务，不能发布。",
            )
        )
    tasks_by_machine: dict[str, list[InjectionScheduleTask]] = defaultdict(list)
    for task in tasks:
        tasks_by_machine[task.machine_id].append(task)
        order = orders.get(task.order_id)
        machine = machines.get(task.machine_id)
        mold = molds.get(task.mold_id) if task.mold_id else None

        if order is None:
            results.append(
                validation_result(
                    task.id,
                    "order_exists",
                    "fail",
                    "订单不存在或不属于当前厂区。",
                )
            )
            continue
        results.append(validation_result(task.id, "order_exists", "pass", "订单存在。"))
        historical_execution = task.execution_status in {
            "completed",
            "cancelled",
        }
        order_status_valid = order.status == "open" or historical_execution
        results.append(
            validation_result(
                task.id,
                "order_status",
                "pass" if order_status_valid else "fail",
                "任务已结束，保留订单历史快照。"
                if historical_execution
                else "订单状态可排产。"
                if order.status == "open"
                else f"订单状态为 {order.status}，不可排产。",
                details={
                    "order_status": order.status,
                    "execution_status": task.execution_status,
                },
            )
        )

        if machine is None:
            results.append(
                validation_result(
                    task.id,
                    "machine_exists",
                    "fail",
                    "机台不存在或不属于当前厂区。",
                )
            )
            continue
        results.append(
            validation_result(task.id, "machine_exists", "pass", "机台存在。")
        )
        results.append(
            validation_result(
                task.id,
                "machine_status",
                "pass" if machine.status == "available" else "fail",
                "机台状态可排产。"
                if machine.status == "available"
                else f"机台状态为 {machine.status}，不可排产。",
                details={"machine_status": machine.status},
            )
        )

        if planned_by_order[order.id] > order.outstanding_qty + 1e-6:
            results.append(
                validation_result(
                    task.id,
                    "order_quantity",
                    "fail",
                    "同一订单的计划数量合计超过欠数。",
                    details={
                        "planned_qty": planned_by_order[order.id],
                        "outstanding_qty": order.outstanding_qty,
                    },
                )
            )
        else:
            results.append(
                validation_result(
                    task.id,
                    "order_quantity",
                    "pass",
                    "计划数量未超过订单欠数。",
                )
            )

        if order.daily_target_qty is None or order.daily_target_qty <= 0:
            results.append(
                validation_result(
                    task.id,
                    "daily_target",
                    "unknown",
                    "订单缺少有效日产量，无法确认排程时长。",
                )
            )
        else:
            results.append(
                validation_result(
                    task.id,
                    "daily_target",
                    "pass",
                    "订单日产量有效。",
                )
            )
        results.append(validate_delivery_due_date(task.id, order.delivery_due_date))

        start = parse_business_timestamp(task.planned_start_at)
        finish = parse_business_timestamp(task.planned_finish_at)
        results.append(
            validation_result(
                task.id,
                "planned_time",
                "pass" if start is not None and finish is not None and start < finish else "fail",
                "计划时间有效。"
                if start is not None and finish is not None and start < finish
                else "计划开始/结束时间无效。",
            )
        )
        available_at = parse_business_timestamp(machine.available_at)
        if available_at is not None and start is not None and start < available_at:
            results.append(
                validation_result(
                    task.id,
                    "machine_available_at",
                    "fail",
                    "任务开始时间早于机台可用时间。",
                    details={
                        "available_at": machine.available_at,
                        "planned_start_at": task.planned_start_at,
                    },
                )
            )
        else:
            results.append(
                validation_result(
                    task.id,
                    "machine_available_at",
                    "pass",
                    "任务未早于机台可用时间。",
                )
            )

        if mold is None:
            results.extend(
                [
                    validation_result(
                        task.id,
                        "mold_master",
                        "unknown",
                        "订单缺少已确认的模具主数据。",
                    ),
                    validation_result(
                        task.id,
                        "shot_capacity",
                        "unknown",
                        "缺少模具或机台射胶量，无法校验射胶能力。",
                    ),
                    validation_result(
                        task.id,
                        "mold_dimensions",
                        "unknown",
                        "缺少模具空间资料，无法校验机台容模尺寸。",
                    ),
                ]
            )
        else:
            results.append(
                validation_result(task.id, "mold_master", "pass", "模具主数据存在。")
            )
            results.append(validate_machine_class(task.id, machine, mold, order))
            results.append(
                validate_shot_capacity(
                    task.id,
                    machine,
                    mold,
                    safety_factor,
                )
            )
            results.append(validate_dimensions(task.id, machine, mold))
            results.append(
                validate_robot_requirement(
                    task.id,
                    mold.robot_type,
                    machine.robot_type,
                )
            )
            results.append(
                validate_text_requirement(
                    task.id,
                    "fixture_type",
                    mold.fixture_type,
                    machine.fixture_type,
                    "夹具",
                )
            )
            results.append(validate_capabilities(task.id, machine, mold))

        results.append(validate_material(task.id, machine, mold, order))
        from app.services.injection_schedule_recommendation import (
            evaluate_phase3_master_constraints,
            evaluate_scheduled_task_time_window,
        )

        phase3_master_checks = evaluate_phase3_master_constraints(
            version.factory_id,
            order,
            mold,
            machine,
            config,
        )
        for check in phase3_master_checks:
            if check["code"] not in {
                "mold_thickness",
                "opening_stroke",
                "screw_compatibility",
                "transition_data",
            }:
                continue
            results.append(
                validation_result(
                    task.id,
                    check["code"],
                    check["status"],
                    check["message"],
                    details=check["details"],
                )
            )
        time_window_check = evaluate_scheduled_task_time_window(
            task,
            machine,
            config,
        )
        results.append(
            validation_result(
                task.id,
                time_window_check["code"],
                time_window_check["status"],
                time_window_check["message"],
                details=time_window_check["details"],
            )
        )
        snapshot_changed = (
            task.order_revision_snapshot != order.revision
            or task.machine_revision_snapshot != machine.revision
            or (
                mold is not None
                and task.mold_revision_snapshot != mold.revision
            )
        )
        results.append(
            validation_result(
                task.id,
                "master_revision",
                "fail" if snapshot_changed else "pass",
                "主数据在排程后已变化，请重新确认。"
                if snapshot_changed
                else "主数据版本与任务快照一致。",
            )
        )

    for machine_id, lane in tasks_by_machine.items():
        lane.sort(key=lambda item: (item.sequence_no, item.id))
        previous: InjectionScheduleTask | None = None
        for task in lane:
            machine = machines.get(machine_id)
            expected_setup_minutes = 0.0
            missing_setup_fields: list[str] = []
            if previous is not None:
                for role, adjacent in (("previous", previous), ("current", task)):
                    for field_name, value in (
                        ("mold_code_snapshot", adjacent.mold_code_snapshot),
                        ("color_snapshot", adjacent.color_snapshot),
                        ("material_snapshot", adjacent.material_snapshot),
                    ):
                        if normalize_key(value) in {
                            "",
                            "UNKNOWN",
                            "未知",
                            "待确认",
                        }:
                            missing_setup_fields.append(
                                f"{role}.{field_name}"
                            )
                if machine is None:
                    missing_setup_fields.append("machine")
                if not missing_setup_fields:
                    expected_setup_minutes = float(
                        calculate_transition_setup(
                            from_mold_code=previous.mold_code_snapshot,
                            from_color=previous.color_snapshot,
                            from_color_rank=previous.color_rank_snapshot,
                            from_material=previous.material_snapshot,
                            to_mold_code=task.mold_code_snapshot,
                            to_color=task.color_snapshot,
                            to_color_rank=task.color_rank_snapshot,
                            to_material=task.material_snapshot,
                            machine_class=machine.machine_class,
                            rules=config,
                        )["setup_minutes"]
                    )
                results.append(validate_lane_time_overlap(previous, task))
            actual_setup_minutes = max(float(task.setup_hours or 0), 0) * 60
            setup_matches = abs(
                actual_setup_minutes - expected_setup_minutes
            ) <= 0.01
            setup_status = (
                "unknown"
                if missing_setup_fields
                else "pass"
                if setup_matches
                else "fail"
            )
            results.append(
                validation_result(
                    task.id,
                    "transition_setup_consistency",
                    setup_status,
                    "相邻任务快照缺失，无法核对换型时长。"
                    if setup_status == "unknown"
                    else
                    "任务换型时长与版本规则快照一致。"
                    if setup_status == "pass"
                    else "任务换型时长与版本颜色/材料/换模规则快照不一致。",
                    details={
                        "expected_setup_minutes": round(
                            expected_setup_minutes,
                            3,
                        ),
                        "actual_setup_minutes": round(
                            actual_setup_minutes,
                            3,
                        ),
                        "previous_task_id": previous.id
                        if previous is not None
                        else "",
                        "missing_fields": missing_setup_fields,
                    },
                )
            )
            previous = task

    data_hash = build_version_data_hash(db, version)
    blocking_count = sum(
        item["blocking"] and item["status"] != "pass" for item in results
    )
    warning_count = sum(
        item["severity"] == "warning" and item["status"] != "pass"
        for item in results
    )
    result_hash = sha256(canonical_json(results).encode("utf-8")).hexdigest()
    timestamp = now_text()
    run = InjectionScheduleValidationRun(
        id=f"IVR-{uuid4().hex.upper()}",
        factory_id=version.factory_id,
        version_id=version.id,
        version_revision=version.revision,
        data_hash=data_hash,
        result_hash=result_hash,
        status="passed" if blocking_count == 0 else "blocked",
        blocking_count=blocking_count,
        warning_count=warning_count,
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
    )
    if persist:
        db.add(run)
        db.flush()
        for result in results:
            db.add(
                InjectionScheduleValidationItem(
                    id=f"IVI-{uuid4().hex.upper()}",
                    factory_id=version.factory_id,
                    run_id=run.id,
                    version_id=version.id,
                    **result,
                )
            )
        add_audit_event(
            db,
            factory_id=version.factory_id,
            entity_type="schedule_version",
            entity_id=version.id,
            action="validated",
            actor=actor,
            old_revision=version.revision,
            new_revision=version.revision,
            after={
                "validation_run_id": run.id,
                "status": run.status,
                "blocking_count": blocking_count,
                "warning_count": warning_count,
                "data_hash": data_hash,
            },
        )
        if commit:
            db.commit()
            db.refresh(run)
        else:
            db.flush()
    persisted_items = (
        list(
            db.scalars(
                select(InjectionScheduleValidationItem)
                .where(
                    InjectionScheduleValidationItem.run_id == run.id,
                    InjectionScheduleValidationItem.factory_id
                    == version.factory_id,
                )
                .order_by(InjectionScheduleValidationItem.id)
            ).all()
        )
        if persist
        else []
    )
    return {
        "id": run.id,
        "factory_id": run.factory_id,
        "version_id": run.version_id,
        "version_revision": run.version_revision,
        "data_hash": run.data_hash,
        "result_hash": run.result_hash,
        "status": run.status,
        "blocking_count": run.blocking_count,
        "warning_count": run.warning_count,
        "created_by": run.created_by,
        "created_by_name": run.created_by_name,
        "created_at": run.created_at,
        "items": (
            [serialize_validation_item(item) for item in persisted_items]
            if persist
            else [
                {
                    "id": f"virtual-{index}",
                    "run_id": run.id,
                    "version_id": version.id,
                    "task_id": result["task_id"],
                    "constraint_code": result["constraint_code"],
                    "status": result["status"],
                    "severity": result["severity"],
                    "blocking": result["blocking"],
                    "message": result["message"],
                    "details": json_object(result["details_json"]),
                }
                for index, result in enumerate(results)
            ]
        ),
    }


def validate_lane_time_overlap(
    previous: InjectionScheduleTask,
    current: InjectionScheduleTask,
) -> dict[str, Any]:
    previous_finish = parse_business_timestamp(previous.planned_finish_at)
    current_start = parse_business_timestamp(current.planned_start_at)
    current_occupied_start = (
        current_start - timedelta(hours=max(float(current.setup_hours or 0), 0))
        if current_start is not None
        else None
    )
    overlaps = (
        previous_finish is not None
        and current_occupied_start is not None
        and current_occupied_start < previous_finish
    )
    return validation_result(
        current.id,
        "time_overlap",
        "fail" if overlaps else "pass",
        "后序任务的换型占机时间与前序任务重叠。"
        if overlaps
        else "同机台任务（含换型占机）时间不重叠。",
        details={
            "previous_task_id": previous.id,
            "previous_finish_at": previous.planned_finish_at,
            "current_production_start_at": current.planned_start_at,
            "current_setup_hours": float(current.setup_hours or 0),
            "current_occupied_start_at": (
                current_occupied_start.strftime("%Y-%m-%d %H:%M:%S")
                if current_occupied_start is not None
                else ""
            ),
        },
    )


def latest_version_conflicts(
    db: Session,
    factory_id: str,
    version_id: str,
) -> list[dict[str, Any]]:
    version = db.scalar(
        select(InjectionScheduleVersion).where(
            InjectionScheduleVersion.id == version_id,
            InjectionScheduleVersion.factory_id == factory_id,
        )
    )
    if version is None:
        return []
    run = db.scalar(
        select(InjectionScheduleValidationRun)
        .where(
            InjectionScheduleValidationRun.factory_id == factory_id,
            InjectionScheduleValidationRun.version_id == version_id,
            InjectionScheduleValidationRun.version_revision == version.revision,
        )
        .order_by(
            InjectionScheduleValidationRun.created_at.desc(),
            InjectionScheduleValidationRun.id.desc(),
        )
    )
    if run is None:
        return []
    items = db.scalars(
        select(InjectionScheduleValidationItem)
        .where(
            InjectionScheduleValidationItem.factory_id == factory_id,
            InjectionScheduleValidationItem.run_id == run.id,
            InjectionScheduleValidationItem.status != "pass",
        )
        .order_by(
            InjectionScheduleValidationItem.blocking.desc(),
            InjectionScheduleValidationItem.task_id,
            InjectionScheduleValidationItem.constraint_code,
        )
    ).all()
    return [serialize_validation_item(item) for item in items]


def load_validation_run(
    db: Session,
    factory_id: str,
    run_id: str,
) -> InjectionScheduleValidationRun | None:
    return db.scalar(
        select(InjectionScheduleValidationRun).where(
            InjectionScheduleValidationRun.id == run_id,
            InjectionScheduleValidationRun.factory_id == factory_id,
        )
    )


def validation_result(
    task_id: str,
    code: str,
    status: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "constraint_code": code,
        "status": status,
        "severity": "error" if status == "fail" else "warning" if status == "unknown" else "info",
        "blocking": status != "pass",
        "message": message,
        "details_json": canonical_json(details or {}),
    }


def validate_machine_class(
    task_id: str,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
    order: InjectionOrderMaster,
) -> dict[str, Any]:
    requirement = mold.machine_class or order.machine_class
    if not requirement:
        return validation_result(
            task_id,
            "machine_class",
            "unknown",
            "缺少模具所需机型资料。",
        )
    if not machine.machine_class:
        return validation_result(
            task_id,
            "machine_class",
            "unknown",
            "缺少机台机型资料。",
        )
    required_tonnage = extract_tonnage(requirement)
    machine_tonnage = machine.tonnage_t or extract_tonnage(machine.machine_class)
    if required_tonnage is not None and machine_tonnage is not None:
        status = "pass" if machine_tonnage >= required_tonnage else "fail"
        return validation_result(
            task_id,
            "machine_class",
            status,
            "机台吨位满足模具要求。"
            if status == "pass"
            else "机台吨位低于模具要求。",
            details={
                "required_tonnage_t": required_tonnage,
                "machine_tonnage_t": machine_tonnage,
            },
        )
    status = (
        "pass"
        if normalize_key(requirement) in normalize_key(machine.machine_class)
        or normalize_key(machine.machine_class) in normalize_key(requirement)
        else "unknown"
    )
    return validation_result(
        task_id,
        "machine_class",
        status,
        "机型文本匹配。" if status == "pass" else "机型资料无法可靠比较。",
    )


def validate_shot_capacity(
    task_id: str,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
    safety_factor: float,
) -> dict[str, Any]:
    if mold.gross_shot_weight_g is None or machine.max_shot_weight_g is None:
        return validation_result(
            task_id,
            "shot_capacity",
            "unknown",
            "缺少整啤毛重或机台最大射胶量。",
        )
    permitted = machine.max_shot_weight_g * safety_factor
    status = "pass" if mold.gross_shot_weight_g <= permitted else "fail"
    return validation_result(
        task_id,
        "shot_capacity",
        status,
        "射胶量满足安全系数要求。"
        if status == "pass"
        else "模具整啤毛重超过机台安全射胶量。",
        details={
            "gross_shot_weight_g": mold.gross_shot_weight_g,
            "permitted_shot_weight_g": permitted,
            "safety_factor": safety_factor,
        },
    )


def validate_dimensions(
    task_id: str,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
) -> dict[str, Any]:
    if (
        mold.length_mm is None
        or mold.width_mm is None
        or machine.tie_bar_x_mm is None
        or machine.tie_bar_y_mm is None
    ):
        return validation_result(
            task_id,
            "mold_dimensions",
            "unknown",
            "缺少模具尺寸或机台柱距资料。",
        )
    fits = (
        mold.length_mm <= machine.tie_bar_x_mm
        and mold.width_mm <= machine.tie_bar_y_mm
    ) or (
        mold.width_mm <= machine.tie_bar_x_mm
        and mold.length_mm <= machine.tie_bar_y_mm
    )
    return validation_result(
        task_id,
        "mold_dimensions",
        "pass" if fits else "fail",
        "模具尺寸可进入机台柱距。"
        if fits
        else "模具尺寸超过机台柱距。",
    )


def validate_text_requirement(
    task_id: str,
    code: str,
    required: str,
    actual: str,
    label: str,
) -> dict[str, Any]:
    if not required:
        return validation_result(task_id, code, "pass", f"模具未声明{label}要求。")
    if not actual:
        return validation_result(task_id, code, "unknown", f"机台缺少{label}资料。")
    required_key = normalize_key(required)
    actual_key = normalize_key(actual)
    matches = required_key in actual_key or actual_key in required_key
    return validation_result(
        task_id,
        code,
        "pass" if matches else "fail",
        f"{label}满足要求。" if matches else f"{label}不符合模具要求。",
    )


def normalize_robot_level(value: str) -> int | None:
    normalized = re.sub(r"[\s_-]+", "", normalize_key(value))
    if not normalized:
        return None
    if (
        "半自动" in normalized
        or normalized in {"无", "无机械手", "NONE", "NOARM", "MANUAL"}
        or normalized.startswith("无机械手")
        or normalized.startswith("SEMI")
    ):
        return 0
    if "双臂" in normalized or "DOUBLE" in normalized:
        return 2
    if (
        "单臂" in normalized
        or "SINGLE" in normalized
        or "三轴" in normalized
        or "THREEAXIS" in normalized
        or normalized == "3AXIS"
    ):
        return 1
    return None


def validate_robot_requirement(
    task_id: str,
    required: str,
    actual: str,
) -> dict[str, Any]:
    if not required:
        return validation_result(
            task_id,
            "robot_type",
            "pass",
            "模具未声明机械手要求。",
        )
    required_level = normalize_robot_level(required)
    if required_level is None:
        return validation_result(
            task_id,
            "robot_type",
            "unknown",
            "模具机械手要求无法识别。",
            details={"required": required, "actual": actual},
        )
    if required_level == 0:
        return validation_result(
            task_id,
            "robot_type",
            "pass",
            "模具为无机械手或半自动要求，不限制机台机械手能力。",
            details={
                "required": required,
                "required_level": required_level,
                "actual": actual,
                "actual_level": normalize_robot_level(actual),
            },
        )
    actual_level = normalize_robot_level(actual)
    if actual_level is None:
        return validation_result(
            task_id,
            "robot_type",
            "unknown",
            "机台机械手能力资料缺失或无法识别。",
            details={
                "required": required,
                "required_level": required_level,
                "actual": actual,
            },
        )
    fits = actual_level >= required_level
    return validation_result(
        task_id,
        "robot_type",
        "pass" if fits else "fail",
        "机台机械手能力满足模具要求。"
        if fits
        else "机台机械手能力低于模具要求。",
        details={
            "required": required,
            "required_level": required_level,
            "actual": actual,
            "actual_level": actual_level,
        },
    )


def validate_capabilities(
    task_id: str,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster,
) -> dict[str, Any]:
    required = {
        normalize_key(value)
        for value in json_list(mold.required_capabilities_json)
        if normalize_key(value)
    }
    actual = {
        normalize_key(value)
        for value in json_list(machine.capabilities_json)
        if normalize_key(value)
    }
    if required and not actual:
        return validation_result(
            task_id,
            "capabilities",
            "unknown",
            "模具有工艺能力要求，但机台能力资料缺失。",
            details={"required": sorted(required)},
        )
    missing = required - actual
    return validation_result(
        task_id,
        "capabilities",
        "fail" if missing else "pass",
        "机台不具备模具要求的全部工艺能力。"
        if missing
        else "机台工艺能力满足要求。",
        details={"missing": sorted(missing), "required": sorted(required)},
    )


def validate_delivery_due_date(
    task_id: str,
    value: str,
) -> dict[str, Any]:
    normalized = (value or "").strip()
    if not normalized:
        return validation_result(
            task_id,
            "delivery_due_date",
            "unknown",
            "订单缺少有效交期。",
        )
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError:
        return validation_result(
            task_id,
            "delivery_due_date",
            "fail",
            "订单交期格式无效，必须为 YYYY-MM-DD。",
            details={"delivery_due_date": normalized},
        )
    return validation_result(
        task_id,
        "delivery_due_date",
        "pass",
        "订单交期有效。",
        details={"delivery_due_date": parsed.isoformat()},
    )


def validate_material(
    task_id: str,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster | None,
    order: InjectionOrderMaster,
) -> dict[str, Any]:
    if not order.material:
        return validation_result(
            task_id,
            "material",
            "unknown",
            "订单缺少材料资料。",
        )
    machine_rules = {
        normalize_key(value)
        for value in json_list(machine.material_rules_json)
        if normalize_key(value)
    }
    mold_rules = {
        normalize_key(value)
        for value in (
            json_list(mold.material_rules_json) if mold is not None else []
        )
        if normalize_key(value)
    }
    if not machine_rules and not mold_rules:
        return validation_result(
            task_id,
            "material",
            "pass",
            "未配置材料限制。",
        )
    material = normalize_key(order.material)
    machine_matches = not machine_rules or any(
        rule in material or material in rule for rule in machine_rules
    )
    mold_matches = not mold_rules or any(
        rule in material or material in rule for rule in mold_rules
    )
    mismatches = []
    if not machine_matches:
        mismatches.append("机台材料限制")
    if not mold_matches:
        mismatches.append("模具材料限制")
    matches = machine_matches and mold_matches
    return validation_result(
        task_id,
        "material",
        "pass" if matches else "fail",
        "材料同时符合机台与模具配置。"
        if matches
        else f"材料不符合{'、'.join(mismatches)}。",
        details={
            "machine_allowed": sorted(machine_rules),
            "mold_allowed": sorted(mold_rules),
            "actual": order.material,
        },
    )


def extract_tonnage(value: str) -> float | None:
    # A class code such as "14A" is an exact machine family, not a 14-ton
    # capacity requirement.  Only values carrying an explicit tonnage unit may
    # use the numeric >= comparison.
    match = TONNAGE_PATTERN.search(value or "")
    return float(match.group(1)) if match else None


def serialize_validation_item(
    item: InjectionScheduleValidationItem,
) -> dict[str, Any]:
    return {
        "id": item.id,
        "run_id": item.run_id,
        "version_id": item.version_id,
        "task_id": item.task_id,
        "constraint_code": item.constraint_code,
        "status": item.status,
        "severity": item.severity,
        "blocking": bool(item.blocking),
        "message": item.message,
        "details": json_object(item.details_json),
    }
