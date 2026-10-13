"""Publish quoted daily shots after the canonical cutting merge.

A local-only predecessor used the same 0149 identifier for the quote column.
Its original bytes are retained in ../legacy, outside Alembic's revision map.
"""
from pathlib import Path
import runpy

from alembic import op
import sqlalchemy as sa

revision = "20261009_0150"
down_revision = "20261009_0149"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("molding_sample_items")}
    cutting_tables = {"cutting_ops_masters", "cutting_ops_revisions", "cutting_ops_commands"}
    missing = cutting_tables - set(inspector.get_table_names())
    if missing:
        # Only this identified local collision may repair the skipped branch.
        # Never stamp over missing schema, infer permissions, or replace tables.
        if bind.dialect.name != "sqlite" or missing != cutting_tables or "quote_target_daily_qty" not in columns:
            raise RuntimeError("0149 cutting schema is incomplete; inspect migration history before upgrading")
        cutting = runpy.run_path(str(Path(__file__).with_name("20261007_0131_cutting_master.py")))
        cutting["upgrade"]()
    if "quote_target_daily_qty" not in columns:
        op.add_column("molding_sample_items", sa.Column("quote_target_daily_qty", sa.Integer(), nullable=True))


def downgrade():
    # Reconciled cutting tables belong to published 0149 and must be retained.
    op.drop_column("molding_sample_items", "quote_target_daily_qty")
