"""Add optional customer PO without changing existing order identity or quantities."""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0108"
down_revision = "20260909_0107"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("carton_orders", sa.Column("customer_po", sa.String(128), nullable=False, server_default=""))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM carton_orders WHERE customer_po <> ''")).scalar():
        raise RuntimeError("客户 PO 已用于订单，请保留证据，不能直接降级删除")
    op.drop_column("carton_orders", "customer_po")
