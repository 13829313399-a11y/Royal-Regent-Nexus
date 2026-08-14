"""add AI conversation management metadata

Revision ID: 20260814_0077
Revises: 20260814_0076
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0077"
down_revision: str | Sequence[str] | None = "20260814_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pinned_at", sa.String(length=32), nullable=False, server_default=""
            )
        )
        batch_op.add_column(
            sa.Column(
                "archived_at", sa.String(length=32), nullable=False, server_default=""
            )
        )
        batch_op.create_index(
            "ix_ai_conversation_owner_archived_updated",
            ["owner_user_id", "archived_at", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_conversations") as batch_op:
        batch_op.drop_index("ix_ai_conversation_owner_archived_updated")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("pinned_at")
