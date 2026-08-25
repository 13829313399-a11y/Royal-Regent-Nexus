from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingShiftReport,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_shared import (
    InjectionSchedulingMoldDefinition,
    InjectionSchedulingMoldOutputSpec,
)
from app.schemas.injection_scheduling_execution import (
    InjectionSchedulingOrderUpdate,
    InjectionSchedulingTaskUpdate,
)
from app.schemas.injection_scheduling_workbench import (
    InjectionSchedulingWorkbenchBulkUpdate,
    InjectionSchedulingWorkbenchJobOut,
    InjectionSchedulingWorkbenchMachineOut,
    InjectionSchedulingWorkbenchOut,
    InjectionSchedulingWorkbenchSummaryOut,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import (
    list_machines,
    list_molds,
    machine_out,
    mold_out,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_execution import (
    current_plan,
    latest_event_sequence,
    list_backlog_orders,
    order_out,
    plan_out,
    update_order,
    update_task,
)


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _number(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value not in {None, ""} else ""


def _nullable_bool(value: Any) -> bool | None:
    if value in {None, ""}:
        return None
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "n", "否"}
    return bool(value)


def _task_status(value: str) -> str:
    return {
        "QUEUED": "PLANNED",
        "RUNNING": "RUNNING",
        "BLOCKED": "PAUSED",
        "COMPLETED": "DONE",
        "CANCELLED": "PAUSED",
    }.get(value, "PAUSED")


def _machine_constraint_summary(
    remarks: str,
    restrictions: list[str],
) -> str:
    parts = [remarks.strip(), *[str(item).strip() for item in restrictions]]
    return "；".join(dict.fromkeys(item for item in parts if item))


def _source_value(
    lineage: dict[str, Any],
    *keys: str,
    fallback: Any = None,
) -> Any:
    for key in keys:
        value = lineage.get(key)
        if value not in {None, ""}:
            return value
    return fallback


def get_injection_scheduling_workbench(
    db: Session,
    *,
    factory_id: str,
    search: str = "",
    status: str = "",
    machine_id: str = "",
) -> InjectionSchedulingWorkbenchOut:
    factory_id = require_injection_scheduling_factory(factory_id)
    machine_records = list_machines(db, factory_id, search="", status="")
    mold_records = list_molds(db, factory_id, search="", status="")
    machines_by_id = {item.id: machine_out(item) for item in machine_records}
    molds_by_id = {item.id: mold_out(item) for item in mold_records}
    machines = [
        InjectionSchedulingWorkbenchMachineOut(
            id=item.id,
            factory_id=factory_id,
            code=item.machine_code,
            position=item.position,
            area=item.area,
            a_class=float(item.machine_a_class) if item.machine_a_class is not None else None,
            tonnage=(
                float(item.clamping_force_tons)
                if item.clamping_force_tons is not None
                else None
            ),
            arm_capabilities=_json_list(item.robot_capabilities_json),
            fixture_capabilities=_json_list(item.fixture_capabilities_json),
            process_restrictions=_json_list(item.process_restrictions_json),
            status=item.status,
            available_for_auto_schedule=item.status in {"available", "running"},
            remark=item.remarks,
            parsed_constraint_summary=_machine_constraint_summary(
                item.remarks,
                _json_list(item.process_restrictions_json),
            ),
            revision=item.revision,
        )
        for item in machine_records
    ]

    plan_record = current_plan(db, factory_id)
    plan = plan_out(db, plan_record) if plan_record is not None else None
    business_date = plan.business_date if plan is not None else ""
    plan_mode = (
        "PLANNING"
        if plan is not None and plan.status == "DRAFT"
        else "EXECUTION"
        if plan is not None
        else "EMPTY"
    )

    definition_ids = {
        order.mold_definition_id
        for order in plan.orders if order.mold_definition_id
    } if plan is not None else set()
    output_ids = {
        order.mold_output_spec_id
        for order in plan.orders if order.mold_output_spec_id
    } if plan is not None else set()
    definitions = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingMoldDefinition).where(
                InjectionSchedulingMoldDefinition.id.in_(definition_ids)
            )
        ).all()
    } if definition_ids else {}
    outputs = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingMoldOutputSpec).where(
                InjectionSchedulingMoldOutputSpec.id.in_(output_ids)
            )
        ).all()
    } if output_ids else {}

    shift_totals: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"DAY": Decimal(0), "NIGHT": Decimal(0), "downtime": 0}
    )
    if plan is not None and business_date:
        reports = db.scalars(
            select(InjectionSchedulingShiftReport).where(
                InjectionSchedulingShiftReport.factory_id == factory_id,
                InjectionSchedulingShiftReport.business_date == business_date,
            )
        ).all()
        for report in reports:
            shift_totals[report.task_id][report.shift_code] += Decimal(
                report.normalized_increment_quantity
            )
            shift_totals[report.task_id]["downtime"] += report.downtime_minutes

    jobs: list[InjectionSchedulingWorkbenchJobOut] = []
    scheduled_order_ids: set[str] = set()
    if plan is not None:
        orders_by_id = {item.id: item for item in plan.orders}
        states_by_order = {item.order_id: item for item in plan.plan_order_states}
        for task in plan.tasks:
            order = orders_by_id.get(task.order_id)
            if order is None:
                continue
            scheduled_order_ids.add(order.id)
            state = states_by_order.get(order.id)
            lineage = order.lineage if isinstance(order.lineage, dict) else {}
            mold = molds_by_id.get(task.mold_id or order.mold_id or "")
            definition = definitions.get(order.mold_definition_id or "")
            output = outputs.get(order.mold_output_spec_id or "")
            machine = machines_by_id.get(task.machine_id)
            machine_summary = next(
                (
                    item.parsed_constraint_summary
                    for item in machines
                    if item.id == task.machine_id
                ),
                "",
            )
            quantity = state.order_quantity if state is not None else order.order_quantity
            completed = (
                state.completed_quantity if state is not None else order.completed_quantity
            )
            opening = (
                state.takeover_source_completed_quantity
                if state is not None
                else order.source_completed_quantity
            )
            reported = (
                state.report_increment_total + state.progress_adjustment_total
                if state is not None
                else max(completed - opening, 0)
            )
            job = InjectionSchedulingWorkbenchJobOut(
                id=task.id,
                factory_id=factory_id,
                plan_id=plan.id,
                task_id=task.id,
                order_id=order.id,
                machine_id=task.machine_id,
                machine_code=machine.machine_code if machine else "",
                sequence_no=task.sequence_no,
                status=_task_status(task.execution_status),
                order_no=order.order_no,
                item_no=order.item_no,
                product_name=order.product_name or (output.product_name if output else ""),
                warehouse_text=order.warehouse_text,
                set_quantity=_number(_source_value(lineage, "set_quantity", "total_sets")),
                order_quantity=quantity,
                opening_completed_quantity=opening,
                reported_quantity=reported,
                completed_quantity=completed,
                outstanding_quantity=max(quantity - completed, 0),
                completion_rate=min(completed / quantity, 1) if quantity else 0,
                mold_id=task.mold_id or order.mold_id,
                mold_no=(
                    mold.mold_no
                    if mold
                    else definition.display_mold_no
                    if definition
                    else _text(_source_value(lineage, "source_mold_no"))
                ),
                mold_name=(
                    mold.name
                    if mold
                    else definition.standard_name
                    if definition
                    else _text(_source_value(lineage, "mold_name"))
                ),
                required_machine_a=(
                    mold.mold_a_class
                    if mold and mold.mold_a_class is not None
                    else float(definition.mold_a_class)
                    if definition and definition.mold_a_class is not None
                    else _number(_source_value(lineage, "required_machine_a", "machine_a_class"))
                ),
                material_name=_text(
                    _source_value(
                        lineage,
                        "material_name",
                        fallback=(output.default_material if output else mold.material_name if mold else ""),
                    )
                ),
                sprue_ratio=_number(_source_value(lineage, "sprue_ratio")),
                color_name=_text(
                    _source_value(
                        lineage,
                        "color_name",
                        fallback=(output.default_color if output else mold.color_profile if mold else ""),
                    )
                ),
                color_powder_code=_text(_source_value(lineage, "color_powder_code")),
                net_weight_g=_number(
                    _source_value(
                        lineage,
                        "whole_shot_net_weight_g",
                        "net_weight_g",
                        fallback=(output.whole_shot_net_weight_g if output else mold.whole_shot_net_weight_g if mold else None),
                    )
                ),
                gross_weight_g=_number(
                    _source_value(
                        lineage,
                        "whole_shot_gross_weight_g",
                        "gross_weight_g",
                        "total_gross_weight",
                        fallback=(output.whole_shot_gross_weight_g if output else mold.whole_shot_gross_weight_g if mold else None),
                    )
                ),
                material_weight_kg=_number(_source_value(lineage, "material_weight_kg")),
                unit_price=_number(_source_value(lineage, "unit_price")),
                spray_required=_nullable_bool(_source_value(lineage, "spray_required")),
                arm_requirement=(
                    _text(_source_value(lineage, "required_arm_type", "arm_requirement"))
                    or (definition.default_arm_type if definition else mold.required_arm_type if mold else "")
                ),
                fixture_requirement=(
                    _text(_source_value(lineage, "required_fixture_type", "fixture_requirement"))
                    or (definition.default_fixture_type if definition else mold.required_fixture_type if mold else "")
                ),
                order_date=_text(_source_value(lineage, "order_date")),
                delivery_start_date=order.delivery_start_date,
                delivery_due_date=order.delivery_due_date,
                priority=order.priority_code,
                planned_start=task.planned_start,
                planned_finish=task.planned_finish,
                estimated_finish=task.estimated_finish,
                delivery_slack_days=task.delivery_slack_days,
                shift_target_quantity=task.shift_target_quantity,
                today_day_quantity=float(shift_totals[task.id]["DAY"]),
                today_night_quantity=float(shift_totals[task.id]["NIGHT"]),
                downtime_minutes=int(shift_totals[task.id]["downtime"]),
                locked=task.locked,
                manual_override_reason=task.manual_override_reason,
                order_remark=order.remark,
                machine_remark=machine.remarks if machine else "",
                parsed_constraint_summary=machine_summary,
                suggestion_reason=_text(task.auto_explanation.get("summary")) if isinstance(task.auto_explanation, dict) else "",
                material_readiness_status=order.material_readiness_status,
                mold_enrichment_status=_text(lineage.get("mold_enrichment_status")),
                source_batch_id=task.import_batch_id,
                source_sheet_name=task.source_sheet_name,
                source_row_number=task.source_row,
                source_line_key=task.stable_row_key,
                task_revision=task.revision,
                order_revision=order.revision,
                plan_revision=plan.revision,
                updated_by_name=task.updated_by_name or order.updated_by_name,
                updated_at=max(task.updated_at, order.updated_at),
                lineage=lineage,
            )
            jobs.append(job)

        for order in plan.orders:
            if order.id in scheduled_order_ids or order.status != "BACKLOG":
                continue
            jobs.append(_backlog_job(factory_id, order, plan.id, plan.revision))
    else:
        jobs.extend(
            _backlog_job(factory_id, order_out(order), None, None)
            for order in list_backlog_orders(db, factory_id)
        )

    normalized_search = search.strip().casefold()
    if normalized_search:
        jobs = [
            item
            for item in jobs
            if normalized_search
            in (
                f"{item.machine_code} {item.order_no} {item.item_no} "
                f"{item.product_name} {item.mold_no} {item.mold_name} "
                f"{item.warehouse_text}"
            ).casefold()
        ]
    if status:
        jobs = [item for item in jobs if item.status == status]
    if machine_id:
        jobs = [item for item in jobs if item.machine_id == machine_id]

    jobs.sort(
        key=lambda item: (
            item.machine_code == "",
            item.machine_code,
            item.sequence_no if item.sequence_no is not None else 1_000_000,
            item.delivery_due_date,
            item.order_no,
        )
    )
    summary = InjectionSchedulingWorkbenchSummaryOut(
        unplanned_count=sum(item.status == "UNPLANNED" for item in jobs),
        overdue_count=sum(
            item.status != "DONE"
            and item.delivery_slack_days is not None
            and item.delivery_slack_days < 0
            for item in jobs
        ),
        conflict_count=sum(
            item.status == "PAUSED"
            or item.material_readiness_status == "blocked"
            or item.mold_enrichment_status in {"PENDING", "AMBIGUOUS"}
            for item in jobs
        ),
        running_count=sum(item.status == "RUNNING" for item in jobs),
        today_day_quantity=sum(item.today_day_quantity for item in jobs),
        today_night_quantity=sum(item.today_night_quantity for item in jobs),
    )
    return InjectionSchedulingWorkbenchOut(
        factory_id=factory_id,
        business_date=business_date,
        plan_id=plan.id if plan else None,
        plan_revision=plan.revision if plan else None,
        rule_revision=plan.rule_revision if plan else None,
        plan_mode=plan_mode,
        polling_revision=latest_event_sequence(db, factory_id),
        machines=machines,
        jobs=jobs,
        summary=summary,
    )


