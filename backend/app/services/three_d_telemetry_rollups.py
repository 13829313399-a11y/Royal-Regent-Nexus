"""Exact, rebuildable hour summaries; only partial hours read raw events on GET."""

import json
import logging
from collections import Counter
from datetime import UTC, timedelta
from functools import lru_cache

from sqlalchemy import func, inspect, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
from app.models import three_d_printing as m

FACTORY = "huakang-a"
HOUR = timedelta(hours=1)
Rollup = m.ThreeDPrintingTelemetryRollup
State = m.ThreeDPrintingTelemetryRollupState
Event = m.ThreeDPrintingPrinterStateEvent


def hour(value):
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


@lru_cache(maxsize=32)
def available(engine):
    schema = inspect(engine)
    return schema.has_table(Rollup.__tablename__) and schema.has_table(State.__tablename__)


def insert(db, model):
    return (pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert)(model)


def invalidate(db, observed_at):
    """Shares the event's transaction, including rollback and duplicate semantics."""
    if observed_at is None or not available(db.get_bind()):
        return
    db.execute(insert(db, Rollup).values(
        factory_id=FACTORY, bucket_start=stamp(hour(observed_at)), dirty=True,
        counters_json="{}", calculated_at="",
    ).on_conflict_do_update(
        index_elements=[Rollup.factory_id, Rollup.bucket_start],
        set_={"dirty": True}, where=Rollup.dirty.is_(False),
    ))


def empty():
    return dict(observed_seconds=0.0, pause_seconds=0.0, waiting_seconds=0.0,
                temperature_alarm_events=0, error_events=0, failure_codes={},
                first=None, last=None)


def bridge(target, previous, current):
    if previous is None or current is None:
        return
    elapsed = (parse_business_timestamp(current[0]) - parse_business_timestamp(previous[0])).total_seconds()
    if 0 <= elapsed <= 120:
        target["observed_seconds"] += elapsed
        if previous[1] == "PAUSE":
            target["pause_seconds"] += elapsed
        if previous[1] in {"IDLE", "FINISH"}:
            target["waiting_seconds"] += elapsed


def scan(db, begin, end, *, include_end=False):
    """At most one hour, narrow columns, indexed seeks for each known machine."""
    values = {}
    for number in range(1, 12):
        # Millisecond upper bound includes the possible partial last millisecond;
        # exact Python comparisons below retain the original time-window contract.
        query = select(Event.observed_at, Event.state, Event.error_code, Event.temperatures_json).where(
            Event.factory_id == FACTORY, Event.machine_no == number,
            Event.observed_at >= stamp(begin),
            Event.observed_at < stamp(end + timedelta(milliseconds=1)),
        ).order_by(Event.observed_at).execution_options(yield_per=500)
        for event in db.execute(query):
            timestamp = parse_business_timestamp(event.observed_at)
            if not timestamp or timestamp < begin or timestamp > end or (timestamp == end and not include_end):
                continue
            value = values.setdefault(str(number), empty())
            current = [event.observed_at, event.state]
            bridge(value, value["last"], current)
            value["first"] = value["first"] or current
            value["last"] = current
            if event.error_code and event.error_code != "0":
                value["error_events"] += 1
                codes = value["failure_codes"]
                codes[event.error_code] = codes.get(event.error_code, 0) + 1
            temperatures = json.loads(event.temperatures_json or "{}")
            value["temperature_alarm_events"] += int(
                float(temperatures.get("nozzle", 0)) > 320 or float(temperatures.get("bed", 0)) > 130
            )
    return values


def cached_hour(engine, bucket):
    # Separate short transactions do not hold an API read transaction or the
    # printer/factory writer while building historical summaries.
    with Session(engine) as db:
        key = (Rollup.factory_id == FACTORY, Rollup.bucket_start == bucket)
        if db.bind.dialect.name == "sqlite":
            db.execute(update(Rollup).where(*key).values(dirty=Rollup.dirty))
        row = db.scalar(select(Rollup).where(*key).with_for_update())
        if row is None:
            return {}
        if row.dirty:
            begin = parse_business_timestamp(bucket)
            result = scan(db, begin, begin + HOUR)
            row.counters_json = json.dumps(result, separators=(",", ":"))
            row.calculated_at = stamp(business_now())
            row.dirty = False
        result = json.loads(row.counters_json)
        db.commit()
        return result


