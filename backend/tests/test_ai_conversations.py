from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from app.core.config import Settings, settings
from app.db import Base, get_db
from app.main import app
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
from app.services.ai.conversation_service import (
    AssistantMessageMetadata,
    ConversationConflictError,
    ConversationNotFoundError,
    ConversationValidationError,
    append_assistant_message,
    append_user_message,
    assemble_conversation_history,
    create_conversation,
    create_safe_summary,
    delete_conversation,
    get_conversation_detail,
    get_owned_conversation,
    list_conversations,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
    get_current_user,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        ai_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="owner,other",
        ai_pilot_factory_ids="huaxing",
        ai_provider="fake",
        ai_conversations_enabled=True,
    )


def _user(user_id: str = "owner", *, factories: tuple[str, ...] = ("huaxing",)) -> AuthContext:
    grants = tuple(
        AuthGrantContext(
            role_id=f"role-{user_id}-{factory}",
            role_name="AI 会话测试",
            factory_id=factory,
            department="production",
            permissions=frozenset(),
            binding_id=f"binding-{user_id}-{factory}",
        )
        for factory in factories
    )
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name=user_id,
        roles=("AI 会话测试",),
        role_codes=("ai-conversation-test",),
        permissions=frozenset(),
        factory_scopes=factories,
        department_scopes=("production",),
        grants=grants,
    )


def _database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AuthAuditLog.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AIConversationSummary.__table__,
        ],
    )
    db = Session(engine)
    for user_id in ("owner", "other"):
        db.add(
            AuthUser(
                id=user_id,
                username=user_id,
                display_name=user_id,
                password_salt="salt",
                password_hash="hash",
                status="active",
                force_password_change=0,
                avatar_png=None,
                avatar_version="",
                last_login_at="",
                created_at="2026-08-12T08:00:00+08:00",
                updated_at="2026-08-12T08:00:00+08:00",
            )
        )
    db.commit()
    return db


def test_persistent_conversation_is_owner_only_and_recovers_from_database() -> None:
    db = _database()
    config = _settings()
    owner = _user()
    try:
        conversation = create_conversation(
            db,
            payload=AIConversationCreate(
                mode="PERSISTENT",
                factory_scope="huaxing",
                title="排产讨论",
            ),
            user=owner,
            settings=config,
        )
        message = append_user_message(
            db,
            conversation_id=conversation.id,
            payload=AIConversationMessageCreate(
                text="请解释当前排产状态",
                idempotency_key="web-message-owner-1",
                expected_revision=1,
            ),
            user=owner,
            settings=config,
        )
        replay = append_user_message(
            db,
            conversation_id=conversation.id,
            payload=AIConversationMessageCreate(
                text="请解释当前排产状态",
                idempotency_key="web-message-owner-1",
                expected_revision=1,
            ),
            user=owner,
            settings=config,
        )
        append_assistant_message(
            db,
            conversation_id=conversation.id,
            user=owner,
            text="历史回答只作背景；当前状态需要重新查询工具。",
            idempotency_key="response-owner-1-assistant",
            settings=config,
            metadata=AssistantMessageMetadata(
                skill_id="injection_scheduling.read_context",
                skill_version="1.0.0",
                prompt_hash="a" * 64,
                provider_profile="business-balanced-v1",
                provider_model_alias="qwen3.7-plus",
                usage={"total_tokens": 12},
            ),
        )

        assert replay.id == message.id
        conversation_id = conversation.id
        assert list_conversations(db, user=owner).items[0].id == conversation_id
        engine = db.get_bind()
        db.close()
        db = Session(engine)
        detail = get_conversation_detail(
            db,
            conversation_id=conversation_id,
            user=owner,
        )
        assert [item.role for item in detail.messages] == ["USER", "ASSISTANT"]
        assert all(item.requires_tool_refresh for item in detail.messages)
        assert detail.messages[1].provider_model_alias == "qwen3.7-plus"

        with pytest.raises(ConversationNotFoundError):
            get_owned_conversation(
                db,
                conversation_id=conversation_id,
                user=_user("other"),
            )
    finally:
        db.close()


