"""merge password-reset and carton-customer migration heads

Revision ID: 20260820_0081
Revises: 20260819_0079, 20260819_0080
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260820_0081"
down_revision: str | Sequence[str] | None = (
    "20260819_0079",
    "20260819_0080",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
