"""Run the P5c mix against a frozen full application and a new synthetic DB.

No service URL, output database, business database or credential input is accepted.
The selected staged acceptance release supplies source/schema, never its data.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT/'.local-dev/cutting-acceptance'
OUTPUT = ROOT/'.tmp/cutting-full-app'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def release_manifest(path):
    path = Path(path).resolve()
    if not path.is_relative_to((CONTROL/'releases').resolve()) or path.name != 'manifest.json':
        raise ValueError('Requires a frozen acceptance release manifest')
    m = read(path)
    source = Path(m['source']).resolve()
    if Path(m['release']).resolve()!=path.parent or source != path.parent/'source' or not (source/'backend/app/main.py').is_file():
        raise ValueError('Frozen full application source is required')
    for name, digest in m['p5c_source_files'].items():
        p = (source/name).resolve()
        if not p.is_relative_to(source) or sha256(p.read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen P5c source fingerprint mismatch')
    return m


def validate_copy(database):
    database = Path(database).resolve()
    if not database.is_relative_to(OUTPUT.resolve()) or database.name != 'cutting.db' or not database.is_file():
        raise ValueError('Requires an exclusively prepared full-app synthetic copy')
    marker = read(database.parent/'fixture.json')
    if marker['kind'] != 'cutting-full-app-synthetic' or marker['database'] != str(database):
        raise ValueError('Full-app fixture provenance mismatch')
    m = release_manifest(marker['manifest'])
    if sha256(Path(marker['manifest']).read_bytes()).hexdigest() != marker['manifest_sha256']:
        raise ValueError('Release manifest changed')
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        names = [r[0] for r in db.execute('SELECT username FROM auth_users')]
        if len(names) != 8 or any(not n.startswith('p5b-') for n in names):
            raise ValueError('Only the eight synthetic fixture users are accepted')
        if db.execute('SELECT version_num FROM alembic_version').fetchall() != [('20261021_0172',)]:
            raise ValueError('Unexpected frozen schema version')
    return database, m


def environment(m, database):
    database = Path(database).resolve()
    if not database.is_relative_to(OUTPUT.resolve()) or database.name != 'cutting.db':
        raise ValueError('Refusing a database outside the exclusive pressure directory')
    env = os.environ.copy()
    env.update({k: str(v) for k, v in read(Path(m['release'])/'environment.local.json').items()})
    env.update(DATABASE_URL='sqlite:///'+database.as_posix(), SEED_DEFAULT_ACCOUNTS='false',
               PYTHONPATH='', PYTHONUTF8='1', PYTHONIOENCODING='utf-8', CUTTING_TEST_POSTGRES_URL='')
    for key in ['ASSISTANT_STORAGE_DIR','COLLABORATION_STORAGE_DIR','DOCUMENT_TOOLS_STORAGE_DIR','THREE_D_ASSET_DIR']:
        env[key]=(database.parent/'storage'/key.lower()).as_posix()
    return env


def install_fixture(seed, target):
    """Import only a proven synthetic fixture into a new full migration schema."""
    target = Path(target).resolve()
    if not target.is_relative_to(OUTPUT.resolve()) or target.name != 'cutting.db':
        raise ValueError('Unsafe synthetic fixture target')
    from verify_cutting_lock_phases import seed_file
    seed = seed_file(seed)
    with sqlite3.connect(seed.as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
        names = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        if 'alembic_version' in names:
            raise ValueError('Seed must not supply a migration version')
        # Test fixture IDs are raw codes; real full-app startup expects canonical
        # permission IDs. Codes, role packages and effective grants do not change.
        permission_ids = {r[0]:'perm-'+r[1].replace(':','-') for r in src.execute('SELECT id,code FROM auth_permissions')}
        dst.execute('PRAGMA foreign_keys=OFF')
        try:
            dst.execute('BEGIN IMMEDIATE')
            triggers = dst.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
            for name, _ in triggers: dst.execute('DROP TRIGGER "'+name+'"')
            for name in reversed(names): dst.execute('DELETE FROM "'+name+'"')
            counts = {}
            for name in names:
                columns = [r[1] for r in src.execute('PRAGMA table_info("'+name+'")')]
                target_columns = {r[1] for r in dst.execute('PRAGMA table_info("'+name+'")')}
                if not set(columns) <= target_columns:
                    raise ValueError('Synthetic/full-schema column mismatch: '+name)
                rows=[]
                for original in src.execute('SELECT * FROM "'+name+'"'):
                    values=dict(zip(columns,original))
                    if name=='auth_permissions':values['id']=permission_ids[values['id']]
                    if name in {'auth_role_permissions','auth_user_permission_overrides'}:
                        values['permission_id']=permission_ids[values['permission_id']]
                    rows.append(tuple(values[col] for col in columns))
                sql='INSERT INTO "'+name+'" ('+','.join('"'+v+'"' for v in columns)+') VALUES ('+','.join('?' for _ in columns)+')'
                dst.executemany(sql, rows)
                # Compare every imported field including bytes/storage values.
                if sorted(map(repr,rows)) != sorted(map(repr,dst.execute('SELECT '+','.join('"'+v+'"' for v in columns)+' FROM "'+name+'"'))):
                    raise ValueError('Fixture import changed values: '+name)
                counts[name]=len(rows)
            for _, ddl in triggers:dst.execute(ddl)
            if dst.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Fixture has foreign-key violations')
            dst.commit()
        except BaseException:
            dst.rollback()
            raise
        finally:dst.execute('PRAGMA foreign_keys=ON')
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid fixture database')
    return counts


def serve(database):
    if not os.environ.get('CUTTING_FULL_APP_INSTANCE'):
        raise ValueError('An owned full-app process identity is required')
    database,m=validate_copy(database)
    # Fence even a direct/manual --serve invocation before any app import.
    # Never trust inherited DATABASE_URL or a source tree's .env file.
    os.environ.update(environment(m,database))
    sys.path[:0]=[str(Path(m['source'])/'backend'),str(ROOT/'backend/tests')]
    from datetime import date
    from zoneinfo import ZoneInfo
    import uvicorn
    from app.main import app
    from app.db import engine
    from app.services import cutting_planning, cutting_exports, warehouse_operations
    from test_cutting_http_soak import Diagnostics
    if Path(engine.url.database).resolve()!=database:
        raise ValueError('Full-app engine is not bound to its exclusive synthetic copy')
    if app.dependency_overrides:raise ValueError('Full-app probe must not override authentication or database dependencies')
    with engine.connect() as conn:
        timeout=conn.exec_driver_sql('PRAGMA busy_timeout').scalar_one()
    (database.parent/'runtime.json').write_text(json.dumps(dict(sqlite_busy_timeout_ms=timeout,
        dependency_overrides=False,source=m['source'],p5c_source_files=m['p5c_source_files'])),encoding='utf-8')
    warehouse_operations.business_now=lambda:datetime(2026,12,15,12,tzinfo=ZoneInfo('Asia/Shanghai'))
    cutting_exports.business_now=warehouse_operations.business_now
    cutting_planning.business_today=lambda:date(2026,12,15)
    diagnostic=Diagnostics(SimpleNamespace(app=app,engine=engine))
    folder=database.parent;stop=threading.Event();sock=socket.socket()
    try:
        sock.bind(('127.0.0.1',0));sock.listen(128)
        server=uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='warning',timeout_graceful_shutdown=10))
        def control():
            while not stop.wait(.1):
                if server.started and not (folder/'ready.json').exists():
                    (folder/'ready.json').write_text(json.dumps(dict(port=sock.getsockname()[1],instance=os.environ['CUTTING_FULL_APP_INSTANCE'],full_lifespan=True)),encoding='utf-8')
                if (folder/'stop').exists():server.should_exit=True;return
        threading.Thread(target=control,daemon=True).start();diagnostic.start();server.run(sockets=[sock])
    finally:
        stop.set();diagnostic.close();sock.close();engine.dispose()
        (folder/'diagnostics.json').write_text(json.dumps(dict(requests=diagnostic.rows,lock_spans=diagnostic.lock_spans,heartbeat_gaps=diagnostic.gaps),ensure_ascii=False),encoding='utf-8')


@contextmanager
def full_http(database):
    database,m=validate_copy(database);folder=database.parent;instance=uuid4().hex
    env=environment(m,database);env['CUTTING_FULL_APP_INSTANCE']=instance
    if any((folder/n).exists() for n in ['ready.json','stop','diagnostics.json']):raise ValueError('Never reuse a probe directory')
    with (folder/'api.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([sys.executable,str(Path(__file__)), '--serve',str(database)],cwd=Path(m['source'])/'backend',env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        try:
            deadline=time.monotonic()+120
            while not (folder/'ready.json').exists():
                if proc.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Full-app startup failed; see api.log')
                time.sleep(.2)
            ready=read(folder/'ready.json')
            if ready['instance']!=instance or proc.poll() is not None:raise RuntimeError('Owned full-app identity mismatch')
            yield 'http://127.0.0.1:'+str(ready['port'])
        finally:
            (folder/'stop').touch(exist_ok=False)
            try:proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                if sys.platform=='win32':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
                else:proc.kill()
                proc.wait(timeout=10)
                raise RuntimeError('Owned full-app shutdown timed out')
            if proc.returncode:raise RuntimeError('Owned full-app exited with failure; see api.log')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seed');parser.add_argument('--seconds',type=int,default=600);parser.add_argument('--serve')
    parser.add_argument('--workload',choices=['burst','paced'],default='burst',help='Burst retains the .2s baseline; paced uses a 2s pause per worker cycle. No failed request is automatically retried.')
    parser.add_argument('--production-write-orders',type=int,default=0,
        help='Rotate handover and usage writes over this many separate orders per clerk (0 disables, 1–40); no receipt/return/month-lock writes.')
    args=parser.parse_args()
    if args.serve:
        serve(args.serve);return 0
    if not args.seed or not 10<=args.seconds<=600:parser.error('Requires a proven seed and 10–600 seconds')
    if not 0<=args.production_write_orders<=40:parser.error('Use 0–40 production-write orders per clerk')
    from verify_cutting_lock_phases import seed_file,run_probe,diagnostics_summary
    from verify_cutting_p5b import source_state
    seed=seed_file(args.seed);manifest=Path(read(CONTROL/'staged.json')['release'])/'manifest.json';m=release_manifest(manifest)
    folder=OUTPUT/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
    database=folder/'cutting.db';initial=source_state();seed_hash=sha256(seed.read_bytes()).hexdigest()
    pause=2. if args.workload=='paced' else .2
    report=dict(status='failed',seconds=args.seconds,release=m['acceptance_release'],source=initial,release_ready=False,workload=args.workload,cycle_pause_seconds=pause,
        scope='Frozen full application with full lifespan; fresh synthetic schema; 500 dispatch/100 production/20 finance chains; test business clock 2026-12-15; not target hardware, competing writers or production approval')
    report['production_write_orders_per_kind']=args.production_write_orders
    print(str(folder),flush=True)
    try:
        with (folder/'migration.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=Path(m['source'])/'backend',env=environment(m,database),stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
        report['imported_tables']=install_fixture(seed,database)
        (folder/'fixture.json').write_text(json.dumps(dict(kind='cutting-full-app-synthetic',database=str(database.resolve()),manifest=str(manifest.resolve()),manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),seed_sha256=seed_hash)),encoding='utf-8')
        run_probe(database,args.seconds,report,server_context=full_http,cycle_pause=pause,
            production_write_orders=args.production_write_orders)
        report['diagnostic_summary']=diagnostics_summary(read(folder/'diagnostics.json'),report['samples'])
        report['runtime']=read(folder/'runtime.json')
        if report['runtime']['sqlite_busy_timeout_ms']!=5000:raise ValueError('Full-app SQLite timeout differs from the unchanged 5s baseline')
        report['status']='passed'
    except Exception as error:report['error']=dict(type=type(error).__name__,detail=str(error)[:1000])
    finally:
        report.update(source_after=source_state(),seed_unchanged=seed_hash==sha256(seed.read_bytes()).hexdigest())
        report['source_unchanged']=initial==report['source_after']
        if not report['source_unchanged'] or not report['seed_unchanged']:report['status']='failed'
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],error=report.get('error'),release_ready=False)),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
