"""Add generated container loading sheets with daily W numbering."""
from alembic import op
import sqlalchemy as sa

revision = '20261114_0197'
down_revision = '20261113_0196'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_loading_sheets',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('number', sa.String(16), nullable=False),
        sa.Column('sheet_date', sa.String(10), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('header_json', sa.Text(), nullable=False),
        sa.Column('lines_json', sa.Text(), nullable=False),
        sa.Column('totals_json', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(64), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
    )
    op.create_index('ix_shipping_loading_sheets_factory', 'shipping_loading_sheets', ['factory_id'])
    op.create_index('ix_shipping_loading_sheets_date', 'shipping_loading_sheets', ['sheet_date'])


def downgrade():
    op.drop_index('ix_shipping_loading_sheets_date', table_name='shipping_loading_sheets')
    op.drop_index('ix_shipping_loading_sheets_factory', table_name='shipping_loading_sheets')
    op.drop_table('shipping_loading_sheets')
