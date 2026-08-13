"""add Nexus-owned AI conversations

Revision ID: 20260813_0068
Revises: 20260812_0067
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0068"
down_revision: str | Sequence[str] | None = "20260812_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.String(64),
            sa.ForeignKey("auth_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("factory_scope", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(160), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_message_ordinal", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("last_message_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("expires_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("title_expires_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("deleted_at", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "tombstone_expires_at", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "last_idempotency_key", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("last_request_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "last_ephemeral_message_id",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.CheckConstraint(
            "mode IN ('PERSISTENT', 'TEMPORARY')",
            name="ck_ai_conversation_mode",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DELETION_PENDING', 'DELETED', 'EXPIRED')",
            name="ck_ai_conversation_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_ai_conversation_revision"),
        sa.CheckConstraint(
            "message_count >= 0", name="ck_ai_conversation_message_count"
        ),
        sa.CheckConstraint(
            "next_message_ordinal >= 1", name="ck_ai_conversation_next_ordinal"
        ),
    )
    for name, columns in (
        ("ix_ai_conversations_owner_user_id", ["owner_user_id"]),
        ("ix_ai_conversations_factory_scope", ["factory_scope"]),
        ("ix_ai_conversations_mode", ["mode"]),
        ("ix_ai_conversations_status", ["status"]),
        ("ix_ai_conversations_created_at", ["created_at"]),
        ("ix_ai_conversations_updated_at", ["updated_at"]),
        ("ix_ai_conversations_last_message_at", ["last_message_at"]),
        ("ix_ai_conversations_expires_at", ["expires_at"]),
        ("ix_ai_conversations_title_expires_at", ["title_expires_at"]),
        ("ix_ai_conversations_deleted_at", ["deleted_at"]),
        ("ix_ai_conversations_tombstone_expires_at", ["tombstone_expires_at"]),
        ("ix_ai_conversation_owner_updated", ["owner_user_id", "updated_at", "id"]),
        (
            "ix_ai_conversation_retention",
            ["status", "expires_at", "tombstone_expires_at"],
        ),
    ):
        op.create_index(name, "ai_conversations", columns)

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column(
            "authority",
            sa.String(32),
            nullable=False,
            server_default="CONVERSATIONAL_ONLY",
        ),
        sa.Column(
            "requires_tool_refresh", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("truncated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skill_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("skill_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("skill_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.String(128), nullable=False, server_default=""),
        sa.Column("prompt_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "provider_profile", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "provider_model_alias", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("usage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "required_access_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "idempotency_key", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("request_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_ai_message_role"),
        sa.CheckConstraint(
            "kind IN ('TEXT', 'SAFE_STAGE_SUMMARY')", name="ck_ai_message_kind"
        ),
        sa.CheckConstraint(
            "authority = 'CONVERSATIONAL_ONLY'", name="ck_ai_message_authority"
        ),
        sa.CheckConstraint("ordinal >= 1", name="ck_ai_message_ordinal"),
    )
    for name, columns in (
        ("ix_ai_messages_conversation_id", ["conversation_id"]),
        ("ix_ai_messages_role", ["role"]),
        ("ix_ai_messages_created_at", ["created_at"]),
        ("ix_ai_messages_expires_at", ["expires_at"]),
        (
            "ix_ai_message_conversation_created",
            ["conversation_id", "created_at", "id"],
        ),
    ):
        op.create_index(name, "ai_messages", columns)
    op.create_index(
        "uq_ai_message_conversation_ordinal",
        "ai_messages",
        ["conversation_id", "ordinal"],
        unique=True,
    )
    op.create_index(
        "uq_ai_message_idempotency",
        "ai_messages",
        ["conversation_id", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key != ''"),
        postgresql_where=sa.text("idempotency_key != ''"),
    )

    op.create_table(
        "ai_conversation_summaries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind", sa.String(32), nullable=False, server_default="SAFE_STAGE_SUMMARY"
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column(
            "authority",
            sa.String(32),
            nullable=False,
            server_default="CONVERSATIONAL_ONLY",
        ),
        sa.Column(
            "requires_tool_refresh", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "source_message_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("prompt_version", sa.String(128), nullable=False, server_default=""),
        sa.Column("prompt_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "required_access_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "kind = 'SAFE_STAGE_SUMMARY'", name="ck_ai_conversation_summary_kind"
        ),
        sa.CheckConstraint(
            "authority = 'CONVERSATIONAL_ONLY'",
            name="ck_ai_conversation_summary_authority",
        ),
        sa.CheckConstraint(
            "source_message_count >= 0",
            name="ck_ai_conversation_summary_message_count",
        ),
    )
    for name, columns in (
        ("ix_ai_conversation_summaries_conversation_id", ["conversation_id"]),
        ("ix_ai_conversation_summaries_created_at", ["created_at"]),
        ("ix_ai_conversation_summaries_expires_at", ["expires_at"]),
        (
            "ix_ai_conversation_summary_conversation_created",
            ["conversation_id", "created_at", "id"],
        ),
    ):
        op.create_index(name, "ai_conversation_summaries", columns)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because AI conversation data cannot be inspected."
        )
    connection = op.get_bind()
    protected = {
        table_name: int(
            connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        )
        for table_name in (
            "ai_conversations",
            "ai_messages",
            "ai_conversation_summaries",
        )
    }
    if any(protected.values()):
        counts = ", ".join(f"{key}={value}" for key, value in protected.items())
        raise RuntimeError(
            "Refusing to downgrade 20260813_0068 while protected conversation "
            f"data exists ({counts}). Disable the feature and complete retention/export review."
        )
    op.drop_table("ai_conversation_summaries")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
