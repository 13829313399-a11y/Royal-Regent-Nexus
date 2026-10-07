import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("maintenance_notice", ROOT / "deploy/maintenance_notice.py")
notice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notice)
NOW = datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc)


def read(folder):
    return json.loads((folder / "status.json").read_text(encoding="utf-8"))


def test_countdown_is_five_minutes_and_does_not_stop_service(tmp_path):
    state = notice.publish(tmp_path, "start", now=NOW)
    assert state["starts_at"] == "2026-10-07T04:05:00Z"
    assert read(tmp_path) == state
    assert not (tmp_path / "active").exists()
    with pytest.raises(ValueError, match="not finished"):
        notice.publish(tmp_path, "maintenance", notice_id=state["id"], now=NOW)
    assert read(tmp_path) == state


def test_cutover_failure_keeps_gate_until_verified_recovery(tmp_path):
    state = notice.publish(tmp_path, "start", now=NOW)
    notice.publish(tmp_path, "maintenance", notice_id=state["id"], now=NOW + timedelta(minutes=5))
    assert (tmp_path / "active").read_text() == state["id"]
    notice.publish(tmp_path, "fail", notice_id=state["id"], now=NOW + timedelta(minutes=6))
    assert read(tmp_path)["phase"] == "maintenance" and (tmp_path / "active").exists()
    with pytest.raises(ValueError, match="verify recovery"):
        notice.publish(tmp_path, "cancel", notice_id=state["id"], now=NOW)
    notice.publish(tmp_path, "complete", notice_id=state["id"], now=NOW + timedelta(minutes=7))
    assert read(tmp_path)["phase"] == "completed" and not (tmp_path / "active").exists()
    assert read(tmp_path)["expires_at"] == "2026-10-07T04:22:00Z"


def test_cancel_before_cutover_and_old_operator_cannot_close_new_notice(tmp_path):
    first = notice.publish(tmp_path, "start", now=NOW)
    notice.publish(tmp_path, "cancel", notice_id=first["id"], now=NOW)
    assert read(tmp_path)["phase"] == "cancelled" and not (tmp_path / "active").exists()
    second = notice.publish(tmp_path, "start", now=NOW)
    with pytest.raises(ValueError, match="ID changed"):
        notice.publish(tmp_path, "cancel", notice_id=first["id"], now=NOW)
    assert read(tmp_path) == second
    with pytest.raises(ValueError, match="existing"):
        notice.publish(tmp_path, "start", now=NOW)


def test_concurrent_deployments_cannot_overwrite_each_other(tmp_path):
    barrier = Barrier(2)
    def start():
        barrier.wait()
        try:
            return notice.publish(tmp_path, "start", now=NOW)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    succeeded = [state for state in results if state]
    assert len(succeeded) == 1 and read(tmp_path) == succeeded[0]


@pytest.mark.parametrize("seconds", [0, 14, 3601])
def test_invalid_countdown_never_publishes(tmp_path, seconds):
    with pytest.raises(ValueError, match="Countdown"):
        notice.publish(tmp_path, "start", seconds=seconds, now=NOW)
    assert not (tmp_path / "status.json").exists()
