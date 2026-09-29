import importlib
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_auth_api import make_client


def test_additive_upgrade_and_personal_data_rollback_guard(monkeypatch):
    with make_client(monkeypatch):
        dbm = importlib.import_module('app.db')
        path = Path(__file__).parents[1] / 'alembic/versions/20260928_0126_work_center.py'
        spec = importlib.util.spec_from_file_location('work_center_migration', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with dbm.engine.begin() as conn:
            for name in ('work_center_preferences', 'work_center_user_states', 'work_center_events', 'work_center_entries'):
                conn.execute(text(f'DROP TABLE {name}'))
            conn.execute(text('ALTER TABLE molding_sample_problems DROP COLUMN responsibility_revision'))
            original = conn.scalar(text('SELECT count(*) FROM auth_users'))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()
            assert conn.scalar(text('SELECT count(*) FROM auth_users')) == original
            assert 'work_center_entries' in inspect(conn).get_table_names()
            conn.execute(text("INSERT INTO work_center_preferences (user_id, values, version, updated_at) VALUES ('user-admin', '{}', 1, CURRENT_TIMESTAMP)".replace('values,', '"values",')))
            with pytest.raises(RuntimeError, match='Export personal'):
                migration.downgrade()
