"""create persistent raw materials

Revision ID: 20260714_0013
Revises: 20260712_0012
Create Date: 2026-07-14 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0013"
down_revision: Union[str, None] = "20260712_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_materials",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("material_code", sa.String(length=128), nullable=False),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("spec", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=False),
        sa.Column("safety_stock_kg", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "material_code", name="uq_raw_materials_factory_code"),
    )
    op.create_index("ix_raw_materials_factory_id", "raw_materials", ["factory_id"])
    op.create_index("ix_raw_materials_material_code", "raw_materials", ["material_code"])
    op.create_index("ix_raw_materials_material_name", "raw_materials", ["material_name"])
    op.create_index("ix_raw_materials_status", "raw_materials", ["status"])
    op.create_index("ix_raw_materials_created_by", "raw_materials", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_raw_materials_created_by", table_name="raw_materials")
    op.drop_index("ix_raw_materials_status", table_name="raw_materials")
    op.drop_index("ix_raw_materials_material_name", table_name="raw_materials")
    op.drop_index("ix_raw_materials_material_code", table_name="raw_materials")
    op.drop_index("ix_raw_materials_factory_id", table_name="raw_materials")
    op.drop_table("raw_materials")
