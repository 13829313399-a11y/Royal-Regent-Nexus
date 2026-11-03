"""Add private feedback, subscription receipts and metadata-only run metrics."""
from alembic import op
import sqlalchemy as sa

revision = '20261102_0189'
down_revision = '20261102_0188'
branch_labels = None
depends_on = None


def run_key():
    return sa.Column('run_id', sa.String(64), sa.ForeignKey('nexus_assistant_runs.id', ondelete='CASCADE'), primary_key=True)


def upgrade():
    op.create_table('nexus_assistant_run_metrics', run_key(),
        sa.Column('protocol_version',sa.Integer(),nullable=False),
        sa.Column('model',sa.String(160),nullable=False),
        sa.Column('thinking',sa.String(16),nullable=False),
        sa.Column('search_mode',sa.String(16),nullable=False),
        sa.Column('route',sa.String(24),nullable=False),
        sa.Column('used_files',sa.Boolean(),nullable=False),
        sa.Column('used_tools',sa.Boolean(),nullable=False),
        sa.Column('started_at',sa.Float(),nullable=False),
        sa.Column('finished_at',sa.Float(),nullable=True),
        sa.Column('terminal_state',sa.String(24),nullable=True),
        sa.Column('error_code',sa.String(64),nullable=True),
        sa.Column('first_event_seconds',sa.Float(),nullable=True),
        sa.Column('first_delta_seconds',sa.Float(),nullable=True),
        sa.Column('first_answer_seconds',sa.Float(),nullable=True),
        sa.Column('elapsed_seconds',sa.Float(),nullable=True),
        sa.Column('cancel_requested_at',sa.Float(),nullable=True),
        sa.Column('upstream_closed_at',sa.Float(),nullable=True),
        sa.Column('counters',sa.JSON(),nullable=False),
        sa.Column('total_tokens',sa.BigInteger(),nullable=True),
        sa.Column('usage_state',sa.String(24),nullable=False))
    op.create_index('ix_narm_window','nexus_assistant_run_metrics',['started_at','run_id'])
    op.create_table('nexus_assistant_subscriptions',run_key(),
        sa.Column('subscriber_id',sa.String(64),primary_key=True),
        sa.Column('after_seq',sa.Integer(),nullable=False),
        sa.Column('delivered_seq',sa.Integer(),nullable=False),
        sa.Column('applied_seq',sa.Integer(),nullable=True),
        sa.Column('connected_at',sa.Float(),nullable=False),
        sa.Column('closed_at',sa.Float(),nullable=True))
    op.create_index('ix_nasu_window','nexus_assistant_subscriptions',['connected_at','run_id'])
    op.create_table('nexus_assistant_feedback',run_key(),
        sa.Column('owner_user_id',sa.String(64),sa.ForeignKey('auth_users.id'),nullable=False),
        sa.Column('employment_epoch',sa.Integer(),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('categories',sa.JSON(),nullable=False),
        sa.Column('source_ids',sa.JSON(),nullable=False),
        sa.Column('comment',sa.Text(),nullable=False),
        sa.Column('last_request_id',sa.String(64),nullable=False),
        sa.Column('last_request_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('updated_at',sa.Float(),nullable=False))
    op.create_index('ix_nafb_window','nexus_assistant_feedback',['updated_at','run_id'])


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError('Inspect private data before empty-only downgrade; code rollback retains tables')
    names=('nexus_assistant_feedback','nexus_assistant_subscriptions','nexus_assistant_run_metrics')
    for name in names:
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {name}')):
            raise RuntimeError('Assistant operations and feedback must be preserved; disable the feature for rollback')
    for name in names:
        op.drop_table(name)
