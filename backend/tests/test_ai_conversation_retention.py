from __future__ import annotations

from datetime import datetime, timedelta

from app.core.config import Settings
from app.db import Base
from app.models.ai_action import AIActionConfirmation
from app.models.ai_conversation import (
    AIConversation,
    AIConversationSummary,
    AIMessage,
)
from app.models.auth import AuthAuditLog, AuthUser
from app.schemas.ai.conversation import (
    AIConversationCreate,
    AIConversationMessageCreate,
)
from app.services.ai.conversation_retention import (
    enforce_conversation_retention,
    reapply_deletion_tombstones,
)
from app.services.ai.conversation_service import (
    append_user_message,
    create_conversation,
    create_safe_summary,
    delete_conversation,
)
from app.services.auth import AuthContext, AuthGrantContext
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def _settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


def _user() -> AuthContext:
    return AuthContext(
        id="retention-owner",
        username="retention-owner",
        display_name="Retention Owner",
        roles=("retention-test",),
        role_codes=("retention-test",),
        permissions=frozenset(),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(
            AuthGrantContext(
                role_id="retention-role",
                role_name="retention-test",
                factory_id="huaxing",
                department="production",
                permissions=frozenset(),
                binding_id="retention-binding",
            ),
        ),
    )


def _database() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AuthAuditLog.__table__,
            AIActionConfirmation.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AIConversationSummary.__table__,
        ],
    )
    db = Session(engine)
    db.add(
        AuthUser(
            id="retention-owner",
            username="retention-owner",
            display_name="Retention Owner",
            password_salt="salt",
            password_hash="hash",
            status="active",
            force_password_change=0,
            avatar_png=None,
            avatar_version="",
            last_login_at="",
            created_at="2026-01-01T00:00:00+08:00",
            updated_at="2026-01-01T00:00:00+08:00",
        )
    )
    db.commit()
    return db


def _persistent(db: Session, now: datetime) -> AIConversation:
    return create_conversation(
        db,
        payload=AIConversationCreate(
            mode="PERSISTENT",
            factory_scope="huaxing",
            title="retained title",
        ),
        user=_user(),
        settings=_settings(),
        now=now,
    )


def test_retention_expires_bodies_summaries_and_titles_at_30_days() -> None:
    db = _database()
    started = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    try:
        record = _persistent(db, started)
        append_user_message(
            db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text="retention body",
                idempotency_key="retention-message-1",
            ),
            user=_user(),
            settings=_settings(),
            now=started,
        )
        create_safe_summary(
            db,
            conversation_id=record.id,
            user=_user(),
            text="controlled stage summary",
            source_message_count=1,
            prompt_version="summary-v1",
            prompt_hash="a" * 64,
            settings=_settings(),
            now=started,
        )
        report = enforce_conversation_retention(
            db,
            settings=_settings(),
            now=started + timedelta(days=30, seconds=1),
        )

        assert report.deleted_messages == 1
        assert report.deleted_summaries == 1
        assert report.cleared_titles == 1
        assert db.scalar(select(func.count(AIMessage.id))) == 0
        assert db.scalar(select(func.count(AIConversationSummary.id))) == 0
        refreshed = db.get(AIConversation, record.id)
        assert refreshed is not None
        assert refreshed.status == "ACTIVE"
        assert refreshed.title == "会话"
        assert refreshed.message_count == 0
    finally:
        db.close()


def test_temporary_metadata_expires_and_deleted_tombstone_is_purged() -> None:
    db = _database()
    started = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    config = _settings()
    try:
        temporary = create_conversation(
            db,
            payload=AIConversationCreate(mode="TEMPORARY", factory_scope="huaxing"),
            user=_user(),
            settings=config,
            now=started,
        )
        first = enforce_conversation_retention(
            db,
            settings=config,
            now=started + timedelta(days=30, seconds=1),
        )
        assert first.expired_temporary_conversations == 1
        assert db.get(AIConversation, temporary.id).status == "EXPIRED"

        second = enforce_conversation_retention(
            db,
            settings=config,
            now=started + timedelta(days=211),
        )
        assert second.deleted_tombstones == 1
        assert db.get(AIConversation, temporary.id) is None
    finally:
        db.close()


