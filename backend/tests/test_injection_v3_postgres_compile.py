"""Dialect compilation only; this does not establish a PostgreSQL migration run."""

import importlib.util
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable


def test_frozen_0100_schema_and_seed_statements_compile_for_postgres():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20260905_0100_injection_v3.py"
    )
    spec = importlib.util.spec_from_file_location("injection_v3_compile", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata, statements, seed_rows = sa.MetaData(), [], []
    dialect = postgresql.dialect()

    class Capture:
        def f(self, name):
            return name

        def create_table(self, name, *elements, **kwargs):
            return sa.Table(name, metadata, *elements, **kwargs)

        def create_index(self, name, table, columns, unique=False):
            sa.Index(
                name,
                *[metadata.tables[table].c[column] for column in columns],
                unique=unique,
            )

        def bulk_insert(self, table, rows):
            seed_rows.extend(rows)
            for row in rows:
                statements.append(
                    str(table.insert().values(**row).compile(dialect=dialect))
                )

        def execute(self, statement):
            statements.append(
                statement
                if isinstance(statement, str)
                else str(statement.compile(dialect=dialect))
            )

    migration.op = Capture()
    migration.upgrade()
    ddl = [
        str(CreateTable(table).compile(dialect=dialect))
        for table in metadata.sorted_tables
    ]
    ddl.extend(
        str(CreateIndex(index).compile(dialect=dialect))
        for table in metadata.sorted_tables
        for index in table.indexes
    )
    assert len(metadata.tables) == 16 and len(seed_rows) == 4
    assert {row["factory_id"] for row in seed_rows} == {
        "huaxing",
        "huadeng",
        "huakang-a",
        "huakang-b",
    }
    assert (
        sum("INSERT INTO auth_permissions" in statement for statement in statements)
        == 4
    )
    assert (
        sum(
            "INSERT INTO auth_permission_metadata" in statement
            for statement in statements
        )
        == 4
    )
    assert any("TIMESTAMP WITH TIME ZONE" in statement for statement in ddl)
    assert any("FOREIGN KEY(machine_id, factory_id)" in statement for statement in ddl)
    output = os.environ.get("INJECTION_V3_POSTGRES_COMPILE_OUTPUT")
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "-- PostgreSQL dialect compilation only. Never executed against a PostgreSQL server.\n"
            + "\n\n".join(
                [*ddl, "-- Bound seed statements (parameters omitted):", *statements]
            ),
            encoding="utf-8",
        )
