"""Persistent overrides for pallet stats summary groups and synced rows."""
from alembic import op
import sqlalchemy as sa

revision = '20261124_0203'
down_revision = '20261124_0202'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_pallet_overrides',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('source_kind', sa.String(32), nullable=False),
        sa.Column('source_id', sa.String(64), nullable=False),
        sa.Column('target_factory_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('ship_date', sa.String(10), nullable=False, server_default=''),
        sa.Column('customer', sa.String(120), nullable=False, server_default=''),
        sa.Column('container_no', sa.String(120), nullable=False, server_default=''),
        sa.Column('container_type', sa.String(40), nullable=False, server_default=''),
        sa.Column('so_no', sa.String(80), nullable=False, server_default=''),
        sa.Column('contract_no', sa.String(120), nullable=False, server_default=''),
        sa.Column('filing_codes', sa.String(300), nullable=False, server_default=''),
        sa.Column('spec', sa.String(120), nullable=False, server_default=''),
        sa.Column('cartons', sa.Float(), nullable=True),
        sa.Column('pallets', sa.Float(), nullable=True),
        sa.Column('unit_price', sa.Float(), nullable=True),
        sa.Column('estimated_cost_override', sa.Float(), nullable=True),
        sa.Column('container_count_override', sa.Integer(), nullable=True),
        sa.Column('is_container', sa.Integer(), nullable=True),
        sa.Column('remark', sa.String(300), nullable=False, server_default=''),
        sa.Column('updated_by', sa.String(64), nullable=False, server_default=''),
        sa.Column('updated_at', sa.String(40), nullable=False, server_default=''),
        sa.UniqueConstraint('factory_id', 'source_kind', 'source_id', name='uq_shipping_pallet_override'),
    )
    op.create_index('ix_shipping_pallet_overrides_factory_id', 'shipping_pallet_overrides', ['factory_id'])
    op.create_index('ix_shipping_pallet_overrides_source_id', 'shipping_pallet_overrides', ['source_id'])
    op.create_index('ix_shipping_pallet_overrides_target_factory_id', 'shipping_pallet_overrides', ['target_factory_id'])


def downgrade():
    op.drop_index('ix_shipping_pallet_overrides_target_factory_id', table_name='shipping_pallet_overrides')
    op.drop_index('ix_shipping_pallet_overrides_source_id', table_name='shipping_pallet_overrides')
    op.drop_index('ix_shipping_pallet_overrides_factory_id', table_name='shipping_pallet_overrides')
    op.drop_table('shipping_pallet_overrides')
