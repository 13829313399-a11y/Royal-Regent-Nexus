from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
    InjectionSchedulingProgressAdjustment,
    InjectionSchedulingShiftReport,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_import import InjectionSchedulingImportBatch
from app.services.auth import AuthContext
from app.services.injection_scheduling_execution import (
    _actor_name,
    _audit,
    _delivery_slack_days,
    _now,
    _remaining_shifts,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _latest_report_event_sequence(db: Session, factory_id: str) -> int:
    return int(
        db.scalar(
            select(func.max(InjectionSchedulingAuditEvent.sequence)).where(
                InjectionSchedulingAuditEvent.factory_id == factory_id,
                InjectionSchedulingAuditEvent.event_type == "shift_report_recorded",
            )
        )
        or 0
    )


def _latest_event_sequence(db: Session, factory_id: str) -> int:
    # Import preview/approval events are evidence about an import batch, not
    # mutations of the execution baseline.  Including them here would make a
    # preview invalidate its own action fingerprint as soon as its audit event
    # is appended.
    return int(
        db.scalar(
            select(func.max(InjectionSchedulingAuditEvent.sequence)).where(
                InjectionSchedulingAuditEvent.factory_id == factory_id,
                ~InjectionSchedulingAuditEvent.event_type.like("import_%"),
            )
        )
        or 0
    )


def explicit_plan_context(
    db: Session, factory_id: str
) -> tuple[InjectionSchedulingPlan | None, InjectionSchedulingPlan | None]:
    draft = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    published = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
        .order_by(InjectionSchedulingPlan.published_at.desc())
    )
    return published, draft


def plan_order_states(
    db: Session, factory_id: str, plan_id: str
) -> list[InjectionSchedulingPlanOrderState]:
    return list(
        db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(
                InjectionSchedulingPlanOrderState.factory_id == factory_id,
                InjectionSchedulingPlanOrderState.plan_id == plan_id,
            )
            .order_by(
                InjectionSchedulingPlanOrderState.status,
                InjectionSchedulingPlanOrderState.stable_order_key,
            )
        ).all()
    )


def _lineage_stable_order(order: InjectionSchedulingOrder) -> str:
    lineage = _load_json(order.lineage_json, {})
    value = lineage.get("stable_order_key")
    if isinstance(value, str) and value:
        return value
    return _hash(
        [
            order.factory_id,
            order.order_no,
            order.item_no,
            order.mold_id or "",
            order.product_name,
        ]
    )


def _revision_snapshot(
    db: Session,
    *,
    factory_id: str,
    target_plan: InjectionSchedulingPlan | None,
    reference_plan: InjectionSchedulingPlan | None,
) -> tuple[str, str]:
    plan_ids = [
        item.id for item in (target_plan, reference_plan) if item is not None
    ]
    tasks = (
        list(
            db.scalars(
                select(InjectionSchedulingTask).where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id.in_(plan_ids),
                )
            ).all()
        )
        if plan_ids
        else []
    )
    states = (
        list(
            db.scalars(
                select(InjectionSchedulingPlanOrderState).where(
                    InjectionSchedulingPlanOrderState.factory_id == factory_id,
                    InjectionSchedulingPlanOrderState.plan_id.in_(plan_ids),
                )
            ).all()
        )
        if plan_ids
        else []
    )
    revision_digest = _hash(
        {
            "plans": [
                [item.id, item.status, item.revision]
                for item in (target_plan, reference_plan)
                if item is not None
            ],
            "tasks": sorted(
                [
                    item.id,
                    item.revision,
                    item.execution_status,
                    str(item.reported_quantity),
                    item.machine_id,
                    item.planned_start,
                    item.planned_finish,
                ]
                for item in tasks
            ),
            "states": sorted(
                [
                    item.id,
                    item.revision,
                    str(item.takeover_source_completed_quantity),
                    str(item.report_increment_total),
                    str(item.progress_adjustment_total),
                    item.status,
                ]
                for item in states
            ),
        }
    )
    masters = {
        "machines": sorted(
            [item.id, item.machine_code, item.revision, item.status]
            for item in db.scalars(
                select(InjectionSchedulingMachine).where(
                    InjectionSchedulingMachine.factory_id == factory_id
                )
            ).all()
        ),
        "molds": sorted(
            [item.id, item.mold_no, item.revision, item.status]
            for item in db.scalars(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.factory_id == factory_id
                )
            ).all()
        ),
    }
    return revision_digest, _hash(masters)


def _task_source_profile_family(task: InjectionSchedulingTask) -> str:
    detail = _load_json(task.auto_explanation_json, {})
    lineage = detail.get("source_lineage", {}) if isinstance(detail, dict) else {}
    return str(lineage.get("profile_family", ""))


