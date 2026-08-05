"""merge carton procurement and injection scheduling migration heads

Revision ID: 20260805_0053
Revises: 20260804_0052, 20260805_0051
Create Date: 2026-08-05
"""

from collections.abc import Sequence


revision: str = "20260805_0053"
down_revision: str | Sequence[str] | None = (
    "20260804_0052",
    "20260805_0051",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
