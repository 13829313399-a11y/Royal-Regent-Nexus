from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_removal_migration_drops_retired_tables_and_alert_rows(monkeypatch) -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260826_0084_remove_ai_subsystem.py"
    )
    spec = importlib.util.spec_from_file_location("retired_assistant_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        metadata = sa.MetaData()
        sa.Table(
            "system_notifications",
            metadata,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("type", sa.String(64), nullable=False),
        )
        for table_name in migration.AI_TABLES_CHILD_FIRST:
            sa.Table(
                table_name,
                metadata,
                sa.Column("id", sa.String(64), primary_key=True),
            )
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                "INSERT INTO system_notifications (id, type) "
                "VALUES ('retired-alert', 'ai_operational_alert'), "
                "('business-notice', 'user_registration')"
            )
        )

        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)
        migration.upgrade()

        remaining_tables = set(sa.inspect(connection).get_table_names())
        assert not (set(migration.AI_TABLES_CHILD_FIRST) & remaining_tables)
        assert connection.execute(
            sa.text("SELECT id FROM system_notifications ORDER BY id")
        ).scalars().all() == ["business-notice"]
