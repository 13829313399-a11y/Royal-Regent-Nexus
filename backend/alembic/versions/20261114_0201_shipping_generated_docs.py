"""Auto-generated shipping documents per email task."""
from alembic import op
import sqlalchemy as sa

revision = '20261114_0201'
down_revision = '20261114_0200'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_generated_docs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('module', sa.String(32), nullable=False),
        sa.Column('filename', sa.String(300), nullable=False),
        sa.Column('header_json', sa.Text(), nullable=False),
        sa.Column('lines_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('created_by', sa.String(64), nullable=False, server_default=''),
        sa.UniqueConstraint('task_id', 'module', name='uq_shipping_generated_doc'),
    )
    op.create_index('ix_shipping_generated_docs_factory', 'shipping_generated_docs', ['factory_id'])
    op.create_index('ix_shipping_generated_docs_task', 'shipping_generated_docs', ['task_id'])
    op.create_index('ix_shipping_generated_docs_module', 'shipping_generated_docs', ['module'])


def downgrade():
    op.drop_index('ix_shipping_generated_docs_module', table_name='shipping_generated_docs')
    op.drop_index('ix_shipping_generated_docs_task', table_name='shipping_generated_docs')
    op.drop_index('ix_shipping_generated_docs_factory', table_name='shipping_generated_docs')
    op.drop_table('shipping_generated_docs')
