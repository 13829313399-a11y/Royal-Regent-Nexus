from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('PERSISTENT', 'TEMPORARY')",
            name="ck_ai_conversation_mode",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DELETION_PENDING', 'DELETED', 'EXPIRED')",
            name="ck_ai_conversation_status",
        ),
        CheckConstraint("revision >= 1", name="ck_ai_conversation_revision"),
        CheckConstraint("message_count >= 0", name="ck_ai_conversation_message_count"),
        CheckConstraint(
            "next_message_ordinal >= 1",
            name="ck_ai_conversation_next_ordinal",
        ),
        Index(
            "ix_ai_conversation_owner_updated",
            "owner_user_id",
            "updated_at",
            "id",
        ),
        Index(
            "ix_ai_conversation_retention",
            "status",
            "expires_at",
            "tombstone_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    factory_scope: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    next_message_ordinal: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[str] = mapped_column(String(32), index=True)
    last_message_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    expires_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    title_expires_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    deleted_at: Mapped[str] = mapped_column(String(32), default="", index=True)
    tombstone_expires_at: Mapped[str] = mapped_column(
        String(32), default="", index=True
    )
    last_idempotency_key: Mapped[str] = mapped_column(String(128), default="")
    last_request_hash: Mapped[str] = mapped_column(String(64), default="")
    last_ephemeral_message_id: Mapped[str] = mapped_column(String(64), default="")
    pinned_at: Mapped[str] = mapped_column(String(32), default="")
    archived_at: Mapped[str] = mapped_column(String(32), default="")


class AIConversationContextBinding(Base):
    __tablename__ = "ai_conversation_context_bindings"
    __table_args__ = (
        CheckConstraint(
            "context_version >= 1",
            name="ck_ai_conversation_context_version",
        ),
        CheckConstraint(
            "selected_entity_revision IS NULL OR selected_entity_revision >= 1",
            name="ck_ai_conversation_context_entity_revision",
        ),
        Index(
            "ix_ai_conversation_context_factory_module",
            "factory_scope",
            "module_id",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), primary_key=True
    )
    factory_scope: Mapped[str] = mapped_column(String(64))
    module_id: Mapped[str] = mapped_column(String(64))
    route_name: Mapped[str] = mapped_column(String(96))
    path: Mapped[str] = mapped_column(String(255))
    context_version: Mapped[int] = mapped_column(Integer, default=1)
    selected_entity_type: Mapped[str] = mapped_column(String(64), default="")
    selected_entity_id: Mapped[str] = mapped_column(String(96), default="")
    selected_entity_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class AIMessage(Base):
    __tablename__ = "ai_messages"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_ai_message_role"),
        CheckConstraint(
            "kind IN ('TEXT', 'SAFE_STAGE_SUMMARY')",
            name="ck_ai_message_kind",
        ),
        CheckConstraint(
            "authority = 'CONVERSATIONAL_ONLY'",
            name="ck_ai_message_authority",
        ),
        CheckConstraint("ordinal >= 1", name="ck_ai_message_ordinal"),
        Index(
            "uq_ai_message_conversation_ordinal",
            "conversation_id",
            "ordinal",
            unique=True,
        ),
        Index(
            "uq_ai_message_idempotency",
            "conversation_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key != ''"),
            postgresql_where=text("idempotency_key != ''"),
        ),
        Index(
            "ix_ai_message_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    body_sha256: Mapped[str] = mapped_column(String(64))
    authority: Mapped[str] = mapped_column(String(32), default="CONVERSATIONAL_ONLY")
    requires_tool_refresh: Mapped[int] = mapped_column(Integer, default=1)
    truncated: Mapped[int] = mapped_column(Integer, default=0)
    skill_id: Mapped[str] = mapped_column(String(128), default="")
    skill_version: Mapped[str] = mapped_column(String(64), default="")
    skill_hash: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(128), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    provider_profile: Mapped[str] = mapped_column(String(128), default="")
    provider_model_alias: Mapped[str] = mapped_column(String(128), default="")
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    required_access_json: Mapped[str] = mapped_column(Text, default="[]")
    idempotency_key: Mapped[str] = mapped_column(String(128), default="")
    request_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[str] = mapped_column(String(32), index=True)


class AIConversationSummary(Base):
    __tablename__ = "ai_conversation_summaries"
    __table_args__ = (
        CheckConstraint(
            "kind = 'SAFE_STAGE_SUMMARY'",
            name="ck_ai_conversation_summary_kind",
        ),
        CheckConstraint(
            "authority = 'CONVERSATIONAL_ONLY'",
            name="ck_ai_conversation_summary_authority",
        ),
        CheckConstraint(
            "source_message_count >= 0",
            name="ck_ai_conversation_summary_message_count",
        ),
        Index(
            "ix_ai_conversation_summary_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="SAFE_STAGE_SUMMARY")
    body: Mapped[str] = mapped_column(Text)
    body_sha256: Mapped[str] = mapped_column(String(64))
    authority: Mapped[str] = mapped_column(String(32), default="CONVERSATIONAL_ONLY")
    requires_tool_refresh: Mapped[int] = mapped_column(Integer, default=1)
    source_message_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(128), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    required_access_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
