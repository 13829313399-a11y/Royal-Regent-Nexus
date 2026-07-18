"""add internal quote pricing baseline

Revision ID: 20260718_0026
Revises: 20260718_0025
Create Date: 2026-07-18 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260718_0026"
down_revision: Union[str, None] = "20260718_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_quote_pricing_baselines",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("workshop_code", sa.String(length=64), nullable=False),
        sa.Column("workshop_name", sa.String(length=128), nullable=False),
        sa.Column("material_prices_json", sa.Text(), nullable=False),
        sa.Column("machine_prices_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by_name", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "workshop_code",
            name="uq_internal_quote_pricing_baselines_factory_workshop",
        ),
    )
    op.create_index(
        op.f("ix_internal_quote_pricing_baselines_factory_id"),
        "internal_quote_pricing_baselines",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_quote_pricing_baselines_workshop_code"),
        "internal_quote_pricing_baselines",
        ["workshop_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_quote_pricing_baselines_created_by"),
        "internal_quote_pricing_baselines",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_quote_pricing_baselines_updated_by"),
        "internal_quote_pricing_baselines",
        ["updated_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_internal_quote_pricing_baselines_updated_by"),
        table_name="internal_quote_pricing_baselines",
    )
    op.drop_index(
        op.f("ix_internal_quote_pricing_baselines_created_by"),
        table_name="internal_quote_pricing_baselines",
    )
    op.drop_index(
        op.f("ix_internal_quote_pricing_baselines_workshop_code"),
        table_name="internal_quote_pricing_baselines",
    )
    op.drop_index(
        op.f("ix_internal_quote_pricing_baselines_factory_id"),
        table_name="internal_quote_pricing_baselines",
    )
    op.drop_table("internal_quote_pricing_baselines")
