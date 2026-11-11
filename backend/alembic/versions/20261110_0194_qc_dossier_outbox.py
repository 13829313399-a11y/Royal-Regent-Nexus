"""Add recoverable QC source delivery; no existing order/approval rewrites."""
from alembic import op
import sqlalchemy as sa

revision = '20261110_0194'
down_revision = '20261107_0193'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('qc_dossier_outbox',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory', sa.String(64), nullable=False),
        sa.Column('source_id', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('delivered_at', sa.String(40), nullable=False, server_default=''),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=False, server_default=''))
    op.create_index('ix_qc_dossier_pending', 'qc_dossier_outbox', ['delivered_at', 'created_at', 'id'])
    op.create_index('ix_qc_dossier_outbox_factory', 'qc_dossier_outbox', ['factory'])
    op.create_index('ix_qc_dossier_outbox_source_id', 'qc_dossier_outbox', ['source_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM qc_dossier_outbox')).scalar():
        raise RuntimeError('资料事件已有数据，请关闭采集开关并保留事件表，不允许删除历史证据。')
    op.drop_table('qc_dossier_outbox')
