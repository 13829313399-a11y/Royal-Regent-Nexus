from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
    InjectionSchedulingRuleSet,
)
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_import import (
    InjectionSchedulingImportBatch,
    InjectionSchedulingImportIssue,
)
from app.schemas.injection_scheduling_import import (
    InjectionSchedulingImportBatchOut,
    InjectionSchedulingImportConfirm,
    InjectionSchedulingImportIssueOut,
    InjectionSchedulingImportTaskPreview,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import require_injection_scheduling_factory
from app.services.injection_scheduling_excel import (
    parse_injection_scheduling_workbook,
)
from app.services.injection_scheduling_execution import (
    _actor_name,
    _audit,
    _delivery_slack_days,
    _now,
    _record_plan_revision,
    _remaining_shifts,
    _validate_schedule_conflicts,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _payload_hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decimal(value: float | str | None) -> Decimal:
    return Decimal(str(value or 0))


def _issue_out(record: InjectionSchedulingImportIssue) -> InjectionSchedulingImportIssueOut:
    return InjectionSchedulingImportIssueOut(
        id=record.id,
        severity=record.severity,
        code=record.code,
        message=record.message,
        sheet_name=record.sheet_name,
        source_row=record.source_row,
        field_name=record.field_name,
        cell_ref=record.cell_ref,
        raw_value=record.raw_value,
        formula_text=record.formula_text,
        blocking=record.blocking,
    )


def _task_preview(task: dict[str, Any]) -> InjectionSchedulingImportTaskPreview:
    return InjectionSchedulingImportTaskPreview(
        machine_code=task["machine_code"],
        sequence_no=task["sequence_no"],
        execution_status=task["execution_status"],
        status_inferred=task["status_inferred"],
        legacy_marker=task["legacy_marker"],
        mold_no=task["mold_no"],
        product_name=task["product_name"],
        order_no=task["order_no"],
        item_no=task["item_no"],
        order_quantity=task["order_quantity"],
        completed_quantity=task["completed_quantity"],
        shift_target_quantity=task["shift_target_quantity"],
        delivery_due_date=task["delivery_due_date"],
        planned_start=task["planned_start"],
        planned_finish=task["planned_finish"],
        priority_code=task["priority_code"],
        source=task["source"],
    )


def import_batch_out(
    db: Session,
    record: InjectionSchedulingImportBatch,
    *,
    idempotent_replay: bool = False,
) -> InjectionSchedulingImportBatchOut:
    normalized = _load_json(record.normalized_json, {})
    issues = list(
        db.scalars(
            select(InjectionSchedulingImportIssue)
            .where(InjectionSchedulingImportIssue.batch_id == record.id)
            .order_by(
                InjectionSchedulingImportIssue.blocking.desc(),
                InjectionSchedulingImportIssue.source_row,
                InjectionSchedulingImportIssue.id,
            )
        ).all()
    )
    return InjectionSchedulingImportBatchOut(
        id=record.id,
        factory_id=record.factory_id,
        source_file_name=record.source_file_name,
        source_file_hash=record.source_file_hash,
        source_size_bytes=record.source_size_bytes,
        parser_version=record.parser_version,
        preview_schema_version=record.preview_schema_version,
        normalized_sha256=record.normalized_sha256,
        summary=_load_json(record.summary_json, {}),
        status=record.status,
        revision=record.revision,
        preview_request_id=record.preview_request_id,
        confirm_request_id=record.confirm_request_id,
        confirm_mode=record.confirm_mode,
        confirmed_plan_id=record.confirmed_plan_id,
        confirmed_plan_revision=record.confirmed_plan_revision,
        result=_load_json(record.result_json, {}),
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        created_at=record.created_at,
        confirmed_by=record.confirmed_by,
        confirmed_by_name=record.confirmed_by_name,
        confirmed_at=record.confirmed_at,
        issues=[_issue_out(item) for item in issues],
        tasks=[_task_preview(item) for item in normalized.get("tasks", [])],
        idempotent_replay=idempotent_replay,
    )


def preview_import(
    db: Session,
    *,
    factory_id: str,
    expected_revision: int,
    source_file_name: str,
    content: bytes,
    preview_request_id: str,
    user: AuthContext,
) -> tuple[InjectionSchedulingImportBatch, bool]:
    factory_id = require_injection_scheduling_factory(factory_id)
    if expected_revision != 0:
        raise HTTPException(status_code=409, detail="新导入预览 expected_revision 必须为 0")
    normalized, issues = parse_injection_scheduling_workbook(content, source_file_name)
    preview_payload_hash = _payload_hash(
        {
            "factory_id": factory_id,
            "expected_revision": expected_revision,
            "source_file_name": source_file_name,
            "source_file_hash": normalized["source_file_hash"],
        }
    )
    existing = db.scalar(
        select(InjectionSchedulingImportBatch).where(
            InjectionSchedulingImportBatch.factory_id == factory_id,
            InjectionSchedulingImportBatch.preview_request_id == preview_request_id,
        )
    )
    if existing is not None:
        if existing.preview_payload_hash != preview_payload_hash:
            raise HTTPException(
                status_code=409,
                detail="相同预览 request_id 已用于不同文件，请更换 request_id",
            )
        return existing, True

    timestamp = _now()
    record = InjectionSchedulingImportBatch(
        id=f"isimport-{uuid4().hex}",
        factory_id=factory_id,
        source_file_name=source_file_name[:255],
        source_file_hash=normalized["source_file_hash"],
        source_size_bytes=normalized["source_size_bytes"],
        plan_sheet_name="计划表",
        parser_version=normalized["parser_version"],
        preview_schema_version=normalized["schema_version"],
        normalized_json=_json(normalized),
        normalized_sha256=normalized["normalized_sha256"],
        summary_json=_json(normalized["summary"]),
        issue_count=normalized["summary"]["issue_count"],
        blocking_issue_count=normalized["summary"]["blocking_issue_count"],
        status="PREVIEW",
        revision=1,
        preview_request_id=preview_request_id,
        preview_payload_hash=preview_payload_hash,
        confirm_request_id=None,
        confirm_payload_hash="",
        confirm_mode="",
        confirmed_plan_id="",
        confirmed_plan_revision=0,
        result_json="{}",
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=timestamp,
        confirmed_by="",
        confirmed_by_name="",
        confirmed_at="",
    )
    db.add(record)
    for issue in issues:
        db.add(
            InjectionSchedulingImportIssue(
                id=f"isissue-{uuid4().hex}",
                batch_id=record.id,
                factory_id=factory_id,
                severity=issue["severity"],
                code=issue["code"],
                message=issue["message"],
                sheet_name=issue["sheet_name"],
                source_row=issue["source_row"],
                field_name=issue["field_name"],
                cell_ref=issue["cell_ref"],
                raw_value=issue["raw_value"],
                formula_text=issue["formula_text"],
                blocking=issue["blocking"],
                created_at=timestamp,
            )
        )
    try:
        db.flush()
        _audit(
            db,
            factory_id=factory_id,
            event_type="import_preview_created",
            entity_type="import_batch",
            entity_id=record.id,
            entity_revision=1,
            request_id=preview_request_id,
            detail={
                "source_file_hash": record.source_file_hash,
                "summary": normalized["summary"],
            },
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(InjectionSchedulingImportBatch).where(
                InjectionSchedulingImportBatch.factory_id == factory_id,
                InjectionSchedulingImportBatch.preview_request_id == preview_request_id,
            )
        )
        if replay is not None and replay.preview_payload_hash == preview_payload_hash:
            return replay, True
        raise HTTPException(status_code=409, detail="导入预览写入冲突") from exc
    return record, False


def _create_missing_masters(
    db: Session,
    *,
    factory_id: str,
    normalized: dict[str, Any],
    user: AuthContext,
    timestamp: str,
) -> tuple[dict[str, InjectionSchedulingMachine], dict[str, InjectionSchedulingMold], int, int]:
    machines = {
        item.machine_code: item
        for item in db.scalars(
            select(InjectionSchedulingMachine).where(
                InjectionSchedulingMachine.factory_id == factory_id
            )
        ).all()
    }
    created_machines = 0
    for source in normalized.get("machines", []):
        code = source["machine_code"]
        if code in machines:
            continue
        record = InjectionSchedulingMachine(
            id=f"ismachine-{uuid4().hex}",
            factory_id=factory_id,
            machine_code=code,
            area=source.get("area", ""),
            position=source.get("position", ""),
            machine_class=source.get("machine_class", ""),
            clamping_force_tons=source.get("clamping_force_tons"),
            injection_capacity_g=source.get("injection_capacity_g"),
            tie_bar_x_mm=source.get("tie_bar_x_mm"),
            tie_bar_y_mm=source.get("tie_bar_y_mm"),
            platen_x_mm=None,
            platen_y_mm=None,
            min_mold_thickness_mm=None,
            max_mold_thickness_mm=None,
            opening_stroke_mm=None,
            machine_type=source.get("machine_type", "standard"),
            robot_capabilities_json=_json(source.get("robot_capabilities", [])),
            fixture_capabilities_json=_json(source.get("fixture_capabilities", [])),
            process_restrictions_json=_json(source.get("process_restrictions", [])),
            status=source.get("status", "available"),
            revision=1,
            created_by=user.id,
            created_by_name=_actor_name(user),
            updated_by=user.id,
            updated_by_name=_actor_name(user),
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(record)
        machines[code] = record
        created_machines += 1

    molds = {
        item.mold_no: item
        for item in db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == factory_id
            )
        ).all()
    }
    created_molds = 0
    for source in normalized.get("molds", []):
        mold_no = source["mold_no"]
        if mold_no in molds:
            continue
        record = InjectionSchedulingMold(
            id=f"ismold-{uuid4().hex}",
            factory_id=factory_id,
            mold_no=mold_no,
            name=source.get("name", ""),
            length_mm=source.get("length_mm"),
            width_mm=source.get("width_mm"),
            height_mm=source.get("height_mm"),
            weight_kg=source.get("weight_kg"),
            recommended_machine_class=source.get("recommended_machine_class", ""),
            whole_shot_net_weight_g=source.get("whole_shot_net_weight_g"),
            whole_shot_gross_weight_g=source.get("whole_shot_gross_weight_g"),
            required_arm_type=source.get("required_arm_type", "none"),
            required_fixture_type=source.get("required_fixture_type", ""),
            material_code=source.get("material_code", ""),
            material_name=source.get("material_name", ""),
            color_profile=source.get("color_profile", ""),
            process_requirements_json=_json(source.get("process_requirements", [])),
            copy_count=source.get("copy_count", 1),
            data_quality_status=source.get("data_quality_status", "needs_review"),
            status=source.get("status", "available"),
            revision=1,
            created_by=user.id,
            created_by_name=_actor_name(user),
            updated_by=user.id,
            updated_by_name=_actor_name(user),
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(record)
        molds[mold_no] = record
        created_molds += 1
    db.flush()
    return machines, molds, created_machines, created_molds


def _prepare_plan(
    db: Session,
    *,
    factory_id: str,
    payload: InjectionSchedulingImportConfirm,
    user: AuthContext,
    timestamp: str,
) -> tuple[InjectionSchedulingPlan, bool]:
    draft = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
    )
    if payload.confirm_mode == "create_draft":
        if draft is not None:
            raise HTTPException(status_code=409, detail="当前厂区已有草案，请改用合并草案")
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
            business_date=payload.business_date.isoformat(),
            status="DRAFT",
            revision=1,
            rule_set_id=rules.id,
            rule_revision=rules.revision,
            based_on_plan_id="",
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
        return draft, True
    if draft is None:
        raise HTTPException(status_code=409, detail="当前厂区没有可合并的草案")
    if draft.revision != payload.expected_plan_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "排产草案已被其他操作更新",
                "expected_revision": payload.expected_plan_revision,
                "current_revision": draft.revision,
            },
        )
    return draft, False