def test_cross_user_and_lost_factory_are_indistinguishable_from_unknown() -> None:
    db = _database()
    try:
        record = create_conversation(
            db,
            payload=AIConversationCreate(factory_scope="huaxing"),
            user=_user(),
            settings=_settings(),
        )
        for user in (_user("other"), _user("owner", factories=())):
            with pytest.raises(ConversationNotFoundError) as exc_info:
                get_owned_conversation(
                    db,
                    conversation_id=record.id,
                    user=user,
                )
            assert exc_info.value.code == "AI_CONVERSATION_NOT_FOUND"
        with pytest.raises(ConversationNotFoundError):
            get_owned_conversation(
                db,
                conversation_id="aicv-" + "0" * 32,
                user=_user(),
            )
    finally:
        db.close()


def test_temporary_conversation_persists_no_body_or_summary() -> None:
    db = _database()
    config = _settings()
    owner = _user()
    try:
        record = create_conversation(
            db,
            payload=AIConversationCreate(
                mode="TEMPORARY",
                factory_scope="huaxing",
                title="不得落库的标题",
            ),
            user=owner,
            settings=config,
        )
        user_message = append_user_message(
            db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text="password: temporary-only-value",
                idempotency_key="temporary-message-1",
            ),
            user=owner,
            settings=config,
        )
        replay = append_user_message(
            db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text="password: temporary-only-value",
                idempotency_key="temporary-message-1",
            ),
            user=owner,
            settings=config,
        )
        assistant = append_assistant_message(
            db,
            conversation_id=record.id,
            user=owner,
            text="temporary reply",
            idempotency_key="temporary-assistant-1",
            settings=config,
        )

        assert record.title == "临时会话"
        assert user_message.persisted is False
        assert replay.id == user_message.id
        assert assistant.persisted is False
        assert db.scalar(select(func.count(AIMessage.id))) == 0
        assert db.scalar(select(func.count(AIConversationSummary.id))) == 0
        detail = get_conversation_detail(
            db,
            conversation_id=record.id,
            user=owner,
        )
        assert detail.messages == []
        assert assemble_conversation_history(
            db,
            conversation_id=record.id,
            user=owner,
            settings=config,
        ).messages == ()
        with pytest.raises(ConversationConflictError):
            create_safe_summary(
                db,
                conversation_id=record.id,
                user=owner,
                text="summary",
                source_message_count=0,
                prompt_version="summary-v1",
                prompt_hash="a" * 64,
                settings=config,
            )
    finally:
        db.close()


def test_delete_hard_deletes_body_keeps_tombstone_and_secret_is_rejected() -> None:
    db = _database()
    config = _settings()
    owner = _user()
    try:
        record = create_conversation(
            db,
            payload=AIConversationCreate(factory_scope="huaxing"),
            user=owner,
            settings=config,
        )
        with pytest.raises(ConversationValidationError):
            append_user_message(
                db,
                conversation_id=record.id,
                payload=AIConversationMessageCreate(
                    text="api_key=abcdefghijklmnop",
                    idempotency_key="secret-message-1",
                ),
                user=owner,
                settings=config,
            )
        append_user_message(
            db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text="ordinary text",
                idempotency_key="ordinary-message-1",
            ),
            user=owner,
            settings=config,
        )
        create_safe_summary(
            db,
            conversation_id=record.id,
            user=owner,
            text="这是阶段摘要，不是正式业务事实。",
            source_message_count=1,
            prompt_version="summary-v1",
            prompt_hash="b" * 64,
            settings=config,
        )
        assert delete_conversation(
            db,
            conversation_id=record.id,
            user=owner,
            settings=config,
            now=datetime.fromisoformat("2026-08-12T12:00:00+08:00"),
        )
        tombstone = db.get(AIConversation, record.id)
        assert tombstone is not None
        assert tombstone.status == "DELETED"
        assert tombstone.title == ""
        assert tombstone.tombstone_expires_at.startswith("2027-02-08")
        assert db.scalar(select(func.count(AIMessage.id))) == 0
        assert db.scalar(select(func.count(AIConversationSummary.id))) == 0
        with pytest.raises(ConversationNotFoundError):
            get_owned_conversation(db, conversation_id=record.id, user=owner)
    finally:
        db.close()


