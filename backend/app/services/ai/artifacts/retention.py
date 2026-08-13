from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_artifact import AIArtifact
from app.models.auth import AuthAuditLog
from app.services.ai.artifacts.contracts import ArtifactStatus
from app.services.ai.artifacts.storage import ArtifactStorage, ArtifactStorageError

retention_logger = logging.getLogger("app.ai.artifacts.retention")
RETENTION_INTERVAL_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class ArtifactRetentionReport:
    expired: int = 0
    deleted_online: int = 0
    pending_online: int = 0
    deleted_security_audits: int = 0


def _text(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def enforce_artifact_retention(
    db: Session,
    *,
    storage: ArtifactStorage,
    settings: Settings,
    now: datetime | None = None,
) -> ArtifactRetentionReport:
    current = now or business_now()
    current_text = _text(current)
    expired_records = tuple(
        db.scalars(
            select(AIArtifact).where(
                AIArtifact.status == ArtifactStatus.ACTIVE.value,
                AIArtifact.retention_until <= current_text,
            )
        ).all()
    )
    for record in expired_records:
        record.status = ArtifactStatus.EXPIRED.value
        record.deleted_at = current_text
        record.tombstone_expires_at = _text(
            current + timedelta(days=settings.ai_artifact_tombstone_retention_days)
        )
        record.backup_delete_by = _text(
            current + timedelta(days=settings.ai_artifact_backup_delete_sla_days)
        )
        record.updated_at = current_text
    db.commit()

    cleanup_records = tuple(
        db.scalars(
            select(AIArtifact).where(
                AIArtifact.status.in_(
                    (
                        ArtifactStatus.DELETION_PENDING.value,
                        ArtifactStatus.EXPIRED.value,
                    )
                ),
                AIArtifact.storage_deleted_at == "",
            )
        ).all()
    )
    deleted_online = 0
    pending_online = 0
    for record in cleanup_records:
        try:
            storage.delete(record.storage_key)
        except ArtifactStorageError:
            pending_online += 1
            retention_logger.error(
                "artifact_retention_delete_pending artifact_id=%s size=%s type=%s hash_prefix=%s status=%s",
                record.id,
                record.size_bytes,
                record.detected_mime_type,
                record.sha256[:12],
                record.status,
            )
            continue
        record.storage_deleted_at = current_text
        if record.status == ArtifactStatus.DELETION_PENDING.value:
            record.status = ArtifactStatus.DELETED.value
        record.updated_at = current_text
        deleted_online += 1

    audit_cutoff = (
        current - timedelta(days=settings.ai_artifact_security_audit_retention_days)
    ).strftime("%Y-%m-%d %H:%M:%S")
    audit_result = db.execute(
        delete(AuthAuditLog).where(
            AuthAuditLog.action.like("ai_artifact_%"),
            AuthAuditLog.created_at < audit_cutoff,
        )
    )
    db.commit()
    return ArtifactRetentionReport(
        expired=len(expired_records),
        deleted_online=deleted_online,
        pending_online=pending_online,
        deleted_security_audits=max(audit_result.rowcount or 0, 0),
    )


async def artifact_retention_loop(
    session_factory,
    *,
    storage: ArtifactStorage,
    settings: Settings,
) -> None:
    while True:
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)
        db = session_factory()
        try:
            report = enforce_artifact_retention(
                db, storage=storage, settings=settings
            )
            retention_logger.info(
                "ai_artifact_retention expired=%s deleted_online=%s pending_online=%s security_audits=%s",
                report.expired,
                report.deleted_online,
                report.pending_online,
                report.deleted_security_audits,
            )
        except Exception:
            db.rollback()
            retention_logger.exception("ai_artifact_retention_failed")
        finally:
            db.close()
