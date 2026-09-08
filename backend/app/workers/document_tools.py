"""Run with python -m app.workers.document_tools (SQLite: one worker)."""
import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import auth  # noqa: F401 - register owner FK metadata in this process
from app.core.config import settings
from app.services.document_tools import storage
from app.services.document_tools.pipeline import run_one


def check_health():
    import json
    for path in (storage.root() / "heartbeats").glob(socket.gethostname() + "-*.json"):
        try:
            if json.loads(path.read_text(encoding="utf-8"))["timestamp"] > time.time() - 25:
                return 0
        except (OSError, ValueError, KeyError):
            continue
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--slot", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        return check_health()
    if args.once:
        run_one(SessionLocal)
        return 0
    if engine.dialect.name == "postgresql" and not args.slot and settings.document_tools_worker_concurrency > 1:
        children = [subprocess.Popen([sys.executable, "-m", "app.workers.document_tools", "--slot"]) for _ in range(settings.document_tools_worker_concurrency)]
        try:
            while all(child.poll() is None for child in children):
                time.sleep(2)
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                child.wait(timeout=15)
        return 1
    lock = None
    if engine.dialect.name == "sqlite":
        lock = (storage.root() / ".sqlite-worker.lock").open("a+b")
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                print("SQLite document worker already running", file=sys.stderr)
                return 1
        else:
            import fcntl
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 1
    stopped = threading.Event()
    heartbeat = storage.resolve(f"heartbeats/{socket.gethostname()}-{os.getpid()}.json")

    def ping():
        while not stopped.is_set():
            try:
                with SessionLocal() as db:
                    db.execute(text("SELECT 1"))
                storage.atomic_json(heartbeat, {"timestamp": time.time(), "pid": os.getpid(), "host": socket.gethostname()})
            except Exception:
                pass
            stopped.wait(5)

    def shutdown(*_):
        stopped.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    ticker = threading.Thread(target=ping, daemon=True)
    ticker.start()
    try:
        while not stopped.is_set():
            if not settings.document_tools_enabled:
                stopped.wait(2)
                continue
            try:
                if not run_one(SessionLocal):
                    stopped.wait(1)
            except Exception:
                # Do not emit source text, credentials or provider messages.
                print("Document worker could not claim a task; retrying", file=sys.stderr)
                stopped.wait(3)
    finally:
        stopped.set()
        ticker.join(timeout=6)
        heartbeat.unlink(missing_ok=True)
        if lock:
            lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
