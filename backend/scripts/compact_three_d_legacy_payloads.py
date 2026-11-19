"""Resumable PostgreSQL first pass for already-normalized legacy event bodies."""
import argparse
import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from itertools import groupby

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import engine
from app.models.three_d_printing import ThreeDPrintingPrinter
from app.services.three_d_telemetry_retention import Event, FACTORY, LOCK_KEY, cutoff_for, retire_rows


BODY_SQL = """
create or replace function pg_temp.rr3_compact(original text) returns text
language plpgsql immutable strict as $fn$
declare
    b jsonb := original::jsonb;
    kept jsonb;
begin
    if jsonb_typeof(b) <> 'object' then raise exception 'Invalid telemetry envelope'; end if;
    kept := jsonb_build_object('device_job_key',coalesce(b->>'device_job_key',''),
            'connected',coalesce(b->'connected','false'::jsonb),
            '_sha256',encode(sha256(convert_to(original,'UTF8')),'hex'));
    if b->>'state' in ('FAILED','ERROR','UNKNOWN','STALE') or coalesce(b->>'error_code','') not in ('','0')
        or coalesce((b->>'nozzle_temperature')::float,0)>320 or coalesce((b->>'bed_temperature')::float,0)>130 then
        kept := kept || jsonb_strip_nulls(jsonb_build_object('nozzle_target',b->'nozzle_target',
            'bed_target',b->'bed_target','layer_num',b->'layer_num','total_layers',b->'total_layers',
            'live_material',b->'live_material'));
    end if;
    return kept::text;
end $fn$
"""

SWEEP = text("""
update three_d_printing_printer_state_events
set raw_payload_json=pg_temp.rr3_compact(raw_payload_json), payload_version=3
where ctid >= cast(:lo as tid) and ctid < cast(:hi as tid)
  and mod((ctid::text::point)[1]::integer, 8) = :slot
  and factory_id=:factory and received_at<:cutoff and payload_version=1 and raw_payload_json<>'{}'
""")
REMAINING = text("""
select exists(select 1 from three_d_printing_printer_state_events
 where factory_id=:factory and received_at<:cutoff and payload_version in (1,2) and raw_payload_json<>'{}')
""")


def save(path, state):
    temp = path.with_suffix(".new")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def finish_missed_rows(cutoff):
    # A concurrent rewrite or an older journal import can place eligible tuples
    # outside the scanned pages. Stream their ids once under a fresh snapshot.
    eligible = (Event.factory_id == FACTORY, Event.received_at < cutoff,
                Event.payload_version.in_((1, 2)), Event.raw_payload_json != "{}")
    changed = 0
    with Session(engine) as reader:
        ids = reader.scalars(select(Event.id).where(*eligible).execution_options(yield_per=256))
        for batch in ids.partitions(256):
            with Session(engine) as writer, writer.begin():
                rows = writer.scalars(select(Event).where(Event.id.in_(batch), *eligible)
                                      .order_by(Event.printer_id, Event.id).with_for_update())
                for printer_id, group in groupby(rows, key=lambda event: event.printer_id):
                    printer = writer.get(ThreeDPrintingPrinter, printer_id)
                    shortened, moved = retire_rows(writer, list(group), printer)
                    changed += shortened + moved
    return changed


def run(path, *, execute=False, pages=256, max_batches=None, pause=0.05, reserve_gib=6):
    if engine.dialect.name != "postgresql" or pages <= 0 or pause < 0 or reserve_gib <= 0:
        raise ValueError("Use PostgreSQL with positive batch and free-space bounds")
    with engine.connect() as db:
        identity = db.execute(text("""select current_database(),pg_relation_filenode(
          'three_d_printing_printer_state_events'::regclass),current_setting('block_size')::int,
          pg_relation_size('three_d_printing_printer_state_events')""")).one()
        reference = [identity[0], identity[1], identity[2], FACTORY]
        if not execute:
            return {"mode":"preview","source":reference,"pages":identity[3]//identity[2],
                    "cutoff":cutoff_for(3)}
        if not db.scalar(text("select pg_try_advisory_lock(:key)"), {"key":LOCK_KEY}):
            raise RuntimeError("Retention is already in progress; retry this checkpoint")
        try:
            db.execute(text(BODY_SQL))
            db.execute(text("set lock_timeout='1s'"))
            db.execute(text("set statement_timeout='30s'"))
            db.execute(text("set max_parallel_workers_per_gather=1"))
            if db.scalar(text("select has_parameter_privilege(current_user, 'wal_compression', 'SET')")):
                db.execute(text("set wal_compression=on"))
            db.commit()
            state = json.loads(path.read_text()) if path.exists() else dict(
                source=reference, cutoff=cutoff_for(3), page=0, end=identity[3]//identity[2],
                changed=0, done=False)
            if state["source"] != reference:
                raise RuntimeError("Checkpoint belongs to a different database or heap")
            if state["done"]:
                return state
            count = 0
            while state["page"] < state["end"] and (max_batches is None or count < max_batches):
                free = shutil.disk_usage(path.parent).free
                if free < reserve_gib * 1024**3:
                    raise RuntimeError("Insufficient free space for another online batch")
                high = min(state["end"], state["page"] + pages)
                params = dict(factory=FACTORY,cutoff=state["cutoff"],
                              lo=f"({state['page']},0)",hi=f"({high},0)")
                # Free old tuples on each page between rounds. This lets PostgreSQL
                # store the smaller successors on the same page and reuse all indexes.
                updated = 0
                for slot in (1, 2, 3, 4, 5, 6, 7, 0):
                    updated += db.execute(SWEEP, {**params, "slot": slot}).rowcount
                    db.commit()
                state.update(page=high,changed=state["changed"]+updated,free=free)
                save(path,state)
                count+=1
                if count==1 or count%100==0:
                    print(json.dumps(state),flush=True)
                if pause:
                    time.sleep(pause)
            if state["page"] < state["end"]:
                return state
            # A heap rewrite or a historical import must never be hidden by a saved cursor.
            db.execute(text("set statement_timeout='10min'"))
            if db.scalar(REMAINING,dict(factory=FACTORY,cutoff=state["cutoff"])):
                state["changed"] += finish_missed_rows(state["cutoff"])
                save(path, state)
                if db.scalar(REMAINING, dict(factory=FACTORY, cutoff=state["cutoff"])):
                    raise RuntimeError("Concurrent historical imports remain; resume this checkpoint")
            db.execute(text("""insert into three_d_printing_retention_cursors(factory_id,printer_id,received_at,event_id)
                select factory_id,id,:cutoff,'' from three_d_printing_printers where factory_id=:factory
                on conflict(factory_id,printer_id) do update set received_at=excluded.received_at,event_id=''
                where three_d_printing_retention_cursors.received_at < excluded.received_at"""),
                       dict(factory=FACTORY,cutoff=state["cutoff"]))
            db.commit()
            state.update(done=True,verified_utc=datetime.now(UTC).isoformat())
            save(path,state)
            return state
        finally:
            db.rollback()
            db.execute(text("select pg_advisory_unlock(:key)"),{"key":LOCK_KEY})
            db.commit()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",type=Path,required=True)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--pages",type=int,default=256)
    parser.add_argument("--max-batches",type=int)
    parser.add_argument("--pause",type=float,default=0.05)
    parser.add_argument("--reserve-gib",type=float,default=6)
    args=parser.parse_args()
    print(json.dumps(run(args.state,execute=args.execute,pages=args.pages,max_batches=args.max_batches,
                         pause=args.pause,reserve_gib=args.reserve_gib)),flush=True)