def _action(
    action_type: str,
    *,
    row: dict[str, Any] | None = None,
    target_order_id: str = "",
    target_task_id: str = "",
    requires_publish: bool = False,
    reason_code: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = (row or {}).get("source", {})
    payload = {
        "action_type": action_type,
        "stable_order_key": (row or {}).get("stable_order_key", ""),
        "stable_row_key": (row or {}).get("stable_row_key", ""),
        "source_sheet_name": source.get("sheet_name", ""),
        "source_row": source.get("source_row"),
        "target_order_id": target_order_id,
        "target_task_id": target_task_id,
        "requires_publish": requires_publish,
        "reason_code": reason_code,
        "detail": detail or {},
    }
    action_sha256 = _hash(payload)
    return {
        "id": f"isaction-{action_sha256[:24]}",
        **payload,
        "action_sha256": action_sha256,
    }


def _task_matches_row(
    task: InjectionSchedulingTask,
    row: dict[str, Any],
    machines: dict[str, str],
    molds: dict[str, str],
) -> bool:
    allocated = row.get("planned_quantity")
    return all(
        (
            machines.get(task.machine_id, "") == row.get("machine_code", ""),
            molds.get(task.mold_id or "", "") == row.get("mold_no", ""),
            task.planned_start == row.get("planned_start", ""),
            task.planned_finish == row.get("planned_finish", ""),
            allocated is None
            or _decimal(task.allocated_quantity) == _decimal(allocated),
        )
    )


def build_reconciliation_preview(
    db: Session,
    *,
    factory_id: str,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    published, draft = explicit_plan_context(db, factory_id)
    virtual_target = draft or published
    target_tasks = (
        list(
            db.scalars(
                select(InjectionSchedulingTask).where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == virtual_target.id,
                )
            ).all()
        )
        if virtual_target is not None
        else []
    )
    target_states = (
        plan_order_states(db, factory_id, virtual_target.id)
        if virtual_target is not None
        else []
    )
    machines = {
        item.id: item.machine_code
        for item in db.scalars(
            select(InjectionSchedulingMachine).where(
                InjectionSchedulingMachine.factory_id == factory_id
            )
        ).all()
    }
    molds = {
        item.id: item.mold_no
        for item in db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == factory_id
            )
        ).all()
    }
    tasks_by_row: defaultdict[str, list[InjectionSchedulingTask]] = defaultdict(list)
    for task in target_tasks:
        if task.stable_row_key:
            tasks_by_row[task.stable_row_key].append(task)
    states_by_order: defaultdict[str, list[InjectionSchedulingPlanOrderState]] = (
        defaultdict(list)
    )
    for state in target_states:
        states_by_order[state.stable_order_key].append(state)

    actions: list[dict[str, Any]] = []
    seen_new_orders: set[str] = set()
    incoming_row_keys: set[str] = set()
    incoming_order_keys: set[str] = set()
    rows = [
        *normalized.get("scheduled_baseline_tasks", []),
        *normalized.get("backlog_orders", []),
    ]
    for row in rows:
        stable_order = row.get("stable_order_key", "")
        stable_row = row.get("stable_row_key", "")
        incoming_order_keys.add(stable_order)
        if stable_row:
            incoming_row_keys.add(stable_row)
        state_matches = states_by_order.get(stable_order, [])
        task_matches = tasks_by_row.get(stable_row, []) if stable_row else []
        if len(state_matches) > 1 or len(task_matches) > 1:
            actions.append(
                _action(
                    "CONFLICT",
                    row=row,
                    reason_code="STABLE_IDENTITY_AMBIGUOUS",
                    detail={
                        "state_ids": [item.id for item in state_matches],
                        "task_ids": [item.id for item in task_matches],
                    },
                )
            )
            continue
        state = state_matches[0] if state_matches else None
        task = task_matches[0] if task_matches else None
        if state is not None:
            excel_completed = _decimal(row.get("completed_quantity"))
            baseline = _decimal(state.takeover_source_completed_quantity)
            report_total = _decimal(state.report_increment_total)
            adjustment_total = _decimal(state.progress_adjustment_total)
            signed_export = row.get("system_export")
            if signed_export is not None:
                exported_completed = _decimal(
                    signed_export.get("completed_at_export")
                )
                exported_report_total = _decimal(
                    signed_export.get("report_increment_total_at_export")
                )
                exported_adjustment_total = _decimal(
                    signed_export.get("progress_adjustment_total_at_export")
                )
                if (
                    report_total != exported_report_total
                    or adjustment_total != exported_adjustment_total
                    or _decimal(state.completed_quantity) != exported_completed
                ):
                    if excel_completed != _decimal(state.completed_quantity):
                        actions.append(
                            _action(
                                "CONFLICT",
                                row=row,
                                target_order_id=state.order_id,
                                target_task_id=task.id if task else "",
                                reason_code="SIGNED_EXPORT_PROGRESS_STALE",
                                detail={
                                    "excel_value": float(excel_completed),
                                    "completed_at_export": float(exported_completed),
                                    "current_completed": float(
                                        state.completed_quantity
                                    ),
                                    "report_increment_total_at_export": float(
                                        exported_report_total
                                    ),
                                    "current_report_increment_total": float(
                                        report_total
                                    ),
                                    "progress_adjustment_total_at_export": float(
                                        exported_adjustment_total
                                    ),
                                    "current_progress_adjustment_total": float(
                                        adjustment_total
                                    ),
                                },
                            )
                        )
                        continue
                elif excel_completed != exported_completed:
                    actions.append(
                        _action(
                            "UPDATE_PROGRESS",
                            row=row,
                            target_order_id=state.order_id,
                            target_task_id=task.id if task else "",
                            reason_code="SIGNED_EXPORT_PROGRESS_DELTA",
                            detail={
                                "excel_value": float(excel_completed),
                                "completed_at_export": float(exported_completed),
                                "signed_quantity": float(
                                    excel_completed - exported_completed
                                ),
                                "report_increment_total_at_export": float(
                                    exported_report_total
                                ),
                                "progress_adjustment_total_at_export": float(
                                    exported_adjustment_total
                                ),
                            },
                        )
                    )
            elif excel_completed != baseline:
                if excel_completed > baseline and report_total == 0 and adjustment_total == 0:
                    actions.append(
                        _action(
                            "UPDATE_PROGRESS",
                            row=row,
                            target_order_id=state.order_id,
                            target_task_id=task.id if task else "",
                            reason_code="SAFE_SOURCE_PROGRESS_DELTA",
                            detail={
                                "excel_value": float(excel_completed),
                                "takeover_baseline": float(baseline),
                                "report_increment_total": 0,
                                "progress_adjustment_total": 0,
                                "signed_quantity": float(excel_completed - baseline),
                            },
                        )
                    )
                else:
                    actions.append(
                        _action(
                            "CONFLICT",
                            row=row,
                            target_order_id=state.order_id,
                            target_task_id=task.id if task else "",
                            reason_code="EXTERNAL_PROGRESS_WATERMARK_UNTRUSTED",
                            detail={
                                "excel_value": float(excel_completed),
                                "takeover_baseline": float(baseline),
                                "report_increment_total": float(report_total),
                                "progress_adjustment_total": float(adjustment_total),
                                "system_completed": float(state.completed_quantity),
                            },
                        )
                    )
                    continue

        if row.get("classification") == "BACKLOG":
            if state is None:
                if stable_order not in seen_new_orders:
                    actions.append(_action("CREATE_ORDER", row=row))
                    seen_new_orders.add(stable_order)
                actions.append(_action("CREATE_BACKLOG_ORDER", row=row))
            else:
                unchanged = all(
                    (
                        _decimal(state.order_quantity)
                        == _decimal(row.get("order_quantity")),
                        state.delivery_start_date
                        == row.get("delivery_start_date", ""),
                        state.delivery_due_date == row.get("delivery_due_date", ""),
                        state.status == (
                            "COMPLETED"
                            if _decimal(state.completed_quantity)
                            >= _decimal(state.order_quantity)
                            else "BACKLOG"
                        ),
                    )
                )
                actions.append(
                    _action(
                        "SKIP_IDENTICAL" if unchanged else "UPDATE_NON_EXECUTED_BASELINE",
                        row=row,
                        target_order_id=state.order_id,
                        requires_publish=not unchanged,
                        reason_code="BACKLOG_OVERLAY_CHANGED" if not unchanged else "",
                    )
                )
            continue

        if task is None:
            if stable_order not in seen_new_orders and state is None:
                actions.append(_action("CREATE_ORDER", row=row))
                seen_new_orders.add(stable_order)
            actions.append(
                _action(
                    "CREATE_BASELINE_TASK",
                    row=row,
                    target_order_id=state.order_id if state else "",
                )
            )
            continue
        if _task_matches_row(task, row, machines, molds):
            actions.append(
                _action(
                    "SKIP_IDENTICAL",
                    row=row,
                    target_order_id=task.order_id,
                    target_task_id=task.id,
                )
            )
        elif (
            task.reported_quantity > 0
            or task.execution_status in {"RUNNING", "COMPLETED"}
        ):
            actions.append(
                _action(
                    "CONFLICT_REPORTED_OR_RUNNING_TASK",
                    row=row,
                    target_order_id=task.order_id,
                    target_task_id=task.id,
                    reason_code="EXECUTION_WATERMARK_PRESENT",
                )
            )
        else:
            actions.append(
                _action(
                    "UPDATE_NON_EXECUTED_BASELINE",
                    row=row,
                    target_order_id=task.order_id,
                    target_task_id=task.id,
                    requires_publish=True,
                    reason_code="LOCKED_BASELINE_CHANGED",
                )
            )

    profile_family = (normalized.get("profile") or {}).get("profile_family", "")
    for task in target_tasks:
        if (
            task.origin != "excel_baseline"
            or not task.stable_row_key
            or task.stable_row_key in incoming_row_keys
        ):
            continue
        if _task_source_profile_family(task) not in {"", profile_family}:
            continue
        if task.reported_quantity > 0 or task.execution_status in {"RUNNING", "COMPLETED"}:
            actions.append(
                _action(
                    "CONFLICT_REPORTED_OR_RUNNING_TASK",
                    target_order_id=task.order_id,
                    target_task_id=task.id,
                    reason_code="SOURCE_ROW_REMOVED_WITH_EXECUTION",
                    detail={"stable_row_key": task.stable_row_key},
                )
            )
        else:
            actions.append(
                _action(
                    "REMOVE_NON_EXECUTED_BASELINE",
                    target_order_id=task.order_id,
                    target_task_id=task.id,
                    requires_publish=True,
                    reason_code="SOURCE_ROW_REMOVED",
                    detail={"stable_row_key": task.stable_row_key},
                )
            )

    revision_digest, master_digest = _revision_snapshot(
        db,
        factory_id=factory_id,
        target_plan=draft,
        reference_plan=published,
    )
    rule = db.scalar(
        select(InjectionSchedulingRuleSet)
        .where(
            InjectionSchedulingRuleSet.factory_id == factory_id,
            InjectionSchedulingRuleSet.status == "active",
        )
        .order_by(InjectionSchedulingRuleSet.revision.desc())
    )
    plan_context = {
        "mode": (
            "MERGE_DRAFT"
            if draft is not None
            else "CREATE_SUCCESSOR_DRAFT"
            if published is not None
            else "CREATE_TAKEOVER_DRAFT"
        ),
        "target_draft_plan_id": draft.id if draft else "",
        "target_draft_plan_revision": draft.revision if draft else 0,
        "reference_published_plan_id": published.id if published else "",
        "reference_published_plan_revision": published.revision if published else 0,
        "reference_published_event_sequence": _latest_event_sequence(db, factory_id),
        "reference_report_watermark": _latest_report_event_sequence(db, factory_id),
        "order_task_revision_digest": revision_digest,
        "master_revision_digest": master_digest,
        "rule_revision": rule.revision if rule else 0,
    }
    action_payload = [
        {key: value for key, value in item.items() if key != "id"}
        for item in actions
    ]
    action_fingerprint = _hash(
        {"plan_context": plan_context, "actions": action_payload}
    )
    counts = Counter(item["action_type"] for item in actions)
    conflicts = sum(
        counts[item]
        for item in ("CONFLICT", "CONFLICT_REPORTED_OR_RUNNING_TASK")
    )
    return {
        "reconciliation_actions": actions,
        "action_fingerprint": action_fingerprint,
        "action_summary": dict(sorted(counts.items())),
        "plan_context": plan_context,
        "has_reconciliation_conflicts": conflicts > 0,
        "restricted_action_count": sum(item["requires_publish"] for item in actions),
    }


