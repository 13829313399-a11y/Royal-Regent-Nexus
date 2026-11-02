"""Bounded OOXML handling and the signed ONLYOFFICE protocol."""
import base64
import hashlib
import hmac
import json
import time
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit, unquote
from zipfile import BadZipFile, ZipFile

import httpx
from fastapi import HTTPException
from app.core.config import settings

MAX_BYTES = 100 * 1024 * 1024


def secret():
    value = settings.onlyoffice_jwt_secret.get_secret_value()
    if len(value) < 32:
        raise HTTPException(503, "在线文档尚未配置")
    return value.encode()


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign(payload):
    header = b64(b'{"alg":"HS256","typ":"JWT"}')
    body = b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    message = f"{header}.{body}"
    return message + "." + b64(hmac.new(secret(), message.encode(), hashlib.sha256).digest())


def verify(token):
    try:
        if not isinstance(token, str) or len(token) > 65536:
            raise ValueError()
        header, body, signature = token.split(".")
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded_header = json.loads(decode(header))
        if not isinstance(decoded_header, dict) or decoded_header.get("alg") != "HS256":
            raise ValueError()
        expected = b64(hmac.new(secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        payload = json.loads(decode(body))
        if not isinstance(payload, dict) or ("exp" in payload and float(payload["exp"]) <= time.time()):
            raise ValueError()
        return payload
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(403, "文档签名无效或已过期") from None


def validate(data, extension):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "文件不能超过 100 MB")
    if extension not in {"docx", "xlsx"}:
        raise HTTPException(422, "请选择 DOCX 或 XLSX 文件")
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {item.filename for item in entries}
            required = "word/document.xml" if extension == "docx" else "xl/workbook.xml"
            if len(entries) > 5000 or len(names) != len(entries) or sum(i.file_size for i in entries) > 160 * 1024 * 1024:
                raise ValueError()
            if required not in names or "[Content_Types].xml" not in names:
                raise ValueError()
            for item in entries:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.flag_bits & 1:
                    raise ValueError()
                if "vbaproject" in item.filename.lower():
                    raise ValueError()
            if archive.testzip() is not None:
                raise ValueError()
    except (BadZipFile, ValueError, RuntimeError, OSError):
        raise HTTPException(422, "文档损坏、加密、含宏或超过安全解析限制，请另存为普通 DOCX / XLSX") from None


def cache_url(url):
    """Only server-generated cache objects, never redirects or arbitrary fetches."""
    try:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment or "\\" in url:
            raise ValueError()
        for base in (settings.onlyoffice_internal_url, settings.onlyoffice_public_url):
            allowed = urlsplit(base.rstrip("/"))
            prefix = allowed.path.rstrip("/") + "/cache/files/"
            if (parsed.scheme, parsed.netloc) != (allowed.scheme, allowed.netloc) or not parsed.path.startswith(prefix):
                continue
            decoded = unquote(unquote(parsed.path))
            if ".." in decoded.split("/") or "\\" in decoded or any(ord(c) < 32 for c in url):
                raise ValueError()
            suffix = parsed.path[len(allowed.path.rstrip("/")):]
            return settings.onlyoffice_internal_url.rstrip("/") + suffix + ("?" + parsed.query if parsed.query else "")
    except (ValueError, TypeError):
        pass
    raise HTTPException(403, "保存文件地址不在受信任的文档服务内")


def fetch_saved(url):
    target = cache_url(url)
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        with client.stream("GET", target) as response:
            response.raise_for_status()
            result = bytearray()
            for chunk in response.iter_bytes(65536):
                result.extend(chunk)
                if len(result) > MAX_BYTES:
                    raise HTTPException(413, "保存文件超过 100 MB")
            return bytes(result)


def command(payload):
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        response = client.post(settings.onlyoffice_internal_url.rstrip("/") + "/coauthoring/CommandService.ashx",
                               json=payload | {"token": sign(payload)})
        response.raise_for_status()
        return response.json()
