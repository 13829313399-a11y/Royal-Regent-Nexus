"""Release gate for the existing Compose deployment; never migrates from a GET.

prepare runs only after all writers stop and the deployment takes a consistent
PostgreSQL dump plus the complete QC directory. start never creates missing QC
schemas. Explicit QC_DOSSIER_ENABLED=false is the emergency collection rollback.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from sqlalchemy import inspect, text
from app.db import engine, SessionLocal
from app.services import qc_dossier as archive
from app.services.qc_dossier_worker import validate_installed

PARENT = '20261107_0193'
REVISION = '20261110_0194'


def version():
    with engine.connect() as conn:
        values = list(conn.execute(text('SELECT version_num FROM alembic_version')).scalars())
    if len(values) != 1 or values[0] not in (PARENT, REVISION):
        raise RuntimeError('Main database must be verified at 0193 or 0194; refusing unrelated historical migrations')
    return values[0]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('QC backup contains a symlink; explicit review required')
        if path.is_file():
            result[str(path.relative_to(root))] = file_hash(path)
    return result


def restore_empty_volume(source, target):
    """Copy only into an empty new volume; never overwrite existing business data."""
    expected = inventory(source)
    if not expected:
        raise RuntimeError('QC backup is empty; refusing to treat a missing legacy store as a new installation')
    target.mkdir(parents=True, exist_ok=True)
    actual = inventory(target)
    if actual:
        if actual != expected:
            raise RuntimeError('Existing QC volume differs from stopped-container backup; no files overwritten')
        return
    shutil.copytree(source, target, dirs_exist_ok=True)
    if inventory(target) != expected:
        raise RuntimeError('QC volume copy verification failed; release remains blocked')


def integrity(root):
    checked = 0
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                continue
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RuntimeError('QC SQLite integrity check failed')
        checked += 1
    return checked


def prepare(backup, source=None):
    # This command must run with deployment writers stopped. The release wrapper
    # owns that boundary; no runtime endpoint can call it.
    before = version()
    backup = backup.resolve()
    if not backup.is_dir():
        raise RuntimeError('Existing private backup directory is required')
    if engine.dialect.name == 'postgresql':
        dump = backup / 'database-stopped.dump'
        manifest = backup / 'database-stopped.sha256'
        listing = backup / 'database-stopped.restore-list.txt'
        if not dump.is_file() or not manifest.is_file() or not listing.is_file() or not listing.stat().st_size:
            raise RuntimeError('Verified stopped-writer PostgreSQL backup is required')
        if file_hash(dump) != manifest.read_text().split()[0]:
            raise RuntimeError('PostgreSQL backup checksum mismatch')
    elif engine.dialect.name == 'sqlite':
        main = Path(engine.url.database).resolve()
        destination = backup / ('main-before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.sqlite3')
        with sqlite3.connect(main.as_uri() + '?mode=ro', uri=True) as old, sqlite3.connect(destination) as copy:
            old.backup(copy)
            if copy.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise RuntimeError('Main backup integrity failed')
        os.chmod(destination, 0o600)
    else:
        raise RuntimeError('Unsupported backup engine')
    root = Path(archive.settings.qc_department_data_dir).resolve()
    if source:
        source = source.resolve()
        integrity(source)
        restore_empty_volume(source, root)
    else:
        snapshot = backup / ('qc-before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
        if not root.is_dir() or not inventory(root):
            raise RuntimeError('Existing QC data directory is required')
        shutil.copytree(root, snapshot)
        if inventory(snapshot) != inventory(root):
            raise RuntimeError('QC backup changed during capture; stop writers and retry')
        integrity(snapshot)
    integrity(root)
    if before == PARENT:
        subprocess.run([sys.executable, '-m', 'alembic', '-c', str(BACKEND/'alembic.ini'), 'upgrade', REVISION], cwd=BACKEND, check=True)
    if version() != REVISION:
        raise RuntimeError('Main migration did not reach required version')
    archive.migrate()
    validate_installed(engine)
    checked = integrity(root)
    result = {'revision': REVISION, 'qcSchema': archive.VERSION, 'sqliteChecks': checked, 'preparedAt': archive.now()}
    marker = root / '.qc-dossier-ready.json'
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps(result))
    temporary.replace(marker)
    return result


def readiness():
    if not archive.settings.qc_dossier_enabled:
        return {'enabled': False, 'status': 'emergency-disabled'}
    validate_installed(engine)
    with archive.connect() as conn:
        state = conn.execute("SELECT value,updated_at FROM dossier_worker_state WHERE key='collection'").fetchone()
        success = conn.execute("SELECT updated_at FROM dossier_worker_state WHERE key='last_success'").fetchone()
        if not state or not success:
            raise RuntimeError('Initial collection is pending')
        value = json.loads(state['value'])
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(success[0])).total_seconds()
        if value.get('status') != 'ready' or age > max(120, archive.settings.qc_dossier_poll_seconds*3):
            raise RuntimeError('Collection is incomplete, failed or stale')
        heads = {(r[0],r[1]) for r in conn.execute('SELECT factory,source_id FROM source_heads')}
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.models.qc_dossier import QcDossierOutbox
    with SessionLocal() as db:
        expected = {(r[0],r[1]) for r in db.query(OrderLedgerLine.factory_id,OrderLedgerLine.id).filter(OrderLedgerLine.factory_id.in_(archive.factories()))}
        pending = db.query(QcDossierOutbox).filter(QcDossierOutbox.factory.in_(archive.factories()),QcDossierOutbox.delivered_at=='').count()
    if expected - heads or pending:
        raise RuntimeError('Source coverage or pending delivery failed')
    from app.services.qc_dossier_read import detail
    summary_path = Path(archive.settings.qc_department_data_dir).resolve()/'_summary'/'summaries.sqlite3'
    detail_checks = 0
    if summary_path.exists():
        with sqlite3.connect(summary_path.as_uri()+'?mode=ro',uri=True) as conn:
            for factory in archive.factories():
                for row in conn.execute('SELECT id FROM records WHERE factory=? AND active=1 LIMIT 5',(factory,)):
                    detail(factory,row[0]); detail_checks += 1
    return {'enabled':True,'status':'ready','sources':len(expected),'lastSuccessAt':success[0],'detailChecks':detail_checks,**value}


def start():
    if archive.settings.qc_dossier_enabled:
        marker = Path(archive.settings.qc_department_data_dir)/'.qc-dossier-ready.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('revision') != REVISION:
            raise RuntimeError('QC release preparation missing; run the versioned deployment flow before startup')
        if version()!=REVISION:
            raise RuntimeError('QC main migration is not ready')
        validate_installed(engine)
    else:
        # Preserve the established startup path when the optional collector is disabled.
        subprocess.run([sys.executable,'-m','alembic','-c',str(BACKEND/'alembic.ini'),'upgrade','head'],cwd=BACKEND,check=True)
    os.execvp('uvicorn',['uvicorn','app.main:app','--host','0.0.0.0','--port','8000'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','verify','start'])
    parser.add_argument('--backup-dir',type=Path)
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.action=='start': start(); return
    if args.action=='prepare':
        if not args.backup_dir: parser.error('--backup-dir is required')
        result=prepare(args.backup_dir,args.source)
    else: result=readiness()
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
