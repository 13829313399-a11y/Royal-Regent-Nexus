"""Evidence-limited runtime counters. Gaps over 120 seconds remain unobserved."""

import json
from collections import Counter
from datetime import timedelta, timezone

from sqlalchemy import DateTime, Float, and_, case, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB

from app.core.time import business_now, parse_business_timestamp
from app.models import three_d_printing as m


def _postgres_event_counters(db, begin, now, values):
    """Aggregate validated connector frames in PostgreSQL, not in API memory."""
    model = m.ThreeDPrintingPrinterStateEvent
    timestamp = cast(model.observed_at, DateTime(timezone=True))
    temperatures = cast(model.temperatures_json, JSONB)
    frames = select(
        model.machine_no, model.observed_at, model.state, model.error_code,
        func.extract("epoch", timestamp).label("seconds"),
        case((
            (cast(temperatures["nozzle"].astext, Float) > 320)
            | (cast(temperatures["bed"].astext, Float) > 130), 1,
        ), else_=0).label("temperature_alarm"),
    ).where(
        model.factory_id == "huakang-a",
        model.observed_at >= begin.astimezone(timezone.utc).isoformat(),
        timestamp <= now,
    ).subquery()
    # Connector timestamps are normalized UTC strings. Keeping their original
    # ordering lets PostgreSQL read the covering index without sorting frames.
    window = {"partition_by": frames.c.machine_no, "order_by": frames.c.observed_at}
    intervals = select(
        frames,
        (frames.c.seconds - func.lag(frames.c.seconds).over(**window)).label("elapsed"),
        func.lag(frames.c.state).over(**window).label("prior_state"),
    ).subquery()
    hours = case((and_(intervals.c.elapsed >= 0, intervals.c.elapsed <= 120),
                  intervals.c.elapsed / 3600), else_=0)
    # Grouping by error code preserves exact error frequencies without returning
    # every frame; codes are reduced to the existing top-ten projection below.
    query = select(
        intervals.c.machine_no, intervals.c.error_code,
        func.count().label("events"),
        func.sum(hours).label("observed_hours"),
        func.sum(case((intervals.c.prior_state == "PAUSE", hours), else_=0)).label("pause_hours"),
        func.sum(case((intervals.c.prior_state.in_(["IDLE", "FINISH"]), hours), else_=0)).label("waiting_hours"),
        func.sum(intervals.c.temperature_alarm).label("temperature_alarm_events"),
    ).group_by(intervals.c.machine_no, intervals.c.error_code)
    # Only grouped counters leave PostgreSQL. A named streaming cursor disables
    # parallel query execution and can make a full-history scan time out.
    for row in db.execute(query):
        if row.machine_no not in values:
            continue
        result = values[row.machine_no]
        for name in ("observed_hours", "pause_hours", "waiting_hours"):
            result[name] += float(getattr(row, name))
        result["temperature_alarm_events"] += row.temperature_alarm_events
        if row.error_code and row.error_code != "0":
            result["error_events"] += row.events
            result["failure_codes"][row.error_code] += row.events


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
    # Set streaming BEFORE execute: Result.yield_per() alone still lets psycopg
    # buffer the entire result. Raw device payloads are large and not needed here.
    event_model = m.ThreeDPrintingPrinterStateEvent
    from app.services.three_d_telemetry_rollups import counters as rollup_counters

    summaries = rollup_counters(db, begin, now)
    if summaries is not None:
        for number, summary in summaries.items():
            target = values[int(number)]
            for name in ("observed", "pause", "waiting"):
                target[name + "_hours"] = summary[name + "_seconds"] / 3600
            for name in ("error_events", "temperature_alarm_events"):
                target[name] = summary[name]
            target["failure_codes"].update(summary["failure_codes"])
        events = ()
    elif db.bind.dialect.name == "postgresql":
        _postgres_event_counters(db, begin, now, values)
        events = ()
    else:
        events = db.execute(
            select(
                event_model.machine_no, event_model.observed_at, event_model.state,
                event_model.error_code, event_model.temperatures_json,
            )
            .where(
                event_model.factory_id == "huakang-a",
                event_model.observed_at >= begin.astimezone(timezone.utc).isoformat(),
            )
            .order_by(event_model.machine_no, event_model.observed_at)
            .execution_options(yield_per=500)
        )
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
    run_model = m.ThreeDPrintingProductionRecord
    runs = db.execute(
        select(
            run_model.machine_no, run_model.business_date,
            run_model.print_start_at, run_model.print_end_at,
        ).where(
            m.ThreeDPrintingProductionRecord.factory_id == "huakang-a",
            m.ThreeDPrintingProductionRecord.deleted_at == "",
            m.ThreeDPrintingProductionRecord.print_end_at != "",
        ).execution_options(yield_per=500)
    )
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
            # Summing SQL hour fractions versus cached seconds can differ by a
            # floating-point epsilon at .005 boundaries. Discard sub-microhour
            # noise before applying the same two-decimal presentation rounding.
            result[key] = round(round(result[key], 9), 2)
    return values
