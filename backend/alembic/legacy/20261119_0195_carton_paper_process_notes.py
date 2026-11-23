"""Keep each order paper's production instructions with the original order."""
from alembic import op
import sqlalchemy as sa

revision = "20261119_0195"
down_revision = "20261110_0194"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("carton_order_lines", sa.Column("process_note", sa.Text(), nullable=False, server_default=""))


def downgrade():
    raise RuntimeError("禁止降级：纸品工艺备注属于订单历史，请使用经验证的备份恢复方案")
