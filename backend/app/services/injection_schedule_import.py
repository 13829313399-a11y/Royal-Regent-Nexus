from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_schedule import (
    InjectionMachineMaster,
    InjectionMoldMaster,
    InjectionOrderMaster,
    InjectionScheduleAuditEvent,
    InjectionScheduleFactoryState,
    InjectionScheduleImportBatch,
    InjectionScheduleImportIssue,
    InjectionScheduleRuleConfig,
)
from app.schemas.injection_schedule import (
    InjectionMachineCreateRequest,
    InjectionMachineUpdateRequest,
    InjectionMoldCreateRequest,
    InjectionMoldUpdateRequest,
    InjectionOrderCreateRequest,
    InjectionOrderUpdateRequest,
)
from app.services.auth import AuthContext
from app.services.injection_schedule_excel import (
    canonical_json,
    normalize_key,
    parse_daily_schedule_workbook,
)
from app.services.injection_schedule_phase4_engine import (
    normalize_priority_code,
)
from app.services.injection_schedule_rules import (
    DEFAULT_RULE_CONFIG,
    normalize_rule_config,
)


def now_text() -> str:
    return business_now().strftime("%Y-%m-%d %H:%M:%S")


def json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def create_import_preview(
    db: Session,
    *,
    factory_id: str,
    source_file_name: str,
    source_content_type: str,
    content: bytes,
    actor: AuthContext,
    request_id: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    parsed = parse_daily_schedule_workbook(
        content,
        source_file_name,
        source_content_type,
    )
    existing = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.factory_id == factory_id,
            InjectionScheduleImportBatch.source_sha256 == parsed["source_sha256"],
        )
    )
    if existing is not None:
        return serialize_import_batch(db, existing)

    timestamp = now_text()
    batch = InjectionScheduleImportBatch(
        id=f"ISB-{uuid4().hex.upper()}",
        factory_id=factory_id,
        source_file_name=source_file_name,
        source_content_type=source_content_type,
        source_size_bytes=len(content),
        source_sha256=parsed["source_sha256"],
        source_content=content,
        parser_version=parsed["parser_version"],
        detected_sheets_json=canonical_json(parsed["detected_sheets"]),
        status="previewed",
        revision=1,
        business_date=parsed["business_date"],
        summary_json=canonical_json(parsed["summary"]),
        preview_json=canonical_json(parsed["preview"]),
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
    )
    db.add(batch)
    db.flush()
    for parsed_issue in parsed["issues"]:
        db.add(
            InjectionScheduleImportIssue(
                id=f"ISI-{uuid4().hex.upper()}",
                factory_id=factory_id,
                batch_id=batch.id,
                **parsed_issue,
            )
        )
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="import_batch",
        entity_id=batch.id,
        action="preview_created",
        actor=actor,
        request_id=request_id,
        ip_address=ip_address,
        new_revision=1,
        after={
            "source_file_name": source_file_name,
            "source_sha256": parsed["source_sha256"],
            "summary": parsed["summary"],
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(InjectionScheduleImportBatch).where(
                InjectionScheduleImportBatch.factory_id == factory_id,
                InjectionScheduleImportBatch.source_sha256
                == parsed["source_sha256"],
            )
        )
        if existing is None:
            raise
        return serialize_import_batch(db, existing)
    db.refresh(batch)
    return serialize_import_batch(db, batch)


def list_import_batches(
    db: Session,
    factory_id: str,
) -> list[dict[str, Any]]:
    batches = db.scalars(
        select(InjectionScheduleImportBatch)
        .where(InjectionScheduleImportBatch.factory_id == factory_id)
        .order_by(
            InjectionScheduleImportBatch.created_at.desc(),
            InjectionScheduleImportBatch.id.desc(),
        )
    ).all()
    return [serialize_import_batch(db, item, include_preview=False) for item in batches]


def load_import_batch(
    db: Session,
    factory_id: str,
    batch_id: str,
) -> InjectionScheduleImportBatch:
    batch = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.id == batch_id,
            InjectionScheduleImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的导入批次")
    return batch


