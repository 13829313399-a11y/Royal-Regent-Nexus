"""Explicit local archive migration/reconciliation; never called by a GET request.

Set DATABASE_URL and QC_DEPARTMENT_DATA_DIR to the intended isolated/local store.
The ledger outbox migration is Alembic 20261110_0194 (run separately on an existing DB).
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect
from app.db import SessionLocal,engine
from app.services import qc_dossier as archive
from app.services.qc_dossier_events import install
from app.services.qc_dossier_worker import cycle, recover_retained_events, validate_installed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['status','migrate','collect','recover'])
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.action!='status' and not args.apply:parser.error('写入操作需要显式 --apply；请先核对目标与备份')
    if archive.settings.app_env=='production' and args.action!='status':parser.error('此本地验收命令不允许生产写入')
    result={'archive':str(archive.path()),'workflow':str(archive.workflow_path()),'enabled':archive.settings.qc_dossier_enabled,'factories':sorted(archive.factories())}
    if args.action=='migrate':
        backups=[]
        for source in (archive.path(),archive.workflow_path()):
            if source.exists():
                target=source.with_name(source.name+'.before-dossier-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.bak')
                with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target) as copy:old.backup(copy)
                backups.append(str(target))
        archive.migrate();result['backups']=backups
    elif args.action in ('collect','recover'):
        if not archive.settings.qc_dossier_enabled:parser.error('先显式启用 QC_DOSSIER_ENABLED')
        if 'qc_dossier_outbox' not in inspect(engine).get_table_names():parser.error('先执行主库 outbox 迁移')
        validate_installed(engine);install()
        if args.action=='recover':
            with SessionLocal() as db:result['recovered']=recover_retained_events(db)
        result['cycle']=cycle(SessionLocal)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
