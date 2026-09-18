"""Read-only replay of stored state events must rebuild runs without side effects."""
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

from app.services.three_d_run_reconciliation import job_key as device_job_key  # noqa: E402
from replay_three_d_runs import (  # noqa: E402
    REVIEW,
    SAFE,
    build_report,
    classify,
    merge_adjacent,
    merge_same_file_window,
    render_markdown,
    replay_runs,
    summarize,
)
from test_three_d_connector import environment as environment_fixture  # noqa: E402
from test_three_d_connector import event, post, session  # noqa: E402

environment = environment_fixture

PRINTER = "printer-1"
PRINTER_B = "printer-2"


@dataclass
class FakeEvent:
    printer_id: str
    machine_no: int
    state: str
    observed_at: str
    progress: int = 0
    device_job_key: str = ""
    current_file: str = ""
    received_at: str = ""

    def __post_init__(self):
        self.received_at = self.received_at or self.observed_at


def at(minutes):
    return f"2026-09-17T{8 + minutes // 60:02d}:{minutes % 60:02d}:00+08:00"


def key(raw, printer=PRINTER):
    return device_job_key(printer, raw)


def test_completed_run_is_rebuilt_and_left_over_run_stays_open():
    events = [
        FakeEvent(PRINTER, 1, "RUNNING", at(0), 0, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "RUNNING", at(5), 40, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "FINISH", at(30), 100, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "IDLE", at(31), 0, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "RUNNING", at(60), 3, key("job-b"), "other.3mf"),
        FakeEvent(PRINTER, 1, "RUNNING", at(70), 55, key("job-b"), "other.3mf"),
    ]
    runs = replay_runs(events)
    assert len(runs) == 2
    finished = runs[0]
    assert finished.device_job_key == key("job-a")
    assert finished.end_state == "FINISH" and finished.max_progress == 100
    assert finished.end_evidence == "device_terminal_state" and finished.ended_at == at(30)
    assert finished.closed_by_observation is False
    still_open = runs[1]
    assert still_open.device_job_key == key("job-b") and still_open.ended_at == ""
    assert still_open.end_evidence == "still_open_at_end_of_data"


def test_idle_or_lost_telemetry_closes_run_without_claiming_success():
    events = [
        FakeEvent(PRINTER, 1, "RUNNING", at(0), 10, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "IDLE", at(20), 10, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER_B, 2, "RUNNING", at(25), 10, key("job-c", PRINTER_B), "part.3mf"),
        FakeEvent(PRINTER_B, 2, "STALE", at(40), 10, key("job-c", PRINTER_B), "part.3mf"),
    ]
    runs = replay_runs(events)
    assert [run.end_state for run in runs] == ["IDLE", ""]
    assert runs[0].closed_by_observation is True
    assert runs[0].end_evidence == "device_idle"
    assert runs[1].end_evidence == "telemetry_unavailable"
    assert runs[1].closed_by_observation is True


def test_device_job_change_closes_previous_run():
    events = [
        FakeEvent(PRINTER, 3, "RUNNING", at(0), 20, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 3, "RUNNING", at(15), 30, key("job-b"), "next.3mf"),
    ]
    runs = replay_runs(events)
    assert len(runs) == 2
    assert runs[0].end_evidence == "device_job_changed"
    assert runs[0].ended_at == at(15) and runs[0].closed_by_observation is True
    assert runs[1].device_job_key == key("job-b") and runs[1].ended_at == ""


def test_reconnect_of_same_job_merges_and_later_reprint_does_not():
    events = [
        FakeEvent(PRINTER, 4, "RUNNING", at(0), 20, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 4, "STALE", at(10), 20, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 4, "RUNNING", at(12), 25, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 4, "FINISH", at(30), 100, key("job-a"), "part.3mf"),
        # The same file reprinted much later is a separate run, never merged away.
        FakeEvent(PRINTER, 4, "RUNNING", at(600), 5, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 4, "FINISH", at(700), 100, key("job-a"), "part.3mf"),
    ]
    runs = merge_adjacent(replay_runs(events))
    assert len(runs) == 2
    assert runs[0].end_state == "FINISH" and runs[0].max_progress == 100
    assert runs[0].end_evidence == "device_terminal_state"
    assert runs[1].started_at == at(600)


class FakeRecord:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "rec-1")
        self.machine_no = kwargs.get("machine_no", 1)
        self.device_job_key = kwargs.get("device_job_key", "")
        self.print_start_at = kwargs.get("print_start_at", "")
        self.created_at = kwargs.get("created_at", "")


def _one_run(minutes_end=20):
    return replay_runs(
        [
            FakeEvent(PRINTER, 1, "RUNNING", at(0), 10, key("job-a"), "part.3mf"),
            FakeEvent(PRINTER, 1, "FINISH", at(minutes_end), 100, key("job-a"), "part.3mf"),
        ]
    )[0]


