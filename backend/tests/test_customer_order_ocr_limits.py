import asyncio
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
from fastapi import Depends, FastAPI
from PIL import Image, ImageDraw, ImageFont
from starlette.concurrency import run_in_threadpool

from app.services import customer_order_ocr as ocr
from app.services.huaxing_order_legacy import multi_po_parser as parser


@pytest.fixture(autouse=True)
def isolated_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "LOCK_PATH", tmp_path / "ocr.lock")


def _script(tmp_path, text):
    script = tmp_path / "worker.py"
    script.write_text(text, encoding="utf-8")
    return [sys.executable, str(script)]


def _alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
        finally:
            kernel.CloseHandle(handle)
    # A terminated orphan can remain a zombie briefly until init reaps it.
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists() and stat.read_text().split(") ", 1)[1].startswith("Z"):
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@pytest.mark.parametrize("reason", ["deadline", "cancel"])
def test_hung_worker_and_its_child_are_stopped_and_reaped(tmp_path, reason):
    pid_file = tmp_path / "pids.json"
    command = _script(tmp_path, f"""
import json, os, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
Path({str(pid_file)!r}).write_text(json.dumps([os.getpid(), child.pid]))
time.sleep(30)
""")
    budget = ocr.OcrBudget(deadline=time.monotonic() + 5)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ocr._run_worker, command, budget)
        for _ in range(100):
            if pid_file.exists():
                break
            time.sleep(0.03)
        assert pid_file.exists(), "Test worker did not start"
        pids = json.loads(pid_file.read_text())
        if reason == "cancel":
            budget.cancelled.set()
        else:
            budget.deadline = time.monotonic() - 1
        with pytest.raises(ValueError, match="超时|取消"):
            future.result(timeout=8)
    assert time.monotonic() - started < 8
    assert all(not _alive(pid) for pid in pids)


