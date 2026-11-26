"""Add stored 通关一体化资料 attachments captured from shipping emails."""
from alembic import op
import sqlalchemy as sa

revision = '20261114_0199'
down_revision = '20261114_0198'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_customs_docs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('mail_item_id', sa.String(64), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('read_at', sa.String(40), nullable=False),
    )
    op.create_index('ix_shipping_customs_docs_factory', 'shipping_customs_docs', ['factory_id'])
    op.create_index('ix_shipping_customs_docs_mail', 'shipping_customs_docs', ['mail_item_id'])


def downgrade():
    op.drop_index('ix_shipping_customs_docs_mail', table_name='shipping_customs_docs')
    op.drop_index('ix_shipping_customs_docs_factory', table_name='shipping_customs_docs')
    op.drop_table('shipping_customs_docs')
