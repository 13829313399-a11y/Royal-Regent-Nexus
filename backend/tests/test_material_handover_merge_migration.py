"""Either published migration branch can reach the shared head without data loss."""
from pathlib import Path
import warnings

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.mark.parametrize('parent', ['20261012_0156', '20261012_0157'])
def test_merge_upgrades_either_parent_and_preserves_existing_rows(tmp_path, monkeypatch, parent):
    from app.core.config import settings

    backend = Path(__file__).resolve().parents[1]
    url = f'sqlite:///{tmp_path / "merge.db"}'
    monkeypatch.setattr(settings, 'database_url', url)
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    with warnings.catch_warnings():
        warnings.simplefilter('error', UserWarning)
        script = ScriptDirectory.from_config(config)
        assert script.get_heads() == ['20261012_0159']
    assert script.get_revision('20261012_0158').down_revision == ('20261012_0156', '20261012_0157')
    assert script.get_revision('20261012_0159').down_revision == '20261012_0158'

    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE auth_users(id TEXT PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO auth_users VALUES ('original-user')")
        connection.exec_driver_sql('CREATE TABLE nexus_assistant_sessions(id TEXT PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO nexus_assistant_sessions VALUES ('original-session')")
        connection.exec_driver_sql('CREATE TABLE nexus_assistant_runs(id TEXT PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO nexus_assistant_runs VALUES ('original-run')")
        connection.exec_driver_sql('CREATE TABLE cutting_ops_orders(line_id TEXT PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO cutting_ops_orders VALUES ('original-order')")
        connection.exec_driver_sql('CREATE TABLE fabric_master_records(id TEXT PRIMARY KEY, factory_id TEXT, UNIQUE(id, factory_id))')
        connection.exec_driver_sql("INSERT INTO fabric_master_records VALUES ('original-supplier', 'huakang-c')")
        connection.exec_driver_sql('CREATE TABLE three_d_printing_printer_state_events(id TEXT PRIMARY KEY, factory_id TEXT, printer_id TEXT, received_at TEXT)')
        connection.exec_driver_sql("INSERT INTO three_d_printing_printer_state_events VALUES ('original-event', 'huakang-a', 'printer', '2026-10-10')")

    command.stamp(config, '20261010_0154')
    command.upgrade(config, parent)
    command.upgrade(config, 'head')
    command.upgrade(config, 'head')

    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').all() == [('20261012_0159',)]
        assert connection.exec_driver_sql('SELECT * FROM auth_users').all() == [('original-user',)]
        assert connection.exec_driver_sql('SELECT * FROM nexus_assistant_sessions').all() == [('original-session',)]
        assert connection.exec_driver_sql('SELECT * FROM nexus_assistant_runs').all() == [('original-run',)]
        assert connection.exec_driver_sql('SELECT * FROM cutting_ops_orders').all() == [('original-order',)]
        assert connection.exec_driver_sql('SELECT * FROM fabric_master_records').all() == [('original-supplier', 'huakang-c')]
        assert connection.exec_driver_sql('SELECT * FROM three_d_printing_printer_state_events').all() == [('original-event', 'huakang-a', 'printer', '2026-10-10')]
        names = set(sa.inspect(connection).get_table_names())
        assert {'material_handover_documents', 'material_handover_supplier_bindings', 'cutting_ops_production_events', 'collab_messages'} <= names
        assert {'nexus_assistant_files', 'nexus_assistant_artifacts', 'nexus_assistant_artifact_versions', 'nexus_assistant_favorites'} <= names
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        assert 'ix_3d_event_printer_received' in {index['name'] for index in sa.inspect(connection).get_indexes('three_d_printing_printer_state_events')}
    engine.dispose()