def test_explicit_deny_hides_previously_authorized_assistant_body_and_summary() -> None:
    db = _database()
    config = _settings()
    base_user = _user()
    permission = "injection_scheduling:view"
    allowed_user = replace(
        base_user,
        permissions=frozenset({permission}),
        grants=(replace(base_user.grants[0], permissions=frozenset({permission})),),
        active_permission_codes=frozenset({permission}),
    )
    denied_user = replace(
        allowed_user,
        overrides=(
            AuthOverrideContext(
                id="deny-conversation-history",
                permission_code=permission,
                effect="deny",
                factory_id="huaxing",
                department="production",
            ),
        ),
    )
    try:
        record = create_conversation(
            db,
            payload=AIConversationCreate(factory_scope="huaxing"),
            user=allowed_user,
            settings=config,
        )
        append_user_message(
            db,
            conversation_id=record.id,
            payload=AIConversationMessageCreate(
                text="请查询排产事实",
                idempotency_key="explicit-deny-user-1",
            ),
            user=allowed_user,
            settings=config,
        )
        append_assistant_message(
            db,
            conversation_id=record.id,
            user=allowed_user,
            text="这是先前授权时生成的业务回答。",
            idempotency_key="explicit-deny-assistant-1",
            settings=config,
            metadata=AssistantMessageMetadata(
                required_access=((permission, ("production",)),),
            ),
        )
        create_safe_summary(
            db,
            conversation_id=record.id,
            user=allowed_user,
            text="先前阶段摘要。",
            source_message_count=2,
            prompt_version="summary-v1",
            prompt_hash="d" * 64,
            settings=config,
        )

        allowed_detail = get_conversation_detail(
            db,
            conversation_id=record.id,
            user=allowed_user,
        )
        denied_detail = get_conversation_detail(
            db,
            conversation_id=record.id,
            user=denied_user,
        )
        denied_history = assemble_conversation_history(
            db,
            conversation_id=record.id,
            user=denied_user,
            settings=config,
        )

        assert [item.role for item in allowed_detail.messages] == ["USER", "ASSISTANT"]
        assert allowed_detail.summary is not None
        assert [item.role for item in denied_detail.messages] == ["USER"]
        assert denied_detail.summary is None
        assert [item.role for item in denied_history.messages] == ["user"]
        assert denied_history.summary == ""
    finally:
        db.close()


def test_conversation_api_is_default_off_then_owner_only(monkeypatch) -> None:
    db = _database()
    user_holder = {"value": _user()}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user_holder["value"]
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_pilot_enabled", True)
    monkeypatch.setattr(settings, "ai_pilot_user_ids", "owner,other")
    monkeypatch.setattr(settings, "ai_pilot_factory_ids", "huaxing")
    monkeypatch.setattr(settings, "ai_runtime_disable_path", "")
    monkeypatch.setattr(settings, "app_env", "development")
    try:
        client = TestClient(app)
        monkeypatch.setattr(settings, "ai_conversations_enabled", False)
        assert client.get("/api/ai/conversations").status_code == 404

        monkeypatch.setattr(settings, "ai_conversations_enabled", True)
        created = client.post(
            "/api/ai/conversations",
            json={
                "mode": "PERSISTENT",
                "factory_scope": "huaxing",
                "title": "API 会话",
            },
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        appended = client.post(
            f"/api/ai/conversations/{conversation_id}/messages",
            json={"text": "API message", "idempotency_key": "api-message-1"},
        )
        assert appended.status_code == 201, appended.text

        user_holder["value"] = _user("other")
        assert client.get(f"/api/ai/conversations/{conversation_id}").status_code == 404
        assert client.delete(f"/api/ai/conversations/{conversation_id}").status_code == 204

        user_holder["value"] = _user()
        assert client.get(f"/api/ai/conversations/{conversation_id}").status_code == 200
        assert client.delete(f"/api/ai/conversations/{conversation_id}").status_code == 204
        assert client.get(f"/api/ai/conversations/{conversation_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_conversation_api_configures_the_shared_guard_backend() -> None:
    from app.api import ai_conversations

    assert ai_conversations.conversation_pilot_guard._shared_backend is not None
