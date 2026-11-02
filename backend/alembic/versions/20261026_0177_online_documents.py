"""Private online documents, additive branch from the deployed 0175 schema."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_0177"
down_revision = "20261022_0175"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("online_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        *[sa.Column(name, sa.String(size), nullable=False) for name, size in (
            ("factory_id",64), ("owner_id",64), ("owner_name",128), ("title",200), ("format",8),
            ("storage_key",400), ("sha256",64), ("editor_key",128), ("editor_source",400),
            ("pending_save",64), ("saved_request",64), ("save_error",200), ("created_at",32), ("updated_at",32))],
        *[sa.Column(name, sa.Integer(), nullable=False) for name in ("owner_epoch", "revision", "byte_size", "editor_started", "pending_since")],
        sa.Column("grants", sa.JSON(), nullable=False), sa.Column("participants", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_online_document_revision"))
    for name in ("factory_id", "owner_id", "editor_key"):
        op.create_index("ix_online_documents_" + name, "online_documents", [name])
    op.create_table("online_document_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("online_documents.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("document_id", "revision", name="uq_online_document_revision"))
    op.create_index("ix_online_document_revisions_document_id", "online_document_revisions", ["document_id"])
    if op.get_context().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER online_document_revisions_no_{action.lower()} BEFORE {action} ON online_document_revisions BEGIN SELECT RAISE(ABORT, 'online document history is append-only'); END")
    elif op.get_context().dialect.name == "postgresql":
        op.execute("CREATE FUNCTION online_document_history_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'online document history is append-only'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER online_document_revisions_immutable BEFORE UPDATE OR DELETE ON online_document_revisions FOR EACH ROW EXECUTE FUNCTION online_document_history_immutable()")


def downgrade():
    if op.get_context().as_sql or op.get_bind().execute(sa.text("SELECT 1 FROM online_documents LIMIT 1")).first():
        raise RuntimeError("不能删除已有文档；回滚程序版本时保留在线文档表和文件")
    op.drop_table("online_document_revisions")
    op.drop_table("online_documents")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION online_document_history_immutable()")
