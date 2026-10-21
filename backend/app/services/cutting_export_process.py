"""One bounded, stateless renderer process; receives captured data, never a DB."""
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi import HTTPException


def package(report, user, title):
    payload = dict(report=report, actor=dict(id=user.id, display_name=user.display_name), title=title)
    worker = Path(__file__).with_name('cutting_export_worker.py')
    try:
        result = subprocess.run([sys.executable, str(worker)],
            input=json.dumps(payload, ensure_ascii=False).encode('utf-8'), capture_output=True,
            timeout=60, check=False,
            env=dict(os.environ, DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1'),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps its child on timeout.
        raise HTTPException(503, '报表生成超时，未返回部分文件，请稍后重试') from None
    except OSError:
        raise HTTPException(503, '报表生成进程无法启动，请稍后重试') from None
    if result.returncode != 0:
        raise HTTPException(503, '报表生成进程异常，未返回部分文件，请稍后重试')
    try:
        header, content = result.stdout.split(b'\n', 1)
        status = json.loads(header)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(503, '报表生成结果不完整，请稍后重试') from None
    if not isinstance(status, dict):
        raise HTTPException(503, '报表生成结果不完整，请稍后重试')
    if 'error' in status:
        if type(status.get('status')) is not int or not 400 <= status['status'] <= 599 or not isinstance(status['error'], str):
            raise HTTPException(503, '报表生成结果不完整，请稍后重试')
        raise HTTPException(status['status'], status['error'])
    if status.get('extension') not in {'xlsx', 'zip'} or not content:
        raise HTTPException(503, '报表生成结果不完整，请稍后重试')
    return content, status['extension']
