"""Hour-scale repeated transitions/exports on a NEW full-app synthetic copy only.

No business database or external service URL is accepted. The source is a proven
synthetic 500/100/20 seed; the full application's startup and diagnostics remain
those of the fingerprinted staged acceptance release.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

from verify_cutting_full_app import (ROOT, CONTROL, OUTPUT, read, release_manifest,
    environment, install_fixture, full_http)
from verify_cutting_p5b import source_state
from verify_cutting_lock_phases import seed_file
from cutting_probe_io import write_snapshot


def validate_duration(seconds):
    if type(seconds) is not int or not 10 <= seconds <= 3600:
        raise ValueError('Use 10–3600 seconds; only >=3600 seconds qualifies as an hour run')
    return seconds


def run_cycles(url, database, seconds, report, *, invoke=None, clock=perf_counter, checkpoint=None):
    """Never reuse a transitioned line or hide a failed/partial cycle."""
    validate_duration(seconds)
    if invoke is None:
        from cutting_workflow_mix import run_workflows
        invoke=run_workflows
    started=clock();report['cycles']=[]
    while clock()-started < seconds or len(report['cycles']) < 2:
        index=len(report['cycles'])
        if index>=80:
            raise ValueError('Reserved fresh-line range exhausted; no stale-plan reuse is allowed')
        cycle=dict(index=index,line_id=f'http-capacity-{20+index}',status='failed')
        report['cycles'].append(cycle)
        if checkpoint:checkpoint()
        invoke(url,database,cycle,line=cycle['line_id'],chains=100,concentrated_exports=True,
               minimum_seconds=min(60,seconds))
        assert cycle['status']=='passed'
        assert cycle['finance']['same_balance_protected'] and cycle['materials']['receipt_race_protected']
        assert cycle['materials']['return_correction_preserved'] and cycle['period']['locked_write_rejected']
        assert cycle['period']['historical_snapshot_unchanged']
        assert len(cycle['reader_cycles'])==3 and all(cycle['reader_cycles'])
        report['elapsed_seconds']=clock()-started
        if checkpoint:checkpoint()
        print(f"Repeated transitions: {index+1} cycles; {report['elapsed_seconds']:.1f}s",flush=True)
    report['elapsed_seconds']=clock()-started
    assert report['elapsed_seconds']>=seconds
    report['hour_duration_achieved']=seconds>=3600 and report['elapsed_seconds']>=3600


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',required=True)
    parser.add_argument('--seconds',type=int,default=3600)
    parser.add_argument('--manifest',type=Path,help='Optional fingerprinted release under the existing acceptance releases directory; never changes the active release')
    args=parser.parse_args();validate_duration(args.seconds)
    # Fence configuration before importing any application/testing code.
    os.environ.update(DATABASE_URL='sqlite://',SEED_DEFAULT_ACCOUNTS='false',CUTTING_TEST_POSTGRES_URL='')
    sys.path[:0]=[str(ROOT/'backend/tests'),str(ROOT/'backend')]
    from test_cutting_http_soak import awake_system
    from cutting_mix_audit import segmented_diagnostics, distribution
    seed=seed_file(args.seed)
    manifest=args.manifest or Path(read(CONTROL/'staged.json')['release'])/'manifest.json'
    m=release_manifest(manifest)
    folder=OUTPUT/('hourly-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False);database=folder/'cutting.db'
    initial=source_state();seed_hash=sha256(seed.read_bytes()).hexdigest()
    report=dict(status='failed',seconds=args.seconds,release=m['acceptance_release'],source=initial,
        release_ready=False,production_capacity_accepted=False,hour_duration_achieved=False,
        scope='Full application; 500 dispatch/100 production/20 financial chains; repeated receipt/return/month-lock/payment races with three export/read workers and ten logged-in sessions per cycle, not ten concurrent writers; local hardware and synthetic business clock')
    def checkpoint():
        if not write_snapshot(folder/'progress.json',report):
            report['progress_sharing_retries']=report.get('progress_sharing_retries',0)+1
    print(str(folder),flush=True)
    try:
        with (folder/'migration.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=Path(m['source'])/'backend',
                env=environment(m,database),stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        report['imported_tables']=install_fixture(seed,database)
        (folder/'fixture.json').write_text(json.dumps(dict(kind='cutting-full-app-synthetic',database=str(database.resolve()),
            manifest=str(manifest.resolve()),manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),seed_sha256=seed_hash)),encoding='utf-8')
        with awake_system(),full_http(database,checkpoint_seconds=30 if args.seconds>=3600 else 5) as url:
            run_cycles(url,database,args.seconds,report,checkpoint=checkpoint)
        diagnostic=read(folder/'diagnostics.json')
        report['diagnostic_io']=read(folder/'diagnostic-io.json')
        assert not report['diagnostic_io']['fatal_errors'], 'Diagnostic control failed'
        assert not diagnostic['heartbeat_gaps'] and not diagnostic.get('in_flight'), 'Incomplete diagnostic interval'
        assert not any(r['failed_sql'] for r in diagnostic['requests']), 'SQL failure during hour workload'
        samples=[sample for cycle in report['cycles'] for sample in cycle['samples']]
        report['requests']=len(samples)
        report['segmented_diagnostics']=segmented_diagnostics(diagnostic,samples,window=300)
        report['per_endpoint']={endpoint:distribution([s['seconds'] for s in samples if s['endpoint']==endpoint])
            for endpoint in sorted({s['endpoint'] for s in samples})}
        report['expected_conflicts']=sum(c['command_event_reconciliation']['rejected_commands_without_facts'] for c in report['cycles'])
        report['verified_commands']=sum(c['command_event_reconciliation']['unique_committed_commands'] for c in report['cycles'])
        report['runtime']=read(folder/'runtime.json')
        assert report['runtime']['sqlite_busy_timeout_ms']==5000 and not report['runtime']['dependency_overrides']
        api_log=(folder/'api.log').read_text(encoding='utf-8',errors='replace')
        assert 'identity_background_retry_required' not in api_log and 'Traceback (most recent call last)' not in api_log
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        report.update(status='passed',diagnostics_complete=True,sql_errors=0,background_errors=0)
    except Exception as error:
        report['error']=dict(type=type(error).__name__,detail=str(error)[:1500],notes=getattr(error,'__notes__',[]))
    finally:
        report.update(source_after=source_state(),seed_unchanged=seed_hash==sha256(seed.read_bytes()).hexdigest())
        report['source_unchanged']=initial==report['source_after']
        if not report['source_unchanged'] or not report['seed_unchanged']:report['status']='failed'
        if not write_snapshot(folder/'report.json',report):
            raise RuntimeError('Final hour evidence replacement was refused')
    print(json.dumps(dict(status=report['status'],error=report.get('error'),hour_duration_achieved=report['hour_duration_achieved'],release_ready=False)),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
