"""The metadata experiment must never become an implicit production migration."""
import json
from pathlib import Path
import sqlite3
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_cutting_history_profile as profile


def fixture(tmp_path):
    folder = tmp_path / '.tmp/cutting-full-app/hourly-test'; folder.mkdir(parents=True)
    source = folder / 'cutting.db'
    with sqlite3.connect(source) as con:
        con.execute('CREATE TABLE auth_users(username TEXT)')
        con.executemany('INSERT INTO auth_users VALUES (?)', [(f'p5b-{i}',) for i in range(8)])
    manifest = folder / 'manifest.json'; manifest.write_text('{}', encoding='utf-8')
    (folder / 'fixture.json').write_text(json.dumps(dict(kind='cutting-full-app-synthetic', database=str(source.resolve()),
        manifest=str(manifest), manifest_sha256=profile.digest_file(manifest))), encoding='utf-8')
    (folder / 'report.json').write_text(json.dumps(dict(status='passed', seconds=3600, elapsed_seconds=3610,
        hour_duration_achieved=True)), encoding='utf-8')
    return source


def candidate(tmp_path):
    folder = tmp_path / '.tmp/cutting-history-profile/probe'; folder.mkdir(parents=True)
    path = folder / 'candidate.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE cutting_ops_period_events(id TEXT PRIMARY KEY,factory_id TEXT,month TEXT,version INTEGER,action TEXT,data TEXT,actor_id TEXT,actor_name TEXT,created_at TEXT,reason TEXT,UNIQUE(factory_id,version))')
        con.execute("CREATE TRIGGER protect_update BEFORE UPDATE ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT,'immutable'); END")
        con.execute("CREATE TRIGGER protect_delete BEFORE DELETE ON cutting_ops_period_events BEGIN SELECT RAISE(ABORT,'immutable'); END")
        for i in range(4):
            con.execute('INSERT INTO cutting_ops_period_events VALUES (?,?,?,?,?,?,?,?,?,?)',
                (str(i), 'huakang-c', '2026-11', i+1, 'save', json.dumps({'snapshot': 'x'*20000}), 'clerk', '合成文员', '2026-11-30', '合成核对'))
    return path


def test_only_completed_proven_synthetic_hour_is_accepted(tmp_path):
    path = fixture(tmp_path); checked = []
    assert profile.validate_source(path, root=tmp_path, validate_manifest=checked.append) == path
    assert checked == [path]
    proof = path.parent / 'report.json'; value = json.loads(proof.read_text()); value['seconds'] = 60
    proof.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Short or incomplete'):
        profile.validate_source(path, root=tmp_path, validate_manifest=checked.append)


def test_business_database_path_is_rejected_before_open(tmp_path):
    original = tmp_path / 'backend/data/original.db'; original.parent.mkdir(parents=True); original.write_bytes(b'original')
    for invoke in [lambda: profile.validate_source(original, root=tmp_path), lambda: profile.profile(original, 3, root=tmp_path)]:
        with pytest.raises(ValueError): invoke()
    assert original.read_bytes() == b'original'


@pytest.mark.parametrize('damage', ['manifest', 'identity', 'kind', 'database'])
def test_provenance_or_account_drift_is_rejected(tmp_path, damage):
    path = fixture(tmp_path)
    if damage == 'manifest': (path.parent / 'manifest.json').write_text('changed')
    elif damage == 'identity':
        with sqlite3.connect(path) as con: con.execute("UPDATE auth_users SET username='real-employee' WHERE username='p5b-0'")
    else:
        name = path.parent / 'fixture.json'; value = json.loads(name.read_text()); value[damage] = 'unexpected'; name.write_text(json.dumps(value))
    with pytest.raises(ValueError): profile.validate_source(path, root=tmp_path, validate_manifest=lambda _: None)


def test_candidate_matches_every_version_and_restores_schema_payloads(tmp_path):
    path = candidate(tmp_path)
    with sqlite3.connect(path) as con: before = profile.table_digest(con)
    result = profile.profile(path, 3, root=tmp_path)
    assert result['versions'] == 4 and result['schema_restored'] and result['captured_rows_equal']
    assert all(v['count'] == 3 for v in result['measurements'].values())
    assert any('COVERING INDEX' in row[-1] for row in result['candidate_plan'])
    with sqlite3.connect(path) as con:
        assert profile.table_digest(con) == before
        assert not con.execute('SELECT 1 FROM sqlite_master WHERE name=?', (profile.INDEX,)).fetchone()
        with pytest.raises(sqlite3.IntegrityError, match='immutable'): con.execute("DELETE FROM cutting_ops_period_events WHERE id='0'")


def test_metadata_reader_is_readonly_and_fences_exact_captured_identity(tmp_path):
    path = candidate(tmp_path); initial = profile.digest_file(path)
    prefixes = [('1', '2026-11', 2, 'save')]
    rows, _ = profile.metadata_read(path, prefixes, 'sqlite_autoindex_cutting_ops_period_events_2')
    assert [r[:4] for r in rows] == prefixes
    with pytest.raises(ValueError, match='identity'):
        profile.metadata_read(path, [('1', '2026-12', 2, 'save')], 'sqlite_autoindex_cutting_ops_period_events_2')
    assert profile.digest_file(path) == initial


def test_later_events_do_not_enter_an_already_captured_prefix(tmp_path):
    path = candidate(tmp_path)
    prefixes = [('1', '2026-11', 2, 'save')]
    with sqlite3.connect(path) as con:
        con.execute('INSERT INTO cutting_ops_period_events VALUES (?,?,?,?,?,?,?,?,?,?)',
            ('later', 'huakang-c', '2026-11', 5, 'lock', '{}', 'reviewer', '后到合成复核', '2026-12-01', '后到版本'))
    rows, _ = profile.metadata_read(path, prefixes, 'sqlite_autoindex_cutting_ops_period_events_2')
    assert len(rows) == 1 and rows[0][0] == '1'


@pytest.mark.parametrize('iterations', [True, 0, 2, 51])
def test_invalid_iterations_do_not_open_or_index_a_database(tmp_path, iterations):
    path = candidate(tmp_path); initial = profile.digest_file(path)
    with pytest.raises(ValueError, match='3–50'): profile.profile(path, iterations, root=tmp_path)
    assert profile.digest_file(path) == initial