def _find_global_order(
    db: Session, factory_id: str, stable_order_key: str
) -> InjectionSchedulingOrder | None:
    matches = [
        item
        for item in db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id
            )
        ).all()
        if _lineage_stable_order(item) == stable_order_key
    ]
    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STABLE_ORDER_IDENTITY_AMBIGUOUS",
                "stable_order_key": stable_order_key,
                "order_ids": [item.id for item in matches],
            },
        )
    return matches[0] if matches else None


def _new_global_order(
    db: Session,
    *,
    factory_id: str,
    row: dict[str, Any],
    mold: InjectionSchedulingMold | None,
    user: AuthContext,
    timestamp: str,
) -> InjectionSchedulingOrder:
    completed = _decimal(row.get("completed_quantity"))
    quantity = _decimal(row.get("order_quantity"))
    order = InjectionSchedulingOrder(
        id=f"isorder-{uuid4().hex}",
        factory_id=factory_id,
        order_no=row.get("order_no", ""),
        item_no=row.get("item_no", ""),
        product_name=row.get("product_name", ""),
        mold_id=mold.id if mold else None,
        order_quantity=quantity,
        source_completed_quantity=completed,
        completed_quantity=completed,
        estimated_completion_at="",
        estimated_remaining_shifts=0,
        delivery_slack_days=None,
        delivery_start_date=row.get("delivery_start_date", ""),
        delivery_due_date=row.get("delivery_due_date", ""),
        priority_code=row.get("priority_code", "NORMAL"),
        material_readiness_status="unknown",
        warehouse_text=row.get("warehouse_text", ""),
        remark=row.get("remark", ""),
        source_type="excel_takeover",
        source_ref=f"{row['source'].get('sheet_name', '')}:{row['source'].get('source_row')}",
        source_version="canonical-v1",
        lineage_json=_json(
            {
                "stable_order_key": row.get("stable_order_key", ""),
                "profile_id": row["source"].get("profile_id"),
                "profile_revision": row["source"].get("profile_revision"),
            }
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
    return order


def _create_plan_state(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    order: InjectionSchedulingOrder,
    row: dict[str, Any],
    batch: InjectionSchedulingImportBatch,
    scheduled: bool,
    user: AuthContext,
    timestamp: str,
) -> InjectionSchedulingPlanOrderState:
    takeover = _decimal(row.get("completed_quantity"))
    quantity = _decimal(row.get("order_quantity"))
    state = InjectionSchedulingPlanOrderState(
        id=f"ispostate-{uuid4().hex}",
        factory_id=plan.factory_id,
        plan_id=plan.id,
        order_id=order.id,
        stable_order_key=row.get("stable_order_key", ""),
        order_quantity=quantity,
        delivery_start_date=row.get("delivery_start_date", ""),
        delivery_due_date=row.get("delivery_due_date", ""),
        takeover_source_completed_quantity=takeover,
        report_increment_total=Decimal(0),
        progress_adjustment_total=Decimal(0),
        completed_quantity=takeover,
        status=(
            "COMPLETED"
            if takeover >= quantity
            else "SCHEDULED"
            if scheduled
            else "BACKLOG"
        ),
        quantity_scope=(batch.profile_id and (row.get("quantity_scope") or "ORDER_CUMULATIVE"))
        or "ORDER_CUMULATIVE",
        source_batch_id=batch.id,
        source_sheet_name=row["source"].get("sheet_name", ""),
        source_row=row["source"].get("source_row"),
        source_profile_id=batch.profile_id,
        source_profile_revision=batch.profile_revision,
        source_lineage_json=_json(
            {
                "stable_order_key": row.get("stable_order_key", ""),
                "source_file_hash": batch.source_file_hash,
            }
        ),
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


def clone_successor_draft(
    db: Session,
    *,
    source: InjectionSchedulingPlan,
    business_date: str,
    user: AuthContext,
    timestamp: str,
    rollback_request_id: str | None = None,
) -> InjectionSchedulingPlan:
    event_watermark = _latest_event_sequence(db, source.factory_id)
    report_watermark = _latest_report_event_sequence(db, source.factory_id)
    draft = InjectionSchedulingPlan(
        id=f"isplan-{uuid4().hex}",
        factory_id=source.factory_id,
        business_date=business_date or source.business_date,
        status="DRAFT",
        revision=1,
        rule_set_id=source.rule_set_id,
        rule_revision=source.rule_revision,
        based_on_plan_id=source.id,
        based_on_event_sequence=event_watermark,
        based_on_report_watermark=report_watermark,
        export_profile_id=source.export_profile_id,
        export_profile_revision=source.export_profile_revision,
        export_profile_family=source.export_profile_family,
        export_renderer_code=source.export_renderer_code,
        export_binding_source=source.export_binding_source,
        calculation_version=source.calculation_version,
        rollback_request_id=rollback_request_id,
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
    db.add(draft)
    db.flush()
    source_states = {
        item.order_id: item for item in plan_order_states(db, source.factory_id, source.id)
    }
    source_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == source.factory_id,
                InjectionSchedulingTask.plan_id == source.id,
            )
            .order_by(InjectionSchedulingTask.machine_id, InjectionSchedulingTask.sequence_no)
        ).all()
    )
    order_ids = {item.order_id for item in source_tasks} | set(source_states)
    orders = {
        item.id: item
        for item in db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == source.factory_id,
                InjectionSchedulingOrder.id.in_(order_ids),
            )
        ).all()
    } if order_ids else {}
    for order_id in sorted(order_ids):
        source_state = source_states.get(order_id)
        order = orders[order_id]
        report_total = _decimal(
            db.scalar(
                select(func.coalesce(func.sum(InjectionSchedulingShiftReport.normalized_increment_quantity), 0))
                .join(InjectionSchedulingTask, InjectionSchedulingTask.id == InjectionSchedulingShiftReport.task_id)
                .where(
                    InjectionSchedulingTask.plan_id == source.id,
                    InjectionSchedulingShiftReport.factory_id == source.factory_id,
                    InjectionSchedulingShiftReport.order_id == order_id,
                )
            )
        )
        takeover = _decimal(
            source_state.takeover_source_completed_quantity
            if source_state is not None
            else order.source_completed_quantity
        )
        adjustments = _decimal(
            source_state.progress_adjustment_total if source_state is not None else 0
        )
        completed = max(takeover + report_total + adjustments, Decimal(0))
        quantity = _decimal(source_state.order_quantity if source_state else order.order_quantity)
        state = InjectionSchedulingPlanOrderState(
            id=f"ispostate-{uuid4().hex}",
            factory_id=source.factory_id,
            plan_id=draft.id,
            order_id=order_id,
            stable_order_key=(source_state.stable_order_key if source_state else _lineage_stable_order(order)),
            order_quantity=quantity,
            delivery_start_date=(source_state.delivery_start_date if source_state else order.delivery_start_date),
            delivery_due_date=(source_state.delivery_due_date if source_state else order.delivery_due_date),
            takeover_source_completed_quantity=takeover,
            report_increment_total=report_total,
            progress_adjustment_total=adjustments,
            completed_quantity=completed,
            status=("COMPLETED" if completed >= quantity else source_state.status if source_state else order.status),
            quantity_scope=source_state.quantity_scope if source_state else "ORDER_CUMULATIVE",
            source_batch_id=source_state.source_batch_id if source_state else None,
            source_sheet_name=source_state.source_sheet_name if source_state else "",
            source_row=source_state.source_row if source_state else None,
            source_profile_id=source_state.source_profile_id if source_state else None,
            source_profile_revision=source_state.source_profile_revision if source_state else None,
            source_lineage_json=_json(
                {
                    **(_load_json(source_state.source_lineage_json, {}) if source_state else {}),
                    "source_plan_order_state_id": source_state.id if source_state else "",
                    "source_plan_id": source.id,
                    "report_increment_at_clone": str(report_total),
                    "progress_adjustment_at_clone": str(adjustments),
                }
            ),
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
    for source_task in source_tasks:
        db.add(
            InjectionSchedulingTask(
                id=f"istask-{uuid4().hex}",
                factory_id=source.factory_id,
                plan_id=draft.id,
                machine_id=source_task.machine_id,
                order_id=source_task.order_id,
                mold_id=source_task.mold_id,
                mold_copy_no=source_task.mold_copy_no,
                sequence_no=source_task.sequence_no,
                execution_status=source_task.execution_status,
                planned_start=source_task.planned_start,
                planned_finish=source_task.planned_finish,
                shift_target_quantity=source_task.shift_target_quantity,
                reported_quantity=source_task.reported_quantity,
                estimated_start=source_task.estimated_start,
                estimated_finish=source_task.estimated_finish,
                estimated_remaining_shifts=source_task.estimated_remaining_shifts,
                delivery_slack_days=source_task.delivery_slack_days,
                locked=source_task.locked,
                manual_override_reason=source_task.manual_override_reason,
                active_execution=False,
                import_batch_id=source_task.import_batch_id,
                source_sheet_name=source_task.source_sheet_name,
                source_row=source_task.source_row,
                source_file_hash=source_task.source_file_hash,
                allocated_quantity=source_task.allocated_quantity,
                takeover_source_completed_quantity=source_task.takeover_source_completed_quantity,
                origin="successor_clone",
                stable_order_key=source_task.stable_order_key,
                stable_row_key=source_task.stable_row_key,
                source_task_id=source_task.id,
                inherited_report_counter=source_task.reported_quantity,
                completed_at_clone=source_task.reported_quantity,
                report_event_watermark=report_watermark,
                profile_id=source_task.profile_id,
                profile_revision=source_task.profile_revision,
                setup_minutes=source_task.setup_minutes,
                production_minutes=source_task.production_minutes,
                planned_downtime_minutes=source_task.planned_downtime_minutes,
                changeover_type=source_task.changeover_type,
                auto_schedule_run_id=None,
                auto_score=None,
                auto_explanation_json=_json(
                    {
                        **_load_json(source_task.auto_explanation_json, {}),
                        "source_lineage": {
                            "source_task_id": source_task.id,
                            "source_plan_id": source.id,
                            "profile_family": _task_source_profile_family(source_task),
                        },
                    }
                ),
                manual_adjusted=source_task.manual_adjusted,
                revision=1,
                created_by=user.id,
                created_by_name=_actor_name(user),
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    db.flush()
    return draft


def rebase_successor_draft(
    db: Session,
    *,
    draft: InjectionSchedulingPlan,
    source: InjectionSchedulingPlan,
    user: AuthContext,
    timestamp: str,
) -> dict[str, Any]:
    if draft.based_on_plan_id != source.id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUCCESSOR_BASE_PLAN_CHANGED",
                "message": "接班草稿引用的执行计划已变化，请重新创建草稿",
                "based_on_plan_id": draft.based_on_plan_id,
                "current_published_plan_id": source.id,
            },
        )
    source_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == draft.factory_id,
                InjectionSchedulingTask.plan_id == source.id,
            )
            .order_by(InjectionSchedulingTask.id)
            .with_for_update()
        ).all()
    )
    draft_tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == draft.factory_id,
                InjectionSchedulingTask.plan_id == draft.id,
            )
            .order_by(InjectionSchedulingTask.id)
            .with_for_update()
        ).all()
    )
    clone_by_source = {
        item.source_task_id: item for item in draft_tasks if item.source_task_id
    }
    running_conflicts: list[dict[str, Any]] = []
    protected_fields = (
        "machine_id",
        "mold_id",
        "mold_copy_no",
        "sequence_no",
        "planned_start",
        "planned_finish",
    )
    for source_task in source_tasks:
        clone = clone_by_source.get(source_task.id)
        if clone is None or source_task.execution_status != "RUNNING":
            continue
        changed = [
            field
            for field in protected_fields
            if getattr(clone, field) != getattr(source_task, field)
        ]
        if changed:
            running_conflicts.append(
                {
                    "source_task_id": source_task.id,
                    "successor_task_id": clone.id,
                    "changed_fields": changed,
                }
            )
    if running_conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUCCESSOR_RUNNING_TASK_CONFLICT",
                "message": "接班期间来源任务已进入 RUNNING，且草稿修改了其执行位置",
                "conflicts": running_conflicts,
            },
        )

    report_watermark = _latest_report_event_sequence(db, draft.factory_id)
    rebased_tasks = 0
    for source_task in source_tasks:
        clone = clone_by_source.get(source_task.id)
        if clone is None:
            continue
        changed = any(
            (
                clone.reported_quantity != source_task.reported_quantity,
                clone.inherited_report_counter != source_task.reported_quantity,
                source_task.execution_status in {"RUNNING", "COMPLETED"}
                and clone.execution_status != source_task.execution_status,
            )
        )
        clone.reported_quantity = source_task.reported_quantity
        clone.inherited_report_counter = source_task.reported_quantity
        clone.report_event_watermark = report_watermark
        if source_task.execution_status in {"RUNNING", "COMPLETED"}:
            clone.execution_status = source_task.execution_status
        if changed:
            clone.revision += 1
            clone.updated_by = user.id
            clone.updated_by_name = _actor_name(user)
            clone.updated_at = timestamp
            rebased_tasks += 1

    source_states = {
        item.order_id: item
        for item in db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(
                InjectionSchedulingPlanOrderState.factory_id == draft.factory_id,
                InjectionSchedulingPlanOrderState.plan_id == source.id,
            )
            .with_for_update()
        ).all()
    }
    draft_states = list(
        db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(
                InjectionSchedulingPlanOrderState.factory_id == draft.factory_id,
                InjectionSchedulingPlanOrderState.plan_id == draft.id,
            )
            .with_for_update()
        ).all()
    )
    scheduled_order_ids = {
        item.order_id
        for item in draft_tasks
        if item.execution_status != "CANCELLED"
    }
    rebased_states = 0
    for state in draft_states:
        source_state = source_states.get(state.order_id)
        if source_state is None:
            continue
        lineage = _load_json(state.source_lineage_json, {})
        cloned_adjustment = _decimal(lineage.get("progress_adjustment_at_clone", 0))
        local_adjustment = _decimal(state.progress_adjustment_total) - cloned_adjustment
        state.report_increment_total = source_state.report_increment_total
        state.progress_adjustment_total = (
            _decimal(source_state.progress_adjustment_total) + local_adjustment
        )
        state.completed_quantity = max(
            _decimal(state.takeover_source_completed_quantity)
            + _decimal(state.report_increment_total)
            + _decimal(state.progress_adjustment_total),
            Decimal(0),
        )
        state.status = (
            "COMPLETED"
            if state.completed_quantity >= state.order_quantity
            else "SCHEDULED"
            if state.order_id in scheduled_order_ids
            else "BACKLOG"
        )
        lineage.update(
            report_increment_at_clone=str(source_state.report_increment_total),
            progress_adjustment_at_clone=str(source_state.progress_adjustment_total),
            rebased_from_event_sequence=_latest_event_sequence(
                db, draft.factory_id
            ),
        )
        state.source_lineage_json = _json(lineage)
        state.revision += 1
        state.updated_by = user.id
        state.updated_by_name = _actor_name(user)
        state.updated_at = timestamp
        rebased_states += 1
    draft.based_on_event_sequence = _latest_event_sequence(db, draft.factory_id)
    draft.based_on_report_watermark = report_watermark
    db.flush()
    return {
        "rebased_task_count": rebased_tasks,
        "rebased_order_state_count": rebased_states,
        "report_watermark": report_watermark,
    }


