"""add molding-sample production dispatch and inventory factory scope

Revision ID: 20260720_0028
Revises: 20260720_0027
Create Date: 2026-07-20 18:00:00

The migration intentionally refuses to guess the production destination for
historical Huakang C/D production work. It also refuses to add non-null
inventory scope when the factory cannot be inferred from an order-linked
requisition. All preflight validation runs before the first schema change.
"""

from collections import defaultdict
from typing import Sequence, Union

from alembic import context, op
from alembic.util import CommandError
import sqlalchemy as sa


revision: str = "20260720_0028"
down_revision: Union[str, None] = "20260720_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SELF_ASSIGNED_FACTORIES = (
    "huakang-a",
    "huakang-b",
    "huadeng",
    "huaxing",
)
HUAKANG_ENGINEERING_FACTORIES = ("huakang-c", "huakang-d")
PRODUCTION_HISTORY_STATUSES = ("待生产", "生产中", "已完成")
PRODUCTION_FACTORY_CHECK = (
    "production_factory_id IS NULL OR production_factory_id IN "
    "('huakang-a', 'huakang-b', 'huadeng', 'huaxing')"
)
OFFLINE_ERROR = (
    "20260720_0028 cannot run as offline SQL because it must preflight "
    "historical Huakang C/D production orders and infer legacy inventory "
    "factory scope; run this revision in online mode"
)
IRREVERSIBLE_ERROR = (
    "20260720_0028 is irreversible because production dispatch history and "
    "non-null inventory factory scope cannot be safely discarded"
)


def _sample(values: list[str], limit: int = 5) -> str:
    return ", ".join(values[:limit]) or "none"