def test_classification_separates_safe_review_and_conflict():
    run = _one_run()
    # Identical device job already recorded: nothing to do.
    same = classify(run, [FakeRecord(device_job_key=key("job-a"))], {})
    assert same.classification == SAFE and same.reason == "already_recorded_same_device_job"
    # An unrelated record on the same machine at the same time needs a human.
    overlapping = classify(
        run, [FakeRecord(device_job_key="", print_start_at=at(5))], {}
    )
    assert overlapping.classification == REVIEW
    assert overlapping.reason == "time_overlaps_existing_record"
    # The legacy writer already owns this run: importing would duplicate it.
    legacy = classify(
        run,
        [],
        {1: [{"gcode_file": "part.3mf", "started_at": at(1), "product_name": "part"}]},
    )
    assert legacy.classification == SAFE and legacy.reason == "legacy_owns_run_history_only"
    # Nothing anywhere: safe to insert.
    missing = classify(run, [], {})
    assert missing.classification == SAFE and missing.reason == "missing_from_nexus_and_legacy"
    # A run with no device identity and no file name can never be applied automatically.
    assert replay_runs([FakeEvent(PRINTER, 1, "RUNNING", at(0), 0, "", "")]) == []


def test_same_file_reprint_inside_the_window_is_one_run():
    """Replay must agree with reconciliation that a quick reprint is one physical run."""
    events = [
        FakeEvent(PRINTER, 5, "RUNNING", at(0), 20, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 5, "FINISH", at(30), 100, key("job-a"), "part.3mf"),
        # Same file, new device job two minutes later: one print, not two.
        FakeEvent(PRINTER, 5, "RUNNING", at(32), 5, key("job-b"), "part.3mf"),
        FakeEvent(PRINTER, 5, "FINISH", at(60), 100, key("job-b"), "part.3mf"),
    ]
    runs = merge_same_file_window(replay_runs(events), window_seconds=600)
    assert len(runs) == 1
    assert runs[0].max_progress == 100
    assert runs[0].ended_at == at(60)
    # Without the window the two device jobs stay separate runs.
    assert len(merge_same_file_window(replay_runs(events), window_seconds=-1)) == 2
    # A different file is never merged, however close in time.
    other_file = merge_same_file_window(
        replay_runs(
            [
                FakeEvent(PRINTER, 5, "RUNNING", at(0), 20, key("job-a"), "part.3mf"),
                FakeEvent(PRINTER, 5, "FINISH", at(30), 100, key("job-a"), "part.3mf"),
                FakeEvent(PRINTER, 5, "RUNNING", at(32), 5, key("job-b"), "next.3mf"),
                FakeEvent(PRINTER, 5, "FINISH", at(60), 100, key("job-b"), "next.3mf"),
            ]
        ),
        window_seconds=600,
    )
    assert len(other_file) == 2


def test_summary_and_markdown_report_are_written_from_replay_only():
    events = [
        FakeEvent(PRINTER, 1, "RUNNING", at(0), 10, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "FINISH", at(20), 100, key("job-a"), "part.3mf"),
        FakeEvent(PRINTER, 1, "RUNNING", at(30), 10, key("job-b"), "other.3mf"),
    ]
    runs = replay_runs(events)
    diffs = [classify(run, [], {}) for run in runs]
    summary = summarize(runs, diffs, events)
    assert summary["runs_rebuilt"] == 2 and summary["events_replayed"] == 3
    assert summary["open_runs_at_end"] == 1
    assert summary["classifications"] == {SAFE: 2}
    markdown = render_markdown(summary, runs, diffs)
    assert "只读回放" in markdown and "重建运行数：2" in markdown
    json.dumps(summary, ensure_ascii=False)


def test_replay_reads_real_stored_events_and_writes_files(environment, tmp_path):
    """End-to-end: stored Connector events become runs and a diff, writing files."""
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    post(env, "/events", event(env, ref, 2, "RUNNING", progress_percent=60))
    other = {"instance_id": ref["instance_id"], "printer_id": env[5][1]}
    grant = post(env, "/leases/acquire", other)
    other.update(
        leader_lease_id=grant["leader_lease_id"], connection_session_id="session-b"
    )
    post(env, "/sessions/start", {**other, "generation": 1})
    post(env, "/events", event(env, other, 1, "RUNNING", current_file="other.3mf"))
    summary, runs, diffs = build_report(env[1].SessionLocal, out_dir=str(tmp_path))
    assert summary["events_replayed"] == 3
    assert summary["runs_rebuilt"] == 2
    assert summary["nexus_records_in_scope"] == 2
    # Both runs already exist in Nexus, so nothing is proposed for insertion.
    assert summary["classifications"] == {SAFE: 2}
    assert all(diff.reason == "already_recorded_same_device_job" for diff in diffs)
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "report.md").exists()
    written = (tmp_path / "diff.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(written) == 2
    # The tool is read-only: nothing was created, closed or repriced by the report.
    with env[1].SessionLocal() as db:
        records = list(db.scalars(select(env[2].ThreeDPrintingProductionRecord)))
        assert all(record.print_end_at == "" for record in records)
