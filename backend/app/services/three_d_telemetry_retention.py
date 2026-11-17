"""Bound raw printer reports by reception time without changing production records."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.models import three_d_printing as m
from app.services import three_d_telemetry_storage as storage

FACTORY = "huakang-a"
LOCK_KEY = 531603702
Event = m.ThreeDPrintingPrinterStateEvent
Tick = m.ThreeDPrintingTelemetryTick
Cursor = m.ThreeDPrintingRetentionCursor


def cutoff_for(days, now=None):
    if days < storage.KEEP_DAYS:
        raise ValueError("Minimum full-report retention is three days")
    clock = now or datetime.now(UTC)
    return (clock - timedelta(days=days)).astimezone(UTC).isoformat(timespec="milliseconds")


def lock(db):
    return (db.bind.dialect.name != "postgresql" or
            db.scalar(text("select pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}))


def retire_rows(db, rows, printer):
    transient_ids = [r.id for r in rows if r.payload_version == storage.JOURNAL_FRAME]
    protected = set()
    if transient_ids:
        protected.update(db.scalars(select(m.ThreeDPrintingInventoryMovement.source_event_id).where(
            m.ThreeDPrintingInventoryMovement.factory_id == FACTORY,
            m.ThreeDPrintingInventoryMovement.source_event_id.in_(transient_ids),
        )))
        meta = json.loads(printer.status_payload_json or "{}").get("connector", {})
        protected.add(meta.get("last_state_event_id"))
    moved = shortened = 0
    for row in rows:
        if row.payload_version not in (storage.FULL_EVENT, storage.JOURNAL_FRAME) or row.raw_payload_json == "{}":
            continue
        if row.payload_version == storage.JOURNAL_FRAME and row.id not in protected:
            # Classification retains errors, threshold excursions, transitions, command
            # evidence, and events cited in business audits in the full history.
            body = json.loads(row.raw_payload_json)
            if (body["connected"] and row.observed_at and row.error_code in ("", "0")
                    and row.state not in {"FAILED", "ERROR", "UNKNOWN", "STALE"}
                    and body["nozzle_temperature"] <= 320 and body["bed_temperature"] <= 130):
                db.add(Tick(id=row.id, factory_id=row.factory_id, machine_no=row.machine_no,
                            observed_at=row.observed_at, received_at=row.received_at, state=row.state,
                            payload_digest=storage.payload_digest(row.raw_payload_json)))
                db.delete(row)
                moved += 1
                continue
        storage.promote(row)
        row.raw_payload_json = storage.compact_payload(row.raw_payload_json)
        row.payload_version = storage.RETAINED_EVIDENCE
        shortened += 1
    return shortened, moved


def printer_batch(db, printer, cutoff, limit, *, execute):
    key = {"factory_id": FACTORY, "printer_id": printer.id}
    cursor = db.get(Cursor, key, with_for_update=execute)
    low, last = (cursor.received_at, cursor.event_id) if cursor else ("", "")
    query = select(Event).where(
        Event.factory_id == FACTORY, Event.printer_id == printer.id,
        Event.received_at >= low, Event.received_at < cutoff,
        or_(Event.received_at > low, and_(Event.received_at == low, Event.id > last)),
    ).order_by(Event.received_at, Event.id).limit(limit)
    if execute:
        query = query.with_for_update()
    else:
        query = query.where(Event.payload_version.in_((storage.FULL_EVENT, storage.JOURNAL_FRAME)),
                            Event.raw_payload_json != "{}")
    rows = list(db.scalars(query))
    if not execute or not rows:
        return len(rows), 0, 0
    high = (rows[-1].received_at, rows[-1].id)
    shortened, moved = retire_rows(db, rows, printer)
    if cursor is None:
        cursor = Cursor(**key)
        db.add(cursor)
    cursor.received_at, cursor.event_id = high
    return len(rows), shortened, moved


def process_due(engine, *, days=storage.KEEP_DAYS, batch_per_printer=180, now=None):
    """One small indexed transaction per device. Other workers can safely retry."""
    cutoff = cutoff_for(days, now)
    with Session(engine) as db:
        ids = list(db.scalars(select(m.ThreeDPrintingPrinter.id).where(
            m.ThreeDPrintingPrinter.factory_id == FACTORY).order_by(m.ThreeDPrintingPrinter.id)))
    totals = [0, 0, 0]
    for printer_id in ids:
        with Session(engine) as db, db.begin():
            if not lock(db):
                return totals
            printer = db.get(m.ThreeDPrintingPrinter, printer_id)
            if printer is None:
                continue
            result = printer_batch(db, printer, cutoff, batch_per_printer, execute=True)
            totals = [a + b for a, b in zip(totals, result)]
    return totals
