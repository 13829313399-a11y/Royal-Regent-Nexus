"""Device evidence updates runs exactly once; ambiguity never implies completion."""

import json
from dataclasses import dataclass, field
from hashlib import sha256

from sqlalchemy import select

from app.core.config import settings
from app.core.time import parse_business_timestamp
from app.models import three_d_printing as m

# Ported from the legacy standalone server's transition guard. The old process
# observed every printer itself; here the same conclusion is drawn from the
# printer row, which only the owner-marked Connector session may advance.
SETTLEABLE_DEVICE_STATES = {"FINISH", "FAILED", "ERROR", "IDLE", "STOPPED", "CANCELLED"}


def _load_json(value, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


@dataclass
class SweepResult:
    """Evidence for settling open runs that received no terminal event."""

    checked: int = 0
    eligible: int = 0
    settled: list = field(default_factory=list)
    settled_for_other_job: list = field(default_factory=list)
    awaiting_evidence: list = field(default_factory=list)
    stale_open: list = field(default_factory=list)

    def as_dict(self):
        return {
            "checked": self.checked,
            "eligible": self.eligible,
            "settled": self.settled,
            "settled_for_other_job": self.settled_for_other_job,
            "awaiting_evidence": self.awaiting_evidence,
            "stale_open": self.stale_open,
        }


def job_key(printer_id, device_key):
    if not device_key.strip() or device_key.strip() in {"0", "-1"}:
        return None
    return "bambu-" + sha256((printer_id + ":" + device_key).encode()).hexdigest()


def reconcile_event(db, printer, event, actor, now, *, connected):
    # Caller locks factory settings BEFORE printer, matching manual inventory writes.
    from app.services import three_d_printing as business
    from app.services.three_d_connector import (
        FACTORY,
        SITE,
        audit,
        encode,
        notify,
        stamp,
    )

    key = job_key(printer.id, event.device_job_key)
    records = list(
        db.scalars(
            select(m.ThreeDPrintingProductionRecord)
            .where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                m.ThreeDPrintingProductionRecord.auto_record.is_(True),
                m.ThreeDPrintingProductionRecord.print_end_at == "",
                m.ThreeDPrintingProductionRecord.deleted_at == "",
            )
            .with_for_update()
        )
    )

    def mark(record, flag):
        flags = set(json.loads(record.data_quality_flags_json))
        if flag in flags and record.reconciliation_status == "pending":
            return
        flags.add(flag)
        record.data_quality_flags_json = encode(sorted(flags))
        record.reconciliation_status = "pending"
        record.run_status = "unknown"
        record.updated_at = stamp(now)
        record.revision += 1
        audit(
            db,
            "production_record",
            record.id,
            "reconciliation_pending",
            {"reason": flag},
            actor,
            now,
        )
        notify(db, "print_run", record.id)

    if not connected or event.state in {"STALE", "UNKNOWN"}:
        for record in records:
            mark(record, "pending_device_reconciliation")
        return

    # Migration/Edge open records without proven device identity must be reviewed first.
    ambiguous = [
        record
        for record in records
        if record.source_system != "cloud-connector" and record.device_job_key != key
    ]
    if ambiguous:
        for record in ambiguous:
            mark(record, "pending_device_reconciliation")
        return
    record = (
        db.scalar(
            select(m.ThreeDPrintingProductionRecord).where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.device_job_key == key,
            )
        )
        if key
        else next((item for item in records if item.device_job_key is None), None)
    )
    for other in records:
        if other is not record:
            mark(other, "device_job_changed_without_end")
    if record and (record.deleted_at or record.print_end_at):
        # Deleted/terminal task identities never create a second record or re-consume.
        return
    if not key:
        if record:
            mark(record, "device_identity_missing")
        elif event.state == "RUNNING":
            audit(
                db,
                "printer_reconciliation",
                printer.id,
                "identity_missing",
                {"event_id": event.event_id, "reason": "device_identity_missing"},
                actor,
                now,
            )
        return
    if record is None:
        if event.state != "RUNNING":
            return
        normalized = business._normalize_gcode_name(event.current_file)
        candidates = (
            list(
                db.scalars(
                    select(m.ThreeDPrintingProduct).where(
                        m.ThreeDPrintingProduct.factory_id == FACTORY,
                        m.ThreeDPrintingProduct.is_active.is_(True),
                        m.ThreeDPrintingProduct.name == normalized,
                    )
                )
            )
            if normalized
            else []
        )
        product = candidates[0] if len(candidates) == 1 else None
        # The legacy server fell back to a contains match after the exact one. Keep that
        # fallback but only accept a unique candidate, so two similarly named products
        # still require a human instead of being guessed. This also covers a name that
        # resolved to nothing before normalization (a plate marker plus a suffix).
        if product is None and normalized:
            relaxed = [
                item
                for item in db.scalars(
                    select(m.ThreeDPrintingProduct).where(
                        m.ThreeDPrintingProduct.factory_id == FACTORY,
                        m.ThreeDPrintingProduct.is_active.is_(True),
                    )
                )
                if len(item.name or "") >= 3
                and (normalized in item.name or item.name in normalized)
            ]
            if len(relaxed) == 1:
                product = relaxed[0]
                candidates = relaxed
        file_version = None
        alias = db.scalar(select(m.ThreeDPrintingOperationsItem).where(
            m.ThreeDPrintingOperationsItem.factory_id == FACTORY,
            m.ThreeDPrintingOperationsItem.kind == "file_alias",
            m.ThreeDPrintingOperationsItem.status == "active",
            m.ThreeDPrintingOperationsItem.resource_key == sha256(event.current_file.replace("\\", "/").rsplit("/", 1)[-1].strip().casefold().encode()).hexdigest()))
        if alias:
            mapping = json.loads(alias.data_json)
            linked = db.get(m.ThreeDPrintingProduct, mapping["product_id"])
            if linked and linked.factory_id == FACTORY and linked.is_active:
                product = linked
                file_version = {**mapping, "alias_id": alias.id, "alias_revision": alias.revision}
        observed = stamp(event.observed_at)
        flags = [] if product else ["product_match_required"]
        day = db.scalar(
            select(m.ThreeDPrintingDayStatus).where(
                m.ThreeDPrintingDayStatus.factory_id == FACTORY,
                m.ThreeDPrintingDayStatus.business_date
                == parse_business_timestamp(observed).date().isoformat(),
            )
        )
        if day and day.is_day_off:
            audit(
                db,
                "printer_reconciliation",
                printer.id,
                "day_off_conflict",
                {"event_id": event.event_id},
                actor,
                now,
            )
            return
        record = m.ThreeDPrintingProductionRecord(
            id="3drun-" + sha256(key.encode()).hexdigest()[:48],
            factory_id=FACTORY,
            site_id=SITE,
            device_job_key=key,
            source_system="cloud-connector",
            auto_record=True,
            business_date=parse_business_timestamp(observed).date().isoformat(),
            machine_no=printer.machine_no,
            status="running",
            run_status="running",
            reconciliation_status="pending" if flags else "resolved",
            product_id=product.id if product else "",
            product_name=product.name if product else normalized or "待匹配产品",
            material_name=product.material_name if product else event.live_material,
            weight_g=product.weight_g if product else 0,
            quantity=product.default_quantity if product else 1,
            duration_hours=product.duration_hours if product else 0,
            quoted_price=product.quoted_price if product else 0,
            design_fee=0,
            customer=product.customer if product else "",
            remark="",
            print_start_at=observed,
            print_end_at="",
            gcode_file=event.current_file,
            inventory_consumed=False,
            data_quality_flags_json=encode(flags),
            revision=1,
            created_by=actor[:64],
            created_by_name="云端打印机连接器",
            created_at=stamp(now),
            updated_at=stamp(now),
        )
        db.add(record)
        db.flush()
        manual = _already_recorded_same_product(db, printer, event, product, observed, record)
        if manual is not None:
            # The run is already covered by a hand-entered record for the same machine,
            # business day and product, so this observation only attaches that identity.
            flags = _record_flags(manual)
            flags.add("observed_run_linked_to_existing_record")
            manual.reconciliation_status = "pending"
            manual.data_quality_flags_json = encode(sorted(flags))
            manual.updated_at = stamp(now)
            manual.revision += 1
            db.delete(record)
            audit(
                db,
                "production_record",
                manual.id,
                "link_observed_run_to_existing_record",
                {
                    "event_id": event.event_id,
                    "device_job_key": key,
                    "current_file": event.current_file,
                    "product_id": product.id,
                    "business_date": manual.business_date,
                },
                actor,
                now,
            )
            notify(db, "print_run", manual.id)
            return
        resumed = _resumable_same_file_record(db, printer, event, now, exclude=record)
        if resumed is not None:
            # Ported from the legacy server's reprint window: the same file on the same
            # machine within the window is one physical run even if the device job id
            # changed (reprint after a finish, or a Connector restart that lost the id).
            flags = _record_flags(resumed)
            flags.add("device_job_changed_same_file")
            resumed.reconciliation_status = "pending"
            resumed.data_quality_flags_json = encode(sorted(flags))
            resumed.updated_at = stamp(now)
            resumed.revision += 1
            db.delete(record)
            audit(
                db,
                "production_record",
                resumed.id,
                "resume_same_file_run",
                {
                    "event_id": event.event_id,
                    "device_job_key": key,
                    "current_file": event.current_file,
                    "flags": sorted(flags),
                },
                actor,
                now,
            )
            notify(db, "print_run", resumed.id)
            return
        business._consume_record(
            db, record, actor, "云端打印机连接器", "云端任务首次运行扣料"
        )
        business.freeze_cost(
            record,
            business.ensure_settings(db, FACTORY),
            business._material_by_name(db, FACTORY, record.material_name),
            initial=True,
        )
        audit(
            db,
            "production_record",
            record.id,
            "auto_create",
            {
                "event_id": event.event_id,
                "match_method": "approved_alias" if file_version else "exact_name" if product else "unmatched",
                "file_version": file_version,
                "match_confidence": 1 if product else 0,
                "candidates": [p.id for p in candidates],
            },
            actor,
            now,
        )
        notify(db, "print_run", record.id)
        return
    if event.state == "IDLE":
        mark(record, "completion_evidence_missing")
        return
    states = {
        "RUNNING": "running",
        "PAUSE": "paused",
        "FINISH": "succeeded",
        "FAILED": "failed",
        "ERROR": "failed",
    }
    target = states.get(event.state)
    if target is None:
        return
    flags = set(json.loads(record.data_quality_flags_json))
    flags.difference_update(
        {"pending_device_reconciliation", "completion_evidence_missing"}
    )
    reconciliation = "pending" if flags else "resolved"
    if record.run_status == target and record.reconciliation_status == reconciliation:
        return
    record.run_status, record.reconciliation_status = target, reconciliation
    record.data_quality_flags_json = encode(sorted(flags))
    if target in {"succeeded", "failed"}:
        record.print_end_at = stamp(event.observed_at)
        if target == "failed":
            record.remark = (record.remark + " 打印失败").strip()
    record.revision += 1
    record.updated_at = stamp(now)
    audit(
        db,
        "production_record",
        record.id,
        "auto_reconcile",
        {"state": target, "event_id": event.event_id},
        actor,
        now,
    )
    notify(db, "print_run", record.id)


