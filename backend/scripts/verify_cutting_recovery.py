"""Rehearse DB + storage + protected configuration on a new synthetic target.

No production database, arbitrary URL, credentials or output path is accepted.
The current acceptance release is never switched. DPAPI is local CurrentUser;
this does not certify another machine/user or production RTO/RPO.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
from uuid import uuid4

from cutting_recovery_bundle import create_bundle,restore_bundle,file_hash,inventory,finalize_cleanup
from verify_cutting_full_app import ROOT,CONTROL,OUTPUT,read,validate_copy,full_http


def snapshot(path, *, protected=False):
    result={}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            if protected and name in {'auth_sessions','auth_audit_logs','auth_user_presence'}:continue
            cols=[v[1] for v in db.execute('PRAGMA table_info("'+name+'")')];values=[]
            for raw in db.execute('SELECT * FROM "'+name+'"'):
                row=dict(zip(cols,raw))
                if protected and name=='auth_users':
                    for key in ['last_login_at','updated_at']:row.pop(key,None)
                if protected and name=='auth_iam_state' and row.get('key')=='identity_mutation_lock':row.pop('updated_at',None)
                encoded=json.dumps(row,ensure_ascii=False,sort_keys=True,default=lambda b:{'bytes':b.hex()}).encode()
                values.append(sha256(encoded).hexdigest())
            result[name]=dict(count=len(values),sha256=sha256('\n'.join(sorted(values)).encode()).hexdigest())
        assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    return result


def validate_seed(value):
    database,m=validate_copy(value)
    report=read(database.parent/'report.json')
    if report.get('status')!='passed' or not (database.parent/'stop').is_file():
        raise ValueError('Recovery accepts only a completed, stopped full-app synthetic run')
    diagnostic=read(database.parent/'diagnostics.json')
    if diagnostic.get('in_flight') or diagnostic.get('heartbeat_gaps'):
        raise ValueError('Incomplete synthetic source cannot certify recovery')
    return database,m


def order_counts(db):
    received=db.execute('SELECT count(*) FROM cutting_ops_orders').fetchone()[0]
    dispatched=db.execute("SELECT count(DISTINCT line_id) FROM order_ledger_dispatches WHERE factory_id='huakang-c' AND recipient='cutting'").fetchone()[0]
    return dispatched,received


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seed',required=True);args=parser.parse_args()
    seed,m=validate_seed(args.seed)
    name='recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    folder=ROOT/'.tmp/cutting-recovery'/name;folder.mkdir(parents=True,exist_ok=False)
    target_folder=OUTPUT/name;release=CONTROL/'releases'/name
    owner=uuid4().hex
    seed_hash=file_hash(seed);original=ROOT/'backend/data/royal_regent_nexus.db';original_hash=file_hash(original)
    control_hash=file_hash(CONTROL/'current.json');report=dict(status='failed',release_ready=False,production_capacity_accepted=False,
        configuration_protection='Windows DPAPI CurrentUser; not portable-key or production recovery acceptance')
    print(str(folder),flush=True)
    try:
        began=perf_counter();before=snapshot(seed);business=snapshot(seed,protected=True)
        settings=read(Path(m['release'])/'environment.local.json')
        if settings.get('SEED_DEFAULT_ACCOUNTS')!='false':raise ValueError('Synthetic release must disable seeding')
        metadata={k:m[k] for k in ['acceptance_release','p5c_source_files']}
        if 'cutting_migration_revision' in m:metadata['cutting_migration_revision']=m['cutting_migration_revision']
        package=create_bundle(seed,Path(m['source']),seed.parent/'storage',settings,metadata,folder/'backup')
        report['backup_seconds']=perf_counter()-began
        began=perf_counter();target,restored=restore_bundle(folder/'backup',target_folder,release,owner_token=owner)
        assert snapshot(target)==before
        report['restore_and_full_readback_seconds']=perf_counter()-began
        with closing(sqlite3.connect(target.as_uri()+'?mode=ro',uri=True)) as db:
            orders,received=order_counts(db)
            selected=db.execute("SELECT id,month,data FROM cutting_ops_period_events WHERE action='lock' ORDER BY version LIMIT 1").fetchone()
        assert orders==500 and 0<received<=orders and selected is not None
        import httpx
        with full_http(target) as url,httpx.Client(base_url=url,trust_env=False,timeout=60) as client:
            # These fixed credentials belong only to the eight p5b fixture users.
            # They are never input, logged, or written into the recovery report.
            login=client.post('/api/auth/login',json={'username':'p5b-reviewer','password':'SyntheticPass123!'})
            assert login.status_code==200,'Synthetic recovered-session login failed'
            for path in ['/api/cutting-operations/access','/api/cutting-operations/workspace/planning',
                         '/api/cutting-operations/workspace/inventory','/api/cutting-operations/workspace/costs']:
                response=client.get(path,params={'factory_id':'huakang-c'});assert response.status_code==200,path
                if path.endswith('/planning'):assert response.json()['total']==orders
            response=client.get('/api/cutting-operations/periods/'+selected[1],params={'factory_id':'huakang-c','event_id':selected[0]})
            assert response.status_code==200 and response.json()['data']==json.loads(selected[2])
        assert snapshot(target,protected=True)==business
        assert file_hash(seed)==seed_hash and file_hash(original)==original_hash and file_hash(CONTROL/'current.json')==control_hash
        report.update(status='passed',tables_restored=len(before),protected_tables_unchanged=len(business),dispatched_orders=orders,received_orders=received,
            storage_files=len([k for k in package['files'] if k.startswith('storage/')]),synthetic_binary_sentinels=2,
            bundled_source_files=len([k for k in package['files'] if k.startswith('source/')]),
            full_snapshot_equal=True,restored_api_checks=5,restored_login=True,frozen_event_equal=True,
            source_unchanged=True,original_unchanged=True,active_release_unchanged=True,
            boundary='Local synthetic stopped-package recovery with matching bundled code; not real attachments, target-server RTO/RPO or production cutover')
    except Exception as error:
        report['error_type']=type(error).__name__
        raise
    finally:
        # Remove only this run's private plaintext runtime config after owned API
        # shutdown; the source and encrypted package remain for evidence.
        primary=sys.exc_info()[1]
        cleanup_error=finalize_cleanup(release,owner,report)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if cleanup_error:
            if primary is None:raise RuntimeError('Recovery runtime configuration cleanup failed; see private report') from cleanup_error
            primary.add_note('Owned plaintext configuration cleanup failed; retained in the private report.')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
