"""Private assistant documents, artifact revisions and session favorites."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_0159"
down_revision = "20261012_0158"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("nexus_assistant_files",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("nexus_assistant_sessions.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(240), nullable=False), sa.Column("storage_key", sa.String(96), nullable=False),
        sa.Column("media_type", sa.String(80), nullable=False), sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("parse_status", sa.String(16), nullable=False), sa.Column("parse_owner", sa.String(64), nullable=False),
        sa.Column("parse_index", sa.JSON(), nullable=False), sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.Float(), nullable=False), sa.Column("updated_at", sa.Float(), nullable=False))
    op.create_index("ix_nexus_assistant_files_session_id", "nexus_assistant_files", ["session_id"])
    op.create_index("ix_nexus_assistant_files_owner_user_id", "nexus_assistant_files", ["owner_user_id"])
    op.create_table("nexus_assistant_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False), sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("source_run_id", sa.String(64), nullable=False), sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False), sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False))
    op.create_index("ix_naa_owner_page", "nexus_assistant_artifacts", ["owner_user_id", "employment_epoch", "updated_at", "id"])
    op.create_table("nexus_assistant_artifact_versions",
        sa.Column("artifact_id", sa.String(64), sa.ForeignKey("nexus_assistant_artifacts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False))
    op.create_table("nexus_assistant_favorites",
        sa.Column("session_id", sa.String(64), sa.ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False), sa.Column("created_at", sa.Float(), nullable=False))
    op.create_index("ix_nexus_assistant_favorites_owner_user_id", "nexus_assistant_favorites", ["owner_user_id"])


def downgrade():
    tables = ("nexus_assistant_favorites", "nexus_assistant_artifact_versions", "nexus_assistant_artifacts", "nexus_assistant_files")
    bind = op.get_bind()
    if any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in tables):
        raise RuntimeError("Assistant materials contain private data. Back up and explicitly remove data before downgrade.")
    for table in tables:
        op.drop_table(table)
