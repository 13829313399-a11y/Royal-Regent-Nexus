"""Audit an unversioned SQLite store using a read-only backup and real migrations.

Never stamps, repairs or opens the source writable. Reports differences against
a fresh complete migration chain, then rehearses upgrade on a separate copy.
Schema equivalence alone cannot prove that historical data conversions ran.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def quote(name):
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def readonly(path):
    with closing(sqlite3.connect(path.resolve(strict=True).as_uri() + '?mode=ro', uri=True)) as db:
        yield db


def backup(source, destination):
    # Exclusive reservation prevents accidentally replacing any existing file.
    with destination.open('xb'):
        pass
    with readonly(source) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)


def state(path):
    with readonly(path) as db:
        db.execute('BEGIN')
        schema = [tuple(row) for row in db.execute(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        tables = {}
        for kind, name, _, _ in schema:
            if kind != 'table':
                continue
            counts = Counter(hashlib.sha256(repr(row).encode()).hexdigest()
                             for row in db.execute('SELECT * FROM ' + quote(name)))
            tables[name] = {'rows': sum(counts.values()), 'digest': hashlib.sha256(
                json.dumps(sorted(counts.items())).encode()).hexdigest()}
        return {'schema': schema, 'tables': tables,
                'integrity': db.execute('PRAGMA integrity_check').fetchall(),
                'foreign_key_violations': db.execute('PRAGMA foreign_key_check').fetchall()}


def logical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def complete_jp_copy(path):
    """Only called on a newly created rehearsal copy; never adopts a version."""
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    repair = runpy.run_path(str(BACKEND / 'alembic/versions/20261017_0167_reconcile_cutting_jp_collision.py'))
    expected = repair['_sqlite_expected']()
    names = repair['GROUPS']['jp']
    frozen = repair['JP'].read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(frozen).hexdigest() != 'dd653505555f3fe0847974ee14f379e41dc78a728bd2eeffbf26c63b3ecce47e':
        raise RuntimeError('Frozen JP source changed; review required')
    engine = sa.create_engine(sa.URL.create('sqlite', database=str(path.resolve(strict=True))))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                tables = set(sa.inspect(connection).get_table_names())
                if 'alembic_version' in tables:
                    raise RuntimeError('Only unversioned rehearsal copies are supported')
                if connection.exec_driver_sql('PRAGMA integrity_check').all() != [('ok',)] or connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                    raise RuntimeError('Existing integrity damage')
                present = set(names) & tables
                if present and present != set(names):
                    raise RuntimeError('Partial JP group; no repair applied')
                if present:
                    for name in names:
                        if repair['_sqlite_contract'](connection, name) != expected[name]:
                            raise RuntimeError('JP schema drift: ' + name)
                else:
                    if 'order_ledger_sources' not in tables:
                        raise RuntimeError('JP source dependency is missing')
                    for name in names:
                        for _, obj, _ in expected[name]:
                            if connection.scalar(sa.text('SELECT count(*) FROM sqlite_master WHERE name=:name'), {'name':obj}):
                                raise RuntimeError('JP object name conflict: ' + obj)
                    repair['_run'](repair['JP'], Operations(MigrationContext.configure(connection)))
                if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                    raise RuntimeError('JP dependency check failed')
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        engine.dispose()


def rehearse_jp(baseline, output):
    candidate = output / 'jp-rehearsal.db'
    backup(baseline, candidate)
    before = state(candidate)
    complete_jp_copy(candidate)
    after = state(candidate)
    old_names = set(before['tables'])
    if (not all(after['tables'].get(t) == value for t, value in before['tables'].items())
            or [r for r in after['schema'] if r[2] in old_names] != before['schema']
            or 'alembic_version' in after['tables']):
        raise RuntimeError('JP rehearsal changed original data, schema or version history')
    new_names = set(after['tables']) - old_names
    if (not all(after['tables'][name]['rows'] == 0 for name in new_names)
            or after['integrity'] != [('ok',)] or after['foreign_key_violations']):
        raise RuntimeError('JP rehearsal added unexpected data or damaged integrity')
    complete_jp_copy(candidate)
    if state(candidate) != after:
        raise RuntimeError('Repeated JP rehearsal changed the database')
    return {'scope': 'JP five-table additive rehearsal ONLY; not full Alembic adoption',
            'original_tables_preserved': len(old_names),
            'original_rows_preserved': sum(v['rows'] for v in before['tables'].values()),
            'original_schema_preserved': True, 'new_empty_tables': sorted(new_names),
            'repeated_execution_unchanged': True, 'version_created': False,
            'integrity': 'ok', 'foreign_keys': 'ok'}


def contract(db, table):
    # Preserve all raw DDL (including CHECK constraints and index expressions),
    # alongside PRAGMAs. Do not treat matching column names as full equivalence.
    return {
        'columns': {r[1]: list(r[2:]) for r in db.execute('PRAGMA table_xinfo(' + quote(table) + ')')},
        'foreign_keys': sorted(tuple(r[2:]) for r in db.execute('PRAGMA foreign_key_list(' + quote(table) + ')')),
        'ddl': [tuple(r) for r in db.execute(
            'SELECT type,name,sql FROM sqlite_master WHERE tbl_name=? ORDER BY type,name', (table,))],
    }


def compare(actual, canonical):
    with readonly(actual) as a, readonly(canonical) as b:
        def names(db):
            return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    if not r[0].startswith('sqlite_') and r[0] != 'alembic_version'}
        left, right = names(a), names(b)
        differences = {}
        for name in sorted(left & right):
            x, y = contract(a, name), contract(b, name)
            changes = {k: {'actual': x[k], 'canonical': y[k]} for k in x if x[k] != y[k]}
            if changes:
                differences[name] = changes
        missing_columns, default_differences = [], []
        for table, changes in differences.items():
            if 'columns' not in changes:
                continue
            x, y = changes['columns']['actual'], changes['columns']['canonical']
            missing_columns += [table + '.' + name for name in sorted(y.keys() - x.keys())]
            default_differences += [table + '.' + name for name in sorted(x.keys() & y.keys())
                                    if x[name][2] != y[name][2]]
        missing_guards = {kind: [] for kind in ('index', 'trigger')}
        for kind in missing_guards:
            def objects(db):
                return {r[0]: r[1] for r in db.execute(
                    'SELECT name,tbl_name FROM sqlite_master WHERE type=? AND sql IS NOT NULL', (kind,))}
            x, y = objects(a), objects(b)
            missing_guards[kind] = sorted(name for name in y.keys() - x.keys() if y[name] in left)
        return {'actual_tables': len(left), 'canonical_tables': len(right),
                'missing_tables': sorted(right-left), 'extra_tables': sorted(left-right),
                'missing_columns': missing_columns, 'default_differences': default_differences,
                'missing_existing_table_objects': missing_guards, 'differences': differences}


def upgrade(path, log):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + path.as_posix(),
               SEED_DEFAULT_ACCOUNTS='false', CUTTING_OPS_ENABLED='false', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                            cwd=BACKEND, env=env, capture_output=True, text=True,
                            encoding='utf-8', timeout=240)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    return result


def source_fingerprints():
    files = [Path(__file__), *(BACKEND / 'alembic').rglob('*.py')]
    return {str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def expected_rejection(report):
    return (report['rehearsal_exit'] != 0 and report['rehearsal_unknown_history_rejected']
            and report['rehearsal_unchanged'] and report['baseline_backup_unchanged']
            and report['source_unchanged'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--rehearse-jp', action='store_true',
                        help='Additionally complete only the frozen JP group on a new copy; no version adoption')
    args = parser.parse_args()
    source = args.database.resolve(strict=True)
    fingerprints = source_fingerprints()
    output = ROOT / '.tmp/unversioned-baseline' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    print(output, flush=True)
    baseline = output / 'before.db'
    backup(source, baseline)
    before = state(baseline)
    if 'alembic_version' in before['tables']:
        raise RuntimeError('This audit is only for unversioned databases')
    if before['integrity'] != [('ok',)] or before['foreign_key_violations']:
        raise RuntimeError('Existing integrity/foreign-key damage; migration rehearsal refused')
    canonical = output / 'canonical.db'
    if upgrade(canonical, output / 'canonical.log').returncode:
        raise RuntimeError('Canonical migration failed; inspect the isolated log')
    with readonly(canonical) as db:
        head = [r[0] for r in db.execute('SELECT version_num FROM alembic_version')]
    comparison = compare(baseline, canonical)
    (output / 'schema-diff.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding='utf-8')
    rehearsal = output / 'rehearsal.db'
    backup(baseline, rehearsal)
    result = upgrade(rehearsal, output / 'rehearsal.log')
    after = state(rehearsal)
    report = {
        'source_read_only': True, 'source_modified_by_tool': False,
        'canonical_head': head, 'history_baseline_proven': False,
        'reason': 'Unversioned mixed schema requires explicit reconciliation of schema AND historical data conversions; no stamp is performed.',
        'rehearsal_exit': result.returncode,
        'rehearsal_unknown_history_rejected': 'Unknown 0163 collision history' in result.stderr,
        'original_tables': comparison['actual_tables'],
        'original_rows': sum(t['rows'] for t in before['tables'].values()),
        'rehearsal_unchanged': before == after, 'baseline_backup_unchanged': before == state(baseline),
        'before_digest': logical_digest(before), 'after_digest': logical_digest(after),
        'counts': {k: len(comparison[k]) for k in ('missing_tables', 'extra_tables', 'missing_columns', 'default_differences')},
        'missing_existing_table_objects': comparison['missing_existing_table_objects'],
        'source_files': fingerprints,
        'ready_for_full_upgrade': False,
    }
    if args.rehearse_jp:
        report['jp_additive_rehearsal'] = rehearse_jp(baseline, output)
    report['source_unchanged'] = fingerprints == source_fingerprints()
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'source_files'}, ensure_ascii=False))
    # An informative audit report is not an approval to migrate the real store.
    return 2 if expected_rejection(report) else 1


if __name__ == '__main__':
    raise SystemExit(main())
