"""Shared option migration merges only unambiguous data on disposable databases."""
from pathlib import Path
import runpy
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).parents[1] / 'alembic/versions/20261022_0174_indonesia_shared_options.py'


def setup_db():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    legacy = sa.Table('indonesia_material_options', metadata, sa.Column('id', sa.String, primary_key=True),
                      sa.Column('factory_id', sa.String), sa.Column('version', sa.Integer), sa.Column('data', sa.JSON))
    metadata.create_all(engine)
    return engine, legacy


def old(factory='huaxing', value='RMB', group='currency', **overrides):
    return dict(id=factory + value, factory_id=factory, version=1,
                data=dict(group=group, value=value, status='active', billing_basis='quantity', kg_per_unit='1') | overrides)


def test_shared_migration_preserves_legacy_data_and_seeds_defaults_once():
    module = runpy.run_path(str(PATH)); engine, legacy = setup_db()
    with engine.begin() as db:
        db.execute(legacy.insert(), [old(), old('huadeng', value='rmb')])
        before = list(db.execute(sa.select(legacy)).mappings())
        with Operations.context(MigrationContext.configure(db)):
            module['upgrade']()
            module['validate_shared_options_schema'](db)
            with pytest.raises(RuntimeError, match='拒绝'):
                module['downgrade']()
        assert list(db.execute(sa.select(legacy)).mappings()) == before
        rows = list(db.execute(sa.text('SELECT id, business_key, data FROM indonesia_material_shared_options')).mappings())
        assert len(rows) == 26 and len({row['business_key'] for row in rows}) == 26
    engine.dispose()


@pytest.mark.parametrize('change', [dict(status='inactive'), dict(deleted=True), dict(billing_basis='weight', kg_per_unit='2000')])
def test_single_factory_default_override_conflicts_before_ddl(change):
    module = runpy.run_path(str(PATH)); engine, legacy = setup_db()
    with engine.begin() as db:
        db.execute(legacy.insert(), old(value='TNE', group='customs_unit', billing_basis='weight', kg_per_unit='1000') | {'data': dict(group='customs_unit', value='TNE', status='active', billing_basis='weight', kg_per_unit='1000') | change})
        with Operations.context(MigrationContext.configure(db)):
            with pytest.raises(RuntimeError, match='冲突'):
                module['upgrade']()
        assert not sa.inspect(db).has_table('indonesia_material_shared_options')
        assert db.scalar(sa.select(sa.func.count()).select_from(legacy)) == 1
    engine.dispose()


def test_all_factory_agreed_conversion_and_new_custom_choices_can_merge():
    module = runpy.run_path(str(PATH)); engine, legacy = setup_db()
    with engine.begin() as db:
        db.execute(legacy.insert(), [old(factory=factory, value='TNE', group='customs_unit', billing_basis='weight', kg_per_unit='2000') for factory in module['FACTORIES']])
        db.execute(legacy.insert(), old(value='NEW-TON', group='customs_unit', billing_basis='weight', kg_per_unit='500'))
        with Operations.context(MigrationContext.configure(db)):
            module['upgrade']()
        assert db.scalar(sa.text('SELECT count(*) FROM indonesia_material_shared_options')) == 26
    engine.dispose()


def test_failed_shared_insert_rolls_back_table_and_can_retry(monkeypatch):
    module = runpy.run_path(str(PATH)); engine, legacy = setup_db()
    with engine.begin() as db:
        db.execute(legacy.insert(), old())
        original = db.execute
        with Operations.context(MigrationContext.configure(db)):
            with monkeypatch.context() as patch:
                def fail(statement, *args, **kwargs):
                    if getattr(getattr(statement, 'table', None), 'name', '') == 'indonesia_material_shared_options':
                        raise RuntimeError('synthetic insert failure')
                    return original(statement, *args, **kwargs)
                patch.setattr(db, 'execute', fail)
                with pytest.raises(RuntimeError, match='synthetic'):
                    module['upgrade']()
            assert not sa.inspect(db).has_table('indonesia_material_shared_options')
            module['upgrade']()
    engine.dispose()
