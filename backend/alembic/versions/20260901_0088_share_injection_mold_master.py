"""share injection mold master across the four molding factories

Revision ID: 20260901_0088
Revises: 20260831_0087
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic.util.exc import CommandError

revision: str = "20260901_0088"
down_revision: str | Sequence[str] | None = "20260831_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _reject_ambiguous_mold_keys() -> None:
    connection = op.get_bind()
    duplicates = (
        connection.execute(
            sa.text(
                """
            SELECT mold_code, product_code, COUNT(*) AS duplicate_count
            FROM injection_schedule_molds
            GROUP BY mold_code, product_code
            HAVING COUNT(*) > 1
            ORDER BY mold_code, product_code
            """
            )
        )
        .mappings()
        .all()
    )
    if duplicates:
        examples = ", ".join(
            f"{row['mold_code']}/{row['product_code']}({row['duplicate_count']})"
            for row in duplicates[:10]
        )
        raise CommandError(
            "cannot create the shared injection mold master while duplicate "
            f"mold/product keys exist: {examples}"
        )


def upgrade() -> None:
    _reject_ambiguous_mold_keys()

    with op.batch_alter_table("injection_schedule_lines") as batch_op:
        batch_op.drop_constraint(
            "fk_injection_schedule_line_mold_factory", type_="foreignkey"
        )

    op.add_column(
        "injection_schedule_molds",
        sa.Column(
            "scope_type",
            sa.String(24),
            nullable=False,
            server_default="COMPANY_SHARED",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE injection_schedule_molds
            SET factory_id = 'company', scope_type = 'COMPANY_SHARED'
            """
        )
    )

    with op.batch_alter_table("injection_schedule_molds") as batch_op:
        batch_op.drop_constraint(
            "uq_injection_schedule_mold_id_factory", type_="unique"
        )
        batch_op.drop_constraint(
            "uq_injection_schedule_mold_factory_code_product", type_="unique"
        )
        batch_op.alter_column(
            "factory_id",
            existing_type=sa.String(64),
            nullable=False,
            server_default="company",
        )
        batch_op.create_unique_constraint(
            "uq_injection_schedule_mold_shared_code_product",
            ["mold_code", "product_code"],
        )
        batch_op.create_check_constraint(
            "ck_injection_schedule_mold_company_scope",
            "factory_id = 'company' AND scope_type = 'COMPANY_SHARED'",
        )

    op.create_index(
        "ix_injection_schedule_molds_scope_type",
        "injection_schedule_molds",
        ["scope_type"],
    )

    with op.batch_alter_table("injection_schedule_lines") as batch_op:
        batch_op.create_foreign_key(
            "fk_injection_schedule_line_shared_mold",
            "injection_schedule_molds",
            ["mold_id"],
            ["id"],
        )


def downgrade() -> None:
    connection = op.get_bind()
    mold_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM injection_schedule_molds")
    ).scalar_one()
    linked_line_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM injection_schedule_lines WHERE mold_id IS NOT NULL"
        )
    ).scalar_one()
    if mold_count or linked_line_count:
        raise CommandError(
            "cannot downgrade shared injection mold master after mold data exists; "
            "restore a verified pre-0088 backup instead"
        )

    with op.batch_alter_table("injection_schedule_lines") as batch_op:
        batch_op.drop_constraint(
            "fk_injection_schedule_line_shared_mold", type_="foreignkey"
        )

    op.drop_index(
        "ix_injection_schedule_molds_scope_type",
        table_name="injection_schedule_molds",
    )
    with op.batch_alter_table("injection_schedule_molds") as batch_op:
        batch_op.drop_constraint(
            "uq_injection_schedule_mold_shared_code_product", type_="unique"
        )
        batch_op.drop_constraint(
            "ck_injection_schedule_mold_company_scope", type_="check"
        )
        batch_op.alter_column(
            "factory_id",
            existing_type=sa.String(64),
            nullable=False,
            server_default=None,
        )
        batch_op.create_unique_constraint(
            "uq_injection_schedule_mold_id_factory", ["id", "factory_id"]
        )
        batch_op.create_unique_constraint(
            "uq_injection_schedule_mold_factory_code_product",
            ["factory_id", "mold_code", "product_code"],
        )
        batch_op.drop_column("scope_type")

    with op.batch_alter_table("injection_schedule_lines") as batch_op:
        batch_op.create_foreign_key(
            "fk_injection_schedule_line_mold_factory",
            "injection_schedule_molds",
            ["mold_id", "factory_id"],
            ["id", "factory_id"],
        )
