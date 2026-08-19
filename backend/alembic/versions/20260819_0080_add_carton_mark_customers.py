"""add factory-scoped carton-mark customers

Revision ID: 20260819_0080
Revises: 20260818_0079
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError


revision: str = "20260819_0080"
down_revision: str | Sequence[str] | None = "20260818_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def upgrade() -> None:
    if context.is_offline_mode():
        raise CommandError(
            "20260819_0080 must run online because it backfills existing carton-mark customers"
        )

    op.create_table(
        "carton_mark_customers",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_carton_mark_customer_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "normalized_name",
            name="uq_carton_mark_customer_factory_name",
        ),
    )
    op.create_index(
        "ix_carton_mark_customers_factory_id",
        "carton_mark_customers",
        ["factory_id"],
        unique=False,
    )
    op.create_index(
        "ix_carton_mark_customers_created_by",
        "carton_mark_customers",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_carton_mark_customers_updated_by",
        "carton_mark_customers",
        ["updated_by"],
        unique=False,
    )
    op.create_index(
        "ix_carton_mark_customer_factory_name",
        "carton_mark_customers",
        ["factory_id", "normalized_name"],
        unique=False,
    )

    connection = op.get_bind()
    existing_names = connection.execute(
        sa.text(
            "SELECT factory_id, customer_name FROM carton_mark_templates "
            "WHERE TRIM(customer_name) <> '' "
            "ORDER BY factory_id, customer_name"
        )
    ).mappings().all()
    names_by_factory: dict[str, dict[str, str]] = {}
    for row in existing_names:
        factory_id = str(row["factory_id"]).strip()
        name = " ".join(str(row["customer_name"]).strip().split())
        if factory_id and name:
            names_by_factory.setdefault(factory_id, {}).setdefault(
                _normalized_name(name),
                name,
            )

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    customer_table = sa.table(
        "carton_mark_customers",
        sa.column("id", sa.String),
        sa.column("factory_id", sa.String),
        sa.column("name", sa.String),
        sa.column("normalized_name", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_by_name", sa.String),
        sa.column("created_at", sa.String),
        sa.column("updated_by", sa.String),
        sa.column("updated_by_name", sa.String),
        sa.column("updated_at", sa.String),
    )
    rows = [
        {
            "id": f"CMC-{uuid4().hex.upper()}",
            "factory_id": factory_id,
            "name": name,
            "normalized_name": normalized_name,
            "revision": 1,
            "created_by": "system",
            "created_by_name": "系统迁移",
            "created_at": timestamp,
            "updated_by": "system",
            "updated_by_name": "系统迁移",
            "updated_at": timestamp,
        }
        for factory_id, names in sorted(names_by_factory.items())
        for normalized_name, name in sorted(names.items())
    ]
    if rows:
        op.bulk_insert(customer_table, rows)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM carton_mark_customers")).scalar_one():
        raise RuntimeError(
            "20260819_0080 cannot be downgraded after carton-mark customer data exists; "
            "back up the customer library first"
        )
    op.drop_index(
        "ix_carton_mark_customer_factory_name",
        table_name="carton_mark_customers",
    )
    op.drop_index(
        "ix_carton_mark_customers_updated_by",
        table_name="carton_mark_customers",
    )
    op.drop_index(
        "ix_carton_mark_customers_created_by",
        table_name="carton_mark_customers",
    )
    op.drop_index(
        "ix_carton_mark_customers_factory_id",
        table_name="carton_mark_customers",
    )
    op.drop_table("carton_mark_customers")
