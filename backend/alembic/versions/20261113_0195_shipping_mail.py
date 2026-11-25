"""Add shipping mail batches/items and shipping tasks for the P2 import flow."""
from alembic import op
import sqlalchemy as sa

revision = '20261113_0195'
down_revision = '20261110_0194'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('shipping_mail_batches',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('source', sa.String(24), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False),
        sa.Column('parsed_count', sa.Integer(), nullable=False),
        sa.Column('failed_count', sa.Integer(), nullable=False),
        sa.Column('parser_version', sa.String(40), nullable=False),
        sa.Column('created_by', sa.String(64), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_shipping_mail_batches_factory', 'shipping_mail_batches', ['factory_id'])

    op.create_table('shipping_mail_items',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('batch_id', sa.String(64), nullable=False),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('sender', sa.String(500), nullable=False),
        sa.Column('received_at', sa.String(80), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('items_json', sa.Text(), nullable=False),
        sa.Column('warnings_json', sa.Text(), nullable=False),
        sa.Column('trace_json', sa.Text(), nullable=False),
        sa.Column('task_ids_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False))
    op.create_index('ix_shipping_mail_items_batch', 'shipping_mail_items', ['batch_id'])
    op.create_index('ix_shipping_mail_items_factory', 'shipping_mail_items', ['factory_id'])
    op.create_index('ix_shipping_mail_items_fingerprint', 'shipping_mail_items', ['fingerprint'])

    op.create_table('shipping_tasks',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('mail_item_id', sa.String(64), nullable=True),
        sa.Column('source_group_key', sa.String(64), nullable=False),
        sa.Column('source', sa.String(24), nullable=False),
        sa.Column('so_number', sa.String(64), nullable=False),
        sa.Column('customer', sa.String(200), nullable=False),
        sa.Column('container_type', sa.String(64), nullable=False),
        sa.Column('port', sa.String(64), nullable=False),
        sa.Column('destination_country', sa.String(64), nullable=False),
        sa.Column('shipment_mode', sa.String(24), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('planned_ship_date', sa.String(10), nullable=False),
        sa.Column('si_deadline', sa.String(20), nullable=False),
        sa.Column('cutoff_date', sa.String(20), nullable=False),
        sa.Column('items_json', sa.Text(), nullable=False),
        sa.Column('warnings_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('mail_item_id', 'source_group_key', name='uq_shipping_task_source'))
    op.create_index('ix_shipping_tasks_factory', 'shipping_tasks', ['factory_id'])
    op.create_index('ix_shipping_tasks_mail_item', 'shipping_tasks', ['mail_item_id'])
    op.create_index('ix_shipping_tasks_so_number', 'shipping_tasks', ['so_number'])
    op.create_index('ix_shipping_tasks_status', 'shipping_tasks', ['status'])


def downgrade():
    for table in ('shipping_tasks', 'shipping_mail_items', 'shipping_mail_batches'):
        if op.get_bind().execute(sa.text(f'SELECT count(*) FROM {table}')).scalar():
            raise RuntimeError('船务邮件/任务表已有数据，请保留历史记录，不允许删除。')
    op.drop_table('shipping_tasks')
    op.drop_table('shipping_mail_items')
    op.drop_table('shipping_mail_batches')
