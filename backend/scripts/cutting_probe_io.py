"""Atomic pressure-test evidence writes; never touches application business data."""
import json
from pathlib import Path


def write_snapshot(path, value):
    """Keep the last complete file if Windows readers temporarily deny replace.

    Only a sharing/permission refusal on replacement is recoverable. Encoding,
    serialization and disk-write failures propagate to the owner. The newest
    complete pending file remains available until the next successful attempt.
    """
    path=Path(path)
    pending=path.with_name(path.name+'.pending')
    pending.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    try:
        pending.replace(path)
    except PermissionError:
        return False
    return True


def control_tick(folder, diagnostic, last_snapshot, now, *, interval=5):
    """Stopping always has priority over optional periodic evidence capture."""
    folder=Path(folder)
    if (folder/'stop').exists():
        return True,last_snapshot,False
    if not 5<=interval<=60:raise ValueError('Diagnostic checkpoint interval must be 5–60 seconds')
    if now-last_snapshot>=interval:
        complete=write_snapshot(folder/'diagnostics.partial.json',diagnostic.snapshot())
        return False,now,not complete
    return False,last_snapshot,False
