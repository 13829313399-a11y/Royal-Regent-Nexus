"""add factory-scoped internal quote customers

Revision ID: 20260721_0029
Revises: 20260720_0028
Create Date: 2026-07-21 10:00:00
"""

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

from alembic import context, op
from alembic.util import CommandError
import sqlalchemy as sa


revision: str = "20260721_0029"
down_revision: Union[str, None] = "20260720_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FACTORY_IDS = (
    "huakang-a",
    "huakang-b",
    "huakang-c",
    "huakang-d",
    "huadeng",
    "huaxing",
)
DEFAULT_CUSTOMERS = ("BuzzBee", "Disney", "Dickie", "彩星", "Huaxing Demo")


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def upgrade() -> None:
    if context.is_offline_mode():
        raise CommandError(
            "20260721_0029 must run online because it backfills distinct historical customers"
        )

    op.create_table(
        "internal_quote_customers",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("normalized_name", sa.String(length=128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_by_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by_name", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "normalized_name",
            name="uq_internal_quote_customers_factory_name",
        ),
    )
    for column_name in ("factory_id", "created_by", "updated_by"):
        op.create_index(
            f"ix_internal_quote_customers_{column_name}",
            "internal_quote_customers",
            [column_name],
            unique=False,
        )

    connection = op.get_bind()
    historical_rows = connection.execute(sa.text("""
        SELECT factory_id, customer
        FROM internal_quotes
        WHERE TRIM(customer) <> ''
        ORDER BY factory_id, customer
    """)).mappings().all()
    names_by_factory: dict[str, dict[str, str]] = {
        factory_id: {
            _normalized_name(name): name for name in DEFAULT_CUSTOMERS
        }
        for factory_id in FACTORY_IDS
    }
    for row in historical_rows:
        factory_id = str(row["factory_id"]).strip()
        name = str(row["customer"]).strip()
        if not factory_id or not name:
            continue
        names_by_factory.setdefault(factory_id, {}).setdefault(
            _normalized_name(name),
            name,
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    customer_table = sa.table(
        "internal_quote_customers",
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
            "id": f"IQC-{uuid4().hex.upper()}",
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
    for column_name in ("updated_by", "created_by", "factory_id"):
        op.drop_index(
            f"ix_internal_quote_customers_{column_name}",
            table_name="internal_quote_customers",
        )
    op.drop_table("internal_quote_customers")
