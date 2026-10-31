"""Explicit operator maintenance: dry-run by default, no app startup or legacy edits."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',required=True,help='Explicit database URL; never defaults to the business store')
    parser.add_argument('--factory',required=True)
    parser.add_argument('--apply',action='store_true',help='Atomically rebuild only this factory projection')
    args=parser.parse_args()
    os.environ['DATABASE_URL']=args.database_url
    os.environ['SEED_DEFAULT_ACCOUNTS']='false'
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app.db import SessionLocal
    from app.services.carton_material_references import rebuild
    with SessionLocal() as db:
        try:
            result=rebuild(db,args.factory,apply=args.apply)
            if args.apply: db.commit()
            else: db.rollback()
        except Exception:
            db.rollback(); raise
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__': main()
