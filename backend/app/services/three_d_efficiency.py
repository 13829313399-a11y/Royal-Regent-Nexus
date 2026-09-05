"""Evidence-limited runtime counters. Gaps over 120 seconds remain unobserved."""

import json
from collections import Counter
from datetime import timedelta, timezone

from sqlalchemy import select

from app.core.time import business_now, parse_business_timestamp
from app.models import three_d_printing as m


def counters(db, days):
    now = business_now()
    begin = now - timedelta(days=days)
    values = {
        n: {
            "pause_hours": 0.0,
            "waiting_hours": 0.0,
            "observed_hours": 0.0,
            "temperature_alarm_events": 0,
            "error_events": 0,
            "failure_codes": Counter(),
            "lifetime_hours_since_service": 0.0,
        }
        for n in range(1, 12)
    }
    previous = {}
    events = db.scalars(
        select(m.ThreeDPrintingPrinterStateEvent)
        .where(
            m.ThreeDPrintingPrinterStateEvent.factory_id == "huakang-a",
            m.ThreeDPrintingPrinterStateEvent.observed_at
            >= begin.astimezone(timezone.utc).isoformat(),
        )
        .order_by(
            m.ThreeDPrintingPrinterStateEvent.machine_no,
            m.ThreeDPrintingPrinterStateEvent.observed_at,
        )
    ).yield_per(500)
    for event in events:
        if event.machine_no not in values:
            continue
        result = values[event.machine_no]
        timestamp = parse_business_timestamp(event.observed_at)
        if not timestamp or timestamp > now:
            continue
        prior = previous.get(event.machine_no)
        if prior:
            elapsed = (timestamp - prior[0]).total_seconds()
            if 0 <= elapsed <= 120:
                result["observed_hours"] += elapsed / 3600
                if prior[1] == "PAUSE":
                    result["pause_hours"] += elapsed / 3600
                if prior[1] in {"IDLE", "FINISH"}:
                    result["waiting_hours"] += elapsed / 3600
        previous[event.machine_no] = (timestamp, event.state)
        if event.error_code and event.error_code != "0":
            result["error_events"] += 1
            result["failure_codes"][event.error_code] += 1
        temperatures = json.loads(event.temperatures_json or "{}")
        if (
            float(temperatures.get("nozzle", 0)) > 320
            or float(temperatures.get("bed", 0)) > 130
        ):
            result["temperature_alarm_events"] += 1
    maintained = {}
    for item in db.scalars(
        select(m.ThreeDPrintingMaintenance).where(
            m.ThreeDPrintingMaintenance.factory_id == "huakang-a"
        )
    ):
        maintained[item.machine_no] = max(
            maintained.get(item.machine_no, ""), item.business_date
        )
    runs = db.scalars(
        select(m.ThreeDPrintingProductionRecord).where(
            m.ThreeDPrintingProductionRecord.factory_id == "huakang-a",
            m.ThreeDPrintingProductionRecord.deleted_at == "",
            m.ThreeDPrintingProductionRecord.print_end_at != "",
        )
    ).yield_per(500)
    for run in runs:
        if run.machine_no not in values or run.business_date <= maintained.get(
            run.machine_no, ""
        ):
            continue
        start, end = (
            parse_business_timestamp(run.print_start_at),
            parse_business_timestamp(run.print_end_at),
        )
        if start and end and start < end <= now:
            values[run.machine_no]["lifetime_hours_since_service"] += (
                end - start
            ).total_seconds() / 3600
    for result in values.values():
        result["failure_codes"] = dict(result["failure_codes"].most_common(10))
        result["maintenance_reasons"] = (
            ["temperature_threshold_exceeded"]
            if result["temperature_alarm_events"]
            else []
        ) + (["repeated_device_errors"] if result["error_events"] >= 3 else [])
        for key in (
            "pause_hours",
            "waiting_hours",
            "observed_hours",
            "lifetime_hours_since_service",
        ):
            result[key] = round(result[key], 2)
    return values