def update_injection_scheduling_workbench_jobs(
    db: Session,
    *,
    payload: InjectionSchedulingWorkbenchBulkUpdate,
    user: AuthContext,
    can_override_baseline: bool,
) -> InjectionSchedulingWorkbenchOut:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    plan_record = current_plan(db, factory_id)
    task_fields = {
        "status",
        "shift_target_quantity",
        "planned_start",
        "planned_finish",
        "locked",
        "manual_override_reason",
    }
    if any(item.field in task_fields for item in payload.changes):
        if plan_record is None or plan_record.status != "DRAFT":
            raise HTTPException(
                status_code=409,
                detail="当前计划不是可编辑规划，不能修改排机字段",
            )
        if payload.expected_plan_revision != plan_record.revision:
            raise HTTPException(status_code=409, detail="计划版本已变化，请刷新后重试")

    task_ids = {item.job_id for item in payload.changes if not item.job_id.startswith("backlog:")}
    tasks = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.id.in_(task_ids),
            )
        ).all()
    } if task_ids else {}
    order_ids = {
        item.job_id.removeprefix("backlog:")
        for item in payload.changes
        if item.job_id.startswith("backlog:")
    } | {task.order_id for task in tasks.values()}
    orders = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id,
                InjectionSchedulingOrder.id.in_(order_ids),
            )
        ).all()
    } if order_ids else {}

    task_changes: dict[str, dict[str, Any]] = defaultdict(dict)
    task_revisions: dict[str, int] = {}
    order_changes: dict[str, dict[str, Any]] = defaultdict(dict)
    order_revisions: dict[str, int] = {}
    for item in payload.changes:
        task = tasks.get(item.job_id)
        order_id = task.order_id if task is not None else item.job_id.removeprefix("backlog:")
        order = orders.get(order_id)
        if order is None:
            raise HTTPException(
                status_code=404,
                detail="待保存订单不存在或不属于当前厂区",
            )
        if item.expected_order_revision != order.revision:
            raise HTTPException(status_code=409, detail="订单版本已变化，请刷新后重试")
        order_revisions[order_id] = item.expected_order_revision
        if item.field == "warehouse_text":
            _merge_bulk_value(order_changes[order_id], "warehouse_text", _text(item.value))
        elif item.field == "order_remark":
            _merge_bulk_value(order_changes[order_id], "remark", _text(item.value))
        else:
            if task is None or item.expected_task_revision != task.revision:
                raise HTTPException(
                    status_code=409,
                    detail="排产任务版本已变化，请刷新后重试",
                )
            task_revisions[task.id] = task.revision
            field = "execution_status" if item.field == "status" else item.field
            value: Any = item.value
            if item.field == "status":
                value = {"PLANNED": "QUEUED", "PAUSED": "BLOCKED"}.get(
                    _text(item.value)
                )
                if value is None:
                    raise HTTPException(
                        status_code=422,
                        detail="规划表只能改为已排队或暂停状态",
                    )
            elif item.field == "shift_target_quantity":
                try:
                    value = float(item.value)
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail="计划目标必须是数字",
                    ) from exc
                if value < 0:
                    raise HTTPException(
                        status_code=422,
                        detail="计划目标不能小于零",
                    )
            elif item.field == "locked":
                if isinstance(item.value, bool):
                    value = item.value
                else:
                    normalized = _text(item.value).casefold()
                    if normalized not in {"true", "false", "1", "0", "是", "否"}:
                        raise HTTPException(
                            status_code=422,
                            detail="锁定字段只支持是或否",
                        )
                    value = normalized in {"true", "1", "是"}
            else:
                value = _text(item.value)
            _merge_bulk_value(task_changes[task.id], field, value)

    try:
        current_plan_revision = payload.expected_plan_revision
        for task_id, changes in task_changes.items():
            if plan_record is None or current_plan_revision is None:
                raise HTTPException(status_code=409, detail="当前计划不存在")
            plan_record, _, _ = update_task(
                db,
                plan_record.id,
                task_id,
                InjectionSchedulingTaskUpdate(
                    factory_id=factory_id,
                    expected_revision=task_revisions[task_id],
                    expected_plan_revision=current_plan_revision,
                    **changes,
                ),
                user,
                f"{payload.request_id}-{len(task_changes)}-{task_id}"[:128],
                can_override_baseline=can_override_baseline,
                commit=False,
            )
            current_plan_revision = plan_record.revision
        for order_id, changes in order_changes.items():
            update_order(
                db,
                order_id,
                InjectionSchedulingOrderUpdate(
                    factory_id=factory_id,
                    expected_revision=order_revisions[order_id],
                    **changes,
                ),
                user,
                f"{payload.request_id}-{len(order_changes)}-{order_id}"[:128],
                commit=False,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_injection_scheduling_workbench(db, factory_id=factory_id)


def _merge_bulk_value(target: dict[str, Any], field: str, value: Any) -> None:
    if field in target and target[field] != value:
        raise HTTPException(
            status_code=422,
            detail="同一次粘贴不能给同一业务字段写入不同值",
        )
    target[field] = value


def _backlog_job(factory_id, order, plan_id, plan_revision):
    lineage = order.lineage if isinstance(order.lineage, dict) else {}
    quantity = order.order_quantity
    completed = order.completed_quantity
    return InjectionSchedulingWorkbenchJobOut(
        id=f"backlog:{order.id}",
        factory_id=factory_id,
        plan_id=plan_id,
        task_id=None,
        order_id=order.id,
        machine_id=None,
        machine_code="",
        sequence_no=None,
        status="UNPLANNED",
        order_no=order.order_no,
        item_no=order.item_no,
        product_name=order.product_name,
        warehouse_text=order.warehouse_text,
        set_quantity=_number(_source_value(lineage, "set_quantity", "total_sets")),
        order_quantity=quantity,
        opening_completed_quantity=order.source_completed_quantity,
        reported_quantity=max(completed - order.source_completed_quantity, 0),
        completed_quantity=completed,
        outstanding_quantity=max(quantity - completed, 0),
        completion_rate=min(completed / quantity, 1) if quantity else 0,
        mold_id=order.mold_id,
        mold_no=_text(_source_value(lineage, "source_mold_no")),
        mold_name=_text(_source_value(lineage, "mold_name")),
        required_machine_a=_number(_source_value(lineage, "required_machine_a", "machine_a_class")),
        material_name=_text(_source_value(lineage, "material_name")),
        sprue_ratio=_number(_source_value(lineage, "sprue_ratio")),
        color_name=_text(_source_value(lineage, "color_name")),
        color_powder_code=_text(_source_value(lineage, "color_powder_code")),
        net_weight_g=_number(_source_value(lineage, "whole_shot_net_weight_g", "net_weight_g")),
        gross_weight_g=_number(_source_value(lineage, "whole_shot_gross_weight_g", "gross_weight_g", "total_gross_weight")),
        material_weight_kg=_number(_source_value(lineage, "material_weight_kg")),
        unit_price=_number(_source_value(lineage, "unit_price")),
        spray_required=None,
        arm_requirement=_text(_source_value(lineage, "required_arm_type", "arm_requirement")),
        fixture_requirement=_text(_source_value(lineage, "required_fixture_type", "fixture_requirement")),
        order_date=_text(_source_value(lineage, "order_date")),
        delivery_start_date=order.delivery_start_date,
        delivery_due_date=order.delivery_due_date,
        priority=order.priority_code,
        planned_start="",
        planned_finish="",
        estimated_finish=order.estimated_completion_at,
        delivery_slack_days=order.delivery_slack_days,
        shift_target_quantity=_number(_source_value(lineage, "source_daily_capacity")) or 0,
        today_day_quantity=0,
        today_night_quantity=0,
        downtime_minutes=0,
        locked=False,
        manual_override_reason="",
        order_remark=order.remark,
        machine_remark="",
        parsed_constraint_summary="",
        suggestion_reason="",
        material_readiness_status=order.material_readiness_status,
        mold_enrichment_status=_text(lineage.get("mold_enrichment_status")),
        source_batch_id=None,
        source_sheet_name=_text(_source_value(lineage, "source_sheet_name")),
        source_row_number=(
            int(lineage["source_row"])
            if isinstance(lineage.get("source_row"), int)
            else None
        ),
        source_line_key=_text(_source_value(lineage, "stable_row_key")),
        task_revision=None,
        order_revision=order.revision,
        plan_revision=plan_revision,
        updated_by_name=order.updated_by_name,
        updated_at=order.updated_at,
        lineage=lineage,
    )
