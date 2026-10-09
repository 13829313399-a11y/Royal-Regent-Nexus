"""Private, disposable OCR worker. Invoked only by customer_order_ocr."""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def recognize(source: Path, page_count: int) -> list[str]:
    import pypdfium2 as pdfium
    import pytesseract

    from app.services.carton_mark import configure_tesseract
    from app.services.huaxing_order_legacy.multi_po_parser import _ocr_contract_page

    command, language = configure_tesseract(pytesseract)
    if not command:
        raise ImportError("Tesseract unavailable")
    document = pdfium.PdfDocument(source)
    try:
        if not 1 <= page_count <= 60 or len(document) != page_count:
            raise ValueError("Invalid page count")
        pages = []
        for index in range(page_count):
            page = document[index]
            try:
                width, height = page.get_size()
                # Keep typical contract resolution; cap oversized page memory.
                scale = min(4, math.sqrt(12_000_000 / max(1, width * height)))
                bitmap = page.render(scale=scale)
                try:
                    with bitmap.to_pil().convert("RGB") as image:
                        pages.append(_ocr_contract_page(pytesseract, image, language))
                finally:
                    bitmap.close()
            finally:
                page.close()
        return pages
    finally:
        document.close()


def _expire() -> None:
    # Independent of the API parent's lifetime. The worker was created in its
    # own session; never signal another process group.
    if os.name != "nt" and os.getpgrp() == os.getpid():
        os.killpg(os.getpid(), signal.SIGKILL)
    elif os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(os.getpid()), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            os._exit(124)
    os._exit(124)


def main() -> int:
    from app.services import customer_order_ocr as limits

    source, result = Path(sys.argv[1]), Path(sys.argv[2])
    limits.LOCK_PATH = Path(sys.argv[5])
    remaining = max(0, min(limits.OCR_SECONDS, float(sys.argv[4]) - time.monotonic()))
    watchdog = threading.Timer(remaining, _expire)
    watchdog.daemon = True
    watchdog.start()
    # The supervisor also removes OCR's temporary bitmaps after a hard stop.
    # Keep them inside this request's private directory, never in shared /tmp.
    tempfile.tempdir = str(source.parent)
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = str(source.parent)
    try:
        # The actual worker owns the lock, so an API parent crash cannot admit
        # a second OCR while the orphan is finishing or reaching its deadline.
        with limits._ocr_slot():
            payload = {"pages": recognize(source, int(sys.argv[3]))}
        code = 0
    except ImportError:
        payload, code = {"error": "missing"}, 1
    except RuntimeError as exc:
        payload, code = {"error": "timeout" if "timeout" in str(exc).lower() else "failed"}, 1
    except ValueError as exc:
        payload, code = {"error": "busy" if str(exc) == limits.BUSY_MESSAGE else "failed"}, 1
    except Exception:
        payload, code = {"error": "failed"}, 1
    result.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    watchdog.cancel()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