def _acquire_migration_lock(connection: sa.Connection) -> None:
    dialect_name = connection.dialect.name
    if dialect_name == "postgresql":
        connection.execute(sa.text(
            "LOCK TABLE molding_sample_orders, molding_sample_requisitions, "
            "molding_sample_inventory_batches, molding_sample_inventory_movements "
            "IN ACCESS EXCLUSIVE MODE"
        ))
        return
    if dialect_name != "sqlite":
        raise CommandError(
            "20260720_0028 supports online migration only for SQLite and PostgreSQL"
        )

    driver_connection = connection.connection.driver_connection
    if getattr(driver_connection, "in_transaction", False):
        connection.exec_driver_sql(
            "UPDATE molding_sample_orders SET factory_id = factory_id WHERE 0"
        )
        return
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _load_preflight_plan(connection: sa.Connection) -> dict[str, dict[object, str]]:
    order_rows = connection.execute(sa.text(
        "SELECT id, factory_id, status FROM molding_sample_orders ORDER BY id"
    )).mappings().all()
    blocked_orders = [
        f"{row['id']}[{row['factory_id']}/{row['status']}]"
        for row in order_rows
        if row["factory_id"] in HUAKANG_ENGINEERING_FACTORIES
        and row["status"] in PRODUCTION_HISTORY_STATUSES
    ]
    if blocked_orders:
        raise CommandError(
            "20260720_0028 found historical Huakang C/D production orders; "
            "production destination must be assigned explicitly before migration. "
            "order IDs: " + ", ".join(blocked_orders)
        )

    order_origin_factory = {
        str(row["id"]): str(row["factory_id"])
        for row in order_rows
    }
    order_production_factory = {
        order_id: factory_id
        for order_id, factory_id in order_origin_factory.items()
        if factory_id in SELF_ASSIGNED_FACTORIES
    }

    requisition_rows = connection.execute(sa.text("""
        SELECT id, req_number, order_id, inventory_batch_id, inventory_batch_no
        FROM molding_sample_requisitions
        ORDER BY id
    """)).mappings().all()
    requisition_factory: dict[str, str] = {}
    requisition_factory_by_number: dict[str, str] = {}
    orphan_requisitions: list[str] = []
    for row in requisition_rows:
        order_id = str(row["order_id"])
        # Only self-producing legacy factories are safe to infer. A C/D order's
        # origin is not its inventory owner, so assigning C/D here would silently
        # invent the very production destination this migration must not guess.
        factory_id = order_production_factory.get(order_id)
        if not factory_id:
            orphan_requisitions.append(str(row["id"]))
            continue
        requisition_factory[str(row["id"])] = factory_id
        requisition_factory_by_number[str(row["req_number"])] = factory_id

    if orphan_requisitions:
        raise CommandError(
            "20260720_0028 cannot infer production factory scope for legacy "
            "requisitions (including C/D orders without an explicit mapping): "
            f"count={len(orphan_requisitions)}, sample={_sample(orphan_requisitions)}"
        )

    batch_rows = connection.execute(sa.text("""
        SELECT id, batch_no
        FROM molding_sample_inventory_batches
        ORDER BY id
    """)).mappings().all()
    batch_ids = {str(row["id"]) for row in batch_rows}
    batch_ids_by_number: dict[str, list[str]] = defaultdict(list)
    for row in batch_rows:
        batch_ids_by_number[str(row["batch_no"])].append(str(row["id"]))

    movement_rows = connection.execute(sa.text("""
        SELECT id, batch_id, batch_no, requisition_id, req_number
        FROM molding_sample_inventory_movements
        ORDER BY id
    """)).mappings().all()

    def referenced_batch_ids(batch_id: object, batch_no: object) -> set[str]:
        matches: set[str] = set()
        normalized_id = str(batch_id or "")
        normalized_number = str(batch_no or "")
        if normalized_id in batch_ids:
            matches.add(normalized_id)
        if normalized_number:
            matches.update(batch_ids_by_number.get(normalized_number, ()))
        return matches

    def referenced_requisition_factories(
        requisition_id: object,
        req_number: object,
    ) -> set[str]:
        factories: set[str] = set()
        normalized_id = str(requisition_id or "")
        normalized_number = str(req_number or "")
        if normalized_id in requisition_factory:
            factories.add(requisition_factory[normalized_id])
        if normalized_number in requisition_factory_by_number:
            factories.add(requisition_factory_by_number[normalized_number])
        return factories

    batch_candidates: dict[str, set[str]] = {
        batch_id: set() for batch_id in batch_ids
    }
    for row in requisition_rows:
        factory_id = requisition_factory.get(str(row["id"]))
        if not factory_id:
            continue
        for batch_id in referenced_batch_ids(
            row["inventory_batch_id"],
            row["inventory_batch_no"],
        ):
            batch_candidates[batch_id].add(factory_id)

    for row in movement_rows:
        factories = referenced_requisition_factories(
            row["requisition_id"],
            row["req_number"],
        )
        for batch_id in referenced_batch_ids(row["batch_id"], row["batch_no"]):
            batch_candidates[batch_id].update(factories)

    batch_factory = {
        batch_id: next(iter(candidates))
        for batch_id, candidates in batch_candidates.items()
        if len(candidates) == 1
    }
    unresolved_batches = sorted(
        batch_id
        for batch_id, candidates in batch_candidates.items()
        if len(candidates) != 1
    )

    movement_factory: dict[int, str] = {}
    unresolved_movements: list[str] = []
    for row in movement_rows:
        candidates = referenced_requisition_factories(
            row["requisition_id"],
            row["req_number"],
        )
        for batch_id in referenced_batch_ids(row["batch_id"], row["batch_no"]):
            candidates.update(batch_candidates[batch_id])
        if len(candidates) == 1:
            movement_factory[int(row["id"])] = next(iter(candidates))
        else:
            unresolved_movements.append(str(row["id"]))

    if unresolved_batches or unresolved_movements:
        raise CommandError(
            "20260720_0028 cannot infer legacy inventory factory scope before "
            "schema changes: "
            f"inventory_batches count={len(unresolved_batches)}, "
            f"sample={_sample(unresolved_batches)}; "
            f"inventory_movements count={len(unresolved_movements)}, "
            f"sample={_sample(unresolved_movements)}"
        )

    return {
        "order_production_factory": order_production_factory,
        "requisition_factory": requisition_factory,
        "batch_factory": batch_factory,
        "movement_factory": movement_factory,
    }


