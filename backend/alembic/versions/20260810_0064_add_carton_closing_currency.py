"""separate carton closings by source currency

Revision ID: 20260810_0064
Revises: 20260810_0063
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0064"
down_revision: str | Sequence[str] | None = "20260810_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CURRENCY_ALIASES = {
    "RMB": "CNY",
    "人民币": "CNY",
    "人民币元": "CNY",
    "¥": "CNY",
    "￥": "CNY",
    "港币": "HKD",
    "港元": "HKD",
    "HK$": "HKD",
}


def _normalize_currency(value: object) -> str:
    normalized = str(value or "").strip().upper()
    return _CURRENCY_ALIASES.get(normalized, normalized or "CNY")


def _period_end(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return end.isoformat()


def _backfill_currency(connection: sa.Connection) -> None:
    closings = list(
        connection.execute(
            sa.text(
                "SELECT id, factory_id, period, customer_code FROM carton_closings"
            )
        ).mappings()
    )
    for closing in closings:
        currencies = {
            _normalize_currency(row.currency)
            for row in connection.execute(
                sa.text(
                    "SELECT DISTINCT currency FROM carton_inventory_movements "
                    "WHERE factory_id = :factory_id "
                    "AND customer_code = :customer_code "
                    "AND occurred_at < :period_end"
                ),
                {
                    "factory_id": closing["factory_id"],
                    "customer_code": closing["customer_code"],
                    "period_end": f"{_period_end(closing['period'])}T",
                },
            )
        }
        if len(currencies) > 1:
            raise RuntimeError(
                "检测到既有纸箱月结混合多个币种，无法安全自动拆分："
                f"{closing['id']} ({', '.join(sorted(currencies))})。"
                "请先按来源流水完成币种对账。"
            )
        currency = next(iter(currencies), "CNY")
        connection.execute(
            sa.text("UPDATE carton_closings SET currency = :currency WHERE id = :id"),
            {"currency": currency, "id": closing["id"]},
        )


def upgrade() -> None:
    connection = op.get_bind()
    old_columns = ["factory_id", "period", "customer_code"]
    old_constraint = next(
        (
            constraint
            for constraint in sa.inspect(connection).get_unique_constraints(
                "carton_closings"
            )
            if constraint.get("column_names") == old_columns
        ),
        None,
    )
    if old_constraint is None:
        raise RuntimeError("找不到纸箱月结旧唯一约束，迁移已中止")
    naming_convention = {
        "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_%(column_2_name)s"
    }
    old_constraint_name = old_constraint.get("name") or (
        "uq_carton_closings_factory_id_period_customer_code"
    )
    with op.batch_alter_table(
        "carton_closings", naming_convention=naming_convention
    ) as batch_op:
        batch_op.add_column(sa.Column("currency", sa.String(8), nullable=True))
        batch_op.drop_constraint(old_constraint_name, type_="unique")
        batch_op.create_unique_constraint(
            "uq_carton_closing_factory_period_customer_currency",
            ["factory_id", "period", "customer_code", "currency"],
        )

    _backfill_currency(connection)

    missing = connection.execute(
        sa.text("SELECT COUNT(*) FROM carton_closings WHERE currency IS NULL")
    ).scalar_one()
    if missing:
        raise RuntimeError("纸箱月结币种回填不完整，迁移已中止")

    with op.batch_alter_table("carton_closings") as batch_op:
        batch_op.alter_column(
            "currency",
            existing_type=sa.String(8),
            nullable=False,
            server_default="CNY",
        )
        batch_op.create_index(
            "ix_carton_closings_currency", ["currency"], unique=False
        )


def downgrade() -> None:
    connection = op.get_bind()
    non_cny = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM carton_closings "
            "WHERE UPPER(TRIM(currency)) <> 'CNY'"
        )
    ).scalar_one()
    duplicate_groups = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "SELECT factory_id, period, customer_code "
            "FROM carton_closings GROUP BY factory_id, period, customer_code "
            "HAVING COUNT(*) > 1"
            ") AS duplicate_closings"
        )
    ).scalar_one()
    if non_cny or duplicate_groups:
        raise RuntimeError(
            "拒绝降级：纸箱月结已经包含非人民币或同客户多币种记录，"
            "移除币种字段会破坏财务数据。"
        )

    with op.batch_alter_table("carton_closings") as batch_op:
        batch_op.drop_index("ix_carton_closings_currency")
        batch_op.drop_constraint(
            "uq_carton_closing_factory_period_customer_currency", type_="unique"
        )
        batch_op.create_unique_constraint(
            "uq_carton_closing_factory_period_customer",
            ["factory_id", "period", "customer_code"],
        )
        batch_op.drop_column("currency")
