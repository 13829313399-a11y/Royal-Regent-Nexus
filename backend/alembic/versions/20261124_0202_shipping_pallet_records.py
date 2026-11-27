"""Manual pallet records and synced pallet stats exclusions."""
from alembic import op
import sqlalchemy as sa

revision = '20261124_0202'
down_revision = '20261123_shipping_merge'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_pallet_records',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('ship_date', sa.String(10), nullable=False),
        sa.Column('customer', sa.String(120), nullable=False),
        sa.Column('container_no', sa.String(120), nullable=False, server_default=''),
        sa.Column('container_type', sa.String(40), nullable=False, server_default='40HQ'),
        sa.Column('so_no', sa.String(80), nullable=False, server_default=''),
        sa.Column('contract_no', sa.String(120), nullable=False, server_default=''),
        sa.Column('filing_codes', sa.String(300), nullable=False, server_default=''),
        sa.Column('spec', sa.String(120), nullable=False, server_default='标准木卡板 (1200×1000)'),
        sa.Column('cartons', sa.Float(), nullable=False, server_default='0'),
        sa.Column('pallets', sa.Float(), nullable=False, server_default='0'),
        sa.Column('unit_price', sa.Float(), nullable=False, server_default='65'),
        sa.Column('is_container', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('remark', sa.String(300), nullable=False, server_default=''),
        sa.Column('created_by', sa.String(64), nullable=False, server_default=''),
        sa.Column('created_at', sa.String(40), nullable=False, server_default=''),
        sa.Column('updated_at', sa.String(40), nullable=False, server_default=''),
    )
    op.create_index('ix_shipping_pallet_records_factory_id', 'shipping_pallet_records', ['factory_id'])
    op.create_index('ix_shipping_pallet_records_ship_date', 'shipping_pallet_records', ['ship_date'])
    op.create_index('ix_shipping_pallet_records_customer', 'shipping_pallet_records', ['customer'])

    op.create_table(
        'shipping_pallet_exclusions',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('source_kind', sa.String(32), nullable=False),
        sa.Column('source_id', sa.String(64), nullable=False),
        sa.Column('excluded_by', sa.String(64), nullable=False, server_default=''),
        sa.Column('excluded_at', sa.String(40), nullable=False, server_default=''),
        sa.UniqueConstraint('factory_id', 'source_kind', 'source_id', name='uq_shipping_pallet_exclusion'),
    )
    op.create_index('ix_shipping_pallet_exclusions_factory_id', 'shipping_pallet_exclusions', ['factory_id'])
    op.create_index('ix_shipping_pallet_exclusions_source_id', 'shipping_pallet_exclusions', ['source_id'])


def downgrade():
    op.drop_index('ix_shipping_pallet_exclusions_source_id', table_name='shipping_pallet_exclusions')
    op.drop_index('ix_shipping_pallet_exclusions_factory_id', table_name='shipping_pallet_exclusions')
    op.drop_table('shipping_pallet_exclusions')

    op.drop_index('ix_shipping_pallet_records_customer', table_name='shipping_pallet_records')
    op.drop_index('ix_shipping_pallet_records_ship_date', table_name='shipping_pallet_records')
    op.drop_index('ix_shipping_pallet_records_factory_id', table_name='shipping_pallet_records')
    op.drop_table('shipping_pallet_records')
