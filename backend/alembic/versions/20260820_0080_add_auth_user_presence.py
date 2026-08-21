"""add low-frequency authenticated user presence

Revision ID: 20260820_0080
Revises: 20260819_0079
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0080"
down_revision: str | Sequence[str] | None = "20260819_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_user_presence",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "last_seen_at", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.Column(
            "created_at", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.Column(
            "updated_at", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_auth_user_presence_last_seen_at",
        "auth_user_presence",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_auth_user_presence_last_seen_at", table_name="auth_user_presence")
    op.drop_table("auth_user_presence")
