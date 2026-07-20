"""share raw material master data across factories

Revision ID: 20260720_0027
Revises: 20260718_0026
Create Date: 2026-07-20 12:00:00

Equivalent rows are compared by business fields only. Identity, factory scope,
creator and timestamp fields are intentionally excluded from conflict checks.
For each material code, the canonical row is the first row ordered by
``factory_id, id``; its identity and audit metadata are retained and its scope
is changed to ``*``. The merge is forward-only, so take and verify a database
backup before applying this revision.
"""

from typing import Sequence, Union

from alembic import context, op
from alembic.util import CommandError
import sqlalchemy as sa


revision: str = "20260720_0027"
down_revision: Union[str, None] = "20260718_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RAW_MATERIAL_BUSINESS_FIELDS = (
    "material_name",
    "category",
    "spec",
    "unit",
    "supplier",
    "safety_stock_kg",
    "status",
    "notes",
)
SQLITE_OFFLINE_ERROR = (
    "20260720_0027 cannot run as SQLite offline SQL because the migration "
    "must inspect and merge existing raw_materials rows and rebuild table "
    "constraints; run this revision in SQLite online mode"
)


def _acquire_sqlite_write_lock(connection: sa.Connection) -> None:
    driver_connection = connection.connection.driver_connection
    if getattr(driver_connection, "in_transaction", False):
        # A prior revision may already have opened the DBAPI transaction. A
        # no-op write promotes it to SQLite's single-writer lock before the
        # first raw-material read without nesting another BEGIN statement.
        connection.exec_driver_sql(
            "UPDATE raw_materials SET factory_id = factory_id WHERE 0",
        )
        return

    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _replace_raw_material_constraints(dialect_name: str) -> None:
    if dialect_name == "sqlite":
        with op.batch_alter_table("raw_materials", recreate="always") as batch_op:
            batch_op.drop_constraint(
                "uq_raw_materials_factory_code",
                type_="unique",
            )
            batch_op.create_unique_constraint(
                "uq_raw_materials_material_code",
                ["material_code"],
            )
            batch_op.create_check_constraint(
                "ck_raw_materials_global_factory",
                "factory_id = '*'",
            )
        return

    op.drop_constraint(
        "uq_raw_materials_factory_code",
        "raw_materials",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_raw_materials_material_code",
        "raw_materials",
        ["material_code"],
    )
    op.create_check_constraint(
        "ck_raw_materials_global_factory",
        "raw_materials",
        "factory_id = '*'",
    )


def _offline_postgresql_upgrade() -> None:
    op.execute(sa.text("LOCK TABLE raw_materials IN ACCESS EXCLUSIVE MODE"))
    op.execute(sa.text("""
        DO $$
        DECLARE
            conflict_codes TEXT;
        BEGIN
            SELECT string_agg(
                DISTINCT left_row.material_code,
                ', ' ORDER BY left_row.material_code
            )
            INTO conflict_codes
            FROM raw_materials AS left_row
            JOIN raw_materials AS right_row
              ON right_row.material_code = left_row.material_code
             AND (
                    left_row.factory_id < right_row.factory_id
                 OR (
                        left_row.factory_id = right_row.factory_id
                    AND left_row.id < right_row.id
                 )
             )
            WHERE left_row.material_name IS DISTINCT FROM right_row.material_name
               OR left_row.category IS DISTINCT FROM right_row.category
               OR left_row.spec IS DISTINCT FROM right_row.spec
               OR left_row.unit IS DISTINCT FROM right_row.unit
               OR left_row.supplier IS DISTINCT FROM right_row.supplier
               OR left_row.safety_stock_kg IS DISTINCT FROM right_row.safety_stock_kg
               OR left_row.status IS DISTINCT FROM right_row.status
               OR left_row.notes IS DISTINCT FROM right_row.notes;

            IF conflict_codes IS NOT NULL THEN
                RAISE EXCEPTION
                    'raw material master data conflict for material_code(s): %',
                    conflict_codes;
            END IF;

            DELETE FROM raw_materials AS duplicate_row
            USING raw_materials AS canonical_row
            WHERE canonical_row.material_code = duplicate_row.material_code
              AND (
                    canonical_row.factory_id < duplicate_row.factory_id
                 OR (
                        canonical_row.factory_id = duplicate_row.factory_id
                    AND canonical_row.id < duplicate_row.id
                 )
              );

            UPDATE raw_materials SET factory_id = '*';
        END $$;
    """))
    _replace_raw_material_constraints("postgresql")


def upgrade() -> None:
    if context.is_offline_mode():
        if context.get_context().dialect.name != "postgresql":
            raise CommandError(SQLITE_OFFLINE_ERROR)
        _offline_postgresql_upgrade()
        return

    connection = op.get_bind()
    dialect_name = connection.dialect.name
    if dialect_name == "postgresql":
        connection.execute(
            sa.text("LOCK TABLE raw_materials IN ACCESS EXCLUSIVE MODE"),
        )
    elif dialect_name == "sqlite":
        _acquire_sqlite_write_lock(connection)

    rows = connection.execute(sa.text("""
        SELECT id, factory_id, material_code, material_name, category, spec,
               unit, supplier, safety_stock_kg, status, notes,
               created_by, created_at, updated_at
        FROM raw_materials
        ORDER BY material_code, factory_id, id
    """)).mappings().all()

    rows_by_code: dict[str, list[sa.RowMapping]] = {}
    for row in rows:
        rows_by_code.setdefault(row["material_code"], []).append(row)

    conflict_codes: list[str] = []
    duplicate_ids: list[str] = []
    for material_code, matching_rows in rows_by_code.items():
        canonical_row = matching_rows[0]
        canonical_signature = tuple(
            canonical_row[field] for field in RAW_MATERIAL_BUSINESS_FIELDS
        )
        if any(
            tuple(row[field] for field in RAW_MATERIAL_BUSINESS_FIELDS)
            != canonical_signature
            for row in matching_rows[1:]
        ):
            conflict_codes.append(material_code)
            continue
        duplicate_ids.extend(row["id"] for row in matching_rows[1:])

    if conflict_codes:
        raise RuntimeError(
            "raw material master data conflict for material_code(s): "
            + ", ".join(sorted(conflict_codes))
        )

    if duplicate_ids:
        connection.execute(
            sa.text("DELETE FROM raw_materials WHERE id = :material_id"),
            [{"material_id": material_id} for material_id in duplicate_ids],
        )
    connection.execute(sa.text("UPDATE raw_materials SET factory_id = '*'"))
    _replace_raw_material_constraints(dialect_name)


def downgrade() -> None:
    message = (
        "20260720_0027 is irreversible because equivalent per-factory raw "
        "material rows were merged into one shared row"
    )
    if context.is_offline_mode():
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                RAISE EXCEPTION '{message}';
            END $$;
        """))
        return
    raise RuntimeError(message)
