"""Versioned anonymous fixture format, not a universal vendor-log adapter."""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
from pathlib import Path
from uuid import uuid4
import os
from .base import ReadResult, capabilities

HEADERS = ["event_key", "machine_code", "native_job_id", "event_type", "event_time", "count", "count_unit", "counter_mode", "ink_total_ml"]
KINDS = {"start":"job_start", "progress":"job_progress", "complete":"job_complete", "failed":"job_failed", "cancelled":"job_cancelled"}


class GenericCsvLog:
    def __init__(self, path, *, encoding="utf-8-sig", format_version="synthetic-csv-v1"):
        self.path = Path(path).resolve()
        if encoding not in {"utf-8-sig", "utf-8", "gb18030", "gbk"} or format_version != "synthetic-csv-v1":
            raise ValueError("Unverified log encoding or format")
        self.encoding, self.format_version = encoding, format_version

    def probe(self):
        return dict(available=self.path.is_file(), format_version=self.format_version, fixture_only=True)

    def capabilities(self):
        return capabilities("vendor_log")

    def read_snapshot(self):
        return dict(work_state="unknown", progress=None, count=None, ink_total_ml=None)

    def health(self):
        return dict(state="ready" if self.path.is_file() else "unconfigured", needs_interactive_session=False)

    def read_events_since(self, cursor):
        if not self.path.is_file():
            return ReadResult([], cursor or {}, [])
        selected = self.path
        current = self.path.stat()
        current_identity = f'{current.st_dev}:{current.st_ino}'
        if cursor and cursor.get('identity') != current_identity:
            # The configured directory is the only search scope. Drain an old
            # renamed file by identity before advancing to the new active file,
            # including after a service restart. Never skip an unavailable tail.
            found = False
            with os.scandir(self.path.parent) as entries:
                for index, entry in enumerate(entries):
                    if index >= 1000:
                        raise ValueError('rotation_directory_limit')
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    # Windows DirEntry cached stat can report st_ino=0.
                    stat = Path(entry.path).stat(follow_symlinks=False)
                    if f'{stat.st_dev}:{stat.st_ino}' == cursor['identity']:
                        found = True
                        if stat.st_size > cursor['offset']:
                            selected = Path(entry.path)
                        break
            if not found:
                raise ValueError('rotated_source_missing_preserve_cursor')
        stat = selected.stat()
        identity = f"{stat.st_dev}:{stat.st_ino}"
        with selected.open("rb") as source:
            header = source.readline(8192)
            if not header.endswith(b"\n"):
                return ReadResult([], cursor or {}, [])
            try:
                fields = next(csv.reader([header.decode(self.encoding).strip()]))
            except (UnicodeError, csv.Error):
                raise ValueError("invalid_csv_header") from None
            if fields != HEADERS:
                raise ValueError("unknown_csv_format")
            reset = not cursor or cursor.get("identity") != identity or cursor.get("offset", 0) > stat.st_size
            if not reset and cursor.get("last_length", 0):
                source.seek(cursor["offset"]-cursor["last_length"])
                reset = sha256(source.read(cursor["last_length"])).hexdigest() != cursor.get("last_fingerprint")
            jobs = dict((cursor or {}).get('jobs', {}))
            state = dict(identity=identity, generation=uuid4().hex, offset=len(header), last_length=0, format_version=self.format_version, jobs=jobs) if reset else dict(cursor)
            state['jobs'] = jobs
            source.seek(state["offset"])
            events, rejected = [], []
            for _ in range(200):
                offset = source.tell()
                raw = source.readline(65537)
                if not raw:
                    break
                if len(raw) > 65536:
                    fingerprint, count, tail = sha256(raw), len(raw), raw[-65536:]
                    while not tail.endswith(b'\n'):
                        chunk = source.readline(65536)
                        if not chunk:
                            break
                        fingerprint.update(chunk)
                        count += len(chunk)
                        tail = (tail+chunk)[-65536:]
                    if not tail.endswith(b'\n') and selected == self.path:
                        break  # Oversized but still incomplete: retain cut point.
                    rejected.append(dict(byte_offset=offset, end_offset=source.tell(), file_identity=identity, source_path=str(selected), byte_length=count, fingerprint=fingerprint.hexdigest(), raw_prefix_hex=raw[:4096].hex(), code='log_line_too_large'))
                    state.update(offset=source.tell(), last_length=len(tail), last_fingerprint=sha256(tail).hexdigest())
                    continue
                if not raw.endswith(b"\n"):
                    if selected != self.path:
                        rejected.append(dict(byte_offset=offset,file_identity=identity,raw_hex=raw.hex(),fingerprint=sha256(raw).hexdigest(),code='rotated_incomplete_line'))
                        state.update(offset=source.tell(),last_length=len(raw),last_fingerprint=sha256(raw).hexdigest())
                    break  # No cursor advance for an active half line.
                try:
                    values = next(csv.reader(StringIO(raw.decode(self.encoding))))
                    if len(values) != len(HEADERS):
                        raise ValueError("column_count")
                    row = dict(zip(HEADERS, values))
                    moment = datetime.fromisoformat(row["event_time"].replace("Z", "+00:00"))
                    if moment.tzinfo is None or not row["event_key"] or not row["native_job_id"]:
                        raise ValueError("timezone_or_identity")
                    if row["count_unit"] not in {"pcs", "board", "pass"} or row["counter_mode"] not in {"cumulative", "delta"}:
                        raise ValueError("count_semantics")
                    for key in ("count", "ink_total_ml"):
                        if row[key]:
                            number = Decimal(row[key])
                            if not number.is_finite() or number < 0:
                                raise ValueError("invalid_count")
                    kind = KINDS[row["event_type"]]
                    job = jobs.get(row['native_job_id'])
                    start_key = row['event_key']+'|'+moment.isoformat()
                    if job is None or kind == 'job_start' and job.get('start_key') != start_key:
                        if len(jobs) >= 2048:
                            completed = next((key for key,value in jobs.items() if value.get('closed')), None)
                            if completed is None:
                                raise ValueError('active_job_capacity')
                            del jobs[completed]
                        job = dict(identity=sha256((row['native_job_id']+'|'+start_key).encode()).hexdigest(), start_key=start_key, closed=False)
                        jobs[row['native_job_id']] = job
                    if kind in {'job_complete','job_failed','job_cancelled'}:
                        job['closed'] = True
                    events.append(dict(kind=kind, observed_at=moment.isoformat(), adapter_type="generic_csv_log", adapter_version="1.0.1", source_identity=dict(generation=state["generation"], job_identity=job['identity'], file_identity=identity, byte_offset=offset, format_version=self.format_version, event_key=row["event_key"]), evidence=dict(level="vendor_log", fixture_only=True, machine_code=row["machine_code"]), payload=dict(native_job_id=row["native_job_id"], count=row["count"] or None, count_unit=row["count_unit"], counter_mode=row["counter_mode"], ink_total_ml=row["ink_total_ml"] or None, work_state="running" if kind in {"job_start","job_progress"} else "fault" if kind=="job_failed" else "idle")))
                except (ValueError, KeyError, UnicodeError, csv.Error, InvalidOperation) as error:
                    rejected.append(dict(byte_offset=offset, fingerprint=sha256(raw).hexdigest(), raw_hex=raw.hex(), code=str(error)[:80]))
                state.update(offset=source.tell(), last_length=len(raw), last_fingerprint=sha256(raw).hexdigest())
            return ReadResult(events, state, rejected)
