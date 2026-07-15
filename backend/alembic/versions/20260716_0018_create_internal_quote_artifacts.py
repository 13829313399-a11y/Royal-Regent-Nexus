"""create internal quote imports attachments and retained exports

Revision ID: 20260716_0018
Revises: 20260715_0017
Create Date: 2026-07-16 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0018"
down_revision: Union[str, None] = "20260715_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_quote_import_batches",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("target_department", sa.String(length=64), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by", sa.String(length=64), nullable=False),
        sa.Column("confirmed_by_name", sa.String(length=128), nullable=False),
        sa.Column("confirmed_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("quote_id", "factory_id", "import_type", "target_department", "source_sha256", "status", "created_by", "confirmed_by"):
        op.create_index(f"ix_internal_quote_import_batches_{column}", "internal_quote_import_batches", [column])

    op.create_table(
        "internal_quote_attachments",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=128), nullable=False),
        sa.Column("uploaded_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("quote_id", "factory_id", "department", "sha256", "uploaded_by"):
        op.create_index(f"ix_internal_quote_attachments_{column}", "internal_quote_attachments", [column])

    op.create_table(
        "internal_quote_export_files",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("section_revisions_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("exported_by", sa.String(length=64), nullable=False),
        sa.Column("exported_by_name", sa.String(length=128), nullable=False),
        sa.Column("exported_at", sa.String(length=32), nullable=False),
        sa.Column("superseded_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("quote_id", "factory_id", "sha256", "status", "exported_by"):
        op.create_index(f"ix_internal_quote_export_files_{column}", "internal_quote_export_files", [column])


def downgrade() -> None:
    op.drop_table("internal_quote_export_files")
    op.drop_table("internal_quote_attachments")
    op.drop_table("internal_quote_import_batches")