def serialize_import_batch(
    db: Session,
    batch: InjectionScheduleImportBatch,
    *,
    include_preview: bool = True,
) -> dict[str, Any]:
    issues = db.scalars(
        select(InjectionScheduleImportIssue)
        .where(
            InjectionScheduleImportIssue.batch_id == batch.id,
            InjectionScheduleImportIssue.factory_id == batch.factory_id,
        )
        .order_by(
            InjectionScheduleImportIssue.source_row,
            InjectionScheduleImportIssue.id,
        )
    ).all()
    return {
        "id": batch.id,
        "factory_id": batch.factory_id,
        "source_file_name": batch.source_file_name,
        "source_content_type": batch.source_content_type,
        "source_size_bytes": batch.source_size_bytes,
        "source_sha256": batch.source_sha256,
        "parser_version": batch.parser_version,
        "detected_sheets": json_list(batch.detected_sheets_json),
        "status": batch.status,
        "revision": batch.revision,
        "business_date": batch.business_date,
        "draft_version_id": batch.draft_version_id,
        "summary": json_object(batch.summary_json),
        "preview": json_object(batch.preview_json) if include_preview else {},
        "issues": [
            {
                "id": item.id,
                "factory_id": item.factory_id,
                "batch_id": item.batch_id,
                "source_sheet": item.source_sheet,
                "source_row": item.source_row,
                "severity": item.severity,
                "code": item.code,
                "field_name": item.field_name,
                "blocking": bool(item.blocking),
                "raw_value": item.raw_value,
                "message": item.message,
            }
            for item in issues
        ],
        "created_by": batch.created_by,
        "created_by_name": batch.created_by_name,
        "created_at": batch.created_at,
        "confirmed_by": batch.confirmed_by,
        "confirmed_by_name": batch.confirmed_by_name,
        "confirmed_at": batch.confirmed_at,
        "confirm_reason": batch.confirm_reason,
        "rejected_by": batch.rejected_by,
        "rejected_by_name": batch.rejected_by_name,
        "rejected_at": batch.rejected_at,
        "rejection_reason": batch.rejection_reason,
    }