def _record_flags(record):
    return set(_load_json(record.data_quality_flags_json, []))


def _resumable_same_file_record(db, printer, event, now, exclude=None):
    """A run already recorded for this machine and file inside the reprint window.

    Only a record whose file matches and whose end is missing or recent qualifies: an
    identical file printed again after the window is a real second run. `exclude` drops
    the row this call is about to insert, which the flush has already made visible.
    """
    gcode = (event.current_file or "").strip()
    if not gcode:
        return None
    from app.services.three_d_connector import FACTORY

    window = settings.three_d_reconciliation_same_file_window_seconds
    existing = list(
        db.scalars(
            select(m.ThreeDPrintingProductionRecord)
            .where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                m.ThreeDPrintingProductionRecord.gcode_file == gcode,
                m.ThreeDPrintingProductionRecord.auto_record.is_(True),
                m.ThreeDPrintingProductionRecord.deleted_at == "",
            )
            .order_by(m.ThreeDPrintingProductionRecord.created_at.desc())
        )
    )
    for candidate in existing:
        if exclude is not None and candidate.id == exclude.id:
            continue
        if not candidate.print_end_at:
            return candidate
        ended = parse_business_timestamp(candidate.print_end_at)
        if ended is not None and (now - ended).total_seconds() <= window:
            return candidate
    return None


