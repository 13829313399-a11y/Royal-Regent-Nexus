"""Add imported per-customer product history (类别 / 每箱毛重 / 每箱净重)."""
from alembic import op
import sqlalchemy as sa

revision = '20261114_0198'
down_revision = '20261114_0197'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_product_history',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('customer', sa.String(64), nullable=False),
        sa.Column('product_code', sa.String(120), nullable=False),
        sa.Column('product_name', sa.String(300), nullable=False),
        sa.Column('category', sa.String(120), nullable=False),
        sa.Column('gross_per_carton', sa.String(32), nullable=False),
        sa.Column('net_per_carton', sa.String(32), nullable=False),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('factory_id', 'customer', 'product_code', name='uq_shipping_product_history'),
    )
    op.create_index('ix_shipping_product_history_factory', 'shipping_product_history', ['factory_id'])
    op.create_index('ix_shipping_product_history_customer', 'shipping_product_history', ['customer'])


def downgrade():
    op.drop_index('ix_shipping_product_history_customer', table_name='shipping_product_history')
    op.drop_index('ix_shipping_product_history_factory', table_name='shipping_product_history')
    op.drop_table('shipping_product_history')
