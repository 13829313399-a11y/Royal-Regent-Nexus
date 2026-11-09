"""Bounded JP-only child processes for this single-computer trial."""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import os
from pathlib import Path
import pickle
import signal
import sys
import tempfile
from threading import BoundedSemaphore, Event
import time

from fastapi import HTTPException, Request

JOB_SECONDS = 240.0
MAX_RESULT_BYTES = 128 * 1024**2
OPERATIONS = frozenset({"_jp_validate_reference", "_jp_preview"})


@dataclass
class JobBudget:
    directory: Path
    slot: BoundedSemaphore
    deadline: float = field(default_factory=lambda: time.monotonic() + JOB_SECONDS)
    cancelled: Event = field(default_factory=Event)

    def check(self):
        if self.cancelled.is_set():
            raise HTTPException(499, "问单处理已取消，任务已停止。")
        if time.monotonic() >= self.deadline:
            raise HTTPException(504, "问单处理超时，任务已停止。请缩小批次后重试。")


_budget: ContextVar[JobBudget | None] = ContextVar("jp_trial_budget", default=None)


async def order_job_request(request: Request):
    budget = JobBudget(request.app.state.job_directory, request.app.state.job_slot)
    token = _budget.set(budget)

    async def monitor():
        while not budget.cancelled.is_set():
            if await request.is_disconnected():
                budget.cancelled.set()
                return
            await asyncio.sleep(0.2)

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


async def _execute(operation, args, kwargs, budget):
    budget.check()
    if not budget.slot.acquire(blocking=False):
        raise HTTPException(429, "已有问单文件正在处理，请等本次完成，勿重复提交。")
    try:
        return await _execute_owned(operation, args, kwargs, budget)
    finally:
        budget.slot.release()


async def _execute_owned(operation, args, kwargs, budget):
    with tempfile.TemporaryDirectory(prefix="jp-job-", dir=budget.directory) as folder:
        source, result = Path(folder) / "input.pkl", Path(folder) / "result.pkl"
        with source.open("wb") as stream:
            # Private IPC generated here; uploaded archives are never unpickled.
            pickle.dump((operation, args, kwargs), stream, protocol=5)
        if source.stat().st_size > MAX_RESULT_BYTES:
            raise HTTPException(413, "本批问单和参照内容过大，请拆分后重试。")
        worker = Path(__file__).parents[1] / "worker.py"
        process = await asyncio.create_subprocess_exec(sys.executable, str(worker), str(source),
            str(result), str(budget.deadline), str(budget.directory.parent / "jp-worker.lock"), stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name != "nt")
        waiter = asyncio.create_task(process.wait())
        try:
            while not waiter.done():
                budget.check()
                await asyncio.wait({waiter}, timeout=min(0.2, max(0.001, budget.deadline - time.monotonic())))
            code = waiter.result()
            budget.check()
            if not result.is_file() or result.stat().st_size > MAX_RESULT_BYTES:
                raise HTTPException(422, "问单文件处理未完成或超出资源限制，请缩小批次后重试。")
            with result.open("rb") as stream:
                payload = pickle.load(stream)
            if code or "error" in payload:
                raise HTTPException(payload.get("status", 422), payload.get("error", "问单文件处理失败。"))
            return payload["value"]
        finally:
            if process.returncode is None:
                try:
                    if os.name == "nt":
                        # JP workers never launch OCR/converter descendants.
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await waiter


async def run_order_job(function, *args, db=None, **kwargs):
    if function.__name__ not in OPERATIONS:
        raise RuntimeError("Unsupported JP trial file operation")
    budget = _budget.get()
    if budget is None:
        raise RuntimeError("JP file jobs require a request budget")
    budget.check()
    if db is not None:
        if db.new or db.dirty or db.deleted:
            raise RuntimeError("Cannot process files with pending database writes")
        db.rollback()
    task = asyncio.create_task(_execute(function.__name__, args, kwargs, budget))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        budget.cancelled.set()
        try:
            await asyncio.shield(task)
        except (HTTPException, asyncio.CancelledError):
            pass
        raise