def test_worker_thread_caps_are_private_and_success_is_returned(tmp_path):
    result = tmp_path / "env.json"
    keys = ("OMP_THREAD_LIMIT", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    before = {key: os.environ.get(key) for key in keys}
    command = _script(tmp_path, f"""
import json, os
from pathlib import Path
Path({str(result)!r}).write_text(json.dumps({{key: os.environ.get(key) for key in {keys!r}}}))
""")
    assert ocr._run_worker(command, ocr.OcrBudget()) == 0
    assert json.loads(result.read_text()) == dict.fromkeys(keys, "1")
    assert {key: os.environ.get(key) for key in keys} == before


def test_worker_deadline_and_lock_survive_api_parent_exit(tmp_path):
    pid_file = tmp_path / "orphan-pids.json"
    source, result = tmp_path / "input.pdf", tmp_path / "result.json"
    source.write_bytes(b"fake scan")
    bootstrap = f"""
import json, os, subprocess, sys, time
from pathlib import Path
from app.services.huaxing_order_legacy import order_ocr_worker as worker
def hang(*args):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    Path({str(pid_file)!r}).write_text(json.dumps([os.getpid(), child.pid]))
    time.sleep(30)
worker.recognize = hang
raise SystemExit(worker.main())
"""
    deadline = time.monotonic() + 4
    command = [sys.executable, "-c", bootstrap, str(source), str(result), "1", str(deadline), str(ocr.LOCK_PATH)]
    # This intermediate process is the API parent. It exits immediately, so
    # neither a parent finally block nor a supervisor can enforce the deadline.
    parent = f"""
import os, subprocess
subprocess.Popen({command!r}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, start_new_session=os.name != 'nt',
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
"""
    subprocess.run([sys.executable, "-c", parent], cwd=ocr.BACKEND_DIR, check=True, timeout=5)
    for _ in range(100):
        if pid_file.exists():
            break
        time.sleep(0.02)
    assert pid_file.exists()
    with pytest.raises(ValueError, match="勿重复提交"):
        with ocr._ocr_slot():
            pytest.fail("API crash released an active OCR's slot")
    pids = json.loads(pid_file.read_text())
    while time.monotonic() < deadline + 3 and any(_alive(pid) for pid in pids):
        time.sleep(0.05)
    assert all(not _alive(pid) for pid in pids), "Worker watchdog left orphaned processes"
    with ocr._ocr_slot():
        pass


def test_slot_rejects_parallel_threads_and_other_api_processes(tmp_path):
    with ocr._ocr_slot():
        with pytest.raises(ValueError, match="勿重复提交"):
            with ocr._ocr_slot():
                pytest.fail("Overlapping worker admitted")
        code = f"""
from pathlib import Path
from app.services import customer_order_ocr as ocr
ocr.LOCK_PATH = Path({str(ocr.LOCK_PATH)!r})
try:
    with ocr._ocr_slot():
        raise SystemExit(9)
except ValueError:
    pass
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=ocr.BACKEND_DIR, timeout=10)
        assert result.returncode == 0
    with ocr._ocr_slot():
        pass


def test_failed_scan_cleans_private_files_and_releases_slot(monkeypatch):
    paths = []

    def fail(command, budget):
        paths.append(Path(command[3]).parent)
        assert Path(command[3]).read_bytes() == b"source"
        raise ValueError(ocr.TIMEOUT_MESSAGE)

    monkeypatch.setattr(ocr, "_run_worker", fail)
    for _ in range(2):
        with pytest.raises(ValueError, match="超时"):
            ocr.read_scanned_order_pdf(b"source", 2)
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("payload,exit_code,message", [
    ({"pages": ["first"]}, 0, "不完整"),
    ({"pages": ["first", 2]}, 0, "不完整"),
    ({"error": "timeout"}, 1, "超时"),
    ({"error": "missing"}, 1, "依赖未安装"),
    ({"error": "busy"}, 1, "勿重复提交"),
])
def test_partial_or_failed_ocr_never_returns_partial_order_text(monkeypatch, payload, exit_code, message):
    def fake_worker(command, budget):
        Path(command[4]).write_text(json.dumps(payload), encoding="utf-8")
        return exit_code
    monkeypatch.setattr(ocr, "_run_worker", fake_worker)
    with pytest.raises(ValueError, match=message):
        ocr.read_scanned_order_pdf(b"source", 2)


def test_completed_scan_keeps_original_page_order(monkeypatch):
    def fake_worker(command, budget):
        Path(command[4]).write_text(json.dumps({"pages": ["PO 002", "PO 001"]}), encoding="utf-8")
        return 0
    monkeypatch.setattr(ocr, "_run_worker", fake_worker)
    assert ocr.read_scanned_order_pdf(b"source", 2) == ["PO 002", "PO 001"]


def test_native_text_bypasses_busy_ocr_and_page_limit_is_checked_early(monkeypatch):
    class Page:
        def extract_text(self, **kwargs):
            return "BARTER Purchase Order 123456 quantity 2400 delivery 2026-10-01"
    class PDF:
        pages = [Page()]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(parser.pdfplumber, "open", lambda source: PDF())
    with ocr._ocr_slot():
        pages, used_ocr = parser.read_pdf_pages(b"native")
    assert "123456" in pages[0] and not used_ocr
    with pytest.raises(ValueError, match="最多支持"):
        parser.read_pdf_pages(b"native", max_pages=0)


def test_both_tesseract_passes_have_finite_deadlines():
    calls = []
    class Engine:
        @staticmethod
        def image_to_string(image, **kwargs):
            calls.append(kwargs)
            return "text"
    with Image.new("RGB", (100, 100), "white") as image:
        assert parser._ocr_contract_page(Engine, image, "eng") == "text\ntext"
    assert [call["timeout"] for call in calls] == [30, 15]


def test_request_disconnect_reaches_threadpool_and_budget_is_shared():
    async def scenario():
        app = FastAPI()
        observed = []
        working = Event()
        @app.post("/preview", dependencies=[Depends(ocr.order_ocr_request)])
        async def preview():
            def work():
                budget = ocr._budget.get()
                observed.append(budget)
                working.set()
                assert budget.cancelled.wait(3), "Disconnect did not reach OCR thread"
                with pytest.raises(ValueError, match="取消"):
                    budget.check()
            await run_in_threadpool(work)
            await run_in_threadpool(lambda: observed.append(ocr._budget.get()))
            return {"ok": True}
        async def receive():
            if working.is_set():
                return {"type": "http.disconnect"}
            await asyncio.sleep(0.01)
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = []
        async def send(message):
            sent.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "scheme": "http",
                 "method": "POST", "path": "/preview", "raw_path": b"/preview", "query_string": b"",
                 "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80)}
        await app(scope, receive, send)
        assert len(observed) == 2 and observed[0] is observed[1]
        assert ocr._budget.get() is None
    asyncio.run(scenario())


def test_request_budget_is_not_reset_between_files(monkeypatch):
    budget = ocr.OcrBudget()
    seen = []
    def worker(command, actual):
        seen.append(actual)
        Path(command[4]).write_text(json.dumps({"pages": ["first"]}))
        return 0
    monkeypatch.setattr(ocr, "_run_worker", worker)
    token = ocr._budget.set(budget)
    try:
        ocr.read_scanned_order_pdf(b"one", 1)
        budget.deadline = time.monotonic() - 1
        with pytest.raises(ValueError, match="超时"):
            ocr.read_scanned_order_pdf(b"two", 1)
    finally:
        ocr._budget.reset(token)
    assert seen == [budget]


def test_real_scanned_pdf_worker_smoke(tmp_path):
    from app.services.carton_mark import find_tesseract_cmd
    if not find_tesseract_cmd():
        pytest.skip("Tesseract not installed")
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    # PIL's bundled scalable font keeps this fixture independent of OS fonts.
    font = ImageFont.load_default(size=42)
    draw.text((60, 100), "BARTER PURCHASE ORDER", fill="black", font=font)
    draw.text((60, 280), "PO NUMBER 123456", fill="black", font=font)
    draw.text((60, 520), "QUANTITY 2400", fill="black", font=font)
    payload = BytesIO()
    image.save(payload, format="PDF", resolution=150)
    image.close()
    pages, used_ocr = parser.read_pdf_pages(payload.getvalue())
    assert used_ocr and len(pages) == 1
    assert "123456" in pages[0] and "2400" in pages[0]
