"""Device evidence updates runs exactly once; ambiguity never implies completion."""

import json
from hashlib import sha256

from sqlalchemy import select

from app.core.time import parse_business_timestamp
from app.models import three_d_printing as m


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
