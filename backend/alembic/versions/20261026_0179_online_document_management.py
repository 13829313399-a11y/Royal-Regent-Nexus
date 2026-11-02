"""Recoverable document management; additive branch from office-only 0177."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_0179"
down_revision = "20261026_0177"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("online_document_revisions", sa.Column("protection", sa.JSON(), nullable=False, server_default="{}"))
    for column in (
        sa.Column("deleted_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("access_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("protection", sa.JSON(), nullable=False, server_default="{}"),
    ):
        op.add_column("online_documents", column)
    op.create_table("online_document_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("online_documents.id"), nullable=False),
        *[sa.Column(name, sa.String(size), nullable=False) for name, size in (
            ("kind",32), ("actor_id",64), ("actor_name",128), ("fingerprint",64), ("created_at",32))],
        sa.Column("actor_epoch", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=True),
        sa.UniqueConstraint("document_id", "command_id", name="uq_online_document_command"))
    op.create_index("ix_online_document_events_document_id", "online_document_events", ["document_id"])
    if op.get_context().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER online_document_events_no_{action.lower()} BEFORE {action} ON online_document_events BEGIN SELECT RAISE(ABORT, 'online document events are append-only'); END")
    elif op.get_context().dialect.name == "postgresql":
        op.execute("CREATE TRIGGER online_document_events_immutable BEFORE UPDATE OR DELETE ON online_document_events FOR EACH ROW EXECUTE FUNCTION online_document_history_immutable()")


def downgrade():
    raise RuntimeError("文档管理包含恢复及审计证据；回退应用时必须保留新增表、列和全部文件")
