"""Synthetic subprocess acceptance for the shared loopback launcher."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

import pytest

LAUNCH = Path(__file__).resolve().parents[1] / "launch.py"
spec = importlib.util.spec_from_file_location("trial_launcher", LAUNCH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def package(tmp_path, fail=False):
    root = tmp_path / "中文 空格 试用包"
    backend = root / "backend/app"
    backend.mkdir(parents=True)
    (backend / "__init__.py").write_text("")
    shutil.copyfile(LAUNCH, root / "launch.py")
    (root / "trial.json").write_text(json.dumps({"kind": "jp", "name": "合成启动测试", "factory_id": "huakang-b"}), encoding="utf-8")
    (backend / "main.py").write_text('''
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI

def create_app(data_dir, static_dir, host, port):
    assert host == "127.0.0.1"
    @asynccontextmanager
    async def lifespan(app):
        if FAIL:
            raise RuntimeError("synthetic startup failure")
        yield
    app = FastAPI(lifespan=lifespan)
    @app.get("/slow")
    async def slow():
        (Path(data_dir) / "slow.started").write_text("started")
        await asyncio.sleep(60)
        return {"status": "finished"}
    return app
'''.replace("FAIL", repr(fail)), encoding="utf-8")
    return root


def start(root):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
    return subprocess.Popen([sys.executable, str(root / "launch.py"), "--no-browser"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", **options)


def ready(root, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail("Launcher stopped before readiness: " + process.stdout.read())
        try:
            value = json.loads((root / "data/running.json").read_text())
            if launcher.instance_is_ready(value["port"], value["id"]):
                return value
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    pytest.fail("Launcher was not ready within 15 seconds")


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        try:
            process.wait(15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(5)
            raise
    if process.stdout:
        process.stdout.close()


def test_same_folder_reopens_verified_process_and_keeps_data(tmp_path):
    root = package(tmp_path)
    process = start(root)
    try:
        identity = ready(root, process)
        running = root / "data/running.json"
        (root / "data/preserve.txt").write_text("existing trial data")
        second = subprocess.run([sys.executable, str(root / "launch.py"), "--no-browser"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=8)
        assert second.returncode == 0 and "程序已启动" in second.stdout
        assert json.loads(running.read_text()) == identity
        running.write_text(json.dumps({**identity, "id": "unrelated-process"}))
        unrelated = subprocess.run([sys.executable, str(root / "launch.py"), "--no-browser"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=8)
        assert unrelated.returncode == 1
        running.write_text(json.dumps(identity))
    finally:
        stop(process)
    assert not (root / "data/running.json").exists()
    assert (root / "data/preserve.txt").read_text() == "existing trial data"
    lock = launcher.InstanceLock(root / "data/.trial.lock")
    lock.close()


def test_shutdown_cancels_slow_request_and_releases_instance_lock(tmp_path):
    root = package(tmp_path)
    process = start(root)
    request_thread = None
    try:
        identity = ready(root, process)
        def slow_request():
            connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=15)
            try:
                connection.request("GET", "/slow")
                connection.getresponse().read()
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
        request_thread = threading.Thread(target=slow_request, daemon=True)
        request_thread.start()
        deadline = time.monotonic() + 5
        while not (root / "data/slow.started").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (root / "data/slow.started").exists()
        started = time.monotonic()
        stop(process)
        assert time.monotonic() - started < 12
    finally:
        stop(process)
        if request_thread:
            request_thread.join(timeout=2)
    assert not (root / "data/running.json").exists()
    lock = launcher.InstanceLock(root / "data/.trial.lock")
    lock.close()


def test_failed_server_start_has_nonzero_exit_and_no_running_marker(tmp_path):
    root = package(tmp_path, fail=True)
    process = start(root)
    try:
        process.wait(10)
        assert process.returncode != 0
        assert not (root / "data/running.json").exists()
    finally:
        stop(process)
