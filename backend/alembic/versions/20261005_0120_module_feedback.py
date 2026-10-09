"""Private factory-scoped module feedback, with append-only conversation evidence."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0120"
down_revision = "20260924_0119"
branch_labels = None
depends_on = None

EVIDENCE_TABLES = ("module_feedback_messages", "module_feedback_attachments", "module_feedback_reads")


def upgrade():
    op.create_table("module_feedback_tickets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("module", sa.String(64), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("author_name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("emoji", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_name", sa.String(128), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("requested_materials", sa.JSON(), nullable=False),
        sa.Column("provided_materials", sa.JSON(), nullable=False),
        sa.Column("release_note", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(96), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("factory_id", "author_id", "client_request_id", name="uq_feedback_create_request"),
        sa.CheckConstraint("revision >= 1", name="ck_feedback_revision"),
        sa.CheckConstraint("status IN ('submitted','needs_info','in_progress','awaiting_verification','resolved')", name="ck_feedback_status"))
    op.create_index("ix_feedback_scope", "module_feedback_tickets", ["factory_id", "module", "author_id"])
    op.create_table("module_feedback_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ticket_id", sa.String(64), sa.ForeignKey("module_feedback_tickets.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("requested_materials", sa.JSON(), nullable=False),
        sa.Column("provided_materials", sa.JSON(), nullable=False),
        sa.Column("release_note", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(96), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("ticket_id", "revision", name="uq_feedback_message_revision"),
        sa.UniqueConstraint("ticket_id", "actor_id", "client_request_id", name="uq_feedback_message_request"))
    op.create_index("ix_module_feedback_messages_ticket_id", "module_feedback_messages", ["ticket_id"])
    op.create_table("module_feedback_attachments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("message_id", sa.String(64), sa.ForeignKey("module_feedback_messages.id"), nullable=False),
        sa.Column("file_name", sa.String(180), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False))
    op.create_index("ix_module_feedback_attachments_message_id", "module_feedback_attachments", ["message_id"])
    op.create_table("module_feedback_reads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("ticket_id", sa.String(64), sa.ForeignKey("module_feedback_tickets.id"), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("through_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("through_revision >= 0", name="ck_feedback_read_revision"))
    op.create_index("ix_module_feedback_reads_ticket_id", "module_feedback_reads", ["ticket_id"])
    op.create_index("ix_module_feedback_reads_user_id", "module_feedback_reads", ["user_id"])
    if op.get_bind().dialect.name == "sqlite":
        for table in EVIDENCE_TABLES:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                           "BEGIN SELECT RAISE(ABORT, 'feedback evidence is append-only'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION module_feedback_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'feedback evidence is append-only'; END;
            $$ LANGUAGE plpgsql""")
        for table in EVIDENCE_TABLES:
            op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION module_feedback_immutable()")
    op.execute(sa.text("""INSERT INTO auth_permissions (id, code, name, description)
        SELECT 'perm-module_feedback-manage', 'module_feedback:manage', '模块反馈开发处理',
        '仅在明确授权的厂区和系统部门处理用户反馈，不授予普通业务职位'
        WHERE NOT EXISTS (SELECT 1 FROM auth_permissions WHERE code = 'module_feedback:manage')"""))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM module_feedback_tickets LIMIT 1")).first():
        raise RuntimeError("Cannot discard persisted feedback evidence")
    for table in reversed(EVIDENCE_TABLES):
        op.drop_table(table)
    op.drop_table("module_feedback_tickets")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION module_feedback_immutable()")
    # Retain the catalog identifier and any explicit IAM assignment; removing
    # either is a separate administrative decision, never a schema downgrade.
