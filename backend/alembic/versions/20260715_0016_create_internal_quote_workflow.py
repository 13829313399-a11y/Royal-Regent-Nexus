"""create workshop-scoped internal quote workflow

Revision ID: 20260715_0016
Revises: 20260715_0015
Create Date: 2026-07-15 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0016"
down_revision: Union[str, None] = "20260715_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "internal_quotes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("workshop_code", sa.String(length=64), nullable=False),
        sa.Column("workshop_name", sa.String(length=128), nullable=False),
        sa.Column("quote_no", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("customer", sa.String(length=128), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "workshop_code",
            "quote_no",
            "version_label",
            name="uq_internal_quotes_factory_workshop_no_version",
        ),
    )
    op.create_index("ix_internal_quotes_factory_id", "internal_quotes", ["factory_id"])
    op.create_index("ix_internal_quotes_workshop_code", "internal_quotes", ["workshop_code"])
    op.create_index("ix_internal_quotes_quote_no", "internal_quotes", ["quote_no"])
    op.create_index("ix_internal_quotes_customer", "internal_quotes", ["customer"])
    op.create_index("ix_internal_quotes_status", "internal_quotes", ["status"])
    op.create_index("ix_internal_quotes_created_by", "internal_quotes", ["created_by"])

    op.create_table(
        "internal_quote_sections",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("department_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("calculation_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("filled_by", sa.String(length=128), nullable=False),
        sa.Column("filled_at", sa.String(length=32), nullable=False),
        sa.Column("submitted_by", sa.String(length=128), nullable=False),
        sa.Column("submitted_by_id", sa.String(length=64), nullable=False),
        sa.Column("submitted_at", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=False),
        sa.Column("reviewed_at", sa.String(length=32), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", "department", name="uq_internal_quote_sections_quote_department"),
    )
    op.create_index("ix_internal_quote_sections_quote_id", "internal_quote_sections", ["quote_id"])
    op.create_index("ix_internal_quote_sections_department", "internal_quote_sections", ["department"])
    op.create_index("ix_internal_quote_sections_status", "internal_quote_sections", ["status"])
    op.create_index("ix_internal_quote_sections_submitted_by_id", "internal_quote_sections", ["submitted_by_id"])

    op.create_table(
        "internal_quote_audit_logs",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("quote_id", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["internal_quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_internal_quote_audit_logs_quote_id", "internal_quote_audit_logs", ["quote_id"])
    op.create_index("ix_internal_quote_audit_logs_department", "internal_quote_audit_logs", ["department"])
    op.create_index("ix_internal_quote_audit_logs_actor_id", "internal_quote_audit_logs", ["actor_id"])
    op.create_index("ix_internal_quote_audit_logs_action", "internal_quote_audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_internal_quote_audit_logs_action", table_name="internal_quote_audit_logs")
    op.drop_index("ix_internal_quote_audit_logs_actor_id", table_name="internal_quote_audit_logs")
    op.drop_index("ix_internal_quote_audit_logs_department", table_name="internal_quote_audit_logs")
    op.drop_index("ix_internal_quote_audit_logs_quote_id", table_name="internal_quote_audit_logs")
    op.drop_table("internal_quote_audit_logs")
    op.drop_index("ix_internal_quote_sections_submitted_by_id", table_name="internal_quote_sections")
    op.drop_index("ix_internal_quote_sections_status", table_name="internal_quote_sections")
    op.drop_index("ix_internal_quote_sections_department", table_name="internal_quote_sections")
    op.drop_index("ix_internal_quote_sections_quote_id", table_name="internal_quote_sections")
    op.drop_table("internal_quote_sections")
    op.drop_index("ix_internal_quotes_created_by", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_status", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_customer", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_quote_no", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_workshop_code", table_name="internal_quotes")
    op.drop_index("ix_internal_quotes_factory_id", table_name="internal_quotes")
    op.drop_table("internal_quotes")
