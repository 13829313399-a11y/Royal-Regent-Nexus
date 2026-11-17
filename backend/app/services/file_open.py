"""Open generated shipping files with the host's default application."""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def open_bytes(filename: str, content: bytes) -> str:
    safe_name = Path(filename or 'document').name
    stem, suffix = os.path.splitext(safe_name)
    folder = Path(tempfile.gettempdir()) / 'royal-regent-open'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S")}{suffix}'
    target.write_bytes(content)
    if sys.platform.startswith('win'):
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(target)])
    else:
        subprocess.Popen(['xdg-open', str(target)])
    return str(target)


def save_to_downloads(filename: str, content: bytes) -> str:
    """Save a copy under the host user's Downloads folder and return its path."""
    folder = Path.home() / 'Downloads'
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename or 'document').name
    stem, suffix = os.path.splitext(safe_name)
    target = folder / safe_name
    if target.exists():
        target = folder / f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S")}{suffix}'
    target.write_bytes(content)
    return str(target)
