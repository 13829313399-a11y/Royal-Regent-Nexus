"""Isolated release rehearsal, never production activation or employee signoff."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import argparse
import json
import os
import shutil
import sys
from html import escape

from sqlalchemy.engine import make_url
from verify_cutting_p5b import source_state, execute_steps, junit_summary, digest

ROOT = Path(__file__).resolve().parents[2]


def validate_postgres(value):
    if not value:
        return False
    try:
        url = make_url(value)
        valid = not url.query and url.get_backend_name() == 'postgresql' and (
            url.database == 'cutting_test' or (url.database or '').startswith('cutting_test_'))
    except Exception:
        valid = False
    if not valid:
        # Never echo a URL that may contain credentials.
        raise ValueError('Use a dedicated PostgreSQL database named cutting_test or cutting_test_* without URL query parameters')
    return True


def outcome(steps, expected_steps, suites, unchanged, require_postgres, has_postgres):
    success = (len(steps) == expected_steps and all(s['exit_code'] == 0 for s in steps)
               and set(suites) == {s['step'] for s in steps}
               and all(s['tests'] > len(s['skipped']) and s['failed'] == 0 for s in suites.values()) and unchanged)
    skipped = [item for suite in suites.values() for item in suite['skipped']]
    # SQLite scope may omit only the explicitly named PostgreSQL cases. An
    # unrelated skip (especially an entire capacity group) is missing evidence.
    def postgres_skip(item):
        name = item.get('test', '')
        return ('[postgresql]' in name or 'test_cutting_postgres_concurrency::' in name
                or 'test_cutting_jp_migration::test_postgres_' in name)
    if any(not postgres_skip(item) for item in skipped):
        success = False
    if require_postgres and (not has_postgres or skipped):
        success = False
    return {'automated_status': 'passed' if success else 'failed',
            'skipped': skipped, 'release_ready': False,
            'postgresql': 'passed' if success and has_postgres and not skipped else 'not_accepted',
            'pending': ['real_employee_and_business_signoff', 'target_environment_capacity_and_recovery',
                        'native_excel_and_physical_print_signoff', 'explicit_production_release_approval']}


def read_suite(path):
    try:
        return junit_summary(path)
    except Exception:
        return {'tests':0, 'failed':1, 'skipped':[], 'evidence_error':'missing_or_invalid_junit'}


def redact_connection_logs(output, connection):
    if not connection:
        return
    url = make_url(connection)
    secrets = [connection, url.password] if url.password else [connection]
    for path in [*output.glob('*.log'), *output.glob('*.xml')]:
        content = path.read_text(encoding='utf-8')
        for secret in secrets:
            # JUnit escapes message attributes and captured traceback text.
            for encoded in {secret, escape(secret, quote=False), escape(secret),
                            escape(secret).replace('&#x27;', '&apos;')}:
                content = content.replace(encoded, '[redacted]')
        path.write_text(content, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-postgres', action='store_true')
    parser.add_argument('--sqlite-only', action='store_true',
                        help='Ignore PostgreSQL credentials; keep PostgreSQL tests explicitly skipped')
    args = parser.parse_args()
    if args.sqlite_only and args.require_postgres:
        parser.error('--sqlite-only cannot be combined with --require-postgres')
    connection = '' if args.sqlite_only else os.environ.get('CUTTING_TEST_POSTGRES_URL', '')
    try:
        has_pg = validate_postgres(connection)
    except ValueError as error:
        parser.error(str(error))
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    output = ROOT/'.tmp'/'cutting-p5c'/run
    output.mkdir(parents=True, exist_ok=False)
    initial = source_state()
    backend = ROOT/'backend'
    groups = {
        'baseline': ['test_cutting_p5c.py', 'test_cutting_p5c_runner.py', 'test_cutting_exports.py'],
        'concurrency': ['test_cutting_usage_concurrency.py', 'test_cutting_period_concurrency.py',
                        'test_cutting_settlement_concurrency.py', 'test_cutting_payments_concurrency.py',
                        'test_cutting_postgres_concurrency.py'],
        'migration': ['test_cutting_migration.py', 'test_cutting_jp_migration.py', 'test_migration_revision_identity.py'],
        'compatibility': ['test_unversioned_database_audit.py', 'test_database_takeover.py', 'test_huakang_b_jp.py'],
        'capacity': ['test_cutting_sqlite_capacity.py'],
    }
    steps = [(name, [sys.executable, '-m', 'pytest', *['tests/'+test for test in tests], '-q',
                    '-p', 'no:cacheprovider', '--basetemp='+str(output/(name+'-db')),
                    '--junitxml='+str(output/(name+'.xml'))], backend) for name, tests in groups.items()]
    env = dict(os.environ, DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false',
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8', CUTTING_P5C_EVIDENCE=str(output/'evidence'),
               CUTTING_TEST_POSTGRES_URL=connection, PYTEST_ADDOPTS='')
    report = {'run_id': run, 'source': initial, 'status': 'running', 'python': sys.version,
              'business_data_used': False, 'release_ready': False,
              'database_scope': 'sqlite_only' if args.sqlite_only else 'sqlite_and_optional_postgres'}
    path = output/'report.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(str(output), flush=True)
    report['steps'] = execute_steps(steps, output, env)
    redact_connection_logs(output, connection)
    report['suites'] = {name:read_suite(output/(name+'.xml')) for name in groups}
    report['source_after'] = source_state()
    report.update(outcome(report['steps'], len(steps), report['suites'],
                          initial == report['source_after'], args.require_postgres, has_pg))
    report['status'] = 'finished'
    report['files'] = {str(p.relative_to(output)): digest(p) for p in (output/'evidence').rglob('*') if p.is_file()}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # Only evidence/logs are packaged. Databases, credentials and environment dumps stay out.
    package = output/'archive'
    package.mkdir()
    for p in [path, *output.glob('*.xml'), *output.glob('*.log')]:
        shutil.copy2(p, package/p.name)
    if (output/'evidence').exists():
        shutil.copytree(output/'evidence', package/'evidence')
    shutil.make_archive(str(output/'p5c-evidence'), 'zip', package)
    print(json.dumps({k: report[k] for k in ('automated_status', 'postgresql', 'release_ready')}, ensure_ascii=False))
    return 0 if report['automated_status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
