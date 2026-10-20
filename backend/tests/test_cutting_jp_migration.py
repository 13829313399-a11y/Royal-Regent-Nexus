"""Rehearse historical 0163 meanings without touching the configured database."""
from pathlib import Path
from hashlib import sha256
import ast
import os
import runpy
import sqlite3
import subprocess
import sys

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND/'alembic/versions'
REPAIR = VERSIONS/'20261017_0167_reconcile_cutting_jp_collision.py'
JP = BACKEND/'alembic/legacy/20261015_0163_huakang_b_jp_intake.py'
CUTTING = VERSIONS/'20261015_0163_cutting_internal_periods.py'


def migrate(path, revision='head', success=True):
    env = dict(os.environ, DATABASE_URL='sqlite:///'+path.as_posix(), SEED_DEFAULT_ACCOUNTS='false',
               CUTTING_OPS_ENABLED='false', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    result = subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=BACKEND,env=env,
                            capture_output=True,text=True,encoding='utf-8',timeout=180)
    assert (result.returncode == 0) == success, result.stdout+result.stderr
    return result


@pytest.fixture(scope='module')
def base_database(tmp_path_factory):
    path = tmp_path_factory.mktemp('collision-base')/'base.db'
    migrate(path,'20261015_0162')
    return path


def clone(base, tmp_path):
    target = tmp_path/'legacy.db'
    with sqlite3.connect(base) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    return target


def run_ddl(conn, path):
    module = runpy.run_path(str(path))
    with Operations.context(MigrationContext.configure(conn)):
        module['upgrade']()


def legacy(path, groups, successor=False):
    engine = sa.create_engine('sqlite:///'+path.as_posix())
    with engine.begin() as conn:
        if 'cutting' in groups:
            run_ddl(conn,CUTTING)
            conn.execute(sa.text("INSERT INTO cutting_ops_period_events VALUES ('frozen','huakang-c','2026-09',1,'lock',:data,'tester','合成会计','2026-10-01','保留原快照')"), {'data':'{"HKD":"123.45","source":"00001"}'})
        if 'jp' in groups:
            run_ddl(conn,JP)
            conn.execute(sa.text("INSERT INTO order_ledger_sources VALUES ('jp-source','huakang-b','synthetic','hash','原附件.xlsx','jp',:data)"),{'data':b'\x00\xff-original'})
            conn.execute(sa.text("INSERT INTO jp_intake_references VALUES ('huakang-b','item','jp-source',1,'tester','2026-10-01','{}')"))
            conn.execute(sa.text("INSERT INTO jp_intake_reference_events VALUES ('jp-reference','huakang-b','item',1,'jp-source','tester','2026-10-01','{}')"))
            conn.execute(sa.text("INSERT INTO jp_intake_counters VALUES ('huakang-b',123)"))
            conn.execute(sa.text("INSERT INTO jp_intake_exports VALUES ('export','huakang-b','request','tester','2026-10-01',120,123,'{}',:data)"),{'data':b'\x00\xff-snapshot'})
            conn.execute(sa.text("INSERT INTO jp_intake_export_identities VALUES ('huakang-b','0000123','export')"))
        if successor:
            for name in ('20261016_0163_carton_quantity_rules.py','20261016_0165_cutting_subcontract_settlement.py','20261016_0166_cutting_subcontract_payments.py'):
                run_ddl(conn,VERSIONS/name)
        # Reproduce historical version evidence only inside disposable fixtures.
        conn.execute(sa.text('UPDATE alembic_version SET version_num=:version'),{'version':'20261016_0166' if successor else '20261015_0163'})
    engine.dispose()


def snapshot(path):
    with sqlite3.connect(path) as conn:
        tables = conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name").fetchall()
        return {name:(sql,conn.execute('SELECT * FROM "'+name+'"').fetchall()) for name,sql in tables}


def version_snapshot(path):
    with sqlite3.connect(path) as conn:
        if not conn.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone():
            return None
        return conn.execute('SELECT version_num FROM alembic_version ORDER BY version_num').fetchall()


