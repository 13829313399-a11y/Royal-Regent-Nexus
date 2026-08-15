from __future__ import annotations

from app.core.config import Settings
from app.db import Base
from app.models.ai_conversation import AIConversation, AIConversationContextBinding
from app.models.auth import AuthUser
from app.schemas.ai.context import AIPageContextInput
from app.schemas.ai.conversation import (
    AIConversationContextUpdate,
    AIConversationCreate,
    AIConversationUpdate,
)
from app.services.ai.conversation_service import (
    ConversationValidationError,
    bound_page_context,
    create_conversation,
    update_conversation,
    update_conversation_context,
)
from app.services.auth import AuthContext, AuthGrantContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        ai_enabled=True,
        ai_conversations_enabled=True,
        ai_conversation_context_enabled=True,
        ai_semantic_gateway_enabled=False,
    )


def _user(*, permission: bool = True) -> AuthContext:
    permissions = (
        frozenset({"injection_scheduling:read"}) if permission else frozenset()
    )
    return AuthContext(
        id="context-owner",
        username="context-owner",
        display_name="Context Owner",
        roles=("排产",),
        role_codes=("planner",),
        permissions=permissions,
        factory_scopes=("huaxing", "huakang-a"),
        department_scopes=("production",),
        grants=(
            AuthGrantContext(
                role_id="role-context",
                role_name="排产",
                factory_id="huaxing",
                department="production",
                permissions=permissions,
                binding_id="binding-context",
            ),
        ),
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
            AIConversation.__table__,
            AIConversationContextBinding.__table__,
        ],
    )
    db = Session(engine)
    db.add(
        AuthUser(
            id="context-owner",
            username="context-owner",
            display_name="Context Owner",
            password_salt="salt",
            password_hash="hash",
            status="active",
            force_password_change=0,
            avatar_png=None,
            avatar_version="",
            last_login_at="",
            created_at="2026-08-14T08:00:00+08:00",
            updated_at="2026-08-14T08:00:00+08:00",
        )
    )
    db.commit()
    return db


def _scheduling_context(factory_id: str = "huaxing") -> AIPageContextInput:
    return AIPageContextInput(
        route_name="injection-scheduling-v2",
        path="/modules/production/injection-scheduling",
        factory_id=factory_id,
        module_id="injection-scheduling",
        selected_entity=None,
    )


def test_context_binding_is_reauthorized_and_cannot_cross_factory() -> None:
    db = _database()
    try:
        owner = _user()
        conversation = create_conversation(
            db,
            payload=AIConversationCreate(factory_scope="huaxing", title="排产连续会话"),
            user=owner,
            settings=_settings(),
        )
        binding = update_conversation_context(
            db,
            conversation_id=conversation.id,
            payload=AIConversationContextUpdate(
                page_context=_scheduling_context(),
                expected_revision=1,
            ),
            user=owner,
            settings=_settings(),
        )
        assert binding is not None
        assert binding.module_id == "injection-scheduling"
        assert (
            bound_page_context(db, conversation_id=conversation.id)
            == _scheduling_context()
        )

        try:
            update_conversation_context(
                db,
                conversation_id=conversation.id,
                payload=AIConversationContextUpdate(
                    page_context=_scheduling_context("huakang-a"),
                    expected_revision=2,
                ),
                user=owner,
                settings=_settings(),
            )
        except ConversationValidationError as exc:
            assert "跨厂区" in exc.public_message
        else:
            raise AssertionError("cross-factory context must fail closed")

        try:
            update_conversation_context(
                db,
                conversation_id=conversation.id,
                payload=AIConversationContextUpdate(
                    page_context=_scheduling_context(),
                    expected_revision=2,
                ),
                user=_user(permission=False),
                settings=_settings(),
            )
        except ConversationValidationError as exc:
            assert "权限" in exc.public_message
        else:
            raise AssertionError("revoked permission must invalidate context")
    finally:
        db.close()


def test_conversation_management_is_ai_only_revisioned_metadata() -> None:
    db = _database()
    try:
        owner = _user()
        conversation = create_conversation(
            db,
            payload=AIConversationCreate(factory_scope="huaxing", title="原标题"),
            user=owner,
            settings=_settings(),
        )
        pinned = update_conversation(
            db,
            conversation_id=conversation.id,
            payload=AIConversationUpdate(
                title="排产例会",
                pinned=True,
                expected_revision=1,
            ),
            user=owner,
        )
        assert pinned.title == "排产例会"
        assert pinned.pinned_at is not None
        assert pinned.revision == 2

        archived = update_conversation(
            db,
            conversation_id=conversation.id,
            payload=AIConversationUpdate(archived=True, expected_revision=2),
            user=owner,
        )
        assert archived.archived_at is not None
        assert archived.pinned_at is None
        assert archived.revision == 3
    finally:
        db.close()
