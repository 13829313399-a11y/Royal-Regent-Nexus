"""Single-printer ownership plan/apply; default is read-only, never deploys services.

Run with the backend virtualenv. Configuration is read from a private URL file.
No API command can prove physical MQTT disconnection: the stopped-writer
assertion is mandatory and must be checked onsite before executing this tool.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import three_d_printing as m
from app.services.three_d_network_health import network_health_snapshot
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import Session


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def plan(db, printer_id, target):
    if target not in {"cloud-connector", "edge-legacy"}:
        raise ValueError("Invalid owner")
    connection = db.get(m.ThreeDPrintingPrinterConnection, printer_id)
    if (
        not connection
        or connection.factory_id != "huakang-a"
        or connection.site_id != "3dsite-huakang-a-heyuan"
    ):
        raise ValueError("Printer is outside Heyuan scope")
    if connection.connection_owner == target:
        raise ValueError("Printer already has requested owner")
    records = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(m.ThreeDPrintingProductionRecord.revision), 0),
        ).where(m.ThreeDPrintingProductionRecord.factory_id == "huakang-a")
    ).one()
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    result = {
        "factory_id": "huakang-a",
        "site_id": connection.site_id,
        "printer_id": printer_id,
        "from": connection.connection_owner,
        "to": target,
        "connection_revision": connection.connection_revision,
        "database_revision": revision,
        "record_watermark": list(records),
        "connection_fingerprint": fingerprint(
            [
                connection.lan_host,
                connection.mqtt_port,
                connection.credential_ref,
                connection.certificate_fingerprint,
            ]
        ),
    }
    return {**result, "plan_hash": fingerprint(result)}


def apply(db, reviewed, *, backup, actor, reason, writers_stopped=False):
    if not writers_stopped or not actor.strip() or not reason.strip():
        raise ValueError("Physical writer-stop evidence, operator and reason required")
    if len(actor) > 64 or len(reason) > 500:
        raise ValueError("Operator/reason too long")
    spec = importlib.util.spec_from_file_location(
        "recovery", Path(__file__).with_name("recovery.py")
    )
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    manifest = recovery.verify(backup)
    age = (
        datetime.now(timezone.utc) - datetime.fromisoformat(manifest["created_at"])
    ).total_seconds()
    if not 0 <= age <= 1800:
        raise ValueError("A verified backup from the last 30 minutes is required")
    if manifest["revision"] != reviewed["database_revision"]:
        raise ValueError("Backup revision mismatch")
    try:
        db.execute(
            update(m.ThreeDPrintingSetting)
            .where(m.ThreeDPrintingSetting.factory_id == "huakang-a")
            .values(revision=m.ThreeDPrintingSetting.revision)
        )
        db.expire_all()
        current = plan(db, reviewed["printer_id"], reviewed["to"])
        if current != reviewed:
            raise ValueError("Plan became stale; review a new plan and backup")
        connection = db.get(m.ThreeDPrintingPrinterConnection, reviewed["printer_id"])
        printer = db.get(m.ThreeDPrintingPrinter, connection.printer_id)
        opened = db.scalar(
            select(func.count())
            .select_from(m.ThreeDPrintingProductionRecord)
            .where(
                m.ThreeDPrintingProductionRecord.factory_id == "huakang-a",
                m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                m.ThreeDPrintingProductionRecord.deleted_at == "",
                m.ThreeDPrintingProductionRecord.run_status.in_(
                    ["running", "paused", "unknown", "pending"]
                ),
            )
        )
        commands = db.scalar(
            select(func.count())
            .select_from(m.ThreeDPrintingPrinterCommand)
            .where(
                m.ThreeDPrintingPrinterCommand.printer_id == printer.id,
                m.ThreeDPrintingPrinterCommand.status.in_(
                    ["queued", "leased", "dispatching", "sent", "pending", "claimed"]
                ),
            )
        )
        if opened or commands:
            raise ValueError(
                "Open runs or commands must be reconciled before ownership transfer"
            )
        if reviewed["to"] == "cloud-connector":
            health = network_health_snapshot(db)
            if not health["configured"] or health["status"] != "healthy":
                raise ValueError("Fresh verified site network evidence required")
            if (
                len(connection.certificate_fingerprint.replace(":", "")) != 64
                or not connection.credential_ref
            ):
                raise ValueError("Pinned certificate and credential reference required")
        connection.connection_owner = reviewed["to"]
        connection.connection_enabled = reviewed["to"] == "cloud-connector"
        connection.connection_revision += 1
        connection.leader_instance_id = None
        connection.leader_lease_id = ""
        connection.leader_leased_until = ""
        printer.connected = False
        printer.state = "STALE"
        db.add(
            m.ThreeDPrintingAuditEvent(
                id="cutover-" + reviewed["plan_hash"][:48],
                factory_id="huakang-a",
                entity_type="printer_ownership",
                entity_id=printer.id,
                action="transfer",
                actor_id=actor,
                actor_name=actor,
                actor_type="operator",
                detail_json=json.dumps(
                    {
                        "plan": reviewed,
                        "backup_batch": manifest["batch_id"],
                        "reason": reason,
                        "writers_stopped_asserted": True,
                    }
                ),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        db.commit()
        return {
            "status": "ownership_transferred_services_unchanged",
            "printer_id": printer.id,
            "owner": reviewed["to"],
            "revision": connection.connection_revision,
        }
    except Exception:
        db.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-file", required=True)
    parser.add_argument("--printer-id", required=True)
    parser.add_argument(
        "--owner", choices=["cloud-connector", "edge-legacy"], required=True
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup")
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    engine = create_engine(
        Path(args.database_url_file).read_text(encoding="utf-8-sig").strip(),
        hide_parameters=True,
    )
    with Session(engine) as db:
        if not args.execute:
            result = plan(db, args.printer_id, args.owner)
            with Path(args.plan).open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
        else:
            reviewed = json.loads(Path(args.plan).read_text(encoding="utf-8"))
            if (
                reviewed["printer_id"] != args.printer_id
                or reviewed["to"] != args.owner
            ):
                raise ValueError("Arguments differ from reviewed plan")
            result = apply(
                db,
                reviewed,
                backup=args.backup,
                actor=args.actor,
                reason=args.reason,
                writers_stopped=args.writers_stopped,
            )
    engine.dispose()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
