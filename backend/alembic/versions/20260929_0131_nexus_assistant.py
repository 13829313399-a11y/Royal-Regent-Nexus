"""Independent private assistant; does not recreate retired ai_* tables."""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0131"
down_revision = "20260929_0130"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("nexus_assistant_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False),
        sa.Column("create_request_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("deletion_state", sa.String(16), nullable=False),
        sa.Column("deleted_at", sa.Float()),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("budget_day", sa.String(10)),
        sa.Column("budget_tokens", sa.BigInteger(), nullable=False),
        sa.Column("budget_unknown", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("owner_user_id", "employment_epoch", "create_request_id", name="uq_nas_create"))
    op.create_index("ix_nas_owner_page", "nexus_assistant_sessions", ["owner_user_id", "employment_epoch", "id"])
    op.create_table("nexus_assistant_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_request_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("provider_request_id", sa.String(160)),
        sa.Column("usage", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("lease_owner", sa.String(64), nullable=False),
        sa.Column("lease_expires_at", sa.Float(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float()),
        sa.Column("request_input", sa.JSON(), nullable=False),
        sa.Column("context_window", sa.JSON(), nullable=False),
        sa.UniqueConstraint("session_id", "client_request_id", name="uq_nar_request"))
    op.create_index("ix_nexus_assistant_runs_session_id", "nexus_assistant_runs", ["session_id"])
    op.create_index("ix_nar_admission", "nexus_assistant_runs", ["state", "lease_expires_at"])
    op.create_table("nexus_assistant_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("nexus_assistant_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_parts", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("help_citations", sa.JSON(), nullable=False),
        sa.Column("context_descriptor", sa.JSON()),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("session_id", "seq", name="uq_nam_seq"))
    op.create_index("ix_nexus_assistant_messages_session_id", "nexus_assistant_messages", ["session_id"])
    op.create_index("ix_nexus_assistant_messages_run_id", "nexus_assistant_messages", ["run_id"])
    op.create_table("nexus_assistant_attachments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("nexus_assistant_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(96), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float()))
    op.create_index("ix_nexus_assistant_attachments_session_id", "nexus_assistant_attachments", ["session_id"])


def downgrade():
    for table in ("nexus_assistant_sessions", "nexus_assistant_runs", "nexus_assistant_messages", "nexus_assistant_attachments"):
        if op.get_bind().scalar(sa.text(f"SELECT COUNT(*) FROM {table}")):
            raise RuntimeError("Assistant records exist. Disable the feature and retain tables; back up before any removal.")
    for table in ("nexus_assistant_attachments", "nexus_assistant_messages", "nexus_assistant_runs", "nexus_assistant_sessions"):
        op.drop_table(table)
