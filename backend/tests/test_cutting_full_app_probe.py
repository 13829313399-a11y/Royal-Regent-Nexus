"""Safety/rollback of the synthetic full-application P5c harness."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_cutting_full_app as probe
import verify_cutting_lock_phases as phases


@pytest.fixture
def frozen(tmp_path,monkeypatch):
    control=tmp_path/'control';release=control/'releases/r1';source=release/'source';backend=source/'backend/app'
    backend.mkdir(parents=True);(backend/'main.py').write_text('# synthetic full app')
    runtime=backend/'cutting.py';runtime.write_text('# pinned runtime')
    m=dict(release=str(release),source=str(source),p5c_source_files={'backend/app/cutting.py':sha256(runtime.read_bytes()).hexdigest()})
    path=release/'manifest.json';path.write_text(json.dumps(m));(release/'environment.local.json').write_text(json.dumps({'DATABASE_URL':'sqlite:///do-not-use.db','SEED_DEFAULT_ACCOUNTS':'true'}))
    monkeypatch.setattr(probe,'CONTROL',control);monkeypatch.setattr(probe,'OUTPUT',tmp_path/'pressure')
    return path,m


def test_release_cannot_escape_or_silently_change_runtime(frozen,tmp_path):
    path,m=frozen;assert probe.release_manifest(path)==m
    with pytest.raises(ValueError):probe.release_manifest(tmp_path/'manifest.json')
    (Path(m['source'])/'backend/app/cutting.py').write_text('# changed')
    with pytest.raises(ValueError,match='fingerprint'):probe.release_manifest(path)


def test_environment_rejects_business_paths_and_replaces_connection_and_seed(frozen,tmp_path):
    _,m=frozen
    with pytest.raises(ValueError):probe.environment(m,tmp_path/'business.db')
    db=probe.OUTPUT/'run/cutting.db';env=probe.environment(m,db)
    assert env['DATABASE_URL']=='sqlite:///'+db.as_posix()
    assert env['SEED_DEFAULT_ACCOUNTS']=='false'
    assert env['CUTTING_TEST_POSTGRES_URL']=='' and env['PYTHONPATH']==''
    assert Path(env['ASSISTANT_STORAGE_DIR']).is_relative_to(db.parent)


def test_direct_serve_without_owned_identity_fails_before_importing_the_app(monkeypatch,tmp_path):
    monkeypatch.delenv('CUTTING_FULL_APP_INSTANCE',raising=False)
    monkeypatch.setenv('DATABASE_URL','sqlite:///do-not-open-business.db')
    with pytest.raises(ValueError,match='owned full-app process identity'):
        probe.serve(tmp_path/'business.db')


@pytest.mark.parametrize('count',['-1','41'])
def test_production_rotation_bounds_fail_before_opening_a_fixture(monkeypatch,count):
    monkeypatch.setattr(sys,'argv',['verify_cutting_full_app.py','--seed','must-not-open',
        '--production-write-orders',count])
    with pytest.raises(SystemExit) as error:probe.main()
    assert error.value.code==2


def test_validate_copy_refuses_missing_provenance_and_real_users(frozen):
    path,_=frozen;db=probe.OUTPUT/'run/cutting.db';db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as q:
        q.execute('CREATE TABLE auth_users(username TEXT)');q.execute("INSERT INTO auth_users VALUES ('real-employee')")
        q.execute('CREATE TABLE alembic_version(version_num TEXT)');q.execute("INSERT INTO alembic_version VALUES ('20261021_0172')")
    with pytest.raises(FileNotFoundError):probe.validate_copy(db)
    marker=dict(kind='cutting-full-app-synthetic',database=str(db.resolve()),manifest=str(path),manifest_sha256=sha256(path.read_bytes()).hexdigest())
    (db.parent/'fixture.json').write_text(json.dumps(marker))
    with pytest.raises(ValueError,match='eight synthetic'):probe.validate_copy(db)
    with sqlite3.connect(db) as q:
        q.execute('DELETE FROM auth_users');q.executemany('INSERT INTO auth_users VALUES (?)',[(f'p5b-{i}',) for i in range(8)])
    assert probe.validate_copy(db)[0]==db
    path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='manifest changed'):probe.validate_copy(db)


@pytest.mark.parametrize('broken',[False,True])
def test_fixture_import_preserves_values_normalizes_only_permission_ids_and_rolls_back(frozen,tmp_path,monkeypatch,broken):
    seed=tmp_path/'seed.db';target=probe.OUTPUT/'run/cutting.db';target.parent.mkdir(parents=True)
    for path in [seed,target]:
        with sqlite3.connect(path) as q:
            q.execute('CREATE TABLE auth_permissions(id TEXT PRIMARY KEY,code TEXT UNIQUE)')
            q.execute('CREATE TABLE auth_role_permissions(id TEXT PRIMARY KEY,permission_id TEXT REFERENCES auth_permissions(id))')
            q.execute('CREATE TABLE facts(id TEXT PRIMARY KEY,payload BLOB)')
            q.execute("CREATE TRIGGER immutable BEFORE DELETE ON facts BEGIN SELECT RAISE(ABORT,'immutable'); END")
    with sqlite3.connect(seed) as q:
        q.execute("INSERT INTO auth_permissions VALUES ('cutting_ops:read','cutting_ops:read')")
        q.execute("INSERT INTO auth_role_permissions VALUES ('role-read','cutting_ops:read')")
        q.execute('INSERT INTO facts VALUES (?,?)',('synthetic',b'\x00\xff'))
        if broken:q.execute('ALTER TABLE facts ADD COLUMN unexpected TEXT')
    with sqlite3.connect(target) as q:q.execute('INSERT INTO facts VALUES (?,?)',('before',b'original'))
    monkeypatch.setattr(phases,'seed_file',lambda value:Path(value))
    if broken:
        with pytest.raises(ValueError,match='column mismatch'):probe.install_fixture(seed,target)
    else:
        assert probe.install_fixture(seed,target)['facts']==1
    with sqlite3.connect(target) as q:
        assert q.execute('SELECT * FROM facts').fetchall()==([('before',b'original')] if broken else [('synthetic',b'\x00\xff')])
        assert q.execute("SELECT count(*) FROM sqlite_master WHERE name='immutable'").fetchone()[0]==1
        assert not q.execute('PRAGMA foreign_key_check').fetchall()
        if not broken:assert q.execute('SELECT permission_id FROM auth_role_permissions').fetchone()[0]=='perm-cutting_ops-read'
        with pytest.raises(sqlite3.IntegrityError):q.execute('DELETE FROM facts')
