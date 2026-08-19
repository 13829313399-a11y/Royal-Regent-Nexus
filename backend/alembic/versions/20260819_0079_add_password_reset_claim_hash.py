"""add same-browser password reset claim hash

Revision ID: 20260819_0079
Revises: 20260817_0078
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0079"
down_revision: str | Sequence[str] | None = "20260817_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("auth_password_reset_requests") as batch_op:
        batch_op.add_column(
            sa.Column("claim_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_auth_password_reset_requests_claim_token_hash",
            ["claim_token_hash"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_password_reset_requests") as batch_op:
        batch_op.drop_index("ix_auth_password_reset_requests_claim_token_hash")
        batch_op.drop_column("claim_token_hash")
