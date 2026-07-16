"""extend retained internal quote artifact tables for P3

Revision ID: 20260716_0022
Revises: 20260716_0021
Create Date: 2026-07-16 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0022"
down_revision: Union[str, None] = "20260716_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("source_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_schema_version", sa.String(length=32), nullable=False, server_default="p3-v1"),
        sa.Column("target_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirm_mode", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("confirmed_revision", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("internal_quote_import_batches", column)

    for column in (
        sa.Column("template_version", sa.String(length=64), nullable=False, server_default="internal-quote-p3-v1"),
        sa.Column("formula_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("reference_snapshot_id", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("header_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("release_stage", sa.String(length=32), nullable=False, server_default="p3_section_approved"),
        sa.Column("export_manifest_json", sa.Text(), nullable=False, server_default="{}"),
    ):
        op.add_column("internal_quote_export_files", column)
    op.create_index(
        "ix_internal_quote_export_files_reference_snapshot_id",
        "internal_quote_export_files",
        ["reference_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_internal_quote_export_files_reference_snapshot_id",
        table_name="internal_quote_export_files",
    )
    for column in (
        "export_manifest_json",
        "release_stage",
        "header_revision",
        "reference_snapshot_id",
        "formula_version",
        "template_version",
    ):
        op.drop_column("internal_quote_export_files", column)
    for column in (
        "confirmed_revision",
        "confirm_mode",
        "target_revision",
        "preview_schema_version",
        "source_size_bytes",
    ):
        op.drop_column("internal_quote_import_batches", column)
