"""Retry only assistant deletion tombstones. Explicit database URL required."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--storage-dir', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expire-retention', action='store_true', help='Also apply the configured optional retention period')
    args = parser.parse_args()
    os.environ['DATABASE_URL'] = args.database_url
    os.environ['ASSISTANT_STORAGE_DIR'] = args.storage_dir
    os.environ['SEED_DEFAULT_ACCOUNTS'] = 'false'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import select, func
    from app.db import SessionLocal
    from app.models.assistant import AssistantSession
    from app.services.assistant.service import cleanup_pending, expire_retention
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(AssistantSession).where(AssistantSession.deletion_state == 'pending'))
    print({'pending': count, 'apply': args.apply})
    if args.apply:
        if args.expire_retention:
            print({'expired': expire_retention()})
        result = cleanup_pending()
        print({'attempted': len(result), 'cleaned': sum(result.values()), 'pending': sum(not v for v in result.values())})


if __name__ == '__main__':
    main()
