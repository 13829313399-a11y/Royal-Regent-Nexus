"""Killable public web reads; DNS cannot outlive the bounded child process."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from .errors import AssistantError

READ_TIMEOUT_SECONDS = 15


async def read(url):
    env = {key: os.environ[key] for key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "PATH") if key in os.environ}
    env["PYTHONUTF8"] = "1"
    try:
        child = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("web_fetch_worker.py")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except OSError:
        raise AssistantError("page_read_unavailable", "网页读取暂不可用，其他来源已保留。", 503) from None
    try:
        raw, _ = await asyncio.wait_for(child.communicate(json.dumps({"url": url}).encode()), READ_TIMEOUT_SECONDS)
        if len(raw) > 150000 or child.returncode != 0:
            raise AssistantError("page_read_failed", "网页读取未完成，其他来源已保留。")
        result = json.loads(raw)
        if not result.get("ok"):
            raise AssistantError(result.get("code", "page_read_failed"), "网页读取受限或未完成，其他来源已保留。")
        return result["page"]
    except asyncio.TimeoutError:
        raise AssistantError("page_timeout", "网页读取超时，其他来源已保留。", 504, True) from None
    except (ValueError, KeyError):
        raise AssistantError("page_read_failed", "网页读取结果无效，其他来源已保留。") from None
    finally:
        if child.returncode is None:
            child.kill()
        await child.wait()