def test_user_delete_preserves_security_and_action_records() -> None:
    db = _database()
    started = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    try:
        record = _persistent(db, started)
        db.add(
            AuthAuditLog(
                user_id="retention-owner",
                username="retention-owner",
                action="permission_denied",
                detail="metadata only",
                ip_address="",
                user_agent="",
                created_at=started.isoformat(timespec="seconds"),
            )
        )
        db.add(
            AIActionConfirmation(
                id="aicf-retention-1",
                user_id="retention-owner",
                tool_name="injection_scheduling.apply_preview_run",
                risk_level="CONSEQUENTIAL_WRITE",
                factory_id="huaxing",
                entity_type="auto_schedule_run",
                entity_id="run-retention-1",
                entity_revision=1,
                args_hash="a" * 64,
                normalized_action_json="{}",
                request_id="retention-action-1",
                expires_at=(started + timedelta(minutes=5)).isoformat(timespec="seconds"),
                status="EXECUTED",
                created_at=started.isoformat(timespec="seconds"),
                confirmed_at=started.isoformat(timespec="seconds"),
                executed_at=started.isoformat(timespec="seconds"),
                execution_request_id="retention-execution-1",
                execution_result_json="{}",
                failure_code="",
            )
        )
        db.commit()

        assert delete_conversation(
            db,
            conversation_id=record.id,
            user=_user(),
            settings=_settings(),
            now=started,
        )
        assert db.scalar(select(func.count(AuthAuditLog.id))) == 1
        assert db.scalar(select(func.count(AIActionConfirmation.id))) == 1
        assert _settings().ai_conversation_security_audit_retention_days == 180
        assert _settings().ai_conversation_action_audit_retention_days == 365
    finally:
        db.close()


def test_restore_reapplies_tombstones_before_serving_body() -> None:
    db = _database()
    started = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    try:
        record = _persistent(db, started)
        record.status = "DELETED"
        record.deleted_at = started.isoformat(timespec="seconds")
        record.tombstone_expires_at = (started + timedelta(days=180)).isoformat(
            timespec="seconds"
        )
        db.add(
            AIMessage(
                id="aimsg-" + "1" * 32,
                conversation_id=record.id,
                ordinal=1,
                role="USER",
                kind="TEXT",
                body="restored body that must be removed",
                body_sha256="b" * 64,
                authority="CONVERSATIONAL_ONLY",
                requires_tool_refresh=1,
                truncated=0,
                skill_id="",
                skill_version="",
                skill_hash="",
                prompt_version="",
                prompt_hash="",
                provider_profile="",
                provider_model_alias="",
                usage_json="{}",
                evidence_json="[]",
                idempotency_key="restore-message-1",
                request_hash="c" * 64,
                created_at=started.isoformat(timespec="seconds"),
                expires_at=(started + timedelta(days=30)).isoformat(timespec="seconds"),
            )
        )
        db.commit()

        assert reapply_deletion_tombstones(db) == 1
        db.commit()
        assert db.scalar(select(func.count(AIMessage.id))) == 0
    finally:
        db.close()


def test_conversation_security_audit_has_independent_180_day_retention() -> None:
    db = _database()
    started = datetime.fromisoformat("2026-01-01T08:00:00+08:00")
    try:
        db.add_all(
            [
                AuthAuditLog(
                    user_id="retention-owner",
                    username="retention-owner",
                    action="ai_conversation_access_denied",
                    detail="operation=detail",
                    ip_address="",
                    user_agent="",
                    created_at="2026-01-01 08:00:00",
                ),
                AuthAuditLog(
                    user_id="retention-owner",
                    username="retention-owner",
                    action="login_denied",
                    detail="owned by auth policy",
                    ip_address="",
                    user_agent="",
                    created_at="2026-01-01 08:00:00",
                ),
            ]
        )
        db.commit()

        report = enforce_conversation_retention(
            db,
            settings=_settings(),
            now=started + timedelta(days=181),
        )

        assert report.deleted_security_audits == 1
        assert db.scalar(select(func.count(AuthAuditLog.id))) == 1
        assert db.scalar(select(AuthAuditLog.action)) == "login_denied"
    finally:
        db.close()
