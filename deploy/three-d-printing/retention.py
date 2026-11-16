"""Clear expired raw telemetry bodies, retaining normalized evidence and audits.

Dry run by default; no production records, inventory, files or audit rows deleted.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import three_d_printing as m
from app.services.three_d_telemetry_retention import FACTORY, cutoff_for, lock, printer_batch
from app.services.three_d_telemetry_storage import KEEP_DAYS


def retain(db, days=KEEP_DAYS, execute=False):
    cutoff = cutoff_for(days)
    changed = examined = 0
    if execute and not lock(db):
        raise RuntimeError("Another retention transaction is in progress")
    printers = db.scalars(select(m.ThreeDPrintingPrinter).where(
        m.ThreeDPrintingPrinter.factory_id == FACTORY).order_by(m.ThreeDPrintingPrinter.id)).all()
    for printer in printers:
        count, shortened, moved = printer_batch(db, printer, cutoff, 500-examined, execute=execute)
        examined += count
        changed += shortened + moved
        if examined == 500:
            break
    if execute:
        db.commit()
    return {"mode": "executed" if execute else "dry_run", "raw_bodies": changed if execute else examined,
            "cutoff": cutoff, "batch_limit": 500, "normalized_events_and_business_data_retained": True}


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-file", required=True)
    parser.add_argument("--days", type=int, default=KEEP_DAYS)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    engine = create_engine(
        Path(args.database_url_file).read_text(encoding="utf-8-sig").strip(),
        hide_parameters=True,
    )
    with Session(engine) as db:
        print(json.dumps(retain(db, args.days, args.execute)))
    engine.dispose()


if __name__ == "__main__":
    main()
