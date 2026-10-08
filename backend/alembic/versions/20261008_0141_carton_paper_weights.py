"""Record packaging weights on individual carton paper lines.

Legacy order/header values remain intact: their allocation to papers is unknown.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0141"
down_revision = "20261008_0140"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("carton_order_lines", sa.Column("net_weight_kg", sa.Numeric(12, 4),
        sa.CheckConstraint("net_weight_kg IS NULL OR net_weight_kg >= 0", name="ck_carton_line_net_weight"), nullable=True))
    op.add_column("carton_order_lines", sa.Column("gross_weight_kg", sa.Numeric(12, 4),
        sa.CheckConstraint("gross_weight_kg IS NULL OR (gross_weight_kg >= 0 AND (net_weight_kg IS NULL OR gross_weight_kg >= net_weight_kg))", name="ck_carton_line_gross_weight"), nullable=True))


def downgrade():
    raise RuntimeError("禁止降级：纸品重量快照须保留，请使用经验证的备份恢复方案")
