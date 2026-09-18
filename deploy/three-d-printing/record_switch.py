"""Turn automatic production recording on or off for a printer connection.

Recording a finished print is independent of hardware control: an observation-only
connection can settle daily records while pause/resume stays refused. Plan first,
then apply with --execute. The connection revision is bumped so the change is visible
in the connection's own version, and nothing here starts a service or sends a command.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import SessionLocal  # noqa: E402
from app.models import three_d_printing as m  # noqa: E402
from app.services.three_d_connector import FACTORY, stamp  # noqa: E402

ACTION_ON = "on"
ACTION_OFF = "off"


def plan(db, machines, enable):
    rows = []
    printers = db.scalars(
        select(m.ThreeDPrintingPrinter)
        .where(m.ThreeDPrintingPrinter.factory_id == FACTORY)
        .order_by(m.ThreeDPrintingPrinter.machine_no)
    )
    for printer in printers:
        if machines and printer.machine_no not in machines:
            continue
        connection = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
        if connection is None:
            rows.append({"machine_no": printer.machine_no, "state": "no_connection"})
            continue
        rows.append(
            {
                "machine_no": printer.machine_no,
                "printer_id": printer.id,
                "connection_owner": connection.connection_owner,
                "connection_enabled": bool(connection.connection_enabled),
                "record_reconcile_enabled": bool(connection.record_reconcile_enabled),
                "connection_revision": connection.connection_revision,
                "planned": bool(enable),
                "changes": bool(connection.record_reconcile_enabled) != bool(enable),
            }
        )
    return rows


def apply(db, rows, enable):
    changed = []
    for row in rows:
        if not row.get("changes"):
            continue
        connection = db.get(m.ThreeDPrintingPrinterConnection, row["printer_id"])
        connection.record_reconcile_enabled = bool(enable)
        connection.connection_revision += 1
        changed.append(
            {
                "machine_no": row["machine_no"],
                "connection_owner": connection.connection_owner,
                "record_reconcile_enabled": bool(enable),
                "connection_revision": connection.connection_revision,
                "changed_at": stamp(datetime.now(UTC)),
            }
        )
    db.commit()
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=[ACTION_ON, ACTION_OFF])
    parser.add_argument("--machine", type=int, action="append", default=[],
                        help="repeatable machine number; omit for all printers")
    parser.add_argument("--execute", action="store_true",
                        help="apply the change; without it only a plan is printed")
    args = parser.parse_args(argv)
    enable = args.action == ACTION_ON
    with SessionLocal() as db:
        rows = plan(db, set(args.machine), enable)
        report = {
            "action": args.action,
            "scope": sorted(args.machine) or "all",
            "planned_changes": sum(1 for row in rows if row.get("changes")),
            "connections": rows,
        }
        if args.execute:
            report["applied"] = apply(db, rows, enable)
            report["status"] = "applied"
        else:
            report["status"] = "planned"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
