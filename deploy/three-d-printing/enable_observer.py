"""Enable cloud status observation for one printer; leave print control with the site."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sqlalchemy import select
from app.db import SessionLocal
from app.models import three_d_printing as m
from app.services import three_d_connector as connector


def enable(db, machine_no):
    printer = db.scalar(select(m.ThreeDPrintingPrinter).where(
        m.ThreeDPrintingPrinter.factory_id == connector.FACTORY,
        m.ThreeDPrintingPrinter.machine_no == machine_no,
    ))
    if printer is None or not printer.enabled:
        raise ValueError("Printer is missing or disabled")
    row = db.scalar(select(m.ThreeDPrintingPrinterConnection).where(
        m.ThreeDPrintingPrinterConnection.printer_id == printer.id,
        m.ThreeDPrintingPrinterConnection.factory_id == connector.FACTORY,
        m.ThreeDPrintingPrinterConnection.site_id == connector.SITE,
    ).with_for_update())
    if row is None or row.connection_owner not in {"edge-legacy", connector.OBSERVER}:
        raise ValueError("Expected a legacy or observer connection")
    if not re.fullmatch("[a-fA-F0-9]{64}", row.certificate_fingerprint) or not row.credential_ref:
        raise ValueError("Printer certificate or credential reference is missing")
    connector.require_network(db)
    if row.connection_owner != connector.OBSERVER or not row.connection_enabled:
        row.connection_owner = connector.OBSERVER
        row.connection_enabled = True
        # Observation never writes production records unless an operator turns the
        # record switch on separately; the old writer remains the record source here.
        row.record_reconcile_enabled = False
        row.connection_revision += 1
        row.leader_instance_id = None
        row.leader_lease_id = ""
        row.leader_leased_until = ""
        printer.connected, printer.state = False, "STALE"
        connector.audit(db, "printer_connection", printer.id, "observation_enabled",
            {"machine_no": machine_no, "mode": connector.OBSERVER,
             "legacy_writer_stopped": False, "control_transferred": False,
             "record_reconcile_enabled": False},
            "onsite-user", connector.database_now(db), actor_type="operator",
            actor_name="现场只读接入")
    return {"machine_no": machine_no, "printer_id": printer.id,
            "mode": row.connection_owner, "connection_revision": row.connection_revision}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine", type=int, choices=range(1, 12), required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = enable(db, args.machine)
        db.commit()
    print(json.dumps(result))
