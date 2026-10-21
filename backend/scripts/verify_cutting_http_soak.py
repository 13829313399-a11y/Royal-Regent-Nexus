"""Run a bounded synthetic SQLite/HTTP soak, never a business service or DB."""
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
from datetime import datetime, timezone
from uuid import uuid4

from verify_cutting_p5b import source_state, execute_steps, junit_summary

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['100', '500'], default='500')
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--workload', choices=['paced', 'burst'], default='paced')
    parser.add_argument('--expanded-finance', action='store_true',
                        help='100 production / 20 financial chains on profile 500, including usage and payment writes')
    args = parser.parse_args()
    if not 30 <= args.seconds <= 600:
        parser.error('Use 30–600 seconds; default is ten minutes')
    orders, chains, workers = (100, 10, 5) if args.profile == '100' else (500, 50, 10)
    if args.expanded_finance:
        chains, finance = (20, 5) if args.profile == '100' else (100, 20)
    output = ROOT/'.tmp'/'cutting-http-soak'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    initial = source_state()
    env = dict(os.environ, DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false',
        CUTTING_TEST_POSTGRES_URL='', PYTEST_ADDOPTS='', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
        CUTTING_P5C_EVIDENCE=str(output/'evidence'), CUTTING_SOAK_ORDERS=str(orders),
        CUTTING_SOAK_CHAINS=str(chains), CUTTING_SOAK_WORKERS=str(workers), CUTTING_SOAK_SECONDS=str(args.seconds),
        CUTTING_SOAK_WORKLOAD=args.workload)
    target = 'tests/test_cutting_http_soak.py::test_expanded_production_chain_mixed_http'
    if args.expanded_finance:
        target = 'tests/test_cutting_financial_soak.py::test_expanded_financial_mixed_http'
        env.update({f'CUTTING_FINANCE_SOAK_{key}':str(value) for key,value in dict(
            ORDERS=orders,CHAINS=chains,FINANCE_CHAINS=finance,WORKERS=workers,SECONDS=args.seconds,WORKLOAD=args.workload).items()})
    steps = [('soak', [sys.executable, '-m', 'pytest', target, '-q', '-s',
              '-p', 'no:cacheprovider', '--basetemp='+str(output/'databases'),
              '--junitxml='+str(output/'soak.xml')], ROOT/'backend')]
    print(str(output), flush=True)
    def bounded_invoke(command, **kwargs):
        kwargs['timeout'] = 3600  # API-created chain setup plus bounded ten-minute soak
        previous = None
        if sys.platform == 'win32':
            import ctypes
            set_state = ctypes.windll.kernel32.SetThreadExecutionState
            previous = set_state(0x80000001)
            if not previous:
                raise RuntimeError('Cannot prevent idle sleep during isolated setup and soak')
        try:
            return subprocess.run(command, **kwargs)
        finally:
            if previous is not None:
                set_state(previous)
    results = execute_steps(steps, output, env, invoke=bounded_invoke)
    final = source_state()
    try:
        suite = junit_summary(output/'soak.xml')
        passed = (len(results) == 1 and results[0]['exit_code'] == 0 and suite['tests'] == 1
                  and not suite['failed'] and not suite['skipped'] and initial == final)
    except Exception:
        suite, passed = {}, False
    report = dict(source=initial, source_after=final, steps=results, suite=suite,
                  automated_status='passed' if passed else 'failed', release_ready=False,
                  production_capacity_accepted=False, original_database_accessed=False)
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding='utf-8')
    print(json.dumps({'automated_status':report['automated_status'], 'release_ready':False}),flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