def _same_product(name_a, name_b):
    """Whether a device file name and a product name denote the same part.

    Both sides lose their plate marker first. A device name is often a truncation of the
    hand-entered product name, so containment counts as long as the shorter side is still
    distinctive; short fragments would merge unrelated parts, so they never qualify.
    """
    from app.services import three_d_printing as business

    left = business._normalize_gcode_name(name_a or "").casefold()
    right = business._normalize_gcode_name(name_b or "").casefold()
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 8 and shorter in longer


def _already_recorded_same_product(db, printer, event, product, observed, exclude):
    """A record already covering this machine, business day and product.

    Operators record many prints by hand while observation is not recording. When such
    a record already exists for the same machine, business day and product, the run is
    that record rather than a second empty one; only an exact normalized product name
    qualifies, so a genuinely different part is never merged away.
    """
    if product is None or not product.name:
        return None
    from app.services.three_d_connector import FACTORY

    business_date = parse_business_timestamp(observed).date().isoformat()
    candidates = list(
        db.scalars(
            select(m.ThreeDPrintingProductionRecord)
            .where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                m.ThreeDPrintingProductionRecord.business_date == business_date,
                m.ThreeDPrintingProductionRecord.print_end_at == "",
                m.ThreeDPrintingProductionRecord.deleted_at == "",
                m.ThreeDPrintingProductionRecord.product_id == product.id,
            )
            .order_by(m.ThreeDPrintingProductionRecord.created_at.desc())
        )
    )
    for candidate in candidates:
        if exclude is not None and candidate.id == exclude.id:
            continue
        if candidate.device_job_key is None and _same_product(
            event.current_file, product.name
        ):
            return candidate
    return None


