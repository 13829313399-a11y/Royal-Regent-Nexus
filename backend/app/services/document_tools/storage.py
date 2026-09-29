import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import settings
from app.services.document_tools.document_ir import ToolError

MIME = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "doc": "application/msword", "xls": "application/vnd.ms-excel", "zip": "application/zip", "json": "application/json", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def root() -> Path:
    location = Path(settings.document_tools_storage_dir).resolve()
    location.mkdir(parents=True, exist_ok=True)
    return location


def resolve(key: str) -> Path:
    base = root()
    value = (base / key).resolve()
    if not value.is_relative_to(base) or value == base:
        raise ToolError("INVALID_PATH", "文件路径无效")
    return value


def key_for(path: Path) -> str:
    return path.resolve().relative_to(root()).as_posix()


def safe_name(name: str, fallback: str = "document") -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")
    return name[:240] or fallback


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + secrets.token_hex(5) + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(temp, path)


def read_json(key: str, default=None):
    if not key:
        return default
    path = resolve(key)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def cipher() -> Fernet:
    # Shared storage key lets API and worker open only the supplied passwords.
    # This key and ciphertext are never served as artifacts.
    path = root() / ".password-key"
    if not path.exists():
        temporary = path.with_name(path.name + "." + secrets.token_hex(12) + ".tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(Fernet.generate_key())
                handle.flush()
                os.fsync(handle.fileno())
            # Publish an already complete key without replacing another process's key.
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    return Fernet(path.read_bytes())


def encrypt_password(value: str) -> str:
    return cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_password(value: str) -> str:
    return cipher().decrypt(value.encode("ascii")).decode("utf-8") if value else ""
