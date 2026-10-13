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
    try:
        apply_memory_limit(memory)
    except Exception:
        Path(target).write_text(json.dumps(dict(error='parse_resource_unavailable')), encoding='utf-8')
        return
    # Pipe EOF also stops a child whose supervisor was killed without shutdown.
    def parent_closed():
        os.read(sys.stdin.fileno(), 1)
        os._exit(125)
    Thread(target=parent_closed, daemon=True).start()
    watchdog = Timer(float(timeout) + 1, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    try:
        result = dict(segments=extract(Path(source).read_bytes(), extension, int(pages), int(characters)))
    except DocumentParseError as exc:
        result = dict(error=exc.code)
    except MemoryError:
        result = dict(error='parse_memory_limit')
    except Exception:
        result = dict(error="parse_failed")
    Path(target).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
