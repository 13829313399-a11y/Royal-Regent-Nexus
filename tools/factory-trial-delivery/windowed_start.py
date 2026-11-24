"""GUI-Python entry point: install real file streams before importing the app."""
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    data = root / 'data'
    data.mkdir(exist_ok=True)
    # pythonw can start with None streams. Never bind the app to a console.
    sys.stdin = open(os.devnull, 'r', encoding='utf-8')
    sys.stdout = open(data / 'startup-console.log', 'a', encoding='utf-8', errors='backslashreplace', buffering=1)
    sys.stderr = sys.stdout
    sys.path.insert(0, str(root))
    print('\n--- Windowed start ---', flush=True)
    import launch
    sys.argv = [str(root / 'launch.py'), '--exit-with-browser']
    try:
        return launch.main()
    except Exception as error:
        launch.report_startup_error(root, error)
        return 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # A read-only extraction location can fail even before file logging.
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '启动未完成：' + str(error), '本机试用', 16)
        raise SystemExit(1)
