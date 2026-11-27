"""Add per-factory IMAP mail accounts and sync runs for the weekly collector."""
from alembic import op
import sqlalchemy as sa

revision = '20261113_0196'
down_revision = '20261113_0195'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_mail_accounts',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('password_enc', sa.Text(), nullable=False),
        sa.Column('use_ssl', sa.Boolean(), nullable=False),
        sa.Column('folder', sa.String(120), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('last_uid', sa.String(32), nullable=False),
        sa.Column('last_sync_at', sa.String(40), nullable=False),
        sa.Column('last_status', sa.String(24), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
    )
    op.create_index('ix_shipping_mail_accounts_factory', 'shipping_mail_accounts', ['factory_id'], unique=True)

    op.create_table(
        'shipping_mail_sync_runs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('factory_id', sa.String(64), nullable=False),
        sa.Column('trigger', sa.String(24), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('fetched', sa.Integer(), nullable=False),
        sa.Column('imported', sa.Integer(), nullable=False),
        sa.Column('confirmed', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('started_at', sa.String(40), nullable=False),
        sa.Column('finished_at', sa.String(40), nullable=False),
    )
    op.create_index('ix_shipping_mail_sync_runs_factory', 'shipping_mail_sync_runs', ['factory_id'])


def downgrade():
    op.drop_index('ix_shipping_mail_sync_runs_factory', table_name='shipping_mail_sync_runs')
    op.drop_table('shipping_mail_sync_runs')
    op.drop_index('ix_shipping_mail_accounts_factory', table_name='shipping_mail_accounts')
    op.drop_table('shipping_mail_accounts')
