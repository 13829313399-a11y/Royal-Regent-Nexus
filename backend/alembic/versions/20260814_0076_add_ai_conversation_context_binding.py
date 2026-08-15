"""add reauthorized AI conversation context bindings

Revision ID: 20260814_0076
Revises: 20260813_0075
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0076"
down_revision: str | Sequence[str] | None = "20260813_0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_context_bindings",
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("factory_scope", sa.String(length=64), nullable=False),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("route_name", sa.String(length=96), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "selected_entity_type",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "selected_entity_id",
            sa.String(length=96),
            nullable=False,
            server_default="",
        ),
        sa.Column("selected_entity_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "context_version >= 1",
            name="ck_ai_conversation_context_version",
        ),
        sa.CheckConstraint(
            "selected_entity_revision IS NULL OR selected_entity_revision >= 1",
            name="ck_ai_conversation_context_entity_revision",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ai_conversations.id"],
            name="fk_ai_conversation_context_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_ai_conversation_context_factory_module",
        "ai_conversation_context_bindings",
        ["factory_scope", "module_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_conversation_context_factory_module",
        table_name="ai_conversation_context_bindings",
    )
    op.drop_table("ai_conversation_context_bindings")