def apply_telemetry_backfill(db, printer, event, actor, now):
    """Fill product identity and material for records created before telemetry arrived.

    The legacy server retried the gcode match on later status frames; the same retry
    keeps a run from staying at "待匹配产品" just because the first frame was thin.
    """
    from app.services.three_d_connector import FACTORY, audit, encode, notify, stamp
    from app.services import three_d_printing as business

    touched = []
    records = list(
        db.scalars(
            select(m.ThreeDPrintingProductionRecord).where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                m.ThreeDPrintingProductionRecord.auto_record.is_(True),
                m.ThreeDPrintingProductionRecord.deleted_at == "",
                m.ThreeDPrintingProductionRecord.print_end_at == "",
            )
        )
    )
    if not records:
        return touched
    gcode = (event.current_file or "").strip()
    for record in records:
        flags = _record_flags(record)
        changed = False
        if not record.gcode_file and gcode:
            record.gcode_file = gcode
            changed = True
        matched = None
        uncertain_name = (
            not (record.product_name or "").strip()
            or record.product_name == "待匹配产品"
            or record.product_name == business._normalize_gcode_name(gcode)
        )
        if not record.product_id and gcode and uncertain_name:
            # Only resolve a name that was never pinned to a product. An ambiguous
            # product name must stay unresolved until an operator confirms it.
            normalized = business._normalize_gcode_name(gcode)
            named = (
                list(
                    db.scalars(
                        select(m.ThreeDPrintingProduct).where(
                            m.ThreeDPrintingProduct.factory_id == FACTORY,
                            m.ThreeDPrintingProduct.is_active.is_(True),
                            m.ThreeDPrintingProduct.name == normalized,
                        )
                    )
                )
                if normalized
                else []
            )
            matched = named[0] if len(named) == 1 else None
            if matched is not None:
                record.product_id = matched.id
                record.product_name = matched.name
                record.weight_g = matched.weight_g
                record.quantity = matched.default_quantity
                record.duration_hours = matched.duration_hours
                record.quoted_price = matched.quoted_price
                record.design_fee = 0
                record.customer = matched.customer
                # The product is authoritative for its own material, including an empty
                # value that lets the device report the loaded filament instead.
                record.material_name = matched.material_name or ""
                flags.discard("product_match_required")
                changed = True
        material = (record.material_name or "").strip()
        if not material and event.live_material:
            record.material_name = event.live_material.strip()
            flags.add("material_source_device")
            changed = bool(record.material_name)
        if not changed:
            continue
        record.data_quality_flags_json = encode(sorted(flags))
        record.updated_at = stamp(now)
        record.revision += 1
        touched.append(record.id)
        audit(
            db,
            "production_record",
            record.id,
            "telemetry_backfill",
            {
                "event_id": event.event_id,
                "product_matched": bool(matched),
                "material": record.material_name,
            },
            actor,
            now,
        )
        notify(db, "print_run", record.id)
    return touched