def initialize(engine, *, now=None, progress=None):
    """One deployment/backfill pass. Readers keep the old path until it finishes."""
    if not available(engine):
        raise RuntimeError("Apply telemetry rollup migration 20260929_0130 first")
    now = now or business_now()
    with Session(engine) as db:
        state = db.get(State, FACTORY)
        if state and state.initialized_at:
            return 0
        buckets = select(
            Event.factory_id,
            (func.substr(Event.observed_at, 1, 13) + ":00:00.000+00:00").label("bucket_start"),
        ).where(Event.factory_id == FACTORY, Event.observed_at != "").distinct()
        db.execute(insert(db, Rollup).from_select(
            ["factory_id", "bucket_start"], buckets,
        ).on_conflict_do_update(index_elements=[Rollup.factory_id, Rollup.bucket_start],
                                set_={"dirty": True}))
        db.commit()
        keys = list(db.scalars(select(Rollup.bucket_start).where(
            Rollup.factory_id == FACTORY, Rollup.bucket_start < stamp(hour(now)),
        ).order_by(Rollup.bucket_start)))
    for index, bucket in enumerate(keys):
        cached_hour(engine, bucket)
        if progress:
            progress(index + 1, len(keys))
    with Session(engine) as db:
        db.execute(insert(db, State).values(factory_id=FACTORY, initialized_at=stamp(now))
                   .on_conflict_do_update(index_elements=[State.factory_id], set_={"initialized_at": stamp(now)}))
        db.commit()
    return len(keys)


def refresh_closed_hours(engine, *, now=None, limit=2):
    """Bounded background work; never seals the actively receiving hour."""
    if not available(engine):
        return 0
    with Session(engine) as db:
        state = db.get(State, FACTORY)
        if not state or not state.initialized_at:
            return 0
        keys = list(db.scalars(select(Rollup.bucket_start).where(
            Rollup.factory_id == FACTORY, Rollup.dirty.is_(True),
            Rollup.bucket_start < stamp(hour(now or business_now())),
        ).order_by(Rollup.bucket_start).limit(limit)))
    for bucket in keys:
        cached_hour(engine, bucket)
    return len(keys)


async def worker():
    import asyncio
    from app.db import engine

    while True:
        try:
            await asyncio.to_thread(refresh_closed_hours, engine)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).warning("three_d_rollup_refresh_failed", exc_info=True)
        await asyncio.sleep(60)


def counters(db, begin, now):
    engine = db.get_bind()
    if not available(engine):
        return None
    state = db.get(State, FACTORY)
    if not state or not state.initialized_at:
        return None
    start, finish = hour(begin), hour(now)
    full_start = start if begin == start else start + HOUR
    rows = db.execute(select(Rollup.bucket_start, Rollup.dirty, Rollup.counters_json).where(
        Rollup.factory_id == FACTORY, Rollup.bucket_start >= stamp(full_start),
        Rollup.bucket_start < stamp(finish),
    ).order_by(Rollup.bucket_start)).all()
    values = {}

    def merge(part):
        for number, source in part.items():
            target = values.setdefault(number, empty())
            bridge(target, target["last"], source["first"])
            for name in ("observed_seconds", "pause_seconds", "waiting_seconds",
                         "temperature_alarm_events", "error_events"):
                target[name] += source[name]
            counts = Counter(target["failure_codes"])
            counts.update(source["failure_codes"])
            target["failure_codes"] = dict(counts)
            target["first"] = target["first"] or source["first"]
            target["last"] = source["last"] or target["last"]

    if begin != start:
        merge(scan(db, begin, min(start + HOUR, now), include_end=now < start + HOUR))
    for row in rows:
        merge(cached_hour(engine, row.bucket_start) if row.dirty else json.loads(row.counters_json))
    if finish >= full_start:
        merge(scan(db, finish, now, include_end=True))
    return values
