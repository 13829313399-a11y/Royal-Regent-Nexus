"""Replay stored printer state events into print runs and diff them against records.

Read-only. Nothing here writes to the database, touches a printer or imports business
data. The observation period already stored every MQTT status frame, so the runs the
Connector was not allowed to settle can be reconstructed afterwards and compared with
what Nexus and the legacy standalone server actually recorded.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/replay_three_d_runs.py \
        --database sqlite:///data/royal_regent_nexus.db \
        --legacy-json D:/private/3d-server/data.json \
        --out D:/private/three-d-replay

The report classifies every replay run as safely insertable, needing human
confirmation, or conflicting with existing data. It never applies anything.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.time import parse_business_timestamp
from app.models import three_d_printing as m
from app.services.three_d_run_reconciliation import job_key as device_job_key

FACTORY = "huakang-a"
TERMINAL_STATES = {"FINISH", "FAILED", "ERROR"}
ENDED_STATES = TERMINAL_STATES | {"IDLE", "STOPPED", "CANCELLED"}
UNAVAILABLE_STATES = {"STALE", "UNKNOWN", ""}
MIN_RUN_PROGRESS = 2
RUN_MERGE_GAP = timedelta(minutes=10)
RECORD_MATCH_WINDOW = timedelta(hours=6)

SAFE = "safe_to_insert"
REVIEW = "needs_review"
CONFLICT = "conflicts_with_existing"


@dataclass
class ReplayRun:
    printer_id: str
    machine_no: int
    device_job_key: str
    current_file: str
    started_at: str
    last_seen_at: str
    ended_at: str = ""
    end_state: str = ""
    max_progress: int = 0
    event_count: int = 0
    end_evidence: str = ""
    closed_by_observation: bool = False

    @property
    def job_key(self) -> str:
        return self.device_job_key or ""


@dataclass
class Diff:
    classification: str
    reason: str
    replay: dict
    nexus_record_id: str = ""
    legacy_ids: list = field(default_factory=list)
    legacy_products: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def load_events(db: Session, date_from: str, date_to: str):
    statement = (
        select(m.ThreeDPrintingPrinterStateEvent)
        .where(m.ThreeDPrintingPrinterStateEvent.factory_id == FACTORY)
        .order_by(
            m.ThreeDPrintingPrinterStateEvent.printer_id,
            m.ThreeDPrintingPrinterStateEvent.observed_at,
            m.ThreeDPrintingPrinterStateEvent.sequence,
        )
    )
    if date_from:
        statement = statement.where(
            m.ThreeDPrintingPrinterStateEvent.observed_at >= date_from
        )
    if date_to:
        statement = statement.where(
            m.ThreeDPrintingPrinterStateEvent.observed_at <= date_to
        )
    return list(db.scalars(statement))


def load_events_csv(path):
    """Read the read-only CSV export of the state event table.

    Same rows as `load_events`, so the report can be produced off a database export
    without opening the production database at all.
    """
    import csv
    import gzip

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        return [StateEventRow(row) for row in csv.DictReader(handle)]


def load_records_csv(path):
    import csv
    import gzip

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        return [RecordRow(row) for row in csv.DictReader(handle)]


class StateEventRow:
    """One exported event row, sharing the attribute names the ORM row exposes."""

    def __init__(self, row):
        self.device_job_key = ""
        self.printer_id = row.get("printer_id", "")
        self.machine_no = int(row.get("machine_no") or 0)
        self.state = row.get("state", "")
        self.progress = int(row.get("progress") or 0)
        self.observed_at = row.get("observed_at", "")
        self.received_at = row.get("received_at", "")
        self.current_file = row.get("current_file", "")
        self.raw_payload_json = row.get("raw_payload_json", "") or "{}"


class RecordRow:
    """One exported production record row, limited to what classification needs."""

    def __init__(self, row):
        self.id = row.get("id", "")
        self.machine_no = int(row.get("machine_no") or 0)
        self.device_job_key = row.get("device_job_key", "") or ""
        self.gcode_file = row.get("gcode_file", "") or ""
        self.print_start_at = row.get("print_start_at", "") or ""
        self.created_at = row.get("created_at", "") or ""
        self.print_end_at = row.get("print_end_at", "") or ""


def _stored_job_key(event) -> str:
    """The event row keeps the device job identity only inside its raw payload.

    Stored events carry the device's own id; a record carries the printer-namespaced
    key, so the replay hashes the raw id with the same helper the Connector uses.
    """
    direct = getattr(event, "device_job_key", "")
    payload = _payload(event)
    raw = str(direct or payload.get("device_job_key") or "")
    if not raw:
        return ""
    if raw.startswith("bambu-"):
        return raw
    printer_id = getattr(event, "printer_id", "")
    return device_job_key(printer_id, raw) or ""


def _payload(event) -> dict:
    raw = getattr(event, "raw_payload_json", "") or "{}"
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def replay_runs(events, *, min_progress: int = MIN_RUN_PROGRESS):
    """Rebuild logical runs from observed state transitions, per printer."""
    by_printer = defaultdict(list)
    for item in events:
        by_printer[item.printer_id].append(item)
    runs: list[ReplayRun] = []
    for printer_id, items in by_printer.items():
        current: ReplayRun | None = None
        for item in items:
            state = (item.state or "").strip().upper()
            progress = int(item.progress or 0)
            observed = item.observed_at or item.received_at
            job_key = _stored_job_key(item)
            if job_key:
                key = job_key
            elif current is not None:
                key = current.device_job_key
            else:
                key = ""
            if state in UNAVAILABLE_STATES:
                if current is not None:
                    current.closed_by_observation = True
                    current.end_evidence = "telemetry_unavailable"
                    current.ended_at = current.ended_at or observed
                    runs.append(current)
                    current = None
                continue
            if current is not None and key and key != current.device_job_key:
                # The device moved on to another job without a terminal frame.
                current.closed_by_observation = True
                current.end_evidence = "device_job_changed"
                current.ended_at = current.ended_at or observed
                runs.append(current)
                current = None
            if current is not None and state in ENDED_STATES:
                current.ended_at = observed
                current.end_state = state
                current.end_evidence = (
                    "device_terminal_state" if state in TERMINAL_STATES else "device_idle"
                )
                current.closed_by_observation = state not in TERMINAL_STATES
                current.last_seen_at = observed
                current.max_progress = max(current.max_progress, progress)
                current.event_count += 1
                runs.append(current)
                current = None
                continue
            if current is None:
                if state != "RUNNING":
                    continue
                if not key and not item.current_file:
                    continue
                current = ReplayRun(
                    printer_id=printer_id,
                    machine_no=int(item.machine_no),
                    device_job_key=key,
                    current_file=item.current_file or "",
                    started_at=observed,
                    last_seen_at=observed,
                    max_progress=progress,
                    event_count=1,
                )
                if min_progress and progress < min_progress:
                    # A start frame with no progress yet is still the same run; the
                    # threshold only prevents pre-heat noise from opening a second run.
                    current.end_evidence = "low_progress_start"
                continue
            current.last_seen_at = observed
            current.max_progress = max(current.max_progress, progress)
            current.event_count += 1
            if not current.current_file and item.current_file:
                current.current_file = item.current_file
        if current is not None:
            current.closed_by_observation = True
            current.end_evidence = "still_open_at_end_of_data"
            runs.append(current)
    runs.sort(key=lambda run: (run.machine_no, run.started_at))
    return runs


def merge_same_file_window(runs, window_seconds=None):
    """Collapse the same file reprinted within the window into one physical run.

    Mirrors the reconciliation rule: a second device job for the identical file on the
    same machine shortly after the first ended is the same print, so replay must not
    report it as a run Nexus forgot to create.
    """
    if window_seconds is None:
        window_seconds = settings.three_d_reconciliation_same_file_window_seconds
    merged: list[ReplayRun] = []
    for run in runs:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.machine_no == run.machine_no
            and previous.current_file
            and previous.current_file == run.current_file
            and previous.ended_at
            and _delta(run.started_at, previous.ended_at)
            <= timedelta(seconds=window_seconds)
        ):
            previous.ended_at = run.ended_at or previous.ended_at
            previous.end_state = run.end_state or previous.end_state
            previous.end_evidence = run.end_evidence or previous.end_evidence
            previous.closed_by_observation = run.closed_by_observation
            previous.last_seen_at = max(previous.last_seen_at, run.last_seen_at)
            previous.max_progress = max(previous.max_progress, run.max_progress)
            previous.event_count += run.event_count
            continue
        merged.append(run)
    return merged


def merge_adjacent(runs):
    """Collapse reconnects that reopened the same device job within a short gap."""
    merged: list[ReplayRun] = []
    for run in runs:
        if (
            merged
            and run.device_job_key
            and merged[-1].device_job_key == run.device_job_key
            and merged[-1].ended_at
            and run.started_at
            and _delta(merged[-1].ended_at, run.started_at) <= RUN_MERGE_GAP
        ):
            previous = merged[-1]
            previous.ended_at = run.ended_at or previous.ended_at
            previous.end_state = run.end_state or previous.end_state
            previous.end_evidence = run.end_evidence or previous.end_evidence
            previous.closed_by_observation = run.closed_by_observation
            previous.last_seen_at = max(previous.last_seen_at, run.last_seen_at)
            previous.max_progress = max(previous.max_progress, run.max_progress)
            previous.event_count += run.event_count
            continue
        merged.append(run)
    return merged


def _delta(later: str, earlier: str) -> timedelta:
    right, left = parse_business_timestamp(later), parse_business_timestamp(earlier)
    if right is None or left is None:
        return timedelta.max
    return abs(right - left)


def _timestamp(value):
    return parse_business_timestamp(value)


def load_nexus_records(db: Session):
    return list(
        db.scalars(
            select(m.ThreeDPrintingProductionRecord).where(
                m.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                m.ThreeDPrintingProductionRecord.deleted_at == "",
            )
        )
    )


def load_legacy_records(path: Path | None):
    """Read the legacy standalone data.json; tolerates the state blob wrapper."""
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records")
    if records is None and isinstance(payload.get("state"), dict):
        records = payload["state"].get("records")
    if not isinstance(records, dict):
        raise SystemExit("legacy json has no records map")
    by_machine = defaultdict(list)
    for business_date, day in records.items():
        for item in (day or {}).get("items") or []:
            if item.get("_deleted"):
                continue
            by_machine[int(item.get("machine") or 0)].append(
                {
                    "business_date": business_date,
                    "machine": int(item.get("machine") or 0),
                    "product_name": item.get("productName") or "",
                    "gcode_file": item.get("_gcodeFile") or "",
                    "auto_record": bool(item.get("autoRecord")),
                    "started_at": item.get("printStartTime") or item.get("createdAt") or "",
                    "ended_at": item.get("printEndTime") or "",
                }
            )
    for items in by_machine.values():
        items.sort(key=lambda item: item["started_at"] or "")
    return by_machine


def classify(run: ReplayRun, nexus_records, legacy_by_machine):
    """Decide whether a replay run may be inserted, needs a human, or conflicts."""
    machine_records = [
        record for record in nexus_records if int(record.machine_no) == run.machine_no
    ]
    for record in machine_records:
        if run.device_job_key and record.device_job_key == run.device_job_key:
            return Diff(
                classification=SAFE,
                reason="already_recorded_same_device_job",
                replay=run.__dict__,
                nexus_record_id=record.id,
            )
    window_records = [
        record
        for record in machine_records
        if _within(record.print_start_at or record.created_at, run.started_at)
    ]
    legacy_matches = [
        item
        for item in legacy_by_machine.get(run.machine_no, [])
        if item["gcode_file"] == run.current_file
        and _within(item["started_at"], run.started_at)
    ]
    if not run.device_job_key:
        return Diff(
            classification=REVIEW,
            reason="device_identity_missing",
            replay=run.__dict__,
            nexus_record_id=window_records[0].id if window_records else "",
            legacy_ids=[item["product_name"] for item in legacy_matches],
        )
    if window_records:
        return Diff(
            classification=REVIEW,
            reason="time_overlaps_existing_record",
            replay=run.__dict__,
            nexus_record_id=window_records[0].id,
            legacy_ids=[item["product_name"] for item in legacy_matches],
        )
    if legacy_matches:
        # The old writer already owns this run; supplementing it would duplicate.
        return Diff(
            classification=SAFE,
            reason="legacy_owns_run_history_only",
            replay=run.__dict__,
            legacy_ids=[item["product_name"] for item in legacy_matches],
        )
    return Diff(
        classification=SAFE,
        reason="missing_from_nexus_and_legacy",
        replay=run.__dict__,
    )


def _within(value: str, target: str) -> bool:
    left, right = _timestamp(value), _timestamp(target)
    if left is None or right is None:
        return False
    return abs(left - right) <= RECORD_MATCH_WINDOW


def summarize(runs, diffs, events, *, nexus_records=(), legacy_by_machine=None):
    counts = Counter(diff.classification for diff in diffs)
    reasons = Counter(diff.reason for diff in diffs)
    per_day = Counter(run.started_at[:10] for run in runs)
    open_runs = [run for run in runs if not run.ended_at]
    return {
        "factory_id": FACTORY,
        "events_replayed": len(events),
        "runs_rebuilt": len(runs),
        "classifications": dict(counts),
        "reasons": dict(reasons),
        "runs_by_day": dict(sorted(per_day.items())),
        "open_runs_at_end": len(open_runs),
        "first_run": runs[0].started_at if runs else "",
        "last_run": runs[-1].started_at if runs else "",
        "nexus_records_in_scope": len(list(nexus_records)),
        "legacy_records_in_scope": sum(
            len(items) for items in (legacy_by_machine or {}).values()
        ),
    }


def build_report(
    session_factory,
    *,
    date_from="",
    date_to="",
    legacy_json=None,
    out_dir=None,
    events_csv=None,
    records_csv=None,
):
    legacy_path = Path(legacy_json) if legacy_json else None
    if events_csv:
        # Export mode: read the read-only CSV instead of opening a database.
        events = load_events_csv(events_csv)
        nexus_records = load_records_csv(records_csv) if records_csv else []
        if date_from:
            events = [e for e in events if e.observed_at >= date_from]
        if date_to:
            events = [e for e in events if e.observed_at <= date_to]
    else:
        with session_factory() as db:
            events = load_events(db, date_from, date_to)
            nexus_records = load_nexus_records(db)
    legacy_by_machine = load_legacy_records(legacy_path)
    runs = merge_same_file_window(replay_runs(events))
    runs = merge_adjacent(runs)
    diffs = [classify(run, nexus_records, legacy_by_machine) for run in runs]
    summary = summarize(
        runs,
        diffs,
        events,
        nexus_records=nexus_records,
        legacy_by_machine=legacy_by_machine,
    )
    if out_dir:
        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with (destination / "runs.ndjson").open("w", encoding="utf-8") as handle:
            for run in runs:
                handle.write(json.dumps(run.__dict__, ensure_ascii=False) + "\n")
        with (destination / "diff.ndjson").open("w", encoding="utf-8") as handle:
            for diff in diffs:
                handle.write(json.dumps(diff.as_dict(), ensure_ascii=False) + "\n")
        (destination / "report.md").write_text(
            render_markdown(summary, runs, diffs), encoding="utf-8"
        )
    return summary, runs, diffs


def render_markdown(summary, runs, diffs):
    lines = [
        "# 3D 打印运行回放差异报告",
        "",
        "只读回放：不写入数据库、不连接打印机、不导入业务数据。",
        "",
        f"- 回放事件数：{summary['events_replayed']}",
        f"- 重建运行数：{summary['runs_rebuilt']}",
        f"- 数据截止仍开放：{summary['open_runs_at_end']}",
        f"- 时间范围：{summary['first_run']} ~ {summary['last_run']}",
        f"- Nexus 现有记录：{summary['nexus_records_in_scope']}",
        f"- 旧系统记录：{summary['legacy_records_in_scope']}",
        "",
        "## 分类",
        "",
        "| 分类 | 数量 |",
        "| --- | ---: |",
    ]
    for name, count in sorted(summary["classifications"].items()):
        lines.append(f"| {name} | {count} |")
    lines += ["", "## 原因", "", "| 原因 | 数量 |", "| --- | ---: |"]
    for name, count in sorted(summary["reasons"].items()):
        lines.append(f"| {name} | {count} |")
    lines += ["", "## 每日重建运行数", "", "| 日期 | 运行数 |", "| --- | ---: |"]
    for day, count in sorted(summary["runs_by_day"].items()):
        lines.append(f"| {day} | {count} |")
    lines += [
        "",
        "## 需要人工确认的运行（前 50 条）",
        "",
        "| 机台 | 开始 | 结束 | 结束证据 | 文件 | 原因 |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    review = [diff for diff in diffs if diff.classification != SAFE]
    for diff in review[:50]:
        run = diff.replay
        lines.append(
            f"| {run['machine_no']} | {run['started_at']} | {run['ended_at'] or '—'} | "
            f"{run['end_evidence'] or '—'} | {run['current_file'] or '—'} | {diff.reason} |"
        )
    if not review:
        lines.append("| — | — | — | — | — | 无 |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default="",
        help="SQLAlchemy URL; opened read-only. Not needed with --events-csv",
    )
    parser.add_argument("--events-csv", default="", help="read-only export of the event table")
    parser.add_argument("--records-csv", default="", help="read-only export of the records table")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--legacy-json", default="", help="legacy 3d-server data.json")
    parser.add_argument("--out", default="", help="directory for the report files")
    args = parser.parse_args(argv)
    if not args.events_csv and not args.database:
        parser.error("provide --database or --events-csv")
    session_factory = None
    if not args.events_csv:
        engine = create_engine(args.database, future=True)
        session_factory = sessionmaker(bind=engine, future=True)
    summary, runs, diffs = build_report(
        session_factory,
        date_from=args.date_from,
        date_to=args.date_to,
        legacy_json=args.legacy_json or None,
        out_dir=args.out or None,
        events_csv=args.events_csv or None,
        records_csv=args.records_csv or None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        print(f"report written to {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
