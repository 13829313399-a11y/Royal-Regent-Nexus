from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
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
    InjectionSchedulingTask,
)
from app.models.injection_scheduling_import import (
    InjectionSchedulingImportAction,
    InjectionSchedulingImportBatch,
    InjectionSchedulingImportIssue,
    InjectionSchedulingImportMasterDecision,
    InjectionSchedulingImportProfile,
    InjectionSchedulingImportProfileFactory,
    InjectionSchedulingUploadArtifact,
)
from app.models.injection_scheduling_shared import (
    InjectionSchedulingCompanyFactoryMembership,
    InjectionSchedulingDemandImportRow,
    InjectionSchedulingDemandOrderIdentity,
    InjectionSchedulingDemandOrderVersion,
    InjectionSchedulingDemandResolutionSnapshot,
    InjectionSchedulingFieldEvidence,
    InjectionSchedulingMasterDataProposal,
    InjectionSchedulingRolloutPolicy,
)
from app.schemas.injection_scheduling_import import (
    InjectionSchedulingImportBatchOut,
    InjectionSchedulingImportConfirm,
    InjectionSchedulingImportIssueOut,
    InjectionSchedulingImportRetry,
    InjectionSchedulingImportTaskPreview,
    InjectionSchedulingMasterApproval,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling import require_injection_scheduling_factory
from app.services.injection_scheduling_demand_import import (
    master_revision_digest,
    parse_demand_order_workbook,
)
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
from app.services.injection_scheduling_export import verify_signed_system_meta
from app.services.injection_scheduling_master_import import (
    parse_master_data_workbook,
)
from app.services.injection_scheduling_profile_registry import (
    active_profiles_for_factory,
    create_profile_revision,
    profile_revision_for_factory,
)
from app.services.injection_scheduling_profiles import (
    CANONICAL_FIELD_CATALOG,
    SYSTEM_STANDARD_EXPORT_PROFILE,
)
from app.services.injection_scheduling_projection import CALCULATION_VERSION
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


def _demand_order_lineage(
    *,
    batch: InjectionSchedulingImportBatch,
    import_row: InjectionSchedulingDemandImportRow,
    identity: InjectionSchedulingDemandOrderIdentity,
    version: InjectionSchedulingDemandOrderVersion,
    canonical: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Keep demand-sheet planning facts available without promoting master data."""

    return {
        "batch_id": batch.id,
        "demand_import_row_id": import_row.id,
        "order_identity_id": identity.id,
        "order_revision_id": version.id,
        "source_mold_no": str(canonical.get("source_mold_no", "")),
        "product_group_no": str(canonical.get("product_group_no", "")),
        "source_daily_capacity": canonical.get("source_daily_capacity"),
        "color_name": str(canonical.get("color_name", "")),
        "color_powder_code": str(canonical.get("color_powder_code", "")),
        "material_name": str(canonical.get("material_name", "")),
        "whole_shot_net_weight_g": canonical.get("whole_shot_net_weight_g"),
        "total_gross_weight": canonical.get("total_gross_weight"),
        "sprue_ratio": canonical.get("sprue_ratio"),
        "order_date": str(canonical.get("order_date", "")),
        "mold_enrichment_status": str(
            resolved.get("mold_enrichment_status", "PENDING")
        ),
        "mold_definition_id": resolved.get("mold_definition_id"),
        "mold_output_spec_id": resolved.get("mold_output_spec_id"),
    }


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
    demand_rows = list(normalized.get("demand_rows", []))
    if record.document_kind == "DEMAND_ORDER" and demand_rows:
        confirmation_by_id = {
            item.id: item.confirmation_state
            for item in db.scalars(
                select(InjectionSchedulingDemandImportRow).where(
                    InjectionSchedulingDemandImportRow.batch_id == record.id,
                    InjectionSchedulingDemandImportRow.preview_generation
                    == record.preview_generation,
                )
            ).all()
        }
        demand_rows = [
            {
                **item,
                "confirmation_state": confirmation_by_id.get(
                    str(item.get("row_id", "")), "PENDING"
                ),
            }
            for item in demand_rows
        ]
    issues = list(
        db.scalars(
            select(InjectionSchedulingImportIssue)
            .where(
                InjectionSchedulingImportIssue.batch_id == record.id,
                InjectionSchedulingImportIssue.preview_generation
                == record.preview_generation,
            )
            .order_by(
                InjectionSchedulingImportIssue.blocking.desc(),
                InjectionSchedulingImportIssue.source_row,
                InjectionSchedulingImportIssue.id,
            )
        ).all()
    )
    artifact = db.scalar(
        select(InjectionSchedulingUploadArtifact).where(
            InjectionSchedulingUploadArtifact.batch_id == record.id,
            InjectionSchedulingUploadArtifact.factory_id == record.factory_id,
        )
    )
    artifact_expires_at = (
        parse_business_timestamp(artifact.expires_at) if artifact is not None else None
    )
    artifact_available = bool(
        artifact is not None
        and artifact.cleanup_status == "RETAINED"
        and artifact.payload_blob is not None
        and artifact_expires_at is not None
        and artifact_expires_at > business_now()
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
        preview_generation=record.preview_generation,
        document_kind=record.document_kind,
        source_namespace_id=record.source_namespace_id,
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
        demand_rows=demand_rows,
        master_data_rows=normalized.get("master_data_rows", []),
        resolution_digest=record.resolution_digest,
        mapping_draft=_load_json(record.mapping_draft_json, {}),
        partial_confirmation=_load_json(record.partial_confirmation_json, {}),
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
        artifact_available=artifact_available,
        artifact_expires_at=artifact.expires_at if artifact is not None else "",
        issues=[_issue_out(item) for item in issues],
        tasks=[_task_preview(item) for item in normalized.get("tasks", [])],
        idempotent_replay=idempotent_replay,
    )


def get_import_batch(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
) -> InjectionSchedulingImportBatch:
    factory_id = require_injection_scheduling_factory(factory_id)
    record = db.scalar(
        select(InjectionSchedulingImportBatch).where(
            InjectionSchedulingImportBatch.factory_id == factory_id,
            InjectionSchedulingImportBatch.id == batch_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return record


def list_import_batches(
    db: Session,
    *,
    factory_id: str,
    limit: int = 20,
) -> list[InjectionSchedulingImportBatch]:
    factory_id = require_injection_scheduling_factory(factory_id)
    return list(
        db.scalars(
            select(InjectionSchedulingImportBatch)
            .where(InjectionSchedulingImportBatch.factory_id == factory_id)
            .order_by(
                InjectionSchedulingImportBatch.created_at.desc(),
                InjectionSchedulingImportBatch.id.desc(),
            )
            .limit(limit)
        ).all()
    )


def _plan_binding_digest(db: Session, plan_id: str) -> str:
    if not plan_id:
        return ""
    tasks = list(
        db.scalars(
            select(InjectionSchedulingTask)
            .where(InjectionSchedulingTask.plan_id == plan_id)
            .order_by(InjectionSchedulingTask.id)
        ).all()
    )
    states = list(
        db.scalars(
            select(InjectionSchedulingPlanOrderState)
            .where(InjectionSchedulingPlanOrderState.plan_id == plan_id)
            .order_by(InjectionSchedulingPlanOrderState.id)
        ).all()
    )
    return _payload_hash(
        {
            "tasks": [
                (
                    item.id,
                    item.revision,
                    item.order_id,
                    item.execution_status,
                    str(item.reported_quantity),
                    item.planned_start,
                    item.planned_finish,
                    item.physical_mold_asset_id,
                )
                for item in tasks
            ],
            "states": [
                (
                    item.id,
                    item.revision,
                    item.order_id,
                    item.order_revision_id,
                    item.status,
                    str(item.completed_quantity),
                )
                for item in states
            ],
        }
    )


def _bind_demand_plan_context(
    db: Session, *, factory_id: str, normalized: dict[str, Any]
) -> None:
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
    bound_plan = draft or published
    context = normalized.setdefault("plan_context", {})
    context.update(
        {
            "target_draft_plan_id": draft.id if draft else "",
            "target_draft_plan_revision": draft.revision if draft else 0,
            "reference_published_plan_id": published.id if published else "",
            "reference_published_plan_revision": published.revision if published else 0,
            "reference_published_event_sequence": int(
                db.scalar(
                    select(func.max(InjectionSchedulingAuditEvent.sequence)).where(
                        InjectionSchedulingAuditEvent.factory_id == factory_id
                    )
                )
                or 0
            ),
            "order_task_revision_digest": _plan_binding_digest(
                db, bound_plan.id if bound_plan else ""
            ),
        }
    )
    normalized.pop("normalized_sha256", None)
    normalized["normalized_sha256"] = _payload_hash(normalized)


def _parse_and_reconcile(
    db: Session,
    *,
    factory_id: str,
    source_file_name: str,
    content: bytes,
    document_kind: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requested_kind = document_kind or "PLANNED_SCHEDULE"
    if requested_kind not in {
        "AUTO",
        "DEMAND_ORDER",
        "PLANNED_SCHEDULE",
        "SYSTEM_ROUND_TRIP",
        "MASTER_DATA",
    }:
        raise HTTPException(status_code=422, detail="document_kind 无效")
    system_meta = verify_signed_system_meta(db, content, factory_id=factory_id)
    if system_meta is not None and requested_kind == "DEMAND_ORDER":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_KIND_MISMATCH",
                "message": "签名系统回传文件不能按需求单导入",
            },
        )
    if requested_kind == "SYSTEM_ROUND_TRIP" and system_meta is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SYSTEM_SIGNATURE_REQUIRED",
                "message": "SYSTEM_ROUND_TRIP 必须携带有效系统签名元数据",
            },
        )
    if requested_kind == "MASTER_DATA":
        master_profiles = active_profiles_for_factory(
            db, factory_id, document_kind="MASTER_DATA"
        )
        if len(master_profiles) != 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MASTER_DATA_PROFILE_UNAVAILABLE",
                    "message": "当前厂区必须且只能有一个 ACTIVE 主数据 Profile",
                },
            )
        return parse_master_data_workbook(
            db,
            content,
            source_file_name,
            factory_id=factory_id,
            profile=master_profiles[0],
        )
    if system_meta is None and requested_kind in {"AUTO", "DEMAND_ORDER"}:
        demand_profiles = active_profiles_for_factory(
            db, factory_id, document_kind="DEMAND_ORDER"
        )
        if not demand_profiles:
            raise HTTPException(
                status_code=409, detail="当前厂区没有 ACTIVE 需求单 Profile"
            )
        if len(demand_profiles) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DEMAND_PROFILE_AMBIGUOUS",
                    "message": "当前厂区存在多个 ACTIVE 需求单 Profile",
                },
            )
        try:
            normalized, issues = parse_demand_order_workbook(
                db,
                content,
                source_file_name,
                factory_id=factory_id,
                profile=demand_profiles[0],
            )
            _bind_demand_plan_context(db, factory_id=factory_id, normalized=normalized)
            return normalized, issues
        except HTTPException as exc:
            code = exc.detail.get("code", "") if isinstance(exc.detail, dict) else ""
            if requested_kind == "DEMAND_ORDER" or code not in {
                "DEMAND_ORDER_PROFILE_NOT_IDENTIFIED",
                "DEMAND_ORDER_PROFILE_AMBIGUOUS",
            }:
                raise
    if system_meta is None and requested_kind == "AUTO":
        master_profiles = active_profiles_for_factory(
            db, factory_id, document_kind="MASTER_DATA"
        )
        if len(master_profiles) == 1:
            try:
                return parse_master_data_workbook(
                    db,
                    content,
                    source_file_name,
                    factory_id=factory_id,
                    profile=master_profiles[0],
                    auto_detection=True,
                )
            except HTTPException as exc:
                code = (
                    exc.detail.get("code", "") if isinstance(exc.detail, dict) else ""
                )
                if code != "MASTER_DATA_PROFILE_NOT_IDENTIFIED":
                    raise
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
    profiles = active_profiles_for_factory(
        db, factory_id, document_kind="PLANNED_SCHEDULE"
    )
    if system_meta is not None:
        signed_profile_id = str(system_meta.get("profile_id", ""))
        signed_profile_revision = int(system_meta.get("profile_revision", 0))
        if signed_profile_id == SYSTEM_STANDARD_EXPORT_PROFILE.profile_id:
            signed_profile = SYSTEM_STANDARD_EXPORT_PROFILE
        else:
            signed_profile = profile_revision_for_factory(
                db,
                factory_id=factory_id,
                profile_id=signed_profile_id,
                profile_revision=signed_profile_revision,
                allowed_statuses=("ACTIVE", "RETIRED"),
            )
        if signed_profile is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SYSTEM_META_PROFILE_UNAVAILABLE",
                    "message": "签名导出引用的 Profile revision 已不可用",
                },
            )
        profiles = (
            signed_profile,
            *(
                item
                for item in profiles
                if item.profile_id != signed_profile.profile_id
            ),
        )
    normalized, issues = parse_injection_scheduling_workbook(
        content,
        source_file_name,
        factory_id=factory_id,
        system_machine_codes=system_machine_codes,
        system_mold_nos=system_mold_nos,
        profiles=profiles,
    )
    if system_meta is not None:
        manifest_by_source_row: dict[int, dict[str, Any]] = {}
        for item in system_meta["rows"]:
            source_row = int(item["source_row"])
            if source_row in manifest_by_source_row:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "SYSTEM_META_ROW_IDENTITY_INVALID",
                        "message": "签名 row manifest 的 source_row 重复",
                    },
                )
            manifest_by_source_row[source_row] = item
        for row in [
            *normalized.get("scheduled_baseline_tasks", []),
            *normalized.get("backlog_orders", []),
            *normalized.get("invalid_rows", []),
        ]:
            source_row = int((row.get("source") or {}).get("source_row") or 0)
            signed_row = manifest_by_source_row.get(source_row)
            if signed_row is None:
                continue
            row["stable_order_key"] = signed_row["stable_order_key"]
            row["stable_row_key"] = signed_row["stable_row_key"]
            row["split_key"] = signed_row["split_key"]
            row["quantity_scope"] = signed_row["quantity_scope"]
            row["planned_quantity"] = signed_row["planned_quantity"]
            row["system_export"] = signed_row
        profile_payload = normalized.get("profile") or {}
        profile_payload["recognition_method"] = "SIGNED_SYSTEM_EXPORT"
        normalized["profile"] = profile_payload
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
                "restricted_action_count": reconciliation["restricted_action_count"],
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
    if system_meta is not None:
        normalized["document_kind"] = "SYSTEM_ROUND_TRIP"
        normalized["system_meta"] = system_meta
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
    return normalized, issues


def preview_import(
    db: Session,
    *,
    factory_id: str,
    expected_revision: int,
    source_file_name: str,
    content: bytes,
    preview_request_id: str,
    user: AuthContext,
    document_kind: str | None = None,
) -> tuple[InjectionSchedulingImportBatch, bool]:
    factory_id = require_injection_scheduling_factory(factory_id)
    if expected_revision != 0:
        raise HTTPException(
            status_code=409, detail="新导入预览 expected_revision 必须为 0"
        )
    normalized, issues = _parse_and_reconcile(
        db,
        factory_id=factory_id,
        source_file_name=source_file_name,
        content=content,
        document_kind=document_kind,
    )
    preview_payload_hash = _payload_hash(
        {
            "factory_id": factory_id,
            "expected_revision": expected_revision,
            "source_file_name": source_file_name,
            "source_file_hash": normalized["source_file_hash"],
            "document_kind": normalized.get("document_kind", "PLANNED_SCHEDULE"),
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
    batch_id = f"isimport-{uuid4().hex}"
    if normalized.get("document_kind") == "DEMAND_ORDER":
        for index, row in enumerate(normalized.get("demand_rows", []), start=1):
            row["row_id"] = f"isdemrow-{batch_id.removeprefix('isimport-')}-{index}"
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
    elif normalized.get("document_kind") == "MASTER_DATA":
        for index, row in enumerate(normalized.get("master_data_rows", []), start=1):
            row["row_id"] = f"ismasterrow-{batch_id.removeprefix('isimport-')}-{index}"
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
    record = InjectionSchedulingImportBatch(
        id=batch_id,
        factory_id=factory_id,
        source_file_name=source_file_name[:255],
        source_file_hash=normalized["source_file_hash"],
        source_size_bytes=normalized["source_size_bytes"],
        document_kind=normalized.get("document_kind", "PLANNED_SCHEDULE"),
        source_namespace_id=normalized.get("source_namespace_id", ""),
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
        preview_generation=1,
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
        resolution_digest=normalized.get("resolution_digest", ""),
        mapping_draft_json=_json(normalized.get("mapping_draft", {})),
        ui_state_json="{}",
        partial_confirmation_json="{}",
        artifact_rebind_count=0,
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
    db.add(
        InjectionSchedulingUploadArtifact(
            id=f"isartifact-{uuid4().hex}",
            batch_id=record.id,
            factory_id=factory_id,
            storage_key=f"injection-import/{uuid4().hex}",
            source_sha256=record.source_file_hash,
            size_bytes=len(content),
            detected_format="XLSX",
            payload_blob=content,
            expires_at=(business_now() + timedelta(hours=72)).isoformat(
                timespec="seconds"
            ),
            cleanup_status="RETAINED",
            created_by=user.id,
            created_by_name=_actor_name(user),
            created_at=timestamp,
            cleaned_at="",
        )
    )
    if record.document_kind == "DEMAND_ORDER":
        for row in normalized.get("demand_rows", []):
            demand_row = InjectionSchedulingDemandImportRow(
                id=row["row_id"],
                batch_id=record.id,
                factory_id=factory_id,
                preview_generation=1,
                source_sheet_name=row.get("source", {}).get("sheet_name", ""),
                source_row=int(row.get("source", {}).get("source_row") or 0),
                source_order_line_id=row.get("source_order_line_id", ""),
                source_revision=row.get("source_revision", ""),
                stable_line_key=row.get("stable_line_key", ""),
                identity_quality=row.get("identity_quality", "FALLBACK_BUSINESS_KEY"),
                canonical_json=_json(row.get("canonical", {})),
                source_lineage_json=_json(row.get("source_lineage", {})),
                resolution_status=row.get("resolution_status", "INVALID"),
                confirmation_state="PENDING",
                row_digest=_payload_hash(
                    {
                        "canonical": row.get("canonical", {}),
                        "source": row.get("source", {}),
                    }
                ),
                confirmed_generation=None,
                confirmed_order_identity_id="",
                confirmed_order_version_id="",
                confirmed_plan_order_state_id="",
                confirm_request_id="",
                created_at=timestamp,
            )
            db.add(demand_row)
            resolved = row.get("resolved_values", {})
            db.add(
                InjectionSchedulingDemandResolutionSnapshot(
                    id=f"isdemres-{uuid4().hex}",
                    demand_import_row_id=demand_row.id,
                    preview_generation=1,
                    resolution_status=demand_row.resolution_status,
                    mold_definition_id=resolved.get("mold_definition_id"),
                    mold_output_spec_id=resolved.get("mold_output_spec_id"),
                    physical_mold_asset_id=resolved.get("physical_mold_asset_id"),
                    factory_capability_id=resolved.get("factory_capability_id"),
                    commercial_rate_rule_id=resolved.get("commercial_rate_rule_id"),
                    master_revision_digest=row.get("master_revision_digest", ""),
                    resolution_digest=row.get("resolution_digest", ""),
                    resolved_values_json=_json(resolved),
                    provenance_json=_json(row.get("provenance", {})),
                    candidate_json=_json(row.get("candidates", {})),
                    created_by=user.id,
                    created_at=timestamp,
                )
            )
    for action in normalized.get("reconciliation_actions", []):
        db.add(
            InjectionSchedulingImportAction(
                id=f"isaction-{record.id.removeprefix('isimport-')}-{action['action_sha256'][:16]}",
                batch_id=record.id,
                factory_id=factory_id,
                preview_generation=1,
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
                preview_generation=1,
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


def retry_import_batch(
    db: Session,
    *,
    batch_id: str,
    payload: InjectionSchedulingImportRetry,
    user: AuthContext,
) -> tuple[InjectionSchedulingImportBatch, bool]:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    replay_event = db.scalar(
        select(InjectionSchedulingAuditEvent).where(
            InjectionSchedulingAuditEvent.factory_id == factory_id,
            InjectionSchedulingAuditEvent.entity_id == batch_id,
            InjectionSchedulingAuditEvent.event_type == "import_batch_reidentified",
            InjectionSchedulingAuditEvent.request_id == payload.request_id,
        )
    )
    if replay_event is not None:
        detail = _load_json(replay_event.detail_json, {})
        if detail.get("payload_hash") != payload_hash:
            raise HTTPException(
                status_code=409, detail="相同 request_id 已用于其他重试"
            )
        return get_import_batch(db, factory_id=factory_id, batch_id=batch_id), True
    batch = db.scalar(
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status not in {"PREVIEW", "PARTIALLY_CONFIRMED"}:
        raise HTTPException(status_code=409, detail="已确认批次不能重新识别")
    if batch.revision != payload.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "导入批次已变化",
                "expected_revision": payload.expected_revision,
                "current_revision": batch.revision,
            },
        )
    artifact = db.scalar(
        select(InjectionSchedulingUploadArtifact)
        .where(
            InjectionSchedulingUploadArtifact.batch_id == batch.id,
            InjectionSchedulingUploadArtifact.factory_id == factory_id,
        )
        .with_for_update()
    )
    expires_at = (
        parse_business_timestamp(artifact.expires_at) if artifact is not None else None
    )
    if (
        artifact is None
        or artifact.cleanup_status != "RETAINED"
        or artifact.payload_blob is None
        or expires_at is None
        or expires_at <= business_now()
    ):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "UPLOAD_ARTIFACT_UNAVAILABLE",
                "message": "原始文件已过期或清理，请创建新导入批次",
            },
        )
    content = bytes(artifact.payload_blob)
    if (
        hashlib.sha256(content).hexdigest() != artifact.source_sha256
        or len(content) != artifact.size_bytes
    ):
        raise HTTPException(status_code=409, detail="原始文件完整性校验失败")
    normalized, issues = _parse_and_reconcile(
        db,
        factory_id=factory_id,
        source_file_name=batch.source_file_name,
        content=content,
        document_kind=batch.document_kind,
    )
    generation = batch.preview_generation + 1
    timestamp = _now()
    if batch.document_kind == "DEMAND_ORDER":
        prior_final_rows = list(
            db.scalars(
                select(InjectionSchedulingDemandImportRow)
                .where(
                    InjectionSchedulingDemandImportRow.batch_id == batch.id,
                    InjectionSchedulingDemandImportRow.confirmation_state.in_(
                        {"CONFIRMED", "RETAINED_FINAL"}
                    ),
                )
                .order_by(InjectionSchedulingDemandImportRow.preview_generation.desc())
            ).all()
        )
        prior_by_key: dict[str, InjectionSchedulingDemandImportRow] = {}
        for prior in prior_final_rows:
            prior_by_key.setdefault(prior.stable_line_key, prior)
        retained_count = 0
        for index, row in enumerate(normalized.get("demand_rows", []), start=1):
            row["row_id"] = (
                f"isdemrow-{batch.id.removeprefix('isimport-')}-{generation}-{index}"
            )
            row_digest = _payload_hash(
                {"canonical": row.get("canonical", {}), "source": row.get("source", {})}
            )
            prior = prior_by_key.get(row.get("stable_line_key", ""))
            if prior is None or prior.row_digest != row_digest:
                continue
            prior_snapshot = db.scalar(
                select(InjectionSchedulingDemandResolutionSnapshot).where(
                    InjectionSchedulingDemandResolutionSnapshot.demand_import_row_id
                    == prior.id,
                    InjectionSchedulingDemandResolutionSnapshot.preview_generation
                    == prior.preview_generation,
                )
            )
            if prior_snapshot is None:
                continue
            row["resolution_status"] = "AUTO_CONFIRMED"
            row["resolution_reasons"] = ["retained_final_from_previous_generation"]
            row["resolved_values"] = _load_json(prior_snapshot.resolved_values_json, {})
            row["provenance"] = _load_json(prior_snapshot.provenance_json, {})
            row["candidates"] = _load_json(prior_snapshot.candidate_json, {})
            row["master_revision_digest"] = prior_snapshot.master_revision_digest
            row["resolution_digest"] = prior_snapshot.resolution_digest
            row["confirmation_state"] = "RETAINED_FINAL"
            row["final_order_identity_id"] = prior.confirmed_order_identity_id
            row["final_order_version_id"] = prior.confirmed_order_version_id
            row["final_plan_order_state_id"] = prior.confirmed_plan_order_state_id
            retained_count += 1
        ready_count = sum(
            row.get("resolution_status") == "READY"
            for row in normalized.get("demand_rows", [])
        )
        normalized["summary"]["ready_count"] = ready_count
        normalized["summary"]["retained_final_count"] = retained_count
        normalized["summary"]["review_required_count"] = sum(
            row.get("resolution_status") not in {"READY", "AUTO_CONFIRMED"}
            for row in normalized.get("demand_rows", [])
        )
        normalized["summary"]["can_confirm"] = ready_count > 0
        if retained_count:
            normalized["batch_state"] = "PARTIALLY_CONFIRMED"
        normalized["resolution_digest"] = _payload_hash(
            [
                (row.get("stable_line_key", ""), row.get("resolution_digest", ""))
                for row in normalized.get("demand_rows", [])
            ]
        )
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
    elif batch.document_kind == "MASTER_DATA":
        for index, row in enumerate(normalized.get("master_data_rows", []), start=1):
            row["row_id"] = (
                f"ismasterrow-{batch.id.removeprefix('isimport-')}-{generation}-{index}"
            )
        normalized.pop("normalized_sha256", None)
        normalized["normalized_sha256"] = _payload_hash(normalized)
    profile = normalized.get("profile") or {}
    context = normalized.get("plan_context") or {}
    batch.plan_sheet_name = next(
        (
            item["sheet_name"]
            for item in normalized.get("sheet_roles", [])
            if item.get("role") == "CURRENT_PLAN"
        ),
        "",
    )
    batch.profile_id = profile.get("profile_id")
    batch.profile_revision = profile.get("revision")
    batch.profile_definition_sha256 = profile.get("definition_digest", "")
    batch.template_signature = normalized.get("template_signature", "")
    batch.mapping_fingerprint = normalized.get("mapping_fingerprint", "")
    batch.document_kind = normalized.get("document_kind", batch.document_kind)
    batch.source_namespace_id = normalized.get(
        "source_namespace_id", batch.source_namespace_id
    )
    batch.resolution_digest = normalized.get("resolution_digest", "")
    batch.mapping_draft_json = _json(normalized.get("mapping_draft", {}))
    batch.batch_state = normalized.get("batch_state", "MAPPING_REQUIRED")
    batch.preview_generation = generation
    batch.target_draft_plan_id = context.get("target_draft_plan_id", "")
    batch.target_draft_plan_revision = context.get("target_draft_plan_revision", 0)
    batch.reference_published_plan_id = context.get("reference_published_plan_id", "")
    batch.reference_published_plan_revision = context.get(
        "reference_published_plan_revision", 0
    )
    batch.reference_published_event_sequence = context.get(
        "reference_published_event_sequence", 0
    )
    batch.order_task_revision_digest = context.get("order_task_revision_digest", "")
    batch.action_fingerprint = normalized.get("action_fingerprint", "")
    batch.rule_revision = context.get("rule_revision", 0)
    batch.master_revision_digest = context.get("master_revision_digest", "")
    batch.parser_version = normalized["parser_version"]
    batch.preview_schema_version = normalized["schema_version"]
    batch.normalized_json = _json(normalized)
    batch.normalized_sha256 = normalized["normalized_sha256"]
    batch.summary_json = _json(normalized["summary"])
    batch.issue_count = normalized["summary"]["issue_count"]
    batch.blocking_issue_count = normalized["summary"]["blocking_issue_count"]
    batch.revision += 1
    if batch.document_kind == "DEMAND_ORDER":
        for row in normalized.get("demand_rows", []):
            confirmation_state = row.get("confirmation_state", "PENDING")
            prior = prior_by_key.get(row.get("stable_line_key", ""))
            demand_row = InjectionSchedulingDemandImportRow(
                id=row["row_id"],
                batch_id=batch.id,
                factory_id=factory_id,
                preview_generation=generation,
                source_sheet_name=row.get("source", {}).get("sheet_name", ""),
                source_row=int(row.get("source", {}).get("source_row") or 0),
                source_order_line_id=row.get("source_order_line_id", ""),
                source_revision=row.get("source_revision", ""),
                stable_line_key=row.get("stable_line_key", ""),
                identity_quality=row.get("identity_quality", "FALLBACK_BUSINESS_KEY"),
                canonical_json=_json(row.get("canonical", {})),
                source_lineage_json=_json(row.get("source_lineage", {})),
                resolution_status=row.get("resolution_status", "INVALID"),
                confirmation_state=confirmation_state,
                row_digest=_payload_hash(
                    {
                        "canonical": row.get("canonical", {}),
                        "source": row.get("source", {}),
                    }
                ),
                confirmed_generation=(
                    prior.confirmed_generation
                    if confirmation_state == "RETAINED_FINAL" and prior
                    else None
                ),
                confirmed_order_identity_id=(
                    prior.confirmed_order_identity_id
                    if confirmation_state == "RETAINED_FINAL" and prior
                    else ""
                ),
                confirmed_order_version_id=(
                    prior.confirmed_order_version_id
                    if confirmation_state == "RETAINED_FINAL" and prior
                    else ""
                ),
                confirmed_plan_order_state_id=(
                    prior.confirmed_plan_order_state_id
                    if confirmation_state == "RETAINED_FINAL" and prior
                    else ""
                ),
                confirm_request_id=(
                    prior.confirm_request_id
                    if confirmation_state == "RETAINED_FINAL" and prior
                    else ""
                ),
                created_at=timestamp,
            )
            db.add(demand_row)
            resolved = row.get("resolved_values", {})
            db.add(
                InjectionSchedulingDemandResolutionSnapshot(
                    id=f"isdemres-{uuid4().hex}",
                    demand_import_row_id=demand_row.id,
                    preview_generation=generation,
                    resolution_status=demand_row.resolution_status,
                    mold_definition_id=resolved.get("mold_definition_id"),
                    mold_output_spec_id=resolved.get("mold_output_spec_id"),
                    physical_mold_asset_id=resolved.get("physical_mold_asset_id"),
                    factory_capability_id=resolved.get("factory_capability_id"),
                    commercial_rate_rule_id=resolved.get("commercial_rate_rule_id"),
                    master_revision_digest=row.get("master_revision_digest", ""),
                    resolution_digest=row.get("resolution_digest", ""),
                    resolved_values_json=_json(resolved),
                    provenance_json=_json(row.get("provenance", {})),
                    candidate_json=_json(row.get("candidates", {})),
                    created_by=user.id,
                    created_at=timestamp,
                )
            )
    for action in normalized.get("reconciliation_actions", []):
        db.add(
            InjectionSchedulingImportAction(
                id=f"isaction-{uuid4().hex}",
                batch_id=batch.id,
                factory_id=factory_id,
                preview_generation=generation,
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
                batch_id=batch.id,
                factory_id=factory_id,
                preview_generation=generation,
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
            event_type="import_batch_reidentified",
            entity_type="import_batch",
            entity_id=batch.id,
            entity_revision=batch.revision,
            request_id=payload.request_id,
            detail={
                "payload_hash": payload_hash,
                "preview_generation": generation,
                "batch_state": batch.batch_state,
                "artifact_sha256": artifact.source_sha256,
            },
            user=user,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="导入批次重新识别冲突") from exc
    return batch, False


def update_import_mapping_draft(
    db: Session,
    *,
    batch_id: str,
    factory_id: str,
    expected_revision: int,
    request_id: str,
    mappings: dict[str, str],
    user: AuthContext,
) -> InjectionSchedulingImportBatch:
    batch = db.scalar(
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.revision != expected_revision:
        raise HTTPException(status_code=409, detail="导入批次已变化，请重新加载")
    if batch.status != "PREVIEW" or batch.document_kind != "DEMAND_ORDER":
        raise HTTPException(status_code=409, detail="只有未确认的需求单批次可编辑映射")
    if batch.batch_state not in {"MAPPING_REQUIRED", "PROFILE_REVIEW_PENDING"}:
        raise HTTPException(status_code=409, detail="当前批次不需要字段映射")
    unknown_fields = set(mappings) - set(CANONICAL_FIELD_CATALOG)
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail={"message": "存在未知规范字段", "fields": sorted(unknown_fields)},
        )
    if len(set(mappings.values())) != len(mappings):
        raise HTTPException(status_code=422, detail="同一来源表头不能映射到多个字段")
    normalized = _load_json(batch.normalized_json, {})
    available_headers = {
        str(item.get("raw_header", "")).strip()
        for item in normalized.get("mapping", [])
        if str(item.get("raw_header", "")).strip()
    }
    unknown_headers = set(mappings.values()) - available_headers
    if unknown_headers:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "来源表头不属于当前预览",
                "headers": sorted(unknown_headers),
            },
        )
    timestamp = _now()
    draft = {
        "mappings": dict(sorted(mappings.items())),
        "preview_generation": batch.preview_generation,
        "mapping_fingerprint": batch.mapping_fingerprint,
        "updated_by": user.id,
        "updated_at": timestamp,
    }
    batch.mapping_draft_json = _json(draft)
    batch.batch_state = "MAPPING_REQUIRED"
    batch.revision += 1
    _audit(
        db,
        factory_id=factory_id,
        event_type="import_mapping_draft_updated",
        entity_type="import_batch",
        entity_id=batch.id,
        entity_revision=batch.revision,
        request_id=request_id,
        detail={"mappings": draft["mappings"]},
        user=user,
    )
    db.commit()
    return batch


def propose_import_profile_from_batch(
    db: Session,
    *,
    batch_id: str,
    factory_id: str,
    expected_revision: int,
    request_id: str,
    name: str,
    reason: str,
    user: AuthContext,
) -> InjectionSchedulingImportBatch:
    batch = db.scalar(
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.revision != expected_revision:
        raise HTTPException(status_code=409, detail="导入批次已变化，请重新加载")
    draft = _load_json(batch.mapping_draft_json, {})
    mappings = draft.get("mappings") or {}
    if not mappings:
        raise HTTPException(status_code=409, detail="请先保存字段映射草案")
    if (
        draft.get("preview_generation") != batch.preview_generation
        or draft.get("mapping_fingerprint") != batch.mapping_fingerprint
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MAPPING_PROPOSAL_STALE",
                "message": "映射草案对应的 Preview 或映射摘要已变化，请重新预览",
            },
        )
    base = db.get(InjectionSchedulingImportProfile, batch.profile_id)
    if base is None or base.document_kind != "DEMAND_ORDER":
        raise HTTPException(status_code=409, detail="需求单基础 Profile 不可用")
    config = _load_json(base.config_json, {})
    fields = list(config.get("fields", []))
    by_name = {str(item.get("canonical_field", "")): item for item in fields}
    for canonical_field, raw_header in mappings.items():
        field = by_name.get(canonical_field)
        if field is None:
            raise HTTPException(
                status_code=422, detail=f"Profile 不支持字段 {canonical_field}"
            )
        headers = [str(item) for item in field.get("headers", [])]
        if raw_header not in headers:
            field["headers"] = [*headers, raw_header]
    latest_revision = int(
        db.scalar(
            select(func.max(InjectionSchedulingImportProfile.revision)).where(
                InjectionSchedulingImportProfile.profile_family == base.profile_family
            )
        )
        or 0
    )
    profile_code = f"{base.profile_family}-r{latest_revision + 1}-{batch.id[-6:]}"[:96]
    profile = create_profile_revision(
        db,
        factory_id=factory_id,
        profile_family=base.profile_family,
        profile_code=profile_code,
        name=name,
        description=reason,
        expected_family_revision=latest_revision,
        request_id=request_id,
        config=config,
        user=user,
    )
    batch = db.scalar(
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None or batch.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Profile 草案已创建，但导入批次同时发生变化",
                "profile_id": profile.id,
            },
        )
    proposal = {
        **draft,
        "proposal_profile_id": profile.id,
        "proposal_profile_revision": profile.revision,
        "proposed_by": user.id,
        "proposed_at": _now(),
    }
    batch.mapping_draft_json = _json(proposal)
    batch.batch_state = "PROFILE_REVIEW_PENDING"
    batch.revision += 1
    _audit(
        db,
        factory_id=factory_id,
        event_type="import_profile_proposed_from_batch",
        entity_type="import_batch",
        entity_id=batch.id,
        entity_revision=batch.revision,
        request_id=request_id,
        detail={"profile_id": profile.id, "reason": reason},
        user=user,
    )
    db.commit()
    return batch


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
            raise HTTPException(
                status_code=409, detail="相同 request_id 已用于其他主数据审批"
            )
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
            detail={
                "message": "包含不属于本批次的主数据差异",
                "differences": sorted(unknown),
            },
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
                        robot_capabilities_json=_json(
                            source.get("robot_capabilities", [])
                        ),
                        fixture_capabilities_json=_json(
                            source.get("fixture_capabilities", [])
                        ),
                        process_restrictions_json=_json(
                            source.get("process_restrictions", [])
                        ),
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
                row = next(
                    (item for item in rows if item.get("mold_no") == business_key), {}
                )
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
                "reconciliation_action_count": len(
                    reconciliation["reconciliation_actions"]
                ),
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
            export_profile_id="isprofile-system-standard-v1",
            export_profile_revision=1,
            export_profile_family="system_standard",
            export_renderer_code="system_standard_v1",
            export_binding_source="SYSTEM_STANDARD",
            calculation_version=CALCULATION_VERSION,
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
        or current_context.get("master_revision_digest") != batch.master_revision_digest
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
            if (
                payload.confirm_mode != "create_draft"
                or payload.expected_plan_revision != 0
            ):
                raise HTTPException(
                    status_code=409,
                    detail="当前确认将创建接管草案，请使用 create_draft 且 revision=0",
                )
        else:
            if payload.confirm_mode != "merge_draft":
                raise HTTPException(
                    status_code=409, detail="当前厂区已有草案，请使用 merge_draft"
                )
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
        profile = normalized.get("profile") or {}
        if not batch.profile_id or batch.profile_revision is None:
            raise HTTPException(status_code=409, detail="规范导入缺少 Profile binding")
        signed_system_meta = normalized.get("system_meta") or {}
        binding_profile_id = signed_system_meta.get(
            "plan_export_profile_id", batch.profile_id
        )
        binding_profile_revision = signed_system_meta.get(
            "plan_export_profile_revision", batch.profile_revision
        )
        binding_profile_family = signed_system_meta.get(
            "plan_export_profile_family", profile.get("profile_family", "")
        )
        binding_renderer_code = signed_system_meta.get(
            "plan_export_renderer_code", profile.get("renderer_code", "")
        )
        binding_source = signed_system_meta.get(
            "plan_export_binding_source", "IMPORT_PROFILE"
        )
        if plan.export_binding_source == "IMPORT_PROFILE" and (
            plan.export_profile_id != binding_profile_id
            or plan.export_profile_revision != binding_profile_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PLAN_EXPORT_PROFILE_CONFLICT",
                    "message": "目标草案已经绑定其他来源 Profile revision",
                },
            )
        plan.export_profile_id = binding_profile_id
        plan.export_profile_revision = binding_profile_revision
        plan.export_profile_family = str(binding_profile_family)
        plan.export_renderer_code = str(binding_renderer_code)
        plan.export_binding_source = str(binding_source)
        plan.calculation_version = CALCULATION_VERSION
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


def _confirm_demand_order(
    db: Session,
    *,
    batch: InjectionSchedulingImportBatch,
    payload: InjectionSchedulingImportConfirm,
    normalized: dict[str, Any],
    confirm_payload_hash: str,
    user: AuthContext,
) -> InjectionSchedulingImportBatch:
    if payload.document_kind not in {None, "DEMAND_ORDER"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_KIND_MISMATCH",
                "message": "确认 document_kind 与批次不一致",
            },
        )
    if payload.expected_preview_generation != batch.preview_generation:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_GENERATION_STALE",
                "message": "需求单预览代次已变化，请重新加载",
                "current_preview_generation": batch.preview_generation,
            },
        )
    if (
        payload.expected_resolution_digest
        and payload.expected_resolution_digest != batch.resolution_digest
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RESOLUTION_DIGEST_STALE",
                "message": "字段补齐结果已变化，请重新预览",
            },
        )
    company_scope_id = str(normalized.get("company_scope_id", ""))
    current_master_digest = master_revision_digest(db, company_scope_id)
    if current_master_digest != batch.master_revision_digest:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MASTER_DATA_STALE",
                "message": "共享模具、客户、厂区能力或价格规则已变化，请重试识别",
            },
        )
    profile_record = db.scalar(
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
            InjectionSchedulingImportProfile.document_kind == "DEMAND_ORDER",
            InjectionSchedulingImportProfileFactory.factory_id == batch.factory_id,
        )
        .with_for_update()
    )
    if (
        profile_record is None
        or profile_record.definition_sha256 != batch.profile_definition_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IMPORT_PROFILE_STALE",
                "message": "需求单 Profile 已变化，请重新预览",
            },
        )
    current_draft = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == batch.factory_id,
            InjectionSchedulingPlan.status == "DRAFT",
        )
        .with_for_update()
    )
    current_published = db.scalar(
        select(InjectionSchedulingPlan)
        .where(
            InjectionSchedulingPlan.factory_id == batch.factory_id,
            InjectionSchedulingPlan.status == "PUBLISHED",
        )
        .order_by(InjectionSchedulingPlan.published_at.desc())
        .with_for_update()
    )
    bound_draft_id = batch.target_draft_plan_id
    bound_draft_revision = batch.target_draft_plan_revision
    if bound_draft_id:
        if (
            current_draft is None
            or current_draft.id != bound_draft_id
            or current_draft.revision != bound_draft_revision
            or payload.confirm_mode != "merge_draft"
            or payload.expected_plan_revision != bound_draft_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TARGET_DRAFT_STALE",
                    "message": "预览绑定的 planning DRAFT 已变化，请重新预览",
                },
            )
        bound_plan = current_draft
    else:
        if (
            current_draft is not None
            or payload.confirm_mode != "create_draft"
            or payload.expected_plan_revision != 0
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TARGET_DRAFT_STALE",
                    "message": "预览后出现了新的 planning DRAFT，请重新预览",
                },
            )
        bound_plan = current_published
    if batch.reference_published_plan_id:
        if (
            current_published is None
            or current_published.id != batch.reference_published_plan_id
            or current_published.revision != batch.reference_published_plan_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REFERENCE_PUBLISHED_STALE",
                    "message": "预览绑定的 execution PUBLISHED 已变化，请重新预览",
                },
            )
    elif current_published is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REFERENCE_PUBLISHED_STALE",
                "message": "预览后出现了 execution PUBLISHED，请重新预览",
            },
        )
    if _plan_binding_digest(db, bound_plan.id if bound_plan else "") != (
        batch.order_task_revision_digest
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PLAN_BINDING_STALE",
                "message": "预览绑定计划的订单、任务或进度已变化，请重新预览",
            },
        )
    demand_rows = list(
        db.scalars(
            select(InjectionSchedulingDemandImportRow)
            .where(
                InjectionSchedulingDemandImportRow.batch_id == batch.id,
                InjectionSchedulingDemandImportRow.preview_generation
                == batch.preview_generation,
            )
            .order_by(
                InjectionSchedulingDemandImportRow.source_sheet_name,
                InjectionSchedulingDemandImportRow.source_row,
            )
            .with_for_update()
        ).all()
    )
    ready_rows = [
        item
        for item in demand_rows
        if item.resolution_status == "READY" and item.confirmation_state == "PENDING"
    ]
    selected_ids = set(payload.selected_row_ids)
    if payload.confirm_scope == "SELECTED":
        unknown = selected_ids - {item.id for item in ready_rows}
        if unknown:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "DEMAND_ROWS_NOT_CONFIRMABLE",
                    "message": "所选行不是当前代次的 READY 未确认行",
                    "row_ids": sorted(unknown),
                },
            )
        confirm_rows = [item for item in ready_rows if item.id in selected_ids]
    else:
        confirm_rows = ready_rows
    if not confirm_rows:
        raise HTTPException(status_code=409, detail="当前没有可确认的 READY 需求行")

    timestamp = _now()
    plan, created_plan, successor_created = prepare_takeover_plan(
        db,
        factory_id=batch.factory_id,
        business_date=payload.business_date.isoformat(),
        user=user,
        timestamp=timestamp,
    )
    if payload.confirm_mode == "create_draft" and not created_plan:
        raise HTTPException(status_code=409, detail="当前厂区已有草案，请改用合并草案")
    if payload.confirm_mode == "merge_draft":
        if created_plan:
            raise HTTPException(status_code=409, detail="当前厂区原本没有可合并的草案")
        if plan.revision != payload.expected_plan_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "排产草案已被其他操作更新",
                    "expected_revision": payload.expected_plan_revision,
                    "current_revision": plan.revision,
                },
            )
    if payload.target_draft_plan_id and payload.target_draft_plan_id != plan.id:
        raise HTTPException(status_code=409, detail="目标 DRAFT 已变化，请重新加载")
    if (
        payload.reference_published_plan_id
        and payload.reference_published_plan_id != plan.based_on_plan_id
    ):
        raise HTTPException(status_code=409, detail="参考 PUBLISHED 基线已变化")

    normalized_rows = {
        str(item.get("row_id", "")): item for item in normalized.get("demand_rows", [])
    }
    created_identities = 0
    created_versions = 0
    created_orders = 0
    created_states = 0
    reused_versions = 0
    for import_row in confirm_rows:
        normalized_row = normalized_rows.get(import_row.id)
        if normalized_row is None:
            raise HTTPException(status_code=409, detail="需求行快照缺失，请重新上传")
        snapshot = db.scalar(
            select(InjectionSchedulingDemandResolutionSnapshot).where(
                InjectionSchedulingDemandResolutionSnapshot.demand_import_row_id
                == import_row.id,
                InjectionSchedulingDemandResolutionSnapshot.preview_generation
                == batch.preview_generation,
            )
        )
        if snapshot is None or snapshot.resolution_digest != normalized_row.get(
            "resolution_digest"
        ):
            raise HTTPException(status_code=409, detail="需求行解析快照不一致")
        canonical = _load_json(import_row.canonical_json, {})
        resolved = _load_json(snapshot.resolved_values_json, {})
        identity = db.scalar(
            select(InjectionSchedulingDemandOrderIdentity)
            .where(
                InjectionSchedulingDemandOrderIdentity.factory_id == batch.factory_id,
                InjectionSchedulingDemandOrderIdentity.stable_line_key
                == import_row.stable_line_key,
            )
            .with_for_update()
        )
        if identity is None:
            identity = InjectionSchedulingDemandOrderIdentity(
                id=f"isdemidentity-{uuid4().hex}",
                factory_id=batch.factory_id,
                source_system="EXCEL_DEMAND_ORDER",
                source_namespace_id=batch.source_namespace_id,
                source_document_id=str(canonical.get("source_document_no", "")),
                source_order_line_id=(
                    import_row.source_order_line_id or import_row.stable_line_key
                ),
                stable_line_key=import_row.stable_line_key,
                current_revision_no=0,
                status="ACTIVE",
                created_at=timestamp,
            )
            db.add(identity)
            db.flush()
            created_identities += 1
        version = db.scalar(
            select(InjectionSchedulingDemandOrderVersion).where(
                InjectionSchedulingDemandOrderVersion.order_identity_id == identity.id,
                InjectionSchedulingDemandOrderVersion.source_revision
                == import_row.source_revision,
            )
        )
        if version is None:
            revision_no = identity.current_revision_no + 1
            version_digest = _payload_hash(
                {
                    "identity_id": identity.id,
                    "revision_no": revision_no,
                    "canonical": canonical,
                    "resolved": resolved,
                    "resolution_digest": snapshot.resolution_digest,
                }
            )
            version = InjectionSchedulingDemandOrderVersion(
                id=f"isdemversion-{uuid4().hex}",
                order_identity_id=identity.id,
                source_revision=import_row.source_revision,
                revision_no=revision_no,
                customer_identity_id=resolved.get("customer_identity_id"),
                source_document_no=str(canonical.get("source_document_no", "")),
                item_no=str(canonical.get("item_no", "")),
                product_name=str(canonical.get("product_name", "")),
                mold_definition_id=resolved.get("mold_definition_id"),
                mold_output_spec_id=resolved.get("mold_output_spec_id"),
                factory_mold_id=None,
                order_quantity=_decimal(canonical.get("order_quantity")),
                set_quantity=(
                    _decimal(canonical.get("set_quantity"))
                    if canonical.get("set_quantity") is not None
                    else None
                ),
                required_shots=(
                    _decimal(canonical.get("required_shots"))
                    if canonical.get("required_shots") is not None
                    else None
                ),
                delivery_due_date=str(canonical.get("delivery_due_date", "")),
                warehouse_text=str(canonical.get("warehouse_text", "")),
                material_name=str(canonical.get("material_name", "")),
                color_name=str(canonical.get("color_name", "")),
                remark=str(canonical.get("remark", "")),
                readiness_status=resolved.get(
                    "factory_readiness_status", "NOT_FACTORY_READY"
                ),
                commercial_rate_rule_id=resolved.get("commercial_rate_rule_id"),
                frozen_amount=(
                    _decimal(resolved.get("frozen_amount"))
                    if resolved.get("frozen_amount") is not None
                    else None
                ),
                frozen_currency=str(resolved.get("frozen_currency", "")),
                frozen_pricing_basis=str(resolved.get("frozen_pricing_basis", "")),
                canonical_json=import_row.canonical_json,
                provenance_json=snapshot.provenance_json,
                source_lineage_json=import_row.source_lineage_json,
                version_digest=version_digest,
                status="ACTIVE",
                created_by=user.id,
                created_at=timestamp,
            )
            db.add(version)
            identity.current_revision_no = revision_no
            created_versions += 1
        else:
            reused_versions += 1
        legacy_mold = db.scalar(
            select(InjectionSchedulingMold).where(
                InjectionSchedulingMold.factory_id == batch.factory_id,
                InjectionSchedulingMold.definition_id == version.mold_definition_id,
            )
        )
        order = db.scalar(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == batch.factory_id,
                InjectionSchedulingOrder.source_type == "DEMAND_ORDER_VERSION",
                InjectionSchedulingOrder.source_ref == version.id,
            )
        )
        if order is None:
            order = InjectionSchedulingOrder(
                id=f"isorder-{uuid4().hex}",
                factory_id=batch.factory_id,
                order_no=version.source_document_no,
                item_no=version.item_no,
                product_name=version.product_name,
                mold_id=legacy_mold.id if legacy_mold else None,
                mold_definition_id=version.mold_definition_id,
                mold_output_spec_id=version.mold_output_spec_id,
                order_quantity=version.order_quantity,
                source_completed_quantity=Decimal(0),
                completed_quantity=Decimal(0),
                estimated_completion_at="",
                estimated_remaining_shifts=0,
                delivery_slack_days=_delivery_slack_days(version.delivery_due_date, ""),
                delivery_start_date="",
                delivery_due_date=version.delivery_due_date,
                priority_code="NORMAL",
                material_readiness_status="unknown",
                warehouse_text=version.warehouse_text,
                remark=version.remark,
                source_type="DEMAND_ORDER_VERSION",
                source_ref=version.id,
                source_version=version.version_digest,
                lineage_json=_json(
                    _demand_order_lineage(
                        batch=batch,
                        import_row=import_row,
                        identity=identity,
                        version=version,
                        canonical=canonical,
                        resolved=resolved,
                    )
                ),
                status="BACKLOG",
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
            created_orders += 1
        elif version.mold_definition_id:
            order.mold_definition_id = version.mold_definition_id
            order.mold_output_spec_id = version.mold_output_spec_id
        state = db.scalar(
            select(InjectionSchedulingPlanOrderState).where(
                InjectionSchedulingPlanOrderState.plan_id == plan.id,
                InjectionSchedulingPlanOrderState.stable_order_key
                == identity.stable_line_key,
            )
        )
        if state is None:
            state = InjectionSchedulingPlanOrderState(
                id=f"isorderstate-{uuid4().hex}",
                factory_id=batch.factory_id,
                plan_id=plan.id,
                order_id=order.id,
                stable_order_key=identity.stable_line_key,
                order_quantity=version.order_quantity,
                delivery_start_date="",
                delivery_due_date=version.delivery_due_date,
                takeover_source_completed_quantity=Decimal(0),
                report_increment_total=Decimal(0),
                progress_adjustment_total=Decimal(0),
                completed_quantity=Decimal(0),
                status="BACKLOG",
                quantity_scope="ORDER_CUMULATIVE",
                source_batch_id=batch.id,
                source_sheet_name=import_row.source_sheet_name,
                source_row=import_row.source_row,
                source_profile_id=batch.profile_id,
                source_profile_revision=batch.profile_revision,
                source_lineage_json=import_row.source_lineage_json,
                order_revision_id=version.id,
                factory_readiness_status=version.readiness_status,
                revision=1,
                created_by=user.id,
                created_by_name=_actor_name(user),
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.add(state)
            created_states += 1
        elif state.order_revision_id != version.id:
            state.order_id = order.id
            state.order_quantity = version.order_quantity
            state.delivery_due_date = version.delivery_due_date
            state.source_batch_id = batch.id
            state.source_sheet_name = import_row.source_sheet_name
            state.source_row = import_row.source_row
            state.source_profile_id = batch.profile_id
            state.source_profile_revision = batch.profile_revision
            state.source_lineage_json = import_row.source_lineage_json
            state.order_revision_id = version.id
            state.factory_readiness_status = version.readiness_status
            state.status = "BACKLOG"
            state.revision += 1
            state.updated_by = user.id
            state.updated_by_name = _actor_name(user)
            state.updated_at = timestamp
        import_row.confirmation_state = "CONFIRMED"
        import_row.confirmed_generation = batch.preview_generation
        import_row.confirmed_order_identity_id = identity.id
        import_row.confirmed_order_version_id = version.id
        import_row.confirmed_plan_order_state_id = state.id
        import_row.confirm_request_id = payload.request_id

    if not created_plan:
        plan.revision += 1
    plan.updated_by = user.id
    plan.updated_by_name = _actor_name(user)
    plan.updated_at = timestamp
    db.flush()
    _record_plan_revision(db, plan=plan, user=user, timestamp=timestamp)
    remaining = sum(item.confirmation_state == "PENDING" for item in demand_rows)
    batch.status = "PARTIALLY_CONFIRMED" if remaining else "CONFIRMED"
    batch.batch_state = "PARTIALLY_CONFIRMED" if remaining else "CONFIRMED"
    batch.revision += 1
    batch.confirm_request_id = payload.request_id
    batch.confirm_payload_hash = confirm_payload_hash
    batch.confirm_mode = payload.confirm_mode
    batch.confirmed_plan_id = plan.id
    batch.confirmed_plan_revision = plan.revision
    batch.confirmed_by = user.id
    batch.confirmed_by_name = _actor_name(user)
    batch.confirmed_at = timestamp
    context = normalized.setdefault("plan_context", {})
    context.update(
        {
            "target_draft_plan_id": plan.id,
            "target_draft_plan_revision": plan.revision,
            "order_task_revision_digest": _plan_binding_digest(db, plan.id),
        }
    )
    batch.target_draft_plan_id = plan.id
    batch.target_draft_plan_revision = plan.revision
    batch.order_task_revision_digest = context["order_task_revision_digest"]
    normalized.pop("normalized_sha256", None)
    normalized["normalized_sha256"] = _payload_hash(normalized)
    batch.normalized_json = _json(normalized)
    batch.normalized_sha256 = normalized["normalized_sha256"]
    result = {
        "document_kind": "DEMAND_ORDER",
        "plan_created": created_plan,
        "successor_created": successor_created,
        "confirmed_row_count": len(confirm_rows),
        "remaining_row_count": remaining,
        "created_identities": created_identities,
        "created_versions": created_versions,
        "reused_versions": reused_versions,
        "created_orders": created_orders,
        "created_plan_order_states": created_states,
        "created_tasks": 0,
        "target_plan_status": plan.status,
        "backlog_only": True,
    }
    batch.result_json = _json(result)
    history = _load_json(batch.partial_confirmation_json, {}).get("history", [])
    history.append(
        {
            "request_id": payload.request_id,
            "confirmed_row_ids": [item.id for item in confirm_rows],
            "confirmed_at": timestamp,
            "plan_id": plan.id,
            "plan_revision": plan.revision,
        }
    )
    batch.partial_confirmation_json = _json({"history": history})
    _audit(
        db,
        factory_id=batch.factory_id,
        event_type="demand_order_rows_confirmed",
        entity_type="import_batch",
        entity_id=batch.id,
        entity_revision=batch.revision,
        request_id=payload.request_id,
        detail=result,
        user=user,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="需求单确认并发冲突") from exc
    return batch


def master_import_required_permissions(
    batch: InjectionSchedulingImportBatch,
    selected_row_ids: list[str] | None = None,
) -> set[str]:
    normalized = _load_json(batch.normalized_json, {})
    selected = set(selected_row_ids or [])
    entity_types = {
        str(row.get("entity_type", ""))
        for row in normalized.get("master_data_rows", [])
        if not selected or str(row.get("row_id", "")) in selected
    }
    permissions: set[str] = set()
    if "MOLD_DEFINITION_BUNDLE" in entity_types:
        permissions.add("shared_mold:propose")
    if "COMMERCIAL_RATE_RULE" in entity_types:
        permissions.add("shared_mold_price:propose")
    return permissions


def _confirm_master_data(
    db: Session,
    *,
    batch: InjectionSchedulingImportBatch,
    payload: InjectionSchedulingImportConfirm,
    normalized: dict[str, Any],
    confirm_payload_hash: str,
    user: AuthContext,
) -> InjectionSchedulingImportBatch:
    if payload.document_kind not in {None, "MASTER_DATA"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_KIND_MISMATCH",
                "message": "确认 document_kind 与主数据批次不一致",
            },
        )
    if payload.expected_preview_generation != batch.preview_generation:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_GENERATION_STALE",
                "message": "主数据预览代次已变化，请重新加载",
            },
        )
    if payload.expected_resolution_digest != batch.resolution_digest:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MASTER_DATA_RESOLUTION_STALE",
                "message": "主数据解析摘要已变化，请重新预览",
            },
        )
    company_scope_id = db.scalar(
        select(InjectionSchedulingCompanyFactoryMembership.company_scope_id).where(
            InjectionSchedulingCompanyFactoryMembership.factory_id == batch.factory_id,
            InjectionSchedulingCompanyFactoryMembership.status == "ACTIVE",
        )
    )
    if not company_scope_id:
        raise HTTPException(status_code=409, detail="当前厂区没有 ACTIVE 公司归属")
    current_master_digest = master_revision_digest(db, str(company_scope_id))
    if current_master_digest != normalized.get("master_revision_digest", ""):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MASTER_DATA_STALE",
                "message": "共享模具或价格主数据已变化，请重新预览",
            },
        )
    rows = list(normalized.get("master_data_rows", []))
    pending = [
        row
        for row in rows
        if row.get("resolution_status") == "PROPOSABLE"
        and row.get("confirmation_state", "PENDING") == "PENDING"
    ]
    if payload.confirm_scope == "SELECTED":
        selected = set(payload.selected_row_ids)
        missing = sorted(selected - {str(row.get("row_id", "")) for row in pending})
        if missing:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MASTER_DATA_ROWS_NOT_PROPOSABLE",
                    "message": "所选主数据行已变化、已提交或仍需复核",
                    "row_ids": missing,
                },
            )
        confirm_rows = [row for row in pending if row.get("row_id") in selected]
    else:
        confirm_rows = pending
    if not confirm_rows:
        raise HTTPException(status_code=409, detail="没有可提交的主数据提案行")

    timestamp = _now()
    actor_name = _actor_name(user)
    proposal_ids: list[str] = []
    for row in confirm_rows:
        row_id = str(row["row_id"])
        proposal_id = f"ismasterproposal-{uuid4().hex}"
        entity_type = str(row.get("entity_type", ""))
        scope_type = "COMPANY"
        controlled_payload = {
            "batch_id": batch.id,
            "preview_generation": batch.preview_generation,
            "row_id": row_id,
            "row_digest": row.get("row_digest", ""),
            "factory_id": batch.factory_id,
            "source_namespace_id": batch.source_namespace_id,
            "canonical": row.get("canonical", {}),
            "activation_blockers": row.get("activation_blockers", []),
            "source": row.get("source", {}),
        }
        proposal_request_id = (
            "master-import:"
            + _payload_hash({"request_id": payload.request_id, "row_id": row_id})[:48]
        )
        proposal = InjectionSchedulingMasterDataProposal(
            id=proposal_id,
            entity_type=entity_type,
            action_type="CREATE",
            target_entity_id="",
            scope_type=scope_type,
            scope_id=str(company_scope_id),
            payload_json=_json(controlled_payload),
            evidence_digest=_payload_hash(row.get("source_lineage", {})),
            status="PROPOSED",
            revision=1,
            request_id=proposal_request_id,
            proposed_by=user.id,
            proposed_by_name=actor_name,
            approved_by="",
            approved_by_name="",
            reason="由受控主数据导入批次提交；批准不会自动激活未签字价格口径",
            created_at=timestamp,
            reviewed_at="",
        )
        db.add(proposal)
        for field_name, evidence in row.get("source_lineage", {}).items():
            if not evidence.get("displayed_value") and not evidence.get("raw_value"):
                continue
            db.add(
                InjectionSchedulingFieldEvidence(
                    id=f"isfieldevidence-{uuid4().hex}",
                    proposal_id=proposal_id,
                    entity_type=entity_type,
                    entity_id=proposal_id,
                    field_name=str(field_name),
                    source_file_hash=batch.source_file_hash,
                    sheet_name=str(row.get("source", {}).get("sheet_name", "")),
                    source_row=int(row.get("source", {}).get("source_row") or 0),
                    cell_ref=str(evidence.get("cell_ref", "")),
                    raw_value=str(evidence.get("raw_value", "")),
                    displayed_value=str(evidence.get("displayed_value", "")),
                    confidence="SOURCE_FACT",
                    submitted_by=user.id,
                    approved_by="",
                    created_at=timestamp,
                )
            )
        row["confirmation_state"] = "PROPOSED"
        row["proposal_id"] = proposal_id
        proposal_ids.append(proposal_id)

    remaining = any(
        row.get("resolution_status") == "PROPOSABLE"
        and row.get("confirmation_state", "PENDING") == "PENDING"
        for row in rows
    )
    batch.status = "PARTIALLY_CONFIRMED" if remaining else "CONFIRMED"
    batch.batch_state = "PARTIALLY_CONFIRMED" if remaining else "CONFIRMED"
    batch.revision += 1
    batch.confirm_request_id = payload.request_id if not remaining else None
    batch.confirm_payload_hash = confirm_payload_hash if not remaining else ""
    batch.confirm_mode = "propose_master_data"
    batch.confirmed_by = user.id if not remaining else ""
    batch.confirmed_by_name = actor_name if not remaining else ""
    batch.confirmed_at = timestamp if not remaining else ""
    normalized["master_data_rows"] = rows
    normalized["batch_state"] = batch.batch_state
    normalized["summary"]["proposed_count"] = sum(
        row.get("confirmation_state") == "PROPOSED" for row in rows
    )
    normalized.pop("normalized_sha256", None)
    normalized["normalized_sha256"] = _payload_hash(normalized)
    batch.normalized_json = _json(normalized)
    batch.normalized_sha256 = normalized["normalized_sha256"]
    batch.summary_json = _json(normalized["summary"])
    result = {
        "document_kind": "MASTER_DATA",
        "proposal_ids": proposal_ids,
        "created_proposals": len(proposal_ids),
        "remaining_proposable_rows": sum(
            row.get("resolution_status") == "PROPOSABLE"
            and row.get("confirmation_state", "PENDING") == "PENDING"
            for row in rows
        ),
        "activation_performed": False,
    }
    batch.result_json = _json(result)
    history = _load_json(batch.partial_confirmation_json, {}).get("history", [])
    history.append(
        {
            "request_id": payload.request_id,
            "proposed_row_ids": [str(item["row_id"]) for item in confirm_rows],
            "proposal_ids": proposal_ids,
            "confirmed_at": timestamp,
        }
    )
    batch.partial_confirmation_json = _json({"history": history})
    _audit(
        db,
        factory_id=batch.factory_id,
        event_type="master_data_rows_proposed",
        entity_type="import_batch",
        entity_id=batch.id,
        entity_revision=batch.revision,
        request_id=payload.request_id,
        detail=result,
        user=user,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="主数据提案写入并发冲突") from exc
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
        select(InjectionSchedulingImportBatch)
        .where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if (
        batch.confirm_request_id == payload.request_id
        and batch.confirm_payload_hash == confirm_payload_hash
    ):
        return batch, True
    prior_request_ids = {
        str(item.get("request_id", ""))
        for item in _load_json(batch.partial_confirmation_json, {}).get("history", [])
    }
    if payload.request_id in prior_request_ids:
        return batch, True
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
    if payload.document_kind and payload.document_kind != batch.document_kind:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_KIND_MISMATCH",
                "message": "确认 document_kind 与已锁定批次不一致",
            },
        )
    if batch.document_kind == "DEMAND_ORDER":
        rollout_policy = db.get(InjectionSchedulingRolloutPolicy, factory_id)
        demand_mode = (
            rollout_policy.demand_mode
            if rollout_policy is not None
            else "MANUAL_CONFIRM"
        )
        if demand_mode in {"SHADOW", "PREVIEW_ONLY"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DEMAND_IMPORT_ROLLOUT_PREVIEW_ONLY",
                    "message": "当前厂区仍处于影子/只预览阶段，不能确认写入 DRAFT",
                    "demand_mode": demand_mode,
                },
            )
        if batch.batch_state not in {"PREVIEW_READY", "PARTIALLY_CONFIRMED"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DEMAND_BATCH_NOT_READY",
                    "message": "需求单尚未完成映射或字段补齐，不能确认",
                    "batch_state": batch.batch_state,
                },
            )
        return (
            _confirm_demand_order(
                db,
                batch=batch,
                payload=payload,
                normalized=normalized,
                confirm_payload_hash=confirm_payload_hash,
                user=user,
            ),
            False,
        )
    if batch.document_kind == "MASTER_DATA":
        if batch.batch_state not in {"PREVIEW_READY", "PARTIALLY_CONFIRMED"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "MASTER_DATA_BATCH_NOT_READY",
                    "message": "主数据文件尚未完成映射，不能提交提案",
                    "batch_state": batch.batch_state,
                },
            )
        return (
            _confirm_master_data(
                db,
                batch=batch,
                payload=payload,
                normalized=normalized,
                confirm_payload_hash=confirm_payload_hash,
                user=user,
            ),
            False,
        )
    if batch.preview_schema_version == "injection-scheduling-canonical-v1":
        signed_system_meta = normalized.get("system_meta") or {}
        signed_profile = (
            signed_system_meta.get("profile_id") == batch.profile_id
            and signed_system_meta.get("profile_revision") == batch.profile_revision
        )
        allowed_profile_statuses = (
            ("ACTIVE", "RETIRED") if signed_profile else ("ACTIVE",)
        )
        active_profile_record = None
        if batch.profile_id != SYSTEM_STANDARD_EXPORT_PROFILE.profile_id:
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
                    InjectionSchedulingImportProfile.status.in_(
                        allowed_profile_statuses
                    ),
                    InjectionSchedulingImportProfileFactory.factory_id == factory_id,
                )
                .with_for_update()
            )
        profile_definition_matches = (
            batch.profile_id == SYSTEM_STANDARD_EXPORT_PROFILE.profile_id
            and signed_profile
            and batch.profile_definition_sha256
            == (normalized.get("profile") or {}).get("definition_digest", "")
        ) or (
            active_profile_record is not None
            and batch.profile_definition_sha256
            == active_profile_record.definition_sha256
        )
        if (
            not profile_definition_matches
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
                    InjectionSchedulingImportIssue.preview_generation
                    == batch.preview_generation,
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
                InjectionSchedulingImportIssue.preview_generation
                == batch.preview_generation,
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
