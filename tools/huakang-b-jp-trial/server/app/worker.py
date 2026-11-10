"""Private JP-only worker entry point, including Windows embedded Python."""
import math
from contextlib import contextmanager
import os
from pathlib import Path
import pickle
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@contextmanager
def job_slot(path):
    """The child owns this lock, so another app instance cannot outlive its guard."""
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"0")
                handle.flush()
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


def main():
    source, result = Path(sys.argv[1]), Path(sys.argv[2])
    deadline = float(sys.argv[3])
    remaining = max(0, min(240, deadline - time.monotonic()))
    watchdog = threading.Timer(remaining, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    tempfile.tempdir = str(source.parent)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(source.parent)
    if os.name != "nt":
        import resource
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(remaining)), max(2, math.ceil(remaining) + 1)))
    try:
        try:
            with job_slot(Path(sys.argv[4])):
                from app.services.huakang_b_jp import intake
                from fastapi import HTTPException
                try:
                    with source.open("rb") as stream:
                        operation, args, kwargs = pickle.load(stream)
                    if operation not in {"_jp_validate_reference", "_jp_preview"}:
                        raise ValueError("Unsupported JP trial operation")
                    payload, code = {"value": getattr(intake, operation)(*args, **kwargs)}, 0
                except HTTPException as error:
                    payload, code = {"error": str(error.detail), "status": error.status_code}, 1
                except (ValueError, MemoryError) as error:
                    payload, code = {"error": str(error) or "问单文件超出内存限制，请缩小批次。", "status": 400}, 1
                except Exception:
                    payload, code = {"error": "问单文件处理失败，请检查文件或联系提供者。", "status": 422}, 1
        except (BlockingIOError, PermissionError):
            payload, code = {"error": "已有问单文件正在处理，请等本次完成，勿重复提交。", "status": 429}, 1
        with result.open("wb") as stream:
            pickle.dump(payload, stream, protocol=5)
        return code
    finally:
        watchdog.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