def prepare_takeover_plan(
    db: Session,
    *,
    factory_id: str,
    business_date: str,
    user: AuthContext,
    timestamp: str,
) -> tuple[InjectionSchedulingPlan, bool, bool]:
    published, draft = explicit_plan_context(db, factory_id)
    if draft is not None:
        return draft, False, False
    if published is not None:
        locked_published = db.scalar(
            select(InjectionSchedulingPlan)
            .where(InjectionSchedulingPlan.id == published.id)
            .with_for_update()
        )
        if locked_published is None or locked_published.status != "PUBLISHED":
            raise HTTPException(status_code=409, detail="执行计划已变化，请重新预览")
        return (
            clone_successor_draft(
                db,
                source=locked_published,
                business_date=business_date,
                user=user,
                timestamp=timestamp,
            ),
            True,
            True,
        )
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
    draft = InjectionSchedulingPlan(
        id=f"isplan-{uuid4().hex}",
        factory_id=factory_id,
        business_date=business_date,
        status="DRAFT",
        revision=1,
        rule_set_id=rules.id,
        rule_revision=rules.revision,
        based_on_plan_id="",
        based_on_event_sequence=0,
        based_on_report_watermark=0,
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
    db.add(draft)
    db.flush()
    return draft, True, False


def _progress_adjustment(
    db: Session,
    *,
    state: InjectionSchedulingPlanOrderState,
    task_id: str | None,
    signed_quantity: Decimal,
    reason: str,
    source_kind: str,
    request_id: str,
    user: AuthContext,
    timestamp: str,
    batch: InjectionSchedulingImportBatch | None = None,
    source_sheet_name: str = "",
    source_row: int | None = None,
    payload_hash: str | None = None,
) -> InjectionSchedulingProgressAdjustment:
    before = _decimal(state.completed_quantity)
    after = before + signed_quantity
    if after < 0:
        raise HTTPException(status_code=409, detail="进度更正后完成量不能为负数")
    payload = {
        "plan_id": state.plan_id,
        "order_id": state.order_id,
        "task_id": task_id,
        "signed_quantity": str(signed_quantity),
        "before": str(before),
        "after": str(after),
        "reason": reason,
        "source_kind": source_kind,
        "source_batch_id": batch.id if batch else None,
    }
    record = InjectionSchedulingProgressAdjustment(
        id=f"isadjust-{uuid4().hex}",
        factory_id=state.factory_id,
        plan_id=state.plan_id,
        order_id=state.order_id,
        task_id=task_id,
        signed_quantity=signed_quantity,
        before_quantity=before,
        after_quantity=after,
        reason=reason,
        source_kind=source_kind,
        source_batch_id=batch.id if batch else None,
        source_sheet_name=source_sheet_name,
        source_row=source_row,
        request_id=request_id,
        payload_hash=payload_hash or _hash(payload),
        adjusted_by=user.id,
        adjusted_by_name=_actor_name(user),
        created_at=timestamp,
    )
    db.add(record)
    state.progress_adjustment_total = (
        _decimal(state.progress_adjustment_total) + signed_quantity
    )
    state.completed_quantity = after
    has_scheduled_task = db.scalar(
        select(InjectionSchedulingTask.id).where(
            InjectionSchedulingTask.factory_id == state.factory_id,
            InjectionSchedulingTask.plan_id == state.plan_id,
            InjectionSchedulingTask.order_id == state.order_id,
            InjectionSchedulingTask.execution_status != "CANCELLED",
        )
    )
    state.status = (
        "COMPLETED"
        if after >= _decimal(state.order_quantity)
        else "SCHEDULED"
        if has_scheduled_task is not None
        else "BACKLOG"
    )
    state.revision += 1
    state.updated_by = user.id
    state.updated_by_name = _actor_name(user)
    state.updated_at = timestamp
    db.flush()
    return record


def apply_takeover_actions(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    batch: InjectionSchedulingImportBatch,
    normalized: dict[str, Any],
    actions: list[dict[str, Any]],
    action_reasons: dict[str, str],
    can_publish: bool,
    user: AuthContext,
    timestamp: str,
) -> dict[str, Any]:
    restricted = [item for item in actions if item.get("requires_publish")]
    if restricted and not can_publish:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PUBLISH_PERMISSION_REQUIRED",
                "action_ids": [item["id"] for item in restricted],
            },
        )
    missing_reasons = [
        item["id"]
        for item in restricted
        if not 4 <= len(action_reasons.get(item["id"], "")) <= 500
    ]
    if missing_reasons:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ACTION_REASON_REQUIRED",
                "action_ids": missing_reasons,
            },
        )
    conflicts = [
        item
        for item in actions
        if item["action_type"] in {"CONFLICT", "CONFLICT_REPORTED_OR_RUNNING_TASK"}
    ]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RECONCILIATION_CONFLICT",
                "action_ids": [item["id"] for item in conflicts],
            },
        )

    rows = {
        item.get("stable_row_key") or f"order:{item.get('stable_order_key')}": item
        for item in [
            *normalized.get("scheduled_baseline_tasks", []),
            *normalized.get("backlog_orders", []),
        ]
    }
    machines = {
        item.machine_code: item
        for item in db.scalars(
            select(InjectionSchedulingMachine).where(
                InjectionSchedulingMachine.factory_id == plan.factory_id
            )
        ).all()
    }
    molds = {
        item.mold_no: item
        for item in db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == plan.factory_id
            )
        ).all()
    }
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(
                InjectionSchedulingTask.factory_id == plan.factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
            .with_for_update()
        ).all()
    )
    states = list(
        db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(
                InjectionSchedulingPlanOrderState.factory_id == plan.factory_id,
                InjectionSchedulingPlanOrderState.plan_id == plan.id,
            )
            .with_for_update()
        ).all()
    )
    task_by_row = {item.stable_row_key: item for item in tasks if item.stable_row_key}
    state_by_order = {item.stable_order_key: item for item in states}
    max_sequences: defaultdict[str, int] = defaultdict(lambda: -1)
    for task in tasks:
        max_sequences[task.machine_id] = max(max_sequences[task.machine_id], task.sequence_no)

    result_counts: Counter[str] = Counter()
    order_cache: dict[str, InjectionSchedulingOrder] = {}
    for action in actions:
        action_type = action["action_type"]
        result_counts[action_type] += 1
        if action_type in {"CREATE_ORDER", "SKIP_IDENTICAL"}:
            continue
        stable_row = action.get("stable_row_key", "")
        stable_order = action.get("stable_order_key", "")
        row = rows.get(stable_row or f"order:{stable_order}")
        state = state_by_order.get(stable_order)
        task = task_by_row.get(stable_row)
        if action_type == "REMOVE_NON_EXECUTED_BASELINE":
            task = next(
                (
                    item
                    for item in tasks
                    if item.id == action["target_task_id"]
                    or item.source_task_id == action["target_task_id"]
                    or (
                        stable_row
                        and item.stable_row_key == stable_row
                    )
                ),
                None,
            )
            if task is None:
                raise HTTPException(status_code=409, detail="待取消基线任务已变化")
            if task.reported_quantity > 0 or task.execution_status in {"RUNNING", "COMPLETED"}:
                raise HTTPException(status_code=409, detail="已有执行水位的基线不能取消")
            task.execution_status = "CANCELLED"
            task.revision += 1
            task.manual_override_reason = action_reasons[action["id"]]
            task.updated_by = user.id
            task.updated_by_name = _actor_name(user)
            task.updated_at = timestamp
            continue
        if row is None:
            raise HTTPException(status_code=409, detail="对账动作缺少来源规范行")
        mold = molds.get(row.get("mold_no", ""))
        if row.get("mold_no") and mold is None:
            raise HTTPException(status_code=409, detail="来源模具尚未通过主数据审批")
        order = order_cache.get(stable_order)
        if order is None:
            order = _find_global_order(db, plan.factory_id, stable_order)
            if order is None:
                order = _new_global_order(
                    db,
                    factory_id=plan.factory_id,
                    row=row,
                    mold=mold,
                    user=user,
                    timestamp=timestamp,
                )
            order_cache[stable_order] = order
        if state is None:
            state = _create_plan_state(
                db,
                plan=plan,
                order=order,
                row=row,
                batch=batch,
                scheduled=action_type == "CREATE_BASELINE_TASK",
                user=user,
                timestamp=timestamp,
            )
            state_by_order[stable_order] = state

        if action_type == "CREATE_BACKLOG_ORDER":
            continue
        if action_type == "UPDATE_PROGRESS":
            delta = _decimal(action.get("detail", {}).get("signed_quantity"))
            _progress_adjustment(
                db,
                state=state,
                task_id=task.id if task else None,
                signed_quantity=delta,
                reason="来源文件安全进度差量",
                source_kind="IMPORT_RECONCILIATION",
                request_id=f"{batch.id}:{action['id']}",
                user=user,
                timestamp=timestamp,
                batch=batch,
                source_sheet_name=row["source"].get("sheet_name", ""),
                source_row=row["source"].get("source_row"),
            )
            continue
        machine = machines.get(row.get("machine_code", ""))
        if action_type in {"CREATE_BASELINE_TASK", "UPDATE_NON_EXECUTED_BASELINE"} and machine is None:
            raise HTTPException(status_code=409, detail="来源机台尚未通过主数据审批")
        if action_type == "UPDATE_NON_EXECUTED_BASELINE":
            state.order_quantity = _decimal(row.get("order_quantity"))
            state.delivery_start_date = row.get("delivery_start_date", "")
            state.delivery_due_date = row.get("delivery_due_date", "")
            state.revision += 1
            state.updated_by = user.id
            state.updated_by_name = _actor_name(user)
            state.updated_at = timestamp
            if task is not None:
                if task.reported_quantity > 0 or task.execution_status in {"RUNNING", "COMPLETED"}:
                    raise HTTPException(status_code=409, detail="已有执行水位的基线不能更新")
                task.machine_id = machine.id
                task.mold_id = mold.id if mold else None
                task.planned_start = row.get("planned_start", "")
                task.planned_finish = row.get("planned_finish", "")
                task.allocated_quantity = _decimal(row.get("planned_quantity"))
                task.manual_override_reason = action_reasons[action["id"]]
                task.revision += 1
                task.updated_by = user.id
                task.updated_by_name = _actor_name(user)
                task.updated_at = timestamp
            continue
        if action_type != "CREATE_BASELINE_TASK":
            continue
        target_quantity = _decimal(row.get("shift_target_quantity"))
        max_sequences[machine.id] += 1
        allocated = _decimal(row.get("planned_quantity"))
        if allocated <= 0:
            allocated = max(
                _decimal(row.get("order_quantity"))
                - _decimal(row.get("completed_quantity")),
                Decimal(0),
            )
        source_lineage = {
            "profile_family": (normalized.get("profile") or {}).get("profile_family", ""),
            "stable_order_key": stable_order,
            "stable_row_key": stable_row,
            "field_lineage": row["source"].get("field_lineage", {}),
        }
        task = InjectionSchedulingTask(
            id=f"istask-{uuid4().hex}",
            factory_id=plan.factory_id,
            plan_id=plan.id,
            machine_id=machine.id,
            order_id=order.id,
            mold_id=mold.id if mold else None,
            mold_copy_no=1,
            sequence_no=max_sequences[machine.id],
            execution_status=row.get("execution_status", "QUEUED"),
            planned_start=row.get("planned_start", ""),
            planned_finish=row.get("planned_finish", ""),
            shift_target_quantity=target_quantity,
            reported_quantity=Decimal(0),
            estimated_start=row.get("planned_start", ""),
            estimated_finish=row.get("planned_finish", ""),
            estimated_remaining_shifts=_remaining_shifts(order, target_quantity),
            delivery_slack_days=_delivery_slack_days(
                state.delivery_due_date, row.get("planned_finish", "")
            ),
            locked=True,
            manual_override_reason=f"Imported baseline: {batch.id}",
            active_execution=False,
            import_batch_id=batch.id,
            source_sheet_name=row["source"].get("sheet_name", ""),
            source_row=row["source"].get("source_row"),
            source_file_hash=batch.source_file_hash,
            allocated_quantity=allocated,
            takeover_source_completed_quantity=_decimal(row.get("completed_quantity")),
            origin="excel_baseline",
            stable_order_key=stable_order,
            stable_row_key=stable_row,
            source_task_id=None,
            inherited_report_counter=Decimal(0),
            completed_at_clone=Decimal(0),
            report_event_watermark=0,
            profile_id=batch.profile_id,
            profile_revision=batch.profile_revision,
            setup_minutes=0,
            production_minutes=0,
            planned_downtime_minutes=0,
            changeover_type="",
            auto_schedule_run_id=None,
            auto_score=None,
            auto_explanation_json=_json({"source_lineage": source_lineage}),
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
        task_by_row[stable_row] = task
        state.status = (
            "COMPLETED"
            if state.completed_quantity >= state.order_quantity
            else "SCHEDULED"
        )
    db.flush()
    return {"action_counts": dict(sorted(result_counts.items()))}


def manual_progress_adjustment(
    db: Session,
    *,
    factory_id: str,
    plan_id: str,
    order_id: str,
    task_id: str | None,
    expected_state_revision: int,
    signed_quantity: Decimal,
    reason: str,
    request_id: str,
    user: AuthContext,
) -> tuple[
    InjectionSchedulingProgressAdjustment,
    InjectionSchedulingPlanOrderState,
    int,
    bool,
]:
    replay = db.scalar(
        select(InjectionSchedulingProgressAdjustment).where(
            InjectionSchedulingProgressAdjustment.factory_id == factory_id,
            InjectionSchedulingProgressAdjustment.request_id == request_id,
        )
    )
    payload_hash = _hash(
        {
            "factory_id": factory_id,
            "plan_id": plan_id,
            "order_id": order_id,
            "task_id": task_id,
            "expected_state_revision": expected_state_revision,
            "signed_quantity": str(signed_quantity),
            "reason": reason,
        }
    )
    if replay is not None:
        if replay.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="相同 request_id 已用于其他进度更正")
        state = db.scalar(
            select(InjectionSchedulingPlanOrderState).where(
                InjectionSchedulingPlanOrderState.plan_id == replay.plan_id,
                InjectionSchedulingPlanOrderState.order_id == replay.order_id,
            )
        )
        audit = db.scalar(
            select(InjectionSchedulingAuditEvent).where(
                InjectionSchedulingAuditEvent.factory_id == factory_id,
                InjectionSchedulingAuditEvent.request_id == request_id,
                InjectionSchedulingAuditEvent.event_type == "progress_adjusted",
            )
        )
        if state is None or audit is None:
            raise HTTPException(status_code=409, detail="进度更正幂等记录不完整")
        return replay, state, audit.sequence, True
    plan = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.id == plan_id,
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
        .with_for_update()
    )
    if plan is None:
        raise HTTPException(status_code=409, detail="只能更正当前 PUBLISHED 执行计划进度")
    state = db.scalar(
        select(InjectionSchedulingPlanOrderState)
        .where(
            InjectionSchedulingPlanOrderState.factory_id == factory_id,
            InjectionSchedulingPlanOrderState.plan_id == plan_id,
            InjectionSchedulingPlanOrderState.order_id == order_id,
        )
        .with_for_update()
    )
    if state is None:
        raise HTTPException(status_code=404, detail="计划级订单状态不存在")
    if state.revision != expected_state_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "计划级订单状态已变化",
                "expected_revision": expected_state_revision,
                "current_revision": state.revision,
            },
        )
    if task_id:
        task = db.scalar(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.id == task_id,
                InjectionSchedulingTask.plan_id == plan_id,
                InjectionSchedulingTask.order_id == order_id,
            )
        )
        if task is None:
            raise HTTPException(status_code=404, detail="进度更正任务不属于指定计划订单")
    timestamp = _now()
    record = _progress_adjustment(
        db,
        state=state,
        task_id=task_id,
        signed_quantity=signed_quantity,
        reason=reason,
        source_kind="MANUAL_CORRECTION",
        request_id=request_id,
        user=user,
        timestamp=timestamp,
        payload_hash=payload_hash,
    )
    audit = _audit(
        db,
        factory_id=factory_id,
        event_type="progress_adjusted",
        entity_type="plan_order_state",
        entity_id=state.id,
        entity_revision=state.revision,
        request_id=request_id,
        detail={
            "adjustment_id": record.id,
            "plan_id": plan_id,
            "order_id": order_id,
            "task_id": task_id,
            "signed_quantity": float(signed_quantity),
            "before_quantity": float(record.before_quantity),
            "after_quantity": float(record.after_quantity),
            "reason": reason,
        },
        user=user,
    )
    db.commit()
    return record, state, audit.sequence, False
