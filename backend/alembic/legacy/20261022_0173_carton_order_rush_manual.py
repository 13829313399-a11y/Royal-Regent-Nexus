"""Add manual planned-date and rush-order flags to carton orders."""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0173'
down_revision = '20261021_0172'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('carton_orders', sa.Column('plan_date_manual', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('carton_orders', sa.Column('rush', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('carton_orders', sa.Column('rush_reason', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('carton_orders', sa.Column('rush_at', sa.String(length=40), nullable=True))
    op.add_column('carton_orders', sa.Column('rush_by', sa.String(length=64), nullable=True))
    op.add_column('carton_orders', sa.Column('rush_ack_at', sa.String(length=40), nullable=True))
    op.add_column('carton_orders', sa.Column('rush_ack_by', sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column('carton_orders', 'rush_ack_by')
    op.drop_column('carton_orders', 'rush_ack_at')
    op.drop_column('carton_orders', 'rush_by')
    op.drop_column('carton_orders', 'rush_at')
    op.drop_column('carton_orders', 'rush_reason')
    op.drop_column('carton_orders', 'rush')
    op.drop_column('carton_orders', 'plan_date_manual')
