"""Run in the production API container: python tools/export_module_feedback.py.

Requires the existing private administrative connection. Does not initialize or
migrate the database, load attachment content, mark messages read or write status.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from app.services.module_feedback_report import collect_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if engine.dialect.name != "postgresql":
        parser.error("The online report requires the production PostgreSQL connection")
    with Session(engine) as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        report = collect_report(db, offset=args.offset, limit=args.limit)
        db.rollback()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
