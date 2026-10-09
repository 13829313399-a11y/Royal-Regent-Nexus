"""Bounded private file computation, with owner-scoped short-lived task results.

Jobs never write business data. Import completion is a separate authenticated,
idempotent transaction. After an API restart the client must check import history.
"""
from __future__ import annotations

import hashlib
import pickle
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import BoundedSemaphore, Event, Lock, Thread, Timer
from uuid import uuid4

from fastapi import HTTPException

from app.services.customer_order_ocr import _run_worker

JOB_SECONDS = 240
RESULT_SECONDS = 1800
MAX_RESULT_BYTES = 32 * 1024 * 1024
MAX_JOBS = 8
OPERATIONS = {"parse", "combined_export", "sheets", "master_parse"}
_slot = BoundedSemaphore(1)
_registry_lock = Lock()
_jobs = {}
LOCK_PATH = Path(tempfile.gettempdir()) / "rr-carton-file-job.lock"


@dataclass
class Budget:
    deadline: float = field(default_factory=lambda: time.monotonic() + JOB_SECONDS)
    cancelled: Event = field(default_factory=Event)

    def check(self):
        if self.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise HTTPException(504, "纸箱文件处理超时，任务已停止；请缩小批次后重试。")


@dataclass
class Job:
    id: str
    owner: str
    factory: str
    operation: str
    fingerprint: str
    folder: object
    metadata: dict
    status: str = "PROCESSING"
    error: str = ""
    error_status: int = 422
    expires: float = field(default_factory=lambda: time.monotonic() + RESULT_SECONDS)
    lock: object = field(default_factory=Lock)
    batch_id: str = ""

    @property
    def path(self):
        return Path(self.folder.name)


def _compute(folder, operation, args):
    if operation not in OPERATIONS:
        raise ValueError("Unsupported carton computation")
    source, result = folder / "input.pkl", folder / "result.pkl"
    with source.open("wb") as stream:
        # Only private server-generated IPC, never deserialize uploaded bytes.
        pickle.dump((operation, args), stream, protocol=5)
    budget = Budget()
    code = _run_worker([sys.executable, "-m", "app.workers.carton_file_job",
        str(source), str(result), str(budget.deadline), str(LOCK_PATH)], budget)
    if not result.is_file() or result.stat().st_size > MAX_RESULT_BYTES:
        raise HTTPException(422, "纸箱文件超出处理资源限制，请拆分后重试；未保存导入批次。")
    with result.open("rb") as stream:
        payload = pickle.load(stream)
    if code or "error" in payload:
        raise HTTPException(payload.get("status", 422), payload.get("error", "纸箱文件处理失败"))
    return payload["value"]


def run_file_job(operation, *args):
    """Compatibility endpoints also isolate computation; caller is a sync route."""
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, "已有纸箱文件正在处理，请稍后重试，勿重复提交。")
    try:
        with tempfile.TemporaryDirectory(prefix="rr-carton-file-") as folder:
            return _compute(Path(folder), operation, args)
    finally:
        _slot.release()


def _expire(identifier):
    with _registry_lock:
        job = _jobs.get(identifier)
        if job is None:
            return
        # Do not remove files while a completion transaction is reading them.
        if job.status == "PROCESSING" or not job.lock.acquire(blocking=False):
            timer = Timer(30, _expire, (identifier,)); timer.daemon = True; timer.start()
            return
        try:
            _jobs.pop(identifier, None)
            job.folder.cleanup()
        finally:
            job.lock.release()


def start_job(owner, factory, operation, args, metadata):
    fingerprint = hashlib.sha256(pickle.dumps((operation, args, metadata), protocol=5)).hexdigest()
    with _registry_lock:
        # Claimed/failed results must not occupy the bounded work capacity.
        # Eviction leaves the durable import batch as the source of truth.
        for identifier, previous in list(_jobs.items()):
            if len(_jobs) < MAX_JOBS:
                break
            if previous.status in {"COMPLETED", "FAILED"} and previous.lock.acquire(blocking=False):
                try:
                    _jobs.pop(identifier, None)
                    previous.folder.cleanup()
                finally:
                    previous.lock.release()
        for job in _jobs.values():
            if (job.owner, job.factory, job.fingerprint) == (owner, factory, fingerprint) and job.status in {"PROCESSING", "READY"}:
                return job_status(job)
        if len(_jobs) >= MAX_JOBS or not _slot.acquire(blocking=False):
            raise HTTPException(429, "已有纸箱文件任务待处理或待领取，请领取结果或稍后重试。")
        try:
            job = Job(uuid4().hex, owner, factory, operation, fingerprint,
                tempfile.TemporaryDirectory(prefix="rr-carton-job-"), metadata)
            _jobs[job.id] = job
        except BaseException:
            _slot.release()
            raise

    def work():
        try:
            _compute(job.path, operation, args)
            job.status = "READY"
        except HTTPException as error:
            job.error, job.error_status, job.status = str(error.detail), error.status_code, "FAILED"
        except Exception:
            job.error, job.status = "文件处理失败，请核对文件或联系管理员；未保存导入批次。", "FAILED"
        finally:
            _slot.release()
            timer = Timer(RESULT_SECONDS, _expire, (job.id,)); timer.daemon = True; timer.start()

    try:
        Thread(target=work, name="carton-file-supervisor", daemon=True).start()
    except BaseException:
        with _registry_lock:
            _jobs.pop(job.id, None)
        job.folder.cleanup()
        _slot.release()
        raise
    return job_status(job)


def get_job(identifier, owner, factory):
    with _registry_lock:
        job = _jobs.get(identifier)
        if job is None:
            raise HTTPException(410, "文件任务已过期或服务已重启；请先核对导入历史再重试。")
        if job.owner != owner or job.factory != factory:
            raise HTTPException(404, "文件任务不存在")
        return job


def job_status(job):
    return {"id": job.id, "status": job.status, "error": job.error,
        "error_status": job.error_status, "batch_id": job.batch_id}


@contextmanager
def result(job):
    with job.lock:
        if job.status == "FAILED":
            raise HTTPException(job.error_status, job.error)
        if job.status not in {"READY", "COMPLETED"}:
            raise HTTPException(409, "文件仍在处理，请等待结果")
        if not (job.path / "result.pkl").is_file():
            raise HTTPException(410, "文件任务已过期，请核对导入历史")
        with (job.path / "result.pkl").open("rb") as stream:
            value = pickle.load(stream)["value"]
        with (job.path / "input.pkl").open("rb") as stream:
            _, args = pickle.load(stream)
        yield value, args
