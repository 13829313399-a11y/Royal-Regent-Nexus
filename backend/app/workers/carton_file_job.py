"""Private disposable carton file worker. Never connects to the business DB."""
import math
import os
import pickle
import sys
import tempfile
import threading
import time
from pathlib import Path


def main():
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["SEED_DEFAULT_ACCOUNTS"] = "false"
    os.environ["RR_CUSTOMER_ORDER_JOB_WORKER"] = "1"
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    remaining = max(0, min(240, float(sys.argv[3]) - time.monotonic()))
    watchdog = threading.Timer(remaining, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    tempfile.tempdir = str(source.parent)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(source.parent)
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(remaining)), max(2, math.ceil(remaining) + 1)))
    from fastapi import HTTPException
    from app.workers.customer_order_job import job_slot
    try:
        with job_slot(Path(sys.argv[4])):
            with source.open("rb") as stream:
                operation, args = pickle.load(stream)
            if operation == "parse":
                from app.services.carton_procurement_imports import parse_carton_file
                value = parse_carton_file(*args)
            elif operation == "sheets":
                from app.services.carton_procurement_imports import _sheet_rows
                value = _sheet_rows(*args)
            elif operation == "master_parse":
                from app.services.carton_master_import import parse
                value = parse(*args)
            elif operation == "combined_export":
                from app.services.carton_procurement_export import build_combined_purchase_order_workbook
                value = build_combined_purchase_order_workbook(args[0], generated_at=args[1])
            else:
                raise HTTPException(422, "不支持的文件处理类型")
            payload, code = {"value": value}, 0
    except HTTPException as error:
        payload, code = {"error": str(error.detail), "status": error.status_code}, 1
    except (BlockingIOError, PermissionError):
        payload, code = {"error": "已有纸箱文件正在处理，请稍后重试", "status": 429}, 1
    except MemoryError:
        payload, code = {"error": "文件超出内存限制，请拆分后重试", "status": 422}, 1
    except Exception:
        payload, code = {"error": "纸箱文件解析失败，请检查格式或联系管理员", "status": 422}, 1
    try:
        with target.open("wb") as stream:
            pickle.dump(payload, stream, protocol=5)
    finally:
        watchdog.cancel()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
