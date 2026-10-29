"""Profile metadata reads on a NEW copy of a passed synthetic hourly fixture.

The optional covering-index candidate exists only in this disposable experiment.
This is not an application migration, release, concurrent-write or capacity gate.
No business DB, external URL, credentials or arbitrary output path is accepted.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from statistics import median
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
INDEX = 'ix_cutting_period_header_probe'
TABLE = 'cutting_ops_period_events'
COLUMNS = 'id,factory_id,month,version,action,actor_id,actor_name,created_at,reason'
PREDICATE = ' WHERE id=? AND factory_id=? AND month=? AND version=? AND action=?'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest_file(path):
    h = sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def validate_source(path, *, root=ROOT, validate_manifest=None):
    path = Path(path).resolve()
    allowed = (root / '.tmp/cutting-full-app').resolve()
    if not path.is_relative_to(allowed) or path.name != 'cutting.db' or not path.is_file():
        raise ValueError('Only a passed isolated synthetic hour fixture is accepted')
    if not path.parent.name.startswith('hourly-'):
        raise ValueError('Expected a dedicated hour-run directory')
    report, fixture = read(path.parent / 'report.json'), read(path.parent / 'fixture.json')
    if (report.get('status') != 'passed' or report.get('seconds', 0) < 3600
            or report.get('elapsed_seconds', 0) < 3600 or report.get('hour_duration_achieved') is not True):
        raise ValueError('Short or incomplete runs are not valid profiling baselines')
    if fixture.get('kind') != 'cutting-full-app-synthetic' or fixture.get('database') != str(path):
        raise ValueError('Synthetic fixture provenance mismatch')
    if validate_manifest is None:
        from verify_cutting_full_app import validate_copy
        validate_manifest = lambda value: validate_copy(value)
    validate_manifest(path)
    manifest = Path(fixture['manifest']).resolve()
    if digest_file(manifest) != fixture['manifest_sha256']:
        raise ValueError('Frozen fixture manifest changed')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        names = con.execute('SELECT username FROM auth_users').fetchall()
        if len(names) != 8 or any(not name.startswith('p5b-') for name, in names):
            raise ValueError('Only the eight synthetic fixture users are accepted')
    return path


def distribution(values):
    import math
    values = sorted(values)
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('Expected finite nonnegative measurements')
    return dict(count=len(values), median=median(values), p95=values[math.ceil(len(values) * .95)-1], maximum=values[-1])


def table_digest(con):
    """Stream full immutable payloads; never copy them into the public report."""
    h = sha256()
    for row in con.execute('SELECT * FROM ' + TABLE + ' ORDER BY id'):
        encoded = json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()
        h.update(len(encoded).to_bytes(8, 'big')); h.update(encoded)
    return h.hexdigest()


def metadata_read(database, prefixes, index):
    if index not in {'sqlite_autoindex_cutting_ops_period_events_2', INDEX}:
        raise ValueError('Unknown experimental query plan')
    sql = 'SELECT actor_id,actor_name,created_at,reason FROM ' + TABLE + ' INDEXED BY ' + index + PREDICATE
    began = perf_counter(); rows = []
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=5)) as con:
        con.execute('PRAGMA query_only=ON').close()
        for identifier, month, version, action in prefixes:
            cursor = con.execute(sql, (identifier, 'huakang-c', month, version, action))
            try:
                row = cursor.fetchone()
            finally:
                cursor.close()
            if row is None:
                raise ValueError('Captured immutable identity no longer matches')
            rows.append((identifier, month, version, action, *row))
        assert not con.in_transaction
    return rows, perf_counter() - began


def profile(database, iterations, *, root=ROOT):
    if type(iterations) is not int or not 3 <= iterations <= 50:
        raise ValueError('Use 3–50 paired local iterations')
    database = Path(database).resolve()
    allowed = (root / '.tmp/cutting-history-profile').resolve()
    if not database.is_relative_to(allowed) or database.name != 'candidate.db' or not database.is_file():
        raise ValueError('Only the exclusive disposable profiling candidate may be indexed')
    with closing(sqlite3.connect(database)) as con:
        before = table_digest(con)
        schema = con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        if con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (INDEX,)).fetchone():
            raise ValueError('Candidate must start without the experimental index')
        old_columns = con.execute('PRAGMA index_info(sqlite_autoindex_cutting_ops_period_events_2)').fetchall()
        if [row[2] for row in old_columns] != ['factory_id', 'version']:
            raise ValueError('The frozen baseline unique index contract changed')
        prefixes = con.execute('SELECT id,month,version,action FROM ' + TABLE + " WHERE factory_id='huakang-c' ORDER BY version").fetchall()
        expected = con.execute('SELECT id,month,version,action,actor_id,actor_name,created_at,reason FROM ' + TABLE + " WHERE factory_id='huakang-c' ORDER BY version").fetchall()
        default_plan = con.execute('EXPLAIN QUERY PLAN SELECT actor_id,actor_name,created_at,reason FROM ' + TABLE + PREDICATE,
                                   (prefixes[0][0], 'huakang-c', *prefixes[0][1:])).fetchall()
        began = perf_counter()
        con.execute('CREATE INDEX ' + INDEX + ' ON ' + TABLE + ' (' + COLUMNS + ')'); con.commit()
        index_seconds = perf_counter() - began
        candidate_plan = con.execute('EXPLAIN QUERY PLAN SELECT actor_id,actor_name,created_at,reason FROM ' + TABLE +
            ' INDEXED BY ' + INDEX + PREDICATE, (prefixes[0][0], 'huakang-c', *prefixes[0][1:])).fetchall()
        if not any('COVERING INDEX ' + INDEX in row[-1] for row in candidate_plan):
            raise ValueError('Candidate is not a covering metadata query')
    groups = {name: [] for name in ['baseline_unique', 'candidate_covering']}
    for iteration in range(iterations):
        order = list(groups) if iteration % 2 == 0 else list(reversed(groups))
        for name in order:
            rows, seconds = metadata_read(database, prefixes, INDEX if name == 'candidate_covering' else 'sqlite_autoindex_cutting_ops_period_events_2')
            assert rows == expected, 'Per-version metadata changed'
            groups[name].append(seconds)
        print(f'History pair {iteration+1}/{iterations}; {len(prefixes)} captured versions matched', flush=True)
    with closing(sqlite3.connect(database)) as con:
        assert table_digest(con) == before, 'Immutable event payloads changed'
        assert con.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        con.execute('DROP INDEX ' + INDEX); con.commit()
        assert con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall() == schema
    return dict(versions=len(prefixes), captured_rows_equal=True, immutable_payloads_unchanged=True,
                schema_restored=True, integrity='ok', foreign_key_errors=0,
                default_plan=default_plan, candidate_plan=candidate_plan, index_build_seconds=index_seconds,
                measurements={k: distribution(v) for k, v in groups.items()}, paired_seconds=groups,
                scope='Warm local paired metadata-only reads; explicit candidate index, not cold disk, HTTP, mixed writes or production SLA')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', required=True)
    parser.add_argument('--iterations', type=int, default=10)
    args = parser.parse_args()
    if not 3 <= args.iterations <= 50:
        parser.error('Use 3–50 paired iterations')
    seed = validate_source(args.seed)
    folder = ROOT / '.tmp/cutting-history-profile' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / 'candidate.db'
    original = ROOT / 'backend/data/royal_regent_nexus.db'
    initial, source_hash = digest_file(original), digest_file(seed)
    report = dict(status='failed', production_capacity_accepted=False, release_ready=False, source_database_unchanged=False)
    print(str(folder), flush=True)
    try:
        with closing(sqlite3.connect(seed.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
        report.update(profile(target, args.iterations))
        assert digest_file(seed) == source_hash and digest_file(original) == initial
        report.update(status='passed', source_database_unchanged=True, original_database_unchanged=True,
                      candidate_index_retained=False, application_migration_applied=False)
    finally:
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
