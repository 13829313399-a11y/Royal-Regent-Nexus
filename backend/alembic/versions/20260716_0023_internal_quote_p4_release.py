"""add internal quote P4 commercial release and artifact handoff

Revision ID: 20260716_0023
Revises: 20260716_0022
Create Date: 2026-07-16 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0023"
down_revision: Union[str, None] = "20260716_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("final_release_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("final_submission_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_submission_manifest_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("final_submitted_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("final_submitted_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("final_submitted_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("final_reviewed_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("final_reviewed_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("final_reviewed_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("final_review_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("final_release_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_release_invalidated_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("final_release_invalidation_reason", sa.Text(), nullable=False, server_default=""),
    ):
        op.add_column("internal_quotes", column)
    op.create_index("ix_internal_quotes_final_release_status", "internal_quotes", ["final_release_status"])
    op.create_index("ix_internal_quotes_final_submitted_by", "internal_quotes", ["final_submitted_by"])
    op.create_index("ix_internal_quotes_final_reviewed_by", "internal_quotes", ["final_reviewed_by"])

    op.create_table(
        "internal_quote_final_reviews",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("submission_revision", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("header_revision", sa.Integer(), nullable=False),
        sa.Column("section_revisions_json", sa.Text(), nullable=False),
        sa.Column("release_manifest_json", sa.Text(), nullable=False),
        sa.Column("release_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("submitted_by", sa.String(length=64), nullable=False),
        sa.Column("submitted_by_name", sa.String(length=128), nullable=False),
        sa.Column("submitted_at", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quote_id",
            "submission_revision",
            name="uq_internal_quote_final_reviews_quote_submission",
        ),
    )
    for column in ("quote_id", "factory_id", "decision", "actor_id"):
        op.create_index(
            f"ix_internal_quote_final_reviews_{column}",
            "internal_quote_final_reviews",
            [column],
        )

    op.create_table(
        "internal_quote_artifact_handoffs",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("export_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("customer", sa.String(length=128), nullable=False),
        sa.Column("quote_no", sa.String(length=128), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("release_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="available"),
        sa.Column("artifact_manifest_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("consumed_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("consumed_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("consumed_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("consumer_reference", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("revoked_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("revoke_reason", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["export_id"], ["internal_quote_export_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("export_id", name="uq_internal_quote_artifact_handoffs_export"),
        sa.UniqueConstraint(
            "quote_id",
            "release_revision",
            name="uq_internal_quote_artifact_handoffs_quote_release",
        ),
    )
    for column in ("quote_id", "export_id", "factory_id", "customer", "status", "created_by", "consumed_by"):
        op.create_index(
            f"ix_internal_quote_artifact_handoffs_{column}",
            "internal_quote_artifact_handoffs",
            [column],
        )


def downgrade() -> None:
    op.drop_table("internal_quote_artifact_handoffs")
    op.drop_table("internal_quote_final_reviews")

    op.drop_index("ix_internal_quotes_final_reviewed_by", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_final_submitted_by", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_final_release_status", table_name="internal_quotes")
    for column in (
        "final_release_invalidation_reason",
        "final_release_invalidated_at",
        "final_release_revision",
        "final_review_comment",
        "final_reviewed_at",
        "final_reviewed_by_name",
        "final_reviewed_by",
        "final_submitted_at",
        "final_submitted_by_name",
        "final_submitted_by",
        "final_submission_manifest_json",
        "final_submission_revision",
        "final_release_status",
    ):
        op.drop_column("internal_quotes", column)
