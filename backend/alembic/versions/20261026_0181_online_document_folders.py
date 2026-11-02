"""Private document classification; leaves document bytes and ACLs untouched."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_0181"
down_revision = "20261026_0179"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("online_document_folders",
        *[sa.Column(name, sa.String(size), primary_key=name == "id", nullable=False) for name, size in (
            ("id", 64), ("factory_id", 64), ("owner_id", 64), ("name", 100), ("name_key", 300), ("created_at", 32))],
        sa.Column("owner_epoch", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint("factory_id", "owner_id", "owner_epoch", "name_key", name="uq_online_document_folder_name"))
    op.create_table("online_document_placements",
        sa.Column("document_id", sa.String(64), sa.ForeignKey("online_documents.id"), primary_key=True),
        sa.Column("folder_id", sa.String(64), sa.ForeignKey("online_document_folders.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_online_document_placement_version"))
    op.create_index("ix_online_document_placements_folder_id", "online_document_placements", ["folder_id"])


def downgrade():
    raise RuntimeError("请保留文档文件夹及归类记录；不支持自动删除用户分类")
