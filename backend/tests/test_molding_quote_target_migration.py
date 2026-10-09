import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_quote_target_migration_preserves_old_rows_and_accepts_preexisting_column():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261009_0149_molding_quote_target.py"
    spec = importlib.util.spec_from_file_location("quote_target_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE molding_sample_items (id TEXT PRIMARY KEY, shoot_qty INTEGER, notes TEXT)")
        connection.exec_driver_sql("INSERT INTO molding_sample_items VALUES ('old', 50, 'keep')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT * FROM molding_sample_items").one() == ('old', 50, 'keep', None)
            connection.exec_driver_sql("UPDATE molding_sample_items SET quote_target_daily_qty=3600")
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT quote_target_daily_qty FROM molding_sample_items").scalar_one() == 3600
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT * FROM molding_sample_items").one() == ('old', 50, 'keep')
