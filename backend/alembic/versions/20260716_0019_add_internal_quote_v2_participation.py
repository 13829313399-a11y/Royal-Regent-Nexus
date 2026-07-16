"""add internal quote v2 initiation and participation fields

Revision ID: 20260716_0019
Revises: 20260716_0018
Create Date: 2026-07-16 12:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0019"
down_revision: Union[str, None] = "20260716_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing quotations retain the original eight-section completion rule.
    op.add_column(
        "internal_quotes",
        sa.Column(
            "initiator_department",
            sa.String(length=64),
            nullable=False,
            server_default="sales",
        ),
    )
    op.create_index(
        "ix_internal_quotes_initiator_department",
        "internal_quotes",
        ["initiator_department"],
    )
    op.add_column(
        "internal_quote_sections",
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_internal_quote_sections_is_required",
        "internal_quote_sections",
        ["is_required"],
    )


def downgrade() -> None:
    op.drop_index("ix_internal_quote_sections_is_required", table_name="internal_quote_sections")
    op.drop_column("internal_quote_sections", "is_required")
    op.drop_index("ix_internal_quotes_initiator_department", table_name="internal_quotes")
    op.drop_column("internal_quotes", "initiator_department")