def confirm_import_batch(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
    expected_revision: int,
    business_date: str,
    reason: str,
    resolutions: dict[str, Any],
    actor: AuthContext,
    request_id: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    batch = load_import_batch(db, factory_id, batch_id)
    if batch.status != "previewed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "import_not_previewed",
                "message": "该批次已处理，不能重复确认",
                "current_revision": batch.revision,
                "expected_revision": expected_revision,
                "entity_id": batch.id,
            },
        )
    blocking_issue_ids = list(
        db.scalars(
            select(InjectionScheduleImportIssue.id)
        .where(
            InjectionScheduleImportIssue.batch_id == batch.id,
            InjectionScheduleImportIssue.factory_id == factory_id,
            InjectionScheduleImportIssue.blocking.is_(True),
        )
        .order_by(InjectionScheduleImportIssue.id)
        )
    )
    if blocking_issue_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "import_blocked",
                "message": "导入预览包含阻断问题，当前批次不能确认",
                "batch_id": batch.id,
                "unresolved_issue_ids": blocking_issue_ids,
            },
        )

    timestamp = now_text()
    updated = db.execute(
        update(InjectionScheduleImportBatch)
        .where(
            InjectionScheduleImportBatch.id == batch.id,
            InjectionScheduleImportBatch.factory_id == factory_id,
            InjectionScheduleImportBatch.status == "previewed",
            InjectionScheduleImportBatch.revision == expected_revision,
        )
        .values(
            status="confirmed",
            revision=InjectionScheduleImportBatch.revision + 1,
            business_date=business_date,
            confirmed_by=actor.id,
            confirmed_by_name=actor.display_name,
            confirmed_at=timestamp,
            confirm_reason=reason,
        )
    )
    if updated.rowcount != 1:
        db.rollback()
        current = load_import_batch(db, factory_id, batch_id)
        raise revision_conflict(current.id, expected_revision, current.revision)

    preview = json_object(batch.preview_json)
    try:
        # Keep the master lock order aligned with validate/publish/refresh:
        # order -> machine -> mold. This avoids a PostgreSQL lock cycle.
        merge_order_masters(
            db,
            factory_id,
            batch.id,
            preview.get("orders", []),
            actor,
            timestamp,
        )
        merge_machine_masters(
            db,
            factory_id,
            batch.id,
            preview.get("machines", []),
            actor,
            timestamp,
        )
        merge_mold_masters(
            db,
            factory_id,
            batch.id,
            preview.get("molds", []),
            actor,
            timestamp,
        )
        ensure_factory_defaults(db, factory_id, actor.id, timestamp)
        from app.schemas.injection_schedule import (
            InjectionScheduleVersionCreateRequest,
        )
        from app.services.injection_schedule import create_version

        draft = create_version(
            db,
            factory_id,
            InjectionScheduleVersionCreateRequest(
                name=f"{business_date} Excel 导入草稿",
                business_date=business_date,
                plan_base_at=f"{business_date} 08:00:00",
            ),
            actor,
            clone_reason=reason,
            source_batch_id_override=batch.id,
            commit=False,
        )
        batch.draft_version_id = draft["id"]
        add_audit_event(
            db,
            factory_id=factory_id,
            entity_type="import_batch",
            entity_id=batch.id,
            action="confirmed",
            actor=actor,
            request_id=request_id,
            ip_address=ip_address,
            reason=reason,
            old_revision=expected_revision,
            new_revision=expected_revision + 1,
            after={
                "business_date": business_date,
                "mode": "merge",
                "resolutions": resolutions,
                "summary": json_object(batch.summary_json),
                "draft_version_id": draft["id"],
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return serialize_import_batch(
        db,
        load_import_batch(db, factory_id, batch_id),
    )


def reject_import_batch(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
    expected_revision: int,
    reason: str,
    actor: AuthContext,
) -> dict[str, Any]:
    batch = load_import_batch(db, factory_id, batch_id)
    timestamp = now_text()
    result = db.execute(
        update(InjectionScheduleImportBatch)
        .where(
            InjectionScheduleImportBatch.id == batch_id,
            InjectionScheduleImportBatch.factory_id == factory_id,
            InjectionScheduleImportBatch.status == "previewed",
            InjectionScheduleImportBatch.revision == expected_revision,
        )
        .values(
            status="rejected",
            revision=InjectionScheduleImportBatch.revision + 1,
            rejected_by=actor.id,
            rejected_by_name=actor.display_name,
            rejected_at=timestamp,
            rejection_reason=reason,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = load_import_batch(db, factory_id, batch_id)
        raise revision_conflict(batch_id, expected_revision, current.revision)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="import_batch",
        entity_id=batch_id,
        action="rejected",
        actor=actor,
        reason=reason,
        old_revision=expected_revision,
        new_revision=expected_revision + 1,
    )
    db.commit()
    db.expire_all()
    return serialize_import_batch(
        db,
        load_import_batch(db, factory_id, batch_id),
    )


def merge_machine_masters(
    db: Session,
    factory_id: str,
    batch_id: str,
    sources: list[dict[str, Any]],
    actor: AuthContext,
    timestamp: str,
) -> None:
    existing = {
        item.machine_code: item
        for item in db.scalars(
            select(InjectionMachineMaster)
            .where(InjectionMachineMaster.factory_id == factory_id)
            .order_by(InjectionMachineMaster.id)
            .with_for_update()
        ).all()
    }
    field_map = {
        "machine_name": "machine_name",
        "workshop": "workshop",
        "machine_class": "machine_class",
        "tonnage_t": "tonnage_t",
        "process_type": "process_type",
        "robot_type": "robot_type",
        "fixture_type": "fixture_type",
        "max_shot_weight_g": "max_shot_weight_g",
        "tie_bar_x_mm": "tie_bar_x_mm",
        "tie_bar_y_mm": "tie_bar_y_mm",
        "mold_thickness_min_mm": "mold_thickness_min_mm",
        "mold_thickness_max_mm": "mold_thickness_max_mm",
        "opening_stroke_mm": "opening_stroke_mm",
        "ejector_stroke_mm": "ejector_stroke_mm",
        "status": "status",
        "available_at": "available_at",
        "quality_status": "quality_status",
    }
    for source in sources:
        machine_code = str(source.get("machine_code") or "").strip()
        if not machine_code:
            continue
        item = existing.get(machine_code)
        if item is None:
            item = InjectionMachineMaster(
                id=f"IMM-{uuid4().hex.upper()}",
                factory_id=factory_id,
                machine_code=machine_code,
                created_by=actor.id,
                created_at=timestamp,
                revision=1,
            )
            db.add(item)
            existing[machine_code] = item
        else:
            item.revision += 1
        provenance = json_object(item.provenance_json)
        manual_fields = set(provenance.get("manual_fields", []))
        for source_field, model_field in field_map.items():
            if model_field not in manual_fields:
                setattr(item, model_field, source.get(source_field))
        if "capabilities" not in manual_fields:
            item.capabilities_json = canonical_json(source.get("capabilities", []))
        if "material_rules" not in manual_fields:
            item.material_rules_json = canonical_json(source.get("material_rules", []))
        item.source_batch_id = batch_id
        item.updated_by = actor.id
        item.updated_at = timestamp
        item.provenance_json = canonical_json(
            {
                **provenance,
                "source": "excel",
                "source_batch_id": batch_id,
                "source_sheet": source.get("source_sheet", ""),
                "source_row": source.get("source_row", 0),
                "manual_fields": sorted(manual_fields),
            }
        )


def merge_mold_masters(
    db: Session,
    factory_id: str,
    batch_id: str,
    sources: list[dict[str, Any]],
    actor: AuthContext,
    timestamp: str,
) -> None:
    existing = {
        item.normalized_mold_code: item
        for item in db.scalars(
            select(InjectionMoldMaster)
            .where(InjectionMoldMaster.factory_id == factory_id)
            .order_by(InjectionMoldMaster.id)
            .with_for_update()
        ).all()
    }
    scalar_fields = (
        "mold_name",
        "machine_class",
        "robot_type",
        "fixture_type",
        "length_mm",
        "width_mm",
        "height_mm",
        "mold_weight_kg",
        "gross_shot_weight_g",
        "cavities",
        "cycle_seconds",
        "quality_status",
    )
    for source in sources:
        mold_code = str(source.get("mold_code") or "").strip()
        normalized = normalize_key(mold_code)
        if not normalized:
            continue
        item = existing.get(normalized)
        if item is None:
            item = InjectionMoldMaster(
                id=f"IMD-{uuid4().hex.upper()}",
                factory_id=factory_id,
                mold_code=mold_code,
                normalized_mold_code=normalized,
                created_by=actor.id,
                created_at=timestamp,
                revision=1,
            )
            db.add(item)
            existing[normalized] = item
        else:
            item.revision += 1
        provenance = json_object(item.provenance_json)
        manual_fields = set(provenance.get("manual_fields", []))
        for field in scalar_fields:
            if field not in manual_fields:
                setattr(item, field, source.get(field))
        if "required_capabilities" not in manual_fields:
            item.required_capabilities_json = canonical_json(
                source.get("required_capabilities", [])
            )
        if "material_rules" not in manual_fields:
            item.material_rules_json = canonical_json(source.get("material_rules", []))
        item.source_batch_id = batch_id
        item.updated_by = actor.id
        item.updated_at = timestamp
        item.provenance_json = canonical_json(
            {
                **provenance,
                "source": "excel",
                "source_batch_id": batch_id,
                "source_sheet": source.get("source_sheet", ""),
                "source_row": source.get("source_row", 0),
                "manual_fields": sorted(manual_fields),
            }
        )


def merge_order_masters(
    db: Session,
    factory_id: str,
    batch_id: str,
    sources: list[dict[str, Any]],
    actor: AuthContext,
    timestamp: str,
) -> None:
    existing = {
        item.natural_key: item
        for item in db.scalars(
            select(InjectionOrderMaster)
            .where(InjectionOrderMaster.factory_id == factory_id)
            .order_by(InjectionOrderMaster.id)
            .with_for_update()
        ).all()
    }
    scalar_fields = (
        "order_no",
        "product_code",
        "product_name",
        "mold_code",
        "color",
        "pigment",
        "material",
        "machine_class",
        "order_qty",
        "produced_qty",
        "daily_target_qty",
        "delivery_due_date",
        "priority_flag",
        "quality_status",
    )
    for source in sources:
        natural_key = str(source.get("natural_key") or "").strip()
        if not natural_key:
            continue
        item = existing.get(natural_key)
        was_canceled = item is not None and item.status == "canceled"
        if item is None:
            item = InjectionOrderMaster(
                id=f"IOM-{uuid4().hex.upper()}",
                factory_id=factory_id,
                natural_key=natural_key,
                created_by=actor.id,
                created_at=timestamp,
                revision=1,
            )
            db.add(item)
            existing[natural_key] = item
        else:
            item.revision += 1
        provenance = json_object(item.provenance_json)
        manual_fields = set(provenance.get("manual_fields", []))
        manual_fields.discard("outstanding_qty")
        for field in scalar_fields:
            if field not in manual_fields:
                setattr(item, field, source.get(field))
        item.priority_code = normalize_priority_code(item.priority_flag)
        item.outstanding_qty = max(
            float(item.order_qty or 0) - float(item.produced_qty or 0),
            0,
        )
        source_canceled = str(source.get("status") or "").strip() == "canceled"
        if was_canceled or source_canceled:
            item.status = "canceled"
        else:
            manual_fields.discard("status")
            item.status = (
                "completed"
                if item.outstanding_qty <= 1e-6
                else "open"
            )
        if "imported_assigned_machine_code" not in manual_fields:
            item.imported_assigned_machine_code = str(
                source.get("assigned_machine_code") or ""
            )
        if "imported_plan_start_at" not in manual_fields:
            item.imported_plan_start_at = str(source.get("plan_start_at") or "")
        if "imported_plan_finish_at" not in manual_fields:
            item.imported_plan_finish_at = str(source.get("plan_finish_at") or "")
        item.source_sheet = str(source.get("source_sheet") or "")
        item.source_row = int(source.get("source_row") or 0)
        item.source_batch_id = batch_id
        item.source_values_json = canonical_json(source.get("source_values", {}))
        item.updated_by = actor.id
        item.updated_at = timestamp
        item.provenance_json = canonical_json(
            {
                **provenance,
                "source": "excel",
                "source_batch_id": batch_id,
                "source_sheet": item.source_sheet,
                "source_row": item.source_row,
                "assignment_state": source.get("assignment_state", ""),
                "manual_fields": sorted(manual_fields),
            }
        )


def ensure_factory_defaults(
    db: Session,
    factory_id: str,
    actor_id: str,
    timestamp: str | None = None,
) -> tuple[InjectionScheduleFactoryState, InjectionScheduleRuleConfig]:
    now = timestamp or now_text()
    state = db.get(InjectionScheduleFactoryState, factory_id)
    if state is None:
        state = InjectionScheduleFactoryState(
            factory_id=factory_id,
            current_published_version_id=None,
            next_version_no=1,
            revision=1,
            updated_at=now,
        )
        db.add(state)
    config = db.get(InjectionScheduleRuleConfig, factory_id)
    if config is None:
        config = InjectionScheduleRuleConfig(
            factory_id=factory_id,
            config_json=canonical_json(DEFAULT_RULE_CONFIG),
            revision=1,
            updated_by=actor_id,
            updated_at=now,
        )
        db.add(config)
    db.flush()
    return state, config


def list_machine_masters(
    db: Session,
    factory_id: str,
) -> list[dict[str, Any]]:
    return [
        serialize_machine(item)
        for item in db.scalars(
            select(InjectionMachineMaster)
            .where(InjectionMachineMaster.factory_id == factory_id)
            .order_by(
                InjectionMachineMaster.workshop,
                InjectionMachineMaster.machine_code,
            )
        ).all()
    ]


def list_mold_masters(
    db: Session,
    factory_id: str,
) -> list[dict[str, Any]]:
    return [
        serialize_mold(item)
        for item in db.scalars(
            select(InjectionMoldMaster)
            .where(InjectionMoldMaster.factory_id == factory_id)
            .order_by(InjectionMoldMaster.normalized_mold_code)
        ).all()
    ]


def list_order_masters(
    db: Session,
    factory_id: str,
) -> list[dict[str, Any]]:
    return [
        serialize_order(item)
        for item in db.scalars(
            select(InjectionOrderMaster)
            .where(InjectionOrderMaster.factory_id == factory_id)
            .order_by(
                InjectionOrderMaster.status,
                InjectionOrderMaster.source_row,
                InjectionOrderMaster.id,
            )
        ).all()
    ]


def create_machine_master(
    db: Session,
    factory_id: str,
    payload: InjectionMachineCreateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    if db.scalar(
        select(InjectionMachineMaster.id).where(
            InjectionMachineMaster.factory_id == factory_id,
            InjectionMachineMaster.machine_code == payload.machine_code,
        )
    ):
        raise HTTPException(status_code=409, detail="本厂区已存在相同机号")
    timestamp = now_text()
    values = payload.model_dump()
    item = InjectionMachineMaster(
        id=f"IMM-{uuid4().hex.upper()}",
        factory_id=factory_id,
        machine_code=values.pop("machine_code"),
        capabilities_json=canonical_json(values.pop("capabilities")),
        material_rules_json=canonical_json(values.pop("material_rules")),
        provenance_json=canonical_json(
            {"source": "manual", "manual_fields": sorted(values)}
        ),
        revision=1,
        created_by=actor.id,
        created_at=timestamp,
        updated_by=actor.id,
        updated_at=timestamp,
        **values,
    )
    db.add(item)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="machine",
        entity_id=item.id,
        action="created",
        actor=actor,
        new_revision=1,
        after=serialize_machine(item),
    )
    db.commit()
    return serialize_machine(item)


def create_mold_master(
    db: Session,
    factory_id: str,
    payload: InjectionMoldCreateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    values = payload.model_dump()
    mold_code = values.pop("mold_code")
    normalized = normalize_key(mold_code)
    if db.scalar(
        select(InjectionMoldMaster.id).where(
            InjectionMoldMaster.factory_id == factory_id,
            InjectionMoldMaster.normalized_mold_code == normalized,
        )
    ):
        raise HTTPException(status_code=409, detail="本厂区已存在相同模具编号")
    timestamp = now_text()
    required = values.pop("required_capabilities")
    material_rules = values.pop("material_rules")
    item = InjectionMoldMaster(
        id=f"IMD-{uuid4().hex.upper()}",
        factory_id=factory_id,
        mold_code=mold_code,
        normalized_mold_code=normalized,
        required_capabilities_json=canonical_json(required),
        material_rules_json=canonical_json(material_rules),
        provenance_json=canonical_json(
            {"source": "manual", "manual_fields": sorted(values)}
        ),
        revision=1,
        created_by=actor.id,
        created_at=timestamp,
        updated_by=actor.id,
        updated_at=timestamp,
        **values,
    )
    db.add(item)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="mold",
        entity_id=item.id,
        action="created",
        actor=actor,
        new_revision=1,
        after=serialize_mold(item),
    )
    db.commit()
    return serialize_mold(item)


def create_order_master(
    db: Session,
    factory_id: str,
    payload: InjectionOrderCreateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    values = payload.model_dump()
    natural_key = values.pop("natural_key") or make_manual_order_key(values)
    if db.scalar(
        select(InjectionOrderMaster.id).where(
            InjectionOrderMaster.factory_id == factory_id,
            InjectionOrderMaster.natural_key == natural_key,
        )
    ):
        raise HTTPException(status_code=409, detail="本厂区已存在相同订单业务键")
    timestamp = now_text()
    order_qty = values.get("order_qty", 0)
    produced_qty = values.get("produced_qty", 0)
    priority_code = normalize_priority_code(values.get("priority_flag"))
    item = InjectionOrderMaster(
        id=f"IOM-{uuid4().hex.upper()}",
        factory_id=factory_id,
        natural_key=natural_key,
        outstanding_qty=max(order_qty - produced_qty, 0),
        imported_plan_start_at="",
        imported_plan_finish_at="",
        source_sheet="manual",
        source_row=0,
        source_batch_id="",
        source_values_json="{}",
        provenance_json=canonical_json(
            {"source": "manual", "manual_fields": sorted(values)}
        ),
        revision=1,
        created_by=actor.id,
        created_at=timestamp,
        updated_by=actor.id,
        updated_at=timestamp,
        priority_code=priority_code,
        **values,
    )
    db.add(item)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="order",
        entity_id=item.id,
        action="created",
        actor=actor,
        new_revision=1,
        after=serialize_order(item),
    )
    db.commit()
    return serialize_order(item)


def update_machine_master(
    db: Session,
    factory_id: str,
    machine_id: str,
    payload: InjectionMachineUpdateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    item = load_machine(db, factory_id, machine_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    before = serialize_machine(item)
    fields = changed_input_fields(before, fields)
    values, provenance = prepare_manual_update(
        item.provenance_json,
        fields,
        manual_field_names=set(fields),
    )
    if "capabilities" in values:
        values["capabilities_json"] = canonical_json(values.pop("capabilities"))
    if "material_rules" in values:
        values["material_rules_json"] = canonical_json(values.pop("material_rules"))
    return apply_master_update(
        db,
        item=item,
        model=InjectionMachineMaster,
        factory_id=factory_id,
        expected_revision=payload.expected_revision,
        values=values,
        provenance=provenance,
        actor=actor,
        entity_type="machine",
        serializer=serialize_machine,
        before=before,
    )


def update_mold_master(
    db: Session,
    factory_id: str,
    mold_id: str,
    payload: InjectionMoldUpdateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    item = load_mold(db, factory_id, mold_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    before = serialize_mold(item)
    fields = changed_input_fields(before, fields)
    values, provenance = prepare_manual_update(
        item.provenance_json,
        fields,
        manual_field_names=set(fields),
    )
    if "required_capabilities" in values:
        values["required_capabilities_json"] = canonical_json(
            values.pop("required_capabilities")
        )
    if "material_rules" in values:
        values["material_rules_json"] = canonical_json(values.pop("material_rules"))
    return apply_master_update(
        db,
        item=item,
        model=InjectionMoldMaster,
        factory_id=factory_id,
        expected_revision=payload.expected_revision,
        values=values,
        provenance=provenance,
        actor=actor,
        entity_type="mold",
        serializer=serialize_mold,
        before=before,
    )


def update_order_master(
    db: Session,
    factory_id: str,
    order_id: str,
    payload: InjectionOrderUpdateRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    item = load_order(db, factory_id, order_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    before = serialize_order(item)
    order_qty = fields.get("order_qty", item.order_qty)
    produced_qty = fields.get("produced_qty", item.produced_qty)
    fields = changed_input_fields(before, fields)
    manual_field_names = set(fields)
    if "priority_flag" in fields:
        fields["priority_code"] = normalize_priority_code(
            fields["priority_flag"]
        )
    outstanding_qty = max(order_qty - produced_qty, 0)
    if outstanding_qty != item.outstanding_qty:
        fields["outstanding_qty"] = outstanding_qty
    values, provenance = prepare_manual_update(
        item.provenance_json,
        fields,
        manual_field_names=manual_field_names,
    )
    return apply_master_update(
        db,
        item=item,
        model=InjectionOrderMaster,
        factory_id=factory_id,
        expected_revision=payload.expected_revision,
        values=values,
        provenance=provenance,
        actor=actor,
        entity_type="order",
        serializer=serialize_order,
        before=before,
    )


def changed_input_fields(
    before: dict[str, Any],
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        field: value
        for field, value in fields.items()
        if before.get(field) != value
    }


def prepare_manual_update(
    provenance_json: str,
    fields: dict[str, Any],
    *,
    manual_field_names: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    provenance = json_object(provenance_json)
    manual_fields = set(provenance.get("manual_fields", []))
    manual_fields.discard("outstanding_qty")
    manual_fields.update(manual_field_names - {"outstanding_qty"})
    provenance.update(
        {
            "source": provenance.get("source") or "manual",
            "manual_fields": sorted(manual_fields),
        }
    )
    return fields, provenance


def apply_master_update(
    db: Session,
    *,
    item: Any,
    model: Any,
    factory_id: str,
    expected_revision: int,
    values: dict[str, Any],
    provenance: dict[str, Any],
    actor: AuthContext,
    entity_type: str,
    serializer: Any,
    before: dict[str, Any],
) -> dict[str, Any]:
    timestamp = now_text()
    result = db.execute(
        update(model)
        .where(
            model.id == item.id,
            model.factory_id == factory_id,
            model.revision == expected_revision,
        )
        .values(
            **values,
            provenance_json=canonical_json(provenance),
            revision=model.revision + 1,
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = db.scalar(
            select(model).where(
                model.id == item.id,
                model.factory_id == factory_id,
            )
        )
        raise revision_conflict(
            item.id,
            expected_revision,
            current.revision if current is not None else None,
        )
    db.flush()
    db.expire_all()
    current = db.scalar(
        select(model).where(
            model.id == item.id,
            model.factory_id == factory_id,
        )
    )
    after = serializer(current)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type=entity_type,
        entity_id=item.id,
        action="updated",
        actor=actor,
        old_revision=expected_revision,
        new_revision=expected_revision + 1,
        before=before,
        after=after,
    )
    db.commit()
    return after


def load_machine(
    db: Session,
    factory_id: str,
    machine_id: str,
) -> InjectionMachineMaster:
    item = db.scalar(
        select(InjectionMachineMaster).where(
            InjectionMachineMaster.id == machine_id,
            InjectionMachineMaster.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的机台")
    return item


def load_mold(
    db: Session,
    factory_id: str,
    mold_id: str,
) -> InjectionMoldMaster:
    item = db.scalar(
        select(InjectionMoldMaster).where(
            InjectionMoldMaster.id == mold_id,
            InjectionMoldMaster.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的模具")
    return item


def load_order(
    db: Session,
    factory_id: str,
    order_id: str,
) -> InjectionOrderMaster:
    item = db.scalar(
        select(InjectionOrderMaster).where(
            InjectionOrderMaster.id == order_id,
            InjectionOrderMaster.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的订单")
    return item


def serialize_machine(item: InjectionMachineMaster) -> dict[str, Any]:
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "machine_code": item.machine_code,
        "machine_name": item.machine_name,
        "workshop": item.workshop,
        "machine_class": item.machine_class,
        "tonnage_t": item.tonnage_t,
        "process_type": item.process_type,
        "screw_type": item.screw_type,
        "robot_type": item.robot_type,
        "fixture_type": item.fixture_type,
        "max_shot_weight_g": item.max_shot_weight_g,
        "tie_bar_x_mm": item.tie_bar_x_mm,
        "tie_bar_y_mm": item.tie_bar_y_mm,
        "mold_thickness_min_mm": item.mold_thickness_min_mm,
        "mold_thickness_max_mm": item.mold_thickness_max_mm,
        "opening_stroke_mm": item.opening_stroke_mm,
        "ejector_stroke_mm": item.ejector_stroke_mm,
        "status": item.status,
        "available_at": item.available_at,
        "capabilities": json_list(item.capabilities_json),
        "material_rules": json_list(item.material_rules_json),
        "quality_status": item.quality_status,
        "provenance": json_object(item.provenance_json),
        "source_batch_id": item.source_batch_id,
        "revision": item.revision,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at,
    }


def serialize_mold(item: InjectionMoldMaster) -> dict[str, Any]:
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "mold_code": item.mold_code,
        "normalized_mold_code": item.normalized_mold_code,
        "mold_name": item.mold_name,
        "machine_class": item.machine_class,
        "robot_type": item.robot_type,
        "fixture_type": item.fixture_type,
        "length_mm": item.length_mm,
        "width_mm": item.width_mm,
        "height_mm": item.height_mm,
        "mold_weight_kg": item.mold_weight_kg,
        "gross_shot_weight_g": item.gross_shot_weight_g,
        "mold_thickness_mm": item.mold_thickness_mm,
        "required_opening_stroke_mm": item.required_opening_stroke_mm,
        "required_screw_type": item.required_screw_type,
        "cavities": item.cavities,
        "cycle_seconds": item.cycle_seconds,
        "required_capabilities": json_list(item.required_capabilities_json),
        "material_rules": json_list(item.material_rules_json),
        "quality_status": item.quality_status,
        "provenance": json_object(item.provenance_json),
        "source_batch_id": item.source_batch_id,
        "revision": item.revision,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at,
    }


def serialize_order(item: InjectionOrderMaster) -> dict[str, Any]:
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "natural_key": item.natural_key,
        "order_no": item.order_no,
        "product_code": item.product_code,
        "product_name": item.product_name,
        "mold_code": item.mold_code,
        "color": item.color,
        "pigment": item.pigment,
        "material": item.material,
        "machine_class": item.machine_class,
        "order_qty": item.order_qty,
        "produced_qty": item.produced_qty,
        "outstanding_qty": item.outstanding_qty,
        "daily_target_qty": item.daily_target_qty,
        "delivery_due_date": item.delivery_due_date,
        "priority_flag": item.priority_flag,
        "priority_code": item.priority_code,
        "color_rank": item.color_rank,
        "downstream_urgency": item.downstream_urgency,
        "warehouse_buffer_hours": item.warehouse_buffer_hours,
        "downstream_buffer_hours": item.downstream_buffer_hours,
        "special_handling_reason": item.special_handling_reason,
        "status": item.status,
        "imported_assigned_machine_code": item.imported_assigned_machine_code,
        "imported_plan_start_at": item.imported_plan_start_at,
        "imported_plan_finish_at": item.imported_plan_finish_at,
        "source_sheet": item.source_sheet,
        "source_row": item.source_row,
        "source_batch_id": item.source_batch_id,
        "source_values": json_object(item.source_values_json),
        "quality_status": item.quality_status,
        "provenance": json_object(item.provenance_json),
        "revision": item.revision,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at,
    }


def serialize_rule_config(item: InjectionScheduleRuleConfig) -> dict[str, Any]:
    return {
        "factory_id": item.factory_id,
        "config": normalize_rule_config(json_object(item.config_json)),
        "revision": item.revision,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at,
    }


def make_manual_order_key(values: dict[str, Any]) -> str:
    base = "|".join(
        normalize_key(values.get(field, ""))
        for field in ("order_no", "product_code", "mold_code")
    )
    if not base.replace("|", ""):
        base = uuid4().hex
    return sha256(base.encode("utf-8")).hexdigest()[:40]


def revision_conflict(
    entity_id: str,
    expected_revision: int,
    current_revision: int | None,
) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "revision_conflict",
            "message": "数据已被其他计划员修改，请刷新后重试",
            "current_revision": current_revision,
            "expected_revision": expected_revision,
            "entity_id": entity_id,
        },
    )


def add_audit_event(
    db: Session,
    *,
    factory_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: AuthContext,
    request_id: str = "",
    ip_address: str = "",
    reason: str = "",
    old_revision: int | None = None,
    new_revision: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> InjectionScheduleAuditEvent:
    event = InjectionScheduleAuditEvent(
        id=f"ISA-{uuid4().hex.upper()}",
        factory_id=factory_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor.id,
        actor_name=actor.display_name,
        request_id=request_id,
        ip_address=ip_address,
        reason=reason,
        old_revision=old_revision,
        new_revision=new_revision,
        before_json=canonical_json(before or {}),
        after_json=canonical_json(after or {}),
        created_at=now_text(),
    )
    db.add(event)
    return event
