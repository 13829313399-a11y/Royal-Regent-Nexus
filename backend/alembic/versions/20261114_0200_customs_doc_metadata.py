"""Add port/container/SI metadata to captured customs documents."""
from alembic import op
import sqlalchemy as sa

revision = '20261114_0200'
down_revision = '20261114_0199'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shipping_customs_docs', sa.Column('port', sa.String(120), nullable=False, server_default=''))
    op.add_column('shipping_customs_docs', sa.Column('container_type', sa.String(60), nullable=False, server_default=''))
    op.add_column('shipping_customs_docs', sa.Column('si_cutoff', sa.String(40), nullable=False, server_default=''))
    op.add_column('shipping_customs_docs', sa.Column('special_note', sa.String(300), nullable=False, server_default=''))


def downgrade():
    op.drop_column('shipping_customs_docs', 'special_note')
    op.drop_column('shipping_customs_docs', 'si_cutoff')
    op.drop_column('shipping_customs_docs', 'container_type')
    op.drop_column('shipping_customs_docs', 'port')
