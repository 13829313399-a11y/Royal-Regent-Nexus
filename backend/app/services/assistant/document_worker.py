"""Invoked only by the bounded parser supervisor, never an HTTP entrypoint."""
import json
from pathlib import Path
import sys
import os
from threading import Thread, Timer
from document_parser import extract, DocumentParseError
from document_limits import apply_memory_limit


def main():
    source, target, extension, pages, characters, timeout = sys.argv[1:7]
    memory = sys.argv[7] if len(sys.argv) > 7 else '512'
    # pypdf may import NumPy before OCR initialization. Set native thread limits
    # before any document library import, in this disposable process only.
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    try:
        apply_memory_limit(memory)
    except Exception:
        Path(target).write_text(json.dumps(dict(error='parse_resource_unavailable')), encoding='utf-8')
        return
    if extension in ('.pdf', '.png', '.jpg', '.jpeg'):
        # Windows/Python native NumPy initialization stalls when Python monitor
        # threads already exist. Load this trusted dependency under the memory
        # cap before starting them and before reading any untrusted input. The
        # external supervisor's deadline/cancellation covers this startup too.
        try:
            import numpy
        except MemoryError:
            Path(target).write_text(json.dumps(dict(error='parse_memory_limit')), encoding='utf-8')
            return
        except ImportError:
            # Text PDF extraction does not require this optional dependency;
            # image OCR reports ocr_unavailable if its engine cannot initialize.
            pass
    # Pipe EOF also stops a child whose supervisor was killed without shutdown.
    def parent_closed():
        os.read(sys.stdin.fileno(), 1)
        os._exit(125)
    Thread(target=parent_closed, daemon=True).start()
    watchdog = Timer(float(timeout) + 1, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    try:
        if extension in ('.docx', '.xlsx'):
            # openpyxl's optional NumPy integration is unnecessary for saved
            # scalar cells. Native numeric-library initialization can stall
            # under the OS memory cap. Disable it only in this disposable child;
            # retain the cap and never alter the API process's imports.
            sys.modules['numpy'] = None
        previews = {}
        raw = Path(source).read_bytes()
        segments = extract(raw, extension, int(pages), int(characters), previews)
        from document_retrieval import stamp_segments
        segments = stamp_segments(raw, segments)
        result = dict(segments=segments, previews=previews)
    except DocumentParseError as exc:
        result = dict(error=exc.code)
    except MemoryError:
        result = dict(error='parse_memory_limit')
    except Exception:
        result = dict(error="parse_failed")
    Path(target).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
