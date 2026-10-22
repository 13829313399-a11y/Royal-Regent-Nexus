"""Additive option migration and SQLite failure recovery on disposable databases."""
from pathlib import Path
import runpy
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).parents[1] / 'alembic/versions/20261022_0173_indonesia_options.py'


def test_failed_option_index_leaves_no_half_table_and_upgrade_can_retry(tmp_path, monkeypatch):
    module = runpy.run_path(str(PATH))
    engine = sa.create_engine('sqlite:///' + (tmp_path / 'options.db').as_posix())
    with engine.begin() as db:
        db.execute(sa.text('CREATE TABLE preserved (id INTEGER PRIMARY KEY, value TEXT)'))
        db.execute(sa.text("INSERT INTO preserved VALUES (1, 'original')"))
    with engine.connect() as db:
        with Operations.context(MigrationContext.configure(db)):
            with monkeypatch.context() as patch:
                def fail_index(*args, **kwargs):
                    raise RuntimeError('synthetic index failure')
                patch.setattr(module['op'], 'create_index', fail_index)
                with pytest.raises(RuntimeError, match='synthetic index failure'):
                    module['upgrade']()
            assert not sa.inspect(db).has_table('indonesia_material_options')
            assert db.execute(sa.text('SELECT value FROM preserved')).scalar_one() == 'original'
            module['upgrade']()
            module['validate_options_schema'](db)
            assert db.execute(sa.text('SELECT count(*) FROM indonesia_material_options')).scalar_one() == 0
    engine.dispose()


def test_option_downgrade_refuses_maintained_values_and_schema_drift(tmp_path):
    module = runpy.run_path(str(PATH))
    engine = sa.create_engine('sqlite:///' + (tmp_path / 'kept.db').as_posix())
    with engine.begin() as db:
        with Operations.context(MigrationContext.configure(db)):
            module['upgrade']()
            db.execute(sa.text("INSERT INTO indonesia_material_options VALUES ('id','huaxing','key',1,'{}','now')"))
            with pytest.raises(RuntimeError, match='已有维护记录'):
                module['downgrade']()
            assert db.execute(sa.text('SELECT count(*) FROM indonesia_material_options')).scalar_one() == 1
    engine.dispose()
