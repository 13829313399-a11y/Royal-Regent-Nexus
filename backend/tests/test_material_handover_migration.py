import importlib
import runpy
from io import StringIO
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration():
    return runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions/20261012_0155_material_handover.py'))


def test_additive_migration_immutable_guards_and_empty_downgrade(tmp_path, monkeypatch):
    script = migration()
    engine = sa.create_engine(f'sqlite:///{tmp_path / "migration.db"}')
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.exec_driver_sql('CREATE TABLE old_inventory(id TEXT PRIMARY KEY, quantity TEXT)')
        connection.exec_driver_sql("INSERT INTO old_inventory VALUES ('old', '123.456')")
        op = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(script['op'], 'get_bind', lambda: connection)
        monkeypatch.setattr(script['op'], 'drop_table', op.drop_table)
        script['upgrade']()
        assert connection.exec_driver_sql('SELECT * FROM old_inventory').all() == [('old','123.456')]
        assert len(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all()) == 4
        script['downgrade']()
        assert sa.inspect(connection).get_table_names() == ['old_inventory']


def test_downgrade_refuses_retained_issuer_evidence(tmp_path, monkeypatch):
    script = migration(); engine = sa.create_engine(f'sqlite:///{tmp_path / "retained.db"}')
    with engine.begin() as connection:
        monkeypatch.setattr(script['op'], 'get_bind', lambda: connection)
        script['upgrade']()
        model = importlib.import_module('app.models.material_handover').HandoverIssuer
        connection.execute(model.__table__.insert().values(id='I',factory_id='huakang-c',name='test',kind='SUPPLIER',token_hash='a',expires_at='2030',active=1,revision=1,created_by='user',created_at='now'))
        with pytest.raises(RuntimeError, match='evidence is retained'):
            script['downgrade']()


def test_postgresql_offline_migration_generates_four_tables_and_evidence_triggers(monkeypatch):
    script = migration(); stream = StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': stream})
    monkeypatch.setattr(script['op'], 'get_bind', Operations(context).get_bind)
    script['upgrade']()
    sql = stream.getvalue()
    assert sql.count('CREATE TABLE material_handover_') == 4
    assert sql.count('CREATE TRIGGER') == 2
    assert 'BYTEA' in sql and 'FOR EACH ROW EXECUTE FUNCTION' in sql