def _order_business_key(
    *,
    order_no: str,
    item_no: str,
    mold_id: str | None,
    product_name: str,
    order_quantity: Decimal,
) -> tuple[str, str, str, str, str]:
    return (
        order_no,
        item_no,
        mold_id or "",
        product_name,
        format(order_quantity.normalize(), "f"),
    )


def confirm_import(
    db: Session,
    batch_id: str,
    payload: InjectionSchedulingImportConfirm,
    user: AuthContext,
) -> tuple[InjectionSchedulingImportBatch, bool]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    confirm_payload_hash = _payload_hash(payload.model_dump(mode="json"))
    request_owner = db.scalar(
        select(InjectionSchedulingImportBatch).where(
            InjectionSchedulingImportBatch.factory_id == factory_id,
            InjectionSchedulingImportBatch.confirm_request_id == payload.request_id,
        )
    )
    if request_owner is not None and request_owner.id != batch_id:
        if request_owner.confirm_payload_hash == confirm_payload_hash:
            return request_owner, True
        raise HTTPException(
            status_code=409,
            detail="相同确认 request_id 已用于其他导入批次",
        )
    batch = db.scalar(
        select(InjectionSchedulingImportBatch).where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status == "CONFIRMED":
        if (
            batch.confirm_request_id == payload.request_id
            and batch.confirm_payload_hash == confirm_payload_hash
        ):
            return batch, True
        raise HTTPException(status_code=409, detail="导入批次已经确认写入")
    if batch.revision != payload.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "导入批次已被其他操作更新",
                "expected_revision": payload.expected_revision,
                "current_revision": batch.revision,
            },
        )
    blocking_issue_ids = set(
        db.scalars(
            select(InjectionSchedulingImportIssue.id).where(
                InjectionSchedulingImportIssue.batch_id == batch.id,
                InjectionSchedulingImportIssue.blocking.is_(True),
            )
        ).all()
    )
    acknowledged = set(payload.acknowledged_blocking_issue_ids)
    unknown_ids = acknowledged - blocking_issue_ids
    if unknown_ids:
        raise HTTPException(
            status_code=422,
            detail={"message": "包含不属于本批次的阻断问题 ID", "issue_ids": sorted(unknown_ids)},
        )
    unacknowledged = blocking_issue_ids - acknowledged
    if unacknowledged:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "仍有未确认的阻断问题；这些源行不会被写入",
                "unacknowledged_issue_ids": sorted(unacknowledged),
            },
        )
    normalized = _load_json(batch.normalized_json, {})
    normalized_copy = dict(normalized)
    expected_normalized_sha256 = normalized_copy.pop("normalized_sha256", "")
    if _payload_hash(normalized_copy) != expected_normalized_sha256:
        raise HTTPException(status_code=409, detail="导入预览内容校验失败，请重新上传")
    if not normalized.get("tasks"):
        raise HTTPException(status_code=409, detail="导入预览没有可写入的有效任务")

    timestamp = _now()
    try:
        machines, molds, created_machines, created_molds = _create_missing_masters(
            db,
            factory_id=factory_id,
            normalized=normalized,
            user=user,
            timestamp=timestamp,
        )
        plan, created_plan = _prepare_plan(
            db,
            factory_id=factory_id,
            payload=payload,
            user=user,
            timestamp=timestamp,
        )
        existing_source_rows = set(
            db.scalars(
                select(InjectionSchedulingTask.source_row).where(
                    InjectionSchedulingTask.factory_id == factory_id,
                    InjectionSchedulingTask.plan_id == plan.id,
                    InjectionSchedulingTask.source_file_hash == batch.source_file_hash,
                    InjectionSchedulingTask.source_sheet_name == "计划表",
                    InjectionSchedulingTask.source_row.is_not(None),
                )
            ).all()
        )
        max_sequences = defaultdict(lambda: -1)
        for machine_id, sequence_no in db.execute(
            select(
                InjectionSchedulingTask.machine_id,
                func.max(InjectionSchedulingTask.sequence_no),
            )
            .where(
                InjectionSchedulingTask.factory_id == factory_id,
                InjectionSchedulingTask.plan_id == plan.id,
            )
            .group_by(InjectionSchedulingTask.machine_id)
        ):
            max_sequences[machine_id] = sequence_no

        existing_orders_by_key: defaultdict[
            tuple[str, str, str, str, str], list[InjectionSchedulingOrder]
        ] = defaultdict(list)
        for order in db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id
            )
        ).all():
            existing_orders_by_key[
                _order_business_key(
                    order_no=order.order_no,
                    item_no=order.item_no,
                    mold_id=order.mold_id,
                    product_name=order.product_name,
                    order_quantity=order.order_quantity,
                )
            ].append(order)

        created_orders = 0
        reused_orders = 0
        created_tasks = 0
        skipped_tasks = 0
        order_cache: dict[tuple[str, str, str, str, str], InjectionSchedulingOrder] = {}
        for source in normalized["tasks"]:
            source_row = source["source"]["source_row"]
            if source_row in existing_source_rows:
                skipped_tasks += 1
                continue
            machine = machines.get(source["machine_code"])
            mold = molds.get(source["mold_no"])
            if machine is None or mold is None:
                raise HTTPException(status_code=409, detail="预览引用的机台或模具不存在")
            quantity = _decimal(source["order_quantity"])
            completed = _decimal(source["completed_quantity"])
            order_key = _order_business_key(
                order_no=source["order_no"],
                item_no=source["item_no"],
                mold_id=mold.id,
                product_name=source["product_name"],
                order_quantity=quantity,
            )
            order = order_cache.get(order_key)
            if order is None:
                matches = existing_orders_by_key.get(order_key, [])
                if len(matches) > 1:
                    raise HTTPException(
                        status_code=409,
                        detail=f"订单 {source['order_no']} / {source['item_no']} 存在重复主记录",
                    )
                if matches:
                    order = matches[0]
                    reused_orders += 1
                else:
                    status = "COMPLETED" if completed >= quantity else "SCHEDULED"
                    order = InjectionSchedulingOrder(
                        id=f"isorder-{uuid4().hex}",
                        factory_id=factory_id,
                        order_no=source["order_no"],
                        item_no=source["item_no"],
                        product_name=source["product_name"],
                        mold_id=mold.id,
                        order_quantity=quantity,
                        source_completed_quantity=completed,
                        completed_quantity=completed,
                        estimated_completion_at="",
                        estimated_remaining_shifts=0,
                        delivery_slack_days=None,
                        delivery_start_date=source["delivery_start_date"],
                        delivery_due_date=source["delivery_due_date"],
                        priority_code=source["priority_code"],
                        material_readiness_status="unknown",
                        warehouse_text=source["warehouse_text"],
                        remark=source["remark"],
                        source_type="excel_import",
                        source_ref=f"计划表:{source_row}",
                        source_version=batch.source_file_hash,
                        lineage_json=_json(
                            {
                                "import_batch_id": batch.id,
                                "sheet_name": "计划表",
                                "source_row": source_row,
                                "source_file_hash": batch.source_file_hash,
                                "order_date": source["order_date"],
                                "legacy_marker": source["legacy_marker"],
                                "formula_cells": source["source"].get("formula_cells", {}),
                            }
                        ),
                        status=status,
                        revision=1,
                        created_by=user.id,
                        created_by_name=_actor_name(user),
                        updated_by=user.id,
                        updated_by_name=_actor_name(user),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    db.add(order)
                    existing_orders_by_key[order_key].append(order)
                    created_orders += 1
                order_cache[order_key] = order
            db.flush()
            target_quantity = _decimal(source["shift_target_quantity"])
            estimated_remaining_shifts = _remaining_shifts(order, target_quantity)
            max_sequences[machine.id] += 1
            sequence_no = max_sequences[machine.id]
            _validate_schedule_conflicts(
                db,
                factory_id=factory_id,
                plan_id=plan.id,
                machine_id=machine.id,
                mold_id=mold.id,
                mold_copy_no=1,
                planned_start=source["planned_start"],
                planned_finish=source["planned_finish"],
            )
            task = InjectionSchedulingTask(
                id=f"istask-{uuid4().hex}",
                factory_id=factory_id,
                plan_id=plan.id,
                machine_id=machine.id,
                order_id=order.id,
                mold_id=mold.id,
                mold_copy_no=1,
                sequence_no=sequence_no,
                execution_status=source["execution_status"],
                planned_start=source["planned_start"],
                planned_finish=source["planned_finish"],
                shift_target_quantity=target_quantity,
                reported_quantity=Decimal(0),
                estimated_start=source["planned_start"],
                estimated_finish=source["planned_finish"],
                estimated_remaining_shifts=estimated_remaining_shifts,
                delivery_slack_days=_delivery_slack_days(
                    order.delivery_due_date,
                    source["planned_finish"],
                ),
                locked=False,
                manual_override_reason="",
                active_execution=False,
                import_batch_id=batch.id,
                source_sheet_name="计划表",
                source_row=source_row,
                source_file_hash=batch.source_file_hash,
                revision=1,
                created_by=user.id,
                created_by_name=_actor_name(user),
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(task)
            db.flush()
            created_tasks += 1

        if created_plan or created_tasks:
            if not created_plan:
                plan.revision += 1
            plan.updated_by = user.id
            plan.updated_by_name = _actor_name(user)
            plan.updated_at = timestamp
            _record_plan_revision(db, plan=plan, user=user, timestamp=timestamp)
        result = {
            "plan_created": created_plan,
            "created_machines": created_machines,
            "created_molds": created_molds,
            "created_orders": created_orders,
            "reused_orders": reused_orders,
            "created_tasks": created_tasks,
            "skipped_duplicate_tasks": skipped_tasks,
            "acknowledged_blocking_issues": len(acknowledged),
        }
        batch.status = "CONFIRMED"
        batch.revision += 1
        batch.confirm_request_id = payload.request_id
        batch.confirm_payload_hash = confirm_payload_hash
        batch.confirm_mode = payload.confirm_mode
        batch.confirmed_plan_id = plan.id
        batch.confirmed_plan_revision = plan.revision
        batch.result_json = _json(result)
        batch.confirmed_by = user.id
        batch.confirmed_by_name = _actor_name(user)
        batch.confirmed_at = timestamp
        _audit(
            db,
            factory_id=factory_id,
            event_type="import_confirmed",
            entity_type="import_batch",
            entity_id=batch.id,
            entity_revision=batch.revision,
            request_id=payload.request_id,
            detail={
                "plan_id": plan.id,
                "plan_revision": plan.revision,
                "source_file_hash": batch.source_file_hash,
                "result": result,
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
            select(InjectionSchedulingImportBatch).where(
                InjectionSchedulingImportBatch.factory_id == factory_id,
                InjectionSchedulingImportBatch.confirm_request_id == payload.request_id,
            )
        )
        if replay is not None and replay.confirm_payload_hash == confirm_payload_hash:
            return replay, True
        raise HTTPException(status_code=409, detail="导入确认写入冲突") from exc
    return batch, False
