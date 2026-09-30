"""Resource boundary for the legacy scanned customer-order PDF parser.

The OCR workers share a lock in one container. Each runs in an owned process
group so a hung renderer or Tesseract cannot outlive its deadline.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from starlette.requests import Request


OCR_SECONDS = 180.0
POLL_SECONDS = 0.2
BUSY_MESSAGE = "已有扫描订单正在识别，请稍后重试，勿重复提交。"
TIMEOUT_MESSAGE = "扫描 PDF 识别超时，任务已停止。请将文件拆成较小批次后重试。"
LOCK_PATH = Path(tempfile.gettempdir()) / "rr-customer-order-ocr.lock"
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass
class OcrBudget:
    deadline: float = field(default_factory=lambda: time.monotonic() + OCR_SECONDS)
    cancelled: Event = field(default_factory=Event)

    def check(self) -> None:
        if self.cancelled.is_set():
            raise ValueError("已取消扫描订单识别。")
        if time.monotonic() >= self.deadline:
            raise ValueError(TIMEOUT_MESSAGE)


_budget: ContextVar[OcrBudget | None] = ContextVar("customer_order_ocr_budget", default=None)


async def order_ocr_request(request: Request):
    """FastAPI dependency; multipart uploads have been read before monitoring."""
    budget = OcrBudget()
    token = _budget.set(budget)

    async def monitor():
        while not budget.cancelled.is_set():
            if await request.is_disconnected():
                budget.cancelled.set()
                return
            await asyncio.sleep(POLL_SECONDS)

    watcher = asyncio.create_task(monitor())
    try:
        yield
    finally:
        budget.cancelled.set()
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        _budget.reset(token)


@contextmanager
def _ocr_slot():
    # Never unlink a lock file: a new inode would admit overlapping workers.
    with LOCK_PATH.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError(BUSY_MESSAGE) from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(BUSY_MESSAGE) from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _stop_process_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            if process.poll() is None:
                # This PID is still owned by Popen; target only its worker subtree.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=True,
                )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def _run_worker(command: list[str], budget: OcrBudget) -> int:
    budget.check()
    env = {**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1",
           "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    process = subprocess.Popen(
        command, cwd=BACKEND_DIR, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        while not _worker_exited(process):
            budget.check()
            budget.cancelled.wait(min(POLL_SECONDS, max(0, budget.deadline - time.monotonic())))
        budget.check()
    finally:
        _stop_process_tree(process)
    return process.returncode


def _worker_exited(process: subprocess.Popen) -> bool:
    if os.name == "nt":
        return process.poll() is not None
    # Leave the leader unreaped until its entire group has been cleaned up.
    # This keeps the PID reserved even if it exited leaving a child behind.
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def read_scanned_order_pdf(content: bytes, page_count: int) -> list[str]:
    budget = _budget.get() or OcrBudget()
    budget.check()
    with tempfile.TemporaryDirectory(prefix="rr-order-ocr-") as temp:
        source, result = Path(temp) / "source.pdf", Path(temp) / "result.json"
        source.write_bytes(content)
        code = _run_worker([
            sys.executable, "-m", "app.services.huaxing_order_legacy.order_ocr_worker",
            str(source), str(result), str(page_count), str(budget.deadline), str(LOCK_PATH),
        ], budget)
        if not result.is_file() or result.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("扫描 PDF 识别失败，任务已停止，请检查文件后重试。")
        payload = json.loads(result.read_text(encoding="utf-8"))
        if code != 0:
            messages = {
                "timeout": TIMEOUT_MESSAGE,
                "missing": "扫描 PDF OCR 依赖未安装，请联系管理员检查识别服务。",
                "busy": BUSY_MESSAGE,
            }
            raise ValueError(messages.get(payload.get("error"), "扫描 PDF 识别失败，请检查文件后重试。"))
        pages = payload.get("pages")
        if not isinstance(pages, list) or len(pages) != page_count or not all(isinstance(p, str) for p in pages):
            raise ValueError("扫描 PDF 识别结果不完整，请重试。")
        return pages
