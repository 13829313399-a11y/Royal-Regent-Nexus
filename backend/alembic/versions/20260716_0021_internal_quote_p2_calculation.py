"""add internal quote P2 calculation snapshots

Revision ID: 20260716_0021
Revises: 20260716_0020
Create Date: 2026-07-16 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0021"
down_revision: Union[str, None] = "20260716_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "internal_quotes",
        sa.Column("reference_snapshot_id", sa.String(length=96), nullable=False, server_default=""),
    )
    op.add_column(
        "internal_quotes",
        sa.Column(
            "formula_version",
            sa.String(length=64),
            nullable=False,
            server_default="legacy_rr2_compatible",
        ),
    )
    op.create_index(
        "ix_internal_quotes_reference_snapshot_id",
        "internal_quotes",
        ["reference_snapshot_id"],
    )
    op.create_index("ix_internal_quotes_formula_version", "internal_quotes", ["formula_version"])

    section_columns = (
        sa.Column("calculation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("calculation_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("calculation_formula_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "calculation_reference_snapshot_id",
            sa.String(length=96),
            nullable=False,
            server_default="",
        ),
        sa.Column("calculated_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("dependency_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dependency_status", sa.String(length=32), nullable=False, server_default="current"),
    )
    for column in section_columns:
        op.add_column("internal_quote_sections", column)
    op.create_index(
        "ix_internal_quote_sections_calculation_status",
        "internal_quote_sections",
        ["calculation_status"],
    )
    op.create_index(
        "ix_internal_quote_sections_dependency_status",
        "internal_quote_sections",
        ["dependency_status"],
    )

    revision_columns = (
        sa.Column("formula_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("input_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("reference_snapshot_id", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("dependency_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
    )
    for column in revision_columns:
        op.add_column("internal_quote_section_revisions", column)
    op.create_index(
        "ix_internal_quote_section_revisions_reference_snapshot_id",
        "internal_quote_section_revisions",
        ["reference_snapshot_id"],
    )

    op.create_table(
        "internal_quote_reference_sets",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("superseded_at", sa.String(length=32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quote_id",
            "source_revision",
            name="uq_internal_quote_reference_sets_quote_revision",
        ),
    )
    for column in ("quote_id", "factory_id", "sha256", "is_current", "created_by"):
        op.create_index(
            f"ix_internal_quote_reference_sets_{column}",
            "internal_quote_reference_sets",
            [column],
        )


def downgrade() -> None:
    op.drop_table("internal_quote_reference_sets")

    op.drop_index(
        "ix_internal_quote_section_revisions_reference_snapshot_id",
        table_name="internal_quote_section_revisions",
    )
    for column in ("warnings_json", "dependency_hash", "reference_snapshot_id", "input_hash", "formula_version"):
        op.drop_column("internal_quote_section_revisions", column)

    op.drop_index("ix_internal_quote_sections_dependency_status", table_name="internal_quote_sections")
    op.drop_index("ix_internal_quote_sections_calculation_status", table_name="internal_quote_sections")
    for column in (
        "dependency_status",
        "dependency_hash",
        "calculated_at",
        "calculation_reference_snapshot_id",
        "calculation_formula_version",
        "calculation_hash",
        "calculation_status",
    ):
        op.drop_column("internal_quote_sections", column)

    op.drop_index("ix_internal_quotes_formula_version", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_reference_snapshot_id", table_name="internal_quotes")
    op.drop_column("internal_quotes", "formula_version")
    op.drop_column("internal_quotes", "reference_snapshot_id")