def _settle_open_record(
    db,
    record,
    *,
    state,
    evidence,
    actor,
    observed_at,
    now,
):
    from app.services.three_d_connector import audit, encode, notify, stamp

    flags = _record_flags(record)
    flags.discard("pending_device_reconciliation")
    flags.discard("completion_evidence_missing")
    if state == "FINISH":
        record.run_status = "succeeded"
        flags.add("closed_by_state_sweep")
    elif state in {"FAILED", "ERROR"}:
        record.run_status = "failed"
    else:
        flags.add("completion_evidence_missing")
    record.reconciliation_status = "pending" if flags else "resolved"
    record.data_quality_flags_json = encode(sorted(flags))
    if record.run_status == "failed" and "打印失败" not in record.remark:
        record.remark = (record.remark + " 打印失败").strip()
    record.print_end_at = observed_at
    record.updated_at = stamp(now)
    record.revision += 1
    audit(
        db,
        "production_record",
        record.id,
        "auto_settle_from_state",
        {"state": state, "evidence": evidence},
        actor,
        now,
    )
    notify(db, "print_run", record.id)


def sweep_open_runs(
    db,
    *,
    factory_id,
    now,
    actor="system:state-sweep",
    ignore_state_since=False,
    apply_start_guard=False,
):
    """Close runs whose printer already finished without an explicit terminal event.

    A push-only Connector can miss the FINISH frame during an outage, a crash or a
    reconnect, which used to leave the daily record open forever. The legacy
    standalone server closed those runs from observed state; this is the same
    conclusion restricted to record-enabled printers that are stale-free.

    `ignore_state_since` is the boot/reconnect settlement variant: the persisted
    printer row already carries a fresh full status pushed on connect, so an open run
    is settled from that state without additionally waiting for a quiet window. The
    rollout start guard is not applied here by default: the sweep only closes records
    that already exist and were created under the guard, so re-checking it would stop
    the sweep from ever completing the very runs it opened.
    """
    from app.services.three_d_connector import (
        FACTORY,
        metadata,
        record_reconcile_allowed,
        stamp,
    )
    from app.services.three_d_network_health import network_blocks_control

    result = SweepResult()
    if factory_id != FACTORY or network_blocks_control(db):
        return result
    grace = (
        0
        if ignore_state_since
        else settings.three_d_reconciliation_terminal_grace_seconds
    )
    stale_after = settings.three_d_reconciliation_stale_open_seconds
    for printer in db.scalars(
        select(m.ThreeDPrintingPrinter).where(
            m.ThreeDPrintingPrinter.factory_id == FACTORY
        )
    ):
        connection = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
        # Recording is gated by the connection's own record flag, never by ownership:
        # an observation-only connection may settle runs while control stays refused.
        # The sweep closes records that already exist, so the rollout start guard is
        # only re-checked when the caller explicitly asks for it.
        if connection is None or not record_reconcile_allowed(
            connection, None, start_guard=apply_start_guard
        ):
            continue
        info = metadata(printer)
        observed_raw = info.get("observed_at") or ""
        observed_at = parse_business_timestamp(observed_raw) if observed_raw else None
        if observed_at is None or (now - observed_at).total_seconds() > 30:
            continue
        result.checked += 1
        if printer.state not in SETTLEABLE_DEVICE_STATES:
            continue
        if since_raw := (info.get("state_since") or ""):
            since = parse_business_timestamp(since_raw)
        else:
            since = None
        if since is None or (now - since).total_seconds() < grace:
            # No proof the printer has been quiet long enough yet.
            continue
        result.eligible += 1
        # Never close a run younger than the printer's own quiet window.
        close_at = max(observed_at, since)
        key = job_key(printer.id, info.get("device_job_key", ""))
        open_records = list(
            db.scalars(
                select(m.ThreeDPrintingProductionRecord)
                .where(
                    m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                    m.ThreeDPrintingProductionRecord.machine_no == printer.machine_no,
                    m.ThreeDPrintingProductionRecord.auto_record.is_(True),
                    m.ThreeDPrintingProductionRecord.print_end_at == "",
                    m.ThreeDPrintingProductionRecord.deleted_at == "",
                )
                .order_by(m.ThreeDPrintingProductionRecord.created_at.desc())
                .with_for_update()
            )
        )
        if not open_records:
            continue
        same_job = next(
            (item for item in open_records if key and item.device_job_key == key), None
        )
        others = [item for item in open_records if item is not same_job]
        if (
            same_job is not None
            and parse_business_timestamp(same_job.print_start_at) is not None
            and (close_at - parse_business_timestamp(same_job.print_start_at)).total_seconds()
            < grace
        ):
            result.awaiting_evidence.append(same_job.id)
            continue
        if same_job is not None:
            _settle_open_record(
                db,
                same_job,
                state=printer.state,
                evidence="device_state_terminal",
                actor=actor,
                observed_at=stamp(close_at),
                now=now,
            )
            result.settled.append(same_job.id)
        for item in others:
            started = parse_business_timestamp(item.print_start_at)
            if started is not None and (close_at - started).total_seconds() < grace:
                result.awaiting_evidence.append(item.id)
                continue
            known = _record_flags(item) | {"device_job_changed_without_end"}
            item.data_quality_flags_json = json.dumps(sorted(known), ensure_ascii=False)
            _settle_open_record(
                db,
                item,
                state=printer.state,
                evidence="device_job_changed",
                actor=actor,
                observed_at=stamp(close_at),
                now=now,
            )
            result.settled_for_other_job.append(item.id)
        for item in open_records:
            if item.print_end_at:
                continue
            started = parse_business_timestamp(item.print_start_at)
            if started is not None and (now - started).total_seconds() >= stale_after:
                result.stale_open.append(item.id)
    return result
