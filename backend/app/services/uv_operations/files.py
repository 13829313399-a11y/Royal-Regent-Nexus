from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from PIL import Image, UnidentifiedImageError
from app.models import uv_operations as m
from . import common as c

MAX_FILE_BYTES = 32 * 1024 * 1024


def validate(name, content, mime, role):
    c.require(name and len(name) <= 200 and '/' not in name and '\\' not in name and '..' not in name and ':' not in name, "unsafe_filename", "文件名不能包含路径", 422)
    c.require(0 < len(content) <= MAX_FILE_BYTES, "file_size", "文件为空或超过 32 MB", 422)
    suffix = PurePath(name).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        expected = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix]
        expected_mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[expected]
        try:
            with Image.open(BytesIO(content)) as image:
                c.require(image.format == expected and image.width*image.height <= 16_000_000 and mime == expected_mime, "file_signature", "图片签名、MIME 或尺寸不符合要求", 422)
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise c.DomainError("file_signature", "无法识别图片内容", 422) from None
    elif suffix == ".pdf":
        c.require(content.startswith(b"%PDF-") and mime == "application/pdf", "file_signature", "PDF 签名或 MIME 不匹配", 422)
        c.require(role != "preview", "preview_format", "浏览器预览请上传已生成的 PNG/JPEG/WebP", 422)
    else:
        c.require(role == "production" and suffix in {".prn", ".prnx", ".prt", ".rip"} and mime == "application/octet-stream", "unsupported_file", "仅接收图片、PDF 或已生成的生产文件；不生成 PRN", 422)
        c.require(not content.startswith((b"PK\x03\x04", b"MZ", b"<script", b"<!DOCTYPE")), "file_signature", "不接受压缩包、可执行文件或网页内容", 422)
    return sha256(content).hexdigest()


def create(db, user, body, content):
    c.get(db, m.UvOpsProcessVersion, body.process_version_id)
    return c.record(c.add(db, m.UvOpsFileVersion, user, **c.values(body), content=content))


def confirm(db, user, entity_id, body):
    row = c.get(db, m.UvOpsFileVersion, entity_id, lock=True, version=body.expected_version)
    c.require(row.confirmed_at is None, "file_frozen", "文件版本已经确认；更改需上传新版本")
    row.confirmed_by, row.confirmed_at = user.id, m.now()
    row.first_article_evidence = body.first_article_evidence
    c.touch(row)
    return c.record(row)
