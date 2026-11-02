"""Short-lived, actor/factory-bound HTTP attachments for browser-built schedule XLSX."""
import hashlib
import hmac
import io
import os
import re
import secrets
import time
import zipfile
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_BYTES = 8 * 1024 * 1024
TTL = 600
NAMES = {'example': 'QC客排期_示例数据.xlsx', 'template': 'QC客排期_空模板.xlsx', 'formal': 'QC客排期.xlsx'}


def folder():
    return Path(settings.qc_department_data_dir).resolve() / '_schedule_exports'


def signature(owner, value):
    key = settings.qc_department_gateway_token.get_secret_value()
    if not key:
        raise HTTPException(503, '下载服务尚未配置')
    return hmac.new(key.encode(), ('qc-schedule-export:' + owner + ':' + value).encode(), hashlib.sha256).hexdigest()


def clean():
    path = folder()
    if not path.exists():
        return []
    remaining = []
    for item in path.glob('*.xlsx'):
        if not re.fullmatch(r'[a-f0-9]{32}\.xlsx', item.name):
            continue
        try:
            info = item.stat()
            if info.st_mtime < time.time() - TTL:
                item.unlink(missing_ok=True)
            else:
                remaining.append(info.st_size)
        except FileNotFoundError:
            pass
    return remaining


def prepare(content, mode, owner):
    if mode not in NAMES or not content or len(content) > MAX_BYTES:
        raise HTTPException(422, '导出内容或类型不正确')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (len(entries) > 4096 or sum(item.file_size for item in entries) > 64 * 1024 * 1024
                    or not {'[Content_Types].xml', 'xl/workbook.xml'} <= set(archive.namelist())):
                raise ValueError()
    except (zipfile.BadZipFile, ValueError):
        raise HTTPException(422, '导出内容不是有效的 Excel 文件') from None
    nonce = secrets.token_hex(16)
    value = f'{nonce}.{int(time.time()) + TTL}.{mode}'
    token = value + '.' + signature(owner, value)
    path = folder()
    try:
        path.mkdir(parents=True, exist_ok=True)
        active = clean()
        if len(active) >= 128 or sum(active) + len(content) > 128 * 1024 * 1024:
            raise HTTPException(429, '下载任务较多，请稍后重试')
        target = path / (nonce + '.xlsx')
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(content)
    except OSError:
        raise HTTPException(503, '暂时无法准备下载，请重试') from None
    return {'url': 'api/schedule-export/' + token, 'filename': NAMES[mode]}


def download(token, owner):
    match = re.fullmatch(r'([a-f0-9]{32})\.(\d{10})\.(example|template|formal)\.([a-f0-9]{64})', token)
    if not match:
        raise HTTPException(404, '下载不存在')
    nonce, expires, mode, supplied = match.groups()
    value = token.rsplit('.', 1)[0]
    if not hmac.compare_digest(signature(owner, value), supplied):
        raise HTTPException(404, '下载不存在')
    if int(expires) < time.time():
        clean()
        raise HTTPException(410, '下载已过期，请重新点击导出 Excel')
    try:
        data = (folder() / (nonce + '.xlsx')).read_bytes()
    except OSError:
        raise HTTPException(410, '下载已过期，请重新点击导出 Excel') from None
    return data, NAMES[mode]
