"""Build and review a NEW SQLite takeover candidate; never replace the source.

The target earns its version by executing the whole migration chain. Original
rows (including empty tables) then replace target seeds in one checked import.
This does not prove historical data migrations ran against the old database.
No apply/stamp option, live server, external worker or production activation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

if __package__:
    from . import audit_unversioned_database as audit
else:
    import audit_unversioned_database as audit

ROOT, BACKEND = audit.ROOT, audit.BACKEND
NEW_COLUMNS = {
    'carton_orders': {'gross_weight_kg', 'net_weight_kg'},
    'carton_order_lines': {'gross_weight_kg', 'net_weight_kg', 'quantity_rule_json'},
}
DOMAINS = (
    ('identity', ('auth_', 'iam_', 'employee_', 'position_review')),
    ('carton_mark', ('carton_mark_',)),
    ('carton', ('carton_',)),
    ('cutting', ('cutting_ops_',)),
    ('fabric', ('fabric_',)),
    ('warehouse', ('warehouse_operations_',)),
    ('material_handover', ('material_handover_',)),
    ('orders', ('order_ledger_', 'customer_order_')),
    ('jp', ('jp_intake_',)),
    ('quotes', ('internal_quote', 'customer_price_', 'pricing_')),
    ('molding', ('molding_sample_',)),
    ('injection', ('injection_v3_',)),
    ('three_d', ('three_d_printing_',)),
    ('qc', ('qc_',)),
    ('spray_current', ('spray_ops_',)),
    ('spray_legacy', ('spray_',)),
    ('uv_current', ('uv_ops_',)),
    ('uv_legacy', ('uv_',)),
    ('collaborative_sheets', ('collaborative_sheet',)),
    ('collaboration', ('collab_', 'member_')),
    ('assistant', ('nexus_assistant_',)),
    ('documents', ('document_tool_',)),
    ('feedback', ('module_feedback_',)),
    ('work_center', ('work_center_',)),
    ('indonesia', ('indonesia_material_',)),
    ('raw_material', ('raw_materials',)),
    ('system', ('system_notifications',)),
)


def domain(table):
    for name, prefixes in DOMAINS:
        if table.startswith(prefixes):
            return name
    raise RuntimeError('Unclassified table requires explicit domain review: ' + table)


def tables(db):
    return sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if not r[0].startswith('sqlite_') and r[0] != 'alembic_version')


def columns(db, table):
    return {r[1]: tuple(r[2:]) for r in db.execute('PRAGMA table_xinfo(' + audit.quote(table) + ')')}


def table_options(db, table):
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
    # Ignore quoted names/literals/comments; a column or string named
    # AUTOINCREMENT must not masquerade as SQLite's allocation policy.
    sql = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|--[^\n]*|/\*.*?\*/", ' ', sql, flags=re.S)
    return bool(re.search(r'\bAUTOINCREMENT\b', sql, re.I)), bool(re.search(r'\bWITHOUT\s+ROWID\b', sql, re.I))


def rows_digest(db, table, fields):
    projection = [audit.quote(c) for c in fields] + ['typeof(' + audit.quote(c) + ')' for c in fields]
    sql = 'SELECT ' + ','.join(projection) + ' FROM ' + audit.quote(table)
    counts = Counter(hashlib.sha256(repr(r).encode()).hexdigest() for r in db.execute(sql))
    return {'rows': sum(counts.values()), 'digest': hashlib.sha256(
        json.dumps(sorted(counts.items())).encode()).hexdigest()}


def check_integrity(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Integrity or foreign-key verification failed')


def verify_original(source, target):
    result = {}
    for table in tables(source):
        fields = list(columns(source, table))
        before = rows_digest(source, table, fields)
        if before != rows_digest(target, table, fields):
            raise RuntimeError('Original values/types changed: ' + table)
        result[table] = before
    return result


def import_original(source_path, canonical_path, candidate_path):
    """Create exclusively, then import; all temporary guard removal is transactional."""
    audit.backup(canonical_path, candidate_path)
    canonical = audit.state(candidate_path)
    with audit.readonly(source_path) as src, closing(sqlite3.connect(candidate_path)) as dst:
        src.execute('BEGIN')
        if src.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchone():
            raise RuntimeError('Only the unversioned source profile is supported')
        check_integrity(src)
        original = tables(src)
        if set(original) - set(tables(dst)):
            raise RuntimeError('Unknown original tables; no import performed')
        for table in tables(dst):
            domain(table)
        additions = {}
        seed_decisions = {}
        for table in original:
            if table_options(src, table) != table_options(dst, table):
                raise RuntimeError('Autoincrement/rowid semantics differ: ' + table)
            a, b = columns(src, table), columns(dst, table)
            if a.keys() - b.keys():
                raise RuntimeError('Original columns missing in target: ' + table)
            extra = b.keys() - a.keys()
            if extra - NEW_COLUMNS.get(table, set()):
                raise RuntimeError('Unreviewed target columns: ' + table)
            if any(b[c][1] or b[c][2] is not None for c in extra):
                raise RuntimeError('New columns must be nullable without defaults: ' + table)
            if any((a[c][0], a[c][1], a[c][3:]) != (b[c][0], b[c][1], b[c][3:]) for c in a):
                raise RuntimeError('Type/nullability/key/hidden-column drift: ' + table)
            if extra:
                additions[table] = sorted(extra)
            seed_decisions[table] = {'decision': 'original_state_replaces_seed_including_empty',
                'seed': rows_digest(dst, table, list(b)), 'original': rows_digest(src, table, list(a))}
        triggers = dst.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
        source_sequences = src.execute("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'").fetchone()
        target_sequences = dst.execute("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'").fetchone()
        if source_sequences and not target_sequences:
            raise RuntimeError('Original autoincrement semantics missing in target')
        # Only the brand-new candidate loses guards briefly. Constraint and
        # old-row verification complete before COMMIT; any failure rolls back.
        dst.execute('PRAGMA foreign_keys=OFF')
        if dst.execute('PRAGMA foreign_keys').fetchone() != (0,):
            raise RuntimeError('Cannot suspend foreign keys in isolated candidate')
        dst.execute('BEGIN IMMEDIATE')
        try:
            for name, _ in triggers:
                dst.execute('DROP TRIGGER ' + audit.quote(name))
            for table in original:
                dst.execute('DELETE FROM ' + audit.quote(table))
            for table in original:
                fields = list(columns(src, table))
                names = ','.join(audit.quote(c) for c in fields)
                dst.executemany('INSERT INTO ' + audit.quote(table) + '(' + names + ') VALUES (' +
                                ','.join('?' for _ in fields) + ')', src.execute('SELECT ' + names + ' FROM ' + audit.quote(table)))
            if target_sequences:
                for table in original:
                    dst.execute('DELETE FROM sqlite_sequence WHERE name=?', (table,))
                if source_sequences:
                    sequences = src.execute('SELECT name,seq FROM sqlite_sequence').fetchall()
                    if any(name not in original for name, _ in sequences):
                        raise RuntimeError('Unclassified original sequence')
                    dst.executemany('INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)', sequences)
                    if sorted(sequences) != sorted(r for r in dst.execute('SELECT name,seq FROM sqlite_sequence') if r[0] in original):
                        raise RuntimeError('Original sequences changed')
            for _, sql in triggers:
                dst.execute(sql)
            preserved = verify_original(src, dst)
            check_integrity(dst)
            schema = [tuple(r) for r in dst.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
            if schema != canonical['schema']:
                raise RuntimeError('Canonical schema/guards were not completely restored')
            dst.commit()
        except Exception:
            dst.rollback()
            raise
        dst.execute('PRAGMA foreign_keys=ON')
        if dst.execute('PRAGMA foreign_keys').fetchone() != (1,):
            raise RuntimeError('Foreign keys not re-enabled')
        check_integrity(dst)
        new_seeds = {t: rows_digest(dst, t, list(columns(dst, t))) for t in tables(dst) if t not in original}
        with audit.readonly(canonical_path) as reference:
            for table, digest in new_seeds.items():
                if digest != rows_digest(reference, table, list(columns(reference, table))):
                    raise RuntimeError('New-module seed changed during import: ' + table)
            versions = dst.execute('SELECT version_num FROM alembic_version ORDER BY version_num').fetchall()
            if versions != reference.execute('SELECT version_num FROM alembic_version ORDER BY version_num').fetchall():
                raise RuntimeError('Migration evidence changed')
    groups = defaultdict(lambda: {'tables': [], 'original_tables': 0, 'original_rows': 0, 'new_tables': 0, 'new_seed_rows': 0})
    for table in sorted(set(preserved) | set(new_seeds)):
        item = groups[domain(table)]
        item['tables'].append(table)
        if table in preserved:
            item['original_tables'] += 1
            item['original_rows'] += preserved[table]['rows']
        else:
            item['new_tables'] += 1
            item['new_seed_rows'] += new_seeds[table]['rows']
    return {'preserved': preserved, 'module_review': dict(groups), 'seed_decisions': seed_decisions,
            'new_tables': new_seeds, 'nullable_additions': additions, 'canonical_guards_restored': True,
            'version_from_real_migrations': versions, 'full_takeover_approved': False}


def changed_tables(before, after):
    return {name: {'before': before['tables'].get(name), 'after': after['tables'].get(name)}
            for name in sorted(before['tables'].keys() | after['tables'].keys())
            if before['tables'].get(name) != after['tables'].get(name)}


def initialization_passed(passes):
    return (len(passes) == 2 and all(
        p['exit_code'] == 0 and not p['changed_tables'] and not p['schema_changed']
        and not p['identity_changed'] and p['integrity'] == [('ok',)]
        and not p['foreign_key_violations'] for p in passes))


def application_probe(original, candidate, output):
    env = dict(os.environ, DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false',
               PYTHONUTF8='1', CUTTING_PERIOD_ADMIN_ACCEPTANCE='false', AUTHZ_MODE='enforce')
    result = subprocess.run([sys.executable, str(BACKEND / 'tools/takeover_read_probe.py'),
                             str(original), str(candidate), str(output / 'application.json')],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
    (output / 'application.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Read-only application probe failed; see application.log')
    return json.loads((output / 'application.json').read_text(encoding='utf-8'))


def initialize_copy(path, log):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + path.as_posix(), SEED_DEFAULT_ACCOUNTS='false',
               CUTTING_OPS_ENABLED='true', CUTTING_PERIOD_ADMIN_ACCEPTANCE='false',
               AUTHZ_MODE='enforce', AUTHZ_WRITES_ENABLED='false', IAM_IDENTITY_WRITES_ENABLED='false',
               IAM_IDENTITY_SCHEDULING_ENABLED='false', PYTHONUTF8='1',
               SPRAY_OPS_ENABLED='false', UV_OPS_ENABLED='false', COLLABORATION_ENABLED='false',
               ASSISTANT_ENABLED='false', THREE_D_CONNECTOR_ENABLED='false')
    for key in ('THREE_D_ASSET_DIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        env[key] = str(path.parent / 'probe-assets' / key.lower())
    # init_db only; never launch lifespan workers, ports, connectors or login.
    code = '''
import sys, socket
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings
if Path(make_url(settings.database_url).database).resolve() != Path(sys.argv[1]).resolve():
    raise RuntimeError('Probe database path mismatch')
def no_network(*args, **kwargs):
    raise RuntimeError('Network disabled during candidate initialization')
socket.create_connection = socket.socket.connect = socket.socket.connect_ex = no_network
from app.db import init_db, engine
try:
    init_db()
finally:
    engine.dispose()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path)],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    return result.returncode


def fingerprints():
    files = {*BACKEND.joinpath('app').rglob('*.py'), *BACKEND.joinpath('alembic').rglob('*.py'),
             Path(__file__), Path(audit.__file__), BACKEND / 'tools/takeover_read_probe.py'}
    return {str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    args = parser.parse_args()
    source = args.database.resolve(strict=True)
    output = ROOT / '.tmp/takeover-candidate' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    print(output, flush=True)
    start = fingerprints()
    backup = output / 'before.db'
    audit.backup(source, backup)
    before = audit.state(backup)
    canonical = output / 'canonical.db'
    if audit.upgrade(canonical, output / 'canonical.log').returncode:
        raise RuntimeError('Canonical migration failed')
    candidate = output / 'candidate.db'
    report = import_original(backup, canonical, candidate)
    report.update(source_opened_read_only=True, source_modified=False, source_files=start,
                  external_workers_started=False, release_ready=False)
    probe = output / 'initialization-probe.db'
    audit.backup(candidate, probe)
    first_before = audit.state(probe)
    passes = []
    for i in (1, 2):
        code = initialize_copy(probe, output / f'init-{i}.log')
        after = audit.state(probe)
        changes = changed_tables(first_before, after)
        passes.append({'pass': i, 'exit_code': code, 'changed_tables': changes,
                       'schema_changed': first_before['schema'] != after['schema'],
                       'identity_changed': [t for t in changes if domain(t) == 'identity'],
                       'integrity': after['integrity'], 'foreign_key_violations': after['foreign_key_violations']})
        first_before = after
        if code:
            break
    report['initialization'] = passes
    report['initialization_unchanged'] = initialization_passed(passes)
    report['application'] = application_probe(backup, candidate, output)
    upgrade_before = audit.state(candidate)
    report['repeat_upgrade_exit'] = audit.upgrade(candidate, output / 'repeat-upgrade.log').returncode
    report['repeat_upgrade_unchanged'] = audit.state(candidate) == upgrade_before
    report['backup_unchanged'] = audit.state(backup) == before
    report['source_code_unchanged'] = start == fingerprints()
    # Verify restoration of the pre-initialization candidate separately.
    restored = output / 'restored.db'
    audit.backup(candidate, restored)
    report['restore_equal'] = audit.state(restored) == audit.state(candidate)
    report['pending'] = ['per_domain_historical_data_semantics', 'new_module_seed_approval',
                         'real_business_and_employee_acceptance', 'explicit_live_cutover']
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'original_tables': len(report['preserved']),
                      'original_rows': sum(v['rows'] for v in report['preserved'].values()),
                      'module_groups': len(report['module_review']), 'initialization': passes,
                      'release_ready': False}, ensure_ascii=False))
    return 0 if (report['backup_unchanged'] and report['source_code_unchanged'] and report['restore_equal']
                 and report['initialization_unchanged'] and report['repeat_upgrade_exit'] == 0
                 and report['repeat_upgrade_unchanged']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
