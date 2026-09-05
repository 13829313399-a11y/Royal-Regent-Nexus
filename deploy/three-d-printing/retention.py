"""Clear expired raw telemetry bodies, retaining normalized evidence and audits.

Dry run by default; no production records, inventory, files or audit rows deleted.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.models.three_d_printing import ThreeDPrintingPrinterStateEvent as Event
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session


def retain(db, days=90, execute=False):
    if days < 30:
        raise ValueError("Minimum raw telemetry retention is 30 days")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    ids = list(
        db.scalars(
            select(Event.id)
            .where(
                Event.factory_id == "huakang-a",
                Event.received_at < cutoff,
                Event.raw_payload_json != "{}",
            )
            .order_by(Event.received_at, Event.id)
            .limit(500)
        )
    )
    if execute and ids:
        db.execute(
            update(Event)
            .where(Event.id.in_(ids), Event.factory_id == "huakang-a")
            .values(raw_payload_json="{}")
        )
        db.commit()
    return {
        "mode": "executed" if execute else "dry_run",
        "raw_bodies": len(ids),
        "cutoff": cutoff,
        "batch_limit": 500,
        "normalized_events_and_business_data_retained": True,
    }


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-file", required=True)
    parser.add_argument("--days", type=int, default=90)
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
