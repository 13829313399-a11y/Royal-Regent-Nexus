"""The 72-hour raw journal, durable event samples and their narrow statistical facts."""
import hashlib
import json
from datetime import timedelta

from sqlalchemy import literal, select, union_all

from app.core.time import parse_business_timestamp
from app.models import three_d_printing as m

KEEP_DAYS = 3
CHECKPOINT = timedelta(minutes=1)
FULL_EVENT = 1
JOURNAL_FRAME = 2
RETAINED_EVIDENCE = 3


def payload_digest(encoded):
    return hashlib.sha256(encoded.encode("utf-8")).digest()


def compact_payload(encoded):
    body = json.loads(encoded)
    evidence = {"device_job_key": body.get("device_job_key", ""),
                "connected": body.get("connected", False),
                "_sha256": payload_digest(encoded).hex()}
    if (body.get("state") in {"FAILED", "ERROR", "UNKNOWN", "STALE"}
            or body.get("error_code") not in (None, "", "0")
            or (body.get("nozzle_temperature") or 0) > 320 or (body.get("bed_temperature") or 0) > 130):
        for field in ("nozzle_target", "bed_target", "layer_num", "total_layers", "live_material"):
            if field in body:
                evidence[field] = body[field]
    return json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))


def body_matches(event, encoded):
    if event.payload_version == RETAINED_EVIDENCE:
        return json.loads(event.raw_payload_json).get("_sha256") == payload_digest(encoded).hex()
    return event.raw_payload_json == encoded


def history_policy(printer, meta, payload, now, *, dispatching):
    """Return (keep detail, preserve previous boundary) before updating the live printer."""
    previous_seen = parse_business_timestamp(meta.get("observed_at"))
    anchor = parse_business_timestamp(meta.get("history_anchor_at"))
    nozzle, bed = payload.nozzle_temperature, payload.bed_temperature
    boundary = (
        meta.get("history_session_id") != payload.connection_session_id
        or payload.state != printer.state or payload.connected != printer.connected
        or payload.current_file != printer.current_file
        or payload.device_job_key != meta.get("device_job_key", "")
        or (payload.error_code or "") != (printer.error_text or "")
        or payload.live_material != printer.live_material
        or payload.progress_percent < (printer.progress_percent or 0)
        or (payload.progress_percent == 100 and printer.progress_percent != 100)
        or not previous_seen or not payload.observed_at
        or payload.observed_at <= previous_seen
        or (payload.observed_at - previous_seen).total_seconds() > 30
        or (nozzle > 320 or bed > 130) !=
           (float(printer.nozzle_temperature or 0) > 320 or float(printer.bed_temperature or 0) > 130)
    )
    important = (not payload.connected or payload.state in {"FAILED", "ERROR", "UNKNOWN", "STALE"}
                 or payload.error_code not in ("", "0") or nozzle > 320 or bed > 130)
    return (boundary or important or dispatching or not anchor or now < anchor or now - anchor >= CHECKPOINT,
            boundary)


def promote(event):
    if event is None or event.payload_version != JOURNAL_FRAME:
        return
    raw = json.loads(event.raw_payload_json)
    event.progress = raw["progress_percent"]
    event.remaining_minutes = raw["remaining_minutes"]
    event.current_file = raw["current_file"]
    event.temperatures_json = json.dumps(
        {"bed": raw["bed_temperature"], "nozzle": raw["nozzle_temperature"]}, separators=(",", ":")
    )
    event.payload_version = FULL_EVENT


def recent_detail(event):
    if event.payload_version == JOURNAL_FRAME:
        body = json.loads(event.raw_payload_json)
        return body["progress_percent"], body["current_file"]
    return event.progress, event.current_file


def statistical_frames():
    """One SQL snapshot of journal/detail rows plus ordinary frames moved out of that table."""
    event, tick = m.ThreeDPrintingPrinterStateEvent, m.ThreeDPrintingTelemetryTick
    return union_all(
        select(event.factory_id, event.machine_no, event.observed_at, event.received_at, event.id, event.state, event.error_code,
               event.temperatures_json),
        select(tick.factory_id, tick.machine_no, tick.observed_at, tick.received_at, tick.id, tick.state,
               literal("").label("error_code"), literal("{}").label("temperatures_json")),
    ).subquery().c
