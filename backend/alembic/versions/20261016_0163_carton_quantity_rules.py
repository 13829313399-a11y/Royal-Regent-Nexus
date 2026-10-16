"""Preserve per-carton component rules and deliberate quantity overrides."""
from alembic import op
import sqlalchemy as sa

revision = "20261016_0163"
down_revision = "20261015_0162"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable and without a backfill: existing requirements and rules stay exact.
    op.add_column("carton_order_lines", sa.Column("quantity_rule_json", sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError("禁止丢弃纸品计算和手动数量依据，请使用向前修复")
