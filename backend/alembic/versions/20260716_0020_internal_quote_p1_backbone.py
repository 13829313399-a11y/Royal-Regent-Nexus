"""add internal quote P1 safety backbone

Revision ID: 20260716_0020
Revises: 20260716_0019
Create Date: 2026-07-16 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0020"
down_revision: Union[str, None] = "20260716_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep all 0016-0019 records in place and only enrich them with compatible
    # defaults. New records explicitly write module_version="v2" in the API.
    quote_columns = (
        sa.Column("business_owner_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("business_owner_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("target_date", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "module_version",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_rr2_compatible",
        ),
        sa.Column("header_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cloned_from_quote_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("archived_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("archived_at", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("archive_reason", sa.Text(), nullable=False, server_default=""),
    )
    for column in quote_columns:
        op.add_column("internal_quotes", column)

    op.create_index("ix_internal_quotes_business_owner_id", "internal_quotes", ["business_owner_id"])
    op.create_index("ix_internal_quotes_module_version", "internal_quotes", ["module_version"])
    op.create_index("ix_internal_quotes_cloned_from_quote_id", "internal_quotes", ["cloned_from_quote_id"])

    audit_columns = (
        sa.Column("factory_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("old_revision", sa.Integer(), nullable=True),
        sa.Column("new_revision", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=96), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(length=128), nullable=False, server_default=""),
    )
    for column in audit_columns:
        op.add_column("internal_quote_audit_logs", column)
    op.create_index("ix_internal_quote_audit_logs_factory_id", "internal_quote_audit_logs", ["factory_id"])
    op.create_index("ix_internal_quote_audit_logs_created_at", "internal_quote_audit_logs", ["created_at"])

    op.create_table(
        "internal_quote_section_revisions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("calculation_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["internal_quote_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", "revision", name="uq_internal_quote_section_revisions_section_revision"),
    )
    for column in ("quote_id", "section_id", "factory_id", "department", "created_by"):
        op.create_index(
            f"ix_internal_quote_section_revisions_{column}",
            "internal_quote_section_revisions",
            [column],
        )

    op.create_table(
        "internal_quote_reviews",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("review_type", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("section_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["internal_quote_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("quote_id", "section_id", "factory_id", "department", "actor_id", "decision"):
        op.create_index(f"ix_internal_quote_reviews_{column}", "internal_quote_reviews", [column])

    op.execute(
        sa.text(
            "UPDATE internal_quotes SET initiator_department = 'sales-business' "
            "WHERE initiator_department = 'sales'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE internal_quote_audit_logs SET factory_id = ("
            "SELECT internal_quotes.factory_id FROM internal_quotes "
            "WHERE internal_quotes.id = internal_quote_audit_logs.quote_id"
            ") WHERE factory_id = ''"
        )
    )


def downgrade() -> None:
    op.drop_table("internal_quote_reviews")
    op.drop_table("internal_quote_section_revisions")

    op.drop_index("ix_internal_quote_audit_logs_created_at", table_name="internal_quote_audit_logs")
    op.drop_index("ix_internal_quote_audit_logs_factory_id", table_name="internal_quote_audit_logs")
    for column in ("ip_address", "request_id", "reason", "new_revision", "old_revision", "factory_id"):
        op.drop_column("internal_quote_audit_logs", column)

    op.drop_index("ix_internal_quotes_cloned_from_quote_id", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_module_version", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_business_owner_id", table_name="internal_quotes")
    for column in (
        "archive_reason",
        "archived_at",
        "archived_by",
        "cloned_from_quote_id",
        "header_revision",
        "module_version",
        "remark",
        "target_date",
        "business_owner_name",
        "business_owner_id",
    ):
        op.drop_column("internal_quotes", column)
