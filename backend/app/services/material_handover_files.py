"""Disposable, bounded document extraction; no business writes in the worker."""
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import BoundedSemaphore, Event
from fastapi import HTTPException
from app.services.customer_order_ocr import _run_worker
from app.services.material_handover_parser import validate_file

_slot = BoundedSemaphore(1)
LOCK_PATH = Path(tempfile.gettempdir()) / 'rr-material-handover-extract.lock'


@dataclass
class Budget:
    deadline: float = field(default_factory=lambda: time.monotonic() + 180)
    cancelled: Event = field(default_factory=Event)
    verb: str = '单据识别'

    def check(self):
        if self.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise HTTPException(504, f'{self.verb}超时，处理进程已停止，请拆分或上传更清晰的文件')


def extract(name, content):
    name = validate_file(name, content)
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, '已有单据正在识别，请稍后重试')
    try:
        with tempfile.TemporaryDirectory(prefix='rr-material-worker-') as folder:
            path = Path(folder)
            (path / 'input.bin').write_bytes(content)
            (path / 'request.json').write_text(json.dumps({'name': name}), encoding='utf-8')
            budget = Budget()
            result_code = _run_worker([sys.executable, '-m', 'app.workers.material_handover', folder,
                str(budget.deadline), str(LOCK_PATH)], budget)
            result_path = path / 'result.json'
            if not result_path.is_file() or result_path.stat().st_size > 10 * 1024 * 1024:
                raise HTTPException(422, '文件无法在资源限制内识别，请拆分后重试')
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result_code or 'error' in result:
                raise HTTPException(result.get('status', 422), result.get('error', '单据识别失败，请检查原文件'))
            return result['value']
    finally:
        _slot.release()


def render_original(name, content, data, extraction, code, corner):
    """Private bounded rendering with the same cross-process gate as extraction."""
    name = validate_file(name, content)
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, '已有单据正在处理，请稍后重试原单加码')
    try:
        with tempfile.TemporaryDirectory(prefix='rr-handover-print-') as folder:
            path = Path(folder)
            (path / 'input.bin').write_bytes(content)
            (path / 'request.json').write_text(json.dumps(dict(operation='print', name=name, data=data,
                extraction=extraction, code=code, corner=corner), ensure_ascii=False), encoding='utf-8')
            budget = Budget(verb='原单加码')
            result_code = _run_worker([sys.executable, '-m', 'app.workers.material_handover', folder,
                str(budget.deadline), str(LOCK_PATH)], budget)
            result_path = path / 'result.json'
            if not result_path.is_file() or result_path.stat().st_size > 1024*1024:
                raise HTTPException(422, '无法准备原单加码打印，请检查打印区域或拆分文件')
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result_code or 'error' in result:
                raise HTTPException(result.get('status', 422), result.get('error', '原单加码失败，请重试'))
            output = path / 'output.pdf'
            if not output.is_file() or not 0 < output.stat().st_size <= 50*1024*1024:
                raise HTTPException(422, '原单加码输出无效或过大，请拆分后重试')
            return output.read_bytes()
    finally:
        _slot.release()
