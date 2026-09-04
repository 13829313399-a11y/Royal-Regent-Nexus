"""Administrator-only projections of migration evidence; never return raw JSON."""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.three_d_printing import (
    ThreeDPrintingMigrationBatch,
    ThreeDPrintingMigrationRowResult,
)
from app.services.auth import AuthContext, authorization_decision, time_window_is_active
from app.services.three_d_printing import THREE_D_DEPARTMENTS, require_three_d_factory

BATCH_STATUSES = {
    "analyzed",
    "dry_run",
    "importing",
    "imported",
    "reconciled",
    "failed",
    "rolled_back",
}
ROW_STATUSES = {
    "pending",
    "imported",
    "updated",
    "skipped",
    "failed",
    "conflict",
    "reconciled",
}
DOMAINS = {
    "settings",
    "materials",
    "products",
    "printers",
    "records",
    "production_records",
    "inventory",
    "stock_in_logs",
    "schedules",
    "maintenance",
    "images",
    "product_images",
    "days",
    "material_aliases",
}
COUNT_FIELDS = DOMAINS | {
    "business_date_keys",
    "active_records",
    "soft_deleted_records",
    "inventory_items",
    "configured_printers",
    "image_total_bytes",
    "inventory_total_g",
    "records_stored",
    "records_active",
    "records_tombstoned",
    "record_dates",
    "stock_in_total_g",
    "stock_in_total_cost",
}
TOTAL_FIELDS = {
    "quantity_total",
    "planned_material_g_total",
    "design_fee_total",
    "quoted_revenue_total",
}
ERROR_CODES = {
    "invalid_text_field",
    "text_field_too_long",
    "invalid_numeric_field",
    "negative_numeric_field",
    "invalid_integer_field",
    "numeric_precision_exceeds_schema",
    "invalid_timestamp",
    "invalid_business_date",
    "missing_legacy_id",
    "duplicate_legacy_id",
    "dependency_unavailable",
    "invalid_boolean_field",
    "unknown_machine_number",
    "invalid_source_image",
    "unsafe_asset_path",
    "source_image_hash_mismatch",
    "asset_content_conflict",
    "asset_write_failed",
    "inventory_movement_already_exists",
    "ambiguous_target_identity",
    "owned_target_missing",
    "target_edited_in_nexus",
    "target_has_no_migration_ownership",
    "immutable_history_changed",
    "stale_source_row",
    "target_constraint_violation",
    "row_not_imported",
    "reconciliation_target_missing",
    "reconciliation_target_mismatch",
    "reconciliation_asset_mismatch",
    "reconciliation_business_field_mismatch",
    "reconciliation_run_status_mismatch",
    "reconciliation_provenance_mismatch",
    "reconciliation_inventory_mismatch",
    "reconciliation_inventory_ledger_mismatch",
    "reconciliation_history_mismatch",
    "reconciliation_counts_mismatch",
    "reconciliation_totals_mismatch",
    "source_missing_previously_imported_row",
    "invalid_machine_count",
    "migration_site_not_ready",
    "migration_schema_not_ready",
    "migration_lease_active",
    "migration_batch_source_mismatch",
    "stale_source_snapshot",
    "source_timestamp_conflict",
    "migration_batch_not_found",
    "migration_resume_required",
    "migration_version_mismatch",
    "migration_lease_lost",
    "invalid_migration_options",
    "asset_source_overlap",
    "standalone_snapshot_required",
    "migration_scope_mismatch",
    "invalid_code_revision",
    "snapshot_manifest_mismatch",
    "snapshot_timestamp_mismatch",
    "migration_reconciliation_failed",
    "migration_execution_failed",
}


def require_migration_administrator(user: AuthContext, factory_id: str) -> str:
    # Role membership alone is insufficient: expired bindings and explicit denies
    # remain authoritative even if global read-only navigation is enabled.
    is_admin = any(
        grant.role_code == "admin"
        and grant.factory_id in {"*", "huakang-a"}
        and grant.department in {"*", "system", *THREE_D_DEPARTMENTS}
        and time_window_is_active(grant.valid_from, grant.valid_until)
        for grant in user.grants
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="仅系统管理员可查看3D迁移记录")
    factory_id = require_three_d_factory(factory_id)
    if not authorization_decision(
        user, "three_d_printing:audit_read", factory_id, THREE_D_DEPARTMENTS[0]
    )[0]:
        raise HTTPException(status_code=403, detail="无权查看3D迁移记录")
    return factory_id


def _object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _identifier(value: str) -> str:
    # Migration ids are opaque labels, not a channel for URLs, paths or tokens.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        return ""
    return "" if re.search(r"gh[pousr]_|github_pat_", value, re.IGNORECASE) else value


def _hash(value: str) -> str:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value)
        else ""
    )


def _opaque_id(value: str) -> str:
    if not value:
        return ""
    return "legacy-" + sha256(str(value).encode("utf-8")).hexdigest()[:24]


def _revision(value: str) -> str:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{40,64}", value)
        else ""
    )


def _error_code(value: Any) -> str:
    if not value:
        return ""
    return value if isinstance(value, str) and value in ERROR_CODES else "unknown"


def _time(value: str) -> str:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[0-9TtZz:+. -]{10,40}", value)
        else ""
    )


def _numbers(value: Any, keys: set[str]) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in keys and type(item) in {int, float} and math.isfinite(item)
    }


def _counts(raw: str) -> dict[str, int | float]:
    return _numbers(_object(raw), COUNT_FIELDS)


