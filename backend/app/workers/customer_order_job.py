"""Private order-computation worker; no database writes or API startup."""
from __future__ import annotations

import math
import os
import pickle
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def job_slot(path):
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0"); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def compute(source):
    from app.services.customer_order_jobs import OPERATIONS
    with source.open("rb") as stream:
        operation, args, kwargs = pickle.load(stream)
    if operation not in OPERATIONS:
        raise ValueError("Unsupported customer-order job")
    if operation == "parse_workbook":
        from app.services.customer_order_history import parse_workbook
        function = parse_workbook
    else:
        from app.api import customer_order
        function = getattr(customer_order, operation)
    return function(*args, **kwargs)


def main():
    from app.services.huaxing_order_legacy.order_ocr_worker import _expire
    source, result = Path(sys.argv[1]), Path(sys.argv[2])
    deadline = float(sys.argv[3])
    remaining = max(0, min(240, deadline - time.monotonic()))
    watchdog = threading.Timer(remaining, _expire)
    watchdog.daemon = True
    watchdog.start()
    # Nested OCR and converters must stay in this owned process group so all
    # descendants die when a browser disconnects or the supervisor is stopped.
    os.environ["RR_CUSTOMER_ORDER_JOB_WORKER"] = "1"
    tempfile.tempdir = str(source.parent)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(source.parent)
    if os.name != "nt":
        import resource
        # Darwin does not support this Linux address-space limit reliably.
        # Keep Linux production limits unchanged; all platforms retain watchdog.
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(remaining)), max(2, math.ceil(remaining) + 1)))
    try:
        with job_slot(Path(sys.argv[4])):
            try:
                value = compute(source)
                payload, code = {"value": value}, 0
            except MemoryError:
                payload, code = {"error": "订单文件超出处理内存限制，请缩小批次或整理排期后重试。", "status": 422}, 1
            except ValueError as error:
                payload, code = {"error": str(error), "status": 400}, 1
            except Exception:
                payload, code = {"error": "订单文件处理失败，请检查文件或联系管理员。", "status": 422}, 1
            with result.open("wb") as stream:
                pickle.dump(payload, stream, protocol=5)
            return code
    except (BlockingIOError, PermissionError):
        with result.open("wb") as stream:
            pickle.dump({"error": "已有订单文件正在处理，请稍后重试，勿重复提交。", "status": 429}, stream)
        return 1
    finally:
        watchdog.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
