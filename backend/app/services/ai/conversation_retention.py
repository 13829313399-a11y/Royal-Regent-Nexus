from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_conversation import (
    AIConversation,
    AIConversationSummary,
    AIMessage,
)
from app.models.auth import AuthAuditLog
from app.services.ai.task_service import enforce_task_retention

retention_logger = logging.getLogger("app.ai.conversation.retention")
RETENTION_INTERVAL_SECONDS = 60 * 60


@dataclass(frozen=True, slots=True)
class ConversationRetentionReport:
    deleted_messages: int = 0
    deleted_summaries: int = 0
    expired_temporary_conversations: int = 0
    cleared_titles: int = 0
    deleted_tombstones: int = 0
    reapplied_tombstones: int = 0
    deleted_security_audits: int = 0


def _now_text(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def _tombstone_expiry(settings: Settings, now: datetime) -> str:
    return (now + timedelta(days=settings.ai_conversation_tombstone_retention_days)).isoformat(
        timespec="seconds"
    )


def reapply_deletion_tombstones(db: Session) -> int:
    """Delete restored body rows before a restored database can serve traffic."""

    tombstone_ids = tuple(
        db.scalars(
            select(AIConversation.id).where(
                AIConversation.status.in_(("DELETED", "EXPIRED"))
            )
        ).all()
    )
    if not tombstone_ids:
        return 0
    message_result = db.execute(
        delete(AIMessage).where(AIMessage.conversation_id.in_(tombstone_ids))
    )
    summary_result = db.execute(
        delete(AIConversationSummary).where(
            AIConversationSummary.conversation_id.in_(tombstone_ids)
        )
    )
    return max(message_result.rowcount or 0, 0) + max(summary_result.rowcount or 0, 0)


def enforce_conversation_retention(
    db: Session,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> ConversationRetentionReport:
    current = now or business_now()
    current_text = _now_text(current)
    security_audit_cutoff = (
        current - timedelta(days=settings.ai_conversation_security_audit_retention_days)
    ).strftime("%Y-%m-%d %H:%M:%S")

    message_result = db.execute(
        delete(AIMessage).where(AIMessage.expires_at <= current_text)
    )
    summary_result = db.execute(
        delete(AIConversationSummary).where(
            AIConversationSummary.expires_at <= current_text
        )
    )

    active_ids = tuple(
        db.scalars(
            select(AIConversation.id).where(AIConversation.status == "ACTIVE")
        ).all()
    )
    for conversation_id in active_ids:
        count = db.scalar(
            select(func.count(AIMessage.id)).where(
                AIMessage.conversation_id == conversation_id
            )
        )
        db.execute(
            update(AIConversation)
            .where(AIConversation.id == conversation_id)
            .values(message_count=int(count or 0))
        )

    title_result = db.execute(
        update(AIConversation)
        .where(
            AIConversation.status == "ACTIVE",
            AIConversation.mode == "PERSISTENT",
            AIConversation.title_expires_at != "",
            AIConversation.title_expires_at <= current_text,
        )
        .values(title="会话", title_expires_at="")
    )

    temporary_ids = tuple(
        db.scalars(
            select(AIConversation.id).where(
                AIConversation.status == "ACTIVE",
                AIConversation.mode == "TEMPORARY",
                AIConversation.expires_at != "",
                AIConversation.expires_at <= current_text,
            )
        ).all()
    )
    if temporary_ids:
        db.execute(delete(AIMessage).where(AIMessage.conversation_id.in_(temporary_ids)))
        db.execute(
            delete(AIConversationSummary).where(
                AIConversationSummary.conversation_id.in_(temporary_ids)
            )
        )
        db.execute(
            update(AIConversation)
            .where(AIConversation.id.in_(temporary_ids))
            .values(
                status="EXPIRED",
                title="",
                message_count=0,
                deleted_at=current_text,
                updated_at=current_text,
                last_message_at="",
                tombstone_expires_at=_tombstone_expiry(settings, current),
                last_idempotency_key="",
                last_request_hash="",
                last_ephemeral_message_id="",
            )
        )

    reapplied = reapply_deletion_tombstones(db)
    security_audit_result = db.execute(
        delete(AuthAuditLog).where(
            AuthAuditLog.action == "ai_conversation_access_denied",
            AuthAuditLog.created_at <= security_audit_cutoff,
        )
    )
    tombstone_result = db.execute(
        delete(AIConversation).where(
            AIConversation.status.in_(("DELETED", "EXPIRED")),
            AIConversation.tombstone_expires_at != "",
            AIConversation.tombstone_expires_at <= current_text,
        )
    )
    db.commit()
    return ConversationRetentionReport(
        deleted_messages=max(message_result.rowcount or 0, 0),
        deleted_summaries=max(summary_result.rowcount or 0, 0),
        expired_temporary_conversations=len(temporary_ids),
        cleared_titles=max(title_result.rowcount or 0, 0),
        deleted_tombstones=max(tombstone_result.rowcount or 0, 0),
        reapplied_tombstones=reapplied,
        deleted_security_audits=max(security_audit_result.rowcount or 0, 0),
    )


async def conversation_retention_loop(
    session_factory,
    *,
    settings: Settings,
    interval_seconds: float = RETENTION_INTERVAL_SECONDS,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("retention interval must be positive")
    while True:
        await asyncio.sleep(interval_seconds)
        db = session_factory()
        try:
            report = enforce_conversation_retention(db, settings=settings)
            retention_logger.info(
                "ai_conversation_retention messages=%s summaries=%s "
                "temporary=%s titles=%s tombstones=%s restored_rows=%s security_audits=%s",
                report.deleted_messages,
                report.deleted_summaries,
                report.expired_temporary_conversations,
                report.cleared_titles,
                report.deleted_tombstones,
                report.reapplied_tombstones,
                report.deleted_security_audits,
            )
            deleted_tasks, deleted_task_audits = enforce_task_retention(
                db,
                settings=settings,
            )
            retention_logger.info(
                "ai_task_retention tasks=%s security_audits=%s",
                deleted_tasks,
                deleted_task_audits,
            )
        except Exception:
            db.rollback()
            retention_logger.exception("ai_conversation_retention_failed")
        finally:
            db.close()
