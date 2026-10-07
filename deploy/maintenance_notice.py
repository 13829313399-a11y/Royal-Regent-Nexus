#!/usr/bin/env python3
"""Publish a public maintenance notice independently of the business API."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o755)
    with (folder / ".lock").open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            # Windows can lock a byte beyond EOF. Reading the lock byte before
            # acquiring it would itself fail while another publisher owns it.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path, text):
    descriptor, temp = tempfile.mkstemp(prefix=".notice-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def publish(folder, action, *, notice_id="", seconds=300, message="", now=None):
    folder = Path(folder)
    now = now or datetime.now(timezone.utc)
    stamp = lambda time: time.isoformat().replace("+00:00", "Z")
    if not 15 <= seconds <= 3600:
        raise ValueError("Countdown must be between 15 and 3600 seconds")
    if len(message) > 300:
        raise ValueError("Public message must be at most 300 characters")
    with locked(folder):
        status_path, flag_path = folder / "status.json", folder / "active"
        state = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        if action == "start":
            if state.get("phase") in {"scheduled", "maintenance"} or flag_path.exists():
                raise ValueError("An existing maintenance notice must be completed or cancelled first")
            state = {"id": uuid4().hex, "phase": "scheduled", "starts_at": stamp(now + timedelta(seconds=seconds)),
                     "message": message or "系统即将更新并暂时停止服务，请及时保存正在填写的内容。"}
        else:
            if not notice_id or state.get("id") != notice_id:
                raise ValueError("Notice ID changed; refusing to alter another deployment")
            phase = state.get("phase")
            if action in {"maintenance", "fail"}:
                if phase not in {"scheduled", "maintenance"}:
                    raise ValueError("Only an active deployment can enter maintenance")
                if action == "maintenance" and now < datetime.fromisoformat(state["starts_at"].replace("Z", "+00:00")):
                    raise ValueError("Countdown has not finished")
                if action == "fail" and phase != "maintenance":
                    raise ValueError("Before cutover, cancel the notice instead")
                atomic_write(flag_path, notice_id)
                state.update(phase="maintenance", message=message or (
                    "更新尚未完成，服务仍在维护中，请保留当前页面并等待恢复。" if action == "fail" else
                    "系统正在更新，暂时无法操作。请保留当前页面，恢复后会提示您。"))
            elif action in {"complete", "cancel"}:
                if phase not in {"scheduled", "maintenance"}:
                    raise ValueError("This deployment is already closed")
                if action == "complete" and phase != "maintenance":
                    raise ValueError("Only maintenance can be completed")
                if action == "cancel" and phase != "scheduled":
                    raise ValueError("After cutover, verify recovery and complete instead of cancelling")
                state.update(phase="completed" if action == "complete" else "cancelled",
                             expires_at=stamp(now + timedelta(minutes=15)),
                             message=message or ("系统更新已完成，可以继续使用。刷新前请核对未保存内容。" if action == "complete" else
                                                 "本次更新已取消，您可以继续使用系统。"))
            else:
                raise ValueError("Unknown action")
        state["updated_at"] = stamp(now)
        atomic_write(status_path, json.dumps(state, ensure_ascii=False))
        if action == "complete":
            # Remove the API/page gate only after the operator's health checks.
            flag_path.unlink(missing_ok=True)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "maintenance", "complete", "cancel", "fail"])
    parser.add_argument("--notice-dir", default=".deployment-notice")
    parser.add_argument("--id", default="")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--message", default="")
    args = parser.parse_args()
    try:
        state = publish(args.notice_dir, args.action, notice_id=args.id, seconds=args.seconds, message=args.message)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Maintenance notice rejected: {error}\n")
    print(state["id"])


if __name__ == "__main__":
    main()