def test_unique_revision_graph_and_frozen_archive():
    identifiers = []
    for path in VERSIONS.glob('*.py'):
        for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0] if isinstance(node, ast.Assign) else None
            if isinstance(target, ast.Name) and target.id=='revision':
                identifiers.append(ast.literal_eval(node.value))
    assert len(identifiers) == len(set(identifiers))
    scripts=ScriptDirectory(str(BACKEND/'alembic'))
    assert scripts.get_heads() == ['20261020_0171']
    assert list(scripts.walk_revisions())
    assert runpy.run_path(str(JP))['revision'] == '20261015_0163'
    assert sha256(JP.read_bytes().replace(b'\r\n',b'\n')).hexdigest() == 'dd653505555f3fe0847974ee14f379e41dc78a728bd2eeffbf26c63b3ecce47e'


@pytest.mark.parametrize('groups,successor', [(['cutting'],False),(['jp'],False),(['cutting','jp'],False),
    (['cutting'],True),(['jp'],True),(['cutting','jp'],True)])
def test_historical_variants_preserve_evidence_and_repeat_safely(base_database,tmp_path,groups,successor):
    path=clone(base_database,tmp_path);legacy(path,groups,successor)
    before=snapshot(path)
    migrate(path)
    after=snapshot(path)
    for name,value in before.items():
        if name=='carton_order_lines' and not successor:
            assert [row[:-1] for row in after[name][1]] == value[1]
        else:
            assert after[name] == value, name
    assert 'cutting_ops_period_events' in after and 'jp_intake_exports' in after
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT version_num FROM alembic_version').fetchall()==[('20261020_0171',)]
        assert conn.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        for table in ('cutting_ops_period_events','jp_intake_reference_events','jp_intake_exports','jp_intake_export_identities'):
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute('DELETE FROM "'+table+'"') if after[table][1] else conn.execute('INSERT INTO "'+table+'" DEFAULT VALUES')
    migrate(path)
    assert snapshot(path)==after


@pytest.mark.parametrize('damage',['partial','column','missing_trigger','extra_trigger','orphan','no_groups','unknown_version','unversioned','invalid_heads'])
def test_damage_is_rejected_before_successor_ddl(base_database,tmp_path,damage):
    path=clone(base_database,tmp_path);legacy(path,[] if damage=='no_groups' else ['cutting','jp'] if damage=='partial' else ['cutting'])
    with sqlite3.connect(path) as conn:
        if damage=='partial': conn.execute('DROP TABLE jp_intake_counters')
        if damage=='column': conn.execute('ALTER TABLE cutting_ops_period_events ADD COLUMN unexpected TEXT')
        if damage=='missing_trigger': conn.execute('DROP TRIGGER cutting_period_no_update')
        if damage=='extra_trigger': conn.execute("CREATE TRIGGER extra_guard BEFORE INSERT ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT,'wrong'); END")
        if damage=='orphan': conn.execute('CREATE INDEX ix_jp_intake_exports_created_at ON cutting_ops_period_events(created_at)')
        if damage=='unknown_version': conn.execute("UPDATE alembic_version SET version_num='unknown-history'")
        if damage=='unversioned': conn.execute('DROP TABLE alembic_version')
        if damage=='invalid_heads': conn.execute("INSERT INTO alembic_version VALUES ('20261016_0166')")
    before=snapshot(path)
    version_before=version_snapshot(path)
    result=migrate(path,success=False)
    assert '0163' in result.stderr
    assert snapshot(path)==before
    assert version_snapshot(path)==version_before
    with sqlite3.connect(path) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='cutting_ops_payment_events'").fetchall()


def test_failed_creation_rolls_back_and_can_retry(base_database,tmp_path):
    path=clone(base_database,tmp_path);legacy(path,['cutting'],True)
    before=snapshot(path)
    version_before=version_snapshot(path)
    engine=sa.create_engine('sqlite:///'+path.as_posix())
    module=runpy.run_path(str(REPAIR)); original=module['upgrade'].__globals__['_run']
    def fail_after_create(script,operation):
        original(script,operation)
        if operation.get_bind().engine is engine:
            raise RuntimeError('injected creation failure')
    module['upgrade'].__globals__['_run']=fail_after_create
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError,match='injected'):
                module['upgrade']()
    assert snapshot(path)==before
    assert version_snapshot(path)==version_before
    engine.dispose()
    migrate(path)


def test_published_cutting_and_carton_heads_join_without_replaying_either(base_database,tmp_path):
    path=clone(base_database,tmp_path);legacy(path,['cutting','jp'])
    engine=sa.create_engine('sqlite:///'+path.as_posix())
    with engine.begin() as conn:
        run_ddl(conn,VERSIONS/'20261016_0163_carton_quantity_rules.py')
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('20261016_0163')"))
    engine.dispose()
    before=snapshot(path)
    migrate(path)
    after=snapshot(path)
    assert all(after[name]==value for name,value in before.items())


