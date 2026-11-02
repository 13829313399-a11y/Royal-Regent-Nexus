"""Add the private V3 execution queue, event log and provider step ledger.

No existing run is converted or replayed. Code rollback disables admission
and retains these tables; populated downgrade is intentionally refused.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261026_0176'
down_revision = '20261022_0175'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('nexus_assistant_executions',
        sa.Column('run_id', sa.String(64), sa.ForeignKey('nexus_assistant_runs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('auth_session_id', sa.String(96), nullable=False),
        sa.Column('context_key', sa.String(256), nullable=True),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('worker_id', sa.String(64), nullable=True),
        sa.Column('fence', sa.Integer(), nullable=False),
        sa.Column('last_seq', sa.Integer(), nullable=False),
        sa.Column('queued_at', sa.Float(), nullable=False),
        sa.Column('claimed_at', sa.Float(), nullable=True),
        sa.Column('limits', sa.JSON(), nullable=False),
        sa.Column('source_refs', sa.JSON(), nullable=False))
    op.create_index('ix_nae_queue', 'nexus_assistant_executions', ['status', 'queued_at'])
    op.create_table('nexus_assistant_run_events',
        sa.Column('run_id', sa.String(64), sa.ForeignKey('nexus_assistant_runs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('seq', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False))
    op.create_table('nexus_assistant_provider_steps',
        sa.Column('run_id', sa.String(64), sa.ForeignKey('nexus_assistant_runs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('step_id', sa.String(96), primary_key=True),
        sa.Column('fence', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(64), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('budget_tokens', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.String(160), nullable=True),
        sa.Column('usage', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.Float(), nullable=False),
        sa.Column('finished_at', sa.Float(), nullable=True))


def downgrade():
    names = ('nexus_assistant_provider_steps', 'nexus_assistant_run_events', 'nexus_assistant_executions')
    if op.get_context().as_sql:
        raise RuntimeError('Inspect private run data before an empty-only downgrade; code rollback retains tables')
    for name in names:
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {name}')):
            raise RuntimeError('Durable run data must be preserved; disable the feature for code rollback')
    for name in names:
        op.drop_table(name)
