"""create persistent factory-scoped carton-mark library

Revision ID: 20260813_0075
Revises: 20260813_0074
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_0075"
down_revision: str | Sequence[str] | None = "20260813_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "carton_mark_templates",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("po", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("item", sa.String(length=128), nullable=False),
        sa.Column("contract_number", sa.String(length=128), nullable=False),
        sa.Column("business_key_sha256", sa.String(length=64), nullable=False),
        sa.Column("document_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("check_status", sa.String(length=16), nullable=False),
        sa.Column("check_result_json", sa.Text(), nullable=False),
        sa.Column("excel_sha256", sa.String(length=64), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("archived_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "archived_by_name",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column("archived_at", sa.String(length=40), nullable=False, server_default=""),
        sa.CheckConstraint("version >= 1", name="ck_carton_mark_template_version"),
        sa.CheckConstraint(
            "check_status IN ('核对通过', '发现差异', '需复核')",
            name="ck_carton_mark_template_check_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "factory_id", name="uq_carton_mark_template_id_factory"
        ),
        sa.UniqueConstraint(
            "factory_id",
            "document_fingerprint",
            name="uq_carton_mark_template_factory_documents",
        ),
        sa.UniqueConstraint(
            "factory_id",
            "business_key_sha256",
            "version",
            name="uq_carton_mark_template_business_version",
        ),
    )
    op.create_index(
        "ix_carton_mark_template_factory_active_created",
        "carton_mark_templates",
        ["factory_id", "is_archived", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_carton_mark_template_factory_customer_item",
        "carton_mark_templates",
        ["factory_id", "customer_name", "item"],
        unique=False,
    )

    op.create_table(
        "carton_mark_documents",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("template_id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "kind IN ('source_excel', 'print_pdf')",
            name="ck_carton_mark_document_kind",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_carton_mark_document_size"),
        sa.ForeignKeyConstraint(
            ["template_id", "factory_id"],
            ["carton_mark_templates.id", "carton_mark_templates.factory_id"],
            name="fk_carton_mark_document_template_factory",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id", "kind", name="uq_carton_mark_document_template_kind"
        ),
    )
    op.create_index(
        "ix_carton_mark_document_factory_template",
        "carton_mark_documents",
        ["factory_id", "template_id"],
        unique=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    populated = [
        table_name
        for table_name in ("carton_mark_templates", "carton_mark_documents")
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "20260813_0075 cannot be downgraded after carton-mark data exists: "
            + ",".join(populated)
        )
    op.drop_index(
        "ix_carton_mark_document_factory_template",
        table_name="carton_mark_documents",
    )
    op.drop_table("carton_mark_documents")
    op.drop_index(
        "ix_carton_mark_template_factory_customer_item",
        table_name="carton_mark_templates",
    )
    op.drop_index(
        "ix_carton_mark_template_factory_active_created",
        table_name="carton_mark_templates",
    )
    op.drop_table("carton_mark_templates")
