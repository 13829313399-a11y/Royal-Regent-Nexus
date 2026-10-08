"""Add carton weights, customer responsibility and explicit shared source bindings.

Primary development lineage; published release must follow its verified carton
photo-group head rather than replaying the unpublished fabric migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0140"
down_revision = "20261007_0138"
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable columns without rebuilding orders or touching immutable evidence.
    op.add_column("carton_orders", sa.Column("net_weight_kg", sa.Numeric(12, 4),
        sa.CheckConstraint("net_weight_kg IS NULL OR net_weight_kg >= 0", name="ck_carton_net_weight"), nullable=True))
    op.add_column("carton_orders", sa.Column("gross_weight_kg", sa.Numeric(12, 4),
        sa.CheckConstraint("gross_weight_kg IS NULL OR (gross_weight_kg >= 0 AND (net_weight_kg IS NULL OR gross_weight_kg >= net_weight_kg))", name="ck_carton_gross_weight"), nullable=True))
    op.create_table("carton_customer_assignments",
        sa.Column("customer_id", sa.String(96), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["customer_id", "factory_id"], ["carton_customers.id", "carton_customers.factory_id"],
                                ondelete="CASCADE", name="fk_carton_assignment_customer_factory"))
    op.create_index("ix_carton_assignment_factory_user", "carton_customer_assignments", ["factory_id", "user_id"])
    op.create_index("uq_carton_mark_asset_id_factory", "carton_mark_assets", ["id", "factory_id"], unique=True)
    op.create_table("carton_mark_asset_order_bindings",
        sa.Column("asset_id", sa.String(96), primary_key=True),
        sa.Column("order_id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["asset_id", "factory_id"], ["carton_mark_assets.id", "carton_mark_assets.factory_id"],
                                ondelete="CASCADE", name="fk_carton_mark_binding_asset_factory"),
        sa.ForeignKeyConstraint(["order_id", "factory_id"], ["carton_orders.id", "carton_orders.factory_id"],
                                ondelete="CASCADE", name="fk_carton_mark_binding_order_factory"))
    op.create_index("ix_carton_mark_binding_factory_order", "carton_mark_asset_order_bindings", ["factory_id", "order_id"])


def downgrade():
    raise RuntimeError("禁止降级：客户责任、重量快照及多合同关联须保留；请使用经验证的备份恢复方案")
