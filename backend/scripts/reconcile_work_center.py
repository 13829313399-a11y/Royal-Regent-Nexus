"""Usage: python scripts/reconcile_work_center.py --database-url sqlite:///COPY.db [--apply]."""
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Explicit database only; dry-run by default. Back up before --apply.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = args.database_url
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Load mappings only. Do not start app, seed data or auto-create any schema.
    from app.db import SessionLocal
    from app.models import auth, identity, molding_sample, internal_quote, carton_supplier_portal, carton_procurement, work_center, pricing, carton_master, carton_stocktake
    from app.services.work_center.reconciliation import reconcile
    with SessionLocal() as db:
        report = reconcile(db, apply=args.apply)
        if args.apply: db.commit()
        else: db.rollback()
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__": main()
