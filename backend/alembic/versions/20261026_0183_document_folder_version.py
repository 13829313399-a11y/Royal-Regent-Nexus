"""Prevent stale folder renames, including a name returning to an earlier value."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_0183"
down_revision = "20261026_0181"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("online_document_folders", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    raise RuntimeError("请保留文件夹并发版本；不支持丢弃重命名冲突保护")
