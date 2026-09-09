"""Preserve explicit paper demand and unknown product/packing quantities."""
import sqlalchemy as sa
from alembic import op

revision = "20260909_0106"
down_revision = "20260909_0105"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite" and connection.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("SQLite 表重建须在迁移专用 foreign_keys=OFF 连接执行，防止级联删除业务记录；迁移后须验证 foreign_key_check")
    # Existing demand remains CALCULATED. Nullable means unknown, never zero.
    with op.batch_alter_table("carton_orders") as batch:
        batch.add_column(sa.Column("quantity_basis", sa.String(16), nullable=False, server_default="CALCULATED"))
        batch.alter_column("product_order_quantity", existing_type=sa.Numeric(18, 6), nullable=True)
        batch.drop_constraint("ck_carton_order_product_quantity", type_="check")
        batch.create_check_constraint("ck_carton_order_product_quantity", "(quantity_basis = 'CALCULATED' AND product_order_quantity IS NOT NULL AND product_order_quantity > 0) OR (quantity_basis = 'EXPLICIT' AND (product_order_quantity IS NULL OR product_order_quantity > 0))")
    with op.batch_alter_table("carton_order_lines") as batch:
        batch.alter_column("usage_quantity", existing_type=sa.Numeric(18, 8), nullable=True)
        batch.drop_constraint("ck_carton_order_line_required", type_="check")
        batch.create_check_constraint("ck_carton_order_line_required", "required_quantity >= 0")
    with op.batch_alter_table("carton_purchase_order_issues") as batch:
        for column in ("before_product_quantity", "after_product_quantity", "product_quantity_delta"):
            batch.alter_column(column, existing_type=sa.Numeric(18, 6), nullable=True)


def downgrade():
    raise RuntimeError("显式需求及未知数量不能无损还原为计算量；请使用已验证备份恢复")