def _set_inventory_columns_not_null(dialect_name: str) -> None:
    table_names = (
        "molding_sample_requisitions",
        "molding_sample_inventory_batches",
        "molding_sample_inventory_movements",
    )
    if dialect_name == "sqlite":
        for table_name in table_names:
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                batch_op.alter_column(
                    "factory_id",
                    existing_type=sa.String(length=64),
                    nullable=False,
                )
        return

    for table_name in table_names:
        op.alter_column(
            table_name,
            "factory_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def _create_order_production_check(dialect_name: str) -> None:
    if dialect_name == "sqlite":
        with op.batch_alter_table("molding_sample_orders", recreate="always") as batch_op:
            batch_op.create_check_constraint(
                "ck_molding_sample_orders_production_factory",
                PRODUCTION_FACTORY_CHECK,
            )
        return
    op.create_check_constraint(
        "ck_molding_sample_orders_production_factory",
        "molding_sample_orders",
        PRODUCTION_FACTORY_CHECK,
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise CommandError(OFFLINE_ERROR)

    connection = op.get_bind()
    _acquire_migration_lock(connection)
    plan = _load_preflight_plan(connection)
    dialect_name = connection.dialect.name

    op.add_column(
        "molding_sample_orders",
        sa.Column("production_factory_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "molding_sample_orders",
        sa.Column(
            "production_assigned_at",
            sa.String(length=32),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "molding_sample_orders",
        sa.Column(
            "production_assigned_by",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "molding_sample_orders",
        sa.Column(
            "production_assignment_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    for table_name in (
        "molding_sample_requisitions",
        "molding_sample_inventory_batches",
        "molding_sample_inventory_movements",
    ):
        op.add_column(
            table_name,
            sa.Column("factory_id", sa.String(length=64), nullable=True),
        )

    if plan["order_production_factory"]:
        connection.execute(
            sa.text(
                "UPDATE molding_sample_orders "
                "SET production_factory_id = :factory_id "
                "WHERE id = :order_id"
            ),
            [
                {"order_id": order_id, "factory_id": factory_id}
                for order_id, factory_id in plan["order_production_factory"].items()
            ],
        )

    for table_name, id_column, plan_key in (
        ("molding_sample_requisitions", "id", "requisition_factory"),
        ("molding_sample_inventory_batches", "id", "batch_factory"),
        ("molding_sample_inventory_movements", "id", "movement_factory"),
    ):
        values = [
            {"row_id": row_id, "factory_id": factory_id}
            for row_id, factory_id in plan[plan_key].items()
        ]
        if values:
            connection.execute(
                sa.text(
                    f"UPDATE {table_name} SET factory_id = :factory_id "
                    f"WHERE {id_column} = :row_id"
                ),
                values,
            )

    _set_inventory_columns_not_null(dialect_name)
    _create_order_production_check(dialect_name)

    op.create_index(
        "ix_molding_sample_orders_production_status_created_at",
        "molding_sample_orders",
        ["production_factory_id", "status", "created_at"],
    )
    op.create_index(
        "ix_molding_sample_requisitions_factory_id",
        "molding_sample_requisitions",
        ["factory_id"],
    )
    op.create_index(
        "ix_molding_sample_inventory_batches_factory_id",
        "molding_sample_inventory_batches",
        ["factory_id"],
    )
    op.create_index(
        "ix_molding_sample_inventory_movements_factory_id",
        "molding_sample_inventory_movements",
        ["factory_id"],
    )

    op.create_table(
        "molding_sample_dispatch_logs",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("origin_factory_id", sa.String(length=64), nullable=False),
        sa.Column("from_production_factory_id", sa.String(length=64), nullable=True),
        sa.Column("to_production_factory_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("actor_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["molding_sample_orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column_name in (
        "order_id",
        "origin_factory_id",
        "to_production_factory_id",
        "action",
        "created_at",
    ):
        op.create_index(
            f"ix_molding_sample_dispatch_logs_{column_name}",
            "molding_sample_dispatch_logs",
            [column_name],
        )


def downgrade() -> None:
    raise CommandError(IRREVERSIBLE_ERROR)
