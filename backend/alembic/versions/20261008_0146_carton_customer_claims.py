"""Customer claim ownership and independent source-file copies.

Local lineage follows 0141; publish after the published 0145 head.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0146"
down_revision = "20261008_0141"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("carton_customer_owners",
        sa.Column("customer_id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id", "factory_id"], ["carton_customers.id", "carton_customers.factory_id"],
            ondelete="CASCADE", name="fk_carton_owner_customer_factory"))
    # Existing multi-person assignments have no recorded first claimant. Keep
    # their scope and let supervisors explicitly designate the owner.
    op.execute(sa.text("""INSERT INTO carton_customer_owners (customer_id, factory_id, user_id)
        SELECT customer_id, factory_id, MIN(user_id) FROM carton_customer_assignments
        GROUP BY customer_id, factory_id HAVING COUNT(*) = 1"""))
    with op.batch_alter_table("carton_mark_assets") as batch:
        batch.drop_constraint("uq_carton_mark_asset_factory_sha", type_="unique")
        batch.create_index("ix_carton_mark_asset_factory_sha", ["factory_id", "sha256"])


def downgrade():
    raise RuntimeError("禁止降级：客户认领及箱唛独立副本须保留，请使用经验证的备份恢复方案")