def test_repair_downgrade_refuses():
    with pytest.raises(RuntimeError,match='cannot be deleted'):
        runpy.run_path(str(REPAIR))['downgrade']()


@pytest.mark.parametrize('sequence', [
    ['20261017_0167'], ['20261019_0167'],
    ['20261017_0167', '20261019_0167'], ['20261019_0167', '20261017_0167'],
])
def test_both_0167_paths_join_with_nonempty_evidence(base_database, tmp_path, sequence):
    path = clone(base_database, tmp_path)
    legacy(path, ['cutting', 'jp'], True)
    before = snapshot(path)
    for revision in sequence:
        migrate(path, revision)
        assert snapshot(path) == before
    assert {row[0] for row in version_snapshot(path)} == set(sequence)
    migrate(path)
    assert version_snapshot(path) == [('20261020_0171',)]
    after = snapshot(path)
    assert all(after[name] == value for name, value in before.items())
    migrate(path)
    assert snapshot(path) == after


@pytest.mark.parametrize('versions,groups', [
    (['20261017_0167'], ['jp']), (['20261019_0167'], ['cutting']),
    (['20261020_0168'], ['jp']), (['20261017_0167', '20261016_0166'], ['cutting', 'jp']),
])
def test_labeled_heads_require_their_complete_contract(base_database, tmp_path, versions, groups):
    path = clone(base_database, tmp_path)
    legacy(path, groups, True)
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM alembic_version')
        db.executemany('INSERT INTO alembic_version VALUES (?)', [(v,) for v in versions])
    before, heads = snapshot(path), version_snapshot(path)
    migrate(path, success=False)
    assert snapshot(path) == before and version_snapshot(path) == heads


def test_main_jp_creation_failure_rolls_back_and_retries(base_database, tmp_path, monkeypatch):
    path = clone(base_database, tmp_path)
    legacy(path, ['cutting'], True)
    before, heads = snapshot(path), version_snapshot(path)
    engine = sa.create_engine('sqlite:///'+path.as_posix())
    module = runpy.run_path(str(VERSIONS/'20261019_0167_huakang_b_jp_intake.py'))
    original = Operations.create_table
    def fail_create(operation, name, *args, **kwargs):
        result = original(operation, name, *args, **kwargs)
        if name == 'jp_intake_reference_events':
            raise RuntimeError('injected main JP create failure')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Operations, 'create_table', fail_create)
        with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
            with pytest.raises(RuntimeError, match='injected'):
                module['upgrade']()
    engine.dispose()
    assert snapshot(path) == before and version_snapshot(path) == heads
    migrate(path)


# Optional dedicated-engine validation; no configured PostgreSQL is an explicit
# skip, never evidence that the PostgreSQL adoption/rollback path passed.
from test_cutting_postgres_concurrency import pg_engine


