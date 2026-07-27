"""Merge injection scheduling Phase 4 with internal quote freight baseline.

Revision ID: 20260727_0036
Revises: 20260725_0035, 20260723_0030
Create Date: 2026-07-27
"""

from collections.abc import Sequence


revision: str = "20260727_0036"
down_revision: str | Sequence[str] | None = (
    "20260725_0035",
    "20260723_0030",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