def _summary(raw: str) -> dict[str, Any]:
    value = _object(raw)
    return {
        "counts": _numbers(value.get("counts"), COUNT_FIELDS),
        "row_status_counts": _numbers(value.get("row_status_counts"), ROW_STATUSES),
        "error_codes": sorted(
            {_error_code(code) for code in value.get("error_codes", [])}
        )
        if isinstance(value.get("error_codes"), list)
        else [],
    }


def _batch_out(batch: ThreeDPrintingMigrationBatch) -> dict[str, Any]:
    return {
        "id": _identifier(batch.id),
        "factory_id": "huakang-a",
        "site_id": _identifier(batch.site_id),
        "source_system": _identifier(batch.source_system),
        "source_sha256": _hash(batch.source_sha256),
        "source_updated_at_ms": batch.source_updated_at_ms,
        "source_size_bytes": batch.source_size_bytes,
        "image_count": batch.image_count,
        "image_bytes": batch.image_bytes,
        "migration_version": _identifier(batch.migration_version),
        "code_revision": _revision(batch.code_revision),
        "status": batch.status if batch.status in BATCH_STATUSES else "unknown",
        "expected_counts": _counts(batch.expected_counts_json),
        "summary": _summary(batch.summary_json),
        "started_at": _time(batch.started_at),
        "completed_at": _time(batch.completed_at),
        "has_error": bool(batch.error_code),
        "error_code": _error_code(batch.error_code),
    }


def _batch(db: Session, factory_id: str, batch_id: str) -> ThreeDPrintingMigrationBatch:
    value = db.scalar(
        select(ThreeDPrintingMigrationBatch).where(
            ThreeDPrintingMigrationBatch.factory_id == factory_id,
            ThreeDPrintingMigrationBatch.id == batch_id,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="迁移批次不存在")
    return value


def list_migration_batches(
    db: Session, *, factory_id: str, page: int, page_size: int
) -> dict[str, Any]:
    where = ThreeDPrintingMigrationBatch.factory_id == factory_id
    total = (
        db.scalar(
            select(func.count()).select_from(ThreeDPrintingMigrationBatch).where(where)
        )
        or 0
    )
    batches = db.scalars(
        select(ThreeDPrintingMigrationBatch)
        .where(where)
        .order_by(
            ThreeDPrintingMigrationBatch.started_at.desc(),
            ThreeDPrintingMigrationBatch.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [_batch_out(batch) for batch in batches],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_migration_batch(
    db: Session, *, factory_id: str, batch_id: str
) -> dict[str, Any]:
    return _batch_out(_batch(db, factory_id, batch_id))


def list_migration_rows(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
    status: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    _batch(db, factory_id, batch_id)
    if status and status not in ROW_STATUSES:
        raise HTTPException(status_code=422, detail="迁移行状态无效")
    where = [
        ThreeDPrintingMigrationRowResult.factory_id == factory_id,
        ThreeDPrintingMigrationRowResult.batch_id == batch_id,
    ]
    if status:
        where.append(ThreeDPrintingMigrationRowResult.status == status)
    total = (
        db.scalar(
            select(func.count())
            .select_from(ThreeDPrintingMigrationRowResult)
            .where(*where)
        )
        or 0
    )
    rows = db.scalars(
        select(ThreeDPrintingMigrationRowResult)
        .where(*where)
        .order_by(
            ThreeDPrintingMigrationRowResult.entity_type,
            ThreeDPrintingMigrationRowResult.legacy_id,
            ThreeDPrintingMigrationRowResult.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "id": _identifier(row.id),
            "entity_type": row.entity_type if row.entity_type in DOMAINS else "unknown",
            "legacy_id": _identifier(row.legacy_id),
            "target_id": _identifier(row.target_id),
            "source_hash": _hash(row.source_hash),
            "target_hash": _hash(row.target_hash),
            "status": row.status if row.status in ROW_STATUSES else "unknown",
            "has_error": bool(row.error_code),
            "error_code": _error_code(row.error_code),
            "legacy_key": _opaque_id(row.legacy_id),
            "attempt_count": row.attempt_count,
            "updated_at": _time(row.updated_at),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_migration_reconciliation(
    db: Session, *, factory_id: str, batch_id: str
) -> dict[str, Any]:
    batch = _batch(db, factory_id, batch_id)
    raw = _object(batch.reconciliation_json)
    totals = raw.get("business_totals")
    if not isinstance(totals, dict):
        totals = {}
    issues = raw.get("issues")
    safe_issues = [
        {
            "code": _error_code(issue.get("code")),
            "entity_type": issue.get("entity_type")
            if isinstance(issue.get("entity_type"), str)
            and issue.get("entity_type") in DOMAINS
            else "unknown",
            "legacy_key": _opaque_id(issue.get("legacy_id", "")),
        }
        for issue in (issues[:200] if isinstance(issues, list) else [])
        if isinstance(issue, dict)
    ]
    return {
        "batch_id": _identifier(batch.id),
        "status": batch.status if batch.status in BATCH_STATUSES else "unknown",
        "passed": raw.get("passed") if type(raw.get("passed")) is bool else None,
        "expected_counts": _numbers(raw.get("expected"), COUNT_FIELDS),
        "actual_counts": _numbers(raw.get("actual"), COUNT_FIELDS),
        "issue_count": len(issues) if isinstance(issues, list) else 0,
        "issues": safe_issues,
        "issues_truncated": isinstance(issues, list) and len(issues) > 200,
        "business_totals": {
            key: _numbers(totals.get(key), TOTAL_FIELDS)
            for key in ("expected", "actual")
        },
    }