@pytest.mark.skipif(not os.getenv('CUTTING_TEST_POSTGRES_URL'), reason='Dedicated cutting_test PostgreSQL not configured')
@pytest.mark.parametrize('groups', [('cutting',),('jp',),('cutting','jp')])
def test_postgres_probe_adopts_or_completes_without_leaving_schema(pg_engine,groups):
    module=runpy.run_path(str(REPAIR))
    with pg_engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('20261016_0166')"))
        for group in groups:
            run_ddl(conn,CUTTING if group=='cutting' else JP)
        if 'cutting' in groups:
            conn.execute(sa.text("INSERT INTO cutting_ops_period_events VALUES ('frozen','huakang-c','2026-09',1,'lock',:data,'tester','合成会计','2026-10-01','保留原快照')"), {'data':'{"HKD":"123.45","source":"00001"}'})
        if 'jp' in groups:
            conn.execute(sa.text("INSERT INTO order_ledger_sources VALUES ('jp-source','huakang-b','synthetic','hash','原附件.xlsx','jp',:data)"), {'data':b'\x00\xff-original'})
            conn.execute(sa.text("INSERT INTO jp_intake_references VALUES ('huakang-b','item','jp-source',1,'tester','2026-10-01','{}')"))
            conn.execute(sa.text("INSERT INTO jp_intake_reference_events VALUES ('jp-reference','huakang-b','item',1,'jp-source','tester','2026-10-01','{}')"))
            conn.execute(sa.text("INSERT INTO jp_intake_counters VALUES ('huakang-b',123)"))
            conn.execute(sa.text("INSERT INTO jp_intake_exports VALUES ('export','huakang-b','request','tester','2026-10-01',120,123,'{}',:data)"), {'data':b'\x00\xff-snapshot'})
            conn.execute(sa.text("INSERT INTO jp_intake_export_identities VALUES ('huakang-b','0000123','export')"))
        before = pg_rows(conn)
        schemas_before=set(conn.scalars(sa.text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'cutting_0167_probe_%'")))
        with Operations.context(MigrationContext.configure(conn)):
            module['upgrade']()
        assert module['preflight'](conn)=={'cutting':False,'jp':False}
        assert set(conn.scalars(sa.text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'cutting_0167_probe_%'")))==schemas_before
        after = pg_rows(conn)
        assert all(after[name] == rows for name, rows in before.items())
        with Operations.context(MigrationContext.configure(conn)):
            module['upgrade']()
        assert pg_rows(conn) == after
        for table in ('cutting_ops_period_events', 'jp_intake_reference_events', 'jp_intake_exports', 'jp_intake_export_identities'):
            if after[table]:
                with pytest.raises(sa.exc.DBAPIError, match='append-only|immutable'):
                    with conn.begin_nested():
                        conn.execute(sa.text('DELETE FROM "'+table+'"'))
        assert pg_rows(conn) == after


def pg_rows(conn):
    return {name: conn.execute(sa.text('SELECT * FROM "'+name+'" ORDER BY 1')).all()
            for name in sa.inspect(conn).get_table_names()}


@pytest.mark.skipif(not os.getenv('CUTTING_TEST_POSTGRES_URL'), reason='Dedicated cutting_test PostgreSQL not configured')
@pytest.mark.parametrize('damage', ['missing_trigger', 'disabled_trigger', 'unvalidated_constraint'])
def test_postgres_damaged_contract_rejected_without_creating_missing_group(pg_engine, damage):
    module = runpy.run_path(str(REPAIR))
    with pg_engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('20261016_0166')"))
        run_ddl(conn, CUTTING)
        if damage == 'missing_trigger':
            conn.execute(sa.text('DROP TRIGGER cutting_period_immutable ON cutting_ops_period_events'))
        elif damage == 'disabled_trigger':
            conn.execute(sa.text('ALTER TABLE cutting_ops_period_events DISABLE TRIGGER cutting_period_immutable'))
        else:
            conn.execute(sa.text('ALTER TABLE cutting_ops_period_events ADD CONSTRAINT invalid_check CHECK (version >= 0) NOT VALID'))
        before = pg_rows(conn)
        schemas = set(sa.inspect(conn).get_schema_names())
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError, match='Unvalidated constraint' if damage == 'unvalidated_constraint' else '0163'):
                module['upgrade']()
        assert pg_rows(conn) == before
        assert set(sa.inspect(conn).get_schema_names()) == schemas
        assert 'jp_intake_exports' not in sa.inspect(conn).get_table_names()


@pytest.mark.skipif(not os.getenv('CUTTING_TEST_POSTGRES_URL'), reason='Dedicated cutting_test PostgreSQL not configured')
def test_postgres_failed_creation_rolls_back_then_retries(pg_engine):
    module = runpy.run_path(str(REPAIR))
    globals_ = module['upgrade'].__globals__
    original = globals_['_run']
    with pg_engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('20261016_0166')"))
        run_ddl(conn, CUTTING)
        before = pg_rows(conn)
        schema = conn.scalar(sa.text('SELECT current_schema()'))
        schemas = set(sa.inspect(conn).get_schema_names())
        def fail_after_create(script, operation):
            original(script, operation)
            if operation.get_bind().scalar(sa.text('SELECT current_schema()')) == schema:
                raise RuntimeError('injected PostgreSQL creation failure')
        globals_['_run'] = fail_after_create
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError, match='injected PostgreSQL'):
                module['upgrade']()
        assert pg_rows(conn) == before
        assert set(sa.inspect(conn).get_schema_names()) == schemas
        globals_['_run'] = original
        with Operations.context(MigrationContext.configure(conn)):
            module['upgrade']()
        assert module['preflight'](conn) == {'cutting':False, 'jp':False}
