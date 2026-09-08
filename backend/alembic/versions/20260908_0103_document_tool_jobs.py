"""Durable owner-scoped document conversion jobs and artifacts. Frozen schema."""
import sqlalchemy as sa
from alembic import op

revision = "20260908_0103"
down_revision = "20260907_0102"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('document_tool_sources',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('owner_user_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('original_name', sa.String(length=256), nullable=False, primary_key=False),
        sa.Column('detected_type', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('byte_size', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False, primary_key=False),
        sa.Column('inspection_status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('inspection_job_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('manifest_key', sa.String(length=512), nullable=False, primary_key=False),
        sa.Column('factory_context', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('credential_ciphertext', sa.Text(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['auth_users.id']),
        sa.UniqueConstraint(*['id', 'owner_user_id'], name='uq_doc_source_owner'),
    )
    op.create_index('ix_document_tool_sources_owner_user_id', 'document_tool_sources', ['owner_user_id'], unique=False)
    op.create_table('document_tool_jobs',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('owner_user_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('source_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('parent_job_id', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('operation', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('options_json', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('request_fingerprint', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('client_request_id', sa.String(length=96), nullable=True, primary_key=False),
        sa.Column('execution_status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('quality_status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('stage', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('completed_units', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('total_units', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('attempt', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('lease_token', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('lease_until', sa.Float(), nullable=True, primary_key=False),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('artifact_revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('summary_json', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('error_code', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('error_message', sa.Text(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('started_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.Column('finished_at', sa.String(length=40), nullable=True, primary_key=False),
        sa.CheckConstraint("execution_status IN ('queued','running','awaiting_input','succeeded','failed','cancelled')", name='ck_doc_job_execution'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['auth_users.id']),
        sa.ForeignKeyConstraint(['source_id', 'owner_user_id'], ['document_tool_sources.id', 'document_tool_sources.owner_user_id']),
        sa.ForeignKeyConstraint(['parent_job_id'], ['document_tool_jobs.id']),
        sa.UniqueConstraint(*['id', 'owner_user_id'], name='uq_doc_job_owner'),
        sa.UniqueConstraint(*['owner_user_id', 'client_request_id'], name='uq_doc_job_request'),
    )
    op.create_index('ix_doc_jobs_claim', 'document_tool_jobs', ['execution_status', 'created_at', 'id'], unique=False)
    op.create_index('ix_doc_jobs_lease', 'document_tool_jobs', ['execution_status', 'lease_until'], unique=False)
    op.create_index('ix_doc_jobs_owner_created', 'document_tool_jobs', ['owner_user_id', 'created_at', 'id'], unique=False)
    op.create_table('document_tool_artifacts',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('job_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('owner_user_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('role', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('format', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('filename', sa.String(length=256), nullable=False, primary_key=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False, primary_key=False),
        sa.Column('size', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('sha256', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.Float(), nullable=True, primary_key=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['auth_users.id']),
        sa.ForeignKeyConstraint(['job_id', 'owner_user_id'], ['document_tool_jobs.id', 'document_tool_jobs.owner_user_id']),
        sa.UniqueConstraint(*['job_id', 'revision', 'storage_key'], name='uq_doc_artifact_publish'),
    )
    op.create_index('ix_document_tool_artifacts_job_id', 'document_tool_artifacts', ['job_id'], unique=False)
    op.create_index('ix_document_tool_artifacts_owner_user_id', 'document_tool_artifacts', ['owner_user_id'], unique=False)
    op.create_table('document_tool_corrections',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('parent_job_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('new_job_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('author_user_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('target_anchor', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('old_value', sa.Text(), nullable=False, primary_key=False),
        sa.Column('new_value', sa.Text(), nullable=False, primary_key=False),
        sa.Column('reason', sa.Text(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.String(length=40), nullable=False, primary_key=False),
        sa.ForeignKeyConstraint(['author_user_id'], ['auth_users.id']),
        sa.ForeignKeyConstraint(['new_job_id'], ['document_tool_jobs.id']),
        sa.ForeignKeyConstraint(['parent_job_id'], ['document_tool_jobs.id']),
    )
    op.create_index('ix_document_tool_corrections_new_job_id', 'document_tool_corrections', ['new_job_id'], unique=False)
    op.create_index('ix_document_tool_corrections_parent_job_id', 'document_tool_corrections', ['parent_job_id'], unique=False)


def downgrade():
    bind = op.get_bind()
    if any(bind.execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar() for table in (
        "document_tool_sources", "document_tool_jobs", "document_tool_artifacts", "document_tool_corrections")):
        raise RuntimeError("文档文件记录已存在，请先完成备份与数据保留决策，禁止直接删除")
    op.drop_table('document_tool_corrections')
    op.drop_table('document_tool_artifacts')
    op.drop_table('document_tool_jobs')
    op.drop_table('document_tool_sources')
