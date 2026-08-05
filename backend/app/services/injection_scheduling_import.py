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
    InjectionSchedulingImportAction,
    InjectionSchedulingImportBatch,
    InjectionSchedulingImportIssue,
    InjectionSchedulingImportMasterDecision,
    InjectionSchedulingImportProfile,
    InjectionSchedulingImportProfileFactory,
)
from app.schemas.injection_scheduling_import import (
    InjectionSchedulingImportBatchOut,
    InjectionSchedulingImportConfirm,
    InjectionSchedulingImportIssueOut,
    InjectionSchedulingImportTaskPreview,
    InjectionSchedulingMasterApproval,
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
from app.services.injection_scheduling_profile_registry import (
    active_profiles_for_factory,
)
from app.services.injection_scheduling_rules import normalize_class_text
from app.services.injection_scheduling_takeover import (
    apply_takeover_actions,
    build_reconciliation_preview,
    prepare_takeover_plan,
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


def _issue_out(
    record: InjectionSchedulingImportIssue,
) -> InjectionSchedulingImportIssueOut:
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
        machine_code=task.get("machine_code", ""),
        sequence_no=int(task.get("sequence_no", 0)),
        execution_status=task.get("execution_status", "QUEUED"),
        status_inferred=bool(task.get("status_inferred", True)),
        legacy_marker=task.get("legacy_marker", ""),
        mold_no=task.get("mold_no", ""),
        product_name=task.get("product_name", ""),
        order_no=task.get("order_no", ""),
        item_no=task.get("item_no", ""),
        order_quantity=task.get("order_quantity"),
        completed_quantity=task.get("completed_quantity"),
        shift_target_quantity=float(task.get("shift_target_quantity") or 0),
        delivery_due_date=task.get("delivery_due_date", ""),
        planned_start=task.get("planned_start", ""),
        planned_finish=task.get("planned_finish", ""),
        priority_code=task.get("priority_code", "NORMAL"),
        source=task.get("source", {}),
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
        batch_state=record.batch_state,
        profile=normalized.get("profile"),
        sheet_roles=normalized.get("sheet_roles", []),
        mapping=normalized.get("mapping", []),
        mapping_fingerprint=record.mapping_fingerprint,
        scheduled_baseline_tasks=normalized.get("scheduled_baseline_tasks", []),
        backlog_orders=normalized.get("backlog_orders", []),
        invalid_rows=normalized.get("invalid_rows", []),
        master_differences=normalized.get("master_differences", []),
        calculation_comparisons=normalized.get("calculation_comparisons", []),
        reconciliation_actions=normalized.get("reconciliation_actions", []),
        plan_context=normalized.get("plan_context", {}),
        action_fingerprint=record.action_fingerprint,
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
        raise HTTPException(
            status_code=409, detail="新导入预览 expected_revision 必须为 0"
        )
    system_machine_codes = set(
        db.scalars(
            select(InjectionSchedulingMachine.machine_code).where(
                InjectionSchedulingMachine.factory_id == factory_id
            )
        ).all()
    )
    system_mold_nos = set(
        db.scalars(
            select(InjectionSchedulingMold.mold_no).where(
                InjectionSchedulingMold.factory_id == factory_id
            )
        ).all()
    )
    normalized, issues = parse_injection_scheduling_workbook(
        content,
        source_file_name,
        factory_id=factory_id,
        system_machine_codes=system_machine_codes,
        system_mold_nos=system_mold_nos,
        profiles=active_profiles_for_factory(db, factory_id),
    )
    if (
        normalized.get("schema_version") == "injection-scheduling-canonical-v1"
        and normalized.get("profile") is not None
    ):
        reconciliation = build_reconciliation_preview(
            db,
            factory_id=factory_id,
            normalized=normalized,
        )
        normalized.update(reconciliation)
        normalized["summary"].update(
            {
                "reconciliation_action_count": len(
                    reconciliation["reconciliation_actions"]
                ),
                "reconciliation_action_counts": reconciliation["action_summary"],
                "restricted_action_count": reconciliation[
                    "restricted_action_count"
                ],
            }
        )
        if (
            reconciliation["has_reconciliation_conflicts"]
            and normalized.get("batch_state") == "PREVIEW_READY"
        ):
            normalized["batch_state"] = "RECONCILIATION_CONFLICT"
        normalized["summary"]["can_confirm"] = (
            normalized["batch_state"] == "PREVIEW_READY"
            and normalized["summary"].get("blocking_issue_count", 0) == 0
        )
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
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
        plan_sheet_name=next(
            (
                item["sheet_name"]
                for item in normalized.get("sheet_roles", [])
                if item.get("role") == "CURRENT_PLAN"
            ),
            "",
        ),
        profile_id=(normalized.get("profile") or {}).get("profile_id"),
        profile_revision=(normalized.get("profile") or {}).get("revision"),
        profile_definition_sha256=(normalized.get("profile") or {}).get(
            "definition_digest", ""
        ),
        template_signature=normalized.get("template_signature", ""),
        mapping_fingerprint=normalized.get("mapping_fingerprint", ""),
        batch_state=normalized.get("batch_state", "MAPPING_REQUIRED"),
        target_draft_plan_id=normalized.get("plan_context", {}).get(
            "target_draft_plan_id", ""
        ),
        target_draft_plan_revision=normalized.get("plan_context", {}).get(
            "target_draft_plan_revision", 0
        ),
        reference_published_plan_id=normalized.get("plan_context", {}).get(
            "reference_published_plan_id", ""
        ),
        reference_published_plan_revision=normalized.get("plan_context", {}).get(
            "reference_published_plan_revision", 0
        ),
        reference_published_event_sequence=normalized.get("plan_context", {}).get(
            "reference_published_event_sequence", 0
        ),
        order_task_revision_digest=normalized.get("plan_context", {}).get(
            "order_task_revision_digest", ""
        ),
        action_fingerprint=normalized.get("action_fingerprint", ""),
        rule_revision=normalized.get("plan_context", {}).get("rule_revision", 0),
        master_revision_digest=normalized.get("plan_context", {}).get(
            "master_revision_digest", ""
        ),
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
    for action in normalized.get("reconciliation_actions", []):
        db.add(
            InjectionSchedulingImportAction(
                id=f"isaction-{record.id.removeprefix('isimport-')}-{action['action_sha256'][:16]}",
                batch_id=record.id,
                factory_id=factory_id,
                action_type=action["action_type"],
                stable_order_key=action.get("stable_order_key", ""),
                stable_row_key=action.get("stable_row_key", ""),
                source_sheet_name=action.get("source_sheet_name", ""),
                source_row=action.get("source_row"),
                target_order_id=action.get("target_order_id", ""),
                target_task_id=action.get("target_task_id", ""),
                requires_publish=bool(action.get("requires_publish")),
                reason_code=action.get("reason_code", ""),
                detail_json=_json(action.get("detail", {})),
                action_sha256=action["action_sha256"],
                created_at=timestamp,
            )
        )
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


def approve_master_differences(
    db: Session,
    *,
    batch_id: str,
    payload: InjectionSchedulingMasterApproval,
    user: AuthContext,
) -> tuple[InjectionSchedulingImportBatch, bool]:
    existing_decisions = list(
        db.scalars(
            select(InjectionSchedulingImportMasterDecision).where(
                InjectionSchedulingImportMasterDecision.factory_id
                == payload.factory_id,
                InjectionSchedulingImportMasterDecision.batch_id == batch_id,
                InjectionSchedulingImportMasterDecision.request_id
                == payload.request_id,
            )
        ).all()
    )
    if existing_decisions:
        existing_keys = {
            f"{item.entity_type}:{item.business_key}" for item in existing_decisions
        }
        if existing_keys != set(payload.differences):
            raise HTTPException(status_code=409, detail="相同 request_id 已用于其他主数据审批")
        replay = db.scalar(
            select(InjectionSchedulingImportBatch).where(
                InjectionSchedulingImportBatch.id == batch_id,
                InjectionSchedulingImportBatch.factory_id == payload.factory_id,
            )
        )
        if replay is None:
            raise HTTPException(status_code=409, detail="主数据审批批次不存在")
        return replay, True
    batch = db.scalar(
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == payload.factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status != "PREVIEW":
        raise HTTPException(status_code=409, detail="已确认批次不能审批主数据差异")
    if batch.revision != payload.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "导入批次已变化",
                "expected_revision": payload.expected_revision,
                "current_revision": batch.revision,
            },
        )
    normalized = _load_json(batch.normalized_json, {})
    difference_by_key = {
        f"{item.get('entity_type', '')}:{item.get('business_key', '')}": item
        for item in normalized.get("master_differences", [])
    }
    unknown = set(payload.differences) - set(difference_by_key)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "包含不属于本批次的主数据差异", "differences": sorted(unknown)},
        )
    timestamp = _now()
    rows = [
        *normalized.get("scheduled_baseline_tasks", []),
        *normalized.get("backlog_orders", []),
    ]
    source_machines = {
        item.get("machine_code", ""): item for item in normalized.get("machines", [])
    }
    existing_machines = {
        item.machine_code
        for item in db.scalars(
            select(InjectionSchedulingMachine).where(
                InjectionSchedulingMachine.factory_id == payload.factory_id
            )
        ).all()
    }
    existing_molds = {
        item.mold_no
        for item in db.scalars(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == payload.factory_id
            )
        ).all()
    }
    created_machines = 0
    created_molds = 0
    try:
        for key in payload.differences:
            difference = difference_by_key[key]
            entity_type = difference["entity_type"]
            business_key = difference["business_key"]
            decision_id = f"ismasterdecision-{uuid4().hex}"
            if entity_type == "MACHINE" and business_key not in existing_machines:
                source = source_machines.get(business_key, {})
                normalized_class = normalize_class_text(source.get("machine_class", ""))
                db.add(
                    InjectionSchedulingMachine(
                        id=f"ismachine-{uuid4().hex}",
                        factory_id=payload.factory_id,
                        machine_code=business_key,
                        area=source.get("area", ""),
                        position=source.get("position", ""),
                        machine_class=normalized_class.raw,
                        machine_class_raw=normalized_class.raw,
                        machine_a_class=normalized_class.a_class,
                        normalization_status=normalized_class.status,
                        process_tags_json=_json(normalized_class.process_tags),
                        special_machine_type=normalized_class.special_machine_type,
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
                        status="available",
                        revision=1,
                        created_by=user.id,
                        created_by_name=_actor_name(user),
                        updated_by=user.id,
                        updated_by_name=_actor_name(user),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                existing_machines.add(business_key)
                created_machines += 1
            elif entity_type == "MOLD" and business_key not in existing_molds:
                row = next((item for item in rows if item.get("mold_no") == business_key), {})
                normalized_class = normalize_class_text(
                    row.get("legacy_machine_class_text", "")
                )
                db.add(
                    InjectionSchedulingMold(
                        id=f"ismold-{uuid4().hex}",
                        factory_id=payload.factory_id,
                        mold_no=business_key,
                        name=row.get("product_name", ""),
                        length_mm=None,
                        width_mm=None,
                        height_mm=None,
                        weight_kg=None,
                        recommended_machine_class=normalized_class.raw,
                        mold_class_raw=normalized_class.raw,
                        mold_a_class=normalized_class.a_class,
                        normalization_status=normalized_class.status,
                        process_tags_json=_json(normalized_class.process_tags),
                        special_machine_type=normalized_class.special_machine_type,
                        whole_shot_net_weight_g=row.get("whole_shot_net_weight_g"),
                        whole_shot_gross_weight_g=row.get("whole_shot_gross_weight_g"),
                        required_arm_type="",
                        required_fixture_type="",
                        material_code=row.get("material_code", ""),
                        material_name=row.get("material_name", ""),
                        color_profile=row.get("color", ""),
                        process_requirements_json="[]",
                        copy_count=1,
                        data_quality_status="needs_review",
                        status="available",
                        revision=1,
                        created_by=user.id,
                        created_by_name=_actor_name(user),
                        updated_by=user.id,
                        updated_by_name=_actor_name(user),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                existing_molds.add(business_key)
                created_molds += 1
            elif entity_type not in {"MACHINE", "MOLD"}:
                raise HTTPException(status_code=422, detail="不支持的主数据差异类型")
            db.add(
                InjectionSchedulingImportMasterDecision(
                    id=decision_id,
                    batch_id=batch.id,
                    factory_id=payload.factory_id,
                    entity_type=entity_type,
                    business_key=business_key,
                    decision="APPROVED",
                    reason=payload.reason,
                    request_id=payload.request_id,
                    decided_by=user.id,
                    decided_by_name=_actor_name(user),
                    created_at=timestamp,
                )
            )
            difference["status"] = "APPROVED_CREATED"
            difference["decision_id"] = decision_id
        db.flush()
        remaining = [
            item
            for item in normalized.get("master_differences", [])
            if item.get("status") != "APPROVED_CREATED"
        ]
        reconciliation = build_reconciliation_preview(
            db,
            factory_id=payload.factory_id,
            normalized=normalized,
        )
        normalized.update(reconciliation)
        normalized["batch_state"] = (
            "MASTER_REVIEW_REQUIRED"
            if remaining
            else "RECONCILIATION_CONFLICT"
            if reconciliation["has_reconciliation_conflicts"]
            else "PREVIEW_READY"
        )
        normalized["summary"].update(
            {
                "master_difference_count": len(remaining),
                "approved_master_difference_count": len(payload.differences),
                "reconciliation_action_count": len(reconciliation["reconciliation_actions"]),
                "reconciliation_action_counts": reconciliation["action_summary"],
                "can_confirm": normalized["batch_state"] == "PREVIEW_READY"
                and normalized["summary"].get("blocking_issue_count", 0) == 0,
            }
        )
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
        context = reconciliation["plan_context"]
        batch.batch_state = normalized["batch_state"]
        batch.normalized_json = _json(normalized)
        batch.normalized_sha256 = normalized["normalized_sha256"]
        batch.summary_json = _json(normalized["summary"])
        batch.action_fingerprint = reconciliation["action_fingerprint"]
        batch.target_draft_plan_id = context["target_draft_plan_id"]
        batch.target_draft_plan_revision = context["target_draft_plan_revision"]
        batch.reference_published_plan_id = context["reference_published_plan_id"]
        batch.reference_published_plan_revision = context[
            "reference_published_plan_revision"
        ]
        batch.reference_published_event_sequence = context[
            "reference_published_event_sequence"
        ]
        batch.order_task_revision_digest = context["order_task_revision_digest"]
        batch.rule_revision = context["rule_revision"]
        batch.master_revision_digest = context["master_revision_digest"]
        batch.revision += 1
        _audit(
            db,
            factory_id=payload.factory_id,
            event_type="import_master_differences_approved",
            entity_type="import_batch",
            entity_id=batch.id,
            entity_revision=batch.revision,
            request_id=payload.request_id,
            detail={
                "differences": payload.differences,
                "reason": payload.reason,
                "created_machines": created_machines,
                "created_molds": created_molds,
                "batch_state": batch.batch_state,
            },
            user=user,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="主数据审批写入冲突") from exc
    return batch, False


def _create_missing_masters(
    db: Session,
    *,
    factory_id: str,
    normalized: dict[str, Any],
    user: AuthContext,
    timestamp: str,
) -> tuple[
    dict[str, InjectionSchedulingMachine], dict[str, InjectionSchedulingMold], int, int
]:
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
        normalized_class = normalize_class_text(source.get("machine_class", ""))
        record = InjectionSchedulingMachine(
            id=f"ismachine-{uuid4().hex}",
            factory_id=factory_id,
            machine_code=code,
            area=source.get("area", ""),
            position=source.get("position", ""),
            machine_class=normalized_class.raw,
            machine_class_raw=normalized_class.raw,
            machine_a_class=normalized_class.a_class,
            normalization_status=normalized_class.status,
            process_tags_json=_json(normalized_class.process_tags),
            special_machine_type=normalized_class.special_machine_type,
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
        normalized_class = normalize_class_text(
            source.get("recommended_machine_class", "")
        )
        record = InjectionSchedulingMold(
            id=f"ismold-{uuid4().hex}",
            factory_id=factory_id,
            mold_no=mold_no,
            name=source.get("name", ""),
            length_mm=source.get("length_mm"),
            width_mm=source.get("width_mm"),
            height_mm=source.get("height_mm"),
            weight_kg=source.get("weight_kg"),
            recommended_machine_class=normalized_class.raw,
            mold_class_raw=normalized_class.raw,
            mold_a_class=normalized_class.a_class,
            normalization_status=normalized_class.status,
            process_tags_json=_json(normalized_class.process_tags),
            special_machine_type=normalized_class.special_machine_type,
            whole_shot_net_weight_g=source.get("whole_shot_net_weight_g"),
            whole_shot_gross_weight_g=source.get("whole_shot_gross_weight_g"),
            required_arm_type=source.get("required_arm_type", ""),
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
            raise HTTPException(
                status_code=409, detail="当前厂区已有草案，请改用合并草案"
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


def _confirm_canonical_takeover(
    db: Session,
    *,
    batch: InjectionSchedulingImportBatch,
    payload: InjectionSchedulingImportConfirm,
    normalized: dict[str, Any],
    confirm_payload_hash: str,
    can_publish: bool,
    user: AuthContext,
) -> InjectionSchedulingImportBatch:
    current = build_reconciliation_preview(
        db,
        factory_id=batch.factory_id,
        normalized=normalized,
    )
    current_context = current["plan_context"]
    if (
        current["action_fingerprint"] != batch.action_fingerprint
        or current_context.get("order_task_revision_digest")
        != batch.order_task_revision_digest
        or current_context.get("master_revision_digest")
        != batch.master_revision_digest
        or current_context.get("rule_revision") != batch.rule_revision
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IMPORT_RECONCILIATION_STALE",
                "message": "计划、任务、报工、主数据或规则已变化，请重新预览",
                "current_action_fingerprint": current["action_fingerprint"],
            },
        )
    if (
        payload.expected_action_fingerprint
        and payload.expected_action_fingerprint != batch.action_fingerprint
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACTION_FINGERPRINT_MISMATCH",
                "current_action_fingerprint": batch.action_fingerprint,
            },
        )
    if current["has_reconciliation_conflicts"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RECONCILIATION_CONFLICT",
                "message": "批次仍含计划或报工水位冲突，不能确认",
            },
        )
    timestamp = _now()
    try:
        plan, created_plan, successor_created = prepare_takeover_plan(
            db,
            factory_id=batch.factory_id,
            business_date=payload.business_date.isoformat(),
            user=user,
            timestamp=timestamp,
        )
        if created_plan:
            if payload.confirm_mode != "create_draft" or payload.expected_plan_revision != 0:
                raise HTTPException(
                    status_code=409,
                    detail="当前确认将创建接管草案，请使用 create_draft 且 revision=0",
                )
        else:
            if payload.confirm_mode != "merge_draft":
                raise HTTPException(status_code=409, detail="当前厂区已有草案，请使用 merge_draft")
            if (
                plan.revision != payload.expected_plan_revision
                or plan.id != batch.target_draft_plan_id
                or plan.revision != batch.target_draft_plan_revision
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "TARGET_DRAFT_STALE",
                        "current_plan_id": plan.id,
                        "current_revision": plan.revision,
                    },
                )
        action_result = apply_takeover_actions(
            db,
            plan=plan,
            batch=batch,
            normalized=normalized,
            actions=current["reconciliation_actions"],
            action_reasons=payload.action_reasons,
            can_publish=can_publish,
            user=user,
            timestamp=timestamp,
        )
        mutating_actions = sum(
            count
            for action_type, count in action_result["action_counts"].items()
            if action_type not in {"SKIP_IDENTICAL", "CREATE_ORDER"}
        )
        if not created_plan and mutating_actions:
            plan.revision += 1
        plan.updated_by = user.id
        plan.updated_by_name = _actor_name(user)
        plan.updated_at = timestamp
        db.flush()
        if created_plan or mutating_actions:
            _record_plan_revision(db, plan=plan, user=user, timestamp=timestamp)
        result = {
            "plan_created": created_plan,
            "successor_created": successor_created,
            "action_counts": action_result["action_counts"],
            "created_machines": 0,
            "created_molds": 0,
            "locked_baseline": True,
            "backlog_without_tasks": True,
            "action_fingerprint": batch.action_fingerprint,
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
            factory_id=batch.factory_id,
            event_type="import_takeover_confirmed",
            entity_type="import_batch",
            entity_id=batch.id,
            entity_revision=batch.revision,
            request_id=payload.request_id,
            detail={
                "plan_id": plan.id,
                "plan_revision": plan.revision,
                "based_on_plan_id": plan.based_on_plan_id,
                "action_reasons": payload.action_reasons,
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
        raise HTTPException(status_code=409, detail="接管确认事务写入冲突") from exc
    return batch


def confirm_import(
    db: Session,
    batch_id: str,
    payload: InjectionSchedulingImportConfirm,
    user: AuthContext,
    *,
    can_publish: bool = False,
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
        ).with_for_update()
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
    normalized = _load_json(batch.normalized_json, {})
    normalized_copy = dict(normalized)
    expected_normalized_sha256 = normalized_copy.pop("normalized_sha256", "")
    if _payload_hash(normalized_copy) != expected_normalized_sha256:
        raise HTTPException(status_code=409, detail="导入预览内容校验失败，请重新上传")
    if batch.preview_schema_version == "injection-scheduling-canonical-v1":
        active_profile_record = db.scalar(
            select(InjectionSchedulingImportProfile)
            .join(
                InjectionSchedulingImportProfileFactory,
                InjectionSchedulingImportProfileFactory.profile_id
                == InjectionSchedulingImportProfile.id,
            )
            .where(
                InjectionSchedulingImportProfile.id == batch.profile_id,
                InjectionSchedulingImportProfile.revision == batch.profile_revision,
                InjectionSchedulingImportProfile.status == "ACTIVE",
                InjectionSchedulingImportProfileFactory.factory_id == factory_id,
            )
            .with_for_update()
        )
        if (
            active_profile_record is None
            or batch.profile_definition_sha256
            != active_profile_record.definition_sha256
            or batch.profile_definition_sha256
            != (normalized.get("profile") or {}).get("definition_digest", "")
            or batch.mapping_fingerprint != normalized.get("mapping_fingerprint", "")
            or batch.template_signature != normalized.get("template_signature", "")
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IMPORT_PROFILE_STALE",
                    "message": "Profile revision 或映射指纹已变化，请重新预览",
                    "profile_id": batch.profile_id,
                    "profile_revision": batch.profile_revision,
                },
            )
        non_overridable = list(
            db.scalars(
                select(InjectionSchedulingImportIssue).where(
                    InjectionSchedulingImportIssue.batch_id == batch.id,
                    InjectionSchedulingImportIssue.blocking.is_(True),
                    InjectionSchedulingImportIssue.code.in_(
                        {
                            "PROFILE_NOT_IDENTIFIED",
                            "REQUIRED_MAPPING_MISSING",
                            "STABLE_IDENTITY_AMBIGUOUS",
                            "CANONICAL_ROW_INVALID",
                            "FORMULA_CACHE_MISSING",
                            "FORMULA_ERROR",
                        }
                    ),
                )
            ).all()
        )
        if non_overridable:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "NON_OVERRIDABLE_CANONICAL_ERRORS",
                    "message": "规范映射或来源完整性错误不可通过确认问题强制跳过",
                    "issue_ids": [item.id for item in non_overridable],
                },
            )
        if batch.batch_state != "PREVIEW_READY":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CANONICAL_BATCH_NOT_READY",
                    "message": "批次尚未完成字段映射或主数据审批，不能确认写入",
                    "batch_state": batch.batch_state,
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
            detail={
                "message": "包含不属于本批次的阻断问题 ID",
                "issue_ids": sorted(unknown_ids),
            },
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
    if batch.preview_schema_version == "injection-scheduling-canonical-v1":
        return (
            _confirm_canonical_takeover(
                db,
                batch=batch,
                payload=payload,
                normalized=normalized,
                confirm_payload_hash=confirm_payload_hash,
                can_publish=can_publish,
                user=user,
            ),
            False,
        )
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
                raise HTTPException(
                    status_code=409, detail="预览引用的机台或模具不存在"
                )
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
                                "formula_cells": source["source"].get(
                                    "formula_cells", {}
                                ),
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
